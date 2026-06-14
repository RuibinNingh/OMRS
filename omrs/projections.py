import copy
import datetime
import json
import os

from .common import (
    HISTORY_HEADERS,
    MASTERY_HEADERS,
    SESSIONS_HEADERS,
    append_csv,
    calc_sm2_interval,
    compute_due_date,
    history_path,
    load_tuning,
    mastery_path,
    save_csv,
    sessions_path,
)
from .ledger import PROJECTOR_VERSION, canonical_json, connect, read_commits
from .scheduling import _safe_float, _safe_int, compute_mastery_update


DEFAULT_MASTERY = {
    "mastery": 0.0,
    "ef": 2.5,
    "attempts": 0,
    "high_correct_streak": 0,
    "repetition": 0,
    "interval_days": 0,
    "due_date": "",
    "last_review_at": "",
}


def rebuild_projection(vault: str, export_csv=True):
    commits = read_commits(vault, ascending=True)
    state = _project_state(vault, commits)
    with connect(vault) as db:
        _write_projection_tables(db, state)
    if export_csv:
        export_legacy_csv(vault, state)
    return state


def rebuild_question_projection(vault: str):
    return rebuild_projection(vault)


def rebuild_mastery_projection(vault: str):
    return rebuild_projection(vault)


def rebuild_session_projection(vault: str):
    return rebuild_projection(vault)


def rebuild_question_mastery(vault: str, question_id: str):
    # The current stream can include session retractions and state restores, so a
    # full replay is the correctness-first path. The public function keeps the
    # narrower contract for callers and can be optimized later.
    state = rebuild_projection(vault)
    return state["mastery"].get(question_id)


def _empty_state():
    return {
        "questions": {},
        "uid_to_question_id": {},
        "mastery": {},
        "mastery_baseline": {},
        "question_tag_baseline": {},
        "sessions": {},
        "history": [],
        "legacy_history": [],
        "review_commits": [],
        "retracted_sessions": set(),
        "retracted_reviews": set(),
        "restored_reviews": set(),
        "review_replacements": {},
        "last_seq": 0,
    }


def _project_state(vault: str, commits, target_seq=None):
    state = _empty_state()
    snapshots = {}
    for commit in commits:
        seq = int(commit["seq"])
        if target_seq is not None and seq > target_seq:
            break
        if commit["commit_type"] == "state.restore":
            restore_to = _safe_int(commit["payload"].get("target_seq"), 0)
            if restore_to <= 0 or restore_to >= seq:
                continue
            base = snapshots.get(restore_to)
            if base is None:
                base = _project_state(vault, commits, restore_to)
            state = copy.deepcopy(base)
        else:
            apply_commit(vault, state, commit)
        state["last_seq"] = seq
        if seq % 100 == 0 or commit["commit_type"] == "state.restore":
            snapshots[seq] = copy.deepcopy(state)
    return state


