"""只读工具（read 级，自动执行）：词表、搜题、看题、概况、推荐、Session。正文截断，Session 条目按页返回。"""
import datetime
import math
import re
from functools import cmp_to_key

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


def _parse_search_date(value, field):
    text = str(value or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?", text):
        raise ValueError(f"{field} 必须是 YYYY-MM-DD 日期")
    try:
        # 搜题筛选使用日期边界；时间戳也接受但统一按本地日期比较。
        return datetime.date.fromisoformat(text[:10])
    except (TypeError, ValueError):
        raise ValueError(f"{field} 必须是 YYYY-MM-DD 日期")


def _effective_created_date(item):
    for value in (item.get("created_at"), item.get("entry_date")):
        text = str(value or "").strip()
        if not text:
            continue
        try:
            return datetime.date.fromisoformat(text[:10])
        except ValueError:
            continue
    return None


def _optional_number(value, field):
    """把工具参数中的数字边界规范化；JSON schema 之外的直接调用也给出可读错误。"""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是数字")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} 必须是数字")
    if not math.isfinite(number):
        raise ValueError(f"{field} 必须是有限数字")
    return number


def _due_range_ok(days, value):
    if value in (None, ""):
        return True
    if value not in {"overdue", "today", "3days", "7days", "future", "not_due"}:
        raise ValueError("due_range 只能是 overdue、today、3days、7days 或 not_due")
    if days is None:
        return False
    if value == "overdue":
        return days < 0
    if value == "today":
        return days == 0
    if value == "3days":
        return 0 <= days <= 3
    if value == "7days":
        return 0 <= days <= 7
    if value in {"future", "not_due"}:
        return days > 0
    return True


SORT_FIELDS = {
    "uid": "uid", "path": "path", "file_path": "file_path", "subject": "subject", "category": "category",
    "current_tag": "tag", "tag": "tag",
    "difficulty": "difficulty", "mastery": "mastery", "decayed_mastery": "decayed_mastery",
    "ef": "ef", "attempts": "attempts", "practice_count": "attempts", "review_count": "attempts",
    "last_review": "last_review", "last_review_at": "last_review",
    "due": "due_date", "due_date": "due_date", "entry_date": "entry_date", "created_at": "created_at",
    "status": "status", "suspended": "suspended", "archived": "archived", "fail_count": "fail_count",
    "errors": "fail_count", "wrong_streak": "wrong_streak", "consecutive_errors": "wrong_streak",
    "high_correct_streak": "high_correct_streak", "repetition": "repetition",
    "interval": "interval", "kill_count": "kill_count", "is_leech": "is_leech",
    "is_killed": "is_killed", "is_revived": "is_revived", "revived": "is_revived", "dormant_days": "dormant_days", "next_revive_date": "next_revive_date",
}
NUMERIC_SORT_FIELDS = {
    "difficulty", "mastery", "decayed_mastery", "ef", "attempts", "suspended", "archived", "fail_count",
    "wrong_streak", "high_correct_streak", "repetition", "interval", "kill_count", "is_killed", "is_leech", "is_revived",
    "dormant_days",
}


def _sort_value(item, field):
    key = SORT_FIELDS[field]
    if field == "status":
        return "suspended" if item.get("suspended") else (item.get("tag") or "active")
    if field == "created_at":
        # 精确创建时间缺失时按录入日期回退；外部题和新题都因此能进入同一序列。
        values = (item.get("created_at"), item.get("entry_date"))
    else:
        value = item.get(key)
        values = (value,)
    for value in values:
        if value in (None, ""):
            continue
        text = str(value).strip()
        if not text:
            continue
        if field in {"created_at", "entry_date"}:
            try:
                parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                return parsed.isoformat(timespec="microseconds")
            except ValueError:
                try:
                    return datetime.datetime.combine(datetime.date.fromisoformat(text[:10]), datetime.time()).isoformat(timespec="microseconds")
                except ValueError:
                    continue
        if field in NUMERIC_SORT_FIELDS:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return text.lower()
    return None


def _validated_sort(args):
    raw = args.get("sort")
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("sort 必须是数组")
    if len(raw) > 3:
        raise ValueError("sort 最多支持 3 级")
    result, seen = [], set()
    for index, spec in enumerate(raw):
        if not isinstance(spec, dict):
            raise ValueError(f"sort[{index}] 必须是对象")
        field = str(spec.get("field") or "").strip()
        direction = str(spec.get("direction") or "asc").strip().lower()
        if field not in SORT_FIELDS:
            raise ValueError(f"sort[{index}].field 不支持：{field or '空'}")
        canonical = SORT_FIELDS[field]
        if canonical in seen:
            raise ValueError(f"sort 不能重复字段：{field}")
        if direction not in {"asc", "desc"}:
            raise ValueError(f"sort[{index}].direction 只能是 asc 或 desc")
        seen.add(canonical)
        result.append((field, direction))
    return result


