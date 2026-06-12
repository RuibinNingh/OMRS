import datetime
import json

from .common import (
    MASTERY_HEADERS,
    SESSIONS_HEADERS,
    load_csv,
    mastery_path,
    omrs_data_dir,
    save_csv,
    sessions_path,
)
from .scheduling import generate_recommendations, schedule_questions


def _load_sessions(vault):
    return load_csv(sessions_path(vault), SESSIONS_HEADERS)


def _save_sessions(vault, rows):
    save_csv(sessions_path(vault), SESSIONS_HEADERS, rows)


def _resolve_session_id(existing_ids, base):
    if base not in existing_ids:
        return base
    for index in range(26):
        candidate = f"{base}-{chr(ord('A') + index)}"
        if candidate not in existing_ids:
            return candidate
    return f"{base}-{datetime.datetime.now().microsecond}"


def _decode_uids(raw):
    """解析 UIDs JSON，兼容旧格式（字符串列表）和新格式（对象列表）。"""
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(item.get("uid", ""))
    return result


def _decode_session_items(raw):
    """解析 UIDs JSON 为带来源信息的对象列表。

    返回: [{"uid": "...", "source": "due|proficiency"}, ...]
    旧格式（纯字符串）默认 source="due"。
    """
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            result.append({"uid": item, "source": "due"})
        elif isinstance(item, dict):
            result.append({
                "uid": item.get("uid", ""),
                "source": item.get("source", "due"),
            })
    return result


def _encode_session_items(items):
    """将带来源的 items 编码为 JSON 字符串。"""
    return json.dumps([
        {"uid": item.get("uid", item) if isinstance(item, dict) else item,
         "source": item.get("source", "due") if isinstance(item, dict) else "due"}
        for item in items
    ], ensure_ascii=False)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _active_session_uids(sessions):
    uids = set()
    for session in sessions:
        if session.get("Status", "active") != "active":
            continue
        uids.update(_decode_uids(session.get("UIDs", "[]")))
    return uids


def active_session_uids(vault):
    """Return UIDs already assigned to active persistent sessions."""
    return _active_session_uids(_load_sessions(vault))


def get_session_uid_sources(vault, session_id):
    """获取 session 中各 UID 的来源映射 {uid: source}。"""
    sessions = _load_sessions(vault)
    match = next((s for s in sessions if s["Session_ID"] == session_id), None)
    if not match:
        return {}
    items = _decode_session_items(match.get("UIDs", "[]"))
    return {item["uid"]: item["source"] for item in items if item["uid"]}


def create_session(vault, count=10, subject=None):
    """旧版创建 Session（保留兼容）。"""
    omrs_data_dir(vault)
    sessions = _load_sessions(vault)
    items = schedule_questions(vault, count, subject, _active_session_uids(sessions))
    existing = {session["Session_ID"] for session in sessions}
    base = f"EXP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    session_id = _resolve_session_id(existing, base)
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    uids = [item["UID"] for item in items]
    sessions.append(
        {
            "Session_ID": session_id,
            "Created_At": now_iso,
            "Subject_Filter": subject or "",
            "Count": str(len(uids)),
            "UIDs": json.dumps(uids, ensure_ascii=False),
            "Status": "active",
            "Completed_At": "",
        }
    )
    _save_sessions(vault, sessions)
    clean = [{key: value for key, value in item.items() if not key.startswith("_")} for item in items]
    return {
        "session_id": session_id,
        "created_at": now_iso,
        "subject_filter": subject or "",
        "count": len(uids),
        "status": "active",
        "completed_at": "",
        "items": clean,
    }


