"""聊天练习卡：agent.db 保存题序与 attempt；Ledger 保存真实反馈。"""
import json
import secrets

from ..ledger import connect
from .store import AgentStore


def create_practice_card(ctx, args):
    vault = ctx["vault"]
    title = str(args.get("title") or "").strip()[:60]
    proposed = args.get("items") or []
    if not title or not isinstance(proposed, list) or not 1 <= len(proposed) <= 50:
        raise ValueError("练习卡需要标题和 1–50 道已入库题目")
    with connect(vault) as db:
        rows = {r["uid"]: r for r in db.execute("SELECT question_id,uid,archived,suspended FROM question_projection")}
    items, seen = [], set()
    for raw in proposed:
        uid = str(raw.get("uid") or "").strip() if isinstance(raw, dict) else ""
        row = rows.get(uid)
        if not row or row["archived"] or row["suspended"]:
            raise ValueError(f"题目不可用于练习：{uid}")
        qid = row["question_id"]
        if qid in seen:
            continue
        seen.add(qid)
        source = raw.get("source") or "due"
        if source not in ("due", "proficiency", "instant"):
            raise ValueError(f"题目来源无效：{source}")
        items.append({"question_id": qid, "uid_at_creation": uid, "source": source})
    card = {"kind": "practice_card", "schema_version": 1, "card_id": "PC-" + secrets.token_hex(12),
            "title": title, "items": items}
    stored = AgentStore(vault).save_practice_card(card, ctx["conversation_id"], ctx["run_id"], ctx["tool_call_id"])
    return {"result": stored, "summary": f"{title} · {len(items)} 题", "wrote": True}


def submitted_entries(vault, attempt_id):
    with connect(vault) as db:
        return submitted_entries_in_db(db, attempt_id)


def submitted_entries_in_db(db, attempt_id):
    found = set()
    for row in db.execute("SELECT payload_json FROM commits WHERE commit_type='review.batch_submit'"):
        payload = json.loads(row["payload_json"])
        for feedback in payload.get("feedbacks") or []:
            if feedback.get("attempt_id") == attempt_id:
                found.add(feedback.get("entry_id"))
    return found


def get_practice(vault, card_id, attempt_id=""):
    store = AgentStore(vault)
    card = store.practice_card(card_id)
    if not card:
        raise ValueError("练习卡不存在")
    attempt = store.practice_attempt(attempt_id) if attempt_id else store.default_practice_attempt(card_id)
    if attempt_id and not attempt:
        raise ValueError("练习尝试不存在")
    if attempt and attempt["card_id"] != card_id:
        raise ValueError("尝试不属于这张练习卡")
    if card["deleted"] and not attempt:
        raise ValueError("对话已删除，不能重新打开练习卡")
    with connect(vault) as db:
        rows = {r["question_id"]: r for r in db.execute("SELECT question_id,uid,archived,suspended FROM question_projection")}
    items, unavailable = [], []
    for item in card["items"]:
        row = rows.get(item["question_id"])
        if not row or row["archived"] or row["suspended"]:
            unavailable.append({**item, "reason": "题目已删除" if not row or row["archived"] else "题目已停用"})
        else:
            items.append({"question_id": item["question_id"], "uid": row["uid"], "_source": item["source"]})
    return {"card": {k: v for k, v in card.items() if k not in ("conversation_id", "deleted")},
            "deleted": card["deleted"], "attempt_id": attempt["attempt_id"] if attempt else "",
            "session_id": f"IMM-{attempt['attempt_id']}" if attempt else "",
            "items": items, "unavailable": unavailable,
            "submitted": sorted(submitted_entries(vault, attempt["attempt_id"])) if attempt else [],
            "progress": attempt["progress"] if attempt else {}}


def start_practice(vault, card_id, restart=False, request_id=""):
    attempt_id = AgentStore(vault).start_practice(card_id, restart=restart, request_id=request_id)
    return get_practice(vault, card_id, attempt_id)


def save_progress(vault, attempt_id, progress):
    store = AgentStore(vault)
    if not store.practice_attempt(attempt_id):
        raise ValueError("练习尝试不存在")
    if not isinstance(progress, dict) or len(json.dumps(progress, ensure_ascii=False)) > 30000:
        raise ValueError("练习进度无效")
    store.save_practice_progress(attempt_id, progress)
    return {"saved": True}


SPECS = [
    ("create_practice_card", "rev", "为聊天创建临时练习卡。只引用已入库题目，不创建正式 Session，也不记录反馈；用户打开后才开始练习。",
     {"type": "object", "required": ["title", "items"], "properties": {
         "title": {"type": "string", "minLength": 1},
         "items": {"type": "array", "minItems": 1, "maxItems": 50,
                   "items": {"type": "object", "required": ["uid"], "properties": {
                       "uid": {"type": "string", "minLength": 1},
                       "source": {"type": "string", "enum": ["due", "proficiency", "instant"]}}}}}},
     create_practice_card),
]
