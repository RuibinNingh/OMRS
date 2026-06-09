"""数据复盘分析：从 mastery_data.csv + history_log.csv 派生尽可能丰富的统计，
供前端「数据」页展示，并生成可导出的复盘报告（程序生成的复盘数据 + 给 AI 分析的原始数据）。

对应 API：
  GET /api/analytics       → get_analytics()
  GET /api/export-review   → build_review_markdown()
"""

import datetime
import json
import os

from .common import (
    HISTORY_HEADERS,
    MASTERY_HEADERS,
    extract_images,
    history_path,
    load_csv,
    load_tuning,
    mastery_path,
    parse_date,
    resolve_sm2_fields,
    split_sections,
)
from .scheduling import (
    _safe_float,
    _safe_int,
    build_fail_counts,
    days_since_review,
    ef_to_difficulty,
    is_killed_state,
    is_leech,
    time_decay,
)

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _question_images(vault, file_path):
    """读取题目 md 的「题目」区，解析其引用的图片文件名（失败返回空）。"""
    if not file_path:
        return []
    # File_Path 可能含 Windows 反斜杠，归一化以跨平台命中
    rel = file_path.replace("\\", "/")
    full = os.path.join(vault, *rel.split("/"))
    if not os.path.isfile(full):
        return []
    try:
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []
    return extract_images(split_sections(content).get("题目", ""))


def _parse_dt(value):
    """解析 history 的 'YYYY-MM-DD HH:MM' → (date, hour) 或 (None, None)。"""
    if not value:
        return None, None
    text = str(value).strip()
    datepart = text[:10]
    d = parse_date(datepart)
    hour = None
    if len(text) >= 16 and ":" in text[10:]:
        try:
            hour = int(text[11:13])
        except ValueError:
            hour = None
    return d, hour


def _accuracy(correct, total):
    return round(correct / total, 4) if total else None


