"""复习计划事务：创建回执、暂停与恢复均在新鲜投影上原子发布。"""
import contextlib
import datetime
import json
import sqlite3
import time

from .config_repository import _file_config, normalized_tuning
from .data_repository import IdentityConflict, _session_item, resolve_question, session_row, storage_write
from .errors import RequestError
from .ledger import PROJECTOR_VERSION, append_commit_in_db, canonical_json, connect
from .locking import DEFAULT_TIMEOUT, WriteLockTimeout
from .projection_runtime import apply_incremental, invalidate, policy_hash
from .projections import rebuild_projection
from .sessions import _decode_session_items, _entries, _read_session_entries, _reserved_session_ids, _resolve_session_id, _session_detail


def _normalize_items(items):
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise RequestError("invalid_request", "items 必须包含 1 到 100 道题")
    normalized, sources = [], {}
    for item in items:
        if not isinstance(item, dict) or set(item) - {"question_id", "source", "uid"}:
            raise RequestError("invalid_request", "每道题只接受 question_id、source 和可选 uid")
        question_id = item.get("question_id")
        if not isinstance(question_id, str) or not 1 <= len(question_id.strip()) <= 200:
            raise RequestError("invalid_request", "question_id 必须是 1 到 200 个字符")
        question_id = question_id.strip()
        source = item.get("source")
        if source not in ("due", "proficiency"):
            raise RequestError("invalid_request", "source 必须为 due 或 proficiency")
        if "uid" in item and (not isinstance(item["uid"], str) or len(item["uid"]) > 200):
            raise RequestError("invalid_request", "uid 必须是最多 200 个字符的展示编号")
        if question_id in sources:
            if sources[question_id] != source:
                raise RequestError("invalid_request", "同一道题不能指定不同来源")
            continue
        sources[question_id] = source
        normalized.append({"question_id": question_id, "source": source})
    return normalized


@contextlib.contextmanager
def _session_transaction(vault):
    """锁内复核链头、活动算法与读模型，避免跨进程使用过期投影。"""
    deadline = time.monotonic() + DEFAULT_TIMEOUT
    while True:
        try:
            state = rebuild_projection(vault)
            with connect(vault) as db:
                db.execute("BEGIN IMMEDIATE")
                head = db.execute("SELECT seq,commit_hash FROM commits ORDER BY seq DESC LIMIT 1").fetchone()
                active = db.execute("SELECT config_json FROM active_config WHERE id=1").fetchone()
                tuning = normalized_tuning(json.loads(active[0]) if active else _file_config(vault))
                metadata = db.execute("SELECT * FROM projection_meta WHERE id=1").fetchone()
                current = (metadata and metadata["projector_version"] == PROJECTOR_VERSION
                           and state["last_seq"] == (head["seq"] if head else 0)
                           and state.get("_head_hash", "") == (head["commit_hash"] if head else "")
                           and state["last_seq"] == metadata["last_seq"]
                           and state.get("_head_hash", "") == metadata["head_hash"]
                           and policy_hash(state["_tuning"]) == metadata["policy_hash"] == policy_hash(tuning))
                if not current:
                    db.rollback()
                    if time.monotonic() >= deadline:
                        raise WriteLockTimeout("复习计划写入繁忙，请稍后重试")
                    continue
                yield state, db, tuning
            return
        except BaseException as exc:
            invalidate(vault)
            if isinstance(exc, sqlite3.OperationalError) and getattr(exc, "sqlite_errorcode", 0) & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise WriteLockTimeout("复习计划写入繁忙，请稍后重试") from None
            raise


def _saved_session(row):
    return {"Session_ID": row["session_id"], "UIDs": row["items_json"]}


def _session_view(vault, db, receipt, reused):
    row = db.execute("SELECT * FROM session_projection WHERE session_id=?", (receipt["session_id"],)).fetchone()
    available = bool(row and not row["retracted"])
    if row:
        summary = _read_session_entries(vault, db, _session_item(row, closeout=True))
        created_at, subject = row["created_at"], row["subject_filter"]
        completed_at = row["completed_at"]
        count = sum(entry["availability"] != "suspended" for entry in summary["entries"])
        status = row["status"] if available else "retracted"
    else:
        summary = {"entries": [], "feedback_uids": [], "pending_uids": [], "feedback_count": 0,
                   "pending_count": 0, "feedback_complete": False, "progress": None, "completion": None}
        completed_at, status = "", "retracted"
        created_at, subject = receipt["created_at"], receipt["subject_filter"]
        count = receipt["count"]
    entries = summary["entries"]
    return {"session_id": receipt["session_id"], "created_at": created_at, "status": status,
            "subject_filter": subject, "completed_at": completed_at, "count": count,
            "total_count": len(entries) if row else receipt["count"],
            "available": available, "reused": reused, **summary,
            "actionable_pending_count": sum(e["availability"] == "active" and not e["feedback_submitted"] for e in entries) if available and status == "active" else 0,
            "blocked_count": sum(e["availability"] in ("archived", "unresolved") and not e["feedback_submitted"] for e in entries)}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class SessionStateConflict(RequestError):
    status = 409

    def __init__(self, message):
        super().__init__("session_state_conflict", message)


