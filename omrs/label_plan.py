"""标记整理的共享校验与预览；准备/读取不修改正式定义或题目。"""
import copy
import json
import os
import re
import uuid

from . import labels
from .common import extract_labels, parse_yaml_frontmatter
from .content_history import check_content_reconcile
from .data_repository import resolve_question, storage_write
from .errors import RequestError
from .ledger import blob_hash, canonical_json, connect
from .question_update import _read, _replace_yaml, editable_values
from .vault_lifecycle import generation

MAX_QUESTIONS = 1000
MAX_DEFINITIONS = 100


def digest(value):
    return blob_hash(canonical_json(value))


def text(value, field, limit=2000, empty=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value if c not in '\n\t'):
        raise ValueError(f'{field} 必须是有效文字，最多 {limit} 字符')
    value = value.strip()
    if not value and not empty:
        raise ValueError(f'{field} 不能为空')
    return value


def catalog(vault):
    """定义文件损坏时拒绝写入，不能把旧宽容读取的空结果当成事实。"""
    path = labels.labels_path(vault)
    if os.path.islink(path) or os.path.islink(os.path.dirname(path)):
        raise RequestError('content_conflict', '标记定义路径不能是链接')
    try:
        with open(path, encoding='utf-8', newline='') as file:
            raw = file.read()
        data = json.loads(raw)
    except FileNotFoundError:
        return {'version': 1, 'labels': []}, None
    except (ValueError, OSError) as exc:
        raise RequestError('content_conflict', '标记定义不可读取，请先核对文件') from exc
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('labels'), list):
        raise RequestError('content_conflict', '标记定义格式不合法')
    ids, names = set(), set()
    for item in data['labels']:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] or
                not isinstance(item.get('name'), str) or labels._clean_name(item['name']) != item['name'] or
                item['id'] in ids or item['name'] in names):
            raise RequestError('content_conflict', '标记定义有缺失身份或重复名称')
        ids.add(item['id'])
        names.add(item['name'])
    return data, raw