def _streaks(dates):
    """连续复习天数：返回 (current_streak, longest_streak, active_days)。"""
    uniq = sorted({d for d in dates if d})
    if not uniq:
        return 0, 0, 0
    longest = run = 1
    for i in range(1, len(uniq)):
        if (uniq[i] - uniq[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    # 当前连续：从最后一个复习日往前数；若最后复习日不是今天/昨天则当前连续仍以最后一段计
    today = datetime.date.today()
    last = uniq[-1]
    if (today - last).days > 1:
        current = 0
    else:
        current = 1
        for i in range(len(uniq) - 1, 0, -1):
            if (uniq[i] - uniq[i - 1]).days == 1:
                current += 1
            else:
                break
    return current, longest, len(uniq)


def _bucket_label(value, edges, labels):
    for i, edge in enumerate(edges):
        if value < edge:
            return labels[i]
    return labels[-1]


def get_analytics(vault):
    rows = [resolve_sm2_fields(r) for r in load_csv(mastery_path(vault), MASTERY_HEADERS)]
    history = load_csv(history_path(vault), HISTORY_HEADERS)
    tuning = load_tuning(vault)
    fail_counts = build_fail_counts(history)
    today = datetime.date.today()

    total = len(rows)

    # ── 全量题目快照 ──
    items = []
    sum_m = sum_dm = sum_ef = sum_attempts = 0.0
    killed = leech_total = never_reviewed = 0
    for row in rows:
        uid = row.get("UID", "")
        mastery = _safe_float(row.get("Mastery", 0))
        ef = _safe_float(row.get("EF", 2.5), 2.5)
        attempts = _safe_int(row.get("Attempts", 0), 0)
        tag = row.get("Current_Tag", "")
        days = days_since_review(row.get("Last_Review", ""), today, 0)
        decayed = time_decay(mastery, days, tuning["decay_mastery_factor"], tuning["decay_base"])
        fc = fail_counts.get(uid, 0)
        leech = is_leech(fc, mastery, tag, tuning)
        killed_flag = is_killed_state(mastery, tag)
        if killed_flag:
            killed += 1
        if leech:
            leech_total += 1
        if attempts == 0:
            never_reviewed += 1
        sum_m += mastery
        sum_dm += decayed
        sum_ef += ef
        sum_attempts += attempts
        items.append({
            "uid": uid,
            "subject": row.get("Subject", ""),
            "category": row.get("Category", ""),
            "difficulty": _safe_int(row.get("Difficulty", 5), 5),
            "eff_difficulty": round(ef_to_difficulty(ef), 1),
            "mastery": round(mastery, 3),
            "decayed_mastery": round(decayed, 3),
            "ef": round(ef, 2),
            "attempts": attempts,
            "fail_count": fc,
            "is_leech": leech,
            "is_killed": killed_flag,
            "repetition": _safe_int(row.get("Repetition", 0), 0),
            "interval": _safe_int(row.get("Interval", 0), 0),
            "due_date": row.get("Due_Date", ""),
            "last_review": row.get("Last_Review", ""),
            "tag": tag,
            "days_since_review": days,
            "images": _question_images(vault, row.get("File_Path", "")),
        })

    # ── 历史派生 ──
    total_reviews = len(history)
    total_correct = sum(1 for h in history if str(h.get("Is_Correct", "")).strip() == "1")
    total_wrong = total_reviews - total_correct
    review_dates = []
    by_weekday = {w: 0 for w in WEEKDAYS}
    by_hour = {h: 0 for h in range(24)}
    by_score = {s: {"count": 0, "correct": 0} for s in range(11)}
    uid_reviews = {}        # uid -> [count, correct]
    weekly = {}             # iso year-week -> [count, correct]
    daily = {}
    for h in history:
        d, hour = _parse_dt(h.get("Date", ""))
        correct = str(h.get("Is_Correct", "")).strip() == "1"
        uid = (h.get("UID") or "").strip()
        score = _safe_int(h.get("Sub_Score", 0), 0)
        if 0 <= score <= 10:
            by_score[score]["count"] += 1
            by_score[score]["correct"] += 1 if correct else 0
        if uid:
            ur = uid_reviews.setdefault(uid, [0, 0])
            ur[0] += 1
            ur[1] += 1 if correct else 0
        if d:
            review_dates.append(d)
            by_weekday[WEEKDAYS[d.weekday()]] += 1
            iso = d.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            w = weekly.setdefault(wk, [0, 0])
            w[0] += 1
            w[1] += 1 if correct else 0
            key = d.isoformat()
            daily[key] = daily.get(key, 0) + 1
        if hour is not None:
            by_hour[hour] += 1

    current_streak, longest_streak, active_days = _streaks(review_dates)
    first_review = min(review_dates).isoformat() if review_dates else ""
    last_review = max(review_dates).isoformat() if review_dates else ""

    reviews_last_7 = sum(1 for d in review_dates if (today - d).days < 7)
    reviews_last_30 = sum(1 for d in review_dates if (today - d).days < 30)

    # ── 科目维度 ──
    subj = {}
    for it in items:
        s = it["subject"] or "未分类"
        bucket = subj.setdefault(s, {"subject": s, "total": 0, "killed": 0, "attacking": 0,
                                     "leech": 0, "sum_m": 0.0, "sum_ef": 0.0,
                                     "reviews": 0, "correct": 0})
        bucket["total"] += 1
        bucket["killed"] += 1 if it["is_killed"] else 0
        bucket["attacking"] += 0 if it["is_killed"] else 1
        bucket["leech"] += 1 if it["is_leech"] else 0
        bucket["sum_m"] += it["mastery"]
        bucket["sum_ef"] += it["ef"]
        ur = uid_reviews.get(it["uid"], [0, 0])
        bucket["reviews"] += ur[0]
        bucket["correct"] += ur[1]
    subjects = []
    for s, b in subj.items():
        subjects.append({
            "subject": s, "total": b["total"], "killed": b["killed"],
            "attacking": b["attacking"], "leech": b["leech"],
            "avg_mastery": round(b["sum_m"] / b["total"], 3) if b["total"] else 0,
            "avg_ef": round(b["sum_ef"] / b["total"], 2) if b["total"] else 0,
            "reviews": b["reviews"], "accuracy": _accuracy(b["correct"], b["reviews"]),
        })
    subjects.sort(key=lambda x: x["avg_mastery"])

    # ── 分类维度 ──
    cat = {}
    for it in items:
        c = it["category"] or "未分类"
        bucket = cat.setdefault(c, {"category": c, "subject": it["subject"],
                                    "total": 0, "sum_m": 0.0, "reviews": 0, "correct": 0,
                                    "leech": 0})
        bucket["total"] += 1
        bucket["sum_m"] += it["mastery"]
        bucket["leech"] += 1 if it["is_leech"] else 0
        ur = uid_reviews.get(it["uid"], [0, 0])
        bucket["reviews"] += ur[0]
        bucket["correct"] += ur[1]
    categories = []
    for c, b in cat.items():
        categories.append({
            "category": c, "subject": b["subject"], "total": b["total"],
            "avg_mastery": round(b["sum_m"] / b["total"], 3) if b["total"] else 0,
            "reviews": b["reviews"], "accuracy": _accuracy(b["correct"], b["reviews"]),
            "leech": b["leech"],
        })
    categories.sort(key=lambda x: x["avg_mastery"])

    # ── 分布 ──
    def hist10(getter):
        out = {f"{i*10}-{(i+1)*10}": 0 for i in range(10)}
        for it in items:
            v = max(0.0, min(1.0, getter(it)))
            idx = min(9, int(v * 10))
            out[f"{idx*10}-{(idx+1)*10}"] += 1
        return out

    mastery_histogram = hist10(lambda it: it["mastery"])
    decayed_histogram = hist10(lambda it: it["decayed_mastery"])

    ef_dist = {"1.3-1.7": 0, "1.7-2.1": 0, "2.1-2.5": 0, "2.5-3.0": 0}
    for it in items:
        ef_dist[_bucket_label(it["ef"], [1.7, 2.1, 2.5], list(ef_dist.keys()))] += 1

    difficulty_dist = {str(i): 0 for i in range(1, 11)}
    for it in items:
        difficulty_dist[str(max(1, min(10, it["difficulty"])))] += 1

    repetition_dist = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
    for it in items:
        r = it["repetition"]
        repetition_dist["5+" if r >= 5 else str(r)] += 1

    interval_dist = {"0-1": 0, "2-6": 0, "7-15": 0, "16-30": 0, "31-60": 0, "60+": 0}
    for it in items:
        interval_dist[_bucket_label(it["interval"], [2, 7, 16, 31, 61], list(interval_dist.keys()))] += 1

    # 主观分维度正确率
    score_accuracy = {}
    for s in range(11):
        c = by_score[s]["count"]
        score_accuracy[str(s)] = {"count": c, "correct": by_score[s]["correct"],
                                  "accuracy": _accuracy(by_score[s]["correct"], c)}

    # 周维度正确率（按时间升序，取最近 12 周）
    weekly_accuracy = []
    for wk in sorted(weekly.keys())[-12:]:
        cnt, cor = weekly[wk]
        weekly_accuracy.append({"week": wk, "reviews": cnt, "correct": cor,
                                "accuracy": _accuracy(cor, cnt)})

    # 每日趋势（近 30 天）
    daily_trend = {}
    for off in range(30):
        dt = (today - datetime.timedelta(days=29 - off)).isoformat()
        daily_trend[dt] = daily.get(dt, 0)

    # ── 到期预测 + 预警 ──
    overdue = due_today = 0
    forecast = {str(i): 0 for i in range(8)}  # 0=今天..7；逾期单列
    forecast["overdue"] = 0
    forecast["7+"] = 0
    urgent = warning = cold = total_due = 0
    for it in items:
        if it["is_killed"]:
            continue
        dd = parse_date(it["due_date"])
        if dd:
            delta = (dd - today).days
            if delta < 0:
                overdue += 1
                forecast["overdue"] += 1
            elif delta == 0:
                due_today += 1
                forecast["0"] += 1
            elif delta <= 7:
                forecast[str(delta)] += 1
            else:
                forecast["7+"] += 1
        days = it["days_since_review"] if it["days_since_review"] else days_since_review(it["last_review"], today, 30)
        dm = it["decayed_mastery"]
        if dm < 0.3 and days > 7:
            urgent += 1
        if dm < 0.5 and days > 14:
            warning += 1
        if days > 30:
            cold += 1

    # ── 薄弱点 ──
    leeches = sorted([it for it in items if it["is_leech"]],
                     key=lambda x: (-x["fail_count"], x["mastery"]))[:20]
    struggling = sorted([it for it in items
                         if not it["is_killed"] and it["attempts"] >= 3 and it["mastery"] < 0.4],
                        key=lambda x: x["mastery"])[:20]
    traps = [it for it in items if "易错" in (it["tag"] or "")]
    recently_killed = sorted([it for it in items if it["is_killed"]],
                             key=lambda x: x["last_review"], reverse=True)[:20]

    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overview": {
            "total": total, "killed": killed, "attacking": total - killed,
            "leech": leech_total, "never_reviewed": never_reviewed,
            "avg_mastery": round(sum_m / total, 3) if total else 0,
            "avg_decayed_mastery": round(sum_dm / total, 3) if total else 0,
            "avg_ef": round(sum_ef / total, 2) if total else 0,
            "avg_attempts": round(sum_attempts / total, 2) if total else 0,
            "total_reviews": total_reviews, "total_correct": total_correct,
            "total_wrong": total_wrong, "accuracy": _accuracy(total_correct, total_reviews),
            "first_review": first_review, "last_review": last_review,
            "active_days": active_days, "current_streak": current_streak,
            "longest_streak": longest_streak,
            "reviews_last_7": reviews_last_7, "reviews_last_30": reviews_last_30,
        },
        "subjects": subjects,
        "categories": categories,
        "distributions": {
            "mastery_histogram": mastery_histogram,
            "decayed_histogram": decayed_histogram,
            "ef_dist": ef_dist,
            "difficulty_dist": difficulty_dist,
            "repetition_dist": repetition_dist,
            "interval_dist": interval_dist,
        },
        "accuracy": {
            "by_score": score_accuracy,
            "weekly": weekly_accuracy,
        },
        "behavior": {
            "by_weekday": by_weekday,
            "by_hour": by_hour,
            "daily_trend": daily_trend,
        },
        "forecast": forecast,
        "review_alert": {"urgent": urgent, "warning": warning, "cold": cold,
                         "total_due": overdue + due_today, "leech": leech_total,
                         "overdue": overdue, "due_today": due_today},
        "weak_spots": {
            "leeches": leeches, "struggling": struggling,
            "traps": traps, "recently_killed": recently_killed,
        },
        "items": items,
    }