def _require_session(vault, db, session_id):
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("必须提供复习计划编号")
    session = session_row(vault, session_id, db, closeout=True)
    if not session:
        raise SessionStateConflict("复习计划不存在或已撤销，请刷新")
    return session


def _require_active(session):
    if session["Status"] == "paused":
        raise SessionStateConflict("复习计划已暂停，请先恢复计划")
    if session["Status"] != "active":
        raise SessionStateConflict("复习计划已结束，请刷新")


def _entry_by_id(entries, entry_id):
    entry = next((item for item in entries if item["entry_id"] == entry_id), None)
    if not entry:
        raise IdentityConflict("计划条目不存在，请刷新")
    return entry


def _publish_session_event(vault, db, state, tuning, kind, message, payload):
    info = append_commit_in_db(db, "api", kind, message, payload)
    apply_incremental(vault, db, state, tuning, info["seq"], info["seq"])


def publish_completion(vault, db, state, tuning, session, summary):
    """调用方已持写事务并确认可结单，处置与状态沿同一链头发布。"""
    sid = session["Session_ID"]
    completed_at = _now().isoformat(timespec="seconds")
    entries = [{key: entry[key] for key in ("entry_id", "question_id", "feedback_state", "feedback_reason")}
               for entry in summary["entries"]]
    counts = {key: count for key, count in summary["progress"].items()
              if key in ("total", "recorded", "pending", "unavailable", "skipped", "unresolved")}
    _publish_session_event(vault, db, state, tuning, "session.complete", f"结束复习计划 {sid}", {
        "session_id": sid, "completed_at": completed_at,
        "completion": {"completed_at": completed_at, "entries": entries, "counts": counts}})


@storage_write
def complete_session(vault, session_id, signature):
    if not isinstance(signature, str) or len(signature) != 64:
        raise ValueError("必须提供当前结单摘要签名")
    with _session_transaction(vault) as (state, db, tuning):
        session = _require_session(vault, db, session_id)
        if session["Status"] != "completed":
            _require_active(session)
            summary = _read_session_entries(vault, db, session)
            progress = summary["progress"]
            if signature != progress["signature"] or not progress["can_finish"]:
                raise SessionStateConflict("复习计划处置已变化或仍有待处理题目，请刷新后重新确认")
            publish_completion(vault, db, state, tuning, session, summary)
        return _session_detail(vault, db, session_id)


@storage_write
def set_entry_skipped(vault, session_id, entry_id, skipped, question_id=""):
    if not isinstance(entry_id, str) or not entry_id.strip() or not isinstance(question_id, str) or type(skipped) is not bool:
        raise ValueError("必须提供计划条目标识与布尔跳过状态")
    with _session_transaction(vault) as (state, db, tuning):
        session = _require_session(vault, db, session_id)
        _require_active(session)
        summary = _read_session_entries(vault, db, session)
        entry = _entry_by_id(summary["entries"], entry_id)
        if question_id and question_id != entry["question_id"]:
            raise IdentityConflict("计划条目身份已变化，请刷新")
        if entry["feedback_state"] == "recorded":
            raise SessionStateConflict("题目已录，不能跳过或撤销跳过")
        current = entry["feedback_state"] == "skipped"
        if current != skipped:
            if skipped and entry["feedback_state"] not in ("pending", "unresolved"):
                raise SessionStateConflict("题目当前不可录，请刷新")
            _publish_session_event(vault, db, state, tuning, "session.entry_skip",
                                   "仅本次跳过" if skipped else "撤销本次跳过",
                                   {"session_id": session_id, "entry_id": entry_id, "skipped": skipped})
        return _session_detail(vault, db, session_id)


@storage_write
def bind_entry(vault, session_id, entry_id, question_id):
    if not isinstance(question_id, str) or not question_id.strip():
        raise ValueError("必须提供题目身份")
    with _session_transaction(vault) as (state, db, tuning):
        session = _require_session(vault, db, session_id)
        _require_active(session)
        entry = _entry_by_id(_read_session_entries(vault, db, session)["entries"], entry_id)
        if entry["availability"] != "unresolved":
            raise IdentityConflict("计划条目已经绑定，请刷新")
        if not resolve_question(vault, question_id=question_id, include_archived=True, db=db):
            raise ValueError("指定题目不存在")
        _publish_session_event(vault, db, state, tuning, "session.items_bind", "人工确认旧复习条目身份",
                               {"session_id": session_id, "entry_id": entry_id, "question_id": question_id,
                                "binding_source": "manual"})
        return _session_detail(vault, db, session_id)


