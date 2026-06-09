import datetime
import os

from .common import (
    HISTORY_HEADERS,
    MASTERY_HEADERS,
    extract_category,
    extract_images,
    extract_knowledge_tags,
    extract_tag,
    history_path,
    load_csv,
    load_tuning,
    mastery_path,
    parse_yaml_frontmatter,
    split_sections,
)
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
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    history = load_csv(history_path(vault), HISTORY_HEADERS)
    tuning = load_tuning(vault)
    fail_counts = build_fail_counts(history)
    today = datetime.date.today()

    total = len(rows)
    killed = sum(
        1
        for row in rows
        if is_killed_state(_safe_float(row.get("Mastery", 0)), row.get("Current_Tag", ""))
    )
    avg_mastery = sum(_safe_float(row.get("Mastery", 0)) for row in rows) / total if total else 0

    subject_dist = {}
    for row in rows:
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
    for row in rows:
        difficulty = row.get("Difficulty", "5")
        diff_dist[difficulty] = diff_dist.get(difficulty, 0) + 1

    recent = {}
    for log in history:
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
            for row in rows
            if (
                lo <= _safe_float(row.get("Mastery", 0)) <= 1.0
                if bucket == 9
                else lo <= _safe_float(row.get("Mastery", 0)) < hi
            )
        )

    daily_counts = {}
    for log in history:
        dt = log.get("Date", "")[:10]
        if dt:
            daily_counts[dt] = daily_counts.get(dt, 0) + 1
    daily_trend = {}
    for offset in range(30):
        dt = (today - datetime.timedelta(days=29 - offset)).isoformat()
        daily_trend[dt] = daily_counts.get(dt, 0)

    scatter_data = []
    for row in rows:
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
    leech = 0
    for row in rows:
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
        if is_leech(fail_counts.get(uid, 0), mastery, tag, tuning):
            leech += 1
        priority = compute_priority(
            decayed_mastery, _safe_float(row.get("EF", 2.5), 2.5),
            days, tag, mastery, fail_counts.get(uid, 0), tuning,
        )
        if priority > 0.3:
            total_due += 1

    items = [_row_to_item(row, today, fail_counts.get(row.get("UID", ""), 0), tuning) for row in rows]

    return {
        "total": total,
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
        "knowledge_tags": extract_knowledge_tags(meta),
        "images": extract_images(question_text),
    }
