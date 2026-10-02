import datetime
import contextlib
import json
import os
import re
import time

from .common import business_today, split_sections
from .ledger import append_commit_in_db, connect
from .locking import DEFAULT_TIMEOUT, WriteLockTimeout
from .projections import rebuild_projection
from .data_repository import resolve_question, storage_write
from .sessions import get_session, mark_session_completed
from .path_safety import safe_question_path


def _question_summary_at_feedback(vault, row):
    """提交时固定题面短句，之后的正文编辑不会改写历史卡。"""
    try:
        path = safe_question_path(vault, os.path.abspath(os.path.join(vault, row["File_Path"])))
        with open(path, "r", encoding="utf-8") as file:
            question = split_sections(file.read()).get("题目", "")
    except (OSError, ValueError, KeyError):
        return ""
    plain = re.sub(r"!\[[^]]*\]\([^)]*\)|!\[\[[^]]*\]\]", " ", question)
    plain = re.sub(r"(?m)^\s*#{1,6}\s+", "", plain)
    return " ".join(plain.split())[:80]


@storage_write
def process_feedback(vault, feedbacks, session_id="", attempt_id=""):
    if not isinstance(feedbacks, list):
        raise ValueError("反馈必须是列表")
    if str(session_id).startswith("IMM-PA-") and not attempt_id:
        raise ValueError("聊天练习反馈必须提供已签发的 attempt_id")
    if attempt_id:
        from .agent.practice import submitted_entries_in_db
        from .agent.store import AgentStore
        attempt = AgentStore(vault).practice_attempt(attempt_id)
        if not attempt or session_id != f"IMM-{attempt_id}":
            raise ValueError("练习尝试不存在或来源不匹配")
        card = AgentStore(vault).practice_card(attempt["card_id"])
        if not card:
            raise ValueError("练习卡不存在")
    else:
        card = None
    with _feedback_transaction(vault) as (state, db):
        seen = submitted_entries_in_db(db, attempt_id) if attempt_id else None
        results = _process_feedback(vault, feedbacks, session_id, attempt_id=attempt_id,
                                    card=card, ledger_db=db, seen=seen, state=state)
    # 完成标记在反馈事务之后读取已发布历史，不在持有SQL写事务时另开写连接。
    if session_id and not attempt_id:
        session = get_session(vault, session_id)
        if session and session["feedback_complete"]:
            mark_session_completed(vault, session_id)
    return results


@contextlib.contextmanager
def _feedback_transaction(vault):
    from .config_repository import normalized_tuning, _file_config
    from .projection_runtime import policy_hash, invalidate
    deadline = time.monotonic() + DEFAULT_TIMEOUT
    while True:
        state = rebuild_projection(vault)
        try:
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
                        raise WriteLockTimeout("反馈写入繁忙，请稍后重试")
                    continue
                yield state, db
            return
        except BaseException:
            invalidate(vault)
            raise


