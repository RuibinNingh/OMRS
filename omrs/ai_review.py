"""AI 业务写操作的统一审批权威；查询不触发领域执行。

磁盘锁顺序为生命周期租约、全局写锁、确认对象锁、SQLite。
完整提案独立于脱敏运行记录，已发生的业务事实以原生回执为准。
"""
import datetime
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
import contextvars
from contextlib import closing
from pathlib import Path

from .common import omrs_data_dir
from . import locking
from .vault_lifecycle import storage, open_sqlite, generation

TTL = 600
ACTIVE = ('running', 'pending_confirmation', 'approved', 'applying')
TERMINAL = ('applied', 'rejected', 'expired', 'conflict', 'interrupted', 'failed', 'partial', 'unchanged', 'cancelled')
AUTO_AGENT = {'create_draft', 'update_draft', 'create_practice_card'}
CONFIRM_AGENT = {'create_review_session', 'set_question_labels', 'update_question_section',
                 'set_knowledge_points', 'move_question', 'suspend_question', 'resume_question',
                 'record_feedback', 'commit_draft', 'create_category', 'propose_label_plan'}
BOARD_TOOLS = {'create_board', 'update_board', 'duplicate_board', 'delete_board', 'add_board_items',
               'remove_board_items', 'reorder_board_items', 'update_board_layout', 'update_board_item',
               'create_board_folder', 'update_board_folder', 'delete_board_folder', 'move_board'}
AUTO_MCP = {'create_draft', 'update_draft', 'create_report'}
WRITE_MCP = AUTO_MCP | BOARD_TOOLS | {'create_review_session', 'propose_question_update', 'propose_label_plan'}
LABELS = {
    'propose_label_plan': '整批整理标记',
    'create_draft': '创建待审核草稿', 'update_draft': '修订待审核草稿',
    'create_practice_card': '创建聊天练习卡', 'create_review_session': '创建正式复习计划',
    'set_question_labels': '修改题目标记', 'update_question_section': '修改题目正文',
    'set_knowledge_points': '修改知识点', 'move_question': '移动题目',
    'suspend_question': '停用题目', 'resume_question': '恢复题目', 'record_feedback': '记录学习反馈',
    'commit_draft': '审核草稿入库', 'create_category': '创建分类', 'create_report': '保存分析报告',
    'propose_question_update': '修改正式题目', 'create_board': '创建展示板',
    'update_board': '编辑展示板', 'duplicate_board': '复制展示板', 'delete_board': '删除展示板',
    'add_board_items': '加入板内题目', 'remove_board_items': '移出板内题目',
    'reorder_board_items': '排序板内题目', 'update_board_layout': '调整展示板版式',
    'update_board_item': '调整题目留白与置顶', 'create_board_folder': '创建展示板文件夹',
    'update_board_folder': '编辑展示板文件夹', 'delete_board_folder': '删除展示板文件夹',
    'move_board': '移动展示板',
}
_JSON_FIELDS = ('payload', 'actor', 'preview', 'snapshot', 'editable_fields', 'result', 'commits')
_DECIDER = contextvars.ContextVar('ai_review_decider', default={})
_AUTO_INTENT = contextvars.ContextVar('ai_review_auto_intent', default=None)
TYPES = {'propose_label_plan': 'label_plan', **{tool: 'board' for tool in BOARD_TOOLS},
         **{tool: 'draft' for tool in ('create_draft', 'update_draft', 'commit_draft')},
         **{tool: 'question' for tool in ('propose_question_update', 'set_question_labels',
            'update_question_section', 'set_knowledge_points', 'move_question', 'suspend_question', 'resume_question')},
         'create_review_session': 'session', 'record_feedback': 'feedback',
         'create_category': 'category', 'create_report': 'report', 'create_practice_card': 'practice'}


