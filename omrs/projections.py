import copy
import datetime
import json
import os

from .common import HISTORY_HEADERS, MASTERY_HEADERS, SESSIONS_HEADERS, business_time, history_path, is_suspended_row, load_tuning, mastery_path, save_csv, sessions_path
from .ledger import canonical_json, connect
from .scheduling import _safe_float, _safe_int, transition_review


DEFAULT_MASTERY = {
    "mastery": 0.0,
    "ef": 2.5,
    "attempts": 0,
    "high_correct_streak": 0,
    "repetition": 0,
    "interval_days": 0,
    "due_date": "",
    "last_review_at": "",
    # 击杀次数：复燃周期按次数分级（见 scheduling.revive_dormant_days）
    "kill_count": 0,
}


def rebuild_projection(vault: str, export_csv=False, force=False):
    from .projection_runtime import project
    state = project(vault, force=force)
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
    state["_tuning"] = load_tuning(vault)
    for commit in commits:
        seq = int(commit["seq"])
        if target_seq is not None and seq > target_seq:
            break
        if commit["commit_type"] == "state.restore":
            restore_to = _safe_int(commit["payload"].get("target_seq"), 0)
            if restore_to <= 0 or restore_to >= seq:
                continue
            base = _project_state(vault, commits, restore_to)
            state = copy.deepcopy(base)
        else:
            apply_commit(vault, state, commit)
        state["last_seq"] = seq
    return state


def _metadata_update(question, after, payload=None):
    """未改变的 Markdown 状态字段不能覆盖反馈产生的投影状态。"""
    from .common import extract_tag
    normalized = _normalize_question_fields(after, question)
    previous_meta, next_meta = question.get("metadata") or {}, after.get("metadata") or {}
    fields = (payload or {}).get("changed_fields")
    if fields is not None:
        tag_changed = "current_tag" in fields or "tags" in fields
    elif previous_meta and next_meta:
        tag_changed = extract_tag(previous_meta) != extract_tag(next_meta)
    else:
        tag_changed = "current_tag" in after and after["current_tag"] != (payload or {}).get("before", {}).get("current_tag", question.get("current_tag"))
    if not tag_changed:
        normalized["current_tag"] = question.get("current_tag", "#状态/待攻克")
    return normalized


def _bind_session_items(state, raw, session_id, legacy=False):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = []
    result = []
    for index, item in enumerate(raw or []):
        item = {"uid": item} if isinstance(item, str) else dict(item)
        uid = item.get("uid_at_creation") or item.get("uid", "")
        qid = item.get("question_id") or ""
        if not qid and not legacy:
            candidates = [q["question_id"] for q in state["questions"].values() if q.get("uid") == uid and not q.get("archived")]
            qid = candidates[0] if len(candidates) == 1 else ""
        result.append({"entry_id": item.get("entry_id") or f"{session_id}:{index}",
                       "question_id": qid, "uid_at_creation": uid, "uid": uid,
                       "source": item.get("source", "due")})
    return result