def _process_feedback(vault, feedbacks, session_id="", *, ledger_db, state, attempt_id="", card=None, seen=None):
    tuning = state["_tuning"]
    if session_id and ledger_db.execute("SELECT 1 FROM projection_session_corrections WHERE session_id=? AND retracted=1", (session_id,)).fetchone():
        raise ValueError("复习计划已撤销，不能提交反馈")
    session = state["sessions"].get(session_id) if session_id and not attempt_id else None
    # 授权只需当前事务已校验的绑定快照，不在写事务内调用详情读模型。
    entries = [{**item, "uid": state["questions"].get(item.get("question_id"), {}).get("uid", item.get("uid", ""))}
               for item in json.loads(session["UIDs"])] if session else []
    allowed = {item["question_id"]: item for item in card["items"]} if card else {}
    now = datetime.datetime.now(datetime.timezone.utc)
    day = business_today(now).isoformat()
    if not session_id:
        session_id = "EXP-" + now.strftime("%Y%m%d%H%M%S")
    results, commit_feedbacks = [], []
    for feedback in feedbacks:
        if not isinstance(feedback, dict):
            results.append({"status": "error", "msg": "反馈条目必须是对象"})
            continue
        uid = str(feedback.get("uid") or "").strip()
        qid = str(feedback.get("question_id") or "").strip()
        entry_id = str(feedback.get("entry_id") or "")
        bound = None
        if session:
            matches = [e for e in entries if (e["question_id"] == qid if qid else uid in (e["uid"], e["uid_at_creation"]))]
            if len(matches) != 1 or not matches[0]["question_id"]:
                results.append({"uid": uid, "question_id": qid, "status": "error", "msg": "题目不属于计划或身份待确认"})
                continue
            bound = matches[0]
            qid = bound["question_id"]
            row = resolve_question(vault, question_id=qid, uid=uid if feedback.get("question_id") else "", db=ledger_db)
        else:
            row = resolve_question(vault, uid=uid, question_id=qid, db=ledger_db)
        if not row or row.get("suspended"):
            results.append({"uid": uid, "question_id": qid, "status": "error", "msg": "题目已删除或停用，不能提交反馈"})
            continue
        qid, uid = row["question_id"], row["uid"]
        if attempt_id:
            if qid not in allowed or entry_id != qid:
                results.append({"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "error", "msg": "练习条目不属于当前卡片"})
                continue
            if entry_id in seen:
                results.append({"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "ok", "reused": True})
                continue
        try:
            score, correct = _parse_sub_score(feedback.get("sub_score")), _parse_bool(feedback.get("is_correct"))
        except ValueError as exc:
            results.append({"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "error", "msg": str(exc)})
            continue
        source = allowed[qid]["source"] if attempt_id else bound["source"] if bound else _parse_source(feedback.get("source")) or "due"
        review = {"question_id": qid, "uid_at_that_time": uid, "subject": row.get("subject", ""),
                  "question_summary": _question_summary_at_feedback(vault, {"File_Path": row["file_path"]}),
                  "session_id": session_id, "source": source, "is_correct": correct, "sub_score": score,
                  "note": feedback.get("note", ""), "occurred_at": day, "review_date": day,
                  "review_timezone": "Asia/Shanghai", "recorded_at": now.isoformat(timespec="seconds")}
        if attempt_id:
            review.update({"attempt_id": attempt_id, "entry_id": entry_id})
            seen.add(entry_id)
        commit_feedbacks.append(review)
        results.append({"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "ok", "source": source})
    if commit_feedbacks:
        payload = {"session_id": session_id, "feedbacks": commit_feedbacks}
        info = append_commit_in_db(ledger_db, "api", "review.batch_submit", f"提交 {len(commit_feedbacks)} 条练习反馈", payload)
        from .projection_runtime import apply_incremental
        apply_incremental(vault, ledger_db, state, tuning, info["seq"], info["seq"])
        actual = iter(state["_review_results"])
        for result in results:
            if result["status"] == "ok" and not result.get("reused"):
                published = next(actual)
                if published["question_id"] != result["question_id"]:
                    raise RuntimeError("反馈投影结果与提交身份不一致")
                result.update({key: published[key] for key in (
                    "label", "old_mastery", "new_mastery", "tag", "new_interval", "new_due_date")})
    return results


def _parse_sub_score(value):
    try:
        score = int(value)
    except (TypeError, ValueError):
        raise ValueError("主观分必须是 0-10 的整数")
    if not 0 <= score <= 10:
        raise ValueError("主观分必须在 0-10 之间")
    return score


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "correct", "right", "对"}:
            return True
        if normalized in {"0", "false", "no", "n", "incorrect", "wrong", "错"}:
            return False
    raise ValueError("对错字段必须是布尔值")


def _parse_source(value):
    value = str(value or "").strip()
    if value in {"due", "proficiency", "instant", "manual", "legacy_unknown"}:
        return value
    return ""
