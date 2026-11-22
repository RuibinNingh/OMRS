import datetime
import json
import os
import re

from .common import business_today, split_sections
from .ledger import append_commit_in_db
from .data_repository import IdentityConflict, resolve_question, session_row, storage_write
from .session_operations import _session_transaction, publish_completion
from .sessions import _read_session_entries, _FEEDBACK_REASONS
from .path_safety import safe_question_path
from .log_utils import log_feedback
from .markdown_text import plain_emphasis


def _question_summary_at_feedback(vault, row):
    """提交时固定题面短句，之后的正文编辑不会改写历史卡。"""
    try:
        path = safe_question_path(vault, os.path.abspath(os.path.join(vault, row["File_Path"])))
        with open(path, "r", encoding="utf-8") as file:
            question = split_sections(file.read()).get("题目", "")
    except (OSError, ValueError, KeyError):
        return ""
    plain = re.sub(r"!\[[^]]*\]\([^)]*\)|!\[\[[^]]*\]\]", " ", plain_emphasis(question))
    plain = re.sub(r"(?m)^\s*#{1,6}\s+", "", plain)
    return " ".join(plain.split())[:80]


@storage_write
def process_feedback(vault, feedbacks, session_id="", attempt_id="", practice_round_id=""):
    if not isinstance(feedbacks, list):
        raise ValueError("反馈必须是列表")
    if not isinstance(practice_round_id, str) or (practice_round_id and not re.fullmatch(r"PR-[0-9a-f]{32}", practice_round_id)):
        raise ValueError("即时练习轮次标识无效")
    if practice_round_id and (attempt_id or not str(session_id).startswith("IMM-")):
        raise ValueError("轮次标识只用于普通即时练习")
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
    diagnostics = []
    with _session_transaction(vault) as (state, db, _):
        seen = submitted_entries_in_db(db, attempt_id) if attempt_id else None
        results = _process_feedback(vault, feedbacks, session_id, attempt_id=attempt_id,
                                    card=card, ledger_db=db, seen=seen, state=state, diagnostics=diagnostics,
                                    practice_round_id=practice_round_id)
    # 只在事务成功后追加诊断；幂等复用、无效条目与回滚不产生成功记录。
    for detail in diagnostics:
        log_feedback(vault, **detail)
    return results