def apply_commit(vault: str, state: dict, commit: dict):
    payload = commit["payload"] or {}
    ctype = commit["commit_type"]
    seq = int(commit["seq"])
    if state.get("_corrections_precomputed") and ctype in {"review.retract", "review.restore", "review.replace"}:
        return
    if ctype == "legacy.bootstrap":
        _apply_legacy_bootstrap(state, payload, seq)
    elif ctype in {"question.create", "question.create_external"}:
        question = dict(payload.get("question") or payload)
        # 创建时间以 Ledger 提交时间为准。外部扫描题的语义是首次纳入 Ledger，
        # legacy.bootstrap 不走这里，旧题因此保留空值并由上层回退到录入日期。
        existing = state["questions"].get(question.get("question_id"))
        question["created_at"] = (existing or {}).get("created_at") or commit.get("created_at") or ""
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
                question.update(_metadata_update(question, payload["after"], payload))
            question["archived"] = False
            question["updated_seq"] = seq
            state["uid_to_question_id"][question["uid"]] = question_id
            _remember_question_tag_baseline(state, question_id)
    elif ctype in {"question.metadata_update", "question.metadata_update_external"}:
        question_id = payload.get("question_id")
        question = state["questions"].get(question_id)
        if question:
            after = payload.get("after", {})
            question.update(_metadata_update(question, after, payload))
            question["updated_seq"] = seq
            state["uid_to_question_id"][question["uid"]] = question_id
            _remember_question_tag_baseline(state, question_id)
    elif ctype == "question.content_update":
        question = state["questions"].get(payload.get("question_id"))
        if question and payload.get("after_hash"):
            question["content_hash"] = payload["after_hash"]
            question["updated_seq"] = seq
    elif ctype == "question.content_snapshot":
        pass  # 只为把正文存进 blobs；投影里的 content_hash 已由之前的 commit 决定
    elif ctype in {"question.archive", "question.archive_external"}:
        question = state["questions"].get(payload.get("question_id"))
        if question:
            question["archived"] = True
            if state["uid_to_question_id"].get(question.get("uid")) == question.get("question_id"):
                state["uid_to_question_id"].pop(question.get("uid"), None)
            question["updated_seq"] = seq
    elif ctype == "question.restore":
        question = state["questions"].get(payload.get("question_id"))
        if question:
            question["archived"] = False
            state["uid_to_question_id"][question["uid"]] = question["question_id"]
            question["updated_seq"] = seq
    elif ctype == "question.suspend":
        question = state["questions"].get(payload.get("question_id"))
        if question and not question.get("archived"):
            question["suspended"] = True
            question["updated_seq"] = seq
    elif ctype == "question.resume":
        question = state["questions"].get(payload.get("question_id"))
        if question and not question.get("archived"):
            question["suspended"] = False
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
                "UIDs": canonical_json(_bind_session_items(state, session.get("entries", session.get("items", session.get("uids", []))), sid)),
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
    elif ctype == "session.items_bind":
        session = state["sessions"].get(payload.get("session_id"))
        if session:
            items = json.loads(session["UIDs"])
            for item in items:
                if item.get("entry_id") == payload.get("entry_id"):
                    item["question_id"] = payload["question_id"]
            session["UIDs"] = canonical_json(items)
            session["_updated_seq"] = seq
    elif ctype == "session.retract":
        sid = payload.get("session_id")
        if not state.get("_corrections_precomputed"):
            state["retracted_sessions"].add(sid)
        session = state["sessions"].get(sid)
        if session:
            session["_retracted"] = True
            session["Status"] = "retracted"
            session["_updated_seq"] = seq
        if not state.get("_corrections_precomputed"):
            _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "session.restore":
        sid = payload.get("session_id")
        if not state.get("_corrections_precomputed"):
            state["retracted_sessions"].discard(sid)
        session = state["sessions"].get(sid)
        if session:
            session["_retracted"] = False
            session["Status"] = "active"
            session["_updated_seq"] = seq
        if not state.get("_corrections_precomputed"):
            _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "review.batch_submit":
        _apply_review_batch(vault, state, commit)
    elif ctype == "review.retract":
        key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
        state["retracted_reviews"].add(key)
        state["restored_reviews"].discard(key)
        if not state.get("_corrections_precomputed"):
            _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "review.restore":
        key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
        state["restored_reviews"].add(key)
        state["retracted_reviews"].discard(key)
        if not state.get("_corrections_precomputed"):
            _recompute_mastery_from_history(vault, state, seq)
    elif ctype == "review.replace":
        key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
        state["review_replacements"][key] = payload.get("replacement", {})
        if not state.get("_corrections_precomputed"):
            _recompute_mastery_from_history(vault, state, seq)


