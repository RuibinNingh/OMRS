import datetime
import os


_LOG_DIRS = {}


def _get_log_dir(vault: str) -> str:
    # 按 vault 缓存日志目录：单一全局变量会让同进程内处理的第二个 vault
    # 把日志写到第一个 vault 的目录里（串台）。以绝对路径为键各自缓存。
    key = os.path.abspath(vault)
    cached = _LOG_DIRS.get(key)
    if cached:
        return cached
    log_dir = os.path.join(key, "logs")
    os.makedirs(log_dir, exist_ok=True)
    _LOG_DIRS[key] = log_dir
    return log_dir


def _log_path(vault: str) -> str:
    today = datetime.date.today().isoformat()
    return os.path.join(_get_log_dir(vault), f"omrs_{today}.log")


def write_log(vault: str, event: str, detail: dict):
    """向当日日志文件追加一条结构化记录。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"[{now}] [{event}]"]
    for key, value in detail.items():
        parts.append(f"  {key}: {value}")
    entry = "\n".join(parts) + "\n\n"
    try:
        with open(_log_path(vault), "a", encoding="utf-8") as file:
            file.write(entry)
    except OSError:
        pass


def log_feedback(vault: str, uid: str, sub_score: int, is_correct: bool,
                 old_mastery: float, new_mastery: float, label: str, session_id: str):
    write_log(vault, "FEEDBACK", {
        "uid": uid,
        "session": session_id,
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
