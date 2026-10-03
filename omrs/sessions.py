import datetime
import json

from .data_repository import IdentityConflict, mastery_rows, history_rows, session_rows, session_row, resolve_question, storage_write
from .ledger import append_commit, canonical_json, connect
from .projections import rebuild_projection
from .scheduling import schedule_questions
from .vault_lifecycle import storage


def _load_sessions(vault):
    return session_rows(vault)


def _reserved_session_ids(vault, db=None):
    """计划编号不可复用：已撤销或被状态恢复移除的计划仍占用原编号。"""
    if db is None:
        with connect(vault) as own:
            return _reserved_session_ids(vault, own)
    reserved = {row[0] for row in db.execute("SELECT session_id FROM session_projection")}
    for row in db.execute("SELECT result_json FROM op_results WHERE op_id LIKE 'mcp:session:%'"):
        session_id = json.loads(row[0]).get("session_id")
        if session_id:
            reserved.add(session_id)
    for row in db.execute("SELECT commit_type,payload_json FROM commits WHERE commit_type IN ('session.create','legacy.bootstrap')"):
        payload = json.loads(row["payload_json"])
        if row["commit_type"] == "session.create":
            session_id = (payload.get("session") or payload).get("session_id")
            if session_id:
                reserved.add(session_id)
        else:
            reserved.update(session["Session_ID"] for session in payload.get("session_rows", []) if session.get("Session_ID"))
    return reserved


def _resolve_session_id(existing_ids, base):
    if base not in existing_ids:
        return base
    for index in range(26):
        candidate = f"{base}-{chr(ord('A') + index)}"
        if candidate not in existing_ids:
            return candidate
    suffix = datetime.datetime.now().microsecond
    while f"{base}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base}-{suffix}"


def _decode_session_items(raw):
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    return [{"uid": item, "source": "due"} if isinstance(item, str) else dict(item)
            for item in values if isinstance(item, (str, dict))]


def _decode_uids(raw):
    return [item.get("uid", "") for item in _decode_session_items(raw)]


def _encode_session_items(items):
    return canonical_json(items)


def _session_feedback_progress(session, history, suspended_uids=None):
    # 无 Ledger 的迁移夹具兼容；正式进度由稳定身份 entries 派生。
    visible = list(dict.fromkeys(u for u in _decode_uids(session.get("UIDs", "[]")) if u and u not in (suspended_uids or set())))
    submitted = {row.get("UID") for row in history if row.get("Session_ID") == session.get("Session_ID")}
    done = [uid for uid in visible if uid in submitted]
    pending = [uid for uid in visible if uid not in submitted]
    return {"feedback_uids": done, "pending_uids": pending, "feedback_count": len(done),
            "pending_count": len(pending), "feedback_complete": bool(visible) and not pending}


def _entries(vault, session, questions=None, submitted=None):
    if submitted is None:
        with connect(vault) as db:
            submitted = {r[0] for r in db.execute("SELECT DISTINCT question_id FROM history_projection WHERE session_id=?", (session["Session_ID"],))}
    result = []
    for index, saved in enumerate(_decode_session_items(session.get("UIDs", "[]"))):
        qid = saved.get("question_id") or ""
        row = (questions.get(qid) if questions is not None else resolve_question(vault, question_id=qid, include_archived=True)) if qid else None
        availability = "unresolved" if not qid else "archived" if not row or row["archived"] else "suspended" if row["suspended"] else "active"
        result.append({"entry_id": saved.get("entry_id") or f"{session['Session_ID']}:{index}",
                       "question_id": qid, "uid_at_creation": saved.get("uid_at_creation") or saved.get("uid", ""),
                       "uid": row["uid"] if row else saved.get("uid", ""), "source": saved.get("source", "due"),
                       "availability": availability, "feedback_submitted": bool(qid and qid in submitted)})
    return result


def _progress(entries):
    required = [entry for entry in entries if entry["availability"] != "suspended"]
    done = [e["uid"] for e in required if e["feedback_submitted"]]
    pending = [e["uid"] for e in required if not e["feedback_submitted"]]
    return {"feedback_uids": done, "pending_uids": pending, "feedback_count": len(done),
            "pending_count": len(pending), "feedback_complete": bool(required) and not pending
            and all(e["availability"] != "unresolved" for e in required)}


@storage
def active_session_uids(vault):
    return {entry["uid"] for session in _load_sessions(vault) if session["Status"] == "active"
            for entry in _entries(vault, session) if entry["availability"] == "active"}


def _active_session_uids(sessions):
    return {uid for s in sessions if s.get("Status", "active") == "active" for uid in _decode_uids(s.get("UIDs", "[]"))}


@storage
def get_session_uid_sources(vault, session_id):
    session = get_session(vault, session_id)
    return {e["uid"]: e["source"] for e in session["entries"] if e["availability"] == "active"} if session else {}


@storage_write
def create_session(vault, count=10, subject=None):
    rows = schedule_questions(vault, count, subject, active_session_uids(vault))
    if not rows:
        return {"session_id": "", "count": 0, "items": [], "entries": []}
    return create_session_from_selection(vault, [{"question_id": row.get("question_id"), "uid": row["UID"], "source": "due"} for row in rows], subject)


