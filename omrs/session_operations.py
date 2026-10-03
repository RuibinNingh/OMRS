"""MCP 复习计划创建：稳定身份、技术回执与领域投影在同一事务发布。"""
import contextlib
import datetime
import json
import sqlite3
import time

from .config_repository import _file_config, normalized_tuning
from .data_repository import resolve_question, storage_write
from .errors import RequestError
from .ledger import append_commit_in_db, canonical_json, connect
from .locking import DEFAULT_TIMEOUT, WriteLockTimeout
from .mcp.common import request_identity
from .projection_runtime import apply_incremental, invalidate, policy_hash
from .projections import rebuild_projection
from .sessions import _decode_session_items, _entries, _progress, _reserved_session_ids, _resolve_session_id


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
                current = (metadata and state["last_seq"] == (head["seq"] if head else 0)
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
        saved = _saved_session(row)
        questions = {}
        for item in _decode_session_items(saved["UIDs"]):
            question_id = item.get("question_id")
            if question_id and question_id not in questions:
                question = resolve_question(vault, question_id=question_id, include_archived=True, db=db)
                if question:
                    questions[question_id] = question
        submitted = {r[0] for r in db.execute("SELECT DISTINCT question_id FROM history_projection WHERE session_id=?", (row["session_id"],))}
        entries = _entries(vault, saved, questions, submitted)
        created_at, subject = row["created_at"], row["subject_filter"]
        completed_at = row["completed_at"]
        count = sum(entry["availability"] != "suspended" for entry in entries)
        status = row["status"] if available else "retracted"
    else:
        entries, completed_at, status = [], "", "retracted"
        created_at, subject = receipt["created_at"], receipt["subject_filter"]
        count = receipt["count"]
    return {"session_id": receipt["session_id"], "created_at": created_at, "status": status,
            "subject_filter": subject, "completed_at": completed_at, "count": count,
            "total_count": len(entries) if row else receipt["count"], "entries": entries,
            "available": available, "reused": reused, **_progress(entries),
            "actionable_pending_count": sum(e["availability"] == "active" and not e["feedback_submitted"] for e in entries) if available else 0,
            "blocked_count": sum(e["availability"] in ("archived", "unresolved") and not e["feedback_submitted"] for e in entries)}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


@storage_write
def create_mcp_session(vault, items, key_id, request_id, validate):
    """创建正式 Session；同请求复用原编号，即使原计划已经撤销。"""
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
