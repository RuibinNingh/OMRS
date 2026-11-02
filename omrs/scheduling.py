from .common import business_today
from .vault_lifecycle import storage
import datetime
import math

from .common import DEFAULT_TUNING, SM2_EF_MAX, SM2_EF_MIN, is_due, is_suspended_row, load_tuning, parse_date, resolve_sm2_fields
from .log_utils import log_schedule
from .data_repository import mastery_rows, history_rows


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


def revive_dormant_days(stage, tuning=None) -> int:
    """当前复核档位的间隔；累计击杀次数不参与计算。"""
    intervals = (tuning or DEFAULT_TUNING)["revive_intervals_days"]
    stage = max(1, min(len(intervals), _safe_int(stage, 1)))
    return intervals[stage - 1]


def is_revive_eligible(mastery, tag, due_date, today=None) -> bool:
    """已击杀题按实际到期日复燃；无可靠日期的旧题待复核。"""
    return is_killed_state(mastery, tag) and is_due(due_date, today)


def review_cycle(mastery, tag, tuning=None):
    """规范化周期，兼容只有旧快照的题；不得从最后练习日重排现有周期。"""
    if not is_killed_state(mastery.get("mastery", 0), tag):
        return {"revive_stage": 0, "revive_anchor_at": "",
                "due_date": mastery.get("due_date", ""), "interval_days": mastery.get("interval_days", 0)}
    stage = max(0, min(5, _safe_int(mastery.get("revive_stage"), 0)))
    anchor = parse_date(mastery.get("revive_anchor_at", "") if stage else mastery.get("last_review_at", ""))
    due = parse_date(mastery.get("due_date", "")) if stage and anchor else None
    stage = stage or 1
    interval = revive_dormant_days(stage, tuning)
    if anchor:
        due = due or parse_date(_next_revive_date(anchor.isoformat(), interval))
        interval = max(0, (due - anchor).days)
    return {"revive_stage": stage, "revive_anchor_at": anchor.isoformat() if anchor else "",
            "due_date": due.isoformat() if due else "", "interval_days": interval}


def resolve_review_fields(row, tuning=None):
    """统一推荐、统计与导出的排期；旧击杀快照统一从第1档起步。"""
    row = dict(row)
    if not is_killed_state(row.get("Mastery", 0), row.get("Current_Tag", "")):
        return resolve_sm2_fields(row)
    cycle = review_cycle({"mastery": row.get("Mastery"), "revive_stage": row.get("Revive_Stage"),
                          "revive_anchor_at": row.get("Revive_Anchor", ""), "due_date": row.get("Due_Date", ""),
                          "last_review_at": row.get("Last_Review", "")}, row.get("Current_Tag", ""), tuning)
    row.update(Revive_Stage=cycle["revive_stage"], Revive_Anchor=cycle["revive_anchor_at"],
               Due_Date=cycle["due_date"], Interval=str(cycle["interval_days"]))
    return row


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


def build_fail_counts(history, uid_by_question_id=None) -> dict:
    """统计累计答错次数；可按稳定 question_id 映射到当前 UID。"""
    counts = {}
    for log in history or []:
        if str(log.get("Is_Correct", "")).strip() == "0":
            question_id = (log.get("Question_ID") or "").strip()
            if question_id and uid_by_question_id is not None:
                uid = (uid_by_question_id.get(question_id) or "").strip()
            else:
                uid = (log.get("UID") or "").strip()
            if uid:
                counts[uid] = counts.get(uid, 0) + 1
    return counts


def build_wrong_streaks(history, uid_by_question_id=None) -> dict:
    """按 Ledger 投影顺序统计每题末尾的连续答错次数；答对即清零。"""
    streaks = {}
    for log in history or []:
        question_id = (log.get("Question_ID") or "").strip()
        if question_id and uid_by_question_id is not None:
            uid = (uid_by_question_id.get(question_id) or "").strip()
        else:
            uid = (log.get("UID") or "").strip()
        if not uid:
            continue
        result = str(log.get("Is_Correct", "")).strip()
        if result == "0":
            streaks[uid] = streaks.get(uid, 0) + 1
        elif result == "1":
            streaks[uid] = 0
    return streaks


def is_leech(wrong_streak, mastery, tag, tuning=None) -> bool:
    """顽固题：未击杀且最近连续答错次数达到阈值。"""
    t = tuning or DEFAULT_TUNING
    if is_killed_state(mastery, tag):
        return False
    return _safe_int(wrong_streak, 0) >= t["leech_fail_threshold"]