@storage_write
def create_session_from_selection(vault, selected_items, subject=None):
    if not isinstance(selected_items, list) or not selected_items:
        raise ValueError("至少选择 1 道题")
    existing = _load_sessions(vault)
    active_qids = {e["question_id"] for s in existing if s.get("Status") == "active" for e in _entries(vault, s) if e["availability"] == "active"}
    clean, seen = [], set()
    for item in selected_items:
        if not isinstance(item, dict) or not (item.get("question_id") or item.get("uid")):
            raise ValueError("每道题必须提供有效题目身份")
        row = resolve_question(vault, uid=item.get("uid", ""), question_id=item.get("question_id", ""))
        if not row:
            raise ValueError("题目不存在或不可用")
        if row["suspended"]:
            raise ValueError(f"以下 UID 已停用，不能加入复习: {row['uid']}")
        source = item.get("source", "due")
        if source not in ("due", "proficiency"):
            raise ValueError("题目来源必须为 due 或 proficiency，请刷新推荐后重试")
        qid = row["question_id"]
        if qid in active_qids:
            raise ValueError(f"所选题目已在进行中的 Session 中：{row['uid']}")
        if qid not in seen:
            seen.add(qid)
            clean.append({"question_id": qid, "uid": row["uid"], "uid_at_creation": row["uid"], "source": source})
    sid = _resolve_session_id(_reserved_session_ids(vault) | {s["Session_ID"] for s in existing}, f"EXP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
    for index, entry in enumerate(clean):
        entry["entry_id"] = f"{sid}:{index}"
    append_commit(vault, "api", "session.create", f"创建 Session {sid}", {"session": {
        "session_id": sid, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "subject_filter": subject or "", "count": len(clean), "entries": clean, "items": clean, "status": "active"}})
    rebuild_projection(vault)
    result = get_session(vault, sid)
    # 创建响应兼容原小写 items，详情仍保留旧大写字段。
    from .scheduling import _row_to_item
    by_id = {r.get("question_id"): r for r in mastery_rows(vault)}
    result["items"] = [{**_row_to_item(by_id[e["question_id"]]), "_source": e["source"]} for e in clean]
    return result


@storage
def get_session(vault, session_id):
    match = session_row(vault, session_id)
    if not match:
        return None
    entries = _entries(vault, match)
    rows = {r.get("question_id"): r for r in mastery_rows(vault, question_ids=[e["question_id"] for e in entries if e["question_id"]])}
    items = []
    for e in entries:
        if e["availability"] == "suspended":
            continue
        row = rows.get(e["question_id"])
        items.append({**(row or {"UID": e["uid"], "_missing": True}), "question_id": e["question_id"],
                      "entry_id": e["entry_id"], "_source": e["source"], "availability": e["availability"]})
    return {"session_id": match["Session_ID"], "created_at": match.get("Created_At", ""),
            "subject_filter": match.get("Subject_Filter", ""), "count": len(items), "status": match.get("Status", "active"),
            "completed_at": match.get("Completed_At", ""), "entries": entries, "items": items, **_progress(entries)}


@storage
def list_sessions(vault, status=None, include_unavailable=False):
    result = []
    with connect(vault) as db:
        questions = {r["question_id"]: dict(r) for r in db.execute("SELECT question_id,uid,archived,suspended FROM question_projection")}
        submitted = {}
        for row in db.execute("SELECT DISTINCT session_id,question_id FROM history_projection WHERE session_id<>''"):
            submitted.setdefault(row["session_id"], set()).add(row["question_id"])
    for session in _load_sessions(vault):
        if status and session["Status"] != status:
            continue
        entries = _entries(vault, session, questions, submitted.get(session["Session_ID"], set()))
        if not include_unavailable and session["Status"] == "active" and not any(e["availability"] != "suspended" for e in entries):
            continue
        value = {"session_id": session["Session_ID"], "created_at": session.get("Created_At", ""),
                 "subject_filter": session.get("Subject_Filter", ""), "status": session["Status"],
                 "completed_at": session.get("Completed_At", ""), "entries": entries,
                 "uids": [e["uid"] for e in entries if e["availability"] != "suspended"], **_progress(entries)}
        value["count"] = len(value["uids"])
        result.append(value)
    return result


@storage_write
def bind_session_entry(vault, session_id, entry_id, question_id):
    session = get_session(vault, session_id)
    if not session:
        raise ValueError("复习计划不存在")
    entry = next((e for e in session["entries"] if e["entry_id"] == entry_id), None)
    if not entry or entry["availability"] != "unresolved":
        raise IdentityConflict("计划条目不存在或已经绑定，请刷新")
    if not resolve_question(vault, question_id=question_id, include_archived=True):
        raise ValueError("指定题目不存在")
    append_commit(vault, "api", "session.items_bind", "人工确认旧复习条目身份", {
        "session_id": session_id, "entry_id": entry_id, "question_id": question_id, "binding_source": "manual"})
    rebuild_projection(vault)
    return get_session(vault, session_id)


@storage_write
def delete_session(vault, session_id):
    if not get_session(vault, session_id):
        return False
    append_commit(vault, "api", "session.retract", f"撤销 Session {session_id}", {"session_id": session_id, "reason": "兼容 /api/session/delete 调用"})
    rebuild_projection(vault)
    return True


@storage_write
def mark_session_completed(vault, session_id):
    session = get_session(vault, session_id)
    if not session or session["status"] == "completed":
        return False
    append_commit(vault, "api", "session.complete", f"完成 Session {session_id}", {
        "session_id": session_id, "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
    rebuild_projection(vault)
    return True