def apply_commit(vault: str, state: dict, commit: dict):
    payload = commit["payload"] or {}
    ctype = commit["commit_type"]
    seq = int(commit["seq"])
    if ctype == "legacy.bootstrap":
        _apply_legacy_bootstrap(state, payload, seq)
    elif ctype in {"question.create", "question.create_external"}:
        question = payload.get("question") or payload
        _upsert_question(state, question, seq)
    elif ctype in {"question.move", "question.move_external"}:
        question_id = payload.get("question_id")
        question = state["questions"].get(question_id)
        if question:
            state["uid_to_question_id"].pop(question.get("uid"), None)
            question["uid"] = payload.get("to_uid", question.get("uid", ""))
            question["file_path"] = payload.get("to_path", question.get("file_path", ""))
            question["category"] = payload.get("to_category", question.get("category", ""))
            if payload.get("after"):
                question.update(_normalize_question_fields(payload["after"], question))
            question["archived"] = False
            question["updated_seq"] = seq
            state["uid_to_question_id"][question["uid"]] = question_id
            _remember_question_tag_baseline(state, question_id)
    elif ctype in {"question.metadata_update", "question.metadata_update_external"}:
        question_id = payload.get("question_id")
        question = state["questions"].get(question_id)
        if question:
            after = payload.get("after", {})
            question.update(_normalize_question_fields(after, question))
            question["updated_seq"] = seq
            state["uid_to_question_id"][question["uid"]] = question_id
            _remember_question_tag_baseline(state, question_id)
    elif ctype in {"question.archive", "question.archive_external"}:
        question = state["questions"].get(payload.get("question_id"))
        if question:
            question["archived"] = True
            question["updated_seq"] = seq
    elif ctype == "question.restore":
        question = state["questions"].get(payload.get("question_id"))
        if question:
            question["archived"] = False
            question["updated_seq"] = seq
    elif ctype == "session.create":
        session = payload.get("session") or payload
        sid = session.get("session_id")
        if sid:
            state["sessions"][sid] = {
                "Session_ID": sid,
                "Created_At": session.get("created_at", commit["created_at"]),
                "Subject_Filter": session.get("subject_filter", ""),
                "Count": str(session.get("count", len(session.get("items", [])))),
                "UIDs": canonical_json(session.get("items", session.get("uids", []))),
                "Status": session.get("status", "active"),
                "Completed_At": session.get("completed_at", ""),
                "_updated_seq": seq,
                "_retracted": False,
            }
    elif ctype == "session.complete":
        session = state["sessions"].get(payload.get("session_id"))
        if session:
            session["Status"] = "completed"
            session["Completed_At"] = payload.get("completed_at", commit["created_at"])
            session["_updated_seq"] = seq
    elif ctype == "session.retract":
        sid = payload.get("session_id")
        state["retracted_sessions"].add(sid)
        session = state["sessions"].get(sid)
        if session:
            session["_retracted"] = True
            session["Status"] = "retracted"
            session["_updated_seq"] = seq
        _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "session.restore":
        sid = payload.get("session_id")
        state["retracted_sessions"].discard(sid)
        session = state["sessions"].get(sid)
        if session:
            session["_retracted"] = False
            session["Status"] = "active"
            session["_updated_seq"] = seq
        _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "review.batch_submit":
        _apply_review_batch(vault, state, commit)
    elif ctype == "review.retract":
        key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
        state["retracted_reviews"].add(key)
        state["restored_reviews"].discard(key)
        _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "review.restore":
        key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
        state["restored_reviews"].add(key)
        state["retracted_reviews"].discard(key)
        _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "review.replace":
        key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
        state["review_replacements"][key] = payload.get("replacement", {})
        _recompute_mastery_from_history(vault, state, seq)


def _apply_legacy_bootstrap(state, payload, seq):
    for question in payload.get("questions", []):
        _upsert_question(state, question, seq)
    for row in payload.get("mastery_rows", []):
        question_id = row.get("question_id") or state["uid_to_question_id"].get(row.get("UID"))
        if not question_id:
            continue
        state["mastery"][question_id] = {
            "mastery": _safe_float(row.get("Mastery"), 0.0),
            "ef": _safe_float(row.get("EF"), 2.5),
            "attempts": _safe_int(row.get("Attempts"), 0),
            "high_correct_streak": _safe_int(row.get("High_Correct_Streak"), 0),
            "repetition": _safe_int(row.get("Repetition"), 0),
            "interval_days": _safe_int(row.get("Interval"), 0),
            "due_date": row.get("Due_Date", ""),
            "last_review_at": row.get("Last_Review", ""),
            "updated_seq": seq,
        }
        state["mastery_baseline"][question_id] = dict(state["mastery"][question_id])
    for question_id in state["questions"]:
        state["mastery"].setdefault(question_id, {**DEFAULT_MASTERY, "updated_seq": seq})
        state["mastery_baseline"].setdefault(question_id, dict(state["mastery"][question_id]))
    for session in payload.get("session_rows", []):
        sid = session.get("Session_ID")
        if sid:
            session = dict(session)
            session["_updated_seq"] = seq
            session["_retracted"] = False
            state["sessions"][sid] = session
    for row in payload.get("history_rows", []):
        uid = row.get("UID", "")
        qid = row.get("question_id") or state["uid_to_question_id"].get(uid)
        legacy_row = {
            **row,
            "_legacy": True,
            "_question_id": qid,
            "_commit_id": "legacy.bootstrap",
            "_review_index": len(state["history"]),
        }
        state["legacy_history"].append(dict(legacy_row))
        state["history"].append(legacy_row)


