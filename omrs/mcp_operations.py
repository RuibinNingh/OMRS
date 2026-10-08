"""MCP 确认兼容入口与原生回执核对；统一权威在 ai_review，查询绝不执行业务。"""
from .vault_lifecycle import storage, open_sqlite, lease, task, generation
import datetime
import json
import os
import re
import sqlite3
import time
import uuid
import logging
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
    from . import ai_review
    row = ai_review.by_identity(vault, identity)
    return row or _import_legacy(vault, _read(vault, 'identity', identity))


def _public(row, web_url=''):
    from . import ai_review
    value = ai_review.public(row, web_url)
    value['key_id'] = (row.get('actor') or {}).get('key_id', row.get('key_id', ''))
    value['impact'] = row.get('preview', row.get('impact', {}))
    return value


@storage
def _save_state(vault, row, status, result=None, error_code=''):
    from . import ai_review
    row = ai_review.set_state(vault, row['operation_id'], status, result=result, error_code=error_code)
    from . import runtime_records
    runtime_records.safely(runtime_records.operation_status, vault, row['operation_id'], status, error_code)
    return row


@storage
def create(vault, key_id, tool, identity, digest, payload, impact, snapshot, web_url):
    from . import ai_review
    row = ai_review.create(vault, 'mcp', tool, identity, payload, actor={'key_id': key_id},
                           preview=impact, snapshot=snapshot, pending=True, digest=digest,
                           expires_at=time.time()+TTL)
    return _public(row, web_url)


def _import_legacy(vault, row):
    """旧记录只接入可验证字段；审批权威统一到新库，绝不执行旧批准。"""
    if not row:
        return None
    from . import ai_review
    imported = ai_review.create(vault, 'mcp', row['tool'], row['identity'], row['payload'],
        actor={'key_id': row['key_id']}, preview=row['impact'], snapshot=row['snapshot'],
        pending=False, digest=row['digest'],
        operation_id=row['operation_id'], expires_at=row['expires_at'])
    if imported['status'] == 'running':
        historical = row['status'] if row['status'] in TERMINAL else 'interrupted'
        imported = _save_state(vault, imported, historical, row['result'],
                               row['error_code'] or ('interrupted' if historical == 'interrupted' else ''))
    with closing(ai_review._connect(vault, True)) as db:
        db.execute('UPDATE operations SET history_readonly=1,history_incomplete=1 WHERE operation_id=?',
                   (row['operation_id'],))
        db.commit()
    return ai_review.get(vault, row['operation_id'])


def _legacy_view(vault, row):
    """只读兼容查询不导入旧库；迁移仅在启动或审批写入口进行。"""
    if not row:
        return None
    status = row['status'] if row['status'] in TERMINAL else 'interrupted'
    return {**row, 'status': status, 'source': 'mcp', 'actor': {'key_id': row['key_id']},
            'preview': row['impact'], 'revision': 1, 'effective_digest': row['digest'],
            'editable_fields': [], 'commits': [], 'updated_at': row['created_at'],
            'generation': generation(vault), 'history_incomplete': True, 'history_readonly': True}


@storage
def _recover(vault, row, persist=False):
    # 已合法提交的领域回执优先，重启/响应丢失后不因随后吊销而误报未执行。
    receipt = _receipt(vault, row) if row['status'] in ('approved', 'applying', 'failed', 'interrupted', 'partial') else None
    if receipt:
        expected = row['effective_digest'] if row['tool'] in ('propose_question_update', 'propose_label_plan') else row['digest']
        if receipt['digest'] != expected:
            return {**row, 'status': 'conflict', 'error_code': 'request_conflict'}
        if persist:
            from . import ai_review
            if hasattr(ai_review, 'reconcile'):
                return ai_review.reconcile(vault, row['operation_id'], receipt['result'])
            if row['status'] in ('approved', 'applying'):
                return _save_state(vault, row, 'applied', receipt['result'])
        status = 'unchanged' if receipt['result'].get('no_op') or receipt['result'].get('wrote') is False else 'applied'
        return {**row, 'status': status, 'result': receipt['result'], 'error_code': ''}
    if row['status'] == 'pending_confirmation' and row.get('expires_at') and time.time() >= row['expires_at']:
        if persist:
            return _save_state(vault, row, 'expired')
        return {**row, 'status': 'expired'}
    # 查询只能核实已有回执，不能执行已批准但无提交证明的操作。
    return row


