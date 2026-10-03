"""题目文件与 Ledger 的崩溃协议：事实和回执同事务，启动只收束已有意图。"""
import json
import os
import re
import sqlite3
import stat
import uuid
from contextlib import closing
from pathlib import Path

from .content_history import (ensure_content_recorded, question_file, question_payload,
                             refresh_projection)
from .data_repository import resolve_question, storage_write
from .errors import RequestError
from .ledger import append_commit_in_db, blob_hash, connect, canonical_json, ledger_path
from .mcp.common import fingerprint
from .question_update import _read, editable_values, prepare_update, patch_content
from .vault_lifecycle import atomic_json, fsync_dir, generation, maintenance_dir, open_sqlite, storage


def _directory(vault):
    path = os.path.join(maintenance_dir(vault), 'question-updates')
    if os.path.islink(path):
        raise RequestError('operation_pending', '题目写入维护目录不能是链接')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _head(db):
    row = db.execute('SELECT seq,commit_hash FROM commits ORDER BY seq DESC LIMIT 1').fetchone()
    return [row['seq'], row['commit_hash']] if row else [0, None]


def _identity(path):
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or os.path.islink(path):
        raise RequestError('operation_pending', '题目写入文件身份不明确')
    return [info.st_dev, info.st_ino]


def _stage(path, content):
    target = path + '.omrs-update-' + uuid.uuid4().hex
    with open(target, 'x', encoding='utf-8', newline='') as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(target, stat.S_IMODE(os.stat(path, follow_symlinks=False).st_mode))
    fsync_dir(os.path.dirname(target))
    return target, _identity(target)


def _receipt(db, intent):
    raw = db.execute('SELECT result_json FROM op_results WHERE op_id=?', ('ai-review:' + intent['operation_id'],)).fetchone()
    if raw is None:
        return None
    result = json.loads(raw[0])
    if (result.get('question_id') != intent['question_id'] or result.get('digest') != intent['digest'] or
            (intent.get('after_hash') and result.get('content_hash') != intent['after_hash'])):
        raise RequestError('operation_pending', '题目回执与审核意图不匹配')
    if not result.get('no_op'):
        fact = db.execute('SELECT payload_json FROM commits WHERE commit_id=?', (result.get('commit_id'),)).fetchone()
        payload = json.loads(fact[0]) if fact else {}
        stamp = payload.get('_ai_review', {})
        if (stamp.get('operation_id') != intent['operation_id'] or stamp.get('digest') != intent['digest'] or
                payload.get('question_id') != intent['question_id'] or payload.get('after_hash') != result.get('content_hash')):
            raise RequestError('operation_pending', '题目回执没有对应的 Ledger 事实')
    return result


