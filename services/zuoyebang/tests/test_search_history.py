"""搜题详情的原件留存、权限、失败回执、迁移与有界清理；使用真实 HTTP。"""
import base64
import copy
import hashlib
import http.client
import json
import time
from unittest.mock import patch
from .support import HttpCase
from .test_accounts import SYNTHETIC_PROFILE
from .test_search import image_bytes
from zyb_gateway.server import create_server
from zyb_gateway.vendor.direct import DirectClient, UpstreamError


class SearchHistoryTests(HttpCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.admin('POST', '/api/admin/profile', {'profile':copy.deepcopy(SYNTHETIC_PROFILE)})
        self.key, self.kid = self.make_key()

    def search(self, image=None, grade=4, result=None, error=None):
        image = image if image is not None else image_bytes()
        result = result if result is not None else {'ok':True, 'data':{'answers':{'mainPageInfo':['<p>SYNTHETIC-返回题目</p>']}}}
        with patch.object(DirectClient, 'search', return_value=result, side_effect=error) as official:
            response = self.request('POST', '/api/v1/search', {'image_base64':base64.b64encode(image).decode(), 'grade':grade}, {'Authorization':'Bearer ' + self.key})
        return response, official

    def rows(self):
        code, data, _ = self.admin('GET', '/api/admin/history?action=search&page_size=100')
        self.assertEqual(code, 200, data)
        return data['items']

    def detail(self, history_id):
        return self.admin('GET', '/api/admin/history/' + str(history_id))

    def image(self, history_id, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=6)
        try:
            connection.request('GET', '/api/admin/history/' + str(history_id) + '/image', headers=headers if headers is not None else {'Cookie':self.cookie})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_original_formats_and_exact_response_survive_restart(self):
        for format, mime in [('PNG','image/png'), ('JPEG','image/jpeg'), ('WEBP','image/webp')]:
            original = image_bytes(format)
            response, official = self.search(original)
            self.assertEqual(response[0], 200, response[1])
            self.assertEqual(official.call_count, 1)
            row = self.rows()[0]
            self.assertTrue(row['has_detail'])
            code, saved, _ = self.detail(row['id'])
            self.assertEqual(code, 200)
            self.assertEqual(saved['detail']['response'], response[1])
            self.assertEqual(saved['detail']['grade'], 4)
            self.assertEqual(saved['detail']['image'], {'content_type':mime, 'width':7, 'height':5, 'bytes':len(original), 'sha256':hashlib.sha256(original).hexdigest()})
            code, raw, headers = self.image(row['id'])
            self.assertEqual((code, raw, headers['Content-Type']), (200, original, mime))
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            again = create_server(self.cfg)
            try:
                self.assertEqual(again.store.history_detail(row['id'])['detail'], saved['detail'])
                self.assertEqual(again.store.history_image(row['id']), (original, mime))
            finally:
                again.server_close()

    def test_distinct_requests_keep_own_image_grade_and_results(self):
        originals = [image_bytes('PNG'), image_bytes('JPEG')]
        responses = []
        for index, original in enumerate(originals):
            response, _ = self.search(original, grade=index, result={'ok':True, 'data':{'marker':index}})
            responses.append(response[1])
        rows = self.rows()
        for row, index in zip(rows, (1, 0)):
            detail = self.detail(row['id'])[1]['detail']
            self.assertEqual(detail['grade'], index)
            self.assertEqual(detail['response'], responses[index])
            self.assertEqual(self.image(row['id'])[1], originals[index])

    def test_failures_keep_valid_image_and_safe_response_only(self):
        for kind in ('network','signing_session','login_required','protocol','upstream'):
            response, official = self.search(error=UpstreamError('SYNTHETIC-PRIVATE-OFFICIAL-ERROR', 6, kind))
            self.assertEqual(response[0], 502)
            self.assertEqual(official.call_count, 1)
            row = self.rows()[0]
            detail = self.detail(row['id'])[1]['detail']
            self.assertEqual(detail['response'], response[1])
            self.assertEqual(self.image(row['id'])[1], image_bytes())
            self.assertNotIn('PRIVATE-OFFICIAL', json.dumps(detail))
        response, official = self.search(image=b'SYNTHETIC-invalid-image')
        self.assertEqual(response[0], 400)
        official.assert_not_called()
        row = self.rows()[0]
        saved = self.detail(row['id'])[1]['detail']
        self.assertIsNone(saved['image'])
        self.assertEqual(saved['response'], response[1])
        self.assertEqual(self.image(row['id'])[0], 404)

    def test_unpublished_late_result_is_never_saved_as_success(self):
        def change_profile(*_args, **_kwargs):
            profile = copy.deepcopy(SYNTHETIC_PROFILE)
            profile['session_token'] = 'SYNTHETIC-new-signing-session'
            self.server.accounts.import_profile(profile)
            return {'ok':True, 'data':{'unpublished':'SYNTHETIC-OLD-RESULT'}}
        response, official = self.search(error=change_profile)
        self.assertEqual(response[0], 409, response[1])
        self.assertEqual(official.call_count, 1)
        saved = self.detail(self.rows()[0]['id'])[1]['detail']
        self.assertEqual(saved['response'], response[1])
        self.assertNotIn('OLD-RESULT', json.dumps(saved))

    def test_details_and_images_require_admin_and_invalid_ids_are_safe(self):
        self.search()
        row = self.rows()[0]
        for suffix in ('', '/image'):
            path = '/api/admin/history/' + str(row['id']) + suffix
            self.assertEqual(self.request('GET', path)[0], 401)
            self.assertEqual(self.request('GET', path, headers={'Authorization':'Bearer ' + self.key})[0], 403)
            self.assertEqual(self.request('GET', path, headers={'Cookie':self.cookie, 'Authorization':'Bearer ' + self.key})[0], 403)
            self.assertEqual(self.admin('GET', path + '?secret=SYNTHETIC-query-secret')[0], 400)
            self.assertEqual(self.admin('POST', path, {})[0], 404)
        self.assertEqual(self.detail(9223372036854775807)[0], 404)
        for value in ('0','-1','../session.json','9999999999999999999','abc','{id}','%7Bid%7D'):
            self.assertEqual(self.detail(value)[0], 404)
        self.assertEqual(self.admin('GET', '/api/admin/history?action=account')[0], 400)
        self.assertEqual(self.admin('GET', '/api/admin/history?action=search&action=search')[0], 400)

    def test_metadata_and_detail_do_not_capture_auth_or_request_headers(self):
        self.search()
        rows = self.rows()
        self.assertNotIn('SYNTHETIC-返回题目', json.dumps(rows, ensure_ascii=False))
        self.assertNotIn('image_base64', json.dumps(rows))
        saved = self.detail(rows[0]['id'])[1]
        for secret in (self.key, self.password, self.cookie, self.csrf, SYNTHETIC_PROFILE['session_token'], SYNTHETIC_PROFILE['fields']['ZYBUSS'], SYNTHETIC_PROFILE['fields']['cuid']):
            self.assertNotIn(secret, json.dumps(saved))
        payload = {'image_base64':base64.b64encode(image_bytes()).decode(), 'grade':0}
        self.assertEqual(self.request('POST', '/api/v1/search', payload, {'Authorization':'Bearer SYNTHETIC-invalid-key'})[0], 401)
        rejected = self.rows()[0]
        self.assertFalse(rejected['has_detail'])
        self.assertIsNone(self.detail(rejected['id'])[1]['detail'])

    def test_storage_failure_rolls_back_history_and_details(self):
        with self.server.store.connect() as db:
            db.execute("CREATE TRIGGER synthetic_details_failure BEFORE INSERT ON search_details BEGIN SELECT RAISE(ABORT, 'SYNTHETIC-PRIVATE-STORAGE-ERROR'); END")
        response, official = self.search()
        self.assertEqual(response[0], 503)
        self.assertEqual(response[1]['code'], 'audit_unavailable')
        self.assertEqual(official.call_count, 1)
        self.assertEqual(self.rows(), [])
        self.assertNotIn('PRIVATE-STORAGE', str(response))

    def test_existing_history_migrates_without_fabricating_details(self):
        # 模拟已有只有 history 的私有库，再用相同配置启动。
        self.search()
        row = self.rows()[0]
        with self.server.store.connect() as db:
            db.execute('DROP TABLE search_details')
        again = create_server(self.cfg)
        try:
            self.assertIsNone(again.store.history_detail(row['id'])['detail'])
            self.assertFalse(again.store.history({'action':['search']})['items'][0]['has_detail'])
        finally:
            again.server_close()

    def test_retention_cleans_details_by_size_age_and_row_limit(self):
        self.search()
        with self.server.store.connect() as db:
            first_size = db.execute('SELECT stored_bytes FROM search_details').fetchone()[0]
        self.cfg.history_detail_bytes = first_size * 2
        self.search(); self.search()
        rows = self.rows()
        self.assertEqual([r['has_detail'] for r in rows], [True, True, False])
        self.assertIsNone(self.detail(rows[2]['id'])[1]['detail'])
        self.assertEqual(self.image(rows[2]['id'])[0], 404)
        with self.server.store.connect() as db:
            self.assertLessEqual(db.execute('SELECT SUM(stored_bytes) FROM search_details').fetchone()[0], self.cfg.history_detail_bytes)
            db.execute('UPDATE history SET time=? WHERE id=?', (time.time() - 31 * 86400, rows[1]['id']))
        self.assertEqual(self.detail(rows[1]['id'])[0], 404)
        self.cfg.history_limit = 1
        self.admin('GET', '/api/admin/account')
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM history').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM search_details').fetchone()[0], 0)

    def test_oversized_detail_does_not_evict_other_records(self):
        self.search()
        first = self.rows()[0]
        with self.server.store.connect() as db:
            self.cfg.history_detail_bytes = db.execute('SELECT stored_bytes FROM search_details').fetchone()[0]
        self.search(result={'ok':True,'data':{'larger':'x'*2000}})
        rows = self.rows()
        self.assertFalse(rows[0]['has_detail'])
        self.assertTrue(rows[1]['has_detail'])
        self.assertEqual(self.image(first['id'])[0], 200)

    def test_detail_budget_configuration_and_readback(self):
        from zyb_gateway.config import Config
        from zyb_gateway.__main__ import parser
        for value in (0, -1, True, '256', 2 * 1024**3 + 1):
            with self.assertRaises(ValueError):
                Config(data_dir=self.cfg.data_dir, history_detail_bytes=value)
        arguments = parser().parse_args(['serve', '--history-detail-bytes', '67108864'])
        self.assertEqual(arguments.history_detail_bytes, 67108864)
        retention = self.admin('GET', '/api/admin/settings')[1]['history_retention']
        self.assertEqual(retention, {'days':30, 'limit':10000, 'detail_bytes':256 * 1024**2})