def _sort_hits(hits, specs):
    if not specs:
        return hits

    def compare(left, right):
        for field, direction in specs:
            a, b = _sort_value(left, field), _sort_value(right, field)
            if a is None and b is None:
                continue
            if a is None:
                return 1
            if b is None:
                return -1
            if a == b:
                continue
            result = -1 if a < b else 1
            return -result if direction == "desc" else result
        left_uid = str(left.get("uid") or "").lower()
        right_uid = str(right.get("uid") or "").lower()
        return -1 if left_uid < right_uid else (1 if left_uid > right_uid else 0)

    return sorted(hits, key=cmp_to_key(compare))


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
    lo = _optional_number(args.get("mastery_min"), "mastery_min")
    hi = _optional_number(args.get("mastery_max"), "mastery_max")
    difficulty_min = _optional_number(args.get("difficulty_min"), "difficulty_min")
    difficulty_max = _optional_number(args.get("difficulty_max"), "difficulty_max")
    if lo is not None and not 0 <= lo <= 1 or hi is not None and not 0 <= hi <= 1:
        raise ValueError("熟练度范围必须在 0 到 1 之间")
    if difficulty_min is not None and not 1 <= difficulty_min <= 10 or difficulty_max is not None and not 1 <= difficulty_max <= 10:
        raise ValueError("难度范围必须在 1 到 10 之间")
    if difficulty_min is not None and difficulty_max is not None and difficulty_min > difficulty_max:
        raise ValueError("difficulty_min 不能大于 difficulty_max")
    due_range = args.get("due_range") or args.get("due")
    raw_labels = args.get("labels") or []
    if isinstance(raw_labels, str):
        raw_labels = [raw_labels]
    labels = [str(label).strip() for label in raw_labels if str(label).strip()]
    if args.get("label"):
        labels.append(str(args["label"]).strip())
    labels = list(dict.fromkeys(label for label in labels if label))
    label_match = args.get("label_match", args.get("labels_match", args.get("label_mode", "any")))
    if label_match not in {"any", "all"}:
        raise ValueError("label_match 只能是 any 或 all")
    if due_range not in (None, "", "overdue", "today", "3days", "7days", "future", "not_due"):
        raise ValueError("due_range 只能是 overdue、today、3days、7days 或 not_due")
    created_from = _parse_search_date(args.get("created_from"), "created_from")
    created_to = _parse_search_date(args.get("created_to"), "created_to")
    if created_from and created_to and created_from > created_to:
        raise ValueError("created_from 不能晚于 created_to")
    sort_specs = _validated_sort(args)
    hits, image_only, scope = [], 0, 0
    for uid, item in sorted(_items(vault).items(), key=lambda kv: (kv[1]["subject"], kv[1]["category"], kv[0])):
        if args.get("subject") and item["subject"] != args["subject"]:
            continue
        if args.get("category") and item["category"] != args["category"]:
            continue
        if args.get("knowledge_point") and args["knowledge_point"] not in (item.get("knowledge_tags") or []):
            continue
        item_labels = set(item.get("labels") or [])
        if labels and (not all(label in item_labels for label in labels) if label_match == "all"
                       else not any(label in item_labels for label in labels)):
            continue
        due_text, days = due_info(item)
        if not _due_range_ok(days, due_range):
            continue
        if args.get("status") and not _status_ok(item, args["status"], days):
            continue
        if not args.get("status") and item.get("suspended"):
            continue
        m = mastery_of(item)
        if lo is not None and (m is None or m < lo):
            continue
        if hi is not None and (m is None or m >= hi):
            continue
        difficulty = item.get("difficulty")
        if difficulty_min is not None and (difficulty is None or difficulty < difficulty_min):
            continue
        if difficulty_max is not None and (difficulty is None or difficulty > difficulty_max):
            continue
        created_date = _effective_created_date(item)
        if created_from and (created_date is None or created_date < created_from):
            continue
        if created_to and (created_date is None or created_date > created_to):
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
        hits.append({"uid": uid, "path": f"{item['subject']} / {item['category']}", "file_path": item.get("path", ""), "snippet": snippet(source, first),
                     "field": field, "subject": item.get("subject", ""), "category": item.get("category", ""),
                     "difficulty": item.get("difficulty"), "mastery": m, "decayed_mastery": item.get("decayed_mastery"),
                     "ef": item.get("ef"), "attempts": item.get("attempts"), "last_review": item.get("last_review", ""),
                     "due": due_text, "due_date": item.get("due_date", ""), "entry_date": item.get("entry_date", ""),
                     "created_at": item.get("created_at", ""), "suspended": bool(item.get("suspended")),
                     "archived": item.get("archived"), "tag": item.get("tag", ""),
                     "status": "suspended" if item.get("suspended") else (item.get("tag") or "active"),
                     "current_tag": item.get("tag", ""), "is_killed": is_killed_state(item.get("mastery", 0), item.get("tag", "")),
                     "is_leech": bool(item.get("is_leech")), "is_revived": bool(item.get("is_revived")),
                     "wrong_streak": item.get("wrong_streak", 0), "fail_count": item.get("fail_count", 0),
                     "high_correct_streak": item.get("high_correct_streak", 0), "repetition": item.get("repetition", 0),
                     "interval": item.get("interval", 0), "kill_count": item.get("kill_count", 0),
                     "dormant_days": item.get("dormant_days", 0), "next_revive_date": item.get("next_revive_date", ""),
                     "labels": item.get("labels") or []})
    hits = _sort_hits(hits, sort_specs)
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
    from ...question_update import note_of
    note = note_of(read_question_file(vault, row))
    return {"result": {"uid": uid, "question_id": row['question_id'], "difficulty": int(item.get('difficulty') or 5),
                       "note": note if len(note) <= cap else note[:cap] + f"…（共 {len(note)} 字，已截断）",
                       "path": f"{item['subject']} / {item['category']}", "sections": out,
                       "images": image_names(secs["题目"] + "\n" + secs["答案"]),
                       "knowledge_points": item.get("knowledge_tags") or [], "labels": item.get("labels") or [],
                       "mastery": mastery_of(item), "due": due_text, "due_days": days,
                       "suspended": bool(item.get("suspended")), "wrong_streak": wrong,
                       "entry_date": item.get("entry_date", ""), "created_at": item.get("created_at", ""),
                       "is_leech": bool(item.get("is_leech")), "content_hash": row.get("content_hash") or "",
                       "records": [{"date": r["date"], "correct": r["correct"], "score": r["score"], "note": r["note"]}
                                   for r in records]},
            "summary": f"连错 {wrong} 次" if wrong >= 2 else ("错因已有" if secs["错因"] else "错因为空")}


