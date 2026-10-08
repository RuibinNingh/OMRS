"""标记整理复用唯一 AI 审核权威、人工修订和正式批准。"""
import copy

from . import ai_review
from .data_repository import storage_write
from .errors import RequestError
from .label_plan import compile_plan
from .label_plan_journal import execute, public_result, receipt, recover_pending
from .label_plan_prepare import prepared_payload

EDITABLE = ['label_changes', 'question_changes', 'excluded_question_ids']


def required_scopes(payload):
    result={'omrs:read','label:write'}
    if any(isinstance(op,dict) and op.get('action') in ('merge','delete') for op in payload.get('label_changes',[])):
        result.add('label:delete')
    return result


def authorize_source(vault, source, owner, payload):
    if source=='mcp':
        from .mcp.keys import active_key
        key=active_key(vault,owner)
        if not key or not required_scopes(payload).issubset(key['scopes']):
            raise RequestError('forbidden','MCP 密钥失效或缺少标记整理权限')


@storage_write
def prepare_proposal(vault, source, owner, plan_id, expected_version):
    payload=prepared_payload(vault,source,owner,plan_id,expected_version)
    authorize_source(vault,source,owner,payload)
    prepared=compile_plan(vault,payload,trusted=True)
    return {key:prepared[key] for key in ('payload','preview','snapshot')}


@storage_write
def propose_mcp(vault,key_id,request_id,plan_id,expected_version,web_url=''):
    from .mcp.common import request_identity
    request={'plan_id':plan_id,'expected_version':expected_version}
    identity,requested_digest=request_identity(key_id,'propose_label_plan',request_id,request)
    previous=ai_review.by_identity(vault,identity)
    if previous:
        if previous['digest']!=requested_digest:raise RequestError('request_conflict','同一请求编号提交内容不同')
        authorize_source(vault,'mcp',key_id,previous['payload'])
        return {**ai_review.public(previous,web_url),'reused':True}
    prepared=prepare_proposal(vault,'mcp',key_id,plan_id,expected_version)
    row=ai_review.create(vault,'mcp','propose_label_plan',identity,**prepared,
                        actor={'key_id':key_id,'request_id':request_id},pending=True,digest=requested_digest,editable_fields=EDITABLE)
    return ai_review.public(row,web_url)


@storage_write
def verify_snapshot(vault,row):
    prepared=compile_plan(vault,row['payload'],trusted=True,allow_cross=True)
    if prepared['snapshot']!=row['snapshot']:
        raise RequestError('content_conflict','预览后定义、题目或级联引用已变化，请重新提出整理方案')
    return prepared


@storage_write
def prepare_revision(vault,row,patch):
    if not isinstance(patch,dict) or set(patch)-set(EDITABLE):
        raise RequestError('forbidden','修订字段超出原提案')
    verify_snapshot(vault,row)
    payload=copy.deepcopy(row['payload'])
    defs={op['change_id']:op for op in payload['label_changes']}
    questions={q['question_id']:q for q in payload['question_changes']}
    if not isinstance(patch.get('label_changes',[]),list) or not isinstance(patch.get('question_changes',[]),list):
        raise ValueError('修订项必须是数组')
    seen=set()
    for edit in patch.get('label_changes',[]):
        if not isinstance(edit,dict) or edit.get('change_id') not in defs or edit['change_id'] in seen:
            raise RequestError('forbidden','不能新增或重复定义操作')
        seen.add(edit['change_id']);op=defs[edit['change_id']]
        allowed={'change_id','enabled'}|({'name','color','order'} if op['action'] in ('create','update') else set())
        if set(edit)-allowed:raise RequestError('forbidden','不能修改原标记目标或操作类型')
        op.update({k:v for k,v in edit.items() if k!='change_id'})
    initial = ai_review.detail(vault, row['operation_id'])['original_payload']
    allowed_refs={op['label_id'] for op in payload['label_changes']}|{op['key'] for op in payload['label_changes'] if op['action']=='create'}
    for op in payload['label_changes']:
        if op.get('into'):allowed_refs.add(op['into'])
    for q in initial['question_changes']:allowed_refs.update(q['add']+q['remove'])
    seen=set()
    for edit in patch.get('question_changes',[]):
        if not isinstance(edit,dict) or edit.get('question_id') not in questions or edit['question_id'] in seen or set(edit)-{'question_id','enabled','add','remove'}:
            raise RequestError('forbidden','不能新增题目、理由或归类字段')
        seen.add(edit['question_id'])
        for key in ('add','remove'):
            if key in edit and (not isinstance(edit[key],list) or any(v not in allowed_refs for v in edit[key])):
                raise RequestError('forbidden','不能引入原方案之外的标记')
        questions[edit['question_id']].update({k:v for k,v in edit.items() if k!='question_id'})
    excluded=patch.get('excluded_question_ids',[])
    if not isinstance(excluded,list) or set(excluded)-{q['question_id'] for q in row['snapshot']['questions']}:
        raise RequestError('forbidden','不能增加原方案之外的题目')
    for qid in excluded:
        if qid in questions:questions[qid]['enabled']=False
        # 定义变更不能留下部分名称引用；排除级联题目同时取消对应定义操作。
        for op in payload['label_changes']:
            preview=next(x for x in row['preview']['label_changes'] if x['change_id']==op['change_id'])
            if qid in preview['affected_question_ids']:op['enabled']=False
    prepared=compile_plan(vault,payload,trusted=True,allow_cross=True)
    if prepared['snapshot']!=row['snapshot']:
        raise RequestError('content_conflict','修订期间目标已变化')
    return {key:prepared[key] for key in ('payload','preview','snapshot')}


@storage_write
def apply_review(vault,row):
    recover_pending(vault)
    saved=receipt(vault,row['operation_id'],row['effective_digest'])
    if saved:return public_result(saved)
    ai_review.verify_question_write(vault,row)
    prepared=verify_snapshot(vault,row)
    saved=execute(vault,prepared,row['operation_id'],row['effective_digest'],source=row['source'],
                  authorize=lambda:ai_review.verify_question_write(vault,row))
    return public_result(saved)
