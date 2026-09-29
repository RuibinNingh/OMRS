"""内容评测只读索引与追加式复核；不加载训练框架、不更改标签。"""
import datetime
import json
from pathlib import Path
import sqlite3

from .trainpanel import safe_path, read_json, train_dir

VERDICTS = ('usable', 'needs_adjustment', 'unusable', 'uncertain')


class Conflict(ValueError):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def audit(root, ident):
    path = safe_path(root, 'audits', ident, 'audit.json')
    value, error = read_json(path)
    if error or not value or not isinstance(value.get('cases'), list):
        raise ValueError(error or '评测不存在')
    return value


def reviews(root, ident, case=None):
    path = safe_path(root, 'reviews.sqlite3')
    if not path.exists():
        return []
    db = sqlite3.connect(path.as_uri() + '?mode=ro', timeout=5)
    db.row_factory = sqlite3.Row
    try:
        sql = 'SELECT * FROM reviews WHERE audit=?'
        args = [ident]
        if case is not None:
            sql += ' AND case_id=?'; args.append(case)
        return [dict(row) for row in db.execute(sql + ' ORDER BY revision', args)]
    finally:
        db.close()


def result(root, ident, case):
    value, error = read_json(safe_path(root, 'audits', ident, case + '.json'))
    return value or {'state': 'pending', 'error': error}


def effective(record, history):
    user = [h for h in history if h['source'] == 'user']
    selected = (user or history)
    return selected[-1]['verdict'] if selected else record.get('judgment', {}).get('verdict', 'uncertain')


def summary(root, ident):
    data = audit(root, ident)
    history = reviews(root, ident)
    grouped, states = {}, {}
    reviewed = user_reviewed = 0
    seconds = total_cost = 0
    confusion = {}
    for c in data['cases']:
        r = result(root, ident, c['id']); states[r['state']] = states.get(r['state'], 0) + 1
        h = [x for x in history if x['case_id'] == c['id']]
        reviewed += bool(h); user_reviewed += any(x['source'] == 'user' for x in h)
        seconds += r.get('seconds',0); total_cost += r.get('cost_usd',0)
        if h:
            pair = r.get('judgment',{}).get('verdict','error') + '→' + effective(r,h)
            confusion[pair] = confusion.get(pair,0)+1
        grouped.setdefault(c['sample'], []).append((c, r, h))
    raw = final = missing = extra = 0
    for entries in grouped.values():
        complete = {c['role'] for c, _, _ in entries} >= {'question', 'answer'}
        def passed(c, r, h, corrected):
            verdict = effective(r, h) if corrected else r.get('judgment', {}).get('verdict')
            # 缺框和额外框是检测结构事实；纠正文字判定不能补出图片。
            return not c.get('structural_error') and verdict == 'usable' and (bool(h) or r['state'] in ('done', 'cached'))
        raw += complete and all(passed(c,r,[],False) for c,r,h in entries)
        final += complete and all(passed(c,r,h,True) for c,r,h in entries)
        missing += any(c.get('structural_error') == 'missing' or effective(r,h) == 'unusable' for c,r,h in entries)
        extra += any(c.get('structural_error') == 'extra' or effective(r,h) == 'needs_adjustment' for c,r,h in entries)
    progress, error = read_json(safe_path(root, 'audits', ident, 'progress.json'))
    return {'progress': progress, 'progress_error': error, **{k: data.get(k) for k in ('id','dataset','split','purpose','model','prompt_version','created_at','conf')}} | {
        'images': len(grouped), 'cases': len(data['cases']), 'raw_passed': raw, 'reviewed_passed': final,
        'reviewed': reviewed, 'user_reviewed': user_reviewed, 'cost_usd':total_cost, 'seconds':seconds, 'confusion':confusion, 'missing_images': missing, 'extra_images': extra, 'states': states}


def list_audits(vault):
    root = train_dir(vault); folder = safe_path(root, 'audits')
    items, errors = [], []
    for p in sorted(folder.glob('*/audit.json'), reverse=True)[:200]:
        try:
            items.append(summary(root, p.parent.name))
        except (ValueError, OSError, sqlite3.Error) as exc:
            errors.append({'id': p.parent.name, 'error': str(exc)})
    return {'audits': items, 'errors': errors}


def detail(vault, ident, params):
    root = train_dir(vault); data = audit(root, ident); history = reviews(root, ident)
    rows = []
    for c in data['cases']:
        r = result(root, ident, c['id']); h = [x for x in history if x['case_id'] == c['id']]
        judgment = r.get('judgment', {})
        row = dict(c, state=r['state'], judgment=judgment, review=([x for x in h if x['source']=='user'] or h)[-1] if h else None,
                   effective=effective(r,h), revision=max((x['revision'] for x in h), default=0),
                   seconds=r.get('seconds',0), usage=r.get('usage',{}), cost_usd=r.get('cost_usd',0), error=r.get('error'))
        if params.get('case') and c['id'] != params['case']: continue
        if params.get('role') and params['role'] != c['role']: continue
        if params.get('verdict') and params['verdict'] != judgment.get('verdict', 'uncertain'): continue
        state = params.get('review', '')
        if state == 'pending' and h: continue
        if state == 'disagreed' and (not h or effective(r,h) == judgment.get('verdict')): continue
        if state == 'reviewed' and not h: continue
        rows.append(row)
    rows.sort(key=lambda c: (bool(c['review']), c['state'] not in ('error','missing'), c['effective']=='usable', c['id']))
    offset = max(0, int(params.get('offset',0))); limit = min(100, max(1,int(params.get('limit',30))))
    return {'audit': summary(root, ident), 'total': len(rows), 'cases': rows[offset:offset+limit]}


def image_path(vault, ident, resource):
    root = train_dir(vault); data = audit(root, ident)
    name = data.get('resources', {}).get(resource)
    if not name:
        raise ValueError('图片未登记')
    path = safe_path(root, 'audits', ident, 'images', name)
    if path.suffix.lower() not in ('.png','.jpg','.jpeg') or path.stat().st_size > 30*1024*1024:
        raise ValueError('图片格式或大小不合法')
    return path


def save_review(root, ident, case_id, revision, action, verdict=None, note='', source='user'):
    data = audit(root, ident)
    if not any(c['id'] == case_id for c in data['cases']): raise ValueError('案例不存在')
    if action not in ('agree','correct','uncertain') or source not in ('user','executor'):
        raise ValueError('复核类型不合法')
    raw = result(root, ident, case_id).get('judgment',{}).get('verdict')
    verdict = raw if action == 'agree' else ('uncertain' if action == 'uncertain' else verdict)
    if verdict not in VERDICTS or not isinstance(note,str) or len(note)>2000 or type(revision) is not int:
        raise ValueError('判定、说明或版本不合法')
    db = sqlite3.connect(safe_path(root, 'reviews.sqlite3'), timeout=5)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS reviews (audit TEXT, case_id TEXT, revision INTEGER, action TEXT, verdict TEXT, note TEXT, source TEXT, created_at TEXT, PRIMARY KEY(audit,case_id,revision))')
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT COALESCE(MAX(revision),0) FROM reviews WHERE audit=? AND case_id=?',(ident,case_id)).fetchone()[0]
        if current != revision: raise Conflict('复核已被修改，请刷新后重试')
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?)',(ident,case_id,current+1,action,verdict,note,source,now()))
        db.commit()
        return {'revision': current+1, 'verdict':verdict}
    finally:
        db.close()