# ──────────────────────────────────────────────────────────
# 复盘报告 Markdown 导出
# ──────────────────────────────────────────────────────────

def _md_table(headers, rows):
    if not rows:
        return "_（无数据）_\n"
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return f"{head}\n{sep}\n{body}\n"


def _pct(value):
    return "—" if value is None else f"{value*100:.0f}%"


def build_review_markdown(vault):
    """生成复盘报告 Markdown：上半部分为程序生成的复盘数据，
    下半部分为给 AI 分析的原始历史 + 机器可读 JSON。

    返回 (bytes, filename)。
    """
    a = get_analytics(vault)
    history = load_csv(history_path(vault), HISTORY_HEADERS)
    today = datetime.date.today().isoformat()
    ov = a["overview"]

    L = []
    L.append(f"# OMRS 错题复盘报告")
    L.append(f"\n> 生成时间：{a['generated_at']}　|　报告基准日：{today}\n")
    L.append("本报告分两部分：**一、复盘数据**（程序统计，供你阅读理解）；**二、历史数据**（原始记录 + 机器可读 JSON，供 AI 深入分析）。\n")

    L.append("\n---\n\n# 一、复盘数据\n")

    L.append("## 1. 总览\n")
    L.append(_md_table(
        ["指标", "值", "指标", "值"],
        [
            ["总题数", ov["total"], "总复习次数", ov["total_reviews"]],
            ["已击杀", f'{ov["killed"]}（{_pct(_accuracy(ov["killed"], ov["total"]))}）', "总体正确率", _pct(ov["accuracy"])],
            ["待攻克", ov["attacking"], "答对 / 答错", f'{ov["total_correct"]} / {ov["total_wrong"]}'],
            ["顽固题(leech)", ov["leech"], "从未复习", ov["never_reviewed"]],
            ["平均熟练度", _pct(ov["avg_mastery"]), "平均衰减后", _pct(ov["avg_decayed_mastery"])],
            ["平均 EF", ov["avg_ef"], "平均复习次数", ov["avg_attempts"]],
            ["活跃天数", ov["active_days"], "当前连续 / 最长连续", f'{ov["current_streak"]} / {ov["longest_streak"]} 天'],
            ["近 7 天复习", ov["reviews_last_7"], "近 30 天复习", ov["reviews_last_30"]],
            ["首次复习", ov["first_review"] or "—", "最近复习", ov["last_review"] or "—"],
        ],
    ))

    L.append("\n## 2. 科目维度（按平均熟练度升序，最薄弱在前）\n")
    L.append(_md_table(
        ["科目", "题数", "已击杀", "待攻克", "leech", "平均熟练度", "平均EF", "复习次数", "正确率"],
        [[s["subject"], s["total"], s["killed"], s["attacking"], s["leech"],
          _pct(s["avg_mastery"]), s["avg_ef"], s["reviews"], _pct(s["accuracy"])]
         for s in a["subjects"]],
    ))

    L.append("\n## 3. 分类维度（最薄弱 Top 20）\n")
    L.append(_md_table(
        ["分类", "科目", "题数", "平均熟练度", "复习次数", "正确率", "leech"],
        [[c["category"], c["subject"], c["total"], _pct(c["avg_mastery"]),
          c["reviews"], _pct(c["accuracy"]), c["leech"]]
         for c in a["categories"][:20]],
    ))

    dist = a["distributions"]
    L.append("\n## 4. 分布\n")
    L.append("**熟练度分布（原始 / 衰减后）**\n")
    L.append(_md_table(
        ["区间", "原始题数", "衰减后题数"],
        [[k, dist["mastery_histogram"][k], dist["decayed_histogram"][k]]
         for k in dist["mastery_histogram"]],
    ))
    L.append("\n**EF / 难度 / Repetition / Interval 分布**\n")
    L.append("- EF：" + "，".join(f"{k} = {v}" for k, v in dist["ef_dist"].items()) + "\n")
    L.append("- 难度：" + "，".join(f"Lv{k} = {v}" for k, v in dist["difficulty_dist"].items()) + "\n")
    L.append("- Repetition：" + "，".join(f"{k} = {v}" for k, v in dist["repetition_dist"].items()) + "\n")
    L.append("- Interval(天)：" + "，".join(f"{k} = {v}" for k, v in dist["interval_dist"].items()) + "\n")

    L.append("\n## 5. 正确率分析\n")
    L.append("**按主观分**\n")
    L.append(_md_table(
        ["主观分", "次数", "答对", "正确率"],
        [[s, a["accuracy"]["by_score"][s]["count"], a["accuracy"]["by_score"][s]["correct"],
          _pct(a["accuracy"]["by_score"][s]["accuracy"])]
         for s in a["accuracy"]["by_score"] if a["accuracy"]["by_score"][s]["count"]],
    ))
    L.append("\n**按周（最近 12 周）**\n")
    L.append(_md_table(
        ["周", "复习次数", "答对", "正确率"],
        [[w["week"], w["reviews"], w["correct"], _pct(w["accuracy"])] for w in a["accuracy"]["weekly"]],
    ))

    beh = a["behavior"]
    L.append("\n## 6. 复习行为\n")
    L.append("**按星期**：" + "，".join(f"{k} {v}" for k, v in beh["by_weekday"].items()) + "\n")
    active_hours = {k: v for k, v in beh["by_hour"].items() if v}
    L.append("\n**按时段（有记录的小时）**：" +
             ("，".join(f"{h:02d}:00 = {c}" for h, c in active_hours.items()) if active_hours else "无") + "\n")

    fc = a["forecast"]
    al = a["review_alert"]
    L.append("\n## 7. 到期与预警\n")
    L.append(f"- 逾期 **{fc['overdue']}** 题，今日到期 **{fc['0']}** 题。\n")
    L.append("- 未来 7 天到期预测：" +
             "，".join(f"+{i}天 {fc[str(i)]}" for i in range(1, 8)) + f"，7天以上 {fc['7+']}\n")
    L.append(f"- 预警：急需 {al['urgent']}、警告 {al['warning']}、长期冷落 {al['cold']}、顽固题 {al['leech']}\n")

    ws = a["weak_spots"]
    L.append("\n## 8. 薄弱点与顽固题\n")
    L.append("**顽固题 Leech（累计答错最多 Top 20）**\n")
    L.append(_md_table(
        ["UID", "科目", "分类", "答错次数", "熟练度", "EF", "复习次数"],
        [[it["uid"], it["subject"], it["category"], it["fail_count"],
          _pct(it["mastery"]), it["ef"], it["attempts"]] for it in ws["leeches"]],
    ))
    L.append("\n**屡练不熟（复习≥3次且熟练度<40% Top 20）**\n")
    L.append(_md_table(
        ["UID", "科目", "分类", "熟练度", "复习次数", "答错次数"],
        [[it["uid"], it["subject"], it["category"], _pct(it["mastery"]),
          it["attempts"], it["fail_count"]] for it in ws["struggling"]],
    ))
    L.append(f"\n**易错坑题数**：{len(ws['traps'])}（高分却答错过的题）\n")

    # ── 第二部分：历史数据（供 AI 分析）──
    L.append("\n\n---\n\n# 二、历史数据（供 AI 分析）\n")
    L.append("以下为原始数据，便于 AI 做更深入的个性化分析与建议。\n")

    L.append("\n## A. 全量题目快照\n")
    L.append(_md_table(
        ["UID", "科目", "分类", "难度", "有效难度", "熟练度", "衰减后", "EF", "复习", "答错", "Rep", "Interval", "到期", "状态", "上次复习"],
        [[it["uid"], it["subject"], it["category"], it["difficulty"], it["eff_difficulty"],
          _pct(it["mastery"]), _pct(it["decayed_mastery"]), it["ef"], it["attempts"],
          it["fail_count"], it["repetition"], it["interval"], it["due_date"] or "—",
          ("已击杀" if it["is_killed"] else ("leech" if it["is_leech"] else "待攻克")),
          it["last_review"] or "—"]
         for it in a["items"]],
    ))

    L.append("\n## B. 完整复习历史\n")
    L.append(_md_table(
        ["日期", "UID", "主观分", "对错", "Session", "备注"],
        [[h.get("Date", ""), h.get("UID", ""), h.get("Sub_Score", ""),
          "对" if str(h.get("Is_Correct", "")).strip() == "1" else "错",
          h.get("Session_ID", ""), (h.get("Note", "") or "").replace("|", "/").replace("\n", " ")]
         for h in history],
    ))

    L.append("\n## C. 机器可读数据（JSON）\n")
    L.append("> 包含全部派生指标、题目快照与原始历史，供 AI 精确解析。\n")
    payload = {
        "generated_at": a["generated_at"],
        "analytics": {k: v for k, v in a.items() if k != "items"},
        "items": a["items"],
        "history": history,
    }
    L.append("```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n")

    md = "\n".join(L)
    filename = f"OMRS-复盘-{today}.md"
    return md.encode("utf-8"), filename
