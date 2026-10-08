"""Ledger 的 SQL 读模型；兼容列名只用于旧调用方，不读取日常 CSV 镜像。"""
import json
import os
import functools

from .ledger import connect


def storage_write(fn):
    """领域写入完整临界区，兼容 HTTP 与直接调用的同一锁顺序。"""
    from .vault_lifecycle import lease
    from .locking import write_lock
    @functools.wraps(fn)
    def wrapped(vault, *args, **kwargs):
        with lease(vault), write_lock():
            return fn(vault, *args, **kwargs)
    return wrapped


class IdentityConflict(RuntimeError):
    """显示 UID 与稳定身份不一致，HTTP 应返回 409。"""
    status = 409
    code = "identity_conflict"


def resolve_question(vault, uid="", question_id="", include_archived=False, db=None):
    if db is None:
        with connect(vault) as own:
            return resolve_question(vault, uid, question_id, include_archived, own)
    if question_id:
        row = db.execute("SELECT * FROM question_projection WHERE question_id=?", (question_id,)).fetchone()
        if row and uid and row["uid"] != uid:
            raise IdentityConflict("题目 UID 已变化，请刷新后重试")
    else:
        row = db.execute("SELECT * FROM question_projection WHERE uid=? AND archived=0", (uid,)).fetchone()
    if row and (include_archived or not row["archived"]):
        return dict(row)
    return None


def _legacy(vault, filename):
    """仅无 Ledger 提交的旧数据／测试夹具可读迁移输入；正式运行不走这里。"""
    from .common import load_csv
    with connect(vault) as db:
        if db.execute("SELECT 1 FROM commits LIMIT 1").fetchone():
            return None
    return load_csv(os.path.join(vault, "错题", ".omrs", filename))


def iter_mastery_rows(db, include_archived=False, question_ids=None):
    identity_filter = " WHERE question_id IN (" + ",".join("?" for _ in question_ids) + ")" if question_ids is not None else ""
    identity_args = tuple(question_ids) if question_ids is not None else ()
    if question_ids is not None and not question_ids:
        return
    knowledge, labels = {}, {}
    for row in db.execute("SELECT question_id,knowledge_point FROM question_knowledge_points" + identity_filter, identity_args):
        knowledge.setdefault(row["question_id"], []).append(row["knowledge_point"])
    for row in db.execute("SELECT question_id,label FROM question_labels" + identity_filter, identity_args):
        labels.setdefault(row["question_id"], []).append(row["label"])
    rows = db.execute("""SELECT q.*,m.mastery,m.ef,m.attempts,m.high_correct_streak,
        m.repetition,m.interval_days,m.due_date,m.last_review_at,m.kill_count
        FROM question_projection q LEFT JOIN mastery_projection m USING(question_id)
        WHERE (? OR q.archived=0)""" + (" AND q.question_id IN (" + ",".join("?" for _ in question_ids) + ")" if question_ids is not None else "") + " ORDER BY q.subject,q.category,q.uid", (int(include_archived), *identity_args))
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        yield {
            "question_id": row["question_id"], "UID": row["uid"], "File_Path": row["file_path"],
            "Subject": row["subject"], "Category": row["category"], "Difficulty": str(row["difficulty"] or 5),
            "Mastery": str(row["mastery"] or 0), "EF": str(row["ef"] if row["ef"] is not None else 2.5),
            "Attempts": str(row["attempts"] or 0), "High_Correct_Streak": str(row["high_correct_streak"] or 0),
            "Repetition": str(row["repetition"] or 0), "Interval": str(row["interval_days"] or 0),
            "Due_Date": row["due_date"] or "", "Last_Review": row["last_review_at"] or "",
            "Kill_Count": str(row["kill_count"] or 0), "Current_Tag": row["current_tag"] or "",
            "Entry_Date": metadata.get("录入日期", ""), "Created_At": row["created_at"] or "",
            "Knowledge_Tags": "|".join(knowledge.get(row["question_id"], [])),
            "Labels": "|".join(labels.get(row["question_id"], [])), "Suspended": str(row["suspended"]),
        }


