"""对话权限与持久送审；中心批准复用原工具执行链，不重新调用模型。"""
import contextlib
import contextvars
import json
import os
import time
from contextlib import closing

from .. import ai_review
from ..actor import current_agent
from ..locking import write_lock
from ..vault_lifecycle import generation, lease
from .config import settings
from .tools import build_registry

MODES = ('manual', 'hold', 'danger')
_CENTER_PERMIT = contextvars.ContextVar('agent_center_permit', default=None)


def _binding(vault, row):
    return (str(vault), row['operation_id'], row['revision'], row['effective_digest'],
            row['generation'], ai_review.fingerprint(row['actor']))


@contextlib.contextmanager
def center_permit(vault, row):
    if row['status'] != 'applying' or row['permission'].get('channel') != 'center':
        raise ai_review.ReviewError('forbidden', '尚未取得中心执行许可', 403)
    token = _CENTER_PERMIT.set(_binding(vault, row))
    try:
        yield
    finally:
        _CENTER_PERMIT.reset(token)


def has_center_permit(vault, row):
    actor = current_agent()
    return bool(_CENTER_PERMIT.get() == _binding(vault, row) and actor and
                row['source'] == 'agent' and row['permission'].get('channel') == 'center' and
                all(actor.stamp().get(key) == row['actor'].get(key)
                    for key in ('conversation_id', 'run_id', 'tool_call_id')))


def pending(rt, conv_id):
    if not os.path.exists(ai_review.path(rt.vault)):
        return []
    with closing(ai_review._connect(rt.vault)) as db:
        rows = db.execute("SELECT * FROM operations WHERE source='agent' AND status='pending_confirmation' "
                          "AND json_extract(actor_json,'$.conversation_id')=? ORDER BY created_at", (conv_id,)).fetchall()
    return [ai_review._decode(row) for row in rows]


def transfer(vault, row, reason):
    """同一操作移交，不更换提案、版本、摘要、目标或原来源。调用者先持写锁。"""
    with write_lock(), closing(ai_review._connect(vault, True)) as db:
        db.execute('BEGIN IMMEDIATE')
        current = ai_review._decode(db.execute('SELECT * FROM operations WHERE operation_id=?', (row['operation_id'],)).fetchone())
        if not current or current['source'] != 'agent' or not current['permission']:
            raise ai_review.ReviewError('forbidden', '该请求不能移交审核中心', 403)
        if current['status'] != 'pending_confirmation' or current['permission'].get('channel') == 'center':
            return ai_review.get(vault, row['operation_id'])
        if current['generation'] != generation(vault):
            raise ai_review.ReviewError('vault_changed', '题库已恢复，旧提案不能送审', 409)
        permission = {**current['permission'], 'channel': 'center', 'reason': reason, 'deferred_at': time.time()}
        db.execute('UPDATE operations SET permission_json=?,expires_at=NULL,updated_at=? WHERE operation_id=?',
                   (ai_review._json(permission), time.time(), row['operation_id']))
        db.commit()
    return ai_review.get(vault, row['operation_id'])


def deferred_result(row):
    pending_review = row['status'] in ai_review.ACTIVE
    result = {} if pending_review else row['result']
    message = ('请求已送到审核中心，尚未执行。继续回答用户，不重复申请；批准后的结果以审核中心为准。'
               if pending_review else '请求已由审核中心处理，结果以当前审核状态和实际回执为准；不要重复申请。')
    return {'status': 'deferred', 'result': {**result, 'ok': True, 'operation_id': row['operation_id'],
            'pending_review': pending_review, 'executed': bool(row['commits']) or row['status'] in ('applied', 'unchanged'),
            'review_status': row['status'], 'message': message}}


def auto_reviewer(conv):
    return {'kind': 'permission_mode', 'mode': 'danger',
            'selected_by': json.loads(conv.get('permission_actor_json') or '{}')}


def mark_automatic(vault, row):
    permission = {**row['permission'], 'mode': 'danger', 'automatic': True}
    with closing(ai_review._connect(vault, True)) as db:
        db.execute('UPDATE operations SET permission_json=?,updated_at=? WHERE operation_id=? AND status=?',
                   (ai_review._json(permission), time.time(), row['operation_id'], 'pending_confirmation'))
        db.commit()


def change_mode(rt, conv_id, mode, reviewer):
    from .runtime import AgentError
    if mode not in MODES:
        raise AgentError(400, '权限模式只能是 manual、hold 或 danger')
    with lease(rt.vault), write_lock():
        if not rt.store.conversation(conv_id):
            raise AgentError(404, '对话不存在')
        conv = rt.store.set_permission_mode(conv_id, mode, dict(reviewer or {'kind': 'web'}))
        handled = 0
        for row in pending(rt, conv_id):
            if mode == 'hold':
                defer(rt, row['operation_id'], row['revision'], 'mode_change')
                handled += 1
            elif mode == 'danger':
                if row.get('expires_at') is not None and time.time() >= row['expires_at']:
                    row = defer(rt, row['operation_id'], row['revision'], 'timeout')
                mark_automatic(rt.vault, row)
                ai_review.decide(rt.vault, row['operation_id'], row['revision'], 'approve', auto_reviewer(conv))
                handled += 1
        return {'conversation': conv, 'handled': handled}


