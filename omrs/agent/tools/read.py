"""只读工具（read 级，自动执行）：词表、搜题、看题、概况、推荐、Session。输出都控制在 6000 字符内。"""
import datetime
import math

from ...ai_assist import collect_taxonomy
from ...content_history import projection_row, read_question_file
from ...labels import list_label_defs
from ...scheduling import generate_recommendations, is_killed_state
from ...sessions import active_session_uids, get_session, list_sessions
from ...stats import get_question_records, get_stats
from .common import due_info, image_names, mastery_of, norm, sections_of, snippet, text_only

_TEXT_CACHE = {}  # content_hash -> (sections, normalized) ；按内容哈希缓存，重复计算结果相同（无锁可接受）


def _items(vault):
    return {i["uid"]: i for i in get_stats(vault)["items"]}


def _content(vault, uid):
    row = projection_row(vault, uid=uid)
    if not row:
        return None, None
    key = row.get("content_hash") or ""
    cached = _TEXT_CACHE.get(key) if key else None
    if cached is None:
        try:
            content = read_question_file(vault, row)
        except OSError:
            return row, None
        secs = sections_of(content)
        cached = (secs, {k: norm(text_only(v)) for k, v in secs.items()})
        if key:
            _TEXT_CACHE[key] = cached
    return row, cached


def list_taxonomy(ctx, args):
    vault = ctx["vault"]
    tax = collect_taxonomy(vault)
    items = _items(vault)
    want = (args.get("subject") or "").strip()
    subjects = []
    for subject in tax["subjects"]:
        if want and subject != want:
            continue
        cats = [{"name": c, "n": sum(1 for i in items.values() if i["subject"] == subject and i["category"] == c
                                     and not i.get("suspended"))}
                for c in tax["categories_by_subject"].get(subject, [])]
        subjects.append({"name": subject, "n": sum(c["n"] for c in cats), "categories": cats})
    kp = {}
    for i in items.values():
        if want and i["subject"] != want:
            continue
        for tag in i.get("knowledge_tags") or []:
            kp[tag] = kp.get(tag, 0) + 1
    page, size = max(1, int(args.get("page") or 1)), 120
    kps = sorted(kp.items(), key=lambda x: (-x[1], x[0]))
    labels = [{"name": d["name"], "n": d.get("count", 0)} for d in list_label_defs(vault)]
    return {"result": {"subjects": subjects, "labels": labels,
                       "knowledge_points": [{"name": k, "n": n} for k, n in kps[(page - 1) * size: page * size]],
                       "knowledge_points_page": page, "knowledge_points_pages": max(1, math.ceil(len(kps) / size))},
            "summary": f"{len(subjects)} 个科目，{sum(len(s['categories']) for s in subjects)} 个分类"}


STATUS = ("due", "overdue", "leech", "killed", "suspended", "new", "active")


def _status_ok(item, status, days):
    killed = is_killed_state(item.get("mastery", 0), item.get("tag", ""))
    return {
        "due": days is not None and days <= 0 and not item.get("suspended"),
        "overdue": days is not None and days < 0 and not item.get("suspended"),
        "leech": bool(item.get("is_leech")) and not item.get("suspended"),
        "killed": killed,
        "suspended": bool(item.get("suspended")),
        "new": int(item.get("attempts") or 0) == 0 and not item.get("suspended"),
        "active": not item.get("suspended"),
    }[status]