def _upsert_question(state, question, seq):
    question = _normalize_question_fields(question)
    question_id = question.get("question_id")
    if not question_id:
        return
    old = state["questions"].get(question_id, {})
    merged = {**old, **question, "updated_seq": seq, "archived": bool(question.get("archived", False))}
    state["questions"][question_id] = merged
    if merged.get("uid"):
        state["uid_to_question_id"][merged["uid"]] = question_id
    state["mastery"].setdefault(question_id, {**DEFAULT_MASTERY, "updated_seq": seq})
    state["mastery_baseline"].setdefault(question_id, dict(state["mastery"][question_id]))
    _remember_question_tag_baseline(state, question_id)


def _remember_question_tag_baseline(state, question_id):
    question = state["questions"].get(question_id)
    if question:
        state["question_tag_baseline"][question_id] = question.get("current_tag", "#状态/待攻克")


def _normalize_question_fields(question, fallback=None):
    fallback = fallback or {}
    metadata = question.get("metadata") or {}
    knowledge = question.get("knowledge_tags")
    if knowledge is None:
        knowledge = question.get("knowledge_points", [])
    if isinstance(knowledge, str):
        knowledge = [tag for tag in knowledge.split("|") if tag]
    return {
        "question_id": question.get("question_id") or question.get("_omrs_id") or fallback.get("question_id", ""),
        "uid": question.get("uid") or question.get("UID") or fallback.get("uid", ""),
        "file_path": question.get("file_path") or question.get("File_Path") or fallback.get("file_path", ""),
        "subject": question.get("subject") or question.get("Subject") or metadata.get("科目") or fallback.get("subject", ""),
        "category": question.get("category") or question.get("Category") or metadata.get("分类") or fallback.get("category", ""),
        "difficulty": _safe_int(question.get("difficulty") or question.get("Difficulty") or metadata.get("难度"), 5),
        "current_tag": question.get("current_tag") or question.get("Current_Tag") or fallback.get("current_tag", "#状态/待攻克"),
        "knowledge_tags": list(knowledge or fallback.get("knowledge_tags", [])),
        "metadata": metadata or fallback.get("metadata", {}),
        "metadata_hash": question.get("metadata_hash", fallback.get("metadata_hash", "")),
        "content_hash": question.get("content_hash", fallback.get("content_hash", "")),
        "archived": bool(question.get("archived", fallback.get("archived", False))),
    }


def _apply_review_batch(vault, state, commit, record=True):
    payload = commit["payload"] or {}
    reviews = payload.get("feedbacks") or payload.get("reviews") or []
    session_id = payload.get("session_id", "")
    if record:
        state["review_commits"].append(copy.deepcopy(commit))
    for idx, review in enumerate(reviews):
        effective = _effective_review(state, commit["commit_id"], idx, review)
        if effective is None:
            continue
        qid = effective.get("question_id")
        if not qid:
            qid = state["uid_to_question_id"].get(effective.get("uid_at_that_time") or effective.get("uid", ""))
        effective_session_id = session_id or effective.get("session_id", "")
        if not qid or effective_session_id in state["retracted_sessions"]:
            continue
        _apply_single_review(vault, state, qid, effective, commit["seq"])
        state["history"].append(_history_row(commit, idx, qid, effective, effective_session_id))


def _effective_review(state, commit_id, idx, review):
    key = _review_key(commit_id, idx)
    if key in state["retracted_reviews"] and key not in state["restored_reviews"]:
        return None
    if key in state["review_replacements"]:
        return {**review, **state["review_replacements"][key]}
    return review


def _review_key(commit_id, idx):
    return f"{commit_id}:{_safe_int(idx, 0)}"


def _apply_single_review(vault, state, question_id, review, seq):
    tuning = load_tuning(vault)
    mastery = dict(state["mastery"].get(question_id, DEFAULT_MASTERY))
    is_correct = bool(review.get("is_correct"))
    sub_score = _safe_int(review.get("sub_score"), 0)
    new_attempts = _safe_int(mastery.get("attempts"), 0) + 1
    update = compute_mastery_update(
        mastery.get("mastery", 0.0),
        mastery.get("ef", 2.5),
        sub_score,
        is_correct,
        new_attempts,
        mastery.get("high_correct_streak", 0),
        tuning,
    )
    old_interval = _safe_int(mastery.get("interval_days"), 0)
    old_repetition = _safe_int(mastery.get("repetition"), 0)
    source = review.get("source") or "legacy_unknown"
    if is_correct:
        repetition = old_repetition + 1
        interval = calc_sm2_interval(
            old_interval,
            repetition,
            update["ef"],
            source=source,
            proficiency_factor=tuning["proficiency_factor"],
        )
    else:
        repetition = 0
        interval = 1
    occurred = (review.get("occurred_at") or review.get("recorded_at") or "")[:10]
    if not occurred:
        occurred = datetime.date.today().isoformat()
    state["mastery"][question_id] = {
        "mastery": update["mastery"],
        "ef": update["ef"],
        "attempts": new_attempts,
        "high_correct_streak": _safe_int(update["high_correct_streak"], 0),
        "repetition": repetition,
        "interval_days": interval,
        "due_date": compute_due_date(occurred, interval),
        "last_review_at": occurred,
        "updated_seq": seq,
    }
    question = state["questions"].get(question_id)
    if question:
        if update["tag_action"] == "kill":
            question["current_tag"] = "#状态/已击杀"
        elif not is_correct and "已击杀" in question.get("current_tag", ""):
            question["current_tag"] = "#状态/待攻克"


