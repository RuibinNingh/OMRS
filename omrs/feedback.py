import datetime
import os
import re

from .common import (
    HISTORY_HEADERS,
    MASTERY_HEADERS,
    calc_sm2_interval,
    history_path,
    load_csv,
    load_tuning,
    mastery_path,
    omrs_data_dir,
    resolve_sm2_fields,
)
from .ledger import append_commit, connect
from .projections import rebuild_projection
from .scheduling import _safe_float, _safe_int, compute_mastery_update
from .sessions import get_session, get_session_uid_sources, mark_session_completed


STATUS_ATTACKING = "状态/待攻克"
STATUS_KILLED = "状态/已击杀"
TRAP_TAG = "标签/易错坑"


def process_feedback(vault, feedbacks, session_id=""):
    omrs_data_dir(vault)
    tuning = load_tuning(vault)
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    row_map = {row["UID"]: row for row in rows}
    history = load_csv(history_path(vault), HISTORY_HEADERS)
    explicit_session_id = bool(session_id)
    question_ids = _question_ids_by_uid(vault)

    # 获取题目来源映射（到期 vs 熟练度）
    uid_sources = {}
    if explicit_session_id:
        uid_sources = get_session_uid_sources(vault, session_id)

    if not session_id:
        session_id = f"EXP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    results = []
    commit_feedbacks = []
    now = datetime.datetime.now(datetime.timezone.utc)

    for feedback in feedbacks:
        uid = (feedback.get("uid") or "").strip()
        try:
            sub_score = _parse_sub_score(feedback.get("sub_score"))
            is_correct = _parse_bool(feedback.get("is_correct"))
        except ValueError as exc:
            results.append({"uid": uid, "status": "error", "msg": str(exc)})
            continue
        note = feedback.get("note", "")

        if uid not in row_map:
            results.append({"uid": uid, "status": "error", "msg": "UID 未找到"})
            continue
        question_id = question_ids.get(uid)
        if not question_id:
            results.append({"uid": uid, "status": "error", "msg": "题目缺少 question_id，请先扫描工作区"})
            continue

        row = resolve_sm2_fields(row_map[uid])
        source = uid_sources.get(uid) or _parse_source(feedback.get("source")) or "due"
        old_mastery = _safe_float(row.get("Mastery", 0))
        # 先把本次复习计入 Attempts，再判定冷启动：
        # 冷启动门 `attempts < 3` 现在统计「含本次」的复习次数，
        # 因此 EF 自第 3 次复习起即可调整（修复此前要到第 4 次才生效的 off-by-one）。
        new_attempts = _safe_int(row.get("Attempts", 0)) + 1
        update = compute_mastery_update(
            old_mastery,
            _safe_float(row.get("EF", 2.5), 2.5),
            sub_score,
            is_correct,
            new_attempts,
            _safe_int(row.get("High_Correct_Streak", 0)),
            tuning,
        )

        old_interval = _safe_int(row.get("Interval", 0), 0)
        old_repetition = _safe_int(row.get("Repetition", 0), 0)

        if is_correct:
            new_repetition = old_repetition + 1
            new_interval = calc_sm2_interval(
                old_interval, new_repetition,
                _safe_float(row.get("EF", 2.5), 2.5),
                source=source,
                proficiency_factor=tuning["proficiency_factor"],
            )
        else:
            new_repetition = 0
            new_interval = 1  # 答错重置为 1 天

        commit_feedbacks.append({
            "question_id": question_id,
            "uid_at_that_time": uid,
            "session_id": session_id,
            "source": source,
            "is_correct": is_correct,
            "sub_score": sub_score,
            "note": note,
            "occurred_at": datetime.date.today().isoformat(),
            "recorded_at": now.isoformat(timespec="seconds"),
        })
        history.append({
            "UID": uid,
            "Session_ID": session_id,
        })

        results.append(
            {
                "uid": uid,
                "status": "ok",
                "label": update["label"],
                "old_mastery": old_mastery,
                "new_mastery": update["mastery"],
                "tag": row["Current_Tag"],
                "source": source,
                "new_interval": new_interval,
                "new_due_date": row["Due_Date"],
            }
        )

    if commit_feedbacks:
        append_commit(vault, "api", "review.batch_submit", f"提交 {len(commit_feedbacks)} 条练习反馈", {
            "session_id": session_id,
            "feedbacks": commit_feedbacks,
        })
        rebuild_projection(vault)
    if explicit_session_id and _session_feedback_complete(vault, session_id, history):
        try:
            mark_session_completed(vault, session_id)
        except Exception:
            pass
    return results


