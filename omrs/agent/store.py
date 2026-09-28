"""对话存储：错题/.omrs/agent.db（对话、消息、运行、事件、工具调用）。不进 Ledger，随备份导出。

每次调用新建连接；模块锁只包住单次 SQL 事务（锁顺序：写锁在外，本锁在内）。
"""
import datetime
import json
import os
import sqlite3
import threading

from ..common import omrs_data_dir

_LOCK = threading.Lock()


def db_path(vault):
    return os.path.join(omrs_data_dir(vault), "agent.db")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


class AgentStore:
    def __init__(self, vault):
        self.vault = vault
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, run_id TEXT,
                role TEXT NOT NULL, message_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS messages_conv ON messages(conversation_id, id);
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                error TEXT, model TEXT, started_at TEXT NOT NULL, ended_at TEXT,
                stats_json TEXT NOT NULL DEFAULT '{}', events_json TEXT NOT NULL DEFAULT '[]',
                reverted_json TEXT);
            CREATE INDEX IF NOT EXISTS runs_conv ON runs(conversation_id, started_at);
            CREATE TABLE IF NOT EXISTS tool_calls (
                call_id TEXT NOT NULL, run_id TEXT NOT NULL, name TEXT NOT NULL, level TEXT NOT NULL,
                args_json TEXT NOT NULL, status TEXT NOT NULL, decision TEXT, result_json TEXT,
                commits_json TEXT NOT NULL DEFAULT '[]', started_at TEXT, ended_at TEXT,
                PRIMARY KEY (run_id, call_id));
            """)

    def _db(self):
        db = sqlite3.connect(db_path(self.vault), timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 5000")
        return db

    def _exec(self, sql, args=(), many=False):
        with _LOCK:
            db = self._db()
            try:
                cur = db.executemany(sql, args) if many else db.execute(sql, args)
                db.commit()
                return cur.lastrowid
            finally:
                db.close()

    def _all(self, sql, args=()):
        with _LOCK:
            db = self._db()
            try:
                return [dict(r) for r in db.execute(sql, args).fetchall()]
            finally:
                db.close()

    # ── 对话 ──
    def create_conversation(self, conv_id, title):
        t = now_iso()
        self._exec("INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                   (conv_id, title, t, t))
        return self.conversation(conv_id)

    def conversation(self, conv_id):
        rows = self._all("SELECT * FROM conversations WHERE id = ? AND deleted = 0", (conv_id,))
        return rows[0] if rows else None

    def touch(self, conv_id, title=None):
        if title:
            self._exec("UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?", (now_iso(), title, conv_id))
        else:
            self._exec("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), conv_id))

    def delete_conversation(self, conv_id):
        self._exec("UPDATE conversations SET deleted = 1, updated_at = ? WHERE id = ?", (now_iso(), conv_id))

    def conversations(self):
        return self._all("""
            SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS msgs
            FROM conversations c WHERE c.deleted = 0 ORDER BY c.updated_at DESC""")

    # ── 消息 ──
    def add_message(self, conv_id, run_id, message):
        return self._exec("INSERT INTO messages(conversation_id, run_id, role, message_json, created_at) VALUES (?, ?, ?, ?, ?)",
                          (conv_id, run_id, message.get("role", ""), json.dumps(message, ensure_ascii=False), now_iso()))

    def messages(self, conv_id):
        rows = self._all("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,))
        out = []
        for row in rows:
            msg = json.loads(row["message_json"])
            msg["_run"], msg["_at"], msg["_id"] = row["run_id"], row["created_at"], row["id"]
            out.append(msg)
        return out

    def message_count(self, conv_id):
        return self._all("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (conv_id,))[0]["n"]

    # ── 运行 ──
    def create_run(self, run_id, conv_id, model):
        self._exec("INSERT INTO runs(id, conversation_id, status, model, started_at) VALUES (?, ?, 'running', ?, ?)",
                   (run_id, conv_id, model, now_iso()))

    def save_run(self, run_id, *, status=None, reason=None, error=None, stats=None, events=None, ended=False):
        sets, args = [], []
        for col, val in (("status", status), ("reason", reason), ("error", error)):
            if val is not None:
                sets.append(f"{col} = ?")
                args.append(val)
        if stats is not None:
            sets.append("stats_json = ?")
            args.append(json.dumps(stats, ensure_ascii=False))
        if events is not None:
            sets.append("events_json = ?")
            args.append(json.dumps(events, ensure_ascii=False, default=str))
        if ended:
            sets.append("ended_at = ?")
            args.append(now_iso())
        if sets:
            self._exec(f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", (*args, run_id))

    def set_reverted(self, run_id, info):
        self._exec("UPDATE runs SET reverted_json = ? WHERE id = ?", (json.dumps(info, ensure_ascii=False), run_id))

    def runs(self, conv_id):
        return [self._run_row(r) for r in self._all(
            "SELECT * FROM runs WHERE conversation_id = ? ORDER BY started_at", (conv_id,))]

    def run(self, run_id):
        rows = self._all("SELECT * FROM runs WHERE id = ?", (run_id,))
        return self._run_row(rows[0]) if rows else None

    @staticmethod
    def _run_row(row):
        row = dict(row)
        row["stats"] = json.loads(row.pop("stats_json") or "{}")
        row["events"] = json.loads(row.pop("events_json") or "[]")
        row["reverted"] = json.loads(row.pop("reverted_json")) if row.get("reverted_json") else None
        return row

    def interrupt_leftovers(self):
        self._exec("UPDATE runs SET status = 'done', reason = 'interrupted', error = '服务重启，运行被中断', "
                   "ended_at = ? WHERE status IN ('running', 'waiting')", (now_iso(),))

    # ── 工具调用 ──
    def save_tool_call(self, run_id, call_id, name, level, args, status, decision=None, result=None, commits=None):
        self._exec("""INSERT INTO tool_calls(call_id, run_id, name, level, args_json, status, decision, result_json,
                      commits_json, started_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                      ON CONFLICT(run_id, call_id) DO UPDATE SET status = excluded.status, decision = excluded.decision,
                      result_json = excluded.result_json, commits_json = excluded.commits_json, ended_at = excluded.ended_at""",
                   (call_id, run_id, name, level, json.dumps(args, ensure_ascii=False), status, decision,
                    json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                    json.dumps(commits or [], ensure_ascii=False), now_iso(), now_iso()))
