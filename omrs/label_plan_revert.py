"""整批撤销标记整理；只恢复本批字段，保留无关的后续改动。"""
import copy
import json

from .common import extract_labels, parse_yaml_frontmatter
from .data_repository import resolve_question, storage_write
from .errors import RequestError
from .label_plan import catalog, digest
from .label_plan_journal import execute, public_result, receipt, recover_pending
from .ledger import blob_hash, connect, get_blob
from .question_update import _read, _replace_yaml
from .vault_lifecycle import generation


def _conflict(message):
    raise RequestError('content_conflict', message)


@storage_write
def prepare_revert(vault, operation_id):
    from .label_plan_journal import assert_readable
    assert_readable(vault)
    original = receipt(vault, operation_id)
    if not original or original.get('no_op') or original.get('revert_of'):
        raise RequestError('not_found', '没有可撤销的完整标记整理批次')
    undo = original['_undo']
    if undo['generation'] != generation(vault):
        _conflict('题库世代已变化，旧批次不能撤销')
    with connect(vault) as db:
        if db.execute('SELECT 1 FROM op_results WHERE op_id=?', ('label-plan-reverted:' + operation_id,)).fetchone():
            raise RequestError('already_reverted', '这批标记整理已经撤销')
    current_catalog, raw = catalog(vault)
    before = json.loads(undo['catalog_before']) if undo['catalog_before'] else {'version': 1, 'labels': []}
    after = json.loads(undo['catalog_after']) if undo['catalog_after'] else {'version': 1, 'labels': []}
    bmap, amap, now = ({d['id']: d for d in data['labels']} for data in (before, after, current_catalog))
    changed = {key for key in bmap.keys() | amap.keys() if bmap.get(key) != amap.get(key)}
    for key in changed:
        if now.get(key) != amap.get(key):
            _conflict('本批涉及的标记定义后来已变化，请先处理冲突')
    restored = copy.deepcopy(now)
    for key in changed:
        if key in bmap:
            restored[key] = copy.deepcopy(bmap[key])
        else:
            restored.pop(key, None)
    names = [d['name'] for d in restored.values()]
    if len(names) != len(set(names)):
        _conflict('恢复原标记名称会与后续新建标记冲突')
    target_ids = {q['question_id'] for q in undo['questions']}
    # 新增引用也要核对。不能只检查本批改过的题目。
    affected_names = {d['name'] for key in changed for d in (bmap.get(key), amap.get(key)) if d}
    allowed_refs = set(target_ids)
    for ids in undo.get('snapshot', {}).get('references', {}).values():
        allowed_refs.update(ids)
    with connect(vault) as db:
        active = [dict(r) for r in db.execute('SELECT * FROM question_projection WHERE archived=0')]
    for row in active:
        content, _ = _read(vault, row)
        if affected_names.intersection(extract_labels(parse_yaml_frontmatter(content))) and row['question_id'] not in allowed_refs:
            _conflict('标记出现本批之外的新引用，不能整批撤销')
    files, items = [], []
    for q in undo['questions']:
        row = resolve_question(vault, question_id=q['question_id'])
        if not row or row['file_path'] != q['file_path']:
            _conflict('本批题目已移动、归档或不存在')
        content, owner = _read(vault, row)
        before_text, after_text = get_blob(vault, q['before_hash']), get_blob(vault, q['after_hash'])
        if before_text is None or after_text is None or blob_hash(before_text) != q['before_hash'] or blob_hash(after_text) != q['after_hash']:
            _conflict('撤销依赖的题目历史不完整')
        if any(parse_yaml_frontmatter(value).get('_omrs_id') != row['question_id'] for value in (before_text, after_text)):
            _conflict('撤销历史题目身份不一致')
        previous_labels = extract_labels(parse_yaml_frontmatter(before_text))
        applied_labels = extract_labels(parse_yaml_frontmatter(after_text))
        current_labels = extract_labels(parse_yaml_frontmatter(content))
        # 只逆转本批的添加与移除；无关新标记和正文可以保留。
        added, removed = set(applied_labels) - set(previous_labels), set(previous_labels) - set(applied_labels)
        if not added.issubset(current_labels) or removed.intersection(current_labels):
            _conflict('题目涉及的标记后来已变化，不能覆盖后续归类')
        if blob_hash(content) != row.get('content_hash'):
            _conflict('题目含未扫描修改，请先扫描再撤销')
        final = [name for name in previous_labels if name in removed or name in current_labels]
        final.extend(name for name in current_labels if name not in added and name not in final)
        updated = _replace_yaml(content, '标记', final)
        files.append({'row': row, 'before': content, 'after': updated, 'owner': owner})
        items.append({'question_id': row['question_id'], 'uid': row['uid'], 'subject': row['subject'],
                      'category': row['category'], 'before': current_labels, 'after': final, 'changed': content != updated})
    final_catalog = {**current_catalog, 'labels': sorted(restored.values(), key=lambda d: (d.get('order', 0), d.get('created_at', ''), d['name']))}
    output_raw = json.dumps(final_catalog, ensure_ascii=False, indent=2)
    if final_catalog == current_catalog:
        output_raw = raw
    elif not restored and undo['catalog_before'] is None:
        output_raw = None
    snapshot = {'generation': generation(vault), 'catalog_hash': blob_hash(raw) if raw is not None else None,
                'questions': [{'question_id': f['row']['question_id'], 'content_hash': blob_hash(f['before'])} for f in files]}
    inverse_digest = digest({'operation_id': operation_id, 'snapshot': snapshot, 'catalog_after': output_raw,
                             'items': items})
    return {'catalog_before': raw, 'catalog_after': output_raw, 'files': files, 'snapshot': snapshot,
            'preview': {'title': '撤销整批标记整理', 'items': items, 'counts': {'definitions': len(changed), 'changed': len(files)}},
            'inverse_digest': inverse_digest}


@storage_write
def revert_preview(vault, operation_id):
    try:
        prepared = prepare_revert(vault, operation_id)
        return {'ok': True, 'operation_id': operation_id, 'inverse_digest': prepared['inverse_digest'], **prepared['preview'], 'conflicts': []}
    except RequestError as exc:
        return {'ok': False, 'operation_id': operation_id, 'conflicts': [str(exc)], 'code': exc.code}


@storage_write
def revert(vault, operation_id, inverse_digest, request_id):
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
        raise ValueError('撤销必须提供幂等请求编号')
    recover_pending(vault)
    undo_id = 'undo_' + digest([operation_id, request_id])[:32]
    existing = receipt(vault, undo_id, inverse_digest)
    if existing:
        return {**public_result(existing), 'reused': True}
    prepared = prepare_revert(vault, operation_id)
    if prepared['inverse_digest'] != inverse_digest:
        _conflict('撤销预览后数据发生变化，请重新预览')
    return public_result(execute(vault, prepared, undo_id, inverse_digest, revert_of=operation_id))