def get_overview(ctx, args):
    vault = ctx["vault"]
    stats = get_stats(vault, subject=args.get("subject") or None)
    alert = stats["review_alert"]
    items = [i for i in stats["items"] if not i.get("suspended")]
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
    pack = lambda i, s: {"question_id": i["question_id"], "uid": i["uid"], "source": s, "why": _why(i, s), "mastery": mastery_of(i)}
    result = {"due": [pack(i, "due") for i in due], "proficiency": [pack(i, "proficiency") for i in prof]}
    result["selection"] = [{"question_id": x["question_id"], "uid": x["uid"], "source": x["source"]}
                           for x in result["due"] + result["proficiency"]]
    return {"result": result, "summary": f"到期 {len(due)} + 熟练度 {len(prof)}"}


def _session_page(args, default_limit):
    offset, limit = args.get("offset", 0), args.get("limit", default_limit)
    if type(offset) is not int or offset < 0:
        raise ValueError("offset 必须是大于等于 0 的整数")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit 必须是 1 到 100 的整数")
    return offset, limit


def _session_details(session):
    entries = session.get("entries", [])
    availability = {state: 0 for state in ("active", "suspended", "archived", "unresolved")}
    for entry in entries:
        availability[entry["availability"]] += 1
    return {"created_at": session.get("created_at", ""), "completed_at": session.get("completed_at", ""),
            "subject_filter": session.get("subject_filter", ""), "feedback_count": session.get("feedback_count", 0),
            "pending_count": session.get("pending_count", 0), "feedback_complete": session.get("feedback_complete", False),
            "total_count": len(entries), "availability_counts": availability}


def list_sessions_tool(ctx, args):
    offset, limit = _session_page(args, 20)
    status = args.get("status")
    if status is not None and status not in ("active", "completed"):
        raise ValueError("status 只能是 active 或 completed")
    rows = list_sessions(ctx["vault"], status, include_unavailable=True)
    rows.sort(key=lambda session: (session["created_at"], session["session_id"]), reverse=True)
    page = rows[offset:offset + limit]
    return {"result": {"sessions": [{"session_id": s["session_id"], "status": s["status"], "count": s["count"],
                                     "pending": s.get("pending_count", 0), **_session_details(s)} for s in page],
                       "total": len(rows), "offset": offset, "limit": limit,
                       "next_offset": offset + len(page) if offset + len(page) < len(rows) else None},
            "summary": f"{len(page)} 个，共 {len(rows)} 个"}