def mastery_rows(vault, include_archived=False, question_ids=None):
    with connect(vault) as db:
        if db.execute("SELECT 1 FROM commits LIMIT 1").fetchone():
            return list(iter_mastery_rows(db, include_archived, question_ids))
    return _legacy(vault, "mastery_data.csv") or []


def _history_item(row):
    return {"Log_ID": row["log_id"], "Question_ID": row["question_id"] or "", "UID": row["uid"] or "",
            "Date": row["date"] or "", "Action": "Feedback", "Sub_Score": str(row["sub_score"]),
            "Is_Correct": str(row["is_correct"]), "Session_ID": row["session_id"] or "", "Note": row["note"] or "",
            "recorded_at": row["recorded_at"] or "", "review_date": row["review_date"] or ""}


def iter_history_rows(db):
    for row in db.execute("SELECT * FROM history_projection ORDER BY rowid"):
        yield _history_item(row)


def _session_item(row):
    return {"Session_ID": row["session_id"], "Created_At": row["created_at"], "Subject_Filter": row["subject_filter"],
            "Count": str(row["count"]), "UIDs": row["items_json"], "Status": row["status"],
            "Completed_At": row["completed_at"] or ""}


def iter_session_rows(db):
    for row in db.execute("SELECT * FROM session_projection WHERE retracted=0 ORDER BY created_at DESC"):
        yield _session_item(row)


def history_rows(vault, question_id=None, session_id=None, limit=None):
    clauses, args = [], []
    if question_id is not None:
        clauses.append("question_id=?")
        args.append(question_id)
    if session_id is not None:
        clauses.append("session_id=?")
        args.append(session_id)
    sql = "SELECT * FROM history_projection" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += " ORDER BY rowid" if limit is None else " ORDER BY rowid DESC LIMIT ?"
    if limit is not None:
        args.append(limit)
    with connect(vault) as db:
        raw = db.execute(sql, args).fetchall()
        exists = db.execute("SELECT 1 FROM commits LIMIT 1").fetchone()
    if not exists:
        rows = _legacy(vault, "history_log.csv") or []
        if question_id is not None:
            rows = [r for r in rows if r.get("Question_ID") == question_id]
        if session_id is not None:
            rows = [r for r in rows if r.get("Session_ID") == session_id]
        return rows[-limit:] if limit else rows
    rows = [_history_item(r) for r in raw]
    return list(reversed(rows)) if limit is not None else rows


def session_rows(vault):
    with connect(vault) as db:
        raw = db.execute("SELECT * FROM session_projection WHERE retracted=0 ORDER BY created_at DESC").fetchall()
        exists = db.execute("SELECT 1 FROM commits LIMIT 1").fetchone()
    if not exists:
        return _legacy(vault, "sessions.csv") or []
    return [_session_item(r) for r in raw]


def session_row(vault, session_id):
    with connect(vault) as db:
        row = db.execute("SELECT * FROM session_projection WHERE session_id=? AND retracted=0", (session_id,)).fetchone()
        if db.execute("SELECT 1 FROM commits LIMIT 1").fetchone():
            return _session_item(row) if row else None
    return next((r for r in (_legacy(vault, "sessions.csv") or []) if r["Session_ID"] == session_id), None)


def storage_read(fn):
    """标签及题面聚合读与整批替换共用一致性保护，不在读取时恢复。"""
    @functools.wraps(fn)
    def wrapped(vault, *args, **kwargs):
        from .vault_lifecycle import lease
        from .locking import label_read_lock
        from .label_plan_journal import assert_readable
        with lease(vault), label_read_lock():
            assert_readable(vault)
            return fn(vault, *args, **kwargs)
    return wrapped
