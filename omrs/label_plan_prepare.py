"""来源与世代绑定的有界技术草稿；准备不产生业务待审或正式数据。"""
import copy
import json
import os
import time
import uuid

from .common import extract_knowledge_tags, parse_yaml_frontmatter
from .data_repository import storage_read, storage_write
from .errors import RequestError
from .label_plan import catalog, digest, in_scope, normalize, text
from .ledger import blob_hash, connect
from .question_update import _read
from .vault_lifecycle import generation

TTL = 1800
_DRAFTS = {}
MAX_DRAFTS = 64
MAX_BYTES = 16 * 1024 * 1024


def _owner(vault, source, owner):
    if source not in ('agent', 'mcp') or not isinstance(owner, str) or not owner:
        raise RequestError('forbidden', '准备方案缺少可信来源')
    return (os.path.realpath(vault), generation(vault), source, owner)


def _prune():
    now = time.monotonic()
    for key, value in list(_DRAFTS.items()):
        if now - value['updated'] >= TTL:
            del _DRAFTS[key]


def _get(vault, source, owner, plan_id):
    _prune()
    draft = _DRAFTS.get(plan_id)
    if not draft or draft['owner'] != _owner(vault, source, owner):
        raise RequestError('plan_expired', '准备方案不存在、已到期或不属于当前来源，请重新准备')
    return draft


def _view(plan_id, draft):
    p = draft['payload']
    return {'plan_id': plan_id, 'version': draft['version'], 'staged_questions': len(p['question_changes']),
            'staged_definitions': len(p['label_changes']), 'fragments': len(draft['fragments']),
            'scope': p['scope'], 'expires_in_seconds': TTL, 'wrote': False,
            'message': '只保存准备进度；完成全部分片后调用 propose_label_plan 统一确认。'}


@storage_write
def stage(vault, source, owner, fragment_id, payload, plan_id='', expected_version=0):
    fragment_id = text(fragment_id, 'fragment_id', 100)
    if not isinstance(payload, dict) or len(payload.get('question_changes') or []) > 50:
        raise ValueError('每个准备分片最多五十道显式题目')
    fragment_digest = digest(payload)
    from .label_plan_review import authorize_source
    authorize_source(vault, source, owner, payload)
    binding = _owner(vault, source, owner)
    _prune()
    new = not plan_id
    if new:
        # 首片响应丢失后用同一来源与分片编号恢复，不能静默新建另一草稿。
        for key, draft in _DRAFTS.items():
            if draft['owner'] == binding and draft['first_fragment'] == fragment_id:
                if draft['fragments'][fragment_id] != fragment_digest:
                    raise RequestError('request_conflict', '同一首分片编号内容不同')
                return {**_view(key, draft), 'reused': True}
        if expected_version != 0 or len(_DRAFTS) >= MAX_DRAFTS:
            raise RequestError('plan_limit', '准备版本不正确或草稿数量已满')
        plan_id = 'lp_' + uuid.uuid4().hex
        draft = {'owner': binding, 'version': 0, 'fragments': {}, 'first_fragment': fragment_id,
                 'updated': time.monotonic(), 'payload': {'scope': payload.get('scope', {}), 'reason': payload.get('reason','整理题目标记'), 'label_changes': [], 'question_changes': []}}
    else:
        draft = _get(vault, source, owner, plan_id)
    if fragment_id in draft['fragments']:
        if draft['fragments'][fragment_id] != fragment_digest:
            raise RequestError('request_conflict', '相同分片编号内容不同')
        draft['updated'] = time.monotonic()
        return {**_view(plan_id, draft), 'reused': True}
    if type(expected_version) is not int or expected_version != draft['version']:
        raise RequestError('revision_conflict', '准备版本已变化，不能覆盖后续分片')
    raw = copy.deepcopy(payload)
    for index, op in enumerate(raw.get('label_changes') or []):
        op.setdefault('change_id', fragment_id + ':' + str(index+1))
    clean = normalize(raw)
    if not new and ('scope' in payload and clean['scope'] != draft['payload']['scope'] or
                    'reason' in payload and clean['reason'] != draft['payload']['reason']):
        raise ValueError('后续分片不能改变整理范围或目标')
    combined = copy.deepcopy(draft['payload'])
    if new: combined['scope'] = clean['scope']
    combined['label_changes'].extend(clean['label_changes']); combined['question_changes'].extend(clean['question_changes'])
    combined = normalize(combined, trusted=True)
    authorize_source(vault, source, owner, combined)
    size = len(json.dumps(combined,ensure_ascii=False).encode())
    total = sum(len(json.dumps(d['payload'],ensure_ascii=False).encode()) for key,d in _DRAFTS.items() if key != plan_id)
    if size + total > MAX_BYTES:
        raise RequestError('plan_limit', '准备草稿总量超过上限')
    draft = {**draft, 'payload': combined, 'version': draft['version']+1,
             'fragments': {**draft['fragments'], fragment_id: fragment_digest}, 'updated': time.monotonic()}
    _DRAFTS[plan_id] = draft
    return _view(plan_id, draft)