def _receipt(vault, row):
    if row['tool'] == 'propose_label_plan':
        from .label_plan_journal import receipt, public_result
        saved = receipt(vault, row['operation_id'], row['effective_digest'])
        return {'digest': row['effective_digest'], 'result': public_result(saved)} if saved else None
    if row['tool'] == 'propose_question_update':
        from .question_update import recover_receipt
        result = recover_receipt(vault, row)
        return {'digest': row['effective_digest'], 'result': result} if result else None
    if row['tool'] == 'create_review_session':
        from .ledger import ledger_path
        target = ledger_path(vault)
        if not os.path.exists(target):
            return None
        with closing(open_sqlite(vault, Path(target).as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            saved = db.execute('SELECT result_json FROM op_results WHERE op_id=?',
                               ('mcp:session:'+row['identity'],)).fetchone()
            if saved:
                from .session_operations import _session_view
                receipt = json.loads(saved['result_json'])
                return {'digest': receipt['digest'], 'result': _session_view(vault, db, receipt, True)}
        return None
    from . import mcp_board
    if row['tool'] in mcp_board.SCOPES:
        identity = (row.get('actor') or {}).get('native_identity', row['identity'])
        return boards.load_boards(vault)['mcp_receipts'].get(identity)
    return None


def session_preview(vault, items):
    """正式调度只预览稳定题目身份和占用，不预留或创建 Session。"""
    from .session_operations import _normalize_items
    from .ledger import connect
    from .data_repository import resolve_question
    from .mcp.common import fingerprint
    normalized = _normalize_items(items)
    preview, snapshot = [], []
    with connect(vault) as db:
        occupied = set()
        from .sessions import _entries, _decode_session_items
        for session in db.execute("SELECT session_id,items_json FROM session_projection WHERE status='active' AND retracted=0"):
            questions = {}
            for saved in _decode_session_items(session['items_json']):
                qid = saved.get('question_id')
                if qid:
                    question = resolve_question(vault, question_id=qid, include_archived=True, db=db)
                    if question:
                        questions[qid] = question
            entries = _entries(vault, {'Session_ID': session['session_id'], 'UIDs': session['items_json']}, questions, set())
            occupied.update(e['question_id'] for e in entries if e['availability'] == 'active')
        for item in normalized:
            row = resolve_question(vault, question_id=item['question_id'], include_archived=True, db=db)
            if not row:
                raise RequestError('not_found', '所选题目不存在')
            if row['archived'] or row['suspended'] or row['question_id'] in occupied:
                raise RequestError('state_conflict', '所选题目已归档、停用或在进行中的计划内')
            selected = {key: row[key] for key in ('question_id', 'uid', 'subject', 'category', 'content_hash')}
            selected['source'] = item['source']
            preview.append(selected)
            snapshot.append(selected)
    return normalized, {'items': preview, 'count': len(preview), 'reasons': ['创建正式复习调度']}, fingerprint(snapshot)


def _session_auth(vault, key_id):
    from .mcp.keys import active_key
    row = active_key(vault, key_id)
    if not row or not {'omrs:read', 'session:create'}.issubset(row['scopes']):
        raise PermissionError('MCP 密钥已失效或缺少调度创建权限')


def _deadline(row):
    if row.get('expires_at') is not None and time.time() >= row['expires_at']:
        from .ai_review import ReviewError
        raise ReviewError('expired', '提案已过期，未执行写入', 409)


def _apply_session(vault, row):
    from .session_operations import create_mcp_session
    key_id = row['actor']['key_id']
    def auth():
        _session_auth(vault, key_id)
        _deadline(row)
    try:
        auth()
        _, _, snapshot = session_preview(vault, row['payload']['items'])
        if snapshot != row['snapshot']:
            return _save_state(vault, row, 'conflict', error_code='revision_conflict')
        row = _save_state(vault, row, 'approved')
        row = _save_state(vault, row, 'applying')
        result = create_mcp_session(vault, row['payload']['items'], key_id, row['actor']['request_id'], auth)
        return _finish_applied(vault, row, result)
    except (PermissionError, RequestError, ValueError) as exc:
        receipt = _receipt(vault, row)
        if receipt and receipt['digest'] == row['digest']:
            return _finish_applied(vault, row, receipt['result'])
        code = 'forbidden' if isinstance(exc, PermissionError) else getattr(exc, 'code', 'invalid_request')
        return _save_state(vault, row, 'expired' if code == 'expired' else 'conflict', error_code=code)


@storage
def create_session(vault, items, key_id, request_id, web_url, authorize):
    """保留旧请求回执，只有尚未创建的正式计划才申请审核。"""
    from . import ai_review
    from .mcp.common import request_identity
    from .session_operations import _normalize_items
    normalized = _normalize_items(items)
    identity, digest = request_identity(key_id, 'create_review_session', request_id, normalized)
    with locking.write_lock():
        authorize()
        existing = by_identity(vault, identity)
        receipt = _receipt(vault, {'tool': 'create_review_session', 'identity': identity})
        if receipt:
            if receipt['digest'] != digest:
                raise RequestError('request_conflict', '同一 request_id 的内容不同')
            authorize()
            return receipt['result']
        if existing:
            if existing['digest'] != digest:
                raise RequestError('request_conflict', '同一 request_id 的内容不同')
            return {**get(vault, existing['operation_id'], key_id, web_url), 'reused': True}
        normalized, preview, snapshot = session_preview(vault, normalized)
        authorize()
        row = ai_review.create(vault, 'mcp', 'create_review_session', identity, {'items': normalized},
            actor={'key_id': key_id, 'request_id': request_id}, preview=preview, snapshot=snapshot,
            pending=True, digest=digest, expires_at=time.time()+TTL)
        authorize()
        return _public(row, web_url)


@storage
def get(vault, operation_id, key_id=None, web_url=''):
    if not isinstance(operation_id, str) or not re.fullmatch(r'op_[0-9a-f]{32}', operation_id):
        raise RequestError('not_found', '确认操作不存在')
    with locking.write_lock():
        from . import ai_review
        try:
            row = ai_review.get(vault, operation_id, key_id=key_id)
        except ai_review.ReviewError as exc:
            if exc.code != 'not_found':
                raise
            row = None
        if not row:
            row = _legacy_view(vault, _read(vault, 'operation_id', operation_id))
        if not row or (key_id is not None and (row.get('actor') or {}).get('key_id') != key_id):
            raise RequestError('not_found', '确认操作不存在')
        return _public(_recover(vault, row), web_url)


@storage
def review_decide(vault, row, decision):
    from . import ai_review, mcp_board
    if decision == 'reject':
        return _save_state(vault, row, 'rejected')
    key_id = (row.get('actor') or {}).get('key_id', '')
    if row['tool'] == 'propose_label_plan':
        from .label_plan_review import apply_review, verify_snapshot, authorize_source
        try:
            _deadline(row)
            authorize_source(vault, 'mcp', key_id, row['payload'])
            verify_snapshot(vault, row)
            row = _save_state(vault, row, 'approved')
            row = _save_state(vault, row, 'applying')
            return _finish_applied(vault, row, apply_review(vault, row))
        except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
            saved = _receipt(vault, row)
            if saved: return _finish_applied(vault, row, saved['result'])
            code = getattr(exc, 'code', 'internal_error')
            return _save_state(vault, row, 'expired' if code == 'expired' else 'conflict', error_code=code)
    if row['tool'] == 'propose_question_update':
        from .mcp.question_write import apply_review, prepare_review
        from .mcp.keys import active_key
        try:
            _deadline(row)
            key = active_key(vault, key_id)
            if not key or not {'omrs:read', 'question:propose'}.issubset(key['scopes']):
                raise PermissionError('MCP 密钥已失效或缺少题目提案权限')
            _, _, snapshot = prepare_review(vault, row, {})
            if snapshot != row['snapshot']:
                return _save_state(vault, row, 'conflict', error_code='content_conflict')
            row = _save_state(vault, row, 'approved')
            row = _save_state(vault, row, 'applying')
            _deadline(row)
            result = apply_review(vault, row)
            return _finish_applied(vault, row, result)
        except (PermissionError, RequestError, ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
            receipt = _receipt(vault, row)
            if receipt and receipt['digest'] == row['effective_digest']:
                return _finish_applied(vault, row, receipt['result'])
            code = 'forbidden' if isinstance(exc, PermissionError) else getattr(exc, 'code', 'internal_error')
            return _save_state(vault, row, 'expired' if code == 'expired' else 'conflict', error_code=code)
    if row['tool'] == 'create_review_session':
        return _apply_session(vault, row)
    if row['tool'] not in mcp_board.SCOPES:
        raise ai_review.ReviewError('unknown_tool', '审核操作类型不支持')
    def auth():
        mcp_board.authorize(vault, key_id, row['tool'])
        _deadline(row)
    try:
        auth()
        _, _, snapshot = mcp_board.preview(vault, row['tool'], row['payload'], auth)
        if snapshot != row['snapshot']:
            return _save_state(vault, row, 'conflict', error_code='revision_conflict')
        # applying 持久化后才动领域；跨文件崩溃以同一原子回执恢复。
        row = _save_state(vault, row, 'approved')
        row = _save_state(vault, row, 'applying')
        result = boards.transaction(vault, lambda: mcp_board.dispatch(vault, row['tool'], row['payload']),
                                    row['identity'], row['digest'], auth, protect_paper=True)
        return _finish_applied(vault, row, result)
    except (PermissionError, boards.BoardConflict, RequestError, ValueError) as exc:
        receipt = boards.load_boards(vault)['mcp_receipts'].get(row['identity']) if row['status'] == 'applying' else None
        if receipt and receipt['digest'] == row['digest']:
            return _finish_applied(vault, row, receipt['result'])
        code = 'forbidden' if isinstance(exc, PermissionError) else getattr(exc, 'code', 'invalid_request')
        return _save_state(vault, row, 'expired' if code == 'expired' else 'conflict', error_code=code)


def _finish_applied(vault, row, result):
    """领域已提交后不能因为辅助记录失败诱导重复业务写入。"""
    status = 'partial' if result.get('failed') else 'unchanged' if result.get('no_op') or result.get('wrote') is False else 'applied'
    try:
        return _save_state(vault, row, status, result)
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).error('审核记录终态写入失败，保留原生回执待核对')
        return {**row, 'status': status, 'result': result, 'error_code': ''}


@storage
def decide(vault, operation_id, decision, expected_revision=None, reviewer=None):
    if not isinstance(operation_id, str) or not re.fullmatch(r'op_[0-9a-f]{32}', operation_id):
        raise RequestError('not_found', '确认操作不存在')
    if decision not in ('confirm', 'reject'):
        raise ValueError('decision 必须是 confirm 或 reject')
    from . import ai_review
    with locking.write_lock():
        try:
            row = ai_review.get(vault, operation_id)
        except ai_review.ReviewError as exc:
            if exc.code != 'not_found':
                raise
            row = _import_legacy(vault, _read(vault, 'operation_id', operation_id))
            if not row:
                raise RequestError('not_found', '确认操作不存在')
        row = _recover(vault, row, persist=True)
        if expected_revision is None:
            if row['revision'] != 1:
                raise RequestError('revision_conflict', '提案已修订，请在审核中心核对当前版本')
            expected_revision = 1
        elif type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('expected_revision 必须是正整数')
        if expected_revision != row['revision']:
            raise RequestError('revision_conflict', '提案版本已变化，请重新查看')
        if row['status'] != 'pending_confirmation':
            return _public(row)
        result = ai_review.decide(vault, operation_id, expected_revision,
            'approve' if decision == 'confirm' else 'reject', reviewer=reviewer)
        return _public(result)


@storage
def refresh(vault):
    """读取历史时仅核对旧回执，绝不重放业务操作。"""
    with locking.write_lock():
        if os.path.exists(path(vault)):
            with closing(_connect(vault)) as db:
                rows = [_decode(row) for row in db.execute('SELECT * FROM operations')]
            for row in rows:
                _import_legacy(vault, row)
        from . import ai_review
        if os.path.exists(ai_review.path(vault)):
            with closing(ai_review._connect(vault)) as db:
                rows = [ai_review._decode(row) for row in db.execute("SELECT * FROM operations WHERE source='mcp'")]
            for row in rows:
                _recover(vault, row, persist=True)


@storage
def invalidate(vault):
    """整库恢复使旧审批失效；原生回执仍保留为业务事实。"""
    if os.path.exists(path(vault)):
        with locking.write_lock(), closing(_connect(vault, True)) as db:
            db.execute("UPDATE operations SET status='conflict',error_code='vault_changed' "
                       "WHERE status IN ('pending_confirmation','approved','applying')")
            db.commit()
    from . import ai_review
    ai_review.invalidate(vault)
