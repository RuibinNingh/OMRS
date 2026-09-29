"""受管服务真实HTTP、隔离后端：切换失败回退、幂等、并发及恢复。"""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from omrs import traincontrol as c
from omrs.common import save_config
from tools.boxdetect.bootstrap_control import bootstrap


class FakeBackend:
    states = {}
    def __init__(self, config):
        self.config=config;self.state=self.states.setdefault(config['root'],{'active':True,'calls':[],'fail':False,'gate':None})
        if 'online' not in self.state:self.state['online']=c.model_info(Path(config['root'])/'managed/active')
    def active(self):return self.state['active']
    def health(self):return self.state['online'] if self.state['active'] else None
    def command(self, action):
        self.state['calls'].append(action);self.state['active']=action!='stop'
        if action!='stop':self.state['online']=c.model_info(Path(self.config['root'])/'managed/active')
        if self.state.get('fail_restart') and self.state['online']['name']=='new':raise ValueError('候选服务启动失败')
    def preflight(self, folder):
        if self.state['gate']:self.state['gate'].wait(5)
        if self.state['fail']:raise ValueError('候选预检失败')


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='omrs-control-test-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'train';self.vault=self.base/'vault'
        self.make_model('old');self.make_model('new')
        bootstrap(self.root,self.root/'models/old')
        self.config={'root':str(self.root),'vault':str(self.vault),'unit':c.UNIT,'port':18991,'python':'python3'}
        self.reg=self.base/'registration.json';c.write(self.reg,self.config)
        save_config(str(self.vault),{'train_dir':str(self.root),'inbox_local_detect_url':'http://127.0.0.1:18991/detect'})
        self.env=patch.dict(os.environ,{'OMRS_BOXDETECT_CONTROL':str(self.reg)});self.env.start();self.addCleanup(self.env.stop)
        self.fake=patch.object(c,'SystemdBackend',FakeBackend);self.fake.start();self.addCleanup(self.fake.stop)
        self.control=c.Controller(self.config)
        self.addCleanup(FakeBackend.states.pop,str(self.root),None)

    def make_model(self,name):
        run=self.root/'runs'/name;run.mkdir(parents=True);(run/'weights').mkdir()
        (run/'model.onnx').write_bytes(name.encode());(run/'weights/best.pt').write_bytes((name+'weights').encode())
        sha=c.digest(run/'model.onnx');meta={'name':name,'run':name,'sha256':sha,'classes':['question','answer'],'imgsz':640,'conf':.55}
        c.write(run/'export.json',{'onnx_sha256':sha,'weights_sha256':c.digest(run/'weights/best.pt')})
        c.write(run/'identity.json',{'imgsz':640});c.write(run/'eval.json',{'model_sha256':sha,'conf':.55})
        model=self.root/'models'/name;model.mkdir(parents=True);(model/'model.onnx').write_bytes(name.encode());c.write(model/'model.json',meta)
        return meta

    def request(self,action='activate',**kwargs):
        return {'action':action,'revision':self.control.state()['revision'],'request_id':os.urandom(16).hex(),
                'model_id':'new','conf':.55,'imgsz':640,'sha256':c.digest(self.root/'runs/new/model.onnx'),**kwargs}

    def finish(self):
        for _ in range(300):
            state=self.control.state()
            if state.get('operation',{}).get('state') in ('done','failed'):
                # 等待持久化及操作锁释放，而不是只看状态。
                try:h=self.control.acquire();h.close();return state
                except c.Conflict:pass
            time.sleep(.01)
        self.fail('操作未完成')

    def test_switch_then_rollback_and_restart_persistence(self):
        self.control.submit(self.request());s=self.finish();self.assertEqual(s['operation']['state'],'done')
        self.assertEqual(self.control.backend.health()['name'],'new')
        restarted=c.Controller(self.config);self.assertEqual(restarted.overview()['selected']['name'],'new')
        self.control.submit(self.request('rollback'));self.finish();self.assertEqual(self.control.backend.health()['name'],'old')
        self.assertEqual(len(list((self.root/'managed/operations').glob('*.json'))),2)

    def test_preflight_and_restart_failures_retain_old(self):
        for kind in ('fail','fail_restart'):
            self.control.backend.state[kind]=True
            self.control.submit(self.request());s=self.finish()
            self.assertEqual(s['operation']['state'],'failed');self.assertFalse(s['operation']['rollback_error'])
            self.assertEqual(self.control.backend.health()['name'],'old')
            self.assertEqual(c.model_info(self.root/'managed/active')['name'],'old')
            self.control.backend.state[kind]=False

    def test_duplicate_and_conflicting_windows(self):
        gate=threading.Event();self.control.backend.state['gate']=gate;payload=self.request()
        self.control.submit(payload)
        self.assertEqual(self.control.submit(payload)['request_id'],payload['request_id'])
        with self.assertRaises(c.Conflict):self.control.submit(self.request('stop'))
        gate.set();self.finish()
        with self.assertRaises(c.Conflict):self.control.submit(self.request('stop',revision=0))
        self.control.submit(payload);self.assertEqual(self.control.backend.state['calls'].count('restart'),1)
        with self.assertRaises(c.Conflict):self.control.submit(dict(payload,action='stop'))

    def test_interrupted_switch_recovers_previous(self):
        before=self.control.pointer();target=self.control.stage('new',c.digest(self.root/'runs/new/model.onnx'))
        self.control.point(target);self.control.backend.command('restart')
        op=dict(self.request(),state='running',before=before,was_active=True,actor='测试',started_at='now')
        c.write(self.root/'managed/state.json',{'revision':1,'current':before,'previous':None,'operation':op})
        self.control.recover();s=self.finish()
        self.assertEqual(s['operation']['state'],'failed');self.assertEqual(self.control.backend.health()['name'],'old')

    def test_recovery_rechecks_state_after_lock(self):
        before=self.control.pointer()
        op=dict(self.request(),state='running',before=before,was_active=True)
        state=self.control.state();state['operation']=op
        c.write(self.root/'managed/state.json',state)
        acquire=self.control.acquire
        def completed_before_lock():
            state['operation']['state']='done'
            c.write(self.root/'managed/state.json',state)
            return acquire()
        with patch.object(self.control,'acquire',side_effect=completed_before_lock), patch.object(self.control,'launch') as launch:
            self.control.recover();launch.assert_not_called()
        self.assertEqual(self.control.backend.state['calls'],[])

    def test_stop_start_and_sha_mismatch(self):
        self.control.submit(self.request('stop'));self.finish();self.assertIsNone(self.control.overview()['online'])
        self.control.submit(self.request('start'));self.finish();self.assertTrue(self.control.overview()['matches'])
        self.control.backend.state['online']={**self.control.backend.state['online'],'sha256':'wrong'}
        self.assertFalse(self.control.overview()['matches'])
        self.control.submit(self.request('restart'));self.finish();self.assertTrue(self.control.overview()['matches'])

    def test_bad_ids_hashes_and_unregistered_instance(self):
        with self.assertRaises(ValueError):self.control.submit(self.request(model_id='../new'))
        with self.assertRaises(ValueError):self.control.submit(self.request(sha256='wrong'))
        with patch.object(c,'fcntl',None):
            self.assertFalse(c.overview(self.vault)['supported'])
        self.assertIsNone(c.registration(self.base/'different-vault'))
        self.assertFalse(c.overview(self.base/'different-vault')['supported'])
        (self.root/'runs/new/model.onnx').write_bytes(b'changed')
        rows,errors=c.candidates(self.root);self.assertEqual([r['id'] for r in rows],['old']);self.assertEqual(errors[0]['id'],'new')

    def test_incomplete_smoke_is_not_a_candidate_or_error(self):
        (self.root/'runs/new/eval.json').unlink()
        rows,errors=c.candidates(self.root)
        self.assertEqual([r['id'] for r in rows],['old']);self.assertEqual(errors,[])

    def test_training_lock_and_changed_threshold_are_rejected(self):
        import fcntl
        with (self.root/'training.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.control.submit(self.request());state=self.finish()
            self.assertEqual(state['operation']['state'],'failed')
            self.assertEqual(self.control.backend.state['calls'],[])
        payload=self.request()
        c.write(self.root/'runs/new/eval.json',{'model_sha256':payload['sha256'],'conf':.25})
        with self.assertRaises(ValueError):self.control.submit(payload)

    def test_http_auth_origin_and_limits(self):
        import http.client
        from functools import partial
        from omrs.cli import OMRSTCPServer
        from omrs.server import OMRSHandler
        vault=str(self.vault)
        class Handler(OMRSHandler):
            vault_path=vault
            def log_message(self,*args):pass
        server=OMRSTCPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def req(method,path,data=None,headers=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_address[1]);conn.request(method,path,json.dumps(data) if data is not None else None,headers or {})
            response=conn.getresponse();body=response.read();conn.close();return response.status,body
        self.assertEqual(req('GET','/api/trainpanel/manager')[0],200)
        self.assertEqual(req('POST','/api/trainpanel/control',self.request('stop'),{'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(req('POST','/api/trainpanel/control',self.request('stop'),{'X-Forwarded-Proto':'https'})[0],401)
        self.assertEqual(req('GET','/api/trainpanel/manager',headers={'X-Forwarded-For':'203.0.113.1','X-Forwarded-Proto':'https'})[0],401)
        payload=self.request('stop');self.assertEqual(req('POST','/api/trainpanel/control',payload)[0],202);self.finish()
        self.assertEqual(req('POST','/api/trainpanel/control',dict(self.request('start'),revision=0))[0],409)

if __name__=='__main__':unittest.main()