def normalize(payload, trusted=False):
    if not isinstance(payload, dict) or set(payload) - {'scope', 'reason', 'label_changes', 'question_changes'}:
        raise ValueError('标记整理参数包含未开放的字段')
    scope = payload.get('scope') or {}
    if not isinstance(scope, dict) or set(scope) - {'subject', 'category', 'question_ids'}:
        raise ValueError('scope 只允许 subject、category、question_ids')
    scope = {key: text(scope.get(key, ''), key, 200, True) for key in ('subject', 'category')} | {
        'question_ids': _strings(scope.get('question_ids') or [], 'scope.question_ids', MAX_QUESTIONS)}
    raw_ops, raw_questions = payload.get('label_changes') or [], payload.get('question_changes') or []
    if (not isinstance(raw_ops, list) or len(raw_ops) > MAX_DEFINITIONS or
            not isinstance(raw_questions, list) or len(raw_questions) > MAX_QUESTIONS):
        raise ValueError('整批最多一百个定义操作和一千道显式题目')
    ops, seen, keys, sources = [], set(), set(), set()
    allowed = {'action', 'change_id', 'label_id', 'key', 'name', 'color', 'order', 'into', 'reason', 'enabled'}
    if trusted:
        allowed |= {'cross_scope', 'detach', 'priority_bonus', 'created_at'}
    for index, raw in enumerate(raw_ops):
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise ValueError('定义操作包含未开放字段')
        op = copy.deepcopy(raw)
        action = op.get('action')
        if action not in ('create', 'update', 'merge', 'delete'):
            raise ValueError('action 只允许 create、update、merge、delete')
        op['change_id'] = text(op.get('change_id', f'L{index + 1}'), 'change_id', 100)
        if op['change_id'] in seen:
            raise ValueError('定义操作编号重复')
        seen.add(op['change_id'])
        if type(op.get('enabled', True)) is not bool:
            raise ValueError('enabled 必须是布尔值')
        op['enabled'] = op.get('enabled', True)
        op['reason'] = text(op.get('reason', ''), 'reason', 2000, True)
        if action == 'create':
            op['key'] = text(op.get('key', ''), 'key', 100)
            if op['key'] in keys:
                raise ValueError('新标记引用重复')
            keys.add(op['key'])
            if not trusted and 'label_id' in op:
                raise ValueError('新标记稳定 ID 由服务端分配')
            op['label_id'] = op.get('label_id') or 'LB-' + uuid.uuid4().hex
            op['created_at'] = op.get('created_at') or labels._now()
        else:
            op['label_id'] = text(op.get('label_id', ''), 'label_id', 200)
            if op['label_id'] in sources:
                raise ValueError('同一标记不能重复编辑、合并或删除')
            sources.add(op['label_id'])
        if action in ('create', 'update'):
            if action == 'create' or 'name' in op:
                op['name'] = labels._clean_name(text(op.get('name', ''), 'name', 80))
            if 'color' in op:
                if not isinstance(op['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', op['color']):
                    raise ValueError('color 必须是十六进制颜色')
                op['color'] = labels._clean_color(op['color'])
            if 'order' in op and (type(op['order']) is not int or op['order'] < 1):
                raise ValueError('order 必须是正整数')
        if action == 'merge':
            op['into'] = text(op.get('into', ''), 'into', 200)
        ops.append(op)
    questions, qids = [], set()
    for raw in raw_questions:
        if not isinstance(raw, dict) or set(raw) - {'question_id', 'expected_content_hash', 'add', 'remove', 'reason', 'enabled', 'uncertain_reason'}:
            raise ValueError('逐题方案包含未开放字段')
        q = copy.deepcopy(raw)
        q['question_id'] = text(q.get('question_id', ''), 'question_id', 200)
        if q['question_id'] in qids:
            raise ValueError('同一道题重复出现在方案中')
        qids.add(q['question_id'])
        if not isinstance(q.get('expected_content_hash'), str) or not re.fullmatch('[0-9a-f]{64}', q['expected_content_hash']):
            raise ValueError('逐题归类必须提供读取时的正文哈希')
        if type(q.get('enabled', True)) is not bool:
            raise ValueError('逐题 enabled 必须是布尔值')
        q.update(add=_strings(q.get('add') or [], 'add', 64), remove=_strings(q.get('remove') or [], 'remove', 64),
                 reason=text(q.get('reason', ''), 'reason', 2000, True), enabled=q.get('enabled', True),
                 uncertain_reason=text(q.get('uncertain_reason', ''), 'uncertain_reason', 2000, True))
        if set(q['add']) & set(q['remove']):
            raise ValueError('同一标记不能同时添加和移除')
        if q['uncertain_reason'] and (q['add'] or q['remove']):
            raise ValueError('待判断题目不能同时执行打标')
        questions.append(q)
    if not ops and not questions:
        raise ValueError('标记整理方案不能为空')
    return {'scope': scope, 'reason': text(payload.get('reason', '整理题目标记'), 'reason'),
            'label_changes': ops, 'question_changes': questions}


def _strings(values, field, cap):
    if not isinstance(values, list) or len(values) > cap:
        raise ValueError(f'{field} 数组超过上限或类型不合法')
    result = [text(value, field, 200) for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f'{field} 有重复值')
    return result


def in_scope(row, scope):
    return (not scope.get('subject') or row['subject'] == scope['subject']) and (
        not scope.get('category') or row['category'] == scope['category']) and (
        not scope.get('question_ids') or row['question_id'] in scope['question_ids'])


@storage_write
def compile_plan(vault, payload, *, trusted=False, allow_cross=False):
    payload = normalize(payload, trusted)
    before_catalog, raw_catalog = catalog(vault)
    originals = {d['id']: copy.deepcopy(d) for d in before_catalog['labels']}
    active = {k: d for k, d in originals.items() if not d.get('archived')}
    definitions = copy.deepcopy(originals)
    refs = {k: k for k in active}
    ops = payload['label_changes']
    for op in ops:
        if op['action'] == 'create':
            if op['key'] in refs or op['label_id'] in definitions:
                raise ValueError('新标记引用与已有 ID 冲突')
            refs[op['key']] = op['label_id']
            refs[op['label_id']] = op['label_id']
        elif op['label_id'] not in active:
            raise ValueError('只能管理当前存在的未归档标记')
    def ref(value):
        if value not in refs:
            raise ValueError(f'标记引用不存在：{value}')
        return refs[value]
    merges, deleted = {}, set()
    for op in ops:
        if op['action'] == 'merge':
            op['into'] = ref(op['into'])
            merges[op['label_id']] = op['into']
        if op['action'] == 'delete':
            deleted.add(op['label_id'])
    for key in merges:
        visited, target = set(), key
        while target in merges:
            if target in visited:
                raise ValueError('合并不能形成自环或循环')
            visited.add(target)
            target = merges[target]
        if target in deleted:
            raise ValueError('合并目标不能同时删除')
    source_names = {active[op['label_id']]['name'] for op in ops if op['action'] != 'create'}
    qchanges = {q['question_id']: q for q in payload['question_changes']}
    rows, contents, references = {}, {}, {op['label_id']: [] for op in ops if op['action'] != 'create'}
    with connect(vault) as db:
        candidates = [dict(r) for r in db.execute('SELECT * FROM question_projection WHERE archived=0 ORDER BY question_id')]
    for row in candidates:
        qid = row['question_id']
        if not source_names and qid not in qchanges:
            continue
        content, owner = _read(vault, row)
        names = extract_labels(parse_yaml_frontmatter(content))
        relevant = bool(source_names & set(names)) or qid in qchanges
        if not relevant:
            continue
        rows[qid], contents[qid] = row, (content, owner, names)
        check_content_reconcile(vault, row, content)
        if blob_hash(content) != row.get("content_hash"):
            raise RequestError("content_conflict", "题目含未扫描的修改，请先重新扫描再整理")
        for op in ops:
            if op['action'] != 'create' and active[op['label_id']]['name'] in names:
                references[op['label_id']].append(qid)
        if qid in qchanges:
            if not in_scope(row, payload['scope']):
                raise ValueError('显式归类题目超出方案范围')
            if blob_hash(content) != qchanges[qid]['expected_content_hash']:
                raise RequestError('content_conflict', '题目在读取与组装之间已变化')
    if set(qchanges) - rows.keys():
        raise RequestError('not_found', '归类题目已归档或不存在')
    previews = []
    for op in ops:
        action, key = op['action'], op['label_id']
        affected = references.get(key, [])
        cascade = action in ('merge', 'delete') or (action == 'update' and op.get('name', active[key]['name']) != active[key]['name'])
        cross = cascade and any(not in_scope(rows[qid], payload['scope']) for qid in affected)
        op['cross_scope'] = bool(cross)
        if cross and not allow_cross:
            op['enabled'] = False
        original = originals.get(key)
        after = copy.deepcopy(original)
        if action == 'create':
            after = {'id': key, 'name': op['name'], 'color': op.get('color', labels.DEFAULT_COLOR),
                     'order': op.get('order', max([d.get('order', 0) for d in definitions.values()] or [0]) + 1),
                     'priority_bonus': op.get('priority_bonus', 0) if trusted else 0.0,
                     'archived': False, 'created_at': op['created_at']}
        elif action == 'update':
            after.update({k: op[k] for k in ('name', 'color', 'order') if k in op})
            if trusted and 'priority_bonus' in op:
                after['priority_bonus'] = op['priority_bonus']
        if action in ('create', 'update') and op['enabled']:
            definitions[key] = after
        previews.append({**copy.deepcopy(op), 'before': original, 'after': after if action in ('create', 'update') else None,
                         'affected_count': len(affected), 'affected_question_ids': affected,
                         'affected_subjects': sorted({rows[qid]['subject'] for qid in affected}),
                         'target_id': op.get('into', '')})
    enabled_merges = {op['label_id']: op['into'] for op in ops if op['action'] == 'merge' and op['enabled']}
    enabled_deleted = {op['label_id'] for op in ops if op['action'] == 'delete' and op['enabled']}
    def target(key):
        while key in enabled_merges:
            key = enabled_merges[key]
        return key
    for key in enabled_merges:
        if target(key) not in definitions or target(key) in enabled_deleted:
            raise ValueError('合并目标的创建已取消或目标被删除')
    name_ids = {d['name']: k for k, d in originals.items()}
    detached = {op['label_id'] for op in ops if op['action'] == 'delete' and op.get('detach', True) is False}
    final_definitions = {k: d for k, d in definitions.items() if k not in enabled_merges and k not in enabled_deleted}
    names = [d['name'] for d in final_definitions.values()]
    if len(names) != len(set(names)):
        raise ValueError('最终标记名称重复，请复用已有标记或先合并')
    items, files = [], []
    for qid, row in rows.items():
        content, owner, before = contents[qid]
        after = []
        for name in before:
            key = name_ids.get(name)
            if key in enabled_deleted and key not in detached:
                continue
            root = target(key)
            after.append(definitions[root]['name'] if root in definitions and key not in detached else name)
        q = qchanges.get(qid)
        selected = bool(q and q['enabled'] and not q['uncertain_reason'])
        if q:
            add, remove = [ref(v) for v in q['add']], [ref(v) for v in q['remove']]
            missing = set(add + remove) - final_definitions.keys()
            if missing:
                cancelled_creations = {op['label_id'] for op in ops if op['action'] == 'create' and not op['enabled']}
                if missing.issubset(cancelled_creations):
                    q['enabled'], selected = False, False
                else:
                    raise ValueError('逐题归类不能引用已经合并或删除的标记')
            if selected:
                removing = {final_definitions[k]['name'] for k in remove}
                after = [name for name in after if name not in removing]
                after.extend(final_definitions[k]['name'] for k in add)
        after = list(dict.fromkeys(after))
        updated = _replace_yaml(content, '标记', after) if before != after else content
        item = {'question_id': qid, 'uid': row['uid'], 'subject': row['subject'], 'category': row['category'],
                'before': before, 'after': after, 'reason': q.get('reason', '') if q else '标记定义级联变更',
                'uncertain_reason': q.get('uncertain_reason', '') if q else '', 'enabled': q.get('enabled', True) if q else True,
                'explicit': q is not None, 'cross_scope': not in_scope(row, payload['scope']), 'changed': updated != content}
        items.append(item)
        if updated != content:
            files.append({'row': row, 'before': content, 'after': updated, 'owner': owner})
    if len(files) > MAX_QUESTIONS:
        raise ValueError('实际受影响题目超过一千道，未截断或执行；请缩小整理范围')
    after_catalog = copy.deepcopy(before_catalog)
    after_catalog['labels'] = sorted(final_definitions.values(), key=lambda d: (d.get('order', 0), d.get('created_at', ''), d['name']))
    summary = {'definitions': sum(op['enabled'] for op in ops), 'questions': len(items), 'changed': len(files),
               'uncertain': sum(bool(i['uncertain_reason']) for i in items), 'cross_scope': sum(p['cross_scope'] for p in previews)}
    snapshot = {'generation': generation(vault), 'catalog_hash': blob_hash(raw_catalog) if raw_catalog is not None else None,
                'questions': [{'question_id': qid, 'file_path': rows[qid]['file_path'], 'content_hash': blob_hash(contents[qid][0])} for qid in sorted(rows)],
                'references': references}
    return {'payload': payload, 'snapshot': snapshot,
            'preview': {'title': '整批整理标记', 'summary': f"{summary['definitions']} 项定义操作 · {summary['changed']} 道题变更", 'scope': payload['scope'],
                        'reason': payload['reason'], 'counts': summary, 'label_changes': previews, 'items': items},
            'catalog_before': raw_catalog,
            'catalog_after': json.dumps(after_catalog, ensure_ascii=False, indent=2) if before_catalog != after_catalog else raw_catalog,
            'files': files}


@storage_write
def apply_web(vault, changes):
    """既有人工管理入口使用同一可靠批次；不借用 AI 身份或审批。"""
    from .label_plan_journal import execute, recover_pending
    recover_pending(vault)
    normalized = normalize({'label_changes': changes}, trusted=True)
    prepared = compile_plan(vault, normalized, trusted=True, allow_cross=True)
    result = execute(vault, prepared, 'web_' + uuid.uuid4().hex, digest(prepared['payload']))
    return prepared, result
