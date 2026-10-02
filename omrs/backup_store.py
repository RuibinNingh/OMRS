"""全库一致备份和可恢复目录交换；维护记录不在被替换的错题目录内。"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import unicodedata
import uuid
import zipfile
from pathlib import Path

from .common import questions_root
from .locking import write_lock
from .vault_lifecycle import exclusive, lease, generation, advance_generation, maintenance_dir, atomic_json, fsync_dir, maintenance_task

MAX_EXPANDED = 32 * 1024**3
MAX_FILES = 200_000
_ID = re.compile(r"restore-[a-f0-9]{32}")


def _hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _identity(path):
    value = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(value.st_mode) or os.path.islink(path):
        raise ValueError("恢复目录不是普通目录，已拒绝交换")
    return [value.st_dev, value.st_ino]


def _files(root):
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            if os.path.islink(os.path.join(current, name)):
                raise ValueError("备份目录含链接，请先处理")
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for name in files:
            path = os.path.join(current, name)
            info = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"备份不支持链接或特殊文件：{name}")
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if relative == ".omrs/backup_manifest.json":
                continue
            result[relative] = (path, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return result


def _tree_digest(root, sync=False):
    result = {}
    for name, entry in _files(root).items():
        result[name] = {"size": entry[3], "sha256": _hash(entry[0])}
        if sync:
            with open(entry[0], "rb") as file:
                os.fsync(file.fileno())
    if sync:
        for current, _, _ in os.walk(root, topdown=False):
            fsync_dir(current)
    return result


def _sqlite(path):
    with open(path, "rb") as file:
        header = file.read(16)
    if header == b"SQLite format 3\x00":
        return True
    if path.endswith(".db"):
        raise ValueError(f"数据库文件格式不可识别：{os.path.basename(path)}")
    return False


def _snapshot(source, target):
    with contextlib.ExitStack() as stack:
        original = stack.enter_context(contextlib.closing(sqlite3.connect(
            Path(source).absolute().as_uri() + "?mode=ro", uri=True, timeout=30)))
        destination = stack.enter_context(contextlib.closing(sqlite3.connect(target)))
        if original.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("数据库校验失败，不能创建可信备份")
        original.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("数据库快照不完整")
        version = original.execute("PRAGMA user_version").fetchone()[0]
    with open(target, "rb") as file:
        os.fsync(file.fileno())
    return version


def _capture(vault, staging):
    from .projections import rebuild_projection, export_legacy_csv
    root = questions_root(vault)
    rebuild_projection(vault)
    export_legacy_csv(vault)
    with contextlib.ExitStack() as stack:
        guards = {}
        for name, entry in _files(root).items():
            if _sqlite(entry[0]):
                db = stack.enter_context(contextlib.closing(sqlite3.connect(
                    Path(entry[0]).absolute().as_uri() + "?mode=ro", uri=True, timeout=30)))
                guards[name] = (db, db.execute("PRAGMA data_version").fetchone()[0])
        return _capture_guarded(vault, staging, guards)


def _capture_guarded(vault, staging, guards):
    root = questions_root(vault)
    inventory = _files(root)
    databases = {name for name, entry in inventory.items() if _sqlite(entry[0])}
    if databases != set(guards):
        raise ValueError("备份期间外部文件数据库集合发生变化，请重试")
    excluded = {name + suffix for name in databases for suffix in ("-wal", "-shm", "-journal")}
    manifest = {"format_version": 2, "snapshot_id": uuid.uuid4().hex,
                "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "vault_generation": generation(vault), "files": []}
    for name, before in inventory.items():
        if name in excluded:
            continue
        destination = os.path.join(staging, "错题", *name.split("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        record = {"path": "错题/" + name}
        if name in databases:
            record.update(sqlite_snapshot="backup", schema_version=_snapshot(before[0], destination))
        else:
            with open(before[0], "rb") as source, open(destination, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if _hash(before[0]) != _hash(destination):
                raise ValueError("备份期间外部文件改变，请重试")
        record.update(size=os.path.getsize(destination), sha256=_hash(destination))
        manifest["files"].append(record)
    after = _files(root)
    for name, (db, version) in guards.items():
        if db.execute("PRAGMA data_version").fetchone()[0] != version or after.get(name, (None,))[1:3] != inventory[name][1:3]:
            raise ValueError("备份期间外部文件数据库改变，请重试")
    # SQLite 自身 WAL/checkpoint 不属于普通文件修改；所有普通文件需保持同一身份。
    before_plain = {name: entry[1:] for name, entry in inventory.items() if name not in databases and name not in excluded}
    after_plain = {name: entry[1:] for name, entry in after.items() if name not in databases and name not in excluded}
    if before_plain != after_plain:
        raise ValueError("备份期间外部文件清单改变，请重试")
    manifest_path = os.path.join(staging, "错题", ".omrs", "backup_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    atomic_json(manifest_path, manifest)
    return manifest


def create_backup(vault):
    if not os.path.isdir(questions_root(vault)):
        raise ValueError("错题目录不存在")
    staging = tempfile.mkdtemp(prefix="omrs-backup-stage-")
    archive_path = None
    started = time.monotonic()
    try:
        with exclusive(vault), write_lock():
            for attempt in range(3):
                try:
                    manifest = _capture(vault, staging)
                    break
                except ValueError as exc:
                    if "外部文件" not in str(exc) or attempt == 2:
                        raise
                    shutil.rmtree(os.path.join(staging, "错题"), ignore_errors=True)
        frozen = time.monotonic() - started
        descriptor, archive_path = tempfile.mkstemp(prefix="omrs-backup-", suffix=".zip")
        os.close(descriptor)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for current, _, files in os.walk(staging):
                for name in files:
                    path = os.path.join(current, name)
                    archive.write(path, os.path.relpath(path, staging).replace(os.sep, "/"))
        filename = "OMRS-backup-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
        return archive_path, filename, "backup-" + manifest["snapshot_id"], frozen
    except BaseException:
        if archive_path:
            with contextlib.suppress(OSError):
                os.unlink(archive_path)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _safe_names(archive, free_bytes):
    if len(archive.infolist()) > MAX_FILES:
        raise ValueError("备份文件数量超过限制")
    entries, names, total = [], set(), 0
    for info in archive.infolist():
        raw = info.filename.replace("\\", "/")
        parts = raw.rstrip("/").split("/")
        if not parts or parts[0] != "错题" or any(p in ("", ".", "..") for p in parts) or ":" in raw or "\x00" in raw:
            raise ValueError("备份路径不合法")
        key = unicodedata.normalize("NFC", "/".join(parts)).casefold()
        if key in names:
            raise ValueError("备份包含重复或冲突路径")
        names.add(key)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
            raise ValueError("备份包含链接或特殊文件")
        if not info.is_dir():
            total += info.file_size
            entries.append(info)
    if len(entries) > MAX_FILES or total > MAX_EXPANDED or total + 64 * 1024**2 > free_bytes:
        raise ValueError("备份展开大小、文件数或可用空间超限")
    if not entries or not any(info.filename.replace("\\", "/").startswith("错题/.omrs/") for info in entries):
        raise ValueError("备份缺少错题/.omrs数据目录")
    return entries, total


def _validate_manifest(staging):
    root = os.path.join(staging, "错题")
    path = os.path.join(root, ".omrs", "backup_manifest.json")
    if not os.path.isfile(path):
        return False
    manifest = _read(path)
    if manifest.get("format_version") != 2 or not isinstance(manifest.get("files"), list):
        raise ValueError("备份清单版本不受支持")
    expected = set()
    for record in manifest["files"]:
        name = record.get("path", "")
        parts = name.split("/")
        if not name.startswith("错题/") or any(p in ("", ".", "..") for p in parts):
            raise ValueError("备份清单路径不合法")
        target = os.path.join(staging, *parts)
        if not os.path.isfile(target) or os.path.getsize(target) != record.get("size") or _hash(target) != record.get("sha256"):
            raise ValueError("备份文件与哈希清单不匹配")
        if name in expected:
            raise ValueError("备份清单含重复文件")
        expected.add(name)
    actual = {"错题/" + name for name in _files(root)}
    if expected != actual:
        raise ValueError("备份清单与文件集合不匹配")
    return True


def _normalize_databases(staging):
    root = os.path.join(staging, "错题")
    databases = [(name, entry[0]) for name, entry in _files(root).items() if _sqlite(entry[0])]
    for name, path in databases:
        temporary = path + ".snapshot"
        _snapshot(path, temporary)
        os.replace(temporary, path)
        for suffix in ("-wal", "-shm", "-journal"):
            with contextlib.suppress(FileNotFoundError):
                os.unlink(path + suffix)
    ledger = os.path.join(root, ".omrs", "ledger.db")
    if os.path.isfile(ledger):
        from .ledger import verify_ledger
        result = verify_ledger(staging)
        if not result["valid"]:
            raise ValueError("备份Ledger提交链损坏")


def _operation(vault, identity):
    if not isinstance(identity, str) or not _ID.fullmatch(identity):
        raise ValueError("restore_id 不合法")
    path = os.path.join(maintenance_dir(vault), identity)
    if os.path.islink(path):
        raise ValueError("恢复暂存目录不允许链接")
    return path


def prepare_import(vault, payload, filename="backup.zip"):
    identity = "restore-" + uuid.uuid4().hex
    operation = _operation(vault, identity)
    os.makedirs(operation, mode=0o700)
    zip_path = os.path.join(operation, "upload.zip")
    staging = os.path.join(operation, "staging")
    try:
        if isinstance(payload, (str, os.PathLike)):
            with open(payload, "rb") as source, open(zip_path, "wb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
        else:
            with open(zip_path, "wb") as target:
                target.write(payload)
        os.makedirs(staging)
        with zipfile.ZipFile(zip_path) as archive:
            entries, total = _safe_names(archive, shutil.disk_usage(operation).free)
            for info in entries:
                destination = os.path.join(staging, *info.filename.replace("\\", "/").split("/"))
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                with archive.open(info) as source, open(destination, "xb") as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
        has_manifest = _validate_manifest(staging)
        _normalize_databases(staging)
        from .config_repository import initialize
        from .inbox_commit import recover_pending
        initialize(staging)
        recover_pending(staging)
        from .indexing import build_index
        count = len(build_index(staging))
        preview = {"filename": os.path.basename(filename), "files": len(entries), "bytes": total,
                   "md_files": sum(info.filename.lower().endswith(".md") for info in entries),
                   "image_files": sum(os.path.splitext(info.filename)[1].lower() in {".png", ".jpg", ".jpeg", ".gif"} for info in entries),
                   "has_attachments": any(info.filename.startswith("错题/附件/") for info in entries),
                   "manifest_verified": has_manifest, "question_count": count}
        durable = _tree_digest(os.path.join(staging, "错题"), sync=True)
        state = {"staging_digest": durable, "restore_id": identity, "preview": preview, "created_at": time.time(), "expires_at": time.time() + 3600,
                 "generation": generation(vault), "archive_hash": _hash(zip_path), "staging_identity": _identity(os.path.join(staging, "错题")),
                 "phase": "prepared"}
        with lease(vault):
            state["generation"] = generation(vault)
            atomic_json(os.path.join(operation, "preview.json"), state)
        return {"status": "ok", "restore_id": identity, "preview": preview}
    except BaseException:
        shutil.rmtree(operation, ignore_errors=True)
        raise


def _check_journal(vault, journal):
    operation = _operation(vault, journal["restore_id"])
    target = questions_root(vault)
    paths = {"target": target, "old": os.path.join(operation, "old"), "new": os.path.join(operation, "staging", "错题")}
    for key, path in paths.items():
        if journal.get(key) != path or os.path.islink(path):
            raise ValueError("恢复记录目录身份不合法，已停止启动")
    return operation


def _recover_locked(vault, journal):
    if journal.get("phase") not in {"prepared", "old_moved", "new_installed", "committed"}:
        raise ValueError("恢复记录阶段不合法，已停止启动")
    operation = _check_journal(vault, journal)
    target, old, new = journal["target"], journal["old"], journal["new"]
    if journal["phase"] == "committed":
        if not os.path.isdir(target) or _identity(target) != journal["new_identity"]:
            raise ValueError("已提交恢复的新目录身份不明确，已停止启动")
        if os.path.exists(old):
            if _identity(old) != journal["old_identity"]:
                raise ValueError("回滚目录身份不明确，已保留所有恢复材料")
            shutil.rmtree(old)
        state = _read(os.path.join(operation, "preview.json"))
        state["phase"] = "committed"
        state["generation"] = generation(vault)
        atomic_json(os.path.join(operation, "preview.json"), state)
    else:
        if os.path.exists(old):
            if _identity(old) != journal["old_identity"]:
                raise ValueError("旧库身份不明确，已停止启动")
            if os.path.exists(target):
                if _identity(target) != journal["new_identity"] or os.path.exists(new):
                    raise ValueError("未提交恢复的目录冲突，已停止启动")
                os.replace(target, new)
            os.replace(old, target)
        elif not os.path.isdir(target) or _identity(target) != journal["old_identity"]:
            if journal["old_identity"] is not None:
                raise ValueError("未提交恢复找不到旧库，已停止启动")
            if os.path.exists(target):
                if _identity(target) != journal["new_identity"] or os.path.exists(new):
                    raise ValueError("新目录身份不明确，已停止启动")
                os.replace(target, new)
        state = _read(os.path.join(operation, "preview.json"))
        state["generation"] = generation(vault)
        atomic_json(os.path.join(operation, "preview.json"), state)
    fsync_dir(os.path.realpath(vault))
    fsync_dir(operation)
    fsync_dir(os.path.dirname(new))
    os.unlink(os.path.join(maintenance_dir(vault), "restore-journal.json"))
    fsync_dir(maintenance_dir(vault))


def recover_restore(vault, allow_recovery=True):
    path = os.path.join(os.path.realpath(vault), ".omrs-maintenance", "restore-journal.json")
    if not os.path.isfile(path):
        return False
    if not allow_recovery:
        raise ValueError("题库有未完成恢复，请先正常启动恢复，不能只读盘点")
    with exclusive(vault), write_lock():
        _recover_locked(vault, _read(path))
    return True


def _invalidate(vault):
    from . import security, optimization
    from .common import reset_tuning_cache
    reset_tuning_cache(vault)
    invalidate = getattr(security, "invalidate_vault", None)
    if invalidate:
        invalidate(vault)
    from .agent import runtime
    with runtime._RT_LOCK:
        old = runtime._RUNTIMES.pop(os.path.abspath(vault), None)
    if old:
        for run in list(old.runs.values()):
            run.abort.set()
            for pending in list(run.pending.values()):
                event = getattr(pending, "event", None)
                if event:
                    event.set()
    with optimization._LOCK:
        optimization._SCANS.clear()
        optimization._BACKUP_TOKENS.clear()
        optimization._JOBS.clear()
    from .config_repository import initialize
    initialize(vault)
    from .projections import rebuild_projection
    rebuild_projection(vault, force=True)
    runtime.get_runtime(vault)
    from . import runtime_records
    runtime_records.recover_interrupted(vault)


def restore(vault, identity, confirm=False):
    if not confirm:
        raise ValueError("恢复备份需要 confirm=true")
    operation = _operation(vault, identity)
    try:
        state = _read(os.path.join(operation, "preview.json"))
    except FileNotFoundError as exc:
        raise ValueError("restore_id 不存在或已过期") from exc
    if state["phase"] == "committed":
        return {"status": "ok", "restored": True, "question_count": state["preview"]["question_count"],
                "vault_generation": state["generation"], "reauth_required": True, "reused": True}
    if state["expires_at"] <= time.time():
        raise ValueError("恢复预检已过期，请重新导入")
    if _hash(os.path.join(operation, "upload.zip")) != state["archive_hash"]:
        raise ValueError("恢复预检原件被修改")
    journal_path = os.path.join(maintenance_dir(vault), "restore-journal.json")
    target, old, new = questions_root(vault), os.path.join(operation, "old"), os.path.join(operation, "staging", "错题")
    with exclusive(vault), write_lock():
        if state["generation"] != generation(vault):
            raise ValueError("题库已变化，请重新预检备份")
        from .traincontrol import registration, Controller
        managed = registration(vault)
        if managed and (Controller(managed).state().get("operation") or {}).get("state") == "running":
            raise ValueError("受管检测操作进行中，请完成后再恢复题库")
        if os.path.exists(journal_path):
            raise ValueError("已有恢复尚未收束")
        if _identity(new) != state["staging_identity"] or _tree_digest(new) != state["staging_digest"]:
            raise ValueError("预检目录身份已变化")
        from . import workspace_sync
        scanner_thread = getattr(workspace_sync.start_workspace_scanner, "_thread", None)
        resume_scanner = bool(scanner_thread and scanner_thread.is_alive())
        workspace_sync.stop_workspace_scanner()
        current = advance_generation(vault)
        with maintenance_task(vault):
            journal = {"restore_id": identity, "phase": "prepared", "generation": current,
                       "target": target, "old": old, "new": new,
                       "old_identity": _identity(target) if os.path.isdir(target) else None, "new_identity": _identity(new)}
            try:
                atomic_json(journal_path, journal)
                if os.path.exists(target):
                    os.replace(target, old)
                    fsync_dir(os.path.dirname(target))
                    fsync_dir(operation)
                journal["phase"] = "old_moved"
                atomic_json(journal_path, journal)
                os.replace(new, target)
                fsync_dir(os.path.dirname(target))
                fsync_dir(os.path.dirname(new))
                journal["phase"] = "new_installed"
                atomic_json(journal_path, journal)
                # 在可回退阶段验证运行库，成功后才提交目录交换。
                _invalidate(vault)
                journal["phase"] = "committed"
                atomic_json(journal_path, journal)
            except BaseException:
                persisted = _read(journal_path) if os.path.isfile(journal_path) else None
                if persisted and persisted["phase"] == "committed":
                    # 提交标记已写入：保留新库，清理可在启动时重试。
                    if resume_scanner:
                        workspace_sync.start_workspace_scanner(vault)
                    return {"status": "ok", "restored": True, "cleanup_pending": True,
                            "question_count": state["preview"]["question_count"],
                            "vault_generation": current, "reauth_required": True}
                if persisted:
                    _recover_locked(vault, persisted)
                else:
                    state["generation"] = current
                    atomic_json(os.path.join(operation, "preview.json"), state)
                _invalidate(vault)
                if resume_scanner:
                    workspace_sync.start_workspace_scanner(vault)
                raise
            cleanup_pending = False
            try:
                _recover_locked(vault, journal)
            except OSError:
                cleanup_pending = True
            if resume_scanner:
                workspace_sync.start_workspace_scanner(vault)
    return {"status": "ok", "restored": True, "question_count": state["preview"]["question_count"],
            "vault_generation": current, "reauth_required": True, "cleanup_pending": cleanup_pending}
