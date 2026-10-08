from .data_repository import storage_read
from .common import business_today
from .data_repository import mastery_rows, history_rows, resolve_question
from .vault_lifecycle import storage
import datetime
import os
import re

from .common import extract_category, extract_images, extract_labels, extract_knowledge_tags, extract_tag, is_suspended_row, load_tuning, parse_date, parse_yaml_frontmatter, resolve_sm2_fields, split_sections
from .ledger import connect
from .scheduling import (
    _row_to_item,
    _safe_float,
    _safe_int,
    build_fail_counts,
    build_wrong_streaks,
    compute_priority,
    days_since_review,
    is_killed_state,
    is_leech,
    time_decay,
)


@storage_read
def get_stats(vault, subject=None):
    rows = [resolve_sm2_fields(r) for r in mastery_rows(vault)]
    history = history_rows(vault)
    with connect(vault) as db:
        projection_rows = db.execute(
            "SELECT * FROM question_projection"
        ).fetchall()
    if subject:
        rows = [row for row in rows if row.get("Subject", "") == subject]
        scoped_uids = {row.get("UID", "") for row in rows}
        projection_rows = [row for row in projection_rows if row["uid"] in scoped_uids]
        scoped_qids = {row["question_id"] for row in projection_rows if not row["archived"]}
        # 改名后的历史以稳定身份匹配，旧记录才退回 UID。
        history = [log for log in history if (
            log["Question_ID"] in scoped_qids if log.get("Question_ID")
            else log.get("UID", "") in scoped_uids
        )]
    projected_suspended_uids = {
        row["uid"] for row in projection_rows if not row["archived"] and row["suspended"]
    }
    active_rows = [
        row for row in rows
        if not is_suspended_row(row) and row.get("UID", "") not in projected_suspended_uids
    ]
    suspended_count = len(rows) - len(active_rows)
    active_uids = {row.get("UID", "") for row in active_rows}
    uid_by_qid = {row["question_id"]: row["uid"] for row in projection_rows if not row["archived"]}
    active_qids = {
        row["question_id"] for row in projection_rows
        if not row["archived"] and not row["suspended"]
    }
    active_history = [
        log for log in history
        if (
            log.get("Question_ID") in active_qids
            if log.get("Question_ID")
            else log.get("UID", "") in active_uids
        )
    ]
    tuning = load_tuning(vault)
    from .labels import label_priority_map
    label_bonuses = label_priority_map(vault)
    all_fail_counts = build_fail_counts(history, uid_by_qid)
    active_wrong_streaks = build_wrong_streaks(active_history, uid_by_qid)
    all_wrong_streaks = build_wrong_streaks(history, uid_by_qid)
    today = business_today()

    total = len(active_rows)
    killed = sum(
        1
        for row in active_rows
        if is_killed_state(_safe_float(row.get("Mastery", 0)), row.get("Current_Tag", ""))
    )
    avg_mastery = sum(_safe_float(row.get("Mastery", 0)) for row in active_rows) / total if total else 0

    subject_dist = {}
    for row in active_rows:
        subject = row.get("Subject", "未分类")
        if subject not in subject_dist:
            subject_dist[subject] = {"total": 0, "killed": 0, "sum_m": 0}
        subject_dist[subject]["total"] += 1
        subject_dist[subject]["sum_m"] += _safe_float(row.get("Mastery", 0))
        if is_killed_state(_safe_float(row.get("Mastery", 0)), row.get("Current_Tag", "")):
            subject_dist[subject]["killed"] += 1
    for subject in subject_dist:
        data = subject_dist[subject]
        data["avg_m"] = round(data["sum_m"] / data["total"], 3) if data["total"] else 0
        del data["sum_m"]

    diff_dist = {}
    for row in active_rows:
        difficulty = row.get("Difficulty", "5")
        diff_dist[difficulty] = diff_dist.get(difficulty, 0) + 1

    recent = {}
    for log in active_history:
        dt = log.get("Date", "")[:10]
        try:
            if (today - datetime.date.fromisoformat(dt)).days <= 30:
                recent[dt] = recent.get(dt, 0) + 1
        except (ValueError, TypeError):
            pass

    mastery_histogram = {}
    for bucket in range(10):
        lo, hi = bucket * 0.1, (bucket + 1) * 0.1
        key = f"{bucket * 10}-{(bucket + 1) * 10}"
        mastery_histogram[key] = sum(
            1
            for row in active_rows
            if (
                lo <= _safe_float(row.get("Mastery", 0)) <= 1.0
                if bucket == 9
                else lo <= _safe_float(row.get("Mastery", 0)) < hi
            )
        )

    daily_counts = {}
    for log in active_history:
        dt = log.get("Date", "")[:10]
        if dt:
            daily_counts[dt] = daily_counts.get(dt, 0) + 1
    daily_trend = {}
    for offset in range(30):
        dt = (today - datetime.timedelta(days=29 - offset)).isoformat()
        daily_trend[dt] = daily_counts.get(dt, 0)

    scatter_data = []
    for row in active_rows:
        mastery = _safe_float(row.get("Mastery", 0))
        days = days_since_review(row.get("Last_Review", ""), today, 0)
        scatter_data.append(
            {
                "uid": row.get("UID", ""),
                "subject": row.get("Subject", ""),
                "difficulty": _safe_int(row.get("Difficulty", 5), 5),
                "mastery": round(mastery, 3),
                "decayed_mastery": round(
                    time_decay(mastery, days, tuning["decay_mastery_factor"], tuning["decay_base"]), 3
                ),
            }
        )

    urgent = 0
    warning = 0
    cold = 0
    total_due = 0
    overdue = 0
    due_today = 0
    due_next_3_days = 0
    due_next_7_days = 0
    low_mastery_not_due = 0
    leech = 0
    for row in active_rows:
        mastery = _safe_float(row.get("Mastery", 0))
        tag = row.get("Current_Tag", "")
        uid = row.get("UID", "")
        if is_killed_state(mastery, tag):
            continue

        days = days_since_review(row.get("Last_Review", ""), today, 30)
        decayed_mastery = time_decay(
            mastery, days, tuning["decay_mastery_factor"], tuning["decay_base"]
        )
        if decayed_mastery < 0.3 and days > 7:
            urgent += 1
        if decayed_mastery < 0.5 and days > 14:
            warning += 1
        if days > 30:
            cold += 1
        if is_leech(active_wrong_streaks.get(uid, 0), mastery, tag, tuning):
            leech += 1
        dd = parse_date(row.get("Due_Date", ""))
        due_delta = None
        if dd:
            due_delta = (dd - today).days
            if due_delta < 0:
                overdue += 1
            elif due_delta == 0:
                due_today += 1
            if 1 <= due_delta <= 3:
                due_next_3_days += 1
            if 1 <= due_delta <= 7:
                due_next_7_days += 1
        if due_delta is not None and due_delta > 0 and decayed_mastery < 0.5:
            low_mastery_not_due += 1
        priority = compute_priority(
            decayed_mastery, _safe_float(row.get("EF", 2.5), 2.5),
            days, tag, mastery, active_wrong_streaks.get(uid, 0), tuning,
            labels=[label.strip() for label in str(row.get("Labels", "") or "").split("|") if label.strip()],
            label_bonuses=label_bonuses,
        )
        if priority > 0.3:
            total_due += 1

    created_at_by_uid = {
        row["uid"]: (row["created_at"] or "")
        for row in projection_rows
        if not row["archived"]
    }
    items = [
        _row_to_item(row, today, all_fail_counts.get(row.get("UID", ""), 0), tuning,
                     all_wrong_streaks.get(row.get("UID", ""), 0))
        for row in rows
    ]
    for item in items:
        item["created_at"] = created_at_by_uid.get(item["uid"], "")
        item["suspended"] = item["suspended"] or item["uid"] in projected_suspended_uids

    return {
        "total": total,
        "suspended": suspended_count,
        "killed": killed,
        "attacking": total - killed,
        "avg_mastery": round(avg_mastery, 3),
        "subject_dist": subject_dist,
        "difficulty_dist": diff_dist,
        "recent_activity": recent,
        "mastery_histogram": mastery_histogram,
        "daily_trend": daily_trend,
        "scatter_data": scatter_data,
        "review_alert": {
            "urgent": urgent,
            "warning": warning,
            "cold": cold,
            "total_due": total_due,
            "overdue": overdue,
            "due_today": due_today,
            "due_next_3_days": due_next_3_days,
            "due_next_7_days": due_next_7_days,
            "due_within_3_days": due_today + due_next_3_days,
            "due_within_7_days": due_today + due_next_7_days,
            "low_mastery_not_due": low_mastery_not_due,
            "leech": leech,
        },
        "items": items,
    }


