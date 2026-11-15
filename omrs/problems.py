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
WEB_ACTIONS = ('manage_problems',)


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


def _reflection_link(vault,db,pid,qid,actor,now,retained=False):
    value=store.load(db,pid,'problem')
    if value.get('deleted_at') and retained:
        return
    _active(value)
    if _link(vault,db,pid,[qid]):
        value.update(revision=value['revision']+1,updated_at=now)
        store.save(db,'problem',value)
        event={'action':'reflection_link','at':now,'actor':actor,'generation':generation(vault),'reason':'错因记录关联题目','value':value}
        db.execute('INSERT INTO events(object_id,data) VALUES(?,?)',(pid,store.dumps(event)))


def _cas(value, data):
    if type(data.get('expected_revision')) is not int or data['expected_revision'] != value['revision']:
        raise ProblemConflict('内容已变化，请重新读取后再保存；草稿已保留')


def _active(value):
    if value.get('deleted_at'):
        raise ProblemConflict('问题已移入回收站，请恢复后再编辑或关联')


def _manage(vault, db, data, actor, now):
    """整批核对版本后再修改，回收站保留材料、错因与审计。"""
    operation = data.get('operation')
    targets = data.get('items')
    if operation not in ('trash', 'restore', 'status') or not isinstance(targets, list) or not 1 <= len(targets) <= 100:
        raise ValueError('批量操作须包含1至100个问题')
    values, seen = [], set()
    reason = text(data.get('reason', ''), 1000, operation == 'status')
    if operation == 'status' and (not isinstance(data.get('status'), str) or data['status'] not in STATUSES):
        raise ValueError('问题状态无效')
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get('id'), str) or target['id'] in seen:
            raise ValueError('问题身份无效或重复')
        seen.add(target['id'])
        value = store.load(db, target['id'], 'problem')
        _cas(value, target)
        if operation == 'restore':
            if not value.get('deleted_at'):
                raise ProblemConflict('问题已恢复，请刷新列表')
        else:
            _active(value)
        values.append(value)
    for value in values:
        if operation == 'status':
            value['status'] = data['status']
        else:
            value['deleted_at'] = now if operation == 'trash' else None
        value.update(revision=value['revision'] + 1, updated_at=now)
        store.save(db, 'problem', value)
        event = {'action': {'trash': 'trash_problem', 'restore': 'restore_problem', 'status': 'update_problem'}[operation],
                 'at': now, 'actor': actor, 'generation': generation(vault),
                 'reason': reason or ('移入回收站' if operation == 'trash' else '从回收站恢复'), 'value': value}
        db.execute('INSERT INTO events(object_id,data) VALUES(?,?)', (value['id'], store.dumps(event)))
    return values


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
def search(vault, query='', status='', question_id='', limit=50, cursor=0, sort='updated_desc', deleted=''):
    if sort not in ('updated_desc', 'updated_asc', 'title', 'questions_desc') or deleted not in ('', 'only'):
        raise ValueError('排序或回收站筛选无效')
    with store.connect(vault) as db:
        values = [json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='problem'")] if db else []
        if question_id and db:
            linked = {r[0] for r in db.execute('SELECT problem_id FROM links WHERE question_id=?',(question_id,))}
            values = [v for v in values if v['id'] in linked]
        values = [v for v in values if query.casefold() in (v['title']+' '+v['description_md']).casefold()]
        counts = {key: sum(not v.get('deleted_at') and v['status'] == key for v in values) for key in STATUSES}
        counts['all'] = sum(counts.values())
        counts['trash'] = sum(bool(v.get('deleted_at')) for v in values)
        values = [v for v in values if bool(v.get('deleted_at')) == (deleted == 'only') and (not status or v['status'] == status)]
        linked_counts = dict(db.execute('SELECT problem_id, COUNT(*) FROM links GROUP BY problem_id')) if db else {}
        for value in values:
            value['question_count'] = linked_counts.get(value['id'], 0)
        key = {'updated_desc': lambda v: (-v['updated_at'], v['id']), 'updated_asc': lambda v: (v['updated_at'], v['id']),
               'title': lambda v: (v['title'].casefold(), v['id']), 'questions_desc': lambda v: (-v['question_count'], -v['updated_at'], v['id'])}[sort]
        return {**_page(sorted(values, key=key), limit, cursor), 'counts': counts}


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
    if action not in ACTIONS + WEB_ACTIONS or not isinstance(data,dict):
        raise ValueError('不支持的问题操作')
    actor = dict(actor or {'kind':'web'})
    if action in WEB_ACTIONS and actor.get('kind') != 'web':
        raise ValueError('批量管理与回收站操作仅支持用户在网页执行')
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
        if action == 'manage_problems':
            value = _manage(vault, db, data, actor, now)
            kind = 'problems'
        elif action == 'create_problem':
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
            _active(value)
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
            recurrence = data.get('recurrence_of','')
            previous_entry = store.load(db,recurrence,'entry') if recurrence else {}
            if recurrence and previous_entry['question_id'] != qid:
                raise ValueError('再次发生必须引用同一道题的记录')
            for pid in pids:
                _reflection_link(vault,db,pid,qid,actor,now,retained=pid in previous_entry.get('problem_ids',[]))
            occurred = _occurred(data.get('occurred_at'))
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
                    _reflection_link(vault,db,pid,value['question_id'],actor,now,retained=pid in value.get('problem_ids',[]))
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
        if action != 'manage_problems':
            store.save(db,kind,value)
            event = {'action':action,'at':now,'actor':actor,'generation':generation(vault), 'reason':data.get('reason',''), 'value':value}
            db.execute('INSERT INTO events(object_id,data) VALUES(?,?)',(value['id'],store.dumps(event)))
        result = {kind:value,'wrote':True,'request_id':request_id}
        db.execute('INSERT INTO receipts VALUES(?,?,?)',(request_id,digest,store.dumps(result)))
        if review:
            db.execute('INSERT INTO ai_review_receipts VALUES(?,?,?)',(review['operation_id'],review['effective_digest'],store.dumps(result)))
        return result