def _question_ids_by_uid(vault):
    with connect(vault) as db:
        rows = db.execute("SELECT question_id, uid FROM question_projection WHERE archived = 0").fetchall()
    return {row["uid"]: row["question_id"] for row in rows}


def _parse_sub_score(value):
    try:
        score = int(value)
    except (TypeError, ValueError):
        raise ValueError("主观分必须是 0-10 的整数")
    if not 0 <= score <= 10:
        raise ValueError("主观分必须在 0-10 之间")
    return score


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "correct", "right", "对"}:
            return True
        if normalized in {"0", "false", "no", "n", "incorrect", "wrong", "错"}:
            return False
    raise ValueError("对错字段必须是布尔值")


def _parse_source(value):
    value = str(value or "").strip()
    if value in {"due", "proficiency", "instant", "manual", "legacy_unknown"}:
        return value
    return ""


def _session_feedback_complete(vault, session_id, history):
    session = get_session(vault, session_id)
    if not session:
        return False
    required = {
        item.get("UID")
        for item in session.get("items", [])
        if item.get("UID") and not item.get("_missing")
    }
    if not required:
        return False
    completed = {
        log.get("UID")
        for log in history
        if log.get("Session_ID") == session_id and log.get("UID")
    }
    return required <= completed


def _writeback_md(vault, row, sub_score, is_correct, note, update):
    file_path = os.path.join(vault, row["File_Path"])
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()

    today = datetime.date.today().isoformat()
    correctness = "对" if is_correct else "错"
    note_part = f", 备注:{note}" if note else ""
    new_line = f"{today} 主观:{sub_score}, {correctness}{note_part}"

    if "# 历史" in content:
        content = content.rstrip() + "\n" + new_line + "\n"
    else:
        content = content.rstrip() + "\n\n# 历史\n" + new_line + "\n"

    content = _update_frontmatter_tags(content, update, is_correct)

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)


def _update_frontmatter_tags(content, update, is_correct):
    match = re.match(r"^(---\s*\n)(.*?)(\n---)", content, re.DOTALL)
    if not match:
        return content

    frontmatter = match.group(2)
    body = content[match.end(3):]
    lines = frontmatter.splitlines()

    tags_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == "tags:":
            tags_idx = idx
            break

    if tags_idx is None:
        return content

    tag_indent = "  "
    tag_start = tags_idx + 1
    tag_end = tag_start
    for idx in range(tag_start, len(lines)):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            tag_end = idx + 1
            continue
        if re.match(r"^\s*-\s+", line):
            tag_end = idx + 1
            continue
        break

    tags = []
    for line in lines[tag_start:tag_end]:
        stripped = line.strip()
        if stripped.startswith("- "):
            tags.append(stripped[2:].strip())

    tags = _normalize_tags(tags, update, is_correct)
    tag_lines = [f"{tag_indent}- {tag}" for tag in tags]
    new_lines = lines[:tag_start] + tag_lines + lines[tag_end:]
    new_frontmatter = "\n".join(new_lines)
    return f"{match.group(1)}{new_frontmatter}{match.group(3)}{body}"


def _normalize_tags(tags, update, is_correct):
    normalized = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            normalized.append(tag)
            seen.add(tag)

    if update["tag_action"] == "kill":
        normalized = [
            STATUS_KILLED if tag == STATUS_ATTACKING else tag for tag in normalized
        ]
        if STATUS_KILLED not in normalized:
            normalized.insert(0, STATUS_KILLED)
        normalized = [tag for tag in normalized if tag != STATUS_ATTACKING]
    elif not is_correct and STATUS_KILLED in normalized:
        normalized = [
            STATUS_ATTACKING if tag == STATUS_KILLED else tag for tag in normalized
        ]

    if update["tag_action"] == "trap" and TRAP_TAG not in normalized:
        insert_at = 1 if normalized else 0
        normalized.insert(insert_at, TRAP_TAG)

    return normalized
