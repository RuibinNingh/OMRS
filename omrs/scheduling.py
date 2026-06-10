import datetime
import math

from .common import (
    DEFAULT_TUNING,
    MASTERY_HEADERS,
    SM2_EF_MAX,
    SM2_EF_MIN,
    is_due,
    load_csv,
    load_tuning,
    mastery_path,
    parse_date,
    resolve_sm2_fields,
)
from .log_utils import log_schedule


def time_decay(mastery: float, days_since: int, factor: float = None, base: float = None) -> float:
    mastery = max(0.0, min(1.0, _safe_float(mastery, 0.0)))
    days_since = max(0, _safe_int(days_since, 0))
    if mastery <= 0:
        return 0.0
    factor = DEFAULT_TUNING["decay_mastery_factor"] if factor is None else factor
    base = DEFAULT_TUNING["decay_base"] if base is None else base
    return mastery * math.exp(-days_since / (mastery * factor + base))


def is_killed_state(mastery: float, tag: str) -> bool:
    return _safe_float(mastery, 0.0) >= 1.0 or "已击杀" in (tag or "")


def ef_to_difficulty(ef) -> float:
    """由 EF 反推「有效难度」(1-10)。

    EF 越低 = 越不稳定 = 越难 = 优先级权重越高。取代此前恒为常数 5、
    从不随表现变化的静态 Difficulty 字段参与优先级计算（Difficulty 仍保留
    在 CSV / 展示 / 导出中，只是不再喂给优先级公式）。
    """
    ef = max(SM2_EF_MIN, min(SM2_EF_MAX, _safe_float(ef, 2.5)))
    span = SM2_EF_MAX - SM2_EF_MIN
    diff = 1.0 + (SM2_EF_MAX - ef) / span * 9.0
    return max(1.0, min(10.0, diff))


def build_fail_counts(history) -> dict:
    """从 history_log 统计每个 UID 的累计答错次数（Is_Correct == 0）。"""
    counts = {}
    for log in history or []:
        if str(log.get("Is_Correct", "")).strip() == "0":
            uid = (log.get("UID") or "").strip()
            if uid:
                counts[uid] = counts.get(uid, 0) + 1
    return counts


def is_leech(fail_count, mastery, tag, tuning=None) -> bool:
    """顽固题：未击杀且历史累计答错次数达到阈值。"""
    t = tuning or DEFAULT_TUNING
    if is_killed_state(mastery, tag):
        return False
    return _safe_int(fail_count, 0) >= t["leech_fail_threshold"]


def compute_priority(decayed_mastery, ef, days, tag, mastery,
                     fail_count=0, tuning=None) -> float:
    """统一的调度优先级公式（此前在 3 处各写一份，现集中于此）。

    priority = (1-decayed)×(eff_diff/10) + (days/divisor)×weight
               + 待攻克低熟练度加成 + leech 加成
    """
    t = tuning or DEFAULT_TUNING
    eff_diff = ef_to_difficulty(ef)
    # decayed_mastery / days 直接参与算术，做与函数内其它参数一致的脏数据保护，
    # 避免 CSV 异常值或上游误传非数字时整次调度/统计崩溃。
    decayed_mastery = max(0.0, min(1.0, _safe_float(decayed_mastery, 0.0)))
    days = max(0, _safe_int(days, 0))
    priority = (1 - decayed_mastery) * (eff_diff / 10.0) \
        + (days / t["priority_days_divisor"]) * t["priority_days_weight"]
    if "待攻克" in (tag or "") and _safe_float(mastery, 0) < t["attack_mastery_threshold"]:
        priority += t["attack_bonus"]
    if is_leech(fail_count, mastery, tag, t):
        priority += t["leech_priority_bonus"]
    return priority


def days_since_review(value: str, today=None, default=30):
    today = today or datetime.date.today()
    parsed = parse_date(value)
    return max(0, (today - parsed).days) if parsed else default


