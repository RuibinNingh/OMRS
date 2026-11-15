"""调度首页提醒：默认关闭，正式创建快照与一次导出覆盖。"""
import base64
import hashlib
import json
import os
from pathlib import Path
from . import problem_store as store
from .problem_assets import inspect
from .data_repository import storage_write
from .vault_lifecycle import storage, open_sqlite


def normalize(svg):
    if not isinstance(svg,str) or len(svg.encode())>256*1024:
        raise ValueError('SVG超过256KiB')
    raw=svg.encode('utf-8')
    inspect(raw,banner=True)
    return {'src':'data:image/svg+xml;base64,'+base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'svg':svg}


@storage
def settings(vault):
    with store.connect(vault) as db:
        row=db.execute("SELECT data FROM settings WHERE key='schedule_banner'").fetchone() if db else None
        return json.loads(row[0]) if row else {'enabled':False,'svg':'','snapshot':None,'revision':0}


@storage_write
def save_settings(vault,data):
    current=settings(vault)
    if type(data.get('expected_revision')) is not int or data['expected_revision']!=current['revision']:
        from .problems import ProblemConflict
        raise ProblemConflict('提醒设置已被修改，请重新加载')
    if type(data.get('enabled')) is not bool:
        raise ValueError('enabled必须为布尔值')
    source=data.get('svg','')
    reminder_id=data.get('reminder_id')
    if not isinstance(source,str) or (reminder_id is not None and not isinstance(reminder_id,str)):
        raise ValueError('SVG和素材编号须为字符串')
    if reminder_id:
        from .schedule_reminders import get
        source=get(vault,reminder_id)['snapshot']['svg']
        if reminder_id.startswith('legacy-'):
            reminder_id=None
    value=normalize(source) if source.strip() else None
    if data['enabled'] and not value:
        raise ValueError('启用提醒前请提供SVG')
    result={'enabled':data['enabled'],'svg':source,'snapshot':value if data['enabled'] else None,'revision':current['revision']+1,'reminder_id':reminder_id or None}
    with store.connect(vault,True) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('schedule_banner',?)",(store.dumps(result),))
    return result


@storage
def for_export(vault,session_id='',override=None):
    if override is not None:
        if not isinstance(override,dict) or override.get('mode') not in ('off','current','replace','session','library'):
            raise ValueError('提醒覆盖模式无效')
        mode=override['mode']
        if mode=='off':
            return None
        if mode=='replace':
            return normalize(override.get('svg',''))
        if mode=='library':
            from .schedule_reminders import get
            return normalize(get(vault,override.get('id'))['snapshot']['svg'])
        if mode=='current':
            return settings(vault)['snapshot']
    if not session_id or session_id.startswith('TMP-'):
        return settings(vault)['snapshot']
    target=Path(os.path.abspath(vault))/'错题'/'.omrs'/'ledger.db'
    if not target.exists():
        return None
    with open_sqlite(vault,target.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute("SELECT payload_json FROM commits WHERE commit_type='session.create' ORDER BY seq DESC")
        for row in rows:
            session=json.loads(row[0]).get('session',{})
            if session.get('session_id')==session_id:
                return session.get('schedule_banner')
    return None