def create_session_from_selection(vault, selected_items, subject=None):
    """根据用户勾选的 items 创建 Session（带来源标记）。

    selected_items: [{"uid": "...", "source": "due|proficiency"}, ...]
    """
    omrs_data_dir(vault)
    sessions = _load_sessions(vault)
    selected_uids = [item["uid"] for item in selected_items if item.get("uid")]
    active_overlap = sorted(set(selected_uids) & _active_session_uids(sessions))
    if active_overlap:
        sample = "、".join(active_overlap[:10])
        extra = "..." if len(active_overlap) > 10 else ""
        raise RuntimeError(
            f"所选题目中有 {len(active_overlap)} 道已在进行中的 Session 中：{sample}{extra}"
        )
    existing = {session["Session_ID"] for session in sessions}
    base = f"EXP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    session_id = _resolve_session_id(existing, base)
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")

    sessions.append(
        {
            "Session_ID": session_id,
            "Created_At": now_iso,
            "Subject_Filter": subject or "",
            "Count": str(len(selected_items)),
            "UIDs": _encode_session_items(selected_items),
            "Status": "active",
            "Completed_At": "",
        }
    )
    _save_sessions(vault, sessions)

    from .scheduling import get_items_by_uids
    items = get_items_by_uids(vault, selected_uids)
    for item in items:
        match = next((s for s in selected_items if s["uid"] == item["uid"]), None)
        item["_source"] = match["source"] if match else "due"

    return {
        "session_id": session_id,
        "created_at": now_iso,
        "subject_filter": subject or "",
        "count": len(selected_items),
        "status": "active",
        "completed_at": "",
        "items": items,
    }


def list_sessions(vault, status=None):
    sessions = _load_sessions(vault)
    if status:
        sessions = [session for session in sessions if session.get("Status") == status]
    sessions.sort(key=lambda session: session.get("Created_At", ""), reverse=True)
    return [
        {
            "session_id": session["Session_ID"],
            "created_at": session.get("Created_At", ""),
            "subject_filter": session.get("Subject_Filter", ""),
            "count": _safe_int(session.get("Count", 0), 0),
            "status": session.get("Status", "active"),
            "completed_at": session.get("Completed_At", ""),
            "uids": _decode_uids(session.get("UIDs", "[]")),
        }
        for session in sessions
    ]


def get_session(vault, session_id):
    sessions = _load_sessions(vault)
    match = next((session for session in sessions if session["Session_ID"] == session_id), None)
    if not match:
        return None
    session_items = _decode_session_items(match.get("UIDs", "[]"))
    uid_source_map = {item["uid"]: item["source"] for item in session_items}
    uids = [item["uid"] for item in session_items]
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    row_map = {row["UID"]: row for row in rows}
    items = []
    for uid in uids:
        row = row_map.get(uid)
        if not row:
            items.append({"UID": uid, "_missing": True})
            continue
        items.append(
            {
                "UID": uid,
                "Subject": row.get("Subject", ""),
                "Category": row.get("Category", ""),
                "Difficulty": row.get("Difficulty", ""),
                "Mastery": row.get("Mastery", ""),
                "Current_Tag": row.get("Current_Tag", ""),
                "Last_Review": row.get("Last_Review", ""),
                "_source": uid_source_map.get(uid, "due"),
            }
        )
    return {
        "session_id": match["Session_ID"],
        "created_at": match.get("Created_At", ""),
        "subject_filter": match.get("Subject_Filter", ""),
        "count": _safe_int(match.get("Count", 0), 0),
        "status": match.get("Status", "active"),
        "completed_at": match.get("Completed_At", ""),
        "items": items,
    }


def delete_session(vault, session_id):
    sessions = _load_sessions(vault)
    before = len(sessions)
    sessions = [session for session in sessions if session["Session_ID"] != session_id]
    if len(sessions) == before:
        return False
    _save_sessions(vault, sessions)
    return True


def mark_session_completed(vault, session_id):
    sessions = _load_sessions(vault)
    changed = False
    for session in sessions:
        if session["Session_ID"] == session_id and session.get("Status") != "completed":
            session["Status"] = "completed"
            session["Completed_At"] = datetime.datetime.now().isoformat(timespec="seconds")
            changed = True
            break
    if changed:
        _save_sessions(vault, sessions)
    return changed
