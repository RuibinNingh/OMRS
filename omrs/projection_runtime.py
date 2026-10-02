"""有界 Ledger 重放：普通追加增量落 SQL，修正／恢复使用流式完整重放。"""
import contextlib
import hashlib
import json
import os
from collections import OrderedDict

from .ledger import PROJECTOR_VERSION, canonical_json, connect, _row_to_commit
from .locking import write_lock

_CACHE = OrderedDict()
_FULL_TYPES = {"review.retract", "review.restore", "review.replace", "session.retract", "session.restore", "state.restore", "legacy.bootstrap"}


def lifecycle(vault):
    try:
        from .vault_lifecycle import lease
    except ImportError:
        return contextlib.nullcontext()
    return lease(vault)


def policy_hash(tuning):
    return hashlib.sha256(canonical_json(tuning).encode()).hexdigest()


def invalidate(vault=None):
    if vault is None:
        _CACHE.clear()
    else:
        _CACHE.pop(os.path.realpath(vault), None)


def _intervals(db, head):
    """恢复到目标前缀，再接上恢复后的后缀；区间迭代，不递归复制全状态。"""
    tails, boundary = [], head
    while boundary:
        row = db.execute("SELECT seq,payload_json FROM commits WHERE commit_type='state.restore' AND seq<=? ORDER BY seq DESC LIMIT 1", (boundary,)).fetchone()
        if not row:
            break
        target = int(json.loads(row["payload_json"]).get("target_seq") or 0)
        if not 0 < target < row["seq"]:
            # 非法历史恢复节点按旧语义忽略，继续找前一个有效节点。
            candidates = db.execute("SELECT seq,payload_json FROM commits WHERE commit_type='state.restore' AND seq<? ORDER BY seq DESC", (row["seq"],))
            row = next((r for r in candidates if 0 < int(json.loads(r["payload_json"]).get("target_seq") or 0) < r["seq"]), None)
            if not row:
                break
            target = int(json.loads(row["payload_json"])["target_seq"])
        if row["seq"] < boundary:
            tails.append((row["seq"] + 1, boundary))
        boundary = target
    return ([(1, boundary)] if boundary else []) + list(reversed(tails))


def _commits(db, intervals, corrections_only=False):
    condition = " AND commit_type IN ('review.retract','review.restore','review.replace','session.retract','session.restore')" if corrections_only else ""
    for start, end in intervals:
        for row in db.execute("SELECT * FROM commits WHERE seq>=? AND seq<=?" + condition + " ORDER BY seq", (start, end)):
            yield _row_to_commit(row)


def _precompute(db, commits):
    from .projections import _review_key
    db.execute("DELETE FROM projection_review_corrections")
    db.execute("DELETE FROM projection_session_corrections")
    for commit in commits:
        kind, payload = commit["commit_type"], commit["payload"]
        if kind in ("session.retract", "session.restore"):
            if payload.get("session_id"):
                db.execute("INSERT INTO projection_session_corrections VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET retracted=excluded.retracted",
                           (payload["session_id"], int(kind == "session.retract")))
        else:
            key = _review_key(payload.get("target_commit_id"), payload.get("target_review_index"))
            if kind in ("review.retract", "review.restore"):
                db.execute("INSERT INTO projection_review_corrections(review_key,status) VALUES(?,?) ON CONFLICT(review_key) DO UPDATE SET status=excluded.status",
                           (key, "retracted" if kind == "review.retract" else "restored"))
            elif kind == "review.replace":
                db.execute("INSERT INTO projection_review_corrections(review_key,replacement_json) VALUES(?,?) ON CONFLICT(review_key) DO UPDATE SET replacement_json=excluded.replacement_json",
                           (key, canonical_json(payload.get("replacement", {}))))


