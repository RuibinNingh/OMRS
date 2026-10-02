"""对话存储：错题/.omrs/agent.db（对话、消息、运行、事件、工具调用）。不进 Ledger，随备份导出。

每次调用新建连接；模块锁只包住单次 SQL 事务（锁顺序：写锁在外，本锁在内）。
"""
import base64
import datetime
import json
import os
import sqlite3
import threading
import secrets

from ..common import omrs_data_dir
from ..vault_lifecycle import lease, open_sqlite, storage

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
            CREATE INDEX IF NOT EXISTS runs_conv ON runs(conversation_id, started_at, id);
            CREATE TABLE IF NOT EXISTS run_events (
                run_id TEXT NOT NULL, seq INTEGER NOT NULL, event_type TEXT NOT NULL,
                event_json TEXT NOT NULL, PRIMARY KEY(run_id, seq));
            CREATE INDEX IF NOT EXISTS run_event_stats ON run_events(run_id,event_type,seq);
            CREATE TABLE IF NOT EXISTS tool_calls (
                call_id TEXT NOT NULL, run_id TEXT NOT NULL, name TEXT NOT NULL, level TEXT NOT NULL,
                args_json TEXT NOT NULL, status TEXT NOT NULL, decision TEXT, result_json TEXT,
                commits_json TEXT NOT NULL DEFAULT '[]', started_at TEXT, ended_at TEXT,
                PRIMARY KEY (run_id, call_id));
            CREATE TABLE IF NOT EXISTS practice_cards (
                card_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, run_id TEXT NOT NULL,
                call_id TEXT NOT NULL, card_json TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE (run_id, call_id));
            CREATE TABLE IF NOT EXISTS practice_attempts (
                attempt_id TEXT PRIMARY KEY, card_id TEXT NOT NULL, created_at TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0, request_id TEXT UNIQUE,
                progress_json TEXT NOT NULL DEFAULT '{}');
            CREATE UNIQUE INDEX IF NOT EXISTS practice_default_attempt
                ON practice_attempts(card_id) WHERE is_default = 1;
            """)
            # 旧完成事件在 SQLite 内逐项迁移，避免 Python 读取整个历史数组。
            db.execute("""INSERT OR IGNORE INTO run_events(run_id,seq,event_type,event_json)
                SELECT runs.id, CAST(j.key AS INTEGER), json_extract(j.value,'$.type'),
                    json_set(j.value,'$.i',CAST(j.key AS INTEGER))
                FROM runs, json_each(runs.events_json) AS j WHERE runs.events_json != '[]'""")
            db.execute("UPDATE runs SET events_json='[]' WHERE events_json != '[]'")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(practice_attempts)")}
            if "request_id" not in columns:
                db.execute("ALTER TABLE practice_attempts ADD COLUMN request_id TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS practice_restart_request ON practice_attempts(request_id)")

    def _db(self):
        db = open_sqlite(self.vault, db_path(self.vault), timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 5000")
        return db

    def _exec(self, sql, args=(), many=False):
        with lease(self.vault), _LOCK:
            db = self._db()
            try:
                cur = db.executemany(sql, args) if many else db.execute(sql, args)
                db.commit()
                return cur.lastrowid
            finally:
                db.close()

    def _all(self, sql, args=()):
        with lease(self.vault), _LOCK:
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
            self._exec("INSERT OR IGNORE INTO run_events(run_id,seq,event_type,event_json) VALUES(?,?,?,?)",
                       [(run_id, i, event["type"], json.dumps({**event, "i": i}, ensure_ascii=False, default=str))
                        for i, event in enumerate(events)], many=True)
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
        row["events"] = json.loads(row.pop("events_json", "[]") or "[]")
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

    # ── 聊天练习卡与尝试：只存题序和非权威界面进度，反馈事实来自 Ledger ──
    def save_practice_card(self, card, conv_id, run_id, call_id):
        with lease(self.vault), _LOCK:
            with self._db() as db:
                row = db.execute("SELECT card_json FROM practice_cards WHERE run_id=? AND call_id=?", (run_id, call_id)).fetchone()
                if row:
                    return json.loads(row["card_json"])
                db.execute("INSERT INTO practice_cards(card_id,conversation_id,run_id,call_id,card_json,created_at) VALUES(?,?,?,?,?,?)",
                           (card["card_id"], conv_id, run_id, call_id, json.dumps(card, ensure_ascii=False), now_iso()))
                return card

    def practice_card(self, card_id):
        rows = self._all("SELECT p.*, c.deleted FROM practice_cards p JOIN conversations c ON c.id=p.conversation_id WHERE p.card_id=?", (card_id,))
        if not rows:
            return None
        row = rows[0]
        return {**json.loads(row["card_json"]), "conversation_id": row["conversation_id"], "deleted": bool(row["deleted"])}

    def start_practice(self, card_id, restart=False, request_id=""):
        with lease(self.vault), _LOCK:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT c.deleted FROM practice_cards p JOIN conversations c ON c.id=p.conversation_id WHERE p.card_id=?", (card_id,)).fetchone()
                if not row:
                    raise ValueError("练习卡不存在")
                if row["deleted"]:
                    raise ValueError("对话已删除，不能重新开始练习")
                if restart:
                    if not request_id or len(request_id) > 100:
                        raise ValueError("重新练习需要稳定请求标识")
                    prior = db.execute("SELECT attempt_id,card_id FROM practice_attempts WHERE request_id=?", (request_id,)).fetchone()
                    if prior:
                        if prior["card_id"] != card_id:
                            raise ValueError("请求标识已用于另一张练习卡")
                        return prior["attempt_id"]
                if not restart:
                    found = db.execute("SELECT attempt_id FROM practice_attempts WHERE card_id=? ORDER BY rowid DESC LIMIT 1", (card_id,)).fetchone()
                    if found:
                        return found["attempt_id"]
                attempt_id = "PA-" + secrets.token_hex(12)
                db.execute("INSERT INTO practice_attempts(attempt_id,card_id,created_at,is_default,request_id) VALUES(?,?,?,?,?)",
                           (attempt_id, card_id, now_iso(), 0 if restart else 1, request_id or None))
                return attempt_id

    def practice_attempt(self, attempt_id):
        rows = self._all("SELECT * FROM practice_attempts WHERE attempt_id=?", (attempt_id,))
        if not rows:
            return None
        row = rows[0]
        return {**row, "progress": json.loads(row["progress_json"] or "{}")}

    def default_practice_attempt(self, card_id):
        rows = self._all("SELECT * FROM practice_attempts WHERE card_id=? ORDER BY rowid DESC LIMIT 1", (card_id,))
        if not rows:
            return None
        row = rows[0]
        return {**row, "progress": json.loads(row["progress_json"] or "{}")}

    def save_practice_progress(self, attempt_id, progress):
        with lease(self.vault), _LOCK:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT progress_json FROM practice_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
                if not row:
                    raise ValueError("练习尝试不存在")
                old = json.loads(row["progress_json"] or "{}")
                if int(progress.get("seq") or 0) > int(old.get("seq") or 0):
                    db.execute("UPDATE practice_attempts SET progress_json=? WHERE attempt_id=?",
                               (json.dumps(progress, ensure_ascii=False), attempt_id))


    @staticmethod
    def _cursor(values):
        return base64.urlsafe_b64encode(json.dumps(values, separators=(",", ":")).encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor):
        if not isinstance(cursor, str) or len(cursor) > 1024:
            raise ValueError("分页游标不合法")
        try:
            values = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("分页游标不合法") from exc
        if not isinstance(values, list) or len(values) != 2 or not all(isinstance(v, str) for v in values):
            raise ValueError("分页游标不合法")
        return values

    def conversation_page(self, limit=30, cursor=None):
        limit = max(1, min(100, int(limit)))
        extra, args = "", []
        if cursor:
            stamp, identity = self._decode_cursor(cursor)
            extra = " AND (c.updated_at < ? OR (c.updated_at = ? AND c.id < ?))"
            args.extend((stamp, stamp, identity))
        rows = self._all("""SELECT c.*,
            (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS msgs,
            (SELECT COUNT(*) FROM runs r WHERE r.conversation_id=c.id) AS runs,
            (SELECT COALESCE(SUM(json_extract(stats_json,'$.writes')),0) FROM runs r
              WHERE r.conversation_id=c.id AND r.reverted_json IS NULL) AS writes,
            (SELECT substr(json_extract(message_json,'$.content'),1,120) FROM messages m
              WHERE m.conversation_id=c.id AND m.role IN ('assistant','user')
              AND json_extract(message_json,'$.content') != '' ORDER BY id DESC LIMIT 1) AS snippet,
            EXISTS(SELECT 1 FROM runs r WHERE r.conversation_id=c.id AND r.reverted_json IS NOT NULL) AS reverted
            FROM conversations c WHERE c.deleted=0""" + extra + " ORDER BY c.updated_at DESC,c.id DESC LIMIT ?",
            (*args, limit + 1))
        more, rows = len(rows) > limit, rows[:limit]
        return {"conversations": rows, "has_more": more,
                "next_cursor": self._cursor([rows[-1]["updated_at"],rows[-1]["id"]]) if more else None}

    def run_page(self, conv_id, limit=20, cursor=None):
        limit = max(1, min(50, int(limit)))
        extra, args = "", [conv_id]
        if cursor:
            stamp, identity = self._decode_cursor(cursor)
            extra = " AND (started_at < ? OR (started_at = ? AND id < ?))"
            args.extend((stamp, stamp, identity))
        rows = self._all("SELECT id,conversation_id,status,reason,error,model,started_at,ended_at,stats_json,reverted_json "
            "FROM runs WHERE conversation_id=?" + extra + " ORDER BY started_at DESC,id DESC LIMIT ?", (*args, limit + 1))
        more, rows = len(rows) > limit, rows[:limit]
        cursor = self._cursor([rows[-1]["started_at"],rows[-1]["id"]]) if more else None
        return {"runs": [self._run_row(row) for row in reversed(rows)], "has_more": more,"next_cursor":cursor}

    def starter_message(self, run_id):
        rows = self._all("SELECT * FROM messages WHERE run_id=? AND role='user' ORDER BY id LIMIT 1", (run_id,))
        if not rows:
            return None
        row = rows[0]
        return {**json.loads(row["message_json"]), "_run":run_id,"_at":row["created_at"],"_id":row["id"]}

    def append_event(self, run_id, event):
        self._exec("INSERT INTO run_events(run_id,seq,event_type,event_json) VALUES(?,?,?,?)",
                   (run_id,event["i"],event["type"],json.dumps(event,ensure_ascii=False,default=str)))

    def event_page(self, run_id, after=0, limit=200):
        after, limit = int(after), max(1,min(500,int(limit)))
        if after < 0:
            raise ValueError("事件游标不能为负数")
        rows = self._all("SELECT seq,event_json FROM run_events WHERE run_id=? AND seq>=? ORDER BY seq LIMIT ?",
                         (run_id,after,limit+1))
        more, rows = len(rows)>limit, rows[:limit]
        events = [json.loads(row["event_json"]) for row in rows]
        return {"events":events,"next": rows[-1]["seq"]+1 if rows else after,"has_more":more}