def _apply_legacy_bootstrap(state, payload, seq):
    for question in payload.get("questions", []):
        question = dict(question)
        # 旧迁移只知道录入日期，没有可核验的 Ledger 精确创建时间。
        question.pop("created_at", None)
        _upsert_question(state, question, seq)
    for row in payload.get("mastery_rows", []):
        question_id = row.get("question_id") or state["uid_to_question_id"].get(row.get("UID"))
        if not question_id:
            continue
        question = state["questions"].get(question_id)
        if question and is_suspended_row(row):
            question["suspended"] = True
        state["mastery"][question_id] = {
            "mastery": _safe_float(row.get("Mastery"), 0.0),
            "ef": _safe_float(row.get("EF"), 2.5),
            "attempts": _safe_int(row.get("Attempts"), 0),
            "high_correct_streak": _safe_int(row.get("High_Correct_Streak"), 0),
            "repetition": _safe_int(row.get("Repetition"), 0),
            "interval_days": _safe_int(row.get("Interval"), 0),
            "due_date": row.get("Due_Date", ""),
            "last_review_at": row.get("Last_Review", ""),
            # 老 CSV 无 Kill_Count 列，缺失按 0 处理
            "kill_count": _safe_int(row.get("Kill_Count"), 0),
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
            session["UIDs"] = canonical_json(_bind_session_items(state, session.get("UIDs", "[]"), sid, legacy=True))
            session["_updated_seq"] = seq
            session["_retracted"] = False
            state["sessions"][sid] = session
    for row in payload.get("history_rows", []):
        uid = row.get("UID", "")
        qid = row.get("question_id") or state["uid_to_question_id"].get(uid)
        legacy_row = {
            **row,
            "Question_ID": row.get("Question_ID") or qid or "",
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
    merged = {
        **old,
        **question,
        "updated_seq": seq,
        "archived": bool(question.get("archived", old.get("archived", False))),
        "suspended": bool(question.get("suspended", old.get("suspended", False))),
    }
    state["questions"][question_id] = merged
    if merged.get("uid") and not merged.get("archived"):
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
        knowledge = question.get("knowledge_points")
    if knowledge is None:
        knowledge = fallback.get("knowledge_tags", [])
    if isinstance(knowledge, str):
        knowledge = [tag for tag in knowledge.split("|") if tag]
    labels = question.get("labels")
    if labels is None:
        labels = question.get("Labels")
    if labels is None:
        labels = metadata.get("标记")
    if labels is None:
        labels = fallback.get("labels", [])
    if isinstance(labels, str):
        labels = [label for label in labels.split("|") if label]
    return {
        "question_id": question.get("question_id") or question.get("_omrs_id") or fallback.get("question_id", ""),
        "uid": question.get("uid") or question.get("UID") or fallback.get("uid", ""),
        "file_path": question.get("file_path") or question.get("File_Path") or fallback.get("file_path", ""),
        "subject": question.get("subject") or question.get("Subject") or metadata.get("科目") or fallback.get("subject", ""),
        "category": question.get("category") or question.get("Category") or metadata.get("分类") or fallback.get("category", ""),
        "difficulty": _safe_int(question.get("difficulty") or question.get("Difficulty") or metadata.get("难度"), 5),
        "current_tag": question.get("current_tag") or question.get("Current_Tag") or fallback.get("current_tag", "#状态/待攻克"),
        "knowledge_tags": list(knowledge or []),
        "labels": list(labels or []),
        "metadata": metadata or fallback.get("metadata", {}),
        "metadata_hash": question.get("metadata_hash", fallback.get("metadata_hash", "")),
        "content_hash": question.get("content_hash", fallback.get("content_hash", "")),
        "created_at": question.get("created_at") or fallback.get("created_at", ""),
        "archived": bool(question.get("archived", fallback.get("archived", False))),
        "suspended": bool(question.get("suspended", fallback.get("suspended", False))),
    }


def _apply_review_batch(vault, state, commit, record=True):
    payload = commit["payload"] or {}
    reviews = payload.get("feedbacks") or payload.get("reviews") or []
    session_id = payload.get("session_id", "")
    if record and not state.get("_corrections_precomputed"):
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
        history_row = _history_row(commit, idx, qid, effective, effective_session_id)
        # 旧提交没有显式业务日期时，使用自身时间戳，不能用重放当天。
        effective = {**effective, "review_date": history_row["review_date"]}
        display = _apply_single_review(vault, state, qid, effective, commit["seq"])
        state.setdefault("_review_results", []).append({"question_id": qid, **display})
        state["history"].append(history_row)


def _effective_review(state, commit_id, idx, review):
    key = _review_key(commit_id, idx)
    replacements = state["review_replacements"]
    if hasattr(replacements, "effective"):
        return replacements.effective(key, review)
    if key in state["retracted_reviews"] and key not in state["restored_reviews"]:
        return None
    if key in state["review_replacements"]:
        return {**review, **state["review_replacements"][key]}
    return review


def _review_key(commit_id, idx):
    return f"{commit_id}:{_safe_int(idx, 0)}"


def _apply_single_review(vault, state, question_id, review, seq):
    tuning = state.get("_tuning") or load_tuning(vault)
    question = state["questions"].get(question_id, {})
    mastery = state["mastery"].get(question_id, DEFAULT_MASTERY)
    updated, tag, display = transition_review(question, mastery, review, tuning)
    state["mastery"][question_id] = {**updated, "updated_seq": seq}
    if question:
        question["current_tag"] = tag
    return display


def _history_row(commit, idx, question_id, review, session_id):
    recorded = review.get("recorded_at") or commit["created_at"]
    try:
        dt = datetime.datetime.fromisoformat(recorded.replace("Z", "+00:00"))
        original_time = False
        if dt.tzinfo is not None:
            from zoneinfo import ZoneInfoNotFoundError
            try:
                dt = business_time(dt, review.get("review_timezone") or "Asia/Shanghai")
            except ZoneInfoNotFoundError:
                # 旧历史／其它时区缺规则时保留原时间，不伪造夏令时转换。
                original_time = True
        business_day = dt.date().isoformat() if original_time else str(review.get("review_date") or review.get("occurred_at") or dt.date().isoformat())[:10]
        date_text = business_day + (dt.strftime(" %H:%M") if len(str(recorded).strip()) > 10 else "")
    except Exception:
        date_text = str(recorded)[:16]
    return {
        "Log_ID": f"{commit['commit_id']}-{idx + 1:03d}",
        "UID": review.get("uid_at_that_time") or review.get("uid", ""),
        "Date": date_text,
        "recorded_at": recorded,
        "review_date": str(review.get("review_date") or review.get("occurred_at") or date_text)[:10],
        "Action": "Feedback",
        "Sub_Score": str(review.get("sub_score", "")),
        "Is_Correct": "1" if review.get("is_correct") else "0",
        "Session_ID": session_id or review.get("session_id", ""),
        "Note": review.get("note", ""),
        "Question_ID": question_id,
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
    db.execute("DELETE FROM question_labels")
    db.execute("DELETE FROM mastery_projection")
    db.execute("DELETE FROM session_projection")
    for qid, question in state["questions"].items():
        db.execute(
            """
            INSERT INTO question_projection
            (question_id, uid, file_path, subject, category, difficulty, current_tag,
             metadata_json, metadata_hash, content_hash, created_at, archived, suspended, updated_seq)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                question.get("created_at") or None,
                1 if question.get("archived") else 0,
                1 if question.get("suspended") else 0,
                _safe_int(question.get("updated_seq"), 0),
            ),
        )
        for tag in question.get("knowledge_tags", []):
            if tag:
                db.execute(
                    "INSERT OR IGNORE INTO question_knowledge_points(question_id, knowledge_point) VALUES (?, ?)",
                    (qid, tag),
                )
        for label in question.get("labels", []):
            if label:
                db.execute(
                    "INSERT OR IGNORE INTO question_labels(question_id, label) VALUES (?, ?)",
                    (qid, label),
                )
    for qid, mastery in state["mastery"].items():
        db.execute(
            """
            INSERT OR REPLACE INTO mastery_projection
            (question_id, mastery, ef, attempts, high_correct_streak, repetition,
             interval_days, due_date, last_review_at, kill_count, updated_seq)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                _safe_int(mastery.get("kill_count"), 0),
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
def export_legacy_csv(vault: str, state=None):
    """显式导出当前 SQL 读模型；历史逐行写出，不累积反馈载荷。"""
    from .data_repository import iter_mastery_rows, iter_history_rows, iter_session_rows
    from .vault_lifecycle import lease
    from .locking import write_lock
    with lease(vault), write_lock():
        if state is None:
            rebuild_projection(vault)
        with connect(vault) as db:
            save_csv(mastery_path(vault), MASTERY_HEADERS,
                     ({key: row.get(key, "") for key in MASTERY_HEADERS} for row in iter_mastery_rows(db)), backup=True)
            save_csv(history_path(vault), HISTORY_HEADERS,
                     ({key: row.get(key, "") for key in HISTORY_HEADERS} for row in iter_history_rows(db)), backup=True)
            save_csv(sessions_path(vault), SESSIONS_HEADERS, iter_session_rows(db), backup=True)


def ledger_history(vault: str, before_seq=None, limit=100, summary_only=False, q="", since="", until=""):
    from .ledger import _row_to_commit
    clauses, args = [], []
    if before_seq is not None:
        clauses.append("seq<?")
        args.append(before_seq)
    for operator, bound in ((">=", since), ("<", until)):
        if bound:
            clauses.append(f"julianday(created_at){operator}julianday(?)")
            args.append(bound)
    sql = "SELECT * FROM commits" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY seq DESC"
    commits = []
    with connect(vault) as db:
        for raw in db.execute(sql, args):
            commit = _row_to_commit(raw)
            searchable = json.dumps(_history_payload_summary(commit["payload"], commit["commit_type"]), ensure_ascii=False)
            if q and q.casefold() not in (commit["message"] + _commit_summary(commit) + searchable).casefold():
                continue
            commits.append(commit)
            if limit is not None and len(commits) >= limit:
                break
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
            "payload": _history_payload_summary(payload, commit["commit_type"]) if summary_only else payload,
            **({"learning": _history_learning_summary(commit)} if summary_only else {}),
        })
    return items


def _history_payload_summary(payload, ctype):
    """列表只带修正状态及操作所需的少量字段；正文和完整载荷由详情接口读取。"""
    if ctype == "review.batch_submit":
        return {"session_id": payload.get("session_id", ""), "feedbacks": [
            {key: fb[key] for key in ("uid_at_that_time", "uid", "question_id", "session_id",
                                       "is_correct", "sub_score", "subject", "question_summary") if key in fb}
            for fb in (payload.get("feedbacks") or payload.get("reviews") or [])]}
    if ctype == "legacy.bootstrap":
        return {"question_count": len(payload.get("questions", []))}
    keys = ("session_id", "target_commit_id", "target_review_index", "target_seq", "reason",
            "uid_at_that_time", "from_uid", "to_uid", "from_category", "to_category",
            "change_summary")
    result = {key: payload[key] for key in keys if key in payload}
    if ctype in {"question.create", "question.create_external"}:
        question = payload.get("question") or payload
        result["question"] = {key: question[key] for key in ("uid", "subject", "category") if key in question}
        if payload.get("_draft", {}).get("draft_id"):
            result["source_draft_id"] = payload["_draft"]["draft_id"]
    if ctype == "session.create":
        session = payload.get("session") or payload
        result["session"] = {key: session[key] for key in ("session_id", "count") if key in session}
    return result


def _history_learning_summary(commit):
    payload = commit["payload"] or {}
    ctype = commit["commit_type"]
    if ctype == "review.batch_submit":
        feedbacks = payload.get("feedbacks") or payload.get("reviews") or []
        subjects = {}
        for fb in feedbacks:
            subject = fb.get("subject")
            if subject:
                subjects[subject] = subjects.get(subject, 0) + 1
        snippets = [fb.get("question_summary", "") for fb in feedbacks if fb.get("question_summary")]
        return {"subjects": subjects, "questions": snippets[:3], "count": len(feedbacks)}
    if ctype in {"question.move", "question.move_external"}:
        before = payload.get("before") or {}
        after = payload.get("after") or {}
        return {"from_category": payload.get("from_category") or before.get("category"),
                "to_category": payload.get("to_category") or after.get("category")}
    if ctype in {"question.metadata_update", "question.metadata_update_external"}:
        before, after = payload.get("before") or {}, payload.get("after") or {}
        fields = {key: [before.get(key), after.get(key)] for key in
                  ("subject", "category", "difficulty", "knowledge_tags", "labels")
                  if key in before and key in after and before[key] != after[key]}
        return {"fields": fields}
    if ctype == "question.content_update":
        return {"change": payload.get("change_summary") or
                {"available": False, "message": "无可用历史摘要"}}
    return {}


def ledger_history_detail(vault: str, seq: int):
    """按需读取单个提交；只有正文变更才额外读取前后两个 blob。"""
    from .ledger import get_commit, get_blob
    commit = get_commit(vault, seq)
    if commit is None:
        return None
    detail = {"seq": commit["seq"], "commit_id": commit["commit_id"],
              "commit_type": commit["commit_type"], "source": commit["source"],
              "payload": commit["payload"], "created_at": commit["created_at"],
              "message": commit["message"], "learning": _history_learning_summary(commit)}
    payload = commit["payload"] or {}
    if commit["commit_type"] in {"question.content_update", "question.metadata_update",
                                  "question.metadata_update_external"}:
        before = get_blob(vault, payload["before_hash"]) if payload.get("before_hash") else None
        after = get_blob(vault, payload["after_hash"]) if payload.get("after_hash") else None
        detail["content_change"] = payload.get("change_summary") or _content_change_summary(before, after)
    return detail


def _content_change_summary(before, after):
    if before is None or after is None:
        return {"available": False, "message": "无可用历史摘要"}
    import difflib
    import re
    def sections(content):
        content = re.sub(r"\A---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|\Z)", "", content, count=1)
        result, current = {}, "正文"
        for line in content.splitlines():
            heading = re.match(r"^#{1,4}\s*(题目|答案|错因)(?:\s|$)", line)
            if heading:
                current = heading.group(1)
                result.setdefault(current, [])
            elif not line.startswith("---") and not line.startswith("# "):
                result.setdefault(current, []).append(line.strip())
        return {key: " ".join(value).strip() for key, value in result.items()}
    old, new = sections(before), sections(after)
    changed = []
    for name in ("题目", "答案", "错因", "正文"):
        if old.get(name, "") != new.get(name, ""):
            left, right = old.get(name, ""), new.get(name, "")
            matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
            edits = [part for part in matcher.get_opcodes() if part[0] != "equal"]
            if edits:
                _, a, b, c, d = edits[0]
                changed.append({"section": name, "before": left[max(0, a-18):min(len(left), b+18)][:100],
                                "after": right[max(0, c-18):min(len(right), d+18)][:100]})
    return {"available": bool(changed), "sections": changed[:3],
            **({} if changed else {"message": "无可用历史摘要"})}


def ledger_retraction_state(vault: str):
    state = rebuild_projection(vault)
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
    if ctype in {"question.archive", "question.archive_external"}:
        return f"归档题目：{payload.get('uid_at_that_time', '')}"
    if ctype == "question.content_update":
        return f"修改正文：{payload.get('uid_at_that_time', '')}"
    if ctype == "question.content_snapshot":
        return f"回填正文：{len(payload.get('items', []))} 道题"
    if ctype in {"question.suspend", "question.resume"}:
        action = "停用" if ctype == "question.suspend" else "恢复"
        return f"{action}题目：{payload.get('uid_at_that_time', payload.get('uid', ''))}"
    if ctype.startswith("review."):
        return commit["message"]
    if ctype.startswith("session."):
        return f"{commit['message']}：{payload.get('session_id', '')}"
    if ctype == "state.restore":
        return f"还原到 seq {payload.get('target_seq')}"
    return commit["message"]
