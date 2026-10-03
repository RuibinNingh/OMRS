"""正式题库和学习数据写入工具：全部在界面确认后执行，计入写入预算。
全部在 runtime 的写锁与 agent_actor 上下文里执行：commit 来源为 agent，payload 带运行身份；可被按运行撤销。
录题改走草稿（tools/drafts.py 的 create_draft），这里不再有录题工具。
"""

import re

from ...common import extract_knowledge_tags, extract_labels, parse_yaml_frontmatter
from ...content_history import projection_row, read_question_file, refresh_projection, write_question
from ...feedback import process_feedback
from ...labels import list_label_defs
from ...question_ops import (_replace_frontmatter_list_field, move_question, resume_question, suspend_question)
from ...scheduling import transition_review
from ...projections import rebuild_projection
from ...data_repository import resolve_question, storage_write
from ...common import business_today
from ...sessions import create_session_from_selection, get_session
from .common import SECTIONS, image_names, sections_of

EMBED_RE = re.compile(r"!\[\[[^\]]+\]\]")


def _row(vault, uid):
    row = projection_row(vault, uid=str(uid or "").strip())
    if not row:
        raise ValueError(f"题目不存在：{uid}")
    return row


# ── confirm：计划和标记 ──
def create_review_session_preview(ctx, args):
    from ...sessions import active_session_uids
    occupied = active_session_uids(ctx['vault'])
    items = []
    for item in args["items"]:
        row = _row(ctx["vault"], item["uid"])
        if row.get("suspended"):
            raise ValueError(f"题目已停用：{row['uid']}")
        if row['uid'] in occupied:
            raise ValueError(f"题目已在进行中的计划内：{row['uid']}")
        items.append({"uid": row["uid"], "question_id": row["question_id"],
                      "source": item.get("source") or "due", "subject": row["subject"],
                      "category": row["category"]})
    return {"items": items, "count": len(items), "message": "确认后创建正式复习调度；尚未创建或记录反馈。"}


def create_review_session(ctx, args):
    items = [{"uid": i["uid"].strip(), "source": i.get("source") or "due"} for i in args["items"]]
    s = create_session_from_selection(ctx["vault"], items)
    return {"result": {"session_id": s["session_id"], "count": s["count"], "status": s["status"],
                       "items": [i["uid"] for i in items]}, "summary": s["session_id"]}


def set_question_labels_preview(ctx, args):
    known = {d["name"] for d in list_label_defs(ctx["vault"])}
    add = [v.strip() for v in args.get("add") or [] if v.strip()]
    remove = {v.strip() for v in args.get("remove") or [] if v.strip()}
    if any(value not in known for value in add):
        raise ValueError("只能添加已有标记")
    if not add and not remove:
        raise ValueError("add 与 remove 至少给一个")
    details = []
    for uid in dict.fromkeys(args["uids"]):
        row = _row(ctx["vault"], uid)
        content = read_question_file(ctx["vault"], row)
        before = extract_labels(parse_yaml_frontmatter(content))
        after = [v for v in dict.fromkeys(before + add) if v not in remove]
        details.append({"question_id": row["question_id"], "uid": row["uid"],
                        "before": before, "after": after})
    return {"items": details, "count": len(details), "message": "确认后修改题目标记。"}


def set_question_labels(ctx, args):
    vault = ctx["vault"]
    known = {d["name"] for d in list_label_defs(vault)}
    add = [v.strip() for v in args.get("add") or [] if v.strip()]
    remove = {v.strip() for v in args.get("remove") or [] if v.strip()}
    unknown = [v for v in add if v not in known]
    if unknown:
        raise ValueError(f"标记「{'、'.join(unknown)}」不存在；现有标记：{'、'.join(sorted(known)) or '（无）'}")
    if not add and not remove:
        raise ValueError("add 与 remove 至少给一个")
    changed, skipped, details = [], [], []
    for uid in dict.fromkeys(u.strip() for u in args["uids"]):
        row = _row(vault, uid)
        content = read_question_file(vault, row)
        current = extract_labels(parse_yaml_frontmatter(content))
        nxt = [v for v in dict.fromkeys(current + add) if v not in remove]
        if nxt == current:
            skipped.append(uid)
            continue
        write_question(vault, row, _replace_frontmatter_list_field(content, "标记", nxt), f"AI 修改 {uid} 的标记")
        changed.append(uid)
        details.append({"uid": uid, "before": current, "after": nxt})
    if changed:
        refresh_projection(vault)
    return {"result": {"changed": changed, "skipped": skipped, "details": details, "add": add, "remove": sorted(remove)},
            "summary": f"{len(changed)} 道"}


