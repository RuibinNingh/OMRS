"""定义 JSON 与多题 Markdown 的整批原生回执和崩溃恢复。"""
import json
import os
import re
import stat
import uuid
from contextlib import closing
from pathlib import Path

from .actor import current_agent
from .content_history import question_payload, refresh_projection
from .data_repository import storage_write
from .errors import RequestError
from .ledger import append_commit_in_db, blob_hash, canonical_json, connect
from .label_plan import digest
from .path_safety import safe_question_path
from .vault_lifecycle import atomic_json, fsync_dir, generation, maintenance_dir, open_sqlite, storage


def directory(vault):
    path = os.path.join(maintenance_dir(vault), 'label-plans')
    if os.path.islink(path):
        raise RequestError('operation_pending', '标记整理维护目录不能是链接')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _head(db):
    row = db.execute('SELECT seq,commit_hash FROM commits ORDER BY seq DESC LIMIT 1').fetchone()
    return [row['seq'], row['commit_hash']] if row else [0, None]


def _read_file(path):
    if os.path.islink(path):
        raise RequestError('operation_pending', '整理文件不能是链接')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return None, None
    with os.fdopen(fd, 'r', encoding='utf-8', newline='') as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise RequestError('operation_pending', '整理文件不是普通文件')
        content = file.read()
        after = os.fstat(file.fileno())
    now = os.stat(path, follow_symlinks=False)
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if signature(before) != signature(after) or signature(before) != signature(now):
        raise RequestError('content_conflict', '读取期间整理文件发生变化')
    return content, [before.st_dev, before.st_ino]


def _stage(target, content):
    path = target + '.omrs-label-' + uuid.uuid4().hex
    try:
        with open(path, 'x', encoding='utf-8', newline='') as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        mode = stat.S_IMODE(os.stat(target, follow_symlinks=False).st_mode) if os.path.exists(target) else 0o600
        os.chmod(path, mode)
        fsync_dir(os.path.dirname(path))
        return path, _read_file(path)[1]
    except BaseException:
        if os.path.isfile(path):
            os.unlink(path)
        raise


def _receipt(db, operation_id, expected_digest=None):
    raw = db.execute('SELECT result_json FROM op_results WHERE op_id=?', ('label-plan:' + operation_id,)).fetchone()
    if raw is None:
        return None
    result = json.loads(raw[0])
    if result.get('operation_id') != operation_id or (expected_digest and result.get('digest') != expected_digest):
        raise RequestError('operation_pending', '标记整理回执摘要不匹配')
    if not result.get('no_op'):
        row = db.execute('SELECT commit_type,payload_json FROM commits WHERE commit_id=?', (result.get('batch_commit_id'),)).fetchone()
        fact = json.loads(row['payload_json']) if row else {}
        if (not row or row['commit_type'] not in ('labels.plan_apply', 'labels.plan_revert') or
                fact.get('operation_id') != operation_id or fact.get('digest') != result.get('digest')):
            raise RequestError('operation_pending', '标记整理回执缺少对应批次事实')
    return result


