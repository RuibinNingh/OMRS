"""独立问题事实库；只读不建库，写入带生命周期租约、审计与原生回执。"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .vault_lifecycle import open_sqlite, lease

SCHEMA = 1


def path(vault):
    return os.path.join(os.path.abspath(vault), '错题', '.omrs', 'problems.db')


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


@contextmanager
def connect(vault, write=False):
    with lease(vault):
        target = path(vault)
        if os.path.islink(target) or os.path.islink(os.path.dirname(target)):
            raise ValueError('问题库路径不安全')
        if not write and not os.path.exists(target):
            yield None
            return
        if write:
            os.makedirs(os.path.dirname(target), exist_ok=True)
        db = open_sqlite(vault, target if write else Path(target).as_uri()+'?mode=ro', uri=not write, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, SCHEMA):
                raise ValueError('问题库版本不受支持，请勿降级打开')
            if write and version == 0:
                db.executescript('''
                    CREATE TABLE objects(id TEXT PRIMARY KEY, kind TEXT NOT NULL, question_id TEXT NOT NULL DEFAULT '', data TEXT NOT NULL);
                    CREATE INDEX object_kind ON objects(kind,question_id);
                    CREATE TABLE links(problem_id TEXT NOT NULL, question_id TEXT NOT NULL, uid TEXT NOT NULL, PRIMARY KEY(problem_id,question_id));
                    CREATE TABLE events(seq INTEGER PRIMARY KEY, object_id TEXT NOT NULL, data TEXT NOT NULL);
                    CREATE TABLE receipts(request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
                    CREATE TABLE settings(key TEXT PRIMARY KEY, data TEXT NOT NULL);
                    CREATE TABLE ai_review_receipts(operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, result_json TEXT NOT NULL);
                    PRAGMA user_version=1;
                ''')
                os.chmod(target, 0o600)
            if version == 0 and not write:
                raise ValueError('问题库架构不完整')
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def load(db, identity, kind=None):
    row = db.execute('SELECT kind,data FROM objects WHERE id=?', (identity,)).fetchone() if db else None
    if not row or kind and row['kind'] != kind:
        raise ValueError('问题或记录不存在')
    return json.loads(row['data'])


def save(db, kind, value):
    db.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?,?)', (value['id'], kind, value.get('question_id',''), dumps(value)))