def compute_mastery_update(old_m, ef, sub_score, is_correct, attempts,
                           high_correct_streak=0, tuning=None):
    # 主观分 0-10：分越高越熟练；≥ high_score_threshold 视为"高分/自信"
    t = tuning or DEFAULT_TUNING
    old_m = max(0.0, min(1.0, _safe_float(old_m, 0.0)))
    ef = max(1.3, min(3.0, _safe_float(ef, 2.5)))
    sub_score = max(0, min(10, _safe_int(sub_score, 0)))
    attempts = max(0, _safe_int(attempts, 0))
    high_correct_streak = max(0, _safe_int(high_correct_streak, 0))
    high = sub_score >= t["high_score_threshold"]
    cold = attempts < t["ef_cold_attempts"]

    if high and is_correct:
        high_correct_streak += 1
        if high_correct_streak >= t["kill_streak"]:
            label, new_m, tag_action = "已击杀", 1.0, "kill"
        else:
            label, tag_action = "高分待确认", "keep"
            new_m = min(0.95, old_m + sub_score / 20.0 * (ef / 2.5))
    elif (not high) and is_correct:
        label, tag_action = "磨合中", "keep"
        new_m = min(1.0, old_m + sub_score / 30.0 * (ef / 2.5))
        high_correct_streak = 0
    elif high and (not is_correct):
        label, new_m, tag_action = "粗心/陷阱", old_m * 0.8, "trap"
        high_correct_streak = 0
    else:
        label, new_m, tag_action = "真不会", old_m * 0.3, "lock"
        high_correct_streak = 0

    new_ef = ef
    if not cold:
        if is_correct and high:
            new_ef = min(3.0, ef + t["ef_up"])
        elif not is_correct:
            new_ef = max(1.3, ef - t["ef_down"])

    return {
        "mastery": round(max(0, min(1, new_m)), 4),
        "ef": round(new_ef, 2),
        "high_correct_streak": str(high_correct_streak),
        "tag_action": tag_action,
        "label": label,
    }


def schedule_questions(vault, count=10, subject=None, exclude_uids=None):
    """原有优先级调度（保留兼容，Phase 2 后由 recommend 替代）。"""
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    tuning = load_tuning(vault)
    today = datetime.date.today()
    scored = []
    count = max(0, _safe_int(count, 10))
    excluded = set(_normalize_uid_list(exclude_uids))

    for row in rows:
        if subject and row.get("Subject", "") != subject:
            continue
        if row.get("UID", "") in excluded:
            continue
        row = resolve_sm2_fields(row)
        mastery = _safe_float(row.get("Mastery", 0))
        tag = row.get("Current_Tag", "")

        if is_killed_state(mastery, tag):
            continue

        days = days_since_review(row.get("Last_Review", ""), today, 30)

        decayed_mastery = time_decay(
            mastery, days, tuning["decay_mastery_factor"], tuning["decay_base"]
        )
        priority = compute_priority(
            decayed_mastery, _safe_float(row.get("EF", 2.5), 2.5),
            days, tag, mastery, tuning=tuning,
        )

        scored.append(
            {
                **row,
                "_priority": round(priority, 4),
                "_decayed_m": round(decayed_mastery, 4),
                "_is_due": is_due(row.get("Due_Date", ""), today),
            }
        )

    scored.sort(key=lambda item: item["_priority"], reverse=True)
    result = scored[:count]
    log_schedule(vault, count, subject, result)
    return result


