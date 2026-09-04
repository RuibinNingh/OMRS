import datetime
import os

from .common import (
    HISTORY_HEADERS,
    MASTERY_HEADERS,
    extract_category,
    extract_images,
    extract_labels,
    extract_knowledge_tags,
    extract_tag,
    history_path,
    is_suspended_row,
    load_csv,
    load_tuning,
    mastery_path,
    parse_date,
    parse_yaml_frontmatter,
    resolve_sm2_fields,
    split_sections,
)
from .ledger import connect
from .scheduling import (
    _row_to_item,
    _safe_float,
    _safe_int,
    build_fail_counts,
    compute_priority,
    days_since_review,
    is_killed_state,
    is_leech,
    time_decay,
)


def get_stats(vault):
    rows = [resolve_sm2_fields(r) for r in load_csv(mastery_path(vault), MASTERY_HEADERS)]
    history = load_csv(history_path(vault), HISTORY_HEADERS)
    with connect(vault) as db:
        projection_rows = db.execute(
            "SELECT question_id, uid, suspended, archived FROM question_projection"
        ).fetchall()
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
    active_fail_counts = build_fail_counts(active_history, uid_by_qid)
    all_fail_counts = build_fail_counts(history, uid_by_qid)
    today = datetime.date.today()

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
        if is_leech(active_fail_counts.get(uid, 0), mastery, tag, tuning):
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
            days, tag, mastery, active_fail_counts.get(uid, 0), tuning,
            labels=[label.strip() for label in str(row.get("Labels", "") or "").split("|") if label.strip()],
            label_bonuses=label_bonuses,
        )
        if priority > 0.3:
            total_due += 1

    items = [_row_to_item(row, today, all_fail_counts.get(row.get("UID", ""), 0), tuning) for row in rows]

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


def get_question_content(vault, uid):
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
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
    return {
        "uid": uid,
        "subject": meta.get("科目", ""),
        "category": extract_category(meta),
        "difficulty": meta.get("难度", "5"),
        "question": question_text,
        "notes": sections.get("备注", ""),
        "answer": sections.get("答案", ""),
        "history": sections.get("历史", ""),
        "tag": extract_tag(meta),
        "suspended": is_suspended_row(row),
        "knowledge_tags": extract_knowledge_tags(meta),
        "labels": extract_labels(meta),
        "images": extract_images(question_text),
    }