class ReviewError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def fingerprint(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def save_auto_receipt(db, result):
    """自动业务写的原生事务同时关联审核意图；失败结果不能借用旧请求回执。"""
    intent = _AUTO_INTENT.get()
    if intent is None:
        return
    db.execute('CREATE TABLE IF NOT EXISTS ai_review_receipts (operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, result_json TEXT NOT NULL)')
    db.execute('INSERT INTO ai_review_receipts VALUES(?,?,?)',
               (intent['operation_id'], intent['effective_digest'], _json(result)))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def classify(source, tool):
    if source == 'agent':
        return 'auto' if tool in AUTO_AGENT else 'confirm' if tool in CONFIRM_AGENT else None
    if source == 'mcp':
        return 'auto' if tool in AUTO_MCP else 'domain' if tool in BOARD_TOOLS else 'confirm' if tool in WRITE_MCP else None
    return None


@storage
def path(vault):
    return os.path.join(omrs_data_dir(vault), 'ai_review.db')


@storage
def _connect(vault, write=False):
    target = path(vault)
    if os.path.islink(target):
        raise ReviewError('unsafe_path', '审核库不允许符号链接')
    if not write:
        db = open_sqlite(vault, Path(target).as_uri() + '?mode=ro', uri=True, timeout=5)
    else:
        fd = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(target, 0o600)
        db = open_sqlite(vault, target, timeout=5)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL, tool TEXT NOT NULL, key_id TEXT NOT NULL DEFAULT '',
                    digest TEXT NOT NULL, effective_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL, actor_json TEXT NOT NULL, preview_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL, editable_fields_json TEXT NOT NULL,
                    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL, expires_at REAL, updated_at REAL NOT NULL,
                    generation INTEGER NOT NULL, result_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT NOT NULL DEFAULT '', commits_json TEXT NOT NULL DEFAULT '[]',
                    history_incomplete INTEGER NOT NULL DEFAULT 0,
                    history_readonly INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS operations_page ON operations(created_at DESC, operation_id);
                CREATE INDEX IF NOT EXISTS operations_pending ON operations(status, expires_at);
                CREATE INDEX IF NOT EXISTS operations_source ON operations(source,tool,created_at);
                CREATE TABLE IF NOT EXISTS revisions (
                    operation_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL, digest TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(operation_id,revision)
                );
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (
                    operation_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, decision TEXT NOT NULL,
                    decided_at REAL NOT NULL, actor_json TEXT NOT NULL
                );
            ''')
        except BaseException:
            db.close()
            raise
    db.row_factory = sqlite3.Row
    return db


def _decode(row):
    if row is None:
        return None
    row = dict(row)
    for field in _JSON_FIELDS:
        row[field] = json.loads(row.pop(field + '_json'))
    row['history_incomplete'] = bool(row['history_incomplete'])
    row['history_readonly'] = bool(row['history_readonly'])
    return row


def _effective(row):
    if row and row['status'] == 'pending_confirmation' and row.get('expires_at') is not None and time.time() >= row['expires_at']:
        return {**row, 'status': 'expired'}
    return row


@storage
def get(vault, operation_id, key_id=None):
    if not isinstance(operation_id, str) or not re.fullmatch(r'op_[0-9a-f]{32}', operation_id):
        raise ReviewError('not_found', '审核操作不存在', 404)
    if not os.path.exists(path(vault)):
        raise ReviewError('not_found', '审核操作不存在', 404)
    with closing(_connect(vault)) as db:
        row = _decode(db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone())
    if not row or (key_id is not None and row['key_id'] != key_id):
        raise ReviewError('not_found', '审核操作不存在', 404)
    return _effective(row)


@storage
def by_identity(vault, identity):
    if not os.path.exists(path(vault)):
        return None
    with closing(_connect(vault)) as db:
        return _effective(_decode(db.execute('SELECT * FROM operations WHERE identity=?', (identity,)).fetchone()))


@storage
def verify_question_write(vault, review):
    """在题目实际落盘前重查唯一批准、原来源权限与运行停止状态。"""
    row = get(vault, review['operation_id'])
    if row['history_readonly'] or row['status'] != 'applying':
        raise ReviewError('state_conflict', '这次题目修改没有可执行的批准', 409)
    for field in ('identity', 'source', 'tool', 'key_id', 'actor', 'revision', 'digest', 'effective_digest',
                  'payload', 'snapshot', 'editable_fields', 'generation', 'expires_at'):
        if row.get(field) != review.get(field):
            raise ReviewError('revision_conflict', '批准的题目提案或来源已变化', 409)
    if row['effective_digest'] != fingerprint(row['payload']):
        raise ReviewError('revision_conflict', '批准的有效题目摘要不匹配', 409)
    if row['generation'] != generation(vault):
        raise ReviewError('content_conflict', '题库世代已变化，旧批准不能写入', 409)
    if row.get('expires_at') is None or time.time() >= row['expires_at']:
        raise ReviewError('expired', '题目修改确认已过期，未执行写入', 409)
    if row['source'] == 'mcp' and row['tool'] == 'propose_label_plan':
        from .label_plan_review import authorize_source
        authorize_source(vault, 'mcp', row['key_id'], row['payload'])
    elif row['source'] == 'mcp' and row['tool'] == 'propose_question_update':
        from .mcp.keys import active_key
        key = active_key(vault, row['actor'].get('key_id', ''))
        if not key or not {'omrs:read', 'question:propose'}.issubset(key['scopes']):
            raise ReviewError('forbidden', 'MCP 密钥已失效或缺少题目提案权限', 403)
    elif row['source'] == 'agent' and row['tool'] in ('update_question_section', 'set_knowledge_points', 'propose_label_plan'):
        from .actor import current_agent
        from .agent.runtime import _RUNTIMES
        rt = _RUNTIMES.get(os.path.abspath(vault))
        run = rt.runs.get(row['actor'].get('run_id')) if rt else None
        actor = current_agent()
        if (not run or run.done or run.closing or run.abort.is_set() or
                run.conv_id != row['actor'].get('conversation_id') or not actor or
                any(actor.stamp().get(key) != row['actor'].get(key)
                    for key in ('conversation_id', 'run_id', 'tool_call_id'))):
            raise ReviewError('interrupted', '原助手运行已结束或中止，未执行写入', 409)
    else:
        raise ReviewError('forbidden', '这次操作没有正式题目写权限', 403)
    return row


@storage
def create(vault, source, tool, identity, payload, actor=None, preview=None, snapshot=None,
           pending=False, digest=None, operation_id=None, editable_fields=None, expires_at=None):
    if classify(source, tool) is None:
        raise ReviewError('unknown_tool', '该工具没有业务写操作分类，已拒绝执行')
    digest = digest or fingerprint(payload)
    actor = dict(actor or {})
    for forbidden in ('token', 'secret', 'pin', 'cookie', 'authorization'):
        if forbidden in actor:
            raise ReviewError('invalid_request', '审核来源包含不允许保存的凭据')
    now = time.time()
    operation_id = operation_id or 'op_' + uuid.uuid4().hex
    if not re.fullmatch(r'op_[0-9a-f]{32}', operation_id):
        raise ReviewError('invalid_request', '审核操作编号不正确')
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        previous = _decode(db.execute('SELECT * FROM operations WHERE identity=?', (identity,)).fetchone())
        if previous:
            if previous['digest'] != digest:
                raise ReviewError('request_conflict', '同一请求编号的内容不同', 409)
            return _effective(previous)
        values = (operation_id, identity, source, tool, actor.get('key_id', ''), digest, fingerprint(payload),
                  _json(payload), _json(actor), _json(preview or {}), _json(snapshot or {}),
                  _json(editable_fields or []), 'pending_confirmation' if pending else 'running', 1, now,
                  (now + TTL if expires_at is None else expires_at) if pending else expires_at,
                  now, generation(vault))
        db.execute('INSERT INTO operations(operation_id,identity,source,tool,key_id,digest,effective_digest,'
                   'payload_json,actor_json,preview_json,snapshot_json,editable_fields_json,status,revision,'
                   'created_at,expires_at,updated_at,generation) VALUES(' + ','.join('?' for _ in values) + ')', values)
        db.commit()
    return get(vault, operation_id)


@storage
def prepare(vault, operation_id, payload=None, preview=None, snapshot=None, pending=True,
            editable_fields=None, expires_at=None):
    """把领域的预登记意图变成待审核；不会重新打开已处理操作。"""
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        row = _decode(db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone())
        if not row:
            raise ReviewError('not_found', '审核操作不存在', 404)
        if row['status'] != 'running':
            return _effective(row)
        effective = row['payload'] if payload is None else payload
        db.execute('UPDATE operations SET payload_json=?,effective_digest=?,preview_json=?,snapshot_json=?,'
                   'editable_fields_json=?,status=?,expires_at=?,updated_at=? WHERE operation_id=? AND status=?',
                   (_json(effective), fingerprint(effective), _json(row['preview'] if preview is None else preview),
                    _json(row['snapshot'] if snapshot is None else snapshot),
                    _json(row['editable_fields'] if editable_fields is None else editable_fields),
                    'pending_confirmation' if pending else 'running',
                    expires_at if expires_at is not None else time.time() + TTL if pending else row['expires_at'],
                    time.time(), operation_id, 'running'))
        db.commit()
    return get(vault, operation_id)


@storage
def set_state(vault, operation_id, status, result=None, error_code='', commits=None,
              expected_status=None, expected_revision=None):
    if status not in ACTIVE + TERMINAL:
        raise ReviewError('invalid_request', '审核状态不正确')
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        db.execute('BEGIN IMMEDIATE')
        row = _decode(db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone())
        if not row:
            raise ReviewError('not_found', '审核操作不存在', 404)
        if expected_revision is not None and row['revision'] != expected_revision:
            raise ReviewError('revision_conflict', '提案版本已变化，请重新查看', 409)
        if expected_status is not None and row['status'] not in ((expected_status,) if isinstance(expected_status, str) else expected_status):
            raise ReviewError('state_conflict', '操作已处理或状态已变化', 409)
        if row['status'] in TERMINAL and status != row['status']:
            raise ReviewError('state_conflict', '已结束的审核操作不能重新执行', 409)
        if row['status'] == 'pending_confirmation' and status in ('approved', 'rejected'):
            db.execute('INSERT INTO decisions VALUES(?,?,?,?,?)', (operation_id, row['revision'],
                       'approve' if status == 'approved' else 'reject', time.time(), _json(_DECIDER.get())))
        db.execute('UPDATE operations SET status=?,result_json=?,error_code=?,commits_json=?,updated_at=? WHERE operation_id=?',
                   (status, _json(row['result'] if result is None else result), error_code,
                    _json(row['commits'] if commits is None else commits), time.time(), operation_id))
        db.commit()
    return get(vault, operation_id)


@storage
def revise(vault, operation_id, expected_revision, payload, preview, editable_fields=None):
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        db.execute('BEGIN IMMEDIATE')
        row = _decode(db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone())
        if not row or row['history_readonly']:
            raise ReviewError('not_found', '待审核操作不存在', 404)
        if row['revision'] != expected_revision:
            raise ReviewError('revision_conflict', '提案版本已变化，请重新查看', 409)
        if _effective(row)['status'] != 'pending_confirmation':
            raise ReviewError('state_conflict', '操作已批准、结束或到期，不能修改', 409)
        db.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',
                   (operation_id, row['revision'], _json(row['payload']), row['effective_digest'], time.time()))
        fields = row['editable_fields'] if editable_fields is None else editable_fields
        if not set(fields).issubset(row['editable_fields']):
            raise ReviewError('forbidden', '不能扩大提案的可编辑范围', 403)
        db.execute('UPDATE operations SET payload_json=?,preview_json=?,effective_digest=?,revision=revision+1,'
                   'updated_at=? WHERE operation_id=?',
                   (_json(payload), _json(preview), fingerprint(payload), time.time(), operation_id))
        db.commit()
    return get(vault, operation_id)


def public(row, web_url=''):
    value = {key: row[key] for key in ('operation_id', 'source', 'tool', 'key_id', 'status', 'revision',
             'payload', 'actor', 'preview', 'editable_fields', 'result', 'error_code', 'commits',
             'history_incomplete', 'history_readonly')}
    value.update(id=row['operation_id'], kind='operation', type=TYPES.get(row['tool'], ''),
                 label=LABELS.get(row['tool'], row['tool']), impact=row['preview'])
    for key in ('created_at', 'updated_at', 'expires_at'):
        stamp = row.get(key)
        value[key] = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat() if stamp is not None else None
    if web_url:
        from .mcp_operations import web_origin
        value['confirmation_url'] = web_origin(web_url) + '/#/ai-review?operation=' + row['operation_id']
    return value


@storage
def decide(vault, operation_id, expected_revision, decision, reviewer=None):
    if decision not in ('approve', 'reject'):
        raise ReviewError('invalid_request', 'decision 只能是 approve 或 reject')
    if type(expected_revision) is not int or expected_revision < 1:
        raise ReviewError('invalid_request', '必须提供有效的提案版本')
    with locking.write_lock():
        row = get(vault, operation_id)
        if row['history_readonly']:
            raise ReviewError('state_conflict', '历史操作只读，不能重新批准', 409)
        if row['revision'] != expected_revision:
            raise ReviewError('revision_conflict', '提案版本已变化，请重新查看', 409)
        if row['status'] in TERMINAL:
            return row
        if row['generation'] != generation(vault):
            return set_state(vault, operation_id, 'cancelled', error_code='vault_changed')
        if row['status'] != 'pending_confirmation':
            return row
        token = _DECIDER.set(dict(reviewer or {}))
        try:
            if row['source'] == 'agent':
                from .agent import runtime
                return runtime.review_decide(vault, row, decision)
            from . import mcp_operations
            return mcp_operations.review_decide(vault, row, decision)
        finally:
            _DECIDER.reset(token)


@storage
def update(vault, operation_id, expected_revision, patch):
    if not isinstance(patch, dict) or not patch:
        raise ReviewError('invalid_request', '修订必须包含非空字段补丁')
    with locking.write_lock():
        row = get(vault, operation_id)
        if row['revision'] != expected_revision:
            raise ReviewError('revision_conflict', '提案版本已变化，请重新查看', 409)
        if row['history_readonly'] or row['status'] != 'pending_confirmation':
            raise ReviewError('state_conflict', '操作已批准、结束或到期，不能修改', 409)
        if row['generation'] != generation(vault):
            raise ReviewError('vault_changed', '题库已恢复，不能修改旧提案', 409)
        if not set(patch).issubset(row['editable_fields']):
            raise ReviewError('forbidden', '包含本提案不允许修改的字段', 403)
        if row['source'] == 'agent':
            from .agent import runtime
            return runtime.review_update(vault, row, patch, expected_revision)
        if row['tool'] == 'propose_label_plan':
            from .label_plan_review import prepare_revision
            prepared = prepare_revision(vault, row, patch)
            return revise(vault, operation_id, expected_revision, prepared['payload'], prepared['preview'])
        if row['tool'] != 'propose_question_update':
            raise ReviewError('forbidden', '此操作只允许批准或拒绝', 403)
        from .mcp import question_write
        payload, preview, snapshot = question_write.prepare_review(vault, row, patch)
        if snapshot != row['snapshot']:
            raise ReviewError('content_conflict', '题目已变化，请重新提交提案', 409)
        return revise(vault, operation_id, expected_revision, payload, preview)


@storage
def invalidate(vault, reason='vault_changed', source=None):
    """恢复与普通重启分别调用；这里只废止审批，不执行任何业务补偿。"""
    if not os.path.exists(path(vault)):
        return 0
    where = "status IN ('running','pending_confirmation','approved','applying')"
    args = [reason, time.time()]
    if source:
        where += ' AND source=?'
        args.append(source)
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        cursor = db.execute('UPDATE operations SET status=\'interrupted\',error_code=?,updated_at=? WHERE '+where, args)
        db.commit()
        return cursor.rowcount



def _readonly(vault, target):
    if os.path.islink(target):
        raise ReviewError('unsafe_path', '审核来源库不允许符号链接')
    db = open_sqlite(vault, Path(target).as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def _draft_path(vault):
    return os.path.join(omrs_data_dir(vault), 'drafts', 'drafts.db')


def _stamp(value):
    if type(value) in (int, float):
        return float(value)
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=datetime.timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    except (TypeError, ValueError):
        return None


def _options(options):
    options = dict(options or {})
    cursor = options.get('cursor')
    if cursor is not None:
        if not isinstance(cursor, str) or not re.fullmatch(r'\d+', cursor):
            raise ReviewError('invalid_request', 'cursor 必须是分页返回的非负偏移字符串')
        if options.get('offset') is not None and str(options['offset']) != cursor:
            raise ReviewError('invalid_request', 'cursor 与 offset 不能指向不同页面')
        options['offset'] = cursor
    try:
        limit, offset = int(options.get('limit') or 30), int(options.get('offset') or 0)
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ReviewError('invalid_request', 'limit 必须为 1–100，offset 必须非负') from None
    if options.get('view', 'pending') not in ('pending', 'records'):
        raise ReviewError('invalid_request', '审核视图不正确')
    if options.get('source', '') not in ('', 'agent', 'mcp', 'legacy') or options.get('type', '') not in ('', *set(TYPES.values())):
        raise ReviewError('invalid_request', '来源或操作类型不正确')
    status = options.get('status', '')
    if status and status not in (*ACTIVE, *TERMINAL, 'failure', 'done', 'discarded', 'review', 'cropping'):
        raise ReviewError('invalid_request', '状态筛选不正确')
    for key in ('from', 'to'):
        if options.get(key) and _stamp(options[key]) is None:
            raise ReviewError('invalid_request', '时间必须是 ISO-8601 时间或日期')
    if options.get('from') and options.get('to') and _stamp(options['from']) >= _stamp(options['to']):
        raise ReviewError('invalid_request', '开始时间必须早于结束时间')
    return options, limit, offset


def _mcp_receipt_view(vault, row):
    """只用精确原生回执展示已提交事实，底层审批状态与权限保持原值。"""
    if row['source'] != 'mcp' or row['status'] not in ('running', 'approved', 'applying', 'failed', 'interrupted', 'partial'):
        return row
    result = None
    if row['tool'] in AUTO_MCP:
        result = _auto_receipt(vault, row)
    else:
        from .mcp_operations import _receipt
        receipt = _receipt(vault, row)
        if receipt:
            expected = row['effective_digest'] if row['tool'] == 'propose_question_update' else row['digest']
            if receipt['digest'] != expected:
                return {**row, 'status': 'conflict', 'error_code': 'request_conflict'}
            result = receipt['result']
    if result is None:
        return row
    status = 'partial' if result.get('failed') else 'unchanged' if result.get('no_op') or result.get('wrote') is False else 'applied'
    return {**row, 'status': status, 'result': result, 'error_code': ''}


def _mcp_active_views(vault, db):
    """只核对未终结 MCP 意图；不扫描已结束历史，也不读取提案正文。"""
    views = {}
    for raw in db.execute("SELECT operation_id,identity,source,tool,digest,effective_digest,actor_json,snapshot_json,status "
                          "FROM operations WHERE source='mcp' AND status IN ('running','approved','applying')"):
        row = dict(raw)
        row['actor'] = json.loads(row.pop('actor_json'))
        row['snapshot'] = json.loads(row.pop('snapshot_json'))
        view = _mcp_receipt_view(vault, row)
        if view['status'] != row['status']:
            views[row['operation_id']] = view['status']
    return views


def _operation_summaries(vault, options, limit, offset):
    if not os.path.exists(path(vault)):
        return [], 0, set()
    now = time.time()
    clauses, args = [], []
    # 查询只计算过期视图；不改审批、更不执行业务恢复。
    effective = ("COALESCE((SELECT status FROM review_view_states WHERE operation_id=operations.operation_id),"
                 "CASE WHEN status='pending_confirmation' AND expires_at IS NOT NULL AND expires_at<=? THEN 'expired' ELSE status END)")
    if options.get('view', 'pending') == 'pending':
        clauses.append("status='pending_confirmation' AND history_readonly=0 AND (expires_at IS NULL OR expires_at>?)")
        args.append(now)
        # 同一草稿只产生一份待办；记录视图仍保存每次真实调用。
        clauses.append("(tool!='commit_draft' OR json_extract(payload_json,'$.draft_id') IS NULL OR NOT EXISTS("
                       "SELECT 1 FROM operations newer WHERE newer.tool='commit_draft' "
                       "AND newer.status='pending_confirmation' AND newer.history_readonly=0 "
                       "AND (newer.expires_at IS NULL OR newer.expires_at>?) "
                       "AND json_extract(newer.payload_json,'$.draft_id')=json_extract(operations.payload_json,'$.draft_id') "
                       "AND (newer.created_at>operations.created_at OR newer.created_at=operations.created_at "
                       "AND newer.operation_id>operations.operation_id)))")
        args.append(now)
    if options.get('source'):
        clauses.append('source=?'); args.append(options['source'])
    if options.get('type'):
        tools = [tool for tool, type_ in TYPES.items() if type_ == options['type']]
        clauses.append('tool IN (' + ','.join('?' for _ in tools) + ')'); args.extend(tools)
    if options.get('status'):
        status = 'failed' if options['status'] == 'failure' else options['status']
        clauses.append(effective+'=?'); args.extend((now, status))
    for key, op in (('from', '>='), ('to', '<')):
        if options.get(key):
            clauses.append('created_at'+op+'?'); args.append(_stamp(options[key]))
    where = ' AND '.join(clauses) or '1'
    with closing(_connect(vault)) as db:
        # 架构判定、总数与页面共用只读快照，避免建表落在两次 schema 查询之间。
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='operations'").fetchone():
            # 首次建库先创建文件，operations 是第一张业务表；此窗口不存在审批记录。
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                raise sqlite3.DatabaseError('审核库架构不完整，缺少 operations 表')
            return [], 0, set()
        views = _mcp_active_views(vault, db) if options.get('view', 'pending') == 'records' else {}
        db.execute('CREATE TEMP TABLE review_view_states(operation_id TEXT PRIMARY KEY,status TEXT NOT NULL)')
        db.executemany('INSERT INTO review_view_states VALUES(?,?)', views.items())
        count = db.execute('SELECT COUNT(*) FROM operations WHERE '+where, args).fetchone()[0]
        # 不向列表暴露完整提案，只在受保护的详情接口取正文。
        rows = db.execute('SELECT operation_id,source,tool,key_id,status,revision,created_at,updated_at,expires_at,'
                          'history_incomplete,history_readonly FROM operations WHERE '+where+
                          ' ORDER BY created_at DESC,operation_id DESC LIMIT ?', (*args, limit+offset)).fetchall()
        represented = {r[0] for r in db.execute("SELECT json_extract(payload_json,'$.draft_id') FROM operations "
                       "WHERE tool='commit_draft' AND status='pending_confirmation' AND history_readonly=0 "
                       "AND (expires_at IS NULL OR expires_at>?)", (now,)) if r[0]}
    summaries = []
    for row in rows:
        item = dict(row)
        item['status'] = views.get(item['operation_id'], item['status'])
        item = _effective(item)
        item.update(id=item['operation_id'], kind='operation', type=TYPES.get(item['tool'], ''), label=LABELS[item['tool']])
        item['_sort'] = item['created_at']
        for key in ('created_at', 'updated_at', 'expires_at'):
            item[key] = datetime.datetime.fromtimestamp(item[key], datetime.timezone.utc).isoformat() if item[key] is not None else None
        summaries.append(item)
    return summaries, count, represented


def _draft_summaries(vault, options, limit, offset, represented):
    if options.get('type', '') not in ('', 'draft') or not os.path.exists(_draft_path(vault)):
        return [], 0
    pending = options.get('view', 'pending') == 'pending'
    clauses, args = ["status IN ('cropping','review')" if pending else '1'], []
    if options.get('status'):
        clauses.append('status=?'); args.append(options['status'])
    with closing(_readonly(vault, _draft_path(vault))) as db:
        columns = {r['name'] for r in db.execute('PRAGMA table_info(drafts)')}
        # 首次原生建库会先出现 SQLite 文件；此时还没有任何草稿，读取不代替迁移。
        if not columns:
            return [], 0
        source = 'source_channel' if 'source_channel' in columns else "'legacy'"
        if options.get('source'):
            clauses.append(source+'=?'); args.append(options['source'])
        if represented and pending:
            # 大量旧待审也按稳定草稿身份去重，避免 SQLite 参数数量限制。
            db.execute('CREATE TEMP TABLE represented(id TEXT PRIMARY KEY)')
            db.executemany('INSERT INTO represented VALUES(?)', ((id_,) for id_ in represented))
            clauses.append('id NOT IN (SELECT id FROM represented)')
        for key, op in (('from', '>='), ('to', '<')):
            if options.get(key):
                clauses.append("(julianday(created_at)-2440587.5)*86400"+op+'?'); args.append(_stamp(options[key]))
        where = ' AND '.join(clauses)
        count = db.execute('SELECT COUNT(*) FROM drafts WHERE '+where, args).fetchone()[0]
        rows = db.execute('SELECT id,status,revision,subject,category,created_at,updated_at,'+source+' AS source FROM drafts WHERE '+where+
                          ' ORDER BY created_at DESC,id DESC LIMIT ?', (*args, limit+offset)).fetchall()
    return [{**dict(row), 'kind': 'draft', 'type': 'draft', 'label': '新题草稿',
             'summary': ' / '.join(filter(None, (row['subject'], row['category']))), '_sort': _stamp(row['created_at']) or 0} for row in rows], count


@storage
def items(vault, options=None):
    options, limit, offset = _options(options)
    operations, total, represented = _operation_summaries(vault, options, limit, offset)
    drafts_, count = _draft_summaries(vault, options, limit, offset, represented)
    page = sorted(operations+drafts_, key=lambda row: (row['_sort'], row['id']), reverse=True)[offset:offset+limit]
    for row in page:
        row.pop('_sort', None)
    total += count
    more = offset + limit < total
    return {'items': page, 'total': total, 'has_more': more, 'next_offset': offset+limit if more else None,
            'next_cursor': str(offset+limit) if more else None}


@storage
def counts(vault):
    _, operations, represented = _operation_summaries(vault, {}, 1, 0)
    _, drafts_, = _draft_summaries(vault, {}, 1, 0, represented)
    return {'pending': operations+drafts_, 'drafts': drafts_, 'operations': operations}


@storage
def detail(vault, item_id):
    if isinstance(item_id, str) and item_id.startswith('op_'):
        row = _mcp_receipt_view(vault, get(vault, item_id))
        out = public(row)
        with closing(_connect(vault)) as db:
            initial = db.execute('SELECT payload_json FROM revisions WHERE operation_id=? ORDER BY revision LIMIT 1', (item_id,)).fetchone()
            decision = db.execute('SELECT * FROM decisions WHERE operation_id=?', (item_id,)).fetchone()
        out['original_payload'] = json.loads(initial[0]) if initial else row['payload']
        out['decision'] = {**dict(decision), 'actor': json.loads(decision['actor_json'])} if decision else None
        if out['decision']:
            out['decision'].pop('actor_json')
        return out
    from . import drafts
    draft = drafts.get_draft(vault, item_id, readonly=True)
    return {'id': draft['id'], 'kind': 'draft', 'type': 'draft', 'source': draft.get('source_channel', 'legacy'),
            'status': draft['status'], 'revision': draft['revision'], 'label': '新题草稿', 'draft': draft}


@storage
def reconcile(vault, operation_id, result, commits=None):
    """调用者已核验领域回执后补记既成事实；不会恢复审批或调用工具。"""
    status = 'partial' if result.get('failed') else 'unchanged' if result.get('no_op') or result.get('wrote') is False else 'applied'
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        db.execute('UPDATE operations SET status=?,result_json=?,commits_json=?,error_code=\'\',updated_at=?, '
                   'history_incomplete=MAX(history_incomplete,?) WHERE operation_id=?',
                   (status, _json(result), _json(commits or result.get('commits') or []), time.time(),
                    int(bool(result.get('history_incomplete'))), operation_id))
        db.commit()
    return get(vault, operation_id)


def _historical(vault, *, identity, source, tool, payload, actor, result, status, created_at, updated_at=None,
                commits=None, incomplete=False):
    if classify(source, tool) is None:
        return
    stamp = _stamp(created_at)
    operation_id = 'op_' + hashlib.sha256(identity.encode()).hexdigest()[:32]
    digest = fingerprint(payload)
    values = (operation_id, identity, source, tool, actor.get('key_id', ''), digest, digest,
              _json(payload), _json(actor), '{}', '{}', '[]', status, 1, stamp or 0, None,
              _stamp(updated_at) or stamp or 0, generation(vault), _json(result or {}), '', _json(commits or []),
              int(incomplete or stamp is None), 1)
    with closing(_connect(vault, True)) as db:
        db.execute('INSERT OR IGNORE INTO operations VALUES('+','.join('?' for _ in values)+')', values)
        db.commit()


def _agent_history_index(ledger):
    """只扫描一次不可变事实，在连接临时库按原运行和调用身份检索。"""
    ledger.execute("CREATE TEMP TABLE agent_history AS SELECT seq,commit_id,"
                   "json_extract(payload_json,'$._agent.run_id') AS run_id,"
                   "json_extract(payload_json,'$._agent.tool_call_id') AS call_id FROM commits "
                   "WHERE json_extract(payload_json,'$._agent.run_id') IS NOT NULL "
                   "AND json_extract(payload_json,'$._agent.tool_call_id') IS NOT NULL")
    ledger.execute('CREATE INDEX agent_history_identity ON agent_history(run_id,call_id,seq)')


def _agent_evidence(db, row, ledger):
    """旧 done 是确认记录，不能推断已写；只接受实际结果、tool.end 或 Ledger 身份。"""
    result = json.loads(row['result_json']) if row['result_json'] else None
    commits = []
    if ledger:
        facts = ledger.execute('SELECT commit_id FROM agent_history WHERE run_id=? AND call_id=? ORDER BY seq',
                               (row['run_id'], row['call_id']))
        commits = [fact[0] for fact in facts]
    event = db.execute("SELECT event_json FROM run_events WHERE run_id=? AND event_type='tool.end' "
                       "AND json_extract(event_json,'$.data.call_id')=? ORDER BY seq DESC LIMIT 1", (row['run_id'], row['call_id'])).fetchone()
    data = json.loads(event[0]).get('data', {}) if event else {}
    if not isinstance(result, dict):
        result = data.get('result') if isinstance(data.get('result'), dict) else {}
    incomplete = not bool(result or event or commits)
    if commits and not result and data.get('wrote') is not True:
        # 只能证明其中有提交；没有逐项结果不能推断完整批量成功。
        result = {'commits': commits, 'wrote': True, 'history_incomplete': True,
                  'failed': [{'reason': '历史信息不完整'}]}
        status, incomplete = 'partial', True
    elif commits or data.get('wrote') is True:
        status = 'partial' if result.get('failed') else 'applied'
    elif result and (result.get('ok') is False or result.get('error')) or data.get('status') in ('error', 'failed') or data.get('error'):
        status = 'failed'
        if not result and data.get('error'):
            result = {'ok': False, 'error': data['error']}
    elif result or event:
        status = 'unchanged'
    elif row['status'] == 'rejected' or row['decision'] in ('deny', 'reject'):
        status = 'rejected'
    elif row['status'] == 'expired':
        status = 'expired'
    else:
        status = 'interrupted'
    return result, commits, status, incomplete


def _import_agent(vault):
    target = os.path.join(omrs_data_dir(vault), 'agent.db')
    ledger_path = os.path.join(omrs_data_dir(vault), 'ledger.db')
    if not os.path.exists(target):
        return
    ledger = _readonly(vault, ledger_path) if os.path.exists(ledger_path) else None
    try:
        if ledger:
            _agent_history_index(ledger)
        with closing(_readonly(vault, target)) as db:
            # SQLite 游标有界迭代，不读取整条对话或整个历史正文。
            for raw in db.execute('SELECT t.*,r.conversation_id FROM tool_calls t LEFT JOIN runs r ON r.id=t.run_id'):
                row = dict(raw)
                if classify('agent', row['name']) is None:
                    continue
                identity = 'agent:'+fingerprint([row['run_id'], row['call_id']])
                existing = by_identity(vault, identity)
                result, commits, status, incomplete = _agent_evidence(db, row, ledger)
                actor = {'run_id': row['run_id'], 'tool_call_id': row['call_id'], 'conversation_id': row['conversation_id']}
                native = _agent_native(vault, {'actor': actor, 'tool': row['name']}, ledger) if not commits else None
                if native:
                    result = {**result, **native}
                    status = 'partial' if native.get('failed') else 'applied'
                    incomplete = bool(native.get('history_incomplete'))
                if existing:
                    if existing['status'] in ACTIVE and (commits or result and not incomplete):
                        if status == 'failed':
                            set_state(vault, existing['operation_id'], 'failed', result=result, error_code='tool_error')
                        else:
                            reconcile(vault, existing['operation_id'], {**result, 'wrote': status in ('applied', 'partial')}, commits)
                    continue
                _historical(vault, identity=identity, source='agent', tool=row['name'], payload=json.loads(row['args_json']),
                    actor=actor,
                    result=result, status=status, commits=commits, incomplete=incomplete,
                    created_at=row['started_at'], updated_at=row['ended_at'])
    finally:
        if ledger:
            ledger.close()


def _import_mcp(vault):
    target = os.path.join(omrs_data_dir(vault), 'runtime.db')
    if not os.path.exists(target):
        return
    with closing(_readonly(vault, target)) as db:
        for raw in db.execute('SELECT * FROM records ORDER BY seq'):
            row = dict(raw)
            if classify('mcp', row['tool']) is None:
                continue
            result = json.loads(row['result_json'])
            if result.get('operation_id'):
                try:
                    get(vault, result['operation_id'])
                    continue
                except ReviewError:
                    pass
            identity = 'mcp:call:'+row['call_id']
            existing = by_identity(vault, identity)
            if existing:
                continue
            # 运行记录的成功响应是一项证据，缺实际对象/回执仍标不完整。
            known = row['status'] == 'success' and any(result.get(key) for key in ('draft_id','report_id','session_id','board_id','folder_id'))
            status = 'unchanged' if result.get('wrote') is False or result.get('reused') else 'applied' if known else 'failed' if row['status'] in ('failure','failed') else 'interrupted'
            _historical(vault, identity=identity, source='mcp', tool=row['tool'], payload=json.loads(row['arguments_json']),
                actor={'key_id': row['key_id'], 'key_name': row['key_name'], 'runtime_seq': row['seq']}, result=result,
                status=status, created_at=row['started_at'], updated_at=row['finished_at'], incomplete=True)


def _auto_receipt(vault, row):
    """技术补记只认原领域请求身份；缺回执不能重新执行业务。"""
    tool = row['tool']
    target = os.path.join(omrs_data_dir(vault), 'mcp_reports.db') if tool == 'create_report' else _draft_path(vault)
    if os.path.exists(target):
        with closing(_readonly(vault, target)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_review_receipts'").fetchone():
                return None
            result = db.execute('SELECT digest,result_json FROM ai_review_receipts WHERE operation_id=?', (row['operation_id'],)).fetchone()
        if result and result[0] == row['effective_digest']:
            return json.loads(result[1])
    return None


@storage
def initialize(vault):
    """监听前导入证据并收束中断；页面 GET 只读取已有记录。"""
    with locking.write_lock(), closing(_connect(vault, True)) as db:
        db.commit()
    with locking.write_lock():
        from . import drafts, mcp_operations
        if os.path.exists(_draft_path(vault)):
            if os.path.islink(_draft_path(vault)) or os.path.islink(os.path.dirname(_draft_path(vault))):
                raise ReviewError('unsafe_path', '审核来源草稿库不允许符号链接')
            # 已有草稿库的迁移只在监听前完成，中心 GET 始终使用只读连接。
            with closing(drafts.connect(vault)):
                pass
        mcp_operations.refresh(vault)
        _import_agent(vault)
        _import_mcp(vault)
        with closing(_connect(vault)) as db:
            rows = db.execute("SELECT * FROM operations WHERE status IN ('running','approved','applying','failed')").fetchall()
        ledger_path = os.path.join(omrs_data_dir(vault), 'ledger.db')
        ledger = _readonly(vault, ledger_path) if os.path.exists(ledger_path) else None
        try:
            if ledger:
                _agent_history_index(ledger)
            for raw in rows:
                row = _decode(raw)
                result = None
                if row['tool'] == 'propose_label_plan':
                    from .label_plan_journal import receipt, public_result
                    saved = receipt(vault, row['operation_id'], row['effective_digest'])
                    result = public_result(saved) if saved else None
                elif row['tool'] in ('propose_question_update', 'update_question_section', 'set_knowledge_points'):
                    from .question_update import recover_receipt
                    result = recover_receipt(vault, row)
                elif row['source'] == 'mcp' and row['tool'] in AUTO_MCP:
                    result = _auto_receipt(vault, row)
                elif row['source'] == 'agent':
                    result = _agent_native(vault, row, ledger)
                if result:
                    reconcile(vault, row['operation_id'], result)
                elif row['status'] in ('running', 'approved', 'applying'):
                    set_state(vault, row['operation_id'], 'interrupted', error_code='interrupted')
        finally:
            if ledger:
                ledger.close()


def _agent_native(vault, row, ledger=None):
    actor, tool = row['actor'], row['tool']
    if tool == 'create_draft' and os.path.exists(_draft_path(vault)):
        with closing(_readonly(vault, _draft_path(vault))) as db:
            draft = db.execute('SELECT id FROM drafts WHERE run_id=? AND tool_call_id=?',
                               (actor.get('run_id'), actor.get('tool_call_id'))).fetchone()
        return {'draft_id': draft[0], 'wrote': True} if draft else None
    target = os.path.join(omrs_data_dir(vault), 'agent.db')
    if tool == 'create_practice_card' and os.path.exists(target):
        with closing(_readonly(vault, target)) as db:
            card = db.execute('SELECT card_id FROM practice_cards WHERE run_id=? AND call_id=?',
                              (actor.get('run_id'), actor.get('tool_call_id'))).fetchone()
        return {'card_id': card[0], 'wrote': True} if card else None
    target = os.path.join(omrs_data_dir(vault), 'ledger.db')
    if not os.path.exists(target):
        return None
    if ledger:
        commits = [r[0] for r in ledger.execute('SELECT commit_id FROM agent_history WHERE run_id=? AND call_id=? ORDER BY seq',
                                              (actor.get('run_id'), actor.get('tool_call_id')))]
    else:
        with closing(_readonly(vault, target)) as db:
            commits = [r[0] for r in db.execute("SELECT commit_id FROM commits WHERE json_extract(payload_json,'$._agent.run_id')=? "
                                               "AND json_extract(payload_json,'$._agent.tool_call_id')=? ORDER BY seq",
                                               (actor.get('run_id'), actor.get('tool_call_id')))]
    # 没有完整逐项结果的批量写只能证明部分已提交，不能编造整批成功。
    return {'commits': commits, 'wrote': True, 'history_incomplete': True,
            'failed': [{'reason': '历史信息不完整'}]} if commits else None