def compute_priority(decayed_mastery, ef, days, tag, mastery,
                     wrong_streak=0, tuning=None, labels=None, label_bonuses=None,
                     is_revived=False) -> float:
    """统一的调度优先级公式（此前在 3 处各写一份，现集中于此）。

    priority = (1-decayed)×(eff_diff/10) + (days/divisor)×weight
               + 待攻克低熟练度加成 + leech 加成 + 复燃加成
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
    if is_leech(wrong_streak, mastery, tag, t):
        priority += t["leech_priority_bonus"]
    if is_revived:
        priority += t.get("revive_priority_bonus", 0.3)
    if labels and label_bonuses:
        try:
            priority += min(
                max(0.0, float(t.get("label_bonus_cap", 1.0))),
                sum(max(0.0, float(label_bonuses.get(label, 0) or 0)) for label in labels),
            )
        except (TypeError, ValueError):
            pass
    return priority


def days_since_review(value: str, today=None, default=30):
    today = today or business_today()
    parsed = parse_date(value)
    return max(0, (today - parsed).days) if parsed else default


def _next_revive_date(last_review: str, dormant_days: int) -> str:
    """已击杀题预计复燃的日期（供界面显示「下次复燃」）。"""
    parsed = parse_date(last_review or "")
    if not parsed:
        return ""
    days = min((datetime.date.max - parsed).days, max(0, _safe_int(dormant_days, 0)))
    return (parsed + datetime.timedelta(days=days)).isoformat()


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
        label, new_m, tag_action = "已击杀", 1.0, "kill"
    elif (not high) and is_correct:
        label, tag_action = "磨合中", "keep"
        new_m = min(0.95, old_m + sub_score / 30.0 * (ef / 2.5))
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


def transition_review(question, mastery, review, tuning):
    """唯一反馈转换：网页响应、增量应用和完整重放共用，不读取磁盘。"""
    from .common import calc_sm2_interval, compute_due_date
    old_m = _safe_float(mastery.get("mastery"), 0)
    correct = bool(review.get("is_correct"))
    attempts = _safe_int(mastery.get("attempts"), 0) + 1
    update = compute_mastery_update(old_m, mastery.get("ef", 2.5), review.get("sub_score", 0),
                                   correct, attempts, mastery.get("high_correct_streak", 0), tuning)
    was_killed = is_killed_state(old_m, question.get("current_tag", ""))
    high_correct = update["tag_action"] == "kill"
    demote = not correct and was_killed
    new_m = min(update["mastery"], old_m * tuning["kill_demote_factor"]) if demote else update["mastery"]
    repetition = _safe_int(mastery.get("repetition"), 0) + 1 if correct else 0
    interval = calc_sm2_interval(_safe_int(mastery.get("interval_days"), 0), repetition, update["ef"],
                                source=review.get("source", "due"),
                                proficiency_factor=tuning["proficiency_factor"]) if correct else 1
    day = str(review.get("review_date") or review.get("occurred_at") or review.get("recorded_at") or "")[:10]
    if not day:
        raise ValueError("反馈缺少业务日期")
    interval = min(interval, (datetime.date.max - datetime.date.fromisoformat(day)).days)
    stage, anchor, kill_delta = 0, "", 0
    due = compute_due_date(day, interval)
    if high_correct:
        cycle = review_cycle(mastery, question.get("current_tag", ""), tuning)
        if was_killed and cycle["revive_anchor_at"] and (day < cycle["due_date"] or day <= cycle["revive_anchor_at"]):
            stage, anchor = cycle["revive_stage"], cycle["revive_anchor_at"]
            interval, due = cycle["interval_days"], cycle["due_date"]
        else:
            stage = min(5, cycle["revive_stage"] + 1) if was_killed and cycle["revive_anchor_at"] and day > cycle["revive_anchor_at"] else 1
            anchor, kill_delta = day, 1
            interval = min(revive_dormant_days(stage, tuning), (datetime.date.max - datetime.date.fromisoformat(day)).days)
            due = compute_due_date(day, interval)
        tag = "#状态/已击杀"
    elif was_killed:
        tag = "#状态/待攻克"
        repetition = 0
        interval = min(3 if correct else 1, (datetime.date.max - datetime.date.fromisoformat(day)).days)
        due = compute_due_date(day, interval)
    else:
        tag = question.get("current_tag", "")
    result = {"mastery": round(new_m, 4), "ef": update["ef"], "attempts": attempts,
              "high_correct_streak": _safe_int(update["high_correct_streak"], 0), "repetition": repetition,
              "interval_days": interval, "due_date": due, "last_review_at": day,
              "revive_stage": stage, "revive_anchor_at": anchor,
              "kill_count": _safe_int(mastery.get("kill_count"), 0) + kill_delta}
    display = {"label": update["label"], "old_mastery": old_m, "new_mastery": result["mastery"],
               "tag": tag, "new_interval": interval, "new_due_date": result["due_date"], "revive_stage": stage}
    return result, tag, display


@storage
def schedule_questions(vault, count=10, subject=None, exclude_uids=None):
    """原有优先级调度（保留兼容，Phase 2 后由 recommend 替代）。"""
    rows = mastery_rows(vault)
    tuning = load_tuning(vault)
    today = business_today()
    scored = []
    count = max(0, _safe_int(count, 10))
    excluded = set(_normalize_uid_list(exclude_uids))

    from .labels import label_priority_map
    label_bonuses = label_priority_map(vault)
    for row in rows:
        if is_suspended_row(row):
            continue
        if subject and row.get("Subject", "") != subject:
            continue
        if row.get("UID", "") in excluded:
            continue
        row = resolve_review_fields(row, tuning)
        mastery = _safe_float(row.get("Mastery", 0))
        tag = row.get("Current_Tag", "")

        # 已击杀题默认跳过；休眠够久（复燃周期）的重新入列
        revived = is_revive_eligible(
            mastery, tag, row.get("Due_Date", ""), today,
        )
        if is_killed_state(mastery, tag) and not revived:
            continue

        days = days_since_review(row.get("Last_Review", ""), today, 30)

        decayed_mastery = time_decay(
            mastery, days, tuning["decay_mastery_factor"], tuning["decay_base"]
        )
        priority = compute_priority(
            decayed_mastery, _safe_float(row.get("EF", 2.5), 2.5),
            days, tag, mastery, tuning=tuning,
            labels=_row_labels(row), label_bonuses=label_bonuses,
            is_revived=revived,
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


@storage
def generate_recommendations(vault, due_count=10, prof_count=10,
                             subject=None, category=None, knowledge_tag=None,
                             label=None, exclude_uids=None, label_mode="any"):
    """生成双列表推荐：到期列表 + 熟练度列表，互斥分配。

    返回:
      {"due": [...], "proficiency": [...]}
    """


    # Treat malformed and negative limits as zero.  In particular, a
    # negative Python slice would otherwise return almost the entire list
    # (e.g. ``items[:-1]``), violating the API's count contract.
    due_count = max(0, _safe_int(due_count, 0))
    prof_count = max(0, _safe_int(prof_count, 0))

    rows = mastery_rows(vault)
    history = history_rows(vault)
    from .ledger import connect
    with connect(vault) as db:
        uid_by_qid = {
            row["question_id"]: row["uid"]
            for row in db.execute(
                "SELECT question_id, uid FROM question_projection WHERE archived = 0"
            ).fetchall()
        }
    fail_counts = build_fail_counts(history, uid_by_qid)
    wrong_streaks = build_wrong_streaks(history, uid_by_qid)
    tuning = load_tuning(vault)
    from .labels import label_priority_map
    label_bonuses = label_priority_map(vault)
    requested_labels = [label] if isinstance(label, str) else [
        str(value).strip() for value in (label or []) if str(value).strip()
    ]
    if label_mode not in ("any", "all"):
        raise ValueError("标记匹配方式只能为 any 或 all")
    today = business_today()
    excluded = set(_normalize_uid_list(exclude_uids))

    due_candidates = []
    prof_candidates = []

    for row in rows:
        uid = row.get("UID", "")
        if is_suspended_row(row):
            continue
        if uid in excluded:
            continue
        row = resolve_review_fields(row, tuning)
        mastery = _safe_float(row.get("Mastery", 0))
        tag = row.get("Current_Tag", "")

        # 已击杀题只在实际复核日到期后重新入列
        if is_killed_state(mastery, tag) and not is_revive_eligible(
            mastery, tag, row.get("Due_Date", ""), today,
        ):
            continue

        if subject and row.get("Subject", "") != subject:
            continue

        if category and row.get("Category", "") != category:
            continue

        if knowledge_tag and knowledge_tag not in _knowledge_tags(row):
            continue
        if requested_labels and not (all if label_mode == "all" else any)(
            value in _row_labels(row) for value in requested_labels
        ):
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
        revived = is_revive_eligible(
            mastery, tag, row.get("Due_Date", ""), today,
        )
        priority = compute_priority(
            decayed, _safe_float(row.get("EF", 2.5), 2.5),
            days, tag, mastery, wrong_streaks.get(uid, 0), tuning,
            labels=_row_labels(row), label_bonuses=label_bonuses,
            is_revived=revived,
        )
        prof_scored.append((priority, row))

    prof_scored.sort(key=lambda x: x[0], reverse=True)

    # 如果请求的数量很大（>=500），返回所有题目（用于前端智能推荐）
    # 否则按原逻辑限制数量
    effective_due_count = len(due_candidates) if due_count >= 500 else due_count
    effective_prof_count = len(prof_scored) if prof_count >= 500 else prof_count

    due_result = []
    for row in due_candidates[:effective_due_count]:
        uid = row.get("UID", "")
        item = _row_to_item(row, today, fail_counts.get(uid, 0), tuning, wrong_streaks.get(uid, 0))
        item["_source"] = "due"
        item["_overdue_days"] = _overdue_days(row.get("Due_Date", ""), today)
        due_result.append(item)

    prof_result = []
    for _, row in prof_scored[:effective_prof_count]:
        uid = row.get("UID", "")
        item = _row_to_item(row, today, fail_counts.get(uid, 0), tuning, wrong_streaks.get(uid, 0))
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


def _knowledge_tags(row):
    return [tag for tag in row.get("Knowledge_Tags", "").split("|") if tag]


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


def _row_to_item(row, today=None, fail_count=0, tuning=None, wrong_streak=0):
    today = today or business_today()
    t = tuning or DEFAULT_TUNING
    row = resolve_review_fields(row, t)
    mastery = _safe_float(row.get("Mastery", 0))
    tag = row.get("Current_Tag", "")
    days = days_since_review(row.get("Last_Review", ""), today, 0)
    last_review = row.get("Last_Review", "")
    kill_count = _safe_int(row.get("Kill_Count", 0), 0)
    stage = _safe_int(row.get("Revive_Stage"), 0)
    dormant_days = revive_dormant_days(stage, t)
    is_revived = is_revive_eligible(mastery, tag, row.get("Due_Date", ""), today)
    return {
        "question_id": row.get("question_id", ""),
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
        "last_review": last_review,
        "interval": _safe_int(row.get("Interval", 0), 0),
        "due_date": row.get("Due_Date", ""),
        "repetition": _safe_int(row.get("Repetition", 0), 0),
        "tag": tag,
        "entry_date": row.get("Entry_Date", ""),
        "created_at": row.get("created_at", row.get("Created_At", "")) or "",
        "knowledge_tags": [k for k in row.get("Knowledge_Tags", "").split("|") if k],
        "labels": _row_labels(row),
        "suspended": is_suspended_row(row),
        "fail_count": _safe_int(fail_count, 0),
        "wrong_streak": _safe_int(wrong_streak, 0),
        "is_leech": is_leech(wrong_streak, mastery, tag, t),
        # 复核档位与累计成绩分离；实际到期日不受提前练习影响
        "kill_count": kill_count,
        "revive_stage": stage,
        "revive_anchor_at": row.get("Revive_Anchor", ""),
        "is_revived": is_revived,
        "dormant_days": dormant_days if is_killed_state(mastery, tag) else 0,
        "next_revive_date": row.get("Due_Date", "")
        if is_killed_state(mastery, tag) else "",
    }


def _row_labels(row):
    return [label.strip() for label in str(row.get("Labels", "") or "").split("|") if label.strip()]


@storage
def get_items_by_uids(vault, uids):
    clean_uids = _normalize_uid_list(uids)
    rows = mastery_rows(vault)
    row_map = {row["UID"]: row for row in rows}
    missing = [uid for uid in clean_uids if uid not in row_map]
    if missing:
        raise RuntimeError("以下 UID 不存在: " + ", ".join(missing))
    suspended = [uid for uid in clean_uids if is_suspended_row(row_map[uid])]
    if suspended:
        raise RuntimeError("以下 UID 已停用，不能加入复习: " + ", ".join(suspended))
    today = business_today()
    tuning = load_tuning(vault)
    return [_row_to_item(row_map[uid], today, tuning=tuning) for uid in clean_uids]
