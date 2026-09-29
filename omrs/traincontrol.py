"""受管检测服务：部署者显式登记，异步串行操作与持久化回退。"""
try:
    import fcntl
except ImportError:  # Windows主程序仍可运行，只禁用本机systemd控制。
    fcntl = None
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid

from . import trainpanel, trainaudit

UNIT = 'omrs-boxdetect.service'
ACTIONS = ('start', 'stop', 'restart', 'activate', 'rollback')


class Conflict(ValueError):
    pass


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def registration(vault):
    name = os.environ.get('OMRS_BOXDETECT_CONTROL')
    if fcntl is None or not name or not Path('/run/systemd/system').exists() or not Path('/usr/bin/systemctl').exists(): return None
    data = json.loads(Path(name).read_text())
    # 配置只来自进程环境指定文件，网页配置无法授予systemd权限。
    if Path(data['vault']).resolve() != Path(vault).resolve(): return None
    if Path(data['root']).resolve() != trainpanel.train_dir(vault): return None
    if data.get('unit') != UNIT or type(data.get('port')) is not int or not 1024 <= data['port'] <= 65535:
        raise ValueError('受管服务登记不合法')
    if trainpanel.config(vault).get('inbox_local_detect_url') != f"http://127.0.0.1:{data['port']}/detect":
        raise ValueError('本地检测地址与受管服务登记不一致')
    return data


class SystemdBackend:
    def __init__(self, config): self.config = config

    def command(self, action):
        if action not in ('start','stop','restart'): raise ValueError('服务操作不合法')
        subprocess.run(['/usr/bin/systemctl', action, UNIT], check=True, capture_output=True, timeout=25)

    def active(self):
        return subprocess.run(['/usr/bin/systemctl','is-active','--quiet',UNIT], timeout=5).returncode == 0

    def health(self):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.config['port']}/health", timeout=2) as response:
                value = json.loads(response.read(4096))
                return value if isinstance(value,dict) else None
        except (OSError, ValueError): return None

    def preflight(self, folder):
        from tools.boxdetect.train import memory_available
        if memory_available() < 2 * 1024**3: raise ValueError('可用内存不足2GiB，暂不预检或切换模型')
        unit = 'omrs-boxdetect-check-' + uuid.uuid4().hex
        script = Path(__file__).resolve().parents[1] / 'tools/boxdetect/probe.py'
        args = ['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect','--unit='+unit,
                '-p','MemoryMax=768M','-p','CPUQuota=200%','-p','RuntimeMaxSec=30',
                '-p','TasksMax=64','-p','Nice=10','-p','NoNewPrivileges=yes',
                self.config['python'], str(script), '--model-dir', str(folder)]
        try:
            subprocess.run(args, check=True, capture_output=True, timeout=40)
        finally:
            subprocess.run(['/usr/bin/systemctl','stop',unit], capture_output=True, timeout=10)


def model_info(folder):
    folder = Path(folder)
    meta = json.loads((folder/'model.json').read_text())
    model = folder/'model.onnx'
    if not model.is_file() or model.stat().st_size > 64*1024*1024: raise ValueError('模型缺失或超过64MiB')
    if meta.get('classes') != ['question','answer'] or meta.get('imgsz') not in (640,960):
        raise ValueError('模型类别或输入尺寸不支持')
    if not isinstance(meta.get('conf'),(int,float)) or not 0 < meta['conf'] <= 1: raise ValueError('模型阈值不合法')
    if digest(model) != meta.get('sha256'): raise ValueError('模型哈希不匹配')
    return meta