def defer(rt, operation_id, revision, reason='manual'):
    from .runtime import _live_review
    with lease(rt.vault), write_lock():
        row = ai_review.get(rt.vault, operation_id)
        if type(revision) is not int or row['revision'] != revision:
            raise ai_review.ReviewError('revision_conflict', '提案已修订，请重新核对', 409)
        original = rt.runs.get(row['actor'].get('run_id'))
        if (row['status'] == 'pending_confirmation' and row['permission'].get('channel') == 'chat'
                and original and original.abort.is_set()):
            return ai_review.set_state(rt.vault, operation_id, 'cancelled', error_code='interrupted',
                                       expected_status='pending_confirmation')
        run, pc = _live_review(rt.vault, row)
        row = transfer(rt.vault, row, reason)
        if row['status'] == 'pending_confirmation' and pc:
            with pc.lock:
                pc.close('defer')
        return row


def record_result(rt, row, out=None, error=''):
    out = out or {'result': {}, 'commits': row['commits'], 'wrote': bool(row['commits'])}
    actor = row['actor']
    data = {'call_id': actor['tool_call_id'], 'operation_id': row['operation_id'],
            'status': 'done' if row['status'] in ('applied', 'unchanged') else row['status'],
            'summary': out.get('summary', ''), 'result': {**out['result'], 'operation_id': row['operation_id']},
            'commits': out['commits'], 'wrote': bool(out['commits'] or out.get('wrote')), 'error': error}
    rt.store.save_tool_call(actor['run_id'], actor['tool_call_id'], row['tool'], 'confirm', row['payload'],
                           data['status'], result=data['result'], commits=data['commits'])
    run = rt.runs.get(actor['run_id'])
    if run:
        with run.cond:
            if not run.done:
                run.emit('tool.reviewed', data)
                return
    rt.store.append_review_event(actor['run_id'], data)


def decide_center(vault, row, decision):
    from .runtime import get_runtime, Run, Hooks, _verify_review_snapshot
    rt = get_runtime(vault)
    if decision == 'reject':
        final = ai_review.set_state(vault, row['operation_id'], 'rejected', expected_status='pending_confirmation')
        record_result(rt, final)
        return final
    try:
        cfg = settings(vault)
        registry = build_registry(cfg)
        tool = registry.get(row['tool'])
        original = rt.store.run(row['actor'].get('run_id'))
        conv = rt.store.conversation(row['actor'].get('conversation_id'))
        if not cfg['enabled'] or not tool or tool.level != 'confirm':
            raise ai_review.ReviewError('forbidden', '助手或该工具已停用，请重新申请', 403)
        if not conv or not original or original['conversation_id'] != conv['id'] or original['reverted']:
            raise ai_review.ReviewError('interrupted', '原对话不存在或该运行已撤销，不能执行旧提案', 409)
        _verify_review_snapshot(vault, row)
    except (ValueError, RuntimeError, OSError) as exc:
        final = ai_review.set_state(vault, row['operation_id'], 'conflict', error_code=getattr(exc, 'code', 'content_conflict'),
                                    expected_status='pending_confirmation')
        record_result(rt, final, error=str(exc))
        return final
    ai_review.set_state(vault, row['operation_id'], 'approved', expected_status='pending_confirmation', expected_revision=row['revision'])
    # 无模型、无新运行；用原身份和严格内部许可复用已验证的落盘链。
    run = Run(original['id'], conv['id'], original['model'])
    hooks = Hooks(rt, run, registry)
    call = {'id': row['actor']['tool_call_id'], 'name': row['tool'], 'args': row['payload']}
    hooks._review_ids[call['id']] = row['operation_id']
    if row['tool'] == 'commit_draft':
        mark = row['snapshot'].get('draft_config_mark')
        hooks._draft_config_marks[call['id']] = tuple(mark) if mark else None
    try:
        out = hooks.execute(call, tool, from_center=True)
        hooks.after_tool_call(call, tool, out)
        final = ai_review.get(vault, row['operation_id'])
        record_result(rt, final, out)
        return final
    except Exception as exc:  # noqa: BLE001 - 已批准失败不重放，仅展示原结果
        final = ai_review.get(vault, row['operation_id'])
        if final['status'] in ai_review.ACTIVE:
            final = ai_review.set_state(vault, row['operation_id'], 'failed', error_code=getattr(exc, 'code', 'internal_error'))
        record_result(rt, final, error=str(exc))
        return final