def search_questions(ctx, args):
    vault = ctx["vault"]
    keywords = [k.strip() for k in args.get("keywords") or [] if str(k).strip()]
    match_all = args.get("match") == "all"
    lo, hi = args.get("mastery_min"), args.get("mastery_max")
    hits, image_only, scope = [], 0, 0
    for uid, item in sorted(_items(vault).items(), key=lambda kv: (kv[1]["subject"], kv[1]["category"], kv[0])):
        if args.get("subject") and item["subject"] != args["subject"]:
            continue
        if args.get("category") and item["category"] != args["category"]:
            continue
        if args.get("knowledge_point") and args["knowledge_point"] not in (item.get("knowledge_tags") or []):
            continue
        if args.get("label") and args["label"] not in (item.get("labels") or []):
            continue
        due_text, days = due_info(item)
        if args.get("status") and not _status_ok(item, args["status"], days):
            continue
        if not args.get("status") and item.get("suspended"):
            continue
        m = mastery_of(item)
        if lo is not None and (m is None or m < lo):
            continue
        if hi is not None and (m is None or m >= hi):
            continue
        scope += 1
        row, cached = _content(vault, uid)
        if cached is None:
            continue
        secs, normed = cached
        if not normed["题目"]:
            image_only += 1
        field, first = "题目", ""
        if keywords:
            meta_text = norm(" ".join([uid, item["category"], *(item.get("knowledge_tags") or [])]))
            found = []
            for kw in keywords:
                nk = norm(kw)
                where = next((f for f in ("题目", "答案", "错因") if nk and nk in normed[f]), None)
                if where is None and nk and nk in meta_text:
                    where = "分类 / 知识点"
                if where:
                    found.append((kw, where))
            if not found or (match_all and len(found) < len(keywords)):
                continue
            first, field = found[0]
        source = secs["题目"] if field in ("题目", "分类 / 知识点") else secs[field]
        hits.append({"uid": uid, "path": f"{item['subject']} / {item['category']}", "snippet": snippet(source, first),
                     "field": field, "mastery": m, "due": due_text, "labels": item.get("labels") or []})
    size = min(30, max(1, int(args.get("page_size") or 20)))
    page = max(1, int(args.get("page") or 1))
    pages = max(1, math.ceil(len(hits) / size))
    return {"result": {"total": len(hits), "page": page, "pages": pages, "in_scope": scope,
                       "image_only": image_only if keywords else 0, "items": hits[(page - 1) * size: page * size]},
            "summary": f"{len(hits)} 题"}


def get_question(ctx, args):
    vault, uid = ctx["vault"], args["uid"].strip()
    item = _items(vault).get(uid)
    row, cached = _content(vault, uid)
    if not item or not row or cached is None:
        raise ValueError(f"题目不存在：{uid}")
    secs = cached[0]
    cap = 1500
    out = {}
    for key, value in secs.items():
        out[key] = value if len(value) <= cap else value[:cap] + f"…（共 {len(value)} 字，已截断）"
    records = get_question_records(vault, uid)[-6:]
    due_text, days = due_info(item)
    wrong = int(item.get("wrong_streak") or 0)
    return {"result": {"uid": uid, "path": f"{item['subject']} / {item['category']}", "sections": out,
                       "images": image_names(secs["题目"] + "\n" + secs["答案"]),
                       "knowledge_points": item.get("knowledge_tags") or [], "labels": item.get("labels") or [],
                       "mastery": mastery_of(item), "due": due_text, "due_days": days,
                       "suspended": bool(item.get("suspended")), "wrong_streak": wrong,
                       "is_leech": bool(item.get("is_leech")), "content_hash": row.get("content_hash") or "",
                       "records": [{"date": r["date"], "correct": r["correct"], "score": r["score"], "note": r["note"]}
                                   for r in records]},
            "summary": f"连错 {wrong} 次" if wrong >= 2 else ("错因已有" if secs["错因"] else "错因为空")}


def get_overview(ctx, args):
    vault = ctx["vault"]
    stats = get_stats(vault)
    alert = stats["review_alert"]
    items = [i for i in stats["items"] if not i.get("suspended")]
    if args.get("subject"):
        items = [i for i in items if i["subject"] == args["subject"]]
    groups = {}
    today = datetime.date.today()
    for i in items:
        g = groups.setdefault(f"{i['subject']} / {i['category']}", {"n": 0, "sum": 0.0, "k": 0, "due": 0})
        g["n"] += 1
        if int(i.get("attempts") or 0):
            g["sum"] += float(i.get("mastery") or 0)
            g["k"] += 1
        _, days = due_info(i, today)
        if days is not None and days <= 0:
            g["due"] += 1
    weakest = sorted(({"path": p, "n": g["n"], "avg": round(g["sum"] / g["k"], 3), "due": g["due"]}
                      for p, g in groups.items() if g["k"]), key=lambda w: w["avg"])[:6]
    leeches = sorted(({"uid": i["uid"], "wrong_streak": int(i.get("wrong_streak") or 0)} for i in items if i.get("is_leech")),
                     key=lambda x: -x["wrong_streak"])[:10]
    result = {"total": len(items), "suspended": stats["suspended"], "overdue": alert["overdue"],
              "due_today": alert["due_today"], "leech": alert["leech"], "killed": stats["killed"],
              "fresh": sum(1 for i in items if not int(i.get("attempts") or 0)),
              "avg_mastery": stats["avg_mastery"], "weakest": weakest, "leeches": leeches}
    return {"result": result, "summary": f"待复习 {alert['overdue'] + alert['due_today']}，顽固 {alert['leech']}"}