def candidates(root):
    """只发现完整已导出的run；切换时重新校验，不把训练目录直接交给服务。"""
    rows, errors = [], []
    for folder in sorted((root/'runs').glob('*'))[:100]:
        if not (folder/'export.json').exists(): continue
        try:
            folder = trainpanel.safe_path(root,'runs',folder.name)
            ex = json.loads((folder/'export.json').read_text()); identity = json.loads((folder/'identity.json').read_text())
            evaluation = json.loads((folder/'eval.json').read_text())
            if digest(folder/'model.onnx') != ex['onnx_sha256'] or digest(folder/'weights/best.pt') != ex['weights_sha256']:
                raise ValueError('导出文件与权重校验不一致')
            if evaluation.get('model_sha256') != ex['onnx_sha256']: raise ValueError('评估模型身份不一致')
            meta = {'name':folder.name,'run':folder.name,'sha256':ex['onnx_sha256'],
                    'imgsz':identity['imgsz'],'conf':evaluation['conf'],'classes':['question','answer']}
            if meta['imgsz'] not in (640,960) or not 0 < meta['conf'] <= 1 or (folder/'model.onnx').stat().st_size > 64*1024*1024:
                raise ValueError('模型参数超出服务范围')
            scores = []
            for path in sorted((root/'audits').glob('*/audit.json'))[:200]:
                try:
                    data = json.loads(path.read_text())
                    if data.get('model_sha256') == meta['sha256'] and data.get('conf') == meta['conf'] and data.get('split') in ('test','independent'):
                        score = trainaudit.summary(root,path.parent.name)
                        scores.append({k:score[k] for k in ('id','purpose','images','raw_passed','reviewed_passed','reviewed','cases','user_reviewed')})
                except (ValueError,OSError,KeyError): continue
            rows.append({'id':folder.name,**meta,'scores':scores})
        except (ValueError,OSError,KeyError,TypeError) as exc: errors.append({'id':folder.name,'error':str(exc)})
    return rows, errors


