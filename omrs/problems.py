"""问题与多次错因；不触碰题目正文、学习状态或调度进度。"""
import datetime
import hashlib
import json
import re
import time
import uuid
from . import problem_store as store
from .data_repository import storage_write, resolve_question
from .vault_lifecycle import storage, generation

STATUSES = {'analyzing':'待分析', 'working':'处理中', 'verifying':'待验证', 'resolved':'已解决', 'parked':'搁置'}
ACTIONS = ('create_problem', 'update_problem', 'link_problem_questions', 'unlink_problem_questions', 'add_reflection_entry', 'revise_reflection_entry', 'add_problem_asset')


class ProblemConflict(ValueError):
    code = 'revision_conflict'
    status = 409


def text(value, maximum=20000, required=False):
    if not isinstance(value, str) or len(value) > maximum or required and not value.strip():
        raise ValueError('文本为空或超过长度限制')
    return value.strip()


def ids(value):
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(v,str) for v in value):
        raise ValueError('关联须为最多100个稳定身份的列表')
    return list(dict.fromkeys(value))


def _question(vault, qid):
    if not isinstance(qid, str) or not re.fullmatch(r'OP-\d+', qid):
        raise ValueError('必须提供稳定 question_id')
    row = resolve_question(vault, question_id=qid, include_archived=True)
    if not row:
        raise ValueError('题目不存在')
    return row


def _link(vault, db, pid, qids):
    count=0
    for qid in ids(qids):
        row = _question(vault, qid)
        count+=db.execute('INSERT OR IGNORE INTO links VALUES(?,?,?)', (pid, qid, row['uid'])).rowcount
    return count


def _reflection_link(vault,db,pid,qid,actor,now):
    value=store.load(db,pid,'problem')
    if _link(vault,db,pid,[qid]):
        value.update(revision=value['revision']+1,updated_at=now)
        store.save(db,'problem',value)
        event={'action':'reflection_link','at':now,'actor':actor,'generation':generation(vault),'reason':'错因记录关联题目','value':value}
        db.execute('INSERT INTO events(object_id,data) VALUES(?,?)',(pid,store.dumps(event)))


def _cas(value, data):
    if type(data.get('expected_revision')) is not int or data['expected_revision'] != value['revision']:
        raise ProblemConflict('内容已变化，请重新读取后再保存；草稿已保留')


def _occurred(value):
    if value in (None,''):
        return None
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('发生日期必须为YYYY-MM-DD或留空')
    return datetime.date.fromisoformat(value).isoformat()


def _page(values, limit=50, cursor=0):
    limit, offset = min(100, max(1,int(limit))), max(0,int(cursor or 0))
    return {'items':values[offset:offset+limit], 'total':len(values), 'next_cursor':str(offset+limit) if offset+limit < len(values) else None}