def _why(item, source):
    if source == "due":
        _, days = due_info(item)
        text = f"逾期 {-days} 天" if days is not None and days < 0 else "今天到期"
        return text + ("，顽固" if item.get("is_leech") else "")
    if item.get("is_revived"):
        return "已击杀题复燃"
    return "新题未练" if not int(item.get("attempts") or 0) else "熟练度偏低"


def get_recommendations(ctx, args):
    vault, count = ctx["vault"], int(args.get("count") or 8)
    rec = generate_recommendations(vault, due_count=count, prof_count=count, subject=args.get("subject") or None,
                                   category=args.get("category") or None, label=args.get("label") or None,
                                   exclude_uids=active_session_uids(vault))
    due = rec["due"][:count]
    prof = rec["proficiency"][:max(0, count - len(due))]
    pack = lambda i, s: {"uid": i["uid"], "source": s, "why": _why(i, s), "mastery": mastery_of(i)}
    result = {"due": [pack(i, "due") for i in due], "proficiency": [pack(i, "proficiency") for i in prof]}
    result["selection"] = [{"uid": x["uid"], "source": x["source"]} for x in result["due"] + result["proficiency"]]
    return {"result": result, "summary": f"到期 {len(due)} + 熟练度 {len(prof)}"}


def list_sessions_tool(ctx, args):
    rows = list_sessions(ctx["vault"], args.get("status") or None)[:20]
    return {"result": {"sessions": [{"session_id": s["session_id"], "status": s["status"], "count": s["count"],
                                     "created_at": s["created_at"], "pending": s.get("pending_count", 0)} for s in rows]},
            "summary": f"{len(rows)} 个"}


def get_session_tool(ctx, args):
    s = get_session(ctx["vault"], args["session_id"].strip())
    if not s:
        raise ValueError(f"Session 不存在：{args['session_id']}")
    return {"result": {"session_id": s["session_id"], "status": s["status"], "count": s["count"],
                       "pending": s.get("pending_uids", []), "done": s.get("feedback_uids", [])},
            "summary": f"待反馈 {len(s.get('pending_uids', []))}"}


_S = {"type": "string"}
SPECS = [
    ("list_taxonomy", "read", "列出题库现有的科目、按科目分组的分类（含题数）、知识点与标记。搜题或录题前先用它对齐叫法。",
     {"type": "object", "properties": {"subject": _S, "page": {"type": "integer", "minimum": 1}}}, list_taxonomy),
    ("search_questions", "read",
     "按关键词在题目、答案、错因、分类、知识点里找题（规范化后子串匹配，两字词也能命中），可按科目、分类、知识点、标记、"
     "状态、熟练度区间筛选。纯图片题没有正文，关键词搜不到，结果里 image_only 给出筛选范围内这类题的数量。单页最多 30 条。",
     {"type": "object", "properties": {
         "keywords": {"type": "array", "items": _S, "maxItems": 8}, "match": {"type": "string", "enum": ["any", "all"]},
         "subject": _S, "category": _S, "knowledge_point": _S, "label": _S,
         "status": {"type": "string", "enum": list(STATUS)},
         "mastery_min": {"type": "number", "minimum": 0, "maximum": 1},
         "mastery_max": {"type": "number", "minimum": 0, "maximum": 1},
         "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": 30}}},
     search_questions),
    ("get_question", "read", "读一道题：题目、答案、错因（长的会截断）、图片名、知识点、标记、熟练度、到期、最近练习记录。",
     {"type": "object", "required": ["uid"], "properties": {"uid": {"type": "string", "minLength": 1}}}, get_question),
    ("get_overview", "read", "整体概况：题量、待复习、顽固题、已击杀，以及按平均熟练度从低到高的分类（最弱的在前）。回答「哪块最弱」用它。",
     {"type": "object", "properties": {"subject": _S}}, get_overview),
    ("get_recommendations", "read", "取复习推荐：到期列表优先，数量不够再从熟练度列表补；已在进行中 Session 里的题已排除。selection 可直接交给 create_review_session。",
     {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 30},
                                       "subject": _S, "category": _S, "label": _S}}, get_recommendations),
    ("list_sessions", "read", "列出复习 Session（最近 20 个）。",
     {"type": "object", "properties": {"status": {"type": "string", "enum": ["active", "completed"]}}}, list_sessions_tool),
    ("get_session", "read", "查一个 Session：状态、题数、待反馈与已反馈的题。",
     {"type": "object", "required": ["session_id"], "properties": {"session_id": {"type": "string", "minLength": 1}}},
     get_session_tool),
]
