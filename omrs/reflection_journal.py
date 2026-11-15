"""错因 Markdown、问题回执与正文 Ledger 的崩溃恢复协议。"""
import hashlib
import json
import os
from pathlib import Path

from . import problem_store
from .content_history import ensure_content_recorded, question_file, refresh_projection
from .data_repository import resolve_question, storage_write
from .ledger import append_commit_in_db, blob_hash, connect
from .question_update import _read
from .question_update_journal import _identity, _stage
from .vault_lifecycle import atomic_json, fsync_dir, generation, maintenance_dir


def _directory(vault):
    return os.path.join(maintenance_dir(vault), 'reflections')


def _cleanup(path, intent):
    staged = intent.get('staged')
    if staged and os.path.isfile(staged) and _identity(staged) == intent['after_identity']:
        os.unlink(staged)
    os.unlink(path)
    fsync_dir(os.path.dirname(path))


def _receipt(vault, intent):
    with problem_store.connect(vault) as db:
        row = db.execute('SELECT digest FROM receipts WHERE request_id=?', (intent['request_id'],)).fetchone() if db else None
        if row and row[0] != intent['digest']:
            raise ValueError('错因写入回执与维护意图冲突')
        return bool(row)


def finish(vault, path, intent):
    key = 'reflection:' + hashlib.sha256(intent['request_id'].encode()).hexdigest()
    with connect(vault) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM op_results WHERE op_id=?', (key,)).fetchone():
            row = resolve_question(vault, question_id=intent['question_id'], include_archived=True, db=db)
            current, owner = _read(vault, row)
            if current != intent['after'] or owner != intent['after_identity']:
                raise ValueError('错因写入中断后题目已被外部修改，已保留现场')
            from .reflection_markdown import notes_of, summary
            changes = {'available': True, 'sections': [{'section':'错因',
                       'before':summary(notes_of(intent['before']))[:100],
                       'after':summary(notes_of(intent['after']))[:100]}]}
            fact = {'question_id': row['question_id'], 'uid_at_that_time': row['uid'],
                    'before_hash': blob_hash(intent['before']), 'after_hash': blob_hash(intent['after']),
                    '_reflection': {'request_id': intent['request_id'], 'digest': intent['digest']},
                    'change_summary': changes}
            append_commit_in_db(db, intent['source'], 'question.content_update', '保存错因记录', fact,
                                blobs=[intent['before'], intent['after']])
            db.execute("INSERT INTO op_results VALUES(?,?,datetime('now'))", (key, json.dumps({'digest': intent['digest']})))
        db.commit()
    refresh_projection(vault)
    _cleanup(path, intent)


def stage(vault, row, before, after, request_id, digest, actor):
    ensure_content_recorded(vault, row, before)
    directory = _directory(vault)
    if os.path.islink(directory):
        raise ValueError('错因维护目录不能是链接')
    os.makedirs(directory, mode=0o700, exist_ok=True)
    target = question_file(vault, row)
    current, owner = _read(vault, row)
    if current != before:
        raise ValueError('题目已变化，请重新读取后保存错因')
    staged, staged_owner = _stage(target, after)
    intent = {'format': 1, 'generation': generation(vault), 'question_id': row['question_id'],
              'file_path': row['file_path'], 'target': target, 'before': before, 'after': after,
              'before_hash': blob_hash(before), 'after_hash': blob_hash(after),
              'before_identity': owner, 'after_identity': staged_owner, 'staged': staged,
              'request_id': request_id, 'digest': digest,
              'source': actor.get('kind') if actor.get('kind') in ('agent', 'mcp') else 'api'}
    path = os.path.join(directory, hashlib.sha256(request_id.encode()).hexdigest() + '.json')
    atomic_json(path, intent)
    current, latest_owner = _read(vault, row)
    if current != before or latest_owner != owner:
        raise ValueError('文件替换前题目已变化，已保留外部编辑')
    os.replace(staged, target)
    fsync_dir(os.path.dirname(target))
    return path, intent


@storage_write
def recover_pending(vault, allow_recovery=True):
    directory = _directory(vault)
    if not os.path.exists(directory):
        return
    if os.path.islink(directory):
        raise ValueError('错因维护目录不能是链接')
    paths = sorted(Path(directory).glob('*.json'))
    if paths and not allow_recovery:
        raise ValueError('题库有未完成错因写入，请先正常启动恢复')
    for path in paths:
        if path.is_symlink():
            raise ValueError('错因维护记录不能是链接')
        intent = json.loads(path.read_text(encoding='utf-8'))
        if intent.get('format') != 1:
            raise ValueError('错因维护记录格式损坏')
        if intent['generation'] != generation(vault):
            os.replace(path, str(path) + '.obsolete')
            continue
        from .question_update_journal import _validate_intent
        _validate_intent(vault, intent)
        if _receipt(vault, intent):
            finish(vault, str(path), intent)
            continue
        row = resolve_question(vault, question_id=intent['question_id'], include_archived=True)
        if not row or question_file(vault, row) != intent['target']:
            raise ValueError('错因恢复时题目路径或身份已变化')
        current, owner = _read(vault, row)
        if current == intent['after'] and owner == intent['after_identity']:
            staged, rollback_owner = _stage(intent['target'], intent['before'])
            intent['rollback_identity'] = rollback_owner
            atomic_json(str(path), intent)
            os.replace(staged, intent['target'])
            fsync_dir(os.path.dirname(intent['target']))
        elif current != intent['before'] or owner not in (intent['before_identity'], intent.get('rollback_identity')):
            raise ValueError('错因写入失败后题目被外部修改，已保留现场')
        _cleanup(str(path), intent)