def _process_feedback(vault, feedbacks, session_id="", *, ledger_db, state, attempt_id="", card=None, seen=None,
                      diagnostics=None, practice_round_id=""):
    tuning = state["_tuning"]
    if session_id and ledger_db.execute("SELECT 1 FROM projection_session_corrections WHERE session_id=? AND retracted=1", (session_id,)).fetchone():
        raise ValueError("复习计划已撤销，不能提交反馈")
    session = session_row(vault, session_id, ledger_db, closeout=True) if session_id and not attempt_id else None
    if not session and session_id and not attempt_id and any(
            isinstance(item, dict) and str(item.get("entry_id", "")).startswith(f"{session_id}:")
            for item in feedbacks):
        raise ValueError("复习计划不存在或已撤销，请刷新")
    if session and practice_round_id:
        raise ValueError("正式复习计划不能使用即时练习轮次标识")
    entries = _read_session_entries(vault, ledger_db, session)["entries"] if session else []
    corrected = _corrected_receipts(ledger_db, session_id) if session else set()
    allowed = {item["question_id"]: item for item in card["items"]} if card else {}
    now = datetime.datetime.now(datetime.timezone.utc)
    day = business_today(now).isoformat()
    if not session_id:
        session_id = "EXP-" + now.strftime("%Y%m%d%H%M%S")
    results, commit_feedbacks, receipts, duplicates = [], [], {}, []
    for feedback in feedbacks:
        if not isinstance(feedback, dict):
            results.append({"status": "error", "msg": "反馈条目必须是对象"})
            continue
        uid = str(feedback.get("uid") or "").strip()
        qid = str(feedback.get("question_id") or "").strip()
        entry_id = str(feedback.get("entry_id") or "")
        bound = None
        receipt_key = None
        if session:
            if entry_id:
                matches = [e for e in entries if e["entry_id"] == entry_id]
            elif qid:
                matches = [e for e in entries if e["question_id"] == qid]
            else:
                matches = [e for e in entries if uid and uid in (e["uid"], e["uid_at_creation"])]
            if len(matches) != 1:
                results.append({"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "error",
                                "msg": "反馈条目与复习计划不匹配"})
                continue
            bound = matches[0]
            entry_id = bound["entry_id"]
            failure = {"uid": bound["uid"], "question_id": bound["question_id"], "entry_id": entry_id, "status": "error"}
            if not bound["question_id"]:
                reason = bound["feedback_reason"] or _FEEDBACK_REASONS["unresolved"]
                results.append({**failure, "msg": reason})
                continue
            if (qid and qid != bound["question_id"]) or (
                    not qid and uid and uid not in (bound["uid"], bound["uid_at_creation"])):
                results.append({**failure, "msg": "反馈条目与题目身份不匹配"})
                continue
            qid = bound["question_id"]
            if feedback.get("question_id") and uid and not feedback.get("entry_id"):
                try:
                    resolve_question(vault, question_id=qid, uid=uid, include_archived=True, db=ledger_db)
                except IdentityConflict as exc:
                    # 保留单条旧客户端的身份冲突响应，混合批次则逐行返回。
                    if len(feedbacks) == 1:
                        raise
                    results.append({**failure, "msg": str(exc)})
                    continue
            receipt_key = "feedback:session:" + json.dumps([session_id, qid, entry_id], ensure_ascii=False)
            if receipt_key in receipts:
                reused = {**receipts[receipt_key], "reused": True}
                results.append(reused)
                duplicates.append((reused, receipts[receipt_key]))
                continue
            saved = ledger_db.execute("SELECT result_json FROM op_results WHERE op_id=?", (receipt_key,)).fetchone()
            if saved or bound["feedback_submitted"] or (entry_id, qid) in corrected or ("", qid) in corrected:
                previous = json.loads(saved[0]) if saved else {**failure, "status": "ok", "source": bound["source"]}
                results.append({**previous, "reused": True})
                continue
            if session["Status"] != "active" or bound["feedback_state"] != "pending":
                if session["Status"] == "paused":
                    reason = "复习计划已暂停，请先恢复计划再录入结果"
                elif session["Status"] == "completed":
                    reason = "复习计划已结束"
                else:
                    reason = bound["feedback_reason"]
                results.append({**failure, "msg": reason})
                continue
            row = resolve_question(vault, question_id=qid, db=ledger_db)
        else:
            if practice_round_id and not qid:
                results.append({"uid": uid, "status": "error", "msg": "即时练习重试必须提供 question_id"})
                continue
            row = resolve_question(vault, uid=uid, question_id=qid, db=ledger_db,
                                   include_archived=bool(practice_round_id))
            if practice_round_id and row:
                receipt_key = "feedback:instant:" + json.dumps([practice_round_id, row["question_id"]])
                if receipt_key in receipts:
                    reused = {**receipts[receipt_key], "reused": True}
                    results.append(reused)
                    duplicates.append((reused, receipts[receipt_key]))
                    continue
                saved = ledger_db.execute("SELECT result_json FROM op_results WHERE op_id=?", (receipt_key,)).fetchone()
                if saved:
                    results.append({**json.loads(saved[0]), "reused": True})
                    continue
        if not row or row.get("suspended") or row.get("archived"):
            results.append({"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "error", "msg": "题目已删除或停用，不能提交反馈"})
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
        if attempt_id or session:
            review.update({"attempt_id": attempt_id, "entry_id": entry_id})
        if practice_round_id:
            review["practice_round_id"] = practice_round_id
        if attempt_id:
            seen.add(entry_id)
        commit_feedbacks.append(review)
        result = {"uid": uid, "question_id": qid, "entry_id": entry_id, "status": "ok", "source": source}
        if practice_round_id:
            result.update({"sub_score": score, "is_correct": correct})
        results.append(result)
        if receipt_key:
            receipts[receipt_key] = result
    if commit_feedbacks:
        payload = {"session_id": session_id, "feedbacks": commit_feedbacks}
        info = append_commit_in_db(ledger_db, "api", "review.batch_submit", f"提交 {len(commit_feedbacks)} 条练习反馈", payload)
        from .projection_runtime import apply_incremental
        apply_incremental(vault, ledger_db, state, tuning, info["seq"], info["seq"])
        actual = iter(state["_review_results"])
        reviews = iter(commit_feedbacks)
        for result in results:
            if result["status"] == "ok" and not result.get("reused"):
                published = next(actual)
                review = next(reviews)
                if published["question_id"] != result["question_id"]:
                    raise RuntimeError("反馈投影结果与提交身份不一致")
                result.update({key: published[key] for key in (
                    "label", "old_mastery", "new_mastery", "tag", "new_interval", "new_due_date", "revive_stage")})
                if diagnostics is not None:
                    diagnostics.append({"uid": result["uid"], "question_id": result["question_id"],
                        "session_id": session_id, "commit_id": info["commit_id"],
                        "sub_score": review["sub_score"], "is_correct": review["is_correct"],
                        **{key: published[key] for key in ("old_mastery", "new_mastery", "label")}})
    for reused, original in duplicates:
        reused.update(original, reused=True)
    for receipt_key, result in receipts.items():
        ledger_db.execute("INSERT INTO op_results(op_id,result_json,created_at) VALUES(?,?,?)",
                         (receipt_key, json.dumps(result, ensure_ascii=False), now.isoformat(timespec="seconds")))
    if session and session["Status"] == "paused" and not any(row["status"] == "ok" for row in results):
        raise ValueError("复习计划已暂停，请先恢复计划再录入结果")
    if commit_feedbacks and session:
        summary = _read_session_entries(vault, ledger_db, session)
        progress = summary["progress"]
        if progress["can_finish"] and progress["total"] == progress["recorded"]:
            publish_completion(vault, ledger_db, state, tuning, session, summary)
    return results


def _corrected_receipts(db, session_id):
    """兼容升级前反馈的幂等身份，历史修正仍由修正通道恢复。"""
    sql = """SELECT c.payload_json, substr(r.review_key,instr(r.review_key,':')+1) AS review_index
        FROM projection_review_corrections r JOIN commits c
          ON c.commit_id=substr(r.review_key,1,instr(r.review_key,':')-1)
        WHERE c.commit_type='review.batch_submit' AND json_extract(c.payload_json,'$.session_id')=?"""
    receipts = set()
    for row in db.execute(sql, (session_id,)):
        payload = json.loads(row["payload_json"])
        reviews = payload.get("feedbacks") or payload.get("reviews") or []
        index = int(row["review_index"])
        if 0 <= index < len(reviews):
            item = reviews[index]
            receipts.add((item.get("entry_id") or "", item.get("question_id")))
    return receipts


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