@storage_read
def get_question_content(vault, uid="", question_id=""):
    if question_id:
        projection = resolve_question(vault, uid=uid, question_id=question_id)
        if not projection:
            return {"error": "题目不存在"}
        uid = projection["uid"]
    rows = mastery_rows(vault)
    row = next((item for item in rows if item["UID"] == uid), None)
    if not row:
        return {"error": "UID not found"}
    file_path = os.path.join(vault, *row["File_Path"].replace("\\", "/").split("/"))
    if not os.path.exists(file_path):
        return {"error": "File not found"}
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    sections = split_sections(content)
    meta = parse_yaml_frontmatter(content)
    question_text = sections.get("题目", "")
    with connect(vault) as db:
        projection = db.execute(
            "SELECT created_at FROM question_projection WHERE uid = ? AND archived = 0", (uid,)
        ).fetchone()
    entry_date = row.get("Entry_Date", "")
    created_at = ""
    if projection:
        created_at = projection["created_at"] or ""
    return {
        "uid": uid,
        "question_id": (resolve_question(vault, uid=uid) or {}).get("question_id", ""),
        "subject": meta.get("科目", ""),
        "category": extract_category(meta),
        "difficulty": meta.get("难度", "5"),
        "question": question_text,
        "notes": sections.get("备注", ""),
        "answer": sections.get("答案", ""),
        "history": sections.get("历史", ""),
        # 正式练习记录：来自 Ledger 投影（history_log.csv），不是上面那段 Markdown 遗留文本。
        "records": get_question_records(vault, uid),
        "tag": row.get("Current_Tag") or extract_tag(meta),
        "suspended": is_suspended_row(row),
        "knowledge_tags": extract_knowledge_tags(meta),
        "labels": extract_labels(meta),
        "images": extract_images(question_text),
        "entry_date": entry_date,
        "created_at": created_at,
    }