@storage
def receipt(vault, operation_id, expected_digest=None):
    """严格只读取已有 Ledger，不初始化 schema 或触发恢复。"""
    path = os.path.join(os.path.abspath(vault), '错题', '.omrs', 'ledger.db')
    if not os.path.isfile(path):
        return None
    if os.path.islink(path):
        raise RequestError('operation_pending', '整理回执库不能是链接')
    with closing(open_sqlite(vault, Path(path).as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = __import__('sqlite3').Row
        return _receipt(db, operation_id, expected_digest)


def public_result(result):
    return {key: value for key, value in result.items() if key != '_undo'}


def _target(vault, entry):
    relative = entry.get('relative', '')
    if not isinstance(relative, str) or not relative or os.path.isabs(relative):
        raise RequestError('operation_pending', '整理维护路径不合法')
    target = os.path.abspath(os.path.join(vault, relative))
    if entry['kind'] == 'catalog':
        expected = os.path.join(os.path.abspath(vault), '错题', '.omrs', 'labels.json')
        if target != expected:
            raise RequestError('operation_pending', '标记定义维护路径不一致')
    elif entry['kind'] == 'question':
        safe_question_path(vault, target)
        from .common import parse_yaml_frontmatter
        for key in ('before', 'after'):
            if parse_yaml_frontmatter(entry[key]).get('_omrs_id') != entry.get('question_id'):
                raise RequestError('operation_pending', '整理维护题目身份不一致')
    else:
        raise RequestError('operation_pending', '整理维护对象未知')
    cursor = target
    while cursor != os.path.abspath(vault):
        if os.path.islink(cursor):
            raise RequestError('operation_pending', '整理维护路径含链接')
        parent = os.path.dirname(cursor)
        if parent == cursor:
            raise RequestError('operation_pending', '整理维护路径超出 Vault')
        cursor = parent
    for key in ('before', 'after'):
        value = entry[key]
        if value is not None and not isinstance(value, str):
            raise RequestError('operation_pending', '整理维护内容不合法')
        if (blob_hash(value) if value is not None else None) != entry[key + '_hash']:
            raise RequestError('operation_pending', '整理维护内容哈希不一致')
    for key in ('staged', 'rollback_staged'):
        path = entry.get(key)
        if path and (not path.startswith(target + '.omrs-label-') or not re.fullmatch('[0-9a-f]{32}', path[len(target + '.omrs-label-'):])):
            raise RequestError('operation_pending', '整理暂存文件路径不一致')
    return target


def _cleanup(path, intent):
    for entry in intent['files']:
        for key, owner in (('staged', 'after_identity'), ('rollback_staged', 'rollback_identity')):
            temporary = entry.get(key)
            if temporary and os.path.lexists(temporary):
                _, identity = _read_file(temporary)
                if identity != entry.get(owner):
                    raise RequestError('operation_pending', '整理暂存材料身份已变化')
                os.unlink(temporary)
                fsync_dir(os.path.dirname(temporary))
    os.unlink(path)
    fsync_dir(os.path.dirname(path))


def _recover(vault, path, intent):
    if (intent.get('format') != 1 or not isinstance(intent.get('files'), list) or
            not isinstance(intent.get('operation_id'), str) or not isinstance(intent.get('digest'), str)):
        raise RequestError('operation_pending', '标记整理维护记录损坏')
    if intent.get('generation') != generation(vault):
        os.replace(path, path + '.obsolete')
        fsync_dir(os.path.dirname(path))
        return 'obsolete'
    targets = [_target(vault, entry) for entry in intent['files']]
    if len(targets) != len(set(targets)):
        raise RequestError('operation_pending', '整理维护目标重复')
    with connect(vault) as db:
        db.execute('BEGIN IMMEDIATE')
        if _receipt(db, intent['operation_id'], intent['digest']):
            _cleanup(path, intent)
            return 'committed'
        if _head(db) != intent['head']:
            raise RequestError('operation_pending', '整理中断后出现其它事实，已保留现场')
        to_restore = []
        # 先检查全部所有权，不能回滚一半才发现外部编辑。
        for entry, target in zip(intent['files'], targets):
            current, owner = _read_file(target)
            value = blob_hash(current) if current is not None else None
            if value == entry['before_hash'] and owner in (entry['before_identity'], entry.get('rollback_identity')):
                continue
            if value != entry['after_hash'] or owner != entry['after_identity']:
                raise RequestError('operation_pending', '整理文件已被外部修改，不能覆盖；已保留现场')
            to_restore.append((entry, target))
        for entry, target in reversed(to_restore):
            if entry['before'] is None:
                os.unlink(target)
                fsync_dir(os.path.dirname(target))
            else:
                staged, owner = _stage(target, entry['before'])
                entry.update(rollback_staged=staged, rollback_identity=owner)
                atomic_json(path, intent)
                os.replace(staged, target)
                fsync_dir(os.path.dirname(target))
        _cleanup(path, intent)
        return 'rolled_back' if to_restore else 'not_written'


@storage_write
def recover_pending(vault, allow_recovery=True):
    path = os.path.join(os.path.realpath(vault), '.omrs-maintenance', 'label-plans')
    counts = {key: 0 for key in ('committed', 'rolled_back', 'not_written', 'obsolete')}
    if not os.path.exists(path):
        return counts
    if os.path.islink(path):
        raise RequestError('operation_pending', '标记整理维护目录不能是链接')
    names = sorted(name for name in os.listdir(path) if re.fullmatch(r'[0-9a-f]{64}\.json', name))
    if names and not allow_recovery:
        raise RequestError('operation_pending', '标记整理尚待恢复，请正常启动恢复后重试')
    for name in names:
        journal = os.path.join(path, name)
        if os.path.islink(journal):
            raise RequestError('operation_pending', '整理维护记录不能是链接')
        with open(journal, encoding='utf-8') as file:
            intent = json.load(file)
        counts[_recover(vault, journal, intent)] += 1
    if counts['committed']:
        refresh_projection(vault)
    return counts


@storage_write
def execute(vault, prepared, operation_id, effective_digest, *, source='api', authorize=None, revert_of=''):
    recover_pending(vault)
    existing = receipt(vault, operation_id, effective_digest)
    if existing:
        return {**existing, 'reused': True}
    authorize = authorize or (lambda: None)
    authorize()
    entries = []
    catalog_path = os.path.join(os.path.abspath(vault), '错题', '.omrs', 'labels.json')
    if prepared['catalog_before'] != prepared['catalog_after']:
        entries.append({'kind': 'catalog', 'relative': os.path.relpath(catalog_path, vault),
                        'before': prepared['catalog_before'], 'after': prepared['catalog_after']})
    for file in prepared['files']:
        row = file['row']
        entries.append({'kind': 'question', 'question_id': row['question_id'], 'relative': row['file_path'],
                        'before': file['before'], 'after': file['after']})
    intent = {'format': 1, 'generation': generation(vault), 'operation_id': operation_id,
              'digest': effective_digest, 'files': entries}
    journal = os.path.join(directory(vault), digest(operation_id) + '.json')
    commits, actor = [], current_agent()
    actor_start = len(actor.commits) if actor else 0
    journal_saved = False
    try:
        with connect(vault) as db:
            db.execute('BEGIN IMMEDIATE')
            intent['head'] = _head(db)
            for entry in entries:
                entry.update(before_hash=blob_hash(entry['before']) if entry['before'] is not None else None,
                             after_hash=blob_hash(entry['after']) if entry['after'] is not None else None)
                target = _target(vault, entry)
                current, owner = _read_file(target)
                if current != entry['before']:
                    raise RequestError('content_conflict', '文件在预览与写入之间发生变化')
                entry.update(before_identity=owner, before_hash=blob_hash(current) if current is not None else None,
                             after_hash=blob_hash(entry['after']) if entry['after'] is not None else None)
                if entry['after'] is not None:
                    entry['staged'], entry['after_identity'] = _stage(target, entry['after'])
                else:
                    entry['after_identity'] = None
            if entries:
                atomic_json(journal, intent)
                journal_saved = True
            for entry in entries:
                target = _target(vault, entry)
                current, owner = _read_file(target)
                if current != entry['before'] or owner != entry['before_identity']:
                    raise RequestError('content_conflict', '替换前文件已变化，保留外部编辑')
                authorize()
                if entry['after'] is None:
                    os.unlink(target)
                else:
                    os.replace(entry['staged'], target)
                fsync_dir(os.path.dirname(target))
            for file in prepared['files']:
                row, before, after = file['row'], file['before'], file['after']
                fact = {'question_id': row['question_id'], 'uid_at_that_time': row['uid'],
                        'before_hash': blob_hash(before), 'after_hash': blob_hash(after),
                        'before': question_payload(row, before), 'after': question_payload(row, after),
                        '_label_plan': {'operation_id': operation_id, 'digest': effective_digest}}
                if revert_of:
                    fact['_label_plan']['revert_of'] = revert_of
                commit = append_commit_in_db(db, source, 'question.metadata_update', f"整理 {row['uid']} 的标记", fact, blobs=[before, after])
                commits.append({**commit, 'commit_type': 'question.metadata_update'})
            batch = None
            if entries:
                kind = 'labels.plan_revert' if revert_of else 'labels.plan_apply'
                batch = append_commit_in_db(db, source, kind, '撤销整批标记整理' if revert_of else '整批整理题目标记',
                    {'operation_id': operation_id, 'digest': effective_digest, 'revert_of': revert_of,
                     'question_ids': [f['row']['question_id'] for f in prepared['files']],
                     'definition_count': prepared['preview']['counts'].get('definitions', 0)})
                commits.append({**batch, 'commit_type': kind})
            authorize()
            result = {'operation_id': operation_id, 'digest': effective_digest, 'no_op': not entries, 'wrote': bool(entries),
                      'counts': prepared['preview']['counts'], 'details': prepared['preview'].get('items', []),
                      'label_changes': prepared['preview'].get('label_changes', []), 'commits': commits,
                      'batch_commit_id': batch['commit_id'] if batch else '', 'revert_of': revert_of,
                      '_undo': {'generation': generation(vault), 'snapshot': prepared.get('snapshot', {}), 'catalog_before': prepared['catalog_before'], 'catalog_after': prepared['catalog_after'],
                                'questions': [{'question_id': f['row']['question_id'], 'file_path': f['row']['file_path'],
                                               'before_hash': blob_hash(f['before']), 'after_hash': blob_hash(f['after'])} for f in prepared['files']]}}
            db.execute('INSERT INTO op_results(op_id,result_json,created_at) VALUES(?,?,datetime(\'now\'))',
                       ('label-plan:' + operation_id, canonical_json(result)))
            if revert_of:
                db.execute('INSERT INTO op_results(op_id,result_json,created_at) VALUES(?,?,datetime(\'now\'))',
                           ('label-plan-reverted:' + revert_of, canonical_json({'operation_id': operation_id})))
            db.commit()
    except BaseException:
        committed = receipt(vault, operation_id, effective_digest)
        if committed:
            recover_pending(vault)
            return committed
        # actor 的临时提交列表不是事实，事务回滚时必须同步剔除。
        if actor:
            del actor.commits[actor_start:]
        if journal_saved:
            recover_pending(vault)
        else:
            for entry in entries:
                temporary = entry.get('staged')
                if temporary and os.path.exists(temporary) and _read_file(temporary)[1] == entry.get('after_identity'):
                    os.unlink(temporary)
        raise
    if entries:
        refresh_projection(vault)
        _cleanup(journal, intent)
    return result


def assert_readable(vault):
    """调用者持一致性锁；GET 仅拒绝待恢复现场，不代替启动恢复。"""
    path = os.path.join(os.path.realpath(vault), '.omrs-maintenance', 'label-plans')
    if os.path.isdir(path) and any(re.fullmatch(r'[0-9a-f]{64}\.json', name) for name in os.listdir(path)):
        raise RequestError('operation_pending', '标记整理尚待恢复，请正常启动后重试')