# ── confirm：正文 ──
def replace_section(content, section, text, mode):
    """返回 (新正文, 旧的这一节)。题目 / 答案是一级标题；错因是「# 备注」下的「## 错因」。原有的图片嵌入一律保留。"""
    text = (text or "").strip()
    if section == "错因":
        m = re.search(r"^##\s*错因[ \t]*\n(.*?)(?=^##?\s|\Z)", content, re.S | re.M)
        if not m:
            b = re.search(r"^#\s+备注[ \t]*\n", content, re.M)
            if b:
                return content[:b.end()] + f"## 错因\n{text}\n\n" + content[b.end():], ""
            a = re.search(r"^#\s+答案[ \t]*\n", content, re.M)
            block = f"# 备注\n## 错因\n{text}\n\n"
            return (content[:a.start()] + block + content[a.start():] if a else content.rstrip() + "\n\n" + block), ""
    else:
        m = re.search(rf"^#\s+{section}[ \t]*\n(.*?)(?=^#\s|\Z)", content, re.S | re.M)
        if not m:
            return content.rstrip() + f"\n\n# {section}\n{text}\n", ""
    old = m.group(1).strip()
    if old == "（请在 Obsidian 中编辑此题目内容）":
        old = ""
    new = text if mode == "replace" or not old else f"{old}\n\n{text}"
    kept = [e for e in EMBED_RE.findall(old) if e not in new]
    if kept:
        new = new + "\n\n" + "\n".join(kept)
    return content[:m.start(1)] + new + "\n\n" + content[m.end(1):].lstrip("\n"), old


def _section_plan(ctx, args):
    row = _row(ctx["vault"], args["uid"])
    content = read_question_file(ctx["vault"], row)
    new, old = replace_section(content, args["section"], args["content"], args.get("mode") or "replace")
    return row, content, new, old


def update_question_section_preview(ctx, args):
    row, content, new, old = _section_plan(ctx, args)
    secs = sections_of(content)
    return {"uid": row["uid"], "section": args["section"], "mode": args.get("mode") or "replace", "before": old,
            "after": sections_of(new)[args["section"]], "question": secs["题目"], "answer": secs["答案"],
            "images_kept": image_names(old), "content_hash": row.get("content_hash") or ""}


def update_question_section(ctx, args):
    row, content, new, old = _section_plan(ctx, args)
    write_question(ctx["vault"], row, new, f"AI 修改 {row['uid']} 的{args['section']}")
    refresh_projection(ctx["vault"])
    return {"result": {"ok": True, "uid": row["uid"], "section": args["section"], "before": old,
                       "after": sections_of(new)[args["section"]],
                       "before_hash": _hash(content),
                       "after_hash": _hash(new)}, "summary": "已写入"}


def _hash(text):
    from ...ledger import blob_hash
    return blob_hash(text)


def _kp_plan(ctx, args):
    row = _row(ctx["vault"], args["uid"])
    content = read_question_file(ctx["vault"], row)
    before = extract_knowledge_tags(parse_yaml_frontmatter(content))
    after = list(dict.fromkeys(p.strip().strip("[]") for p in args["points"] if p.strip()))
    return row, content, before, after


def set_knowledge_points_preview(ctx, args):
    row, _, before, after = _kp_plan(ctx, args)
    return {"uid": row["uid"], "before": before, "after": after}