def _split_history_date(value):
    """把 history_log.csv 的 Date（"YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM"）拆成日期 + 时间两段。"""
    text = str(value or "").strip()
    match = re.match(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?", text)
    if not match:
        return text[:10], ""
    return match.group(1), match.group(2) or ""


@storage
def get_question_records(vault, uid):
    """返回一道题的正式练习记录（按 Ledger 提交顺序，旧到新）。

    数据源是 Ledger 的 SQL ``history_projection``；题目 Markdown 里的
    ``# 历史`` 只是早期遗留文本，反馈流程早已不再写它，所以这里不看它。
    优先按隐藏稳定身份 ``Question_ID`` 匹配（改名不断链），老行没有 Question_ID 时退回按 UID 匹配。
    """
    uid = str(uid or "").strip()
    if not uid:
        return []
    question_id = ""
    try:
        with connect(vault) as db:
            row = db.execute(
                "SELECT question_id FROM question_projection WHERE uid = ? AND archived = 0",
                (uid,),
            ).fetchone()
            if row:
                question_id = row["question_id"] or ""
    except Exception:
        question_id = ""
    records = []
    for row in history_rows(vault, question_id=question_id or None):
        row_qid = (row.get("Question_ID") or "").strip()
        row_uid = (row.get("UID") or "").strip()
        if question_id and row_qid:
            keep = row_qid == question_id
        else:
            keep = row_uid == uid
        if not keep:
            continue
        date_text, time_text = _split_history_date(row.get("Date"))
        records.append({
            "log_id": row.get("Log_ID", ""),
            "date": date_text,
            "time": time_text,
            "score": _safe_int(row.get("Sub_Score"), 0),
            "correct": str(row.get("Is_Correct", "")).strip() == "1",
            "note": row.get("Note", "") or "",
            "session_id": row.get("Session_ID", "") or "",
            "recorded_at": row.get("recorded_at", ""),
        })
    return records


@storage
def get_question_records_page(vault, uid, offset=0, limit=50):
    """单题正式历史按 SQL 分页，避免 MCP 后续页先载入全部反馈。"""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("历史分页范围不合法")
    row = resolve_question(vault, uid=uid)
    if not row:
        return {"items": [], "total": 0, "offset": offset, "next_offset": None}
    with connect(vault) as db:
        total = db.execute("SELECT COUNT(*) FROM history_projection WHERE question_id=?", (row["question_id"],)).fetchone()[0]
        raw = db.execute("SELECT * FROM history_projection WHERE question_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                         (row["question_id"], limit, offset))
        items = []
        for record in raw:
            day, clock = _split_history_date(record["date"])
            items.append({"log_id": record["log_id"], "date": day, "time": clock,
                          "score": record["sub_score"], "correct": bool(record["is_correct"]),
                          "note": record["note"] or "", "session_id": record["session_id"] or "",
                          "recorded_at": record["recorded_at"] or ""})
    return {"items": items, "total": total, "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None}