@storage
def receipt(vault, row):
    """只读已提交回执；供共享确认库恢复状态，不重新执行操作。"""
    snapshot = row.get('snapshot') or {}
    if not isinstance(snapshot, dict):
        raise RequestError('operation_pending', '题目审批快照不可识别')
    intent = {'operation_id': row['operation_id'], 'question_id': snapshot.get('question_id'),
              'digest': row.get('effective_digest') or fingerprint(row['payload'])}
    target = ledger_path(vault)
    if not os.path.exists(target):
        return None
    if os.path.islink(target):
        raise RequestError('operation_pending', '题目回执库不能是链接')
    with closing(open_sqlite(vault, Path(target).as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        return _receipt(db, intent)


def _cleanup(path, intent):
    staged = intent.get('staged')
    if staged and os.path.isfile(staged) and _identity(staged) == intent['after_identity']:
        os.unlink(staged)
        fsync_dir(os.path.dirname(staged))
    os.unlink(path)
    fsync_dir(os.path.dirname(path))


def _validate_intent(vault, intent):
    from .common import parse_yaml_frontmatter
    from .path_safety import safe_question_path
    relative = intent.get('file_path', '')
    target = os.path.abspath(os.path.join(vault, relative))
    if not relative or os.path.isabs(relative) or target != intent.get('target'):
        raise RequestError('operation_pending', '题目维护记录路径不一致')
    safe_question_path(vault, target)
    for key in ('before', 'after'):
        text = intent.get(key)
        if not isinstance(text, str) or blob_hash(text) != intent.get(key + '_hash') or parse_yaml_frontmatter(text).get('_omrs_id') != intent.get('question_id'):
            raise RequestError('operation_pending', '题目维护记录内容或身份不一致')
    staged = intent.get('staged', '')
    if not staged.startswith(target + '.omrs-update-') or not re.fullmatch('[0-9a-f]{32}', staged[len(target + '.omrs-update-'):]):
        raise RequestError('operation_pending', '题目维护暂存文件身份不一致')


def _recover(vault, path, intent):
    if intent.get('format') != 1:
        raise RequestError('operation_pending', '题目写入维护记录损坏，已停止启动')
    if intent.get('generation') != generation(vault):
        # 旧世代材料保留在维护目录，绝不读写已经恢复的题库文件。
        os.replace(path, path + '.obsolete')
        fsync_dir(os.path.dirname(path))
        return 'obsolete'
    _validate_intent(vault, intent)
    with connect(vault) as db:
        db.execute('BEGIN IMMEDIATE')
        if _receipt(db, intent):
            _cleanup(path, intent)
            return 'committed'
        row = resolve_question(vault, question_id=intent['question_id'], db=db)
        if (not row or row['file_path'] != intent['file_path'] or _head(db) != intent['head']):
            raise RequestError('operation_pending', '题目写入中断后出现其它事实，已保留文件并停止启动')
        current, owner = _read(vault, row)
        target = question_file(vault, row)
        if target != intent['target'] or blob_hash(intent['before']) != intent['before_hash'] or blob_hash(intent['after']) != intent['after_hash']:
            raise RequestError('operation_pending', '题目写入维护内容不一致，已停止启动')
        if blob_hash(current) == intent['before_hash'] and owner in (intent['before_identity'], intent.get('rollback_identity')):
            _cleanup(path, intent)
            return 'not_written'
        if blob_hash(current) != intent['after_hash'] or owner != intent['after_identity']:
            raise RequestError('operation_pending', '题目文件不再属于中断写入，已保留现场并停止启动')
        staged, owner = _stage(target, intent['before'])
        intent.update(rollback_staged=staged, rollback_identity=owner, phase='rolling_back')
        atomic_json(path, intent)
        os.replace(staged, target)
        fsync_dir(os.path.dirname(target))
        _cleanup(path, intent)
        return 'rolled_back'


@storage_write
def recover_pending(vault, allow_recovery=True):
    """在扫描和监听前恢复；无事实的意图仅在精确文件所有权与链头下回滚。"""
    directory = os.path.join(os.path.realpath(vault), '.omrs-maintenance', 'question-updates')
    if not os.path.exists(directory):
        return {'committed': 0, 'rolled_back': 0, 'not_written': 0, 'obsolete': 0}
    if os.path.islink(directory):
        raise RequestError('operation_pending', '题目写入维护目录不能是链接')
    pending = sorted(name for name in os.listdir(directory) if re.fullmatch(r'[0-9a-f]{64}\.json', name))
    if pending and not allow_recovery:
        raise RequestError('operation_pending', '题库有未完成题目写入，请先正常启动恢复')
    results = {'committed': 0, 'rolled_back': 0, 'not_written': 0, 'obsolete': 0}
    for name in pending:
        path = os.path.join(directory, name)
        if os.path.islink(path):
            raise RequestError('operation_pending', '题目写入维护记录不能是链接')
        with open(path, encoding='utf-8') as file:
            intent = json.load(file)
        results[_recover(vault, path, intent)] += 1
    return results


def apply(vault, review):
    from .ai_review import verify_question_write
    existing = receipt(vault, review)
    if existing:
        return {**existing, 'reused': True}
    verify_question_write(vault, review)
    recover_pending(vault)
    payload, _, snapshot = prepare_update(vault, **review['payload'])
    if snapshot != review.get('snapshot'):
        raise RequestError('content_conflict', '题目基线或题库世代已变化，请重新提交提案')
    row = resolve_question(vault, uid=payload['uid'], question_id=payload['question_id'])
    before, owner = _read(vault, row)
    after = patch_content(before, payload['patch'])
    ensure_content_recorded(vault, row, before)
    intent = {'format': 1, 'operation_id': review['operation_id'], 'question_id': row['question_id'],
              'file_path': row['file_path'], 'target': question_file(vault, row), 'generation': generation(vault),
              'digest': review.get('effective_digest') or fingerprint(payload),
              'before': before, 'after': after, 'before_hash': blob_hash(before), 'after_hash': blob_hash(after),
              'before_identity': owner, 'phase': 'prepared'}
    journal = os.path.join(_directory(vault), fingerprint(review['operation_id']) + '.json')
    with connect(vault) as db:
        db.execute('BEGIN IMMEDIATE')
        if _receipt(db, intent):
            return {**_receipt(db, intent), 'reused': True}
        now, identity = _read(vault, row)
        if now != before or identity != owner:
            raise RequestError('content_conflict', '题目在批准写入前发生变化')
        commit = None
        if before != after:
            staged, staged_owner = _stage(intent['target'], after)
            intent.update(staged=staged, after_identity=staged_owner, head=_head(db))
            atomic_json(journal, intent)
            latest, latest_owner = _read(vault, row)
            if latest != before or latest_owner != owner:
                raise RequestError('content_conflict', '题目在文件替换前发生变化，已保留外部编辑')
            verify_question_write(vault, review)
            os.replace(staged, intent['target'])
            fsync_dir(os.path.dirname(intent['target']))
            from .workspace_sync import metadata_hash
            from .projections import _content_change_summary
            fact = {'question_id': row['question_id'], 'uid_at_that_time': row['uid'],
                    'before_hash': intent['before_hash'], 'after_hash': intent['after_hash'],
                    'change_summary': _content_change_summary(before, after),
                    '_ai_review': {'operation_id': review['operation_id'], 'digest': intent['digest'],
                                   'source': review.get('source', ''), 'actor': review.get('actor') or {}}}
            kind = 'question.content_update'
            if metadata_hash(parse_yaml(before)) != metadata_hash(parse_yaml(after)):
                kind = 'question.metadata_update'
                fact.update(before=question_payload(row, before), after=question_payload(row, after))
            source = 'agent' if review.get('source') == 'agent' else 'mcp'
            commit = append_commit_in_db(db, source, kind, f"审核修改题目 {row['uid']}", fact, blobs=[before, after])
        if before == after:
            verify_question_write(vault, review)
        result = {'uid': row['uid'], 'question_id': row['question_id'], 'content_hash': intent['after_hash'],
                  'before_hash': intent['before_hash'], 'after_hash': intent['after_hash'], 'digest': intent['digest'],
                  'no_op': before == after, 'changed': before != after,
                  'fields': {k: editable_values(after)[k] for k in payload['patch']},
                  'commits': [{**commit, 'commit_type': kind}] if commit else []}
        if commit:
            result['commit_id'] = commit['commit_id']
        db.execute('INSERT INTO op_results(op_id,result_json,created_at) VALUES(?,?,datetime(\'now\'))',
                   ('ai-review:' + review['operation_id'], canonical_json(result)))
        db.commit()
    if before != after:
        refresh_projection(vault)
        _cleanup(journal, intent)
    return result


def parse_yaml(content):
    from .common import parse_yaml_frontmatter
    return parse_yaml_frontmatter(content)