class HistorySink:
    """历史行逐条落 SQL，不在内存累积全量反馈载荷。"""
    def __init__(self, db):
        self.db = db
        self.count = 0

    def append(self, row):
        self.db.execute("""INSERT INTO history_projection(log_id,question_id,uid,date,recorded_at,review_date,
            sub_score,is_correct,session_id,note,commit_id,review_index,legacy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(log_id) DO UPDATE SET question_id=excluded.question_id,uid=excluded.uid,date=excluded.date,
            recorded_at=excluded.recorded_at,review_date=excluded.review_date,sub_score=excluded.sub_score,
            is_correct=excluded.is_correct,session_id=excluded.session_id,note=excluded.note,
            commit_id=excluded.commit_id,review_index=excluded.review_index,legacy=excluded.legacy""",
            (row.get("Log_ID") or f"legacy-{self.count}", row.get("Question_ID") or row.get("_question_id"),
             row.get("UID", ""), row.get("Date", ""), row.get("recorded_at", ""),
             row.get("review_date") or str(row.get("Date", ""))[:10], int(row.get("Sub_Score") or 0),
             int(row.get("Is_Correct") or 0), row.get("Session_ID", ""), row.get("Note", ""),
             row.get("_commit_id", ""), row.get("_review_index", 0), int(bool(row.get("_legacy")))))
        self.count += 1

    def __len__(self):
        return self.count


def _upsert_question(db, q):
    qid = q["question_id"]
    db.execute("""INSERT INTO question_projection(question_id,uid,file_path,subject,category,difficulty,current_tag,
        metadata_json,metadata_hash,content_hash,created_at,archived,suspended,updated_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(question_id) DO UPDATE SET uid=excluded.uid,file_path=excluded.file_path,subject=excluded.subject,
        category=excluded.category,difficulty=excluded.difficulty,current_tag=excluded.current_tag,
        metadata_json=excluded.metadata_json,metadata_hash=excluded.metadata_hash,content_hash=excluded.content_hash,
        created_at=excluded.created_at,archived=excluded.archived,suspended=excluded.suspended,updated_seq=excluded.updated_seq""",
        (qid, q.get("uid", ""), q.get("file_path", ""), q.get("subject", ""), q.get("category", ""),
         q.get("difficulty", 5), q.get("current_tag", ""), canonical_json(q.get("metadata", {})),
         q.get("metadata_hash", ""), q.get("content_hash", ""), q.get("created_at"), int(bool(q.get("archived"))),
         int(bool(q.get("suspended"))), q.get("updated_seq", 0)))
    for table, column, key in (("question_knowledge_points", "knowledge_point", "knowledge_tags"), ("question_labels", "label", "labels")):
        db.execute(f"DELETE FROM {table} WHERE question_id=?", (qid,))
        db.executemany(f"INSERT OR IGNORE INTO {table}(question_id,{column}) VALUES(?,?)", ((qid, value) for value in q.get(key, []) if value))


def _upsert_mastery(db, qid, m):
    columns = ("mastery", "ef", "attempts", "high_correct_streak", "repetition", "interval_days", "due_date", "last_review_at", "kill_count", "updated_seq")
    db.execute("INSERT INTO mastery_projection(question_id," + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in range(11)) + ") ON CONFLICT(question_id) DO UPDATE SET " + ",".join(f"{name}=excluded.{name}" for name in columns),
               (qid, *(m.get(name, "" if name in ("due_date", "last_review_at") else 0) for name in columns)))


def _upsert_session(db, sid, s):
    db.execute("""INSERT INTO session_projection(session_id,created_at,subject_filter,count,items_json,status,completed_at,retracted,updated_seq)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET created_at=excluded.created_at,
        subject_filter=excluded.subject_filter,count=excluded.count,items_json=excluded.items_json,status=excluded.status,
        completed_at=excluded.completed_at,retracted=excluded.retracted,updated_seq=excluded.updated_seq""",
        (sid, s.get("Created_At", ""), s.get("Subject_Filter", ""), int(s.get("Count") or 0), s.get("UIDs", "[]"),
         s.get("Status", "active"), s.get("Completed_At", ""), int(bool(s.get("_retracted"))), s.get("_updated_seq", 0)))