def _history_row(commit, idx, question_id, review, session_id):
    recorded = review.get("recorded_at") or commit["created_at"]
    try:
        dt = datetime.datetime.fromisoformat(recorded.replace("Z", "+00:00"))
        date_text = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_text = str(recorded)[:16]
    return {
        "Log_ID": f"{commit['commit_id']}-{idx + 1:03d}",
        "UID": review.get("uid_at_that_time") or review.get("uid", ""),
        "Date": date_text,
        "Action": "Feedback",
        "Sub_Score": str(review.get("sub_score", "")),
        "Is_Correct": "1" if review.get("is_correct") else "0",
        "Session_ID": session_id or review.get("session_id", ""),
        "Note": review.get("note", ""),
        "_question_id": question_id,
        "_commit_id": commit["commit_id"],
        "_review_index": idx,
    }


def _recompute_mastery_from_history(vault, state, seq):
    base = {}
    for qid in state["questions"]:
        base[qid] = dict(state.get("mastery_baseline", {}).get(qid, {**DEFAULT_MASTERY, "updated_seq": seq}))
    state["mastery"] = base
    for qid, question in state["questions"].items():
        if qid in state["question_tag_baseline"]:
            question["current_tag"] = state["question_tag_baseline"][qid]
    state["history"] = [dict(row) for row in state.get("legacy_history", [])]
    for commit in state.get("review_commits", []):
        replay = copy.deepcopy(commit)
        replay["seq"] = seq
        _apply_review_batch(vault, state, replay, record=False)