def get_session_tool(ctx, args):
    offset, limit = _session_page(args, 100)
    session_id = args.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id 必须是非空字符串")
    s = get_session(ctx["vault"], session_id.strip())
    if not s:
        raise ValueError(f"Session 不存在：{session_id}")
    entries = s.get("entries", [])
    page = entries[offset:offset + limit]
    return {"result": {"session_id": s["session_id"], "status": s["status"], "count": s["count"],
                       "pending": s.get("pending_uids", []), "done": s.get("feedback_uids", []), **_session_details(s),
                       "entries": page, "entries_total": len(entries), "offset": offset, "limit": limit,
                       "next_offset": offset + len(page) if offset + len(page) < len(entries) else None},
            "summary": f"待反馈 {s.get('pending_count', 0)}，已反馈 {s.get('feedback_count', 0)}"}


_S = {"type": "string"}
SPECS = [
    ("list_taxonomy", "read", "列出题库现有的科目、按科目分组的分类（含题数）、知识点与标记。搜题或录题前先用它对齐叫法。",
     {"type": "object", "properties": {"subject": _S, "page": {"type": "integer", "minimum": 1}}}, list_taxonomy),
    ("search_questions", "read",
     "按关键词在题目、答案、错因、分类、知识点里找题（规范化后子串匹配，两字词也能命中），可组合筛选科目、分类、知识点、"
     "多标记、状态、难度 / 熟练度 / 到期 / 创建日期范围，并在分页前按最多 3 级自定义排序。纯图片题没有正文，关键词搜不到，"
     "结果里 image_only 给出筛选范围内这类题的数量。单页最多 30 条。",
     {"type": "object", "properties": {
         "keywords": {"type": "array", "items": _S, "maxItems": 8}, "match": {"type": "string", "enum": ["any", "all"]},
         "subject": _S, "category": _S, "knowledge_point": _S, "label": _S,
         "labels": {"type": "array", "items": _S, "maxItems": 20},
         "label_match": {"type": "string", "enum": ["any", "all"]}, "labels_match": {"type": "string", "enum": ["any", "all"]},
         "label_mode": {"type": "string", "enum": ["any", "all"]},
         "status": {"type": "string", "enum": list(STATUS)},
         "mastery_min": {"type": "number", "minimum": 0, "maximum": 1},
         "mastery_max": {"type": "number", "minimum": 0, "maximum": 1},
         "difficulty_min": {"type": "number", "minimum": 1, "maximum": 10},
         "difficulty_max": {"type": "number", "minimum": 1, "maximum": 10},
         "due_range": {"type": "string", "enum": ["overdue", "today", "3days", "7days", "future", "not_due"]},
         "due": {"type": "string", "enum": ["overdue", "today", "3days", "7days", "future", "not_due"]},
         "created_from": _S, "created_to": _S,
         "sort": {"type": "array", "maxItems": 3, "items": {"type": "object", "required": ["field"],
             "properties": {"field": _S, "direction": {"type": "string", "enum": ["asc", "desc"]}}}},
         "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": 30}}},
     search_questions),
    ("get_question", "read", "读一道题：题目、答案、错因（长的会截断）、图片名、知识点、标记、熟练度、到期、最近练习记录。",
     {"type": "object", "required": ["uid"], "properties": {"uid": {"type": "string", "minLength": 1}}}, get_question),
    ("get_overview", "read", "整体概况：题量、待复习、顽固题、已击杀，以及按平均熟练度从低到高的分类（最弱的在前）。回答「哪块最弱」用它。",
     {"type": "object", "properties": {"subject": _S}}, get_overview),
    ("get_recommendations", "read", "取复习推荐：到期列表优先，数量不够再从熟练度列表补；已在进行中 Session 里的题已排除。selection 可直接交给 create_review_session。",
     {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 30},
                                       "subject": _S, "category": _S, "label": _S}}, get_recommendations),
    ("list_sessions", "read", "按创建时间从新到旧分页列出复习 Session，含反馈进度和停用、归档、待绑定条目数量。",
     {"type": "object", "properties": {"status": {"type": "string", "enum": ["active", "completed"]},
         "offset": {"type": "integer", "minimum": 0, "default": 0},
         "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}}, list_sessions_tool),
    ("get_session", "read", "查一个 Session：完整计划进度、稳定身份和可用状态；entries 分页，pending/done 始终为完整计划。",
     {"type": "object", "required": ["session_id"], "properties": {
         "session_id": {"type": "string", "minLength": 1}, "offset": {"type": "integer", "minimum": 0, "default": 0},
         "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100}}},
     get_session_tool),
]
