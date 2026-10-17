"""固定目录内的运行／AI 请求日志清单与只读 ZIP 导出。"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from . import vault_lifecycle


MAX_EXPORT_BYTES = 256 * 1024 * 1024
MAX_EXPORT_FILES = 1000
_ROOTS = {"runtime": ("logs",), "ai": ("错题", ".omrs", "logs")}
_NAMES = re.compile(r"[^/\\:\x00]+\.(?:log|jsonl)(?:\.\d+)?(?:\.gz)?", re.IGNORECASE)
_SHANGHAI = dt.timezone(dt.timedelta(hours=8))


class LogUnavailable(ValueError):
    status = 409


@contextlib.contextmanager
def _directory(vault, kind):
    """逐级拒绝链接；支持 dir_fd 时固定目录句柄，避免路径替换绕过。"""
    root = Path(os.path.realpath(vault))
    if os.open in os.supports_dir_fd and os.listdir in os.supports_fd and hasattr(os, "O_NOFOLLOW"):
        handles = []
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            handles.append(os.open(root, flags))
            for part in _ROOTS[kind]:
                handles.append(os.open(part, flags, dir_fd=handles[-1]))
        except (FileNotFoundError, NotADirectoryError):
            for handle in reversed(handles):
                os.close(handle)
            yield None
            return
        except BaseException:
            for handle in reversed(handles):
                os.close(handle)
            raise
        try:
            yield handles[-1]
        finally:
            for handle in reversed(handles):
                os.close(handle)
    else:
        directory = root
        for part in _ROOTS[kind]:
            directory /= part
            if directory.is_symlink() or not directory.is_dir():
                yield None
                return
        yield directory


def _file_stat(directory, name):
    if isinstance(directory, int):
        return os.stat(name, dir_fd=directory, follow_symlinks=False)
    return (directory / name).lstat()


def list_logs(vault):
    files = []
    with vault_lifecycle.lease(vault):
        for kind in _ROOTS:
            with _directory(vault, kind) as directory:
                if directory is None:
                    continue
                for name in os.listdir(directory):
                    if name.startswith('.') or not _NAMES.fullmatch(name):
                        continue
                    try:
                        info = _file_stat(directory, name)
                    except FileNotFoundError:
                        continue  # 日志轮换与清单读取可以同时发生。
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    modified = dt.datetime.fromtimestamp(info.st_mtime, dt.timezone.utc)
                    files.append({"id": f"{kind}:{name}", "kind": kind, "name": name,
                                  "size_bytes": info.st_size, "modified_at": modified.isoformat(),
                                  "modified_day": modified.astimezone(_SHANGHAI).date().isoformat()})
    files.sort(key=lambda row: (row["modified_at"], row["id"]), reverse=True)
    return {"files": files, "max_bytes": MAX_EXPORT_BYTES, "max_files": MAX_EXPORT_FILES}


@contextlib.contextmanager
def _open_log(vault, kind, name):
    with _directory(vault, kind) as directory:
        if directory is None:
            raise FileNotFoundError(name)
        info = _file_stat(directory, name)
        if not stat.S_ISREG(info.st_mode):
            raise FileNotFoundError(name)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        handle = os.open(name, flags, dir_fd=directory) if isinstance(directory, int) else os.open(directory / name, flags)
        with os.fdopen(handle, "rb") as source:
            opened = os.fstat(source.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise FileNotFoundError(name)
            yield source, opened


def create_log_export(vault, files):
    if not isinstance(files, list) or not files or any(not isinstance(item, str) for item in files):
        raise ValueError("请至少选择一份日志")
    files = list(dict.fromkeys(files))
    if len(files) > MAX_EXPORT_FILES:
        raise ValueError(f"每次最多导出 {MAX_EXPORT_FILES} 份日志，请分批选择")
    selected = []
    for identity in files:
        kind, separator, name = identity.partition(":")
        if not separator or kind not in _ROOTS or name.startswith('.') or not _NAMES.fullmatch(name) or ':' in name:
            raise ValueError("日志选择无效，请刷新列表后重试")
        selected.append((kind, name))
    handle, artifact = tempfile.mkstemp(prefix="omrs-logs-", suffix=".zip")
    os.close(handle)
    total = 0
    try:
        with vault_lifecycle.lease(vault), zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
            for kind, name in selected:
                try:
                    with _open_log(vault, kind, name) as (source, info):
                        total += info.st_size
                        if total > MAX_EXPORT_BYTES:
                            raise ValueError("日志总大小超过 256 MiB，请分批选择")
                        # 固定打开时的长度，避免持续追加的请求日志使导出无法结束。
                        remaining = info.st_size
                        modified = dt.datetime.fromtimestamp(info.st_mtime, _SHANGHAI)
                        if not 1980 <= modified.year <= 2107:
                            modified = dt.datetime(1980, 1, 1)
                        entry = zipfile.ZipInfo(f"{'运行日志' if kind == 'runtime' else 'AI请求日志'}/{name}", modified.timetuple()[:6])
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        entry.external_attr = 0o600 << 16
                        with archive.open(entry, "w") as target:
                            while remaining:
                                block = source.read(min(65536, remaining))
                                if not block:
                                    raise LogUnavailable("日志已变更，请刷新列表后重新选择")
                                target.write(block)
                                remaining -= len(block)
                except OSError as exc:
                    raise LogUnavailable("所选日志已删除或无法读取，请刷新列表后重新选择") from exc
        stamp = dt.datetime.now(_SHANGHAI).strftime("%Y%m%d-%H%M%S")
        return artifact, f"OMRS-logs-{stamp}.zip"
    except BaseException:
        os.unlink(artifact)
        raise