def set_knowledge_points(ctx, args):
    row, content, before, after = _kp_plan(ctx, args)
    if before == after:
        return {"result": {"uid": row["uid"], "changed": False, "points": after}, "summary": "没有变化"}
    new = _replace_frontmatter_list_field(content, "相关知识点", [f"[[{p}]]" for p in after])
    write_question(ctx["vault"], row, new, f"AI 修改 {row['uid']} 的知识点")
    refresh_projection(ctx["vault"])
    return {"result": {"uid": row["uid"], "changed": True, "before": before, "after": after}, "summary": "已写入"}


# ── confirm：结构 ──
def move_preview(ctx, args):
    row = _row(ctx["vault"], args["uid"])
    return {"uid": row["uid"], "from": f"{row['subject']} / {row['category']}",
            "to": f"{args.get('subject') or row['subject']} / {args['category']}"}


def move_tool(ctx, args):
    row = _row(ctx["vault"], args["uid"])
    out = move_question(ctx["vault"], row["uid"], args.get("subject") or row["subject"], args["category"])
    return {"result": {"old_uid": out["old_uid"], "uid": out["uid"], "path": out["file_path"]},
            "summary": f"{out['old_uid']} → {out['uid']}"}


def suspend_preview(ctx, args):
    row = _row(ctx["vault"], args["uid"])
    return {"uid": row["uid"], "path": f"{row['subject']} / {row['category']}", "reason": args.get("reason") or ""}


def suspend_tool(ctx, args):
    out = suspend_question(ctx["vault"], args["uid"].strip(), args.get("reason") or "AI 助手停用")
    return {"result": out, "summary": "已停用"}


def resume_preview(ctx, args):
    return {"uid": args["uid"].strip(), "reason": args.get("reason") or ""}


def resume_tool(ctx, args):
    out = resume_question(ctx["vault"], args["uid"].strip(), args.get("reason") or "AI 助手恢复")
    return {"result": out, "summary": "已恢复"}


# ── confirm：反馈 ──
@storage_write
def predict_feedback(vault, items, session_id=""):
    state = rebuild_projection(vault)
    session = get_session(vault, session_id) if session_id else None
    sources = {e["question_id"]: e["source"] for e in session["entries"]} if session else {}
    out, local = [], {}
    for item in items:
        row = resolve_question(vault, uid=item.get("uid", "").strip(), question_id=item.get("question_id", ""))
        if not row:
            raise ValueError(f"题目不存在：{item.get('uid', '')}")
        qid = row["question_id"]
        question = dict(state["questions"][qid])
        mastery = local.get(qid, state["mastery"][qid])
        if qid in local:
            question["current_tag"] = local[qid]["_tag"]
        updated, tag, display = transition_review(question, mastery, {
            "sub_score": int(item["sub_score"]), "is_correct": bool(item["is_correct"]),
            "source": sources.get(qid, item.get("source") or "due"), "review_date": business_today().isoformat()}, state["_tuning"])
        local[qid] = {**updated, "_tag": tag}
        out.append({"uid": row["uid"], "question_id": qid, "is_correct": bool(item["is_correct"]), "sub_score": int(item["sub_score"]),
                    "mastery_before": round(display["old_mastery"], 3), "mastery_after": round(updated["mastery"], 3), "state": display["label"]})
    return out


def _check_session(vault, args):
    sid = (args.get("session_id") or "").strip()
    if not sid:
        return "", None
    s = get_session(vault, sid)
    if not s:
        raise ValueError(f"Session 不存在：{sid}")
    missing = [i["uid"] for i in args["items"] if i["uid"].strip() not in s.get("pending_uids", [])]
    if missing:
        raise ValueError(f"这些题不在 {sid} 的待反馈列表里：{'、'.join(missing)}")
    return sid, s


def feedback_preview(ctx, args):
    sid, s = _check_session(ctx["vault"], args)
    left = len(s.get("pending_uids", [])) - len(args["items"]) if s else None
    return {"user_statement": args["user_statement"], "session_id": sid, "session_left": left,
            "items": predict_feedback(ctx["vault"], args["items"], sid)}