@storage_write
def prepared_payload(vault, source, owner, plan_id, expected_version):
    draft = _get(vault, source, owner, plan_id)
    if type(expected_version) is not int or expected_version != draft['version']:
        raise RequestError('revision_conflict', '提交版本与准备进度不一致')
    draft['updated'] = time.monotonic()
    return copy.deepcopy(draft['payload'])


@storage_read
def list_labels(vault, cursor='', limit=10):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('每页标记数量为 1 到 100')
    data, raw = catalog(vault)
    values = [d for d in data['labels'] if not d.get('archived')]
    try: offset = int(cursor or '0')
    except (TypeError, ValueError): raise ValueError('分页游标不合法') from None
    if offset < 0: raise ValueError('分页游标不合法')
    with connect(vault) as db:
        counts = {r['label']:r['n'] for r in db.execute('SELECT label,COUNT(*) n FROM question_labels JOIN question_projection USING(question_id) WHERE archived=0 GROUP BY label')}
    result = [{**d,'count':counts.get(d['name'],0)} for d in values[offset:offset+limit]]
    return {'items':result,'total':len(values),'next_cursor':str(offset+limit) if offset+limit<len(values) else None,
            'definition_digest':blob_hash(raw) if raw is not None else None}


@storage_read
def candidates(vault, scope=None, label_ids=None, cursor='', limit=20):
    from .agent.tools.common import sections_of, image_names
    scope = scope or {}
    if not isinstance(scope,dict) or set(scope)-{'subject','category','question_ids'}:
        raise ValueError('候选范围字段不正确')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('候选每页最多二十题')
    for key in ('subject','category'):text(scope.get(key,''),key,200,True)
    ids=scope.get('question_ids') or []
    if not isinstance(ids,list) or len(ids)>1000 or any(not isinstance(v,str) for v in ids):raise ValueError('候选身份数组不合法')
    data,_=catalog(vault); defs={d['id']:d for d in data['labels'] if not d.get('archived')}
    label_ids=label_ids or []
    if not isinstance(label_ids,list) or set(label_ids)-defs.keys():raise ValueError('候选标记 ID 不存在')
    with connect(vault) as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM question_projection WHERE archived=0 ORDER BY question_id')]
        labels_by_q={}
        for row in db.execute('SELECT question_id,label FROM question_labels'):labels_by_q.setdefault(row['question_id'],set()).add(row['label'])
    rows=[r for r in rows if in_scope(r,scope) and all(defs[k]['name'] in labels_by_q.get(r['question_id'],set()) for k in label_ids)]
    signature=digest({'scope':scope,'label_ids':label_ids})[:16]
    offset=0
    if cursor:
        try:
            sig,number=cursor.split(':');offset=int(number)
            if sig!=signature or offset<0:raise ValueError()
        except (ValueError,AttributeError):raise ValueError('候选游标与筛选范围不一致') from None
    out=[]
    for row in rows[offset:offset+limit]:
        content,_=_read(vault,row);parts=sections_of(content);meta=parse_yaml_frontmatter(content)
        limits={'题目':1000,'答案':650,'错因':400}
        summary={k:v[:limits[k]] for k,v in parts.items()}
        item={key:row[key] for key in ('question_id','uid','subject','category','suspended')}
        item.update(content_hash=blob_hash(content),summary=summary,knowledge_points=extract_knowledge_tags(meta),
                    images=image_names(content),truncated=any(len(v)>limits[k] for k,v in parts.items()),
                    labels=sorted(labels_by_q.get(row['question_id'],set())))
        if len(json.dumps({'items':out+[item]},ensure_ascii=False)) > 21500:
            if not out:
                item.update(knowledge_points=[],images=[],labels=[]);item['truncated']=True
            else:break
        out.append(item)
    more=offset+len(out)<len(rows)
    return {'items':out,'total':len(rows),'next_cursor':f'{signature}:{offset+len(out)}' if more else None,
            'analyzed_range':{'offset':offset,'count':len(out)},'message':'摘要截断或图片信息不足时读取完整题面；不能猜测错因。'}
