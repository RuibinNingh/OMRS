"""OMRS与框选真实双进程：同端口代理、私有配置与三个调用入口。"""
import base64
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/boxdetect'))
from boxdetect_service import server as box_server
from boxdetect_service.config import Config
from services.boxdetect.tests.test_panel import FakeDetector,model,image
from omrs import common,inbox,trainpanel
from omrs.boxdetect import config,client
from omrs.boxdetect.errors import ServiceError
from omrs.cli import OMRSTCPServer
from omrs.server import OMRSHandler


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='omrs-box-panel-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.vault=str(self.root/'vault')
        common.save_config(self.vault,{'inbox_detect_provider':'local_http'})
        model(self.root/'model')
        with patch.object(box_server,'Detector',FakeDetector):self.box=box_server.make_server(self.root/'model',0,config=Config(self.root/'state',port=0))
        self.key,metadata=self.box.auth.create_key('隔离客户端');self.kid=metadata['id']
        config.save(self.vault,{'mode':'local','base_url':f'http://127.0.0.1:{self.box.server_port}','api_key':self.key})
        vault=self.vault
        class Handler(OMRSHandler):
            vault_path=vault
            def log_message(self,*args):pass
        self.main=OMRSTCPServer(('127.0.0.1',0),Handler)
        for http in (self.box,self.main):
            thread=threading.Thread(target=lambda http=http:http.serve_forever(poll_interval=.01),daemon=True);thread.start()
            self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        self.base=f'http://127.0.0.1:{self.main.server_address[1]}'

    def request(self,method,path,body=None,headers=None):
        heads={'Content-Type':'application/json','Origin':self.base,**(headers or {})}
        connection=http.client.HTTPConnection('127.0.0.1',self.main.server_address[1],timeout=10)
        try:
            connection.request(method,path,json.dumps(body) if body is not None else None,heads)
            response=connection.getresponse();raw=response.read();value=json.loads(raw) if 'application/json' in response.getheader('Content-Type','') else raw
            return response.status,value,dict(response.getheaders())
        finally:connection.close()

    def login(self):
        secret=(self.root/'state/admin-secret.txt').read_text().strip()
        status,data,heads=self.request('POST','/boxdetect/api/admin/login',{'password':secret})
        self.assertEqual(status,200)
        return {'Cookie':heads['Set-Cookie'].split(';')[0],'X-CSRF-Token':data['csrf_token']},heads['Set-Cookie']

    def test_private_key_projection_clear_and_keep(self):
        public=config.public(self.vault);self.assertTrue(public['api_key_configured']);self.assertNotIn(self.key,json.dumps(public))
        self.assertEqual(config.save(self.vault,{'api_key':''})['api_key_fingerprint'],public['api_key_fingerprint'])
        self.assertEqual(config.snapshot(self.vault).api_key,self.key)
        config.save(self.vault,{'clear_api_key':True});self.assertFalse(config.public(self.vault)['api_key_configured'])
        self.assertEqual(config.location(self.vault).stat().st_mode&0o777,0o600)

    def test_same_origin_panel_cookie_and_refresh(self):
        status,html,_=self.request('GET','/boxdetect/');self.assertEqual(status,200);self.assertIn('AI 框选'.encode(),html)
        headers,cookie=self.login();self.assertIn('Path=/boxdetect/',cookie)
        self.assertNotIn(self.key,cookie);self.assertEqual(self.request('GET','/boxdetect/api/admin/session',headers=headers)[0],200)
        self.assertEqual(self.request('GET','/boxdetect/assets/panel.js')[0],200)
        config.save(self.vault,{'api_key':self.key})
        self.assertEqual(self.request('GET','/boxdetect/api/admin/session',headers=headers)[0],401)

    def test_external_service_cannot_supply_same_origin_code_or_html(self):
        from omrs.boxdetect import transport
        with patch.object(transport,'request',side_effect=AssertionError('不应从上游下载面板代码')):
            self.assertEqual(self.request('GET','/boxdetect/')[0],200)
            self.assertEqual(self.request('GET','/boxdetect/assets/panel.js')[0],200)
        with patch.object(transport,'request',return_value=(200,{'Content-Type':'text/html'},b'<script>alert(1)</script>')):
            self.assertEqual(self.request('GET','/boxdetect/api/admin/overview')[0],502)
            self.assertEqual(self.request('GET','/boxdetect/api/admin/history/1/image')[0],502)

    def test_proxy_network_does_not_hold_global_write_lock(self):
        from omrs import locking
        from omrs.boxdetect import transport
        original=transport.request
        def unlocked(*args,**kwargs):
            self.assertFalse(locking.held_by_current_thread())
            return original(*args,**kwargs)
        with patch.object(transport,'request',side_effect=unlocked):
            self.assertEqual(self.request('POST','/api/boxdetect/service/test',{})[0],200)

    def test_key_only_public_endpoint_stays_separate_from_omrs(self):
        self.box.store.set('allow_external',True)
        headers={'Authorization':'Bearer '+self.key,'X-Real-IP':'203.0.113.12'}
        self.assertEqual(self.request('GET','/boxdetect/api/v1/status',headers=headers)[0],200)
        self.assertEqual(self.request('GET','/api/config',headers=headers)[0],403)
        self.assertEqual(self.request('GET','/boxdetect/api/admin/keys',headers=headers)[0],403)
        self.assertEqual(self.request('POST','/boxdetect/api/v1/detect',{'image':'data:image/png;base64,'+base64.b64encode(image()).decode(),'request_id':'a'*32},headers=headers)[0],200)
        self.box.auth.revoke_key(self.kid)
        self.assertEqual(self.request('GET','/boxdetect/api/v1/status',headers=headers)[0],401)

    def test_remote_cannot_bypass_external_switch_through_proxy(self):
        headers={'Authorization':'Bearer '+self.key,'X-Real-IP':'203.0.113.12'}
        self.assertEqual(self.request('GET','/boxdetect/api/v1/status',headers=headers)[0],403)

    def test_unified_client_inbox_and_legacy_try(self):
        raw=image()
        uploaded=inbox.upload_images(self.vault,[('test.png',raw)])['items'][0]
        result=inbox._run_detect(self.vault,object(),{'item_id':uploaded['id'],'replace':True})
        self.assertGreater(result['boxes'],0)
        tested=trainpanel.try_image(self.vault,[('test.png',raw)])
        self.assertGreater(tested['strips'],1)
        rows=self.box.store.history({})['items']
        self.assertEqual({r['source'] for r in rows},{'inbox','test'});self.assertEqual(len(rows),2)
        self.assertEqual(self.request('POST','/api/boxdetect/service/test',{})[0],200)

    def test_service_switch_rejects_old_result(self):
        from omrs.boxdetect import transport
        original=transport.json_request
        def switched(*args,**kwargs):
            result=original(*args,**kwargs);config.save(self.vault,{'api_key':self.key});return result
        with patch('omrs.boxdetect.client.json_request',side_effect=switched):
            with self.assertRaisesRegex(ServiceError,'旧结果未发布'):client.detect(self.vault,image(),'image/png')

    def test_service_switch_prevents_old_test_result_from_entering_training(self):
        from omrs import annotate
        common.save_config(self.vault,{'train_try_collect':True})
        original=client.detect
        def switched(*args,**kwargs):
            result=original(*args,**kwargs)
            config.save(self.vault,{'api_key':self.key})
            return result
        with patch.object(client,'detect',side_effect=switched):
            with self.assertRaisesRegex(ServiceError,'旧结果未发布'):
                trainpanel.try_image(self.vault,[('test.png',image())])
        self.assertFalse(annotate.list_images(self.vault))

    def test_old_protocol_not_silently_migrated_or_written(self):
        other=str(self.root/'old')
        common.save_config(other,{'inbox_local_detect_url':'http://127.0.0.1:19099/detect'})
        self.assertFalse(config.snapshot(other).configured);self.assertFalse(config.location(other).exists())
        self.assertIsNone(client.detect(other,image(),'image/png'))

    def test_target_validation_rejects_unsafe_and_allows_prefix(self):
        for base in ('http://169.254.169.254','https://x.example/a/../b','https://x.example/a%2fb','https://u:p@x.example','http://x.example'):
            with self.subTest(base=base),self.assertRaises(ServiceError):config.save(self.vault,{'mode':'external','base_url':base})
        config.save(self.vault,{'mode':'external','base_url':'https://example.com/boxdetect'})