def full_project(vault, db, tuning, head=None):
    from .projections import _empty_state, apply_commit, _write_projection_tables
    head = head or db.execute("SELECT COALESCE(MAX(seq),0) FROM commits").fetchone()[0]
    state = _empty_state()
    state["_tuning"] = tuning
    state["_corrections_precomputed"] = True
    intervals = _intervals(db, head)
    _precompute(db, _commits(db, intervals, corrections_only=True))
    from .projection_corrections import install
    install(vault, state, db)
    db.execute("DELETE FROM history_projection")
    sink = HistorySink(db)
    state["history"] = sink
    for commit in _commits(db, intervals):
        state["_review_results"] = []
        apply_commit(vault, state, commit)
        state["last_seq"] = commit["seq"]
        state["legacy_history"].clear()
    state["last_seq"] = head
    _write_projection_tables(db, state)
    state["history"] = []
    return state


def _snapshot(db, state, digest):
    # 历史明细留在 SQL；快照仅存当前状态。最多两个最近点，恢复点按需重建。
    serial = {key: value for key, value in state.items() if not key.startswith("_") and key not in ("history", "legacy_history", "review_commits", "retracted_sessions", "retracted_reviews", "restored_reviews", "review_replacements")}
    serial = {key: sorted(value) if isinstance(value, set) else value for key, value in serial.items()}
    serial["policy_hash"] = digest
    row = db.execute("SELECT commit_hash,created_at FROM commits WHERE seq=?", (state["last_seq"],)).fetchone()
    if not row:
        return
    serial["head_hash"] = row["commit_hash"]
    db.execute("INSERT OR REPLACE INTO snapshots(seq,snapshot_json,projector_version,created_at) VALUES(?,?,?,?)",
               (state["last_seq"], canonical_json(serial), PROJECTOR_VERSION, row["created_at"]))
    db.execute("DELETE FROM snapshots WHERE seq NOT IN (SELECT seq FROM snapshots ORDER BY seq DESC LIMIT 2)")


def _load_snapshot(vault, db, metadata, digest, tuning, epoch):
    if not metadata or metadata["policy_hash"] != digest or metadata["projector_version"] != PROJECTOR_VERSION:
        return None
    row = db.execute("SELECT snapshot_json FROM snapshots WHERE seq=? AND projector_version=?",
                     (metadata["last_seq"], PROJECTOR_VERSION)).fetchone()
    if not row:
        return None
    try:
        saved = json.loads(row["snapshot_json"])
        if saved.pop("policy_hash", None) != digest or saved.pop("head_hash", None) != metadata["head_hash"]:
            return None
        from .projections import _empty_state
        state = _empty_state()
        state.update(saved)
        from .projection_corrections import install
        install(vault, state)
        state.update(_tuning=tuning, _generation=epoch, _corrections_precomputed=True,
                     _head_hash=metadata["head_hash"])
        return state
    except (ValueError, TypeError, KeyError):
        return None


def apply_incremental(vault, connection, state, tuning, start, maximum):
    """调用方持有写事务；普通追加与反馈提交共用同一有界发布路径。"""
    from .projections import apply_commit
    from .projection_corrections import bind
    previous_seq = state["last_seq"]
    digest = policy_hash(tuning)
    bind(state, connection)
    state["history"] = HistorySink(connection)
    state["_tuning"] = tuning
    try:
        for commit in _commits(connection, [(start, maximum)]):
            state["_review_results"] = []
            apply_commit(vault, state, commit)
            payload = commit["payload"]
            qids = {payload.get("question_id"), (payload.get("question") or {}).get("question_id")}
            qids.update(f.get("question_id") for f in (payload.get("feedbacks") or payload.get("reviews") or []))
            for qid in qids - {None, ""}:
                if qid in state["questions"]:
                    _upsert_question(connection, state["questions"][qid])
                if qid in state["mastery"]:
                    _upsert_mastery(connection, qid, state["mastery"][qid])
            sid = payload.get("session_id") or (payload.get("session") or {}).get("session_id")
            if sid in state["sessions"]:
                _upsert_session(connection, sid, state["sessions"][sid])
            state["last_seq"] = commit["seq"]
        if state["last_seq"] // 1000 > previous_seq // 1000:
            _snapshot(connection, state, digest)
        _publish_meta(connection, state, digest)
        return state
    except BaseException:
        invalidate(vault)
        raise
    finally:
        state["history"] = []
        bind(state)