class Controller:
    def __init__(self, config):
        self.config = config; self.root = Path(config['root']).resolve(); self.home = self.root/'managed'
        self.backend = SystemdBackend(config)

    def state(self):
        return json.loads((self.home/'state.json').read_text())

    def pointer(self):
        path = (self.home/'active').resolve(strict=True)
        if path.parent != (self.home/'snapshots').resolve(): raise ValueError('在线模型映射越界')
        model_info(path)
        return path.name

    def point(self, name):
        path = trainpanel.safe_path(self.home,'snapshots',name); model_info(path)
        temp = self.home/('active-'+uuid.uuid4().hex)
        temp.symlink_to(Path('snapshots')/name, target_is_directory=True); os.replace(temp,self.home/'active')

    def acquire(self):
        handle = (self.home/'operation.lock').open('a')
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: handle.close(); raise Conflict('服务操作进行中，请等待完成')
        return handle

    def wait_health(self, name):
        expected = model_info(self.home/'snapshots'/name)
        for _ in range(30):
            health = self.backend.health()
            if health and all(health.get(k)==expected[k] for k in ('sha256','imgsz','conf')): return health
            time.sleep(.2)
        raise ValueError('服务健康检查失败或实际加载模型不匹配')

    def stage(self, ident, expected_sha, conf=None, imgsz=None):
        rows,_ = candidates(self.root); candidate = next((r for r in rows if r['id']==ident),None)
        if not candidate or candidate['sha256'] != expected_sha or (conf is not None and candidate['conf'] != conf) or (imgsz is not None and candidate['imgsz'] != imgsz): raise ValueError('模型不存在或身份已改变，请刷新')
        meta = {k:v for k,v in candidate.items() if k not in ('id','scores')}
        name = hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest()
        dest = self.home/'snapshots'/name
        if not dest.exists():
            stage = self.home/('stage-'+uuid.uuid4().hex); stage.mkdir()
            try:
                shutil.copyfile(trainpanel.safe_path(self.root,'runs',ident,'model.onnx'),stage/'model.onnx')
                write(stage/'model.json',meta); model_info(stage); stage.rename(dest)
            finally:
                if stage.exists(): shutil.rmtree(stage)
        model_info(dest)
        return name

    def launch(self, op, handle, recovering=False):
        thread = threading.Thread(target=self.execute,args=(op,handle,recovering),daemon=True)
        thread.start()

    def execute(self, op, handle, recovering=False):
        state = self.state(); error = ''; rollback_error = ''; touched = False; changed = op['action'] in ('activate','rollback')
        try:
            if recovering: raise ValueError('上次操作被服务重启中断，执行恢复')
            if changed:
                target = state.get('previous') if op['action']=='rollback' else self.stage(op['model_id'],op['sha256'],op['conf'],op['imgsz'])
                if not target: raise ValueError('没有可恢复的上一模型')
                with (self.root/'training.lock').open('a') as training:
                    try: fcntl.flock(training,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError: raise ValueError('训练运行中，暂不预检或切换模型')
                    self.backend.preflight(self.home/'snapshots'/target)
                    touched = True
                    self.point(target); self.backend.command('restart'); self.wait_health(target)
                state['previous'] = op['before']; state['current'] = target
            else:
                self.backend.command(op['action'])
                if op['action']=='stop':
                    if self.backend.active() or self.backend.health(): raise ValueError('服务未完全停止')
                else: self.wait_health(op['before'])
            op['state'] = 'done'
        except Exception as exc:
            error = str(exc) if isinstance(exc,ValueError) else type(exc).__name__+'：服务操作失败，请查看服务日志'
            if changed and (touched or recovering):
                try:
                    self.point(op['before'])
                    self.backend.command('restart' if op['was_active'] else 'stop')
                    if op['was_active']: self.wait_health(op['before'])
                except Exception as rollback: rollback_error = type(rollback).__name__+'：回退未完成，请检查服务'
            op['state'] = 'failed'
        finally:
            health = self.backend.health()
            op.update(error=error,rollback_error=rollback_error,finished_at=trainaudit.now(),
                      resulting_sha256=health.get('sha256') if health else None)
            try:
                state['operation'] = op; write(self.home/'operations'/(op['request_id']+'.json'),op); write(self.home/'state.json',state)
                with (self.home/'events.jsonl').open('a') as events: events.write(json.dumps(op,ensure_ascii=False)+'\n')
            finally: handle.close()

    def recover(self):
        state = self.state(); op = state.get('operation')
        if op and op['state']=='running':
            try: handle = self.acquire()
            except Conflict: return
            # 获取锁前操作可能刚好完成；锁内重读，不能恢复旧快照。
            current = self.state().get('operation')
            if not current or current['state'] != 'running':
                handle.close(); return
            self.launch(current,handle,True)

    def submit(self, data):
        action = data.get('action'); ident = data.get('request_id')
        if action not in ACTIONS or not isinstance(ident,str) or len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('操作或请求ID不合法')
        if type(data.get('revision')) is not int: raise ValueError('缺少操作版本')
        if action=='activate': trainpanel.safe_path(self.root,'runs',data.get('model_id',''))
        request = {k:data.get(k) for k in ('action','revision','request_id','model_id','sha256','conf','imgsz')}
        record = self.home/'operations'/(ident+'.json')
        if record.exists():
            op = json.loads(record.read_text())
            if op['request'] != request: raise Conflict('请求ID已被其他操作使用')
            return op
        handle = self.acquire()
        try:
            state = self.state()
            if state.get('operation',{}).get('state')=='running': raise Conflict('上次操作待恢复，请刷新')
            if state['revision'] != data['revision']: raise Conflict('服务状态已被修改，请刷新后重试')
            if action=='activate' and not any(r['id']==data.get('model_id') and r['sha256']==data.get('sha256') and r['conf']==data.get('conf') and r['imgsz']==data.get('imgsz') for r in candidates(self.root)[0]):
                raise ValueError('模型未登记或哈希已改变')
            before = self.pointer()
            if action=='rollback' and not state.get('previous'): raise ValueError('没有上一模型')
            op = dict(request,request=request,state='running',before=before,was_active=self.backend.active(),
                      actor='已认证用户',before_sha256=model_info(self.home/'snapshots'/before)['sha256'],
                      started_at=trainaudit.now(),error='',rollback_error='')
            state.update(revision=state['revision']+1,operation=op)
            write(record,op); write(self.home/'state.json',state)
            self.launch(op,handle); return op
        except BaseException: handle.close(); raise

    def overview(self):
        self.recover(); state = self.state(); health = self.backend.health(); rows,errors = candidates(self.root)
        chosen = model_info(self.home/'snapshots'/state['current'])
        match = bool(health and all(health.get(k)==chosen[k] for k in ('sha256','imgsz','conf')))
        history = []
        for path in sorted((self.home/'operations').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            item = json.loads(path.read_text()); history.append({k:item.get(k) for k in ('action','state','started_at','finished_at','error','rollback_error','model_id','actor','sha256','resulting_sha256')})
        return {'supported':True,'revision':state['revision'],'operation':state.get('operation'),
                'online':health,'matches':match,'selected':chosen,'previous':bool(state.get('previous')),
                'models':rows,'errors':errors,'history':history}


def overview(vault):
    config = registration(vault)
    if not config: return {'supported':False,'message':'此实例未登记受管检测服务，请由部署者配置；仍可使用已有检测地址。'}
    return Controller(config).overview()


def submit(vault, data):
    config = registration(vault)
    if not config: raise ValueError('此实例未登记受管检测服务')
    if not isinstance(data,dict): raise ValueError('请求必须是对象')
    return Controller(config).submit(data)
