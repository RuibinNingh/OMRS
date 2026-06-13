import datetime
import hashlib
import json
import os
import sqlite3

from .common import omrs_data_dir
from .version import __version__


SCHEMA_VERSION = 1
PROJECTOR_VERSION = "ledger-v1"


def ledger_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), "ledger.db")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        result = super().__exit__(exc_type, exc, tb)
        self.close()
        return result


def connect(vault: str):
    db = sqlite3.connect(ledger_path(vault), factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    init_db(db)
    return db


def init_db(db):
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS commits (
            seq               INTEGER PRIMARY KEY AUTOINCREMENT,
            commit_id         TEXT NOT NULL UNIQUE,
            prev_hash         TEXT,
            commit_hash       TEXT NOT NULL UNIQUE,
            created_at        TEXT NOT NULL,
            source            TEXT NOT NULL,
            commit_type       TEXT NOT NULL,
            message           TEXT NOT NULL,
            payload_json      TEXT NOT NULL,
            schema_version    INTEGER NOT NULL,
            projector_version TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS counters (
            name  TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS question_projection (
            question_id   TEXT PRIMARY KEY,
            uid           TEXT NOT NULL UNIQUE,
            file_path     TEXT NOT NULL UNIQUE,
            subject       TEXT NOT NULL,
            category      TEXT NOT NULL,
            difficulty    INTEGER,
            current_tag   TEXT,
            metadata_json TEXT NOT NULL,
            metadata_hash TEXT NOT NULL,
            content_hash  TEXT,
            archived      INTEGER NOT NULL DEFAULT 0,
            updated_seq   INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS question_knowledge_points (
            question_id     TEXT NOT NULL,
            knowledge_point TEXT NOT NULL,
            PRIMARY KEY (question_id, knowledge_point)
        );

        CREATE TABLE IF NOT EXISTS mastery_projection (
            question_id           TEXT PRIMARY KEY,
            mastery               REAL NOT NULL,
            ef                    REAL NOT NULL,
            attempts              INTEGER NOT NULL,
            high_correct_streak   INTEGER NOT NULL,
            repetition            INTEGER NOT NULL,
            interval_days         INTEGER NOT NULL,
            due_date              TEXT,
            last_review_at        TEXT,
            updated_seq           INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_projection (
            session_id     TEXT PRIMARY KEY,
            created_at     TEXT NOT NULL,
            subject_filter TEXT,
            count          INTEGER NOT NULL,
            items_json     TEXT NOT NULL,
            status         TEXT NOT NULL,
            completed_at   TEXT,
            retracted      INTEGER NOT NULL DEFAULT 0,
            updated_seq    INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            seq               INTEGER PRIMARY KEY,
            snapshot_json     TEXT NOT NULL,
            projector_version TEXT NOT NULL,
            created_at        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workspace_fingerprint (
            file_path     TEXT PRIMARY KEY,
            question_id   TEXT,
            uid           TEXT NOT NULL,
            metadata_hash TEXT NOT NULL,
            content_hash  TEXT NOT NULL,
            last_seen_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workspace_scan_status (
            id               INTEGER PRIMARY KEY CHECK (id = 1),
            last_scan_at     TEXT,
            change_count     INTEGER NOT NULL DEFAULT 0,
            conflict_count   INTEGER NOT NULL DEFAULT 0,
            conflicts_json   TEXT NOT NULL DEFAULT '[]',
            last_error       TEXT
        );
        """
    )
    db.execute(
        "INSERT OR IGNORE INTO workspace_scan_status "
        "(id, change_count, conflict_count, conflicts_json) VALUES (1, 0, 0, '[]')"
    )
    db.commit()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_commit_hash(prev_hash, created_at, source, commit_type, payload) -> str:
    raw = f"{prev_hash or ''}{created_at}{source}{commit_type}{canonical_json(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _next_counter(db, name: str) -> int:
    row = db.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()
    if row is None:
        value = 1
        db.execute("INSERT INTO counters(name, value) VALUES (?, ?)", (name, value))
    else:
        value = int(row["value"]) + 1
        db.execute("UPDATE counters SET value = ? WHERE name = ?", (value, name))
    return value


def reserve_operation_id(vault: str) -> str:
    with connect(vault) as db:
        return reserve_operation_id_in_db(db)


def reserve_operation_id_in_db(db) -> str:
    return f"OP-{_next_counter(db, 'operation'):06d}"


def has_commits(vault: str) -> bool:
    if not os.path.exists(ledger_path(vault)):
        return False
    with connect(vault) as db:
        row = db.execute("SELECT COUNT(*) AS n FROM commits").fetchone()
        return bool(row and row["n"])


def append_commit(vault: str, source: str, commit_type: str, message: str, payload: dict):
    with connect(vault) as db:
        return append_commit_in_db(db, source, commit_type, message, payload)


def append_commit_in_db(db, source: str, commit_type: str, message: str, payload: dict):
    payload = payload or {}
    row = db.execute(
        "SELECT seq, commit_hash FROM commits ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    prev_hash = row["commit_hash"] if row else None
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    commit_hash = compute_commit_hash(prev_hash, created_at, source, commit_type, payload)
    cur = db.execute(
        """
        INSERT INTO commits
        (commit_id, prev_hash, commit_hash, created_at, source, commit_type,
         message, payload_json, schema_version, projector_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PENDING",
            prev_hash,
            commit_hash,
            created_at,
            source,
            commit_type,
            message,
            canonical_json(payload),
            SCHEMA_VERSION,
            PROJECTOR_VERSION,
        ),
    )
    seq = cur.lastrowid
    commit_id = "GENESIS" if commit_type == "system.genesis" and seq == 1 else f"CMT-{seq:06d}"
    db.execute("UPDATE commits SET commit_id = ? WHERE seq = ?", (commit_id, seq))
    db.commit()
    return {
        "seq": seq,
        "commit_id": commit_id,
        "commit_hash": commit_hash,
        "created_at": created_at,
        "version": __version__,
    }


def read_commits(vault: str, before_seq=None, limit=None, ascending=True):
    with connect(vault) as db:
        where = ""
        args = []
        if before_seq:
            where = "WHERE seq < ?"
            args.append(int(before_seq))
        order = "ASC" if ascending else "DESC"
        sql = f"SELECT * FROM commits {where} ORDER BY seq {order}"
        if limit:
            sql += " LIMIT ?"
            args.append(int(limit))
        return [_row_to_commit(row) for row in db.execute(sql, args).fetchall()]


def get_commit(vault: str, seq: int):
    with connect(vault) as db:
        row = db.execute("SELECT * FROM commits WHERE seq = ?", (int(seq),)).fetchone()
        return _row_to_commit(row) if row else None


def _row_to_commit(row):
    return {
        "seq": row["seq"],
        "commit_id": row["commit_id"],
        "prev_hash": row["prev_hash"],
        "commit_hash": row["commit_hash"],
        "created_at": row["created_at"],
        "source": row["source"],
        "commit_type": row["commit_type"],
        "message": row["message"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "schema_version": row["schema_version"],
        "projector_version": row["projector_version"],
    }


def verify_ledger(vault: str) -> dict:
    if not os.path.exists(ledger_path(vault)):
        return {"status": "ok", "valid": False, "commits": 0, "errors": ["ledger.db 不存在"]}
    errors = []
    head = None
    prev_hash = None
    expected_seq = None
    with connect(vault) as db:
        rows = db.execute("SELECT * FROM commits ORDER BY seq ASC").fetchall()
    for row in rows:
        if expected_seq is None:
            expected_seq = int(row["seq"])
        elif int(row["seq"]) != expected_seq + 1:
            errors.append(f"seq 不连续: {expected_seq} -> {row['seq']}")
        expected_seq = int(row["seq"])
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            errors.append(f"{row['commit_id']} payload_json 无法解析")
            payload = {}
        if row["prev_hash"] != prev_hash:
            errors.append(f"{row['commit_id']} prev_hash 不匹配")
        expected_hash = compute_commit_hash(
            row["prev_hash"],
            row["created_at"],
            row["source"],
            row["commit_type"],
            payload,
        )
        if row["commit_hash"] != expected_hash:
            errors.append(f"{row['commit_id']} commit_hash 不匹配")
        prev_hash = row["commit_hash"]
        head = row
    return {
        "status": "ok",
        "valid": not errors,
        "commits": len(rows),
        "head_commit_id": head["commit_id"] if head else "",
        "errors": errors,
    }