def record_feedback(ctx, args):
    vault = ctx["vault"]
    sid, _ = _check_session(vault, args)
    predicted = {p["uid"]: p for p in predict_feedback(vault, args["items"])}
    results = process_feedback(vault, [{"uid": i["uid"].strip(), "is_correct": bool(i["is_correct"]),
                                        "sub_score": int(i["sub_score"]), "note": ""} for i in args["items"]], sid)
    bad = [r for r in results if r.get("status") != "ok"]
    if bad and len(bad) == len(results):
        raise ValueError("；".join(f"{r['uid']}：{r.get('msg')}" for r in bad))
    items = [{"uid": r["uid"], "mastery_before": round(r["old_mastery"], 3), "mastery_after": round(r["new_mastery"], 3),
              "state": r["label"], "due": r.get("new_due_date", "")} for r in results if r.get("status") == "ok"]
    left = len(get_session(vault, sid).get("pending_uids", [])) if sid else None
    return {"result": {"recorded": len(items), "items": items, "failed": bad, "session_id": sid, "session_pending": left},
            "summary": f"{len(items)} 条", "extra": {"predicted": list(predicted.values())}}


_S = {"type": "string", "minLength": 1}
_UID = {"type": "string", "minLength": 1}
SPECS = [
    ("create_review_session", "confirm", "按选好的题建一个复习 Session（可撤销），须在聊天或审核中心确认后执行。items 里 source 是 due 或 proficiency，通常直接用 get_recommendations 的 selection。",
     {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 30, "items": {
         "type": "object", "required": ["uid"], "properties": {"uid": _UID, "source": {"type": "string", "enum": ["due", "proficiency"]}}}}}},
     create_review_session, create_review_session_preview),
    ("set_question_labels", "confirm", "批量给题目加上或去掉标记（可撤销），须确认后执行，单次最多 50 题。只能用已有的标记名。",
     {"type": "object", "required": ["uids"], "properties": {"uids": {"type": "array", "minItems": 1, "maxItems": 50, "items": _UID},
                                                          "add": {"type": "array", "items": _S}, "remove": {"type": "array", "items": _S}}},
     set_question_labels, set_question_labels_preview),
    ("update_question_section", "confirm", "改一道题的「题目」「答案」或「错因」这一节（替换或追加）。需要用户在界面上点允许；原有图片会保留。",
     {"type": "object", "required": ["uid", "section", "content"], "properties": {
         "uid": _UID, "section": {"type": "string", "enum": list(SECTIONS)},
         "mode": {"type": "string", "enum": ["replace", "append"]}, "content": _S}},
     update_question_section, update_question_section_preview),
    ("set_knowledge_points", "confirm", "把一道题的知识点整体设为给定列表。需要用户允许。",
     {"type": "object", "required": ["uid", "points"], "properties": {"uid": _UID, "points": {"type": "array", "maxItems": 12, "items": _S}}},
     set_knowledge_points, set_knowledge_points_preview),
    ("move_question", "confirm", "把题目移到另一个分类（可跨科目），UID 会按新分类重排。需要用户允许。",
     {"type": "object", "required": ["uid", "category"], "properties": {"uid": _UID, "subject": {"type": "string"}, "category": _S}},
     move_tool, move_preview),
    ("suspend_question", "confirm", "停用一道题（暂不复习）。需要用户允许。",
     {"type": "object", "required": ["uid"], "properties": {"uid": _UID, "reason": {"type": "string"}}}, suspend_tool, suspend_preview),
    ("resume_question", "confirm", "恢复一道停用的题。需要用户允许。",
     {"type": "object", "required": ["uid"], "properties": {"uid": _UID, "reason": {"type": "string"}}}, resume_tool, resume_preview),
    ("record_feedback", "confirm", "按用户明说的对错和自评分（0–10）记录练习反馈。user_statement 必须是用户的原话。需要用户允许。",
     {"type": "object", "required": ["items", "user_statement"], "properties": {
         "session_id": {"type": "string"}, "user_statement": {"type": "string", "minLength": 2},
         "items": {"type": "array", "minItems": 1, "maxItems": 30, "items": {"type": "object", "required": ["uid", "is_correct", "sub_score"],
                   "properties": {"uid": _UID, "is_correct": {"type": "boolean"}, "sub_score": {"type": "integer", "minimum": 0, "maximum": 10}}}}}},
     record_feedback, feedback_preview),
]
