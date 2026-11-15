"""问题域的统一审核适配；正式写只在原权限与CAS再次核对后发生。"""
import base64
from . import problems, ai_review, problem_store
from .data_repository import storage_write
from .mcp.keys import active_key


def authorize(vault,key_id,write=True):
    key=active_key(vault,key_id)
    needed={'omrs:read','problem:read'} | ({'problem:write'} if write else set())
    if not key or not needed.issubset(key['scopes']):
        raise PermissionError('MCP Key 没有问题域权限或已被吊销')


def snapshot(vault,tool,data):
    if tool not in problems.ACTIONS:
        raise ValueError('不支持的问题操作')
    problems.text(data.get('request_id',''),120,True)
    target={}
    if tool in ('update_problem','link_problem_questions','unlink_problem_questions','revise_reflection_entry'):
        with problem_store.connect(vault) as db:
            target=problem_store.load(db,data.get('id'))
        problems._cas(target,data)
    if tool=='create_problem':
        problems.text(data.get('title',''),160,True)
    if tool=='add_reflection_entry':
        problems._question(vault,data.get('question_id'))
        problems.text(data.get('content_md',''),20000,True)
    if tool=='add_problem_asset':
        from .problem_assets import inspect
        encoded=data.get('data_base64','')
        if not isinstance(encoded,str) or len(encoded)>11200000:
            raise ValueError('附件过大')
        inspect(base64.b64decode(encoded,validate=True))
    return {'target_id':target.get('id'),'revision':target.get('revision')}


def preview(tool,data,vault=None):
    before={}
    if vault and tool in ('update_problem','link_problem_questions','unlink_problem_questions','revise_reflection_entry'):
        with problem_store.connect(vault) as db:
            before=problem_store.load(db,data.get('id'))
            if tool in ('link_problem_questions','unlink_problem_questions'):
                before['question_ids']=[r[0] for r in db.execute('SELECT question_id FROM links WHERE problem_id=?',(data['id'],))]
    safe={k:v for k,v in data.items() if k not in ('data_base64','request_id')}
    result={'message':'问题域操作；AI内容保留假设标记，不改变学习状态。','changes':[{'field':k,'label':{'title':'标题','description_md':'描述','status':'状态','content_md':'错因内容','question_ids':'关联题目','reason':'变更依据'}.get(k,k),'before':before.get(k,''),'after':v} for k,v in safe.items()], 'problem_action':tool}
    if tool=='add_problem_asset':
        from .problem_assets import inspect
        raw=base64.b64decode(data.get('data_base64',''),validate=True)
        _,mime=inspect(raw)
        result['asset']={'src':'data:'+mime+';base64,'+base64.b64encode(raw).decode(),'bytes':len(raw),'mime':mime}
    return result


@storage_write
def propose(vault,key_id,tool,data,web_url):
    authorize(vault,key_id)
    identity='problem:'+ai_review.fingerprint([key_id,tool,data.get('request_id')])
    old=ai_review.by_identity(vault,identity)
    if old:
        if old['digest']!=ai_review.fingerprint(data):
            raise problems.ProblemConflict('同一请求编号对应不同内容')
        return ai_review.public(old,web_url)
    snap=snapshot(vault,tool,data)
    row=ai_review.create(vault,'mcp',tool,identity,data,actor={'kind':'mcp','key_id':key_id},snapshot=snap,
                         preview=preview(tool,data,vault),pending=True,editable_fields=[k for k in ('title','description_md','content_md','status','reason') if k in data])
    return ai_review.public(row,web_url)


def apply_review(vault,row):
    current=ai_review.get(vault,row['operation_id'])
    if current['status']!='applying' or current['effective_digest']!=row['effective_digest']:
        raise ValueError('没有有效的问题写执行许可')
    if row['source']=='mcp':
        authorize(vault,row['key_id'])
    if snapshot(vault,row['tool'],row['payload'])!=row['snapshot']:
        raise problems.ProblemConflict('审核后目标已变化')
    return problems.execute(vault,row['tool'],row['payload'],actor={'kind':row['source'],**row['actor']},review=row)


def decide(vault,row,decision):
    if decision=='reject':
        return ai_review.set_state(vault,row['operation_id'],'rejected')
    try:
        authorize(vault,row['key_id'])
        if snapshot(vault,row['tool'],row['payload'])!=row['snapshot']:
            raise problems.ProblemConflict('人工更新后版本已变化')
        row=ai_review.set_state(vault,row['operation_id'],'applying',expected_status='pending_confirmation')
        result=apply_review(vault,row)
        return ai_review.set_state(vault,row['operation_id'],'applied',result=result)
    except (ValueError,PermissionError) as exc:
        return ai_review.set_state(vault,row['operation_id'],'conflict',error_code=getattr(exc,'code','forbidden'))
