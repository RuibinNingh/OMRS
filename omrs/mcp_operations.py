"""高风险 MCP 操作独立确认库；完整参数不进入脱敏系统运行库。"""
from .vault_lifecycle import storage, open_sqlite, lease, task, generation
import datetime
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from . import boards, locking
from .common import omrs_data_dir
from .mcp.common import RequestError

TTL = 600
TERMINAL = ('applied', 'rejected', 'expired', 'conflict')


def web_origin(value):
    parts = urlsplit(value)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or
            parts.path not in ('', '/') or parts.query or parts.fragment):
        raise ValueError('Web 公共地址必须是无路径、凭据和查询参数的 HTTP/HTTPS 来源')
    try:
        parts.port
    except ValueError:
        raise ValueError('Web 公共地址端口无效') from None
    return value.rstrip('/')


@storage
def path(vault):
    return os.path.join(omrs_data_dir(vault), 'mcp_operations.db')


@storage
def _connect(vault, write=False):
    target = path(vault)
    if os.path.islink(target):
        raise ValueError('确认库不允许符号链接')
    if write:
        descriptor = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        os.chmod(target, 0o600)
        db = open_sqlite(vault, target, timeout=5)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL,
                    key_id TEXT NOT NULL, tool TEXT NOT NULL, digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL, impact_json TEXT NOT NULL, snapshot TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}', error_code TEXT NOT NULL DEFAULT ''
                );
            ''')
        except BaseException:
            db.close()
            raise
    else:
        db = open_sqlite(vault, Path(target).as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def _decode(row):
    if row is None:
        return None
    row = dict(row)
    for key in ('payload', 'impact', 'result'):
        row[key] = json.loads(row.pop(key + '_json'))
    return row


@storage
def _read(vault, field, value):
    if not os.path.exists(path(vault)):
        return None
    with closing(_connect(vault)) as db:
        return _decode(db.execute(f'SELECT * FROM operations WHERE {field}=?', (value,)).fetchone())


@storage
def by_identity(vault, identity):
    return _read(vault, 'identity', identity)


def _public(row, web_url=''):
    stamp = lambda value: datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat()
    value = {k: row[k] for k in ('operation_id', 'key_id', 'tool', 'status', 'impact', 'result', 'error_code')}
    value.update(created_at=stamp(row['created_at']), expires_at=stamp(row['expires_at']))
    if web_url:
        value['confirmation_url'] = web_origin(web_url) + '/#/history?operation=' + row['operation_id']
    return value


@storage
def _save_state(vault, row, status, result=None, error_code=''):
    with closing(_connect(vault, True)) as db:
        db.execute('UPDATE operations SET status=?, result_json=?, error_code=? WHERE operation_id=?',
                   (status, json.dumps(result or {}, ensure_ascii=False), error_code, row['operation_id']))
        db.commit()
    row.update(status=status, result=result or {}, error_code=error_code)
    from . import runtime_records
    runtime_records.safely(runtime_records.operation_status, vault, row['operation_id'], status, error_code)
    return row


@storage
def create(vault, key_id, tool, identity, digest, payload, impact, snapshot, web_url):
    now = time.time()
    row = {'operation_id': 'op_' + uuid.uuid4().hex, 'identity': identity, 'digest': digest,
           'key_id': key_id, 'tool': tool, 'payload': payload, 'impact': impact, 'snapshot': snapshot,
           'status': 'pending_confirmation', 'created_at': now, 'expires_at': now+TTL, 'result': {}, 'error_code': ''}
    with closing(_connect(vault, True)) as db:
        db.execute('INSERT INTO operations(operation_id,identity,key_id,tool,digest,payload_json,impact_json,snapshot,'
                   'status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (row['operation_id'], identity, key_id, tool, digest, json.dumps(payload, ensure_ascii=False),
                    json.dumps(impact, ensure_ascii=False), snapshot, row['status'], now, now+TTL))
        db.commit()
    return _public(row, web_url)


@storage
def _recover(vault, row):
    from . import mcp_board
    # 已合法提交的领域回执优先，重启/响应丢失后不因随后吊销而误报未执行。
    receipt = boards.load_boards(vault)['mcp_receipts'].get(row['identity']) if row['status'] == 'applying' else None
    if receipt:
        if receipt['digest'] != row['digest']:
            return _save_state(vault, row, 'conflict', error_code='request_conflict')
        return _save_state(vault, row, 'applied', receipt['result'])
    if row['status'] not in ('pending_confirmation', 'applying'):
        return row
    if time.time() >= row['expires_at']:
        return _save_state(vault, row, 'expired')
    if row['status'] == 'applying':
        return _apply(vault, row)
    return row


@storage
def get(vault, operation_id, key_id=None, web_url=''):
    if not isinstance(operation_id, str) or not re.fullmatch(r'op_[0-9a-f]{32}', operation_id):
        raise RequestError('not_found', '确认操作不存在')
    with locking.write_lock():
        row = _read(vault, 'operation_id', operation_id)
        if not row or (key_id is not None and row['key_id'] != key_id):
            raise RequestError('not_found', '确认操作不存在')
        return _public(_recover(vault, row), web_url)


@storage
def _apply(vault, row):
    from . import mcp_board
    auth = lambda: mcp_board.authorize(vault, row['key_id'], row['tool'])
    try:
        auth()
        _, _, snapshot = mcp_board.preview(vault, row['tool'], row['payload'], auth)
        if snapshot != row['snapshot']:
            return _save_state(vault, row, 'conflict', error_code='revision_conflict')
        # applying 持久化后才动领域；跨文件崩溃以同一原子回执恢复。
        _save_state(vault, row, 'applying')
        result = boards.transaction(vault, lambda: mcp_board.dispatch(vault, row['tool'], row['payload']),
                                    row['identity'], row['digest'], auth, protect_paper=True)
        return _save_state(vault, row, 'applied', result)
    except (PermissionError, boards.BoardConflict, RequestError, ValueError) as exc:
        receipt = boards.load_boards(vault)['mcp_receipts'].get(row['identity']) if row['status'] == 'applying' else None
        if receipt and receipt['digest'] == row['digest']:
            return _save_state(vault, row, 'applied', receipt['result'])
        code = 'forbidden' if isinstance(exc, PermissionError) else getattr(exc, 'code', 'invalid_request')
        return _save_state(vault, row, 'conflict', error_code=code)


@storage
def decide(vault, operation_id, decision):
    if not isinstance(operation_id, str) or not re.fullmatch(r'op_[0-9a-f]{32}', operation_id):
        raise RequestError('not_found', '确认操作不存在')
    if decision not in ('confirm', 'reject'):
        raise ValueError('decision 必须是 confirm 或 reject')
    with locking.write_lock():
        row = _read(vault, 'operation_id', operation_id)
        if not row:
            raise RequestError('not_found', '确认操作不存在')
        row = _recover(vault, row)
        if row['status'] != 'pending_confirmation':
            return _public(row)
        if decision == 'reject':
            return _public(_save_state(vault, row, 'rejected'))
        return _public(_apply(vault, row))


@storage
def refresh(vault):
    """网页读运行列表时收束到期和上次已确认的中断执行。"""
    if not os.path.exists(path(vault)):
        return
    with locking.write_lock():
        with closing(_connect(vault)) as db:
            rows = [_decode(row) for row in db.execute("SELECT * FROM operations WHERE status IN ('pending_confirmation','applying')")]
        for row in rows:
            _recover(vault, row)
