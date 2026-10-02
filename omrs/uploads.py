"""16 MiB 分块上传暂存：引用绑定 Vault 世代与 Web 操作者，不进入学习数据。"""
import base64
import contextlib
import contextvars
import hashlib
import itertools
import json
import os
import re
import secrets
import stat
import shutil
import tempfile
import threading
import time
from pathlib import Path
from .vault_lifecycle import lease, storage

CHUNK_BYTES = 16 * 1024 * 1024
TTL_SECONDS = 3600
_LOCK = threading.RLock()
_OWNER = contextvars.ContextVar("omrs_upload_owner", default=None)
_ID = re.compile(r"upl_[0-9a-f]{32}")


@contextlib.contextmanager
def request_owner(owner):
    token = _OWNER.set(owner)
    try:
        yield
    finally:
        _OWNER.reset(token)


def _generation(vault):
    try:
        from .vault_lifecycle import generation
    except ImportError:
        return 0
    return generation(vault)


def _root(vault):
    key = hashlib.sha256(os.path.realpath(vault).encode()).hexdigest()
    parent = Path(tempfile.gettempdir()) / "omrs-upload-v1"
    parent.mkdir(exist_ok=True, mode=0o700)
    root = parent / key
    root.mkdir(exist_ok=True, mode=0o700)
    if parent.is_symlink() or root.is_symlink():
        raise ValueError("上传暂存目录不允许链接")
    return root


def _directory(vault, identity):
    if not isinstance(identity, str) or not _ID.fullmatch(identity):
        raise ValueError("上传引用不合法")
    directory = _root(vault) / identity
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("上传不存在或已到期")
    return directory


def _save(directory, state):
    temporary = directory / ("state." + secrets.token_hex(8) + ".tmp")
    with open(temporary, "x", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, directory / "state.json")


def _load(vault, identity, owner=None):
    directory = _directory(vault, identity)
    target = directory / "state.json"
    if target.is_symlink():
        raise ValueError("上传状态不允许链接")
    with open(target, encoding="utf-8") as source:
        state = json.load(source)
    if state["expires_at"] <= time.time():
        raise ValueError("上传已到期，请重新上传")
    if state["generation"] != _generation(vault):
        raise ValueError("题库已恢复，旧上传引用已失效")
    expected = _OWNER.get() if owner is None else owner
    if expected is not None and state["owner"] != expected:
        raise ValueError("上传引用不属于当前会话")
    return directory, state


def _cleanup(vault):
    # 每次最多检查 128 项，避免大量过期暂存阻塞正常上传。
    for directory in itertools.islice(_root(vault).iterdir(), 128):
        if not _ID.fullmatch(directory.name) or directory.is_symlink():
            continue
        try:
            with open(directory / "state.json", encoding="utf-8") as stream:
                expired = json.load(stream)["expires_at"] <= time.time()
            if expired:
                shutil.rmtree(directory)
        except (OSError, ValueError, KeyError):
            continue


@storage
def start(vault, filename="image", mime="", total_bytes=None, purpose="image", owner=None):
    if total_bytes is not None and (type(total_bytes) is not int or total_bytes < 0):
        raise ValueError("total_bytes 必须是非负整数")
    if purpose not in ("image", "create", "inbox", "annotate", "draft", "assistant", "backup"):
        raise ValueError("未知上传用途")
    with _LOCK:
        _cleanup(vault)
        root = _root(vault)
        if total_bytes is not None and total_bytes > max(0, shutil.disk_usage(root).free - 64 * 1024 * 1024):
            raise ValueError("暂存空间不足，无法接收此文件")
        identity = "upl_" + secrets.token_hex(16)
        directory = root / identity
        directory.mkdir(mode=0o700)
        state = {"upload_id": identity, "filename": os.path.basename(str(filename))[:200] or "image",
                 "mime": str(mime), "total_bytes": total_bytes, "purpose": purpose,
                 "generation": _generation(vault), "owner": owner if owner is not None else _OWNER.get(),
                 "expires_at": time.time() + TTL_SECONDS, "bytes": 0, "chunks": [], "complete": False}
        _save(directory, state)
    return {"upload_id": identity, "chunk_bytes": CHUNK_BYTES, "expires_at": state["expires_at"]}


@storage
def chunk(vault, upload_id, index, data, owner=None):
    if type(index) is not int or index < 0:
        raise ValueError("分块下标必须是非负整数")
    if not data or len(data) > CHUNK_BYTES:
        raise ValueError("上传分块必须为 1 字节到 16 MiB")
    digest = hashlib.sha256(data).hexdigest()
    with _LOCK:
        directory, state = _load(vault, upload_id, owner)
        if index < len(state["chunks"]):
            saved = state["chunks"][index]
            if saved != {"sha256": digest, "bytes": len(data)}:
                raise ValueError("同一上传分块的内容不同")
            return {"upload_id": upload_id, "index": index, "bytes": state["bytes"], "reused": True}
        if state["complete"] or index != len(state["chunks"]):
            raise ValueError("上传分块顺序不正确或已经完成")
        if state["total_bytes"] is not None and state["bytes"] + len(data) > state["total_bytes"]:
            raise ValueError("上传字节超过声明的文件长度")
        if len(data) > max(0, shutil.disk_usage(directory).free - 64 * 1024 * 1024):
            raise ValueError("暂存空间不足，无法接收此分块")
        with _open_content(directory / "content", writing=True) as target:
            target.truncate(state["bytes"])
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(directory / "content", 0o600)
        state["chunks"].append({"sha256": digest, "bytes": len(data)})
        state["bytes"] += len(data)
        _save(directory, state)
    return {"upload_id": upload_id, "index": index, "bytes": state["bytes"], "reused": False}