def generate_recommendations(vault, due_count=10, prof_count=10,
                             subject=None, exclude_uids=None):
    """生成双列表推荐：到期列表 + 熟练度列表，互斥分配。

    返回:
      {"due": [...], "proficiency": [...]}
    """
    from .common import HISTORY_HEADERS, history_path

    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    history = load_csv(history_path(vault), HISTORY_HEADERS)
    fail_counts = build_fail_counts(history)
    tuning = load_tuning(vault)
    today = datetime.date.today()
    excluded = set(_normalize_uid_list(exclude_uids))

    due_candidates = []
    prof_candidates = []

    for row in rows:
        uid = row.get("UID", "")
        if uid in excluded:
            continue
        row = resolve_sm2_fields(row)
        mastery = _safe_float(row.get("Mastery", 0))
        tag = row.get("Current_Tag", "")

        if is_killed_state(mastery, tag):
            continue

        if subject and row.get("Subject", "") != subject:
            continue

        if is_due(row.get("Due_Date", ""), today):
            due_candidates.append(row)
        else:
            prof_candidates.append(row)

    # 到期列表排序：已逾期优先 → EF 升序（越不稳定越优先）
    due_candidates.sort(key=lambda r: (
        not _is_overdue(r.get("Due_Date", ""), today),
        _safe_float(r.get("EF", 2.5), 2.5),
    ))

    # 熟练度列表排序：按统一优先级公式降序（含 leech 加成）
    prof_scored = []
    for row in prof_candidates:
        mastery = _safe_float(row.get("Mastery", 0))
        tag = row.get("Current_Tag", "")
        uid = row.get("UID", "")
        days = days_since_review(row.get("Last_Review", ""), today, 30)
        decayed = time_decay(
            mastery, days, tuning["decay_mastery_factor"], tuning["decay_base"]
        )
        priority = compute_priority(
            decayed, _safe_float(row.get("EF", 2.5), 2.5),
            days, tag, mastery, fail_counts.get(uid, 0), tuning,
        )
        prof_scored.append((priority, row))

    prof_scored.sort(key=lambda x: x[0], reverse=True)

    due_result = []
    for row in due_candidates[:due_count]:
        item = _row_to_item(row, today, fail_counts.get(row.get("UID", ""), 0), tuning)
        item["_source"] = "due"
        item["_overdue_days"] = _overdue_days(row.get("Due_Date", ""), today)
        due_result.append(item)

    prof_result = []
    for _, row in prof_scored[:prof_count]:
        item = _row_to_item(row, today, fail_counts.get(row.get("UID", ""), 0), tuning)
        item["_source"] = "proficiency"
        prof_result.append(item)

    return {"due": due_result, "proficiency": prof_result}


def _is_overdue(due_date: str, today) -> bool:
    """Due_Date 严格小于今天 = 已逾期。"""
    if not due_date:
        return False
    dt = parse_date(due_date)
    if not dt:
        return False
    return dt < today


def _overdue_days(due_date: str, today) -> int:
    """计算逾期天数（正数=已逾期，0=今日到期，负数=未到期）。"""
    if not due_date:
        return 0
    dt = parse_date(due_date)
    if not dt:
        return 0
    return (today - dt).days


def _normalize_uid_list(uids):
    clean = []
    seen = set()
    for uid in uids or []:
        uid = (uid or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        clean.append(uid)
    return clean


def _safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _row_to_item(row, today=None, fail_count=0, tuning=None):
    today = today or datetime.date.today()
    t = tuning or DEFAULT_TUNING
    row = resolve_sm2_fields(row)
    mastery = _safe_float(row.get("Mastery", 0))
    tag = row.get("Current_Tag", "")
    days = days_since_review(row.get("Last_Review", ""), today, 0)
    return {
        "uid": row.get("UID", ""),
        "path": row.get("File_Path", ""),
        "subject": row.get("Subject", ""),
        "category": row.get("Category", ""),
        "difficulty": _safe_int(row.get("Difficulty", 5), 5),
        "mastery": round(mastery, 3),
        "decayed_mastery": round(
            time_decay(mastery, days, t["decay_mastery_factor"], t["decay_base"]), 3
        ),
        "ef": round(_safe_float(row.get("EF", 2.5), 2.5), 2),
        "attempts": _safe_int(row.get("Attempts", 0), 0),
        "high_correct_streak": _safe_int(row.get("High_Correct_Streak", 0), 0),
        "last_review": row.get("Last_Review", ""),
        "interval": _safe_int(row.get("Interval", 0), 0),
        "due_date": row.get("Due_Date", ""),
        "repetition": _safe_int(row.get("Repetition", 0), 0),
        "tag": tag,
        "entry_date": row.get("Entry_Date", ""),
        "knowledge_tags": [k for k in row.get("Knowledge_Tags", "").split("|") if k],
        "fail_count": _safe_int(fail_count, 0),
        "is_leech": is_leech(fail_count, mastery, tag, t),
    }


def get_items_by_uids(vault, uids):
    clean_uids = _normalize_uid_list(uids)
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    row_map = {row["UID"]: row for row in rows}
    missing = [uid for uid in clean_uids if uid not in row_map]
    if missing:
        raise RuntimeError("以下 UID 不存在: " + ", ".join(missing))
    today = datetime.date.today()
    return [_row_to_item(row_map[uid], today) for uid in clean_uids]