@storage_write
def set_session_paused(vault, session_id, paused):
    """保留题目与反馈；恢复前在同一写事务内检查活动计划占用。"""
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("必须提供复习计划编号")
    if not isinstance(paused, bool):
        raise ValueError("暂停状态必须为布尔值")
    target = "paused" if paused else "active"
    with _session_transaction(vault) as (state, db, tuning):
        session = db.execute("SELECT * FROM session_projection WHERE session_id=? AND retracted=0", (session_id,)).fetchone()
        if not session:
            raise ValueError("复习计划不存在或已撤销")
        if session["status"] not in {"active", "paused"}:
            raise ValueError("已完成的复习计划不能暂停或恢复")
        if session["status"] != target:
            if not paused:
                entries = _entries(vault, _saved_session(session))
                question_ids = {e["question_id"] for e in entries if e["availability"] == "active"}
                for other in db.execute("SELECT session_id,items_json FROM session_projection WHERE status='active' AND retracted=0"):
                    if question_ids.intersection(e["question_id"] for e in _decode_session_items(other["items_json"])):
                        raise ValueError(f"题目已被待完成计划 {other['session_id']} 占用，请先完成或暂停该计划")
            action = "暂停" if paused else "恢复"
            info = append_commit_in_db(db, "api", "session.pause" if paused else "session.resume",
                                       f"{action}复习计划 {session_id}", {"session_id": session_id})
            apply_incremental(vault, db, state, tuning, info["seq"], info["seq"])
        return _session_detail(vault, db, session_id)


@storage_write
def create_mcp_session(vault, items, key_id, request_id, validate):
    """创建正式 Session；同请求复用原编号，即使原计划已经撤销。"""
    from .mcp.common import request_identity
    validate()
    normalized = _normalize_items(items)
    if not isinstance(key_id, str) or not key_id.strip():
        raise RequestError("invalid_request", "缺少 MCP 密钥身份")
    try:
        identity, digest = request_identity(key_id, "create_review_session", request_id, normalized)
    except ValueError as exc:
        raise RequestError("invalid_request", str(exc)) from None
    operation_id = "mcp:session:" + identity
    with _session_transaction(vault) as (state, db, tuning):
        # 等待共同写锁及 SQLite 写事务后重新授权；回执优先于当前题目占用检查。
        validate()
        previous = db.execute("SELECT result_json FROM op_results WHERE op_id=?", (operation_id,)).fetchone()
        if previous:
            receipt = json.loads(previous["result_json"])
            if receipt["digest"] != digest:
                raise RequestError("request_conflict", "request_id 已用于不同的复习计划")
            result = _session_view(vault, db, receipt, True)
        else:
            questions, clean = {}, []
            for item in normalized:
                row = resolve_question(vault, question_id=item["question_id"], include_archived=True, db=db)
                if not row:
                    raise RequestError("invalid_request", "所选题目不存在")
                if row["archived"] or row["suspended"]:
                    raise RequestError("state_conflict", "所选题目已归档或停用，请刷新后重试")
                questions[row["question_id"]] = row
                clean.append({**item, "uid": row["uid"], "uid_at_creation": row["uid"]})
            active_ids = set()
            for saved in db.execute("SELECT session_id,items_json FROM session_projection WHERE status='active' AND retracted=0"):
                active_ids.update(entry["question_id"] for entry in _entries(vault, _saved_session(saved), questions, set())
                                  if entry["availability"] == "active")
            if active_ids.intersection(questions):
                raise RequestError("state_conflict", "所选题目已在进行中的复习计划中")
            existing_ids = _reserved_session_ids(vault, db=db)
            now = _now()
            session_id = _resolve_session_id(existing_ids, "EXP-" + now.strftime("%Y%m%d%H%M%S"))
            for index, entry in enumerate(clean):
                entry["entry_id"] = f"{session_id}:{index}"
            subjects = {row["subject"] for row in questions.values()}
            subject = next(iter(subjects)) if len(subjects) == 1 else ""
            created_at = now.isoformat(timespec="seconds")
            payload = {"session": {"session_id": session_id, "created_at": created_at,
                                   "subject_filter": subject, "count": len(clean), "entries": clean,
                                   "items": clean, "status": "active"}}
            validate()
            info = append_commit_in_db(db, "mcp", "session.create", f"创建 Session {session_id}", payload)
            apply_incremental(vault, db, state, tuning, info["seq"], info["seq"])
            receipt = {"digest": digest, "session_id": session_id, "created_at": created_at,
                       "subject_filter": subject, "count": len(clean), "commit_id": info["commit_id"]}
            db.execute("INSERT INTO op_results(op_id,result_json,created_at) VALUES(?,?,?)",
                       (operation_id, canonical_json(receipt), info["created_at"]))
            result = _session_view(vault, db, receipt, False)
        validate()
    # 已提交的合法计划保留；结果返回前吊销则仅拒绝本次响应。
    validate()
    return result
