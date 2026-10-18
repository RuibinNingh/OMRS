"""真实HTTP回归：独立权限、整图历史、去重、限流和模型恢复。"""
import base64
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image
from boxdetect_service import server
from boxdetect_service.config import Config
from boxdetect_service.storage import Store
from boxdetect_service.slicing import slice_plan,merge_strip_boxes


class FakeDetector:
    calls=0
    def __init__(self,path,conf): self.size=640;self.conf=conf
    def __call__(self,image):
        type(self).calls+=1
        if self.conf==.9: raise RuntimeError('不应回显到页面的原始错误')
        return [{'role':'question','card':1,'x':.1,'y':.1,'w':.8,'h':.3,'conf':.8},{'role':'answer','card':1,'x':.1,'y':.5,'w':.8,'h':.3,'conf':.7}]


def model(path,name='old',conf=.1):
    path.mkdir(parents=True,exist_ok=True);(path/'model.onnx').write_bytes(name.encode())
    (path/'model.json').write_text(json.dumps({'name':name,'sha256':hashlib.sha256(name.encode()).hexdigest(),'classes':['question','answer'],'imgsz':640,'conf':conf}))


def image(width=400,height=1800):
    stream=io.BytesIO()
    with Image.new('RGB',(width,height),'white') as im: im.save(stream,'PNG')
    return stream.getvalue()


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        model(self.root/'model');model(self.root/'models/new','new',.2);model(self.root/'models/bad','bad',.9)
        self.config=Config(self.root/'state',port=0,models_dir=self.root/'models')
        with patch.object(server,'Detector',FakeDetector):self.http=server.make_server(self.root/'model',0,config=self.config)
        self.thread=threading.Thread(target=lambda:self.http.serve_forever(poll_interval=.01),daemon=True);self.thread.start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown);self.addCleanup(self.thread.join,.02)
        self.base=f'http://127.0.0.1:{self.http.server_port}'
        self.cookie='';self.csrf=''

    def request(self,method,path,body=None,key=None,admin=False,headers=None):
        heads={'Content-Type':'application/json'}
        if admin: heads.update({'Cookie':self.cookie,'Origin':self.base,'X-CSRF-Token':self.csrf})
        if key:heads['Authorization']='Bearer '+key
        heads.update(headers or {})
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        try:
            conn.request(method,path,json.dumps(body) if body is not None else None,heads);response=conn.getresponse();raw=response.read();result=json.loads(raw) if 'application/json' in response.getheader('Content-Type','') else raw
            return response.status,result,dict(response.getheaders())
        finally:conn.close()

    def login(self):
        password=(self.root/'state/admin-secret.txt').read_text().strip()
        status,data,headers=self.request('POST','/api/admin/login',{'password':password},headers={'Origin':self.base})
        self.assertEqual(status,200);self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=data['csrf_token']

    def key(self,name='客户端'):
        if not self.cookie:self.login()
        status,data,_=self.request('POST','/api/admin/keys',{'name':name},admin=True);self.assertEqual(status,200)
        return data['key'],data['metadata']['id']

    def detect(self,key,rid='a'*32,data=None):
        raw=data or image()
        return self.request('POST','/api/v1/detect',{'image':'data:image/png;base64,'+base64.b64encode(raw).decode(),'request_id':rid,'source':'inbox'},key=key)

    def test_default_requires_key_and_admin_is_separate(self):
        self.assertEqual(self.request('GET','/health')[0],401)
        self.assertEqual(self.request('POST','/detect',{})[0],401)
        key,kid=self.key()
        self.assertEqual(self.request('GET','/api/v1/status',key=key)[0],200)
        self.assertEqual(self.request('GET','/api/admin/keys',key=key,admin=True)[0],403)
        self.assertEqual(self.request('POST','/api/admin/settings',{'paused':True},admin=True,headers={'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('POST','/api/admin/settings',{'paused':True},admin=True,headers={'Origin':'https://evil.example'})[0],403)

    def test_long_image_has_one_original_and_complete_receipt(self):
        key,kid=self.key();raw=image();status,result,_=self.detect(key,data=raw)
        self.assertEqual(status,200);self.assertEqual(result['strips'],len(slice_plan(400,1800)))
        _,listing,_=self.request('GET','/api/admin/history',admin=True);self.assertEqual(listing['total'],1)
        ident=listing['items'][0]['id']
        _,detail,_=self.request('GET',f'/api/admin/history/{ident}',admin=True)
        self.assertEqual(detail['image']['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(detail['item']['response']['boxes'],result['boxes'])
        _,original,_=self.request('GET',f'/api/admin/history/{ident}/image',admin=True);self.assertEqual(original,raw)
        self.assertEqual(detail['item']['model']['name'],'old')

    def test_retry_deduplicates_and_conflict_is_rejected(self):
        key,kid=self.key();before=FakeDetector.calls
        first=self.detect(key);second=self.detect(key)
        self.assertEqual(first[:2],second[:2]);self.assertEqual(FakeDetector.calls-before,first[1]['strips'])
        self.assertEqual(self.detect(key,data=image(300,600))[0],409)

    def test_revocation_and_per_key_limits(self):
        key,kid=self.key();other,_=self.key('第二个')
        self.http.store.set('per_key_per_minute',1)
        self.assertEqual(self.detect(key)[0],200)
        self.assertEqual(self.detect(key,'b'*32)[0],429)
        self.assertEqual(self.detect(other)[0],200)
        self.request('POST','/api/admin/keys/revoke',{'id':kid},admin=True)
        self.assertEqual(self.request('GET','/api/v1/status',key=key)[0],401)

    def test_revocation_during_inference_records_failure(self):
        key,kid=self.key()
        def revoked(image):
            self.http.auth.revoke_key(kid)
            return []
        self.http.runtime.detector=revoked
        self.assertEqual(self.detect(key)[0],401)
        row=self.http.store.history({})['items'][0]
        self.assertEqual(row['state'],'failure')
        self.assertEqual(self.http.store.detail(row['id'])['item']['response']['code'],'key_invalid')

    def test_pause_preserves_management_and_empty_boxes_are_success(self):
        key,kid=self.key();self.request('POST','/api/admin/settings',{'paused':True},admin=True)
        self.assertEqual(self.detect(key)[0],503);self.assertEqual(self.request('GET','/api/admin/overview',admin=True)[0],200)
        self.request('POST','/api/admin/settings',{'paused':False},admin=True)
        with patch.object(FakeDetector,'__call__',return_value=[]):
            status,result,_=self.detect(key,'b'*32);self.assertEqual(status,200);self.assertEqual(result['boxes'],[])

    def test_retention_removes_original_but_keeps_result(self):
        key,kid=self.key();status,result,_=self.detect(key);ident=result['history_id']
        self.http.store.set('retention',{'days':30,'limit':10000,'detail_bytes':1})
        _,detail,_=self.request('GET',f'/api/admin/history/{ident}',admin=True)
        self.assertIsNone(detail['image']);self.assertEqual(detail['item']['state'],'success')
        self.assertEqual(self.request('GET',f'/api/admin/history/{ident}/image',admin=True)[0],404)

    def test_invalid_image_failure_is_recorded_without_exception_text(self):
        key,kid=self.key();status,result,_=self.detect(key,data=b'invalid')
        self.assertEqual(status,400);self.assertEqual(result['code'],'image_invalid')
        _,history,_=self.request('GET','/api/admin/history?state=failure',admin=True);self.assertEqual(history['total'],1)

    def test_models_apply_retry_rollback_and_failed_candidate(self):
        self.login()
        body={'action':'activate','model_id':'new','revision':0,'request_id':'c'*32}
        status,data,_=self.request('POST','/api/admin/models/apply',body,admin=True)
        self.assertEqual(status,200);self.assertEqual(data['operation']['state'],'done');self.assertEqual(self.http.runtime.metadata['name'],'new')
        self.assertEqual(self.request('POST','/api/admin/models/apply',body,admin=True)[1],data)
        bad={'action':'activate','model_id':'bad','revision':1,'request_id':'d'*32}
        self.assertEqual(self.request('POST','/api/admin/models/apply',bad,admin=True)[1]['operation']['state'],'failed')
        self.assertEqual(self.http.runtime.metadata['name'],'new')
        back={'action':'rollback','revision':1,'request_id':'e'*32}
        self.assertEqual(self.request('POST','/api/admin/models/apply',back,admin=True)[1]['operation']['state'],'done');self.assertEqual(self.http.runtime.metadata['name'],'old')

    def test_external_proxy_cannot_bypass_access_switch(self):
        key,_=self.key()
        self.assertEqual(self.request('GET','/api/v1/status',key=key,headers={'X-Forwarded-For':'203.0.113.12'})[0],403)
        self.http.store.set('allow_external',True)
        self.assertEqual(self.request('GET','/api/v1/status',key=key,headers={'X-Forwarded-For':'203.0.113.12'})[0],200)

    def test_restart_keeps_history_and_marks_incomplete_work(self):
        key,kid=self.key();self.detect(key)
        self.http.store.begin(kid,'f'*32,'hash','api','127.0.0.1','127.0.0.1',self.http.runtime.metadata)
        store=Store(self.config);history=store.history({})
        self.assertEqual(history['total'],2);self.assertEqual(history['items'][0]['state'],'interrupted')
        self.assertEqual(history['items'][1]['state'],'success');self.assertIsNotNone(store.detail(history['items'][1]['id'])['image'])
