"""非 loopback 真实 HTTP 与 SQLite 审计；XFF 从不授予本机权限。"""
import json
import sqlite3
import threading
from .support import HttpCase
from zyb_gateway.server import create_server

class AccessAuditTests(HttpCase):
    def remote(self, method, path, body=None, headers=None):
        return self.request(method,path,body, {'Host':self.base.removeprefix('http://'), **(headers or {})},host=self.lan_ip())

    def test_external_default_denied_even_with_valid_key_and_forged_xff(self):
        key, _ = self.make_key()
        for xff in ('127.0.0.1','127.0.0.1, ::1','invalid'):
            code, data, _ = self.remote('GET','/api/v1/status',headers={'Authorization':'Bearer '+key,'X-Forwarded-For':xff})
            self.assertEqual(code,403,data)
            self.assertEqual(data['code'],'external_disabled')
        self.assertEqual(self.remote('POST','/api/admin/login',{'password':self.password},{'Origin':self.base})[0],403)
        self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],200)

    def test_external_switch_persists_and_still_requires_key(self):
        self.login()
        self.assertEqual(self.admin('GET','/api/admin/settings')[0],200)
        self.assertEqual(self.admin('GET','/api/admin/settings')[1]['allow_external'],False)
        self.assertEqual(self.admin('POST','/api/admin/settings',{'allow_external':True})[0],200)
        self.assertEqual(self.admin('GET','/api/admin/settings')[1]['allow_external'],True)
        self.assertEqual(self.remote('GET','/api/v1/status')[0],401)
        key, _ = self.make_key()
        self.assertEqual(self.remote('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],200)
        again = create_server(self.cfg)
        try:
            self.assertTrue(again.store.get('allow_external'))
        finally:
            again.server_close()
        self.assertEqual(self.admin('POST','/api/admin/settings',{'allow_external':False})[0],200)
        self.assertEqual(self.remote('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],403)
        for bad in ('false',1,None):
            self.assertEqual(self.admin('POST','/api/admin/settings',{'allow_external':bad})[0],400)

    def test_audit_success_bad_key_external_and_management_no_secrets(self):
        key, kid = self.make_key()
        self.request('GET','/api/v1/status?querysecret=NEVER-STORE-THIS',headers={'Authorization':'Bearer '+key,'X-Forwarded-For':'203.0.113.100'})
        self.request('GET','/api/v1/status',headers={'Authorization':'Bearer SYNTHETIC-bad-key'})
        self.remote('GET','/api/v1/status',headers={'Authorization':'Bearer '+key,'X-Forwarded-For':'127.0.0.1'})
        self.admin('POST','/api/admin/keys/revoke',{'id':kid,'extra':'BODY-NEVER-STORE'})
        code, history, _ = self.admin('GET','/api/admin/history?page_size=100')
        self.assertEqual(code,200,history)
        rows = history['items']
        local = next(r for r in rows if r['key_id']==kid and r['action']=='status')
        self.assertEqual((local['source'],local['client_ip'],local['peer_ip']),('local','127.0.0.1','127.0.0.1'))
        self.assertEqual(local['http_status'],200)
        self.assertGreaterEqual(local['latency_ms'],0)
        self.assertIn('time',local)
        remote = next(r for r in rows if r['result']=='external_disabled')
        self.assertEqual((remote['source'],remote['client_ip'],remote['peer_ip']),('external',self.lan_ip(),self.lan_ip()))
        self.assertTrue(any(r['result']=='key_invalid' for r in rows))
        self.assertTrue(any(r['action']=='key_revoke' for r in rows))
        raw = json.dumps(history)
        for forbidden in (key,self.password,'NEVER-STORE-THIS','SYNTHETIC-bad-key','BODY-NEVER-STORE',self.cookie,self.csrf):
            self.assertNotIn(forbidden,raw)
        self.assertNotIn('?',raw)

    def test_pagination_filters_and_restart_persistence(self):
        key, kid = self.make_key()
        for _ in range(5):
            self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})
        self.assertEqual(self.admin('GET','/api/admin/history')[0],200)
        first = self.admin('GET',f'/api/admin/history?page=1&page_size=2&key_id={kid}&source=local&result=ok')[1]
        second = self.admin('GET',f'/api/admin/history?page=2&page_size=2&key_id={kid}&source=local&result=ok')[1]
        self.assertEqual(first['total'],5)
        self.assertEqual(len(first['items']),2)
        self.assertTrue(first['has_more'])
        self.assertFalse(set(r['id'] for r in first['items']) & set(r['id'] for r in second['items']))
        again=create_server(self.cfg)
        try:
            self.assertEqual(again.store.history({'key_id':[kid]})['total'],5)
        finally:
            again.server_close()
        for query in ('page=0','page_size=101','source=anything','result=invalid','key_id=bad'):
            self.assertEqual(self.admin('GET','/api/admin/history?'+query)[0],400)

    def test_trusted_proxy_preserves_peer_and_cannot_turn_remote_local(self):
        self.server.config.trusted_proxies=('127.0.0.1/32', self.lan_ip()+'/32')
        key, kid = self.make_key()
        self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key,'X-Forwarded-For':'203.0.113.45'})[0],403)
        self.admin('POST','/api/admin/settings',{'allow_external':True})
        self.assertEqual(self.remote('GET','/api/v1/status',headers={'Authorization':'Bearer '+key,'X-Forwarded-For':'127.0.0.1'})[0],200)
        rows=self.admin('GET','/api/admin/history?source=external')[1]['items']
        row=next(r for r in rows if r['key_id']==kid)
        self.assertEqual(row['source'],'external')
        self.assertEqual(row['peer_ip'],self.lan_ip())
        self.assertEqual(row['client_ip'],'127.0.0.1')
        self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key,'X-Forwarded-For':'broken'})[0],400)

class RetentionTests(HttpCase):
    config_overrides={'history_limit':5}
    def test_history_retention_is_bounded(self):
        key,_=self.make_key()
        for _ in range(12):
            self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})
        self.assertEqual(self.admin('GET','/api/admin/history')[0],200)
        rows=self.admin('GET','/api/admin/history')[1]
        self.assertEqual(rows['total'],5)

class ApiRateTests(HttpCase):
    config_overrides={'api_per_minute':2}
    def test_per_key_rate_persists_after_restart(self):
        key,kid=self.make_key()
        for _ in range(2):
            self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],200)
        self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],429)
        again=create_server(self.cfg)
        try:
            from zyb_gateway.errors import ApiError
            with self.assertRaises(ApiError):
                again.store.rate('api',kid,2,60)
        finally:
            again.server_close()
