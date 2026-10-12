"""管理员与调用密钥主路径先 RED；不是上游会话测试。"""
from contextlib import closing
import sqlite3
import time
from .support import HttpCase

class AuthTests(HttpCase):
    def test_login_cookie_independent_session_and_logout(self):
        self.assertEqual(self.request('GET', '/api/admin/session')[0], 401)
        data, heads = self.login()
        for token in ('HttpOnly', 'SameSite=Strict', 'Path=/'):
            self.assertIn(token, heads['Set-Cookie'])
        code, after, _ = self.admin('GET', '/api/admin/session')
        self.assertEqual(code, 200)
        self.assertEqual(after['csrf_token'], data['csrf_token'])
        self.assertEqual(self.admin('POST', '/api/admin/logout', {})[0], 200)
        self.assertEqual(self.admin('GET', '/api/admin/session')[0], 401)

    def test_login_failures_are_limited(self):
        for _ in range(self.cfg.login_failures):
            code, data, _ = self.request('POST', '/api/admin/login', {'password': 'SYNTHETIC-wrong-password'}, {'Origin': self.base})
            self.assertEqual(code, 401)
            self.assertNotIn('SYNTHETIC', str(data))
        self.assertEqual(self.request('POST', '/api/admin/login', {'password': self.password}, {'Origin': self.base})[0], 429)

    def test_expired_session_cannot_administer(self):
        self.login()
        with closing(sqlite3.connect(self.cfg.data_dir / 'gateway.sqlite3')) as db, db:
            db.execute('UPDATE sessions SET expires_at=?', (time.time() - 1,))
        self.assertEqual(self.admin('GET', '/api/admin/session')[0], 401)

    def test_status_requires_key_and_exact_offline_contract(self):
        self.assertEqual(self.request('GET', '/api/v1/status')[0], 401)
        self.assertEqual(self.request('GET', '/api/v1/status', headers={'Authorization':'Bearer fake'})[0], 401)
        key, _ = self.make_key()
        code, data, _ = self.request('GET', '/api/v1/status', headers={'Authorization':'Bearer '+key})
        self.assertEqual(code, 200)
        self.assertEqual(data, {'status':'ok', 'account':{'local_session_ready':False, 'has_account_credential':False, 'observations':{'account':{},'signing':{},'events':[]}}, 'panel_url':'/'})

    def test_key_only_once_digest_metadata_and_immediate_revoke(self):
        key, kid = self.make_key('<img src=x onerror=alert(1)>')
        code, data, _ = self.admin('GET', '/api/admin/keys')
        self.assertEqual(code, 200)
        self.assertNotIn(key, str(data))
        row = data['keys'][0]
        self.assertEqual(row['id'], kid)
        self.assertEqual(row['state'], 'active')
        self.assertIsNone(row['last_used_at'])
        self.request('GET', '/api/v1/status', headers={'Authorization':'Bearer '+key})
        self.assertIsNotNone(self.admin('GET', '/api/admin/keys')[1]['keys'][0]['last_used_at'])
        self.assertEqual(self.admin('POST', '/api/admin/keys/revoke', {'id':kid})[0], 200)
        self.assertEqual(self.request('GET', '/api/v1/status', headers={'Authorization':'Bearer '+key})[0], 401)
        self.assertEqual(self.admin('GET', '/api/admin/keys')[1]['keys'][0]['state'], 'revoked')
        with closing(sqlite3.connect(self.cfg.data_dir / 'gateway.sqlite3')) as db, db:
            self.assertNotIn(key, str(list(db.execute('SELECT * FROM api_keys'))))
            self.assertNotIn(self.password, str(list(db.execute('SELECT * FROM settings'))))

    def test_api_key_never_grants_management(self):
        key, _ = self.make_key()
        for method, path, body in [('GET','/api/admin/keys',None),('POST','/api/admin/keys',{'name':'hacked'}),('POST','/api/admin/profile',{'profile':{}})]:
            code, data, _ = self.request(method, path, body, {'Authorization':'Bearer '+key, 'Origin':self.base})
            self.assertEqual(code, 403, data)
        self.assertEqual(len(self.admin('GET', '/api/admin/keys')[1]['keys']), 1)

    def test_origin_csrf_required_for_login_and_management(self):
        self.assertEqual(self.request('POST', '/api/admin/login', {'password': self.password})[0], 403)
        self.assertEqual(self.request('POST', '/api/admin/login', {'password': self.password}, {'Origin':'https://evil.example'})[0], 403)
        self.login()
        self.assertEqual(self.request('POST', '/api/admin/keys', {'name':'bad'}, {'Cookie':self.cookie, 'Origin':self.base})[0], 403)
        self.assertEqual(self.admin('POST', '/api/admin/keys', {'name':'bad'}, {'Origin':'https://evil.example'})[0], 403)
        self.assertEqual(self.admin('POST', '/api/admin/keys', {'name':'bad'}, {'X-CSRF-Token':'wrong'})[0], 403)
        self.assertEqual(self.admin('POST', '/api/admin/keys', {'name':'valid'})[0], 200)

    def test_host_validation_security_headers_and_unknown_route(self):
        self.assertEqual(self.request('GET', '/healthz', headers={'Host':'evil.example'})[0], 403)
        code, data, heads = self.request('GET', '/healthz')
        self.assertEqual(code, 200)
        self.assertEqual(heads['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(heads['X-Frame-Options'], 'DENY')
        self.assertIn("default-src 'self'", heads['Content-Security-Policy'])
        self.assertEqual(self.request('GET', '/unknown')[0], 404)

    def test_reject_invalid_json_names_and_unbounded_headers(self):
        self.login()
        for value in ('', 'x'*81, 0, None):
            self.assertEqual(self.admin('POST','/api/admin/keys',{'name':value})[0], 400)
        for raw in (b'null', b'[]', b'{bad'):
            self.assertEqual(self.admin('POST','/api/admin/keys',raw,{'Content-Type':'application/json'})[0], 400)