@storage
def complete(vault, upload_id, sha256=None, owner=None):
    with _LOCK:
        directory, state = _load(vault, upload_id, owner)
        if not state["bytes"] or (state["total_bytes"] is not None and state["bytes"] != state["total_bytes"]):
            raise ValueError("上传尚未接收完整文件")
        target = directory / "content"
        digest = hashlib.sha256()
        with _open_content(target) as source:
            if os.fstat(source.fileno()).st_size != state["bytes"]:
                raise ValueError("上传原件长度与已接收分块不一致")
            prefix = source.read(16)
            digest.update(prefix)
            while block := source.read(65536):
                digest.update(block)
        actual = digest.hexdigest()
        if sha256 is not None and sha256 != actual:
            raise ValueError("上传文件 SHA-256 不匹配")
        if state["purpose"] != "backup":
            actual_mime = ("image/png" if prefix.startswith(b"\x89PNG\r\n\x1a\n") else
                           "image/jpeg" if prefix.startswith(b"\xff\xd8\xff") else
                           "image/gif" if prefix.startswith((b"GIF87a", b"GIF89a")) else None)
            if actual_mime is None:
                raise ValueError("暂存图只支持 PNG / JPEG / GIF")
            state["mime"] = actual_mime
        state.update(complete=True, sha256=actual)
        _save(directory, state)
        return {"upload_ref": upload_id, "bytes": state["bytes"], "mime": state["mime"],
                "sha256": actual, "filename": state["filename"], "expires_at": state["expires_at"]}


@storage
def resolve(vault, reference, owner=None, purpose=None):
    identity = reference.get("upload_ref") if isinstance(reference, dict) else reference
    with _LOCK:
        directory, state = _load(vault, identity, owner)
        if not state["complete"]:
            raise ValueError("上传尚未完成")
        allowed = ("backup",) if purpose == "backup" else ("image", purpose)
        if purpose is not None and state["purpose"] not in allowed:
            raise ValueError("上传引用用途与当前操作不一致")
        target = directory / "content"
        if target.is_symlink() or not target.is_file() or target.stat().st_size != state["bytes"]:
            raise ValueError("上传原件不存在或已变化")
        return {**state, "path": str(target)}


def copy_to(vault, reference, target, owner=None, purpose=None):
    """锁外分块校验复制；前后短租约核验上传身份、期限和题库世代。"""
    state = resolve(vault, reference, owner, purpose)
    digest, size = hashlib.sha256(), 0
    with _open_content(state["path"]) as source:
        while block := source.read(65536):
            if size + len(block) > state["bytes"]:
                raise ValueError("上传原件长度超过声明的已完成字节，已拒绝消费")
            target.write(block)
            digest.update(block)
            size += len(block)
    if size != state["bytes"] or digest.hexdigest() != state["sha256"]:
        raise ValueError("上传原件校验失败")
    with lease(vault, state["generation"]):
        current = resolve(vault, reference, owner, purpose)
        if (current["bytes"], current["sha256"]) != (state["bytes"], state["sha256"]):
            raise ValueError("上传状态在读取期间变化，已拒绝消费")
    return state


@storage
def read(vault, reference, owner=None):
    state = resolve(vault, reference, owner)
    with _open_content(state["path"]) as source:
        data = source.read()
    if hashlib.sha256(data).hexdigest() != state["sha256"]:
        raise ValueError("上传原件校验失败")
    return data


@storage
def image_data_url(vault, reference, owner=None, purpose=None):
    state = resolve(vault, reference, owner, purpose)
    if state["purpose"] == "backup":
        raise ValueError("备份上传不能用作图片")
    return "data:" + state["mime"] + ";base64," + base64.b64encode(read(vault, reference, owner)).decode("ascii")


@contextlib.contextmanager
def _open_content(path, writing=False):
    flags = os.O_RDWR | os.O_CREAT if writing else os.O_RDONLY
    descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(descriptor)
        identity = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino) or stat.S_ISLNK(identity.st_mode):
            raise ValueError("上传原件不是安全普通文件")
        with os.fdopen(descriptor, "r+b" if writing else "rb") as stream:
            descriptor = None
            if writing:
                stream.seek(0, os.SEEK_END)
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)


@storage
def stage_file(vault, path, filename="image", mime="", purpose="image"):
    """旧 multipart/data URL 流式转换成同一暂存引用，不保留整批图片字节。"""
    result = start(vault, filename, mime, os.path.getsize(path), purpose)
    identity = result["upload_id"]
    with open(path, "rb") as source:
        index = 0
        while data := source.read(CHUNK_BYTES):
            chunk(vault, identity, index, data)
            index += 1
    return complete(vault, identity)