@storage
def search(vault, query='', status='', question_id='', limit=50, cursor=0):
    with store.connect(vault) as db:
        values = [json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='problem'")] if db else []
        if question_id and db:
            linked = {r[0] for r in db.execute('SELECT problem_id FROM links WHERE question_id=?',(question_id,))}
            values = [v for v in values if v['id'] in linked]
        values = [v for v in values if (not status or v['status']==status) and query.casefold() in (v['title']+' '+v['description_md']).casefold()]
        for value in values:
            value['question_count'] = db.execute('SELECT COUNT(*) FROM links WHERE problem_id=?',(value['id'],)).fetchone()[0]
        return _page(sorted(values,key=lambda v:v['updated_at'],reverse=True),limit,cursor)


@storage
def get(vault, identity):
    with store.connect(vault) as db:
        value = store.load(db, identity, 'problem')
        value['questions'] = []
        for link in db.execute('SELECT * FROM links WHERE problem_id=?',(identity,)):
            row = resolve_question(vault, question_id=link['question_id'], include_archived=True)
            value['questions'].append({'question_id':link['question_id'], 'uid':row['uid'] if row else link['uid'], 'available':bool(row and not row['archived'])})
        value['events'] = [json.loads(r[0]) for r in db.execute('SELECT data FROM events WHERE object_id=? ORDER BY seq DESC LIMIT 100',(identity,))]
        value['entries'] = [json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='entry'") if identity in json.loads(r[0]).get('problem_ids',[])]
        return value


@storage
def reflections(vault, question_id, limit=50, cursor=0):
    with store.connect(vault) as db:
        values = [json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='entry' AND question_id=?",(question_id,))] if db else []
        page = _page(sorted(values,key=lambda v:v['created_at'],reverse=True),limit,cursor)
        for value in page['items']:
            value['revisions']=[json.loads(r[0]) for r in db.execute('SELECT data FROM events WHERE object_id=? ORDER BY seq DESC LIMIT 50',(value['id'],))]
        return page


@storage_write
def execute(vault, action, data, actor=None, review=None):
    if action not in ACTIONS or not isinstance(data,dict):
        raise ValueError('不支持的问题操作')
    actor = dict(actor or {'kind':'web'})
    request_id = text(data.get('request_id',''),120,True)
    digest = hashlib.sha256(store.dumps([action,data,actor]).encode()).hexdigest()
    with store.connect(vault,True) as db:
        previous = db.execute('SELECT digest,result FROM receipts WHERE request_id=?',(request_id,)).fetchone()
        if previous:
            if previous['digest'] != digest:
                raise ProblemConflict('同一请求编号对应不同内容')
            return {**json.loads(previous['result']), 'reused':True}
        now = time.time()
        ai = actor.get('kind') in ('agent','mcp')
        if action == 'create_problem':
            value = {'id':'PRB-'+uuid.uuid4().hex, 'title':text(data.get('title',''),160,True),
                     'description_md':text(data.get('description_md','')), 'status':'analyzing',
                     'subject':text(data.get('subject',''),80), 'basis':'ai_hypothesis' if ai else 'user_confirmed',
                     'revision':1, 'created_at':now, 'updated_at':now, 'source':actor}
            if data.get('status','analyzing') not in STATUSES:
                raise ValueError('问题状态无效')
            value['status'] = data.get('status','analyzing')
            _link(vault, db, value['id'], data.get('question_ids',[]))
            kind = 'problem'
        elif action in ('update_problem','link_problem_questions','unlink_problem_questions'):
            value = store.load(db,data.get('id'),'problem')
            _cas(value,data)
            if action == 'update_problem':
                for key,cap in [('title',160),('description_md',20000),('subject',80)]:
                    if key in data:
                        value[key] = text(data[key],cap,key=='title')
                if 'status' in data and data['status'] != value['status']:
                    if data['status'] not in STATUSES:
                        raise ValueError('问题状态无效')
                    text(data.get('reason',''),1000,True)
                    value['status'] = data['status']
                if 'basis' in data and not ai:
                    if data['basis'] not in ('user_confirmed','ai_hypothesis'):
                        raise ValueError('依据类型无效')
                    text(data.get('reason',''),1000,True)
                    value['basis'] = data['basis']
                if ai and any(k in data for k in ('title','description_md','subject')):
                    value['basis']='ai_hypothesis'
            else:
                qids = ids(data.get('question_ids',[]))
                if action.startswith('unlink'):
                    for qid in qids:
                        db.execute('DELETE FROM links WHERE problem_id=? AND question_id=?',(value['id'],qid))
                else:
                    _link(vault,db,value['id'],qids)
            value['revision'] += 1
            value['updated_at'] = now
            kind = 'problem'
        elif action == 'add_reflection_entry':
            qid = data.get('question_id')
            _question(vault,qid)
            pids = ids(data.get('problem_ids',[]))
            for pid in pids:
                _reflection_link(vault,db,pid,qid,actor,now)
            occurred = _occurred(data.get('occurred_at'))
            recurrence = data.get('recurrence_of','')
            if recurrence and store.load(db,recurrence,'entry')['question_id'] != qid:
                raise ValueError('再次发生必须引用同一道题的记录')
            value = {'id':'REF-'+uuid.uuid4().hex,'question_id':qid, 'content_md':text(data.get('content_md',''),20000,True),
                     'problem_ids':pids,'recurrence_of':recurrence, 'occurred_at':occurred,
                     'created_at':now,'updated_at':now,'revision':1,'withdrawn':False,'source':actor,
                     'basis':'ai_hypothesis' if ai else 'user_confirmed'}
            kind = 'entry'
        elif action == 'revise_reflection_entry':
            value = store.load(db,data.get('id'),'entry')
            _cas(value,data)
            text(data.get('reason',''),1000,True)
            if 'content_md' in data:
                value['content_md'] = text(data['content_md'],20000,True)
            if 'problem_ids' in data:
                pids=ids(data['problem_ids'])
                for pid in pids:
                    _reflection_link(vault,db,pid,value['question_id'],actor,now)
                value['problem_ids']=pids
            if 'withdrawn' in data:
                if type(data['withdrawn']) is not bool:
                    raise ValueError('撤回标志无效')
                value['withdrawn'] = data['withdrawn']
            if 'occurred_at' in data:
                value['occurred_at']=_occurred(data['occurred_at'])
            if 'basis' in data and not ai:
                if data['basis'] not in ('user_confirmed','ai_hypothesis'):
                    raise ValueError('依据类型无效')
                value['basis']=data['basis']
            if ai and value['basis']=='user_confirmed':
                value['basis']='ai_hypothesis'
            value.update(revision=value['revision']+1,updated_at=now)
            kind = 'entry'
        else:
            from .problem_assets import save
            value = save(vault,data)
            kind = 'asset'
        store.save(db,kind,value)
        event = {'action':action,'at':now,'actor':actor,'generation':generation(vault), 'reason':data.get('reason',''), 'value':value}
        db.execute('INSERT INTO events(object_id,data) VALUES(?,?)',(value['id'],store.dumps(event)))
        result = {kind:value,'wrote':True,'request_id':request_id}
        db.execute('INSERT INTO receipts VALUES(?,?,?)',(request_id,digest,store.dumps(result)))
        if review:
            db.execute('INSERT INTO ai_review_receipts VALUES(?,?,?)',(review['operation_id'],review['effective_digest'],store.dumps(result)))
        return result
