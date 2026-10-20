"""尽力写入的诊断日志：有界轮换、并发串行与固定故障提示。"""
import contextlib
import datetime
import errno
import logging
import os
from pathlib import Path
import re
import stat
import threading
import time


MAX_LOG_BYTES = 8 * 1024 * 1024
LOG_BACKUPS = 3
RUNTIME_KEEP_DAYS = 30
RUNTIME_MAX_BYTES = 64 * 1024 * 1024
SHANGHAI = datetime.timezone(datetime.timedelta(hours=8))
_RUNTIME_NAME = re.compile(r"omrs_(\d{4}-\d{2}-\d{2})\.log(?:\.[1-3])?$")
_WRITE_LOCK = threading.RLock()
_LAST_WARNING = None


def _warn_failure():
    global _LAST_WARNING
    now = time.monotonic()
    if _LAST_WARNING is None or now - _LAST_WARNING >= 60:
        _LAST_WARNING = now
        logging.getLogger("omrs.logs").warning("诊断日志暂时无法写入或清理，请检查存储；业务结果不受影响。")


def _regular(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise OSError("日志路径不是普通文件")
    return info


@contextlib.contextmanager
def _directory_lock(directory):
    """同进程线程与独立 CLI 共用目录锁，轮换时不持有长期打开的日志句柄。"""
    if any(part.is_symlink() for part in (directory, *directory.parents)):
        raise OSError("日志目录不允许符号链接")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / ".omrs-logs.lock"
    _regular(path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("日志锁不是普通文件")
        if os.name == "nt":
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
        else:
            import fcntl
        deadline = time.monotonic() + 2
        while True:
            try:
                if os.name == "nt":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise OSError("诊断日志锁等待超时") from None
                time.sleep(0.02)
        yield
    finally:
        try:
            if locked:
                if os.name == "nt":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _rotate(path, size):
    for index in range(1, LOG_BACKUPS + 1):
        backup = Path(f"{path}.{index}")
        previous = _regular(backup)
        if previous is not None and previous.st_size > MAX_LOG_BYTES:
            backup.unlink()
    info = _regular(path)
    if info is None or info.st_size + size <= MAX_LOG_BYTES:
        return
    for index in range(LOG_BACKUPS, 0, -1):
        source = path if index == 1 else Path(f"{path}.{index - 1}")
        target = Path(f"{path}.{index}")
        _regular(target)
        previous = _regular(source)
        if previous is not None:
            if previous.st_size > MAX_LOG_BYTES:
                source.unlink()  # 旧版本的超限文件也不能无限占用轮换空间。
            else:
                os.replace(source, target)


def _prune_runtime(directory, current, today):
    files = []
    for path in directory.iterdir():
        match = _RUNTIME_NAME.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        try:
            day = datetime.date.fromisoformat(match[1])
        except ValueError:
            continue
        info = path.stat()
        if path != current and (today - day).days >= RUNTIME_KEEP_DAYS:
            path.unlink()
        else:
            files.append((day, -int(path.suffix[1:]) if path.suffix[1:].isdigit() else 0, path, info.st_size))
    total = sum(item[3] for item in files)
    for _, _, path, size in sorted(files):
        if total <= RUNTIME_MAX_BYTES:
            break
        if path != current:
            path.unlink()
            total -= size


def append_log(path, entry, *, runtime_day=None):
    """完整追加一条有界记录；失败只节流提示，不能把已完成业务变成失败。"""
    path = Path(os.path.abspath(path))
    body = entry.encode("utf-8", "replace")
    with _WRITE_LOCK:
        try:
            if len(body) > MAX_LOG_BYTES:
                raise ValueError("单条诊断记录超过大小上限")
            with _directory_lock(path.parent):
                _rotate(path, len(body))
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                descriptor = os.open(path, flags, 0o600)
                with os.fdopen(descriptor, "ab") as file:
                    if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                        raise OSError("日志路径不是普通文件")
                    file.write(body)
                if runtime_day is not None:
                    _prune_runtime(path.parent, path, runtime_day)
            return True
        except (OSError, ValueError):
            _warn_failure()
            return False


def _get_log_dir(vault: str) -> str:
    return os.path.join(os.path.abspath(vault), "logs")


def _log_path(vault: str) -> str:
    today = datetime.datetime.now(SHANGHAI).date().isoformat()
    return os.path.join(_get_log_dir(vault), f"omrs_{today}.log")


def write_log(vault: str, event: str, detail: dict):
    """向当日日志文件追加一条结构化记录。"""
    now = datetime.datetime.now(SHANGHAI)
    parts = [f"[{now.isoformat(sep=' ', timespec='seconds')}] [{event}]"]
    for key, value in detail.items():
        parts.append(f"  {key}: {value}")
    entry = "\n".join(parts) + "\n\n"
    path = os.path.join(_get_log_dir(vault), f"omrs_{now.date().isoformat()}.log")
    return append_log(path, entry, runtime_day=now.date())


def log_feedback(vault: str, uid: str, sub_score: int, is_correct: bool,
                 old_mastery: float, new_mastery: float, label: str, session_id: str,
                 *, question_id="", commit_id=""):
    write_log(vault, "FEEDBACK", {
        "uid": uid,
        "session": session_id,
        "question_id": question_id,
        "commit_id": commit_id,
        "sub_score": sub_score,
        "correct": is_correct,
        "old_mastery": round(old_mastery, 4),
        "new_mastery": round(new_mastery, 4),
        "label": label,
    })


def log_schedule(vault: str, count: int, subject: str, items: list):
    uids = [item.get("UID", item.get("uid", "")) for item in items]
    write_log(vault, "SCHEDULE", {
        "subject": subject or "全科",
        "requested": count,
        "returned": len(items),
        "uids": ", ".join(uids),
    })


def log_index(vault: str, added: int, updated: int, total: int):
    write_log(vault, "INDEX", {
        "added": added,
        "updated": updated,
        "total": total,
    })