def _write_projection_tables(db, state):
    db.execute("DELETE FROM question_projection")
    db.execute("DELETE FROM question_knowledge_points")
    db.execute("DELETE FROM mastery_projection")
    db.execute("DELETE FROM session_projection")
    for qid, question in state["questions"].items():
        db.execute(
            """
            INSERT OR REPLACE INTO question_projection
            (question_id, uid, file_path, subject, category, difficulty, current_tag,
             metadata_json, metadata_hash, content_hash, archived, updated_seq)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qid,
                question.get("uid", ""),
                question.get("file_path", ""),
                question.get("subject", ""),
                question.get("category", ""),
                _safe_int(question.get("difficulty"), 5),
                question.get("current_tag", ""),
                canonical_json(question.get("metadata", {})),
                question.get("metadata_hash", ""),
                question.get("content_hash", ""),
                1 if question.get("archived") else 0,
                _safe_int(question.get("updated_seq"), 0),
            ),
        )
        for tag in question.get("knowledge_tags", []):
            if tag:
                db.execute(
                    "INSERT OR IGNORE INTO question_knowledge_points(question_id, knowledge_point) VALUES (?, ?)",
                    (qid, tag),
                )
    for qid, mastery in state["mastery"].items():
        db.execute(
            """
            INSERT OR REPLACE INTO mastery_projection
            (question_id, mastery, ef, attempts, high_correct_streak, repetition,
             interval_days, due_date, last_review_at, updated_seq)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qid,
                _safe_float(mastery.get("mastery"), 0.0),
                _safe_float(mastery.get("ef"), 2.5),
                _safe_int(mastery.get("attempts"), 0),
                _safe_int(mastery.get("high_correct_streak"), 0),
                _safe_int(mastery.get("repetition"), 0),
                _safe_int(mastery.get("interval_days"), 0),
                mastery.get("due_date", ""),
                mastery.get("last_review_at", ""),
                _safe_int(mastery.get("updated_seq"), 0),
            ),
        )
    for sid, session in state["sessions"].items():
        db.execute(
            """
            INSERT OR REPLACE INTO session_projection
            (session_id, created_at, subject_filter, count, items_json, status,
             completed_at, retracted, updated_seq)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                session.get("Created_At", ""),
                session.get("Subject_Filter", ""),
                _safe_int(session.get("Count"), 0),
                session.get("UIDs", "[]"),
                session.get("Status", "active"),
                session.get("Completed_At", ""),
                1 if session.get("_retracted") else 0,
                _safe_int(session.get("_updated_seq"), 0),
            ),
        )
    db.commit()


def export_legacy_csv(vault: str, state=None):
    state = state or _project_state(vault, read_commits(vault, ascending=True))
    rows = []
    for qid, question in state["questions"].items():
        if question.get("archived"):
            continue
        mastery = state["mastery"].get(qid, DEFAULT_MASTERY)
        rows.append({
            "UID": question.get("uid", ""),
            "File_Path": question.get("file_path", ""),
            "Subject": question.get("subject", ""),
            "Category": question.get("category", ""),
            "Difficulty": str(question.get("difficulty", 5)),
            "Mastery": str(mastery.get("mastery", 0.0)),
            "EF": str(mastery.get("ef", 2.5)),
            "Attempts": str(mastery.get("attempts", 0)),
            "High_Correct_Streak": str(mastery.get("high_correct_streak", 0)),
            "Last_Review": mastery.get("last_review_at", ""),
            "Interval": str(mastery.get("interval_days", 0)),
            "Due_Date": mastery.get("due_date", ""),
            "Repetition": str(mastery.get("repetition", 0)),
            "Current_Tag": question.get("current_tag", "#状态/待攻克"),
            "Entry_Date": question.get("metadata", {}).get("录入日期", ""),
            "Knowledge_Tags": "|".join(question.get("knowledge_tags", [])),
        })
    rows.sort(key=lambda item: (item["Subject"], item["Category"], item["UID"]))
    save_csv(mastery_path(vault), MASTERY_HEADERS, rows, backup=True)

    history_rows = []
    for row in state["history"]:
        history_rows.append({key: row.get(key, "") for key in HISTORY_HEADERS})
    save_csv(history_path(vault), HISTORY_HEADERS, history_rows, backup=True)

    session_rows = []
    for session in state["sessions"].values():
        if session.get("_retracted"):
            continue
        session_rows.append({key: session.get(key, "") for key in SESSIONS_HEADERS})
    save_csv(sessions_path(vault), SESSIONS_HEADERS, session_rows, backup=True)


def ledger_history(vault: str, before_seq=None, limit=100):
    commits = read_commits(vault, before_seq=before_seq, limit=limit, ascending=False)
    items = []
    for commit in reversed(commits):
        payload = commit["payload"]
        items.append({
            "seq": commit["seq"],
            "commit_id": commit["commit_id"],
            "created_at": commit["created_at"],
            "source": commit["source"],
            "commit_type": commit["commit_type"],
            "message": commit["message"],
            "summary": _commit_summary(commit),
            "payload": payload,
        })
    return items


def ledger_retraction_state(vault: str):
    state = _project_state(vault, read_commits(vault, ascending=True))
    return {
        "retracted_sessions": sorted(sid for sid in state["retracted_sessions"] if sid),
        "retracted_reviews": sorted(state["retracted_reviews"]),
    }


def _commit_summary(commit):
    payload = commit["payload"]
    ctype = commit["commit_type"]
    if ctype == "review.batch_submit":
        return f"提交 {len(payload.get('feedbacks', []))} 条练习反馈"
    if ctype == "legacy.bootstrap":
        return f"迁移旧数据：{len(payload.get('questions', []))} 道题"
    if ctype in {"question.create", "question.create_external"}:
        q = payload.get("question", payload)
        return f"新增题目：{q.get('uid', '')}"
    if ctype in {"question.move", "question.move_external"}:
        return f"迁移题目：{payload.get('from_uid', '')} -> {payload.get('to_uid', '')}"
    if ctype.startswith("review."):
        return commit["message"]
    if ctype.startswith("session."):
        return f"{commit['message']}：{payload.get('session_id', '')}"
    if ctype == "state.restore":
        return f"还原到 seq {payload.get('target_seq')}"
    return commit["message"]