def project(vault, force=False, tuning=None, db=None):
    from .config_repository import normalized_tuning, _file_config

    def effective_tuning(connection):
        if tuning is not None:
            return tuning
        active = connection.execute("SELECT config_json FROM active_config WHERE id=1").fetchone()
        return normalized_tuning(json.loads(active[0]) if active else _file_config(vault))

    if db is not None:
        effective = effective_tuning(db)
        state = full_project(vault, db, effective)
        _publish_meta(db, state, policy_hash(effective))
        invalidate(vault)
        return state
    with lifecycle(vault) as epoch, write_lock():
        key = os.path.realpath(vault)
        with connect(vault) as connection:
            connection.execute("BEGIN IMMEDIATE")
            # 参数与投影共享写事务；跨进程调参不能被迟到读取覆盖。
            effective = effective_tuning(connection)
            digest = policy_hash(effective)
            head = connection.execute("SELECT seq,commit_hash FROM commits ORDER BY seq DESC LIMIT 1").fetchone()
            maximum = head["seq"] if head else 0
            state = _CACHE.get(key)
            metadata = connection.execute("SELECT * FROM projection_meta WHERE id=1").fetchone()
            if state is None and not force:
                state = _load_snapshot(vault, connection, metadata, digest, effective, epoch)
            prefix = connection.execute("SELECT commit_hash FROM commits WHERE seq=?", (metadata["last_seq"],)).fetchone() if metadata else None
            valid = state and state.get("_generation") == epoch and metadata and metadata["policy_hash"] == digest and metadata["projector_version"] == PROJECTOR_VERSION and state["last_seq"] == metadata["last_seq"] and maximum >= state["last_seq"] and state.get("_head_hash", "") == metadata["head_hash"] and (prefix[0] if prefix else "") == metadata["head_hash"]
            if valid and maximum == state["last_seq"] and not force:
                _CACHE[key] = state
                _CACHE.move_to_end(key)
                while len(_CACHE) > 2:
                    _CACHE.popitem(last=False)
                return state
            start = state["last_seq"] + 1 if valid else 1
            requires_full = connection.execute("SELECT 1 FROM commits WHERE seq>=? AND seq<=? AND commit_type IN (" +
                ",".join("?" for _ in _FULL_TYPES) + ") LIMIT 1", (start, maximum, *sorted(_FULL_TYPES))).fetchone()
            if force or not valid or requires_full:
                state = full_project(vault, connection, effective, maximum)
                _snapshot(connection, state, digest)
                _publish_meta(connection, state, digest)
            else:
                apply_incremental(vault, connection, state, effective, start, maximum)
            from .projection_corrections import bind
            bind(state)
            state["_generation"] = epoch
        _CACHE[key] = state
        _CACHE.move_to_end(key)
        while len(_CACHE) > 2:
            _CACHE.popitem(last=False)
        return state


def _publish_meta(db, state, digest):
    row = db.execute("SELECT commit_hash FROM commits WHERE seq=?", (state["last_seq"],)).fetchone()
    state["_head_hash"] = row[0] if row else ""
    db.execute("INSERT OR REPLACE INTO projection_meta VALUES(1,?,?,?,?)",
               (state["last_seq"], row[0] if row else "", digest, PROJECTOR_VERSION))
