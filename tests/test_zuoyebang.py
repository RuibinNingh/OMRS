"""作业帮接入：配对、私有会话、过期观察、保真渲染、重试与创建回执。"""
import base64
import gzip
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from omrs import ai_assist, locking, vault_lifecycle as lifecycle, creation, uploads, workspace_sync
from omrs.zuoyebang import jobs, session, store, service_config
from omrs.zuoyebang.account import AccountClient
from omrs.zuoyebang.direct import DirectClient, decode_response, rc4, UpstreamError, NoRedirect
from omrs.zuoyebang.normalize import normalize_questions
from omrs.zuoyebang.html import candidate_html, sanitize, fetch_image
from omrs.zuoyebang.render import render_documents
from omrs.zuoyebang.commit import commit
from omrs.zuoyebang.validation import validate_image
from tests.zuoyebang_fixtures import profile, png, candidates
from tests.zuoyebang_gateway import SyntheticGateway, KEY


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-zyb-test-')
        self.vault = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def render_record(self, candidate=None):
        source = candidate or candidates()[0]
        return jobs.render(self.vault, {'source': source, 'search_id': 'search-' + 'a' * 32, 'candidate': {'index': 0, 'title': '合成题'}})

    def commit_data(self):
        return {'form': {'subject': '数学', 'category': '几何', 'difficulty': 5},
                'sections': {'question': {'mode': 'image'}, 'answer': {'mode': 'text', 'text': '完整答案 $AD=4$，面积 $12$。'}}}

    def test_candidates_remain_paired(self):
        result = normalize_questions({'data': {'answers': {'mainPageInfo': [json.dumps(candidates()[:2]), json.dumps(candidates()[2])]}}})
        self.assertEqual(len(result), 3)
        self.assertIn('候选二答案', result[1]['answer'][0]['content'])
        self.assertEqual(result[2]['location_index'], 1)
        self.assertEqual(result[2]['answer'], [])

    def test_login_notice_is_not_a_question(self):
        with self.assertRaises(UpstreamError) as caught:
            normalize_questions({'question': '登录提醒，请在个人中心登录', 'answer': ''})
        self.assertEqual(caught.exception.kind, 'login_required')

    def test_rc4_and_plain_gzip(self):
        self.assertEqual(rc4(b'Plaintext', 'Key').hex(), 'bbf316e8d940af0ad3')
        body = {'errNo': 0, 'data': {'encode': 1, 'answers': {'gzip': 1, 'mainPageInfo': [base64.b64encode(gzip.compress('测试题'.encode())).decode()]}}}
        self.assertEqual(decode_response(body, 'unused')['data']['answers']['mainPageInfo'], ['测试题'])
        with self.assertRaises(UpstreamError) as caught:
            decode_response({'errNo': 6}, 'unused')
        self.assertEqual(caught.exception.kind, 'signing_session')

    def test_no_credential_redirect(self):
        with self.assertRaises(UpstreamError):
            NoRedirect().redirect_request(None, None, None, None, None, 'https://example.org')

    def test_import_is_private_atomic_and_does_not_claim_verified(self):
        self.assertFalse(session.status(self.vault)['local_session_ready'])
        summary = session.import_profile(self.vault, profile())
        self.assertEqual(summary['observations']['account']['state'], 'unknown')
        self.assertNotIn('synthetic-account', json.dumps(summary))
        path = store.root(self.vault) / 'session.json'
        if os.name != 'nt':
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        previous = path.read_bytes()
        for invalid in [dict(profile(), url='https://localhost'), dict(profile(), headers={'Host': 'evil'}), dict(profile(), fields={})]:
            with self.assertRaises(store.ZybError):
                session.import_profile(self.vault, invalid)
            self.assertEqual(path.read_bytes(), previous)

    def test_webp_upload_preserves_bytes_and_cannot_be_consumed_as_create(self):
        encoded = io.BytesIO()
        with Image.open(io.BytesIO(png())) as image:
            image.save(encoded, 'WEBP')
        raw = encoded.getvalue()
        with uploads.request_owner('zyb-test'):
            started = uploads.start(self.vault, 'photo.webp', 'image/jpeg', len(raw), 'zuoyebang')
            uploads.chunk(self.vault, started['upload_id'], 0, raw)
            done = uploads.complete(self.vault, started['upload_id'])
            self.assertEqual(done['mime'], 'image/webp')
            self.assertEqual(uploads.read(self.vault, done), raw)
            with self.assertRaises(ValueError):
                uploads.resolve(self.vault, done, purpose='create')
            with SyntheticGateway() as gateway:
                service_config.save(self.vault, {'base_url': gateway.url, 'api_key': KEY})
                job = jobs.start_job(self.vault, 'search', {'image': done})
                for _ in range(100):
                    result = jobs.get_job(self.vault, job['id'])
                    if result['status'] != 'running': break
                    time.sleep(.02)
                self.assertEqual(result['status'], 'done')
                seen = [base64.b64decode(call['body']['image_base64']) for call in gateway.calls if call['path'] == '/api/v1/search']
                self.assertEqual(seen, [raw])

    def test_search_upload_rejects_incomplete_unsupported_and_oversize_images(self):
        with self.assertRaisesRegex(ValueError, '8MB'):
            uploads.start(self.vault, total_bytes=8 * 1024 * 1024 + 1, purpose='zuoyebang')
        started = uploads.start(self.vault, purpose='zuoyebang')
        with self.assertRaisesRegex(ValueError, '8MB'):
            uploads.chunk(self.vault, started['upload_id'], 0, b'x' * (8 * 1024 * 1024 + 1))
        with self.assertRaises(store.ZybError):
            validate_image(png()[:30])
        with patch('omrs.zuoyebang.validation.MAX_PIXELS', 100):
            with self.assertRaisesRegex(store.ZybError, '像素'):
                validate_image(png())
        gif = io.BytesIO()
        Image.new('RGB', (2, 2)).save(gif, 'GIF')
        with self.assertRaises(store.ZybError):
            validate_image(gif.getvalue())

    def test_expiry_is_observed_separately_and_network_is_not_expiry(self):
        session.import_profile(self.vault, profile())
        with patch('omrs.zuoyebang.store.time.time', return_value=10):
            store.observe(self.vault, 'search')
        with patch('omrs.zuoyebang.store.time.time', return_value=20):
            store.observe(self.vault, 'search', 'network')
        self.assertEqual(store.observations(self.vault)['account']['state'], 'valid')
        with patch('omrs.zuoyebang.store.time.time', return_value=30):
            store.observe(self.vault, 'search', 'signing_session', 6)
        state = store.observations(self.vault)
        self.assertEqual(state['account']['state'], 'valid')
        self.assertEqual(state['signing']['valid_until_after'], 10)
        self.assertEqual(state['signing']['first_invalid_at'], 30)
        store.observe(self.vault, 'verify', 'login_required')
        self.assertEqual(store.observations(self.vault)['account']['state'], 'invalid')
        store.observe(self.vault, 'verify')
        self.assertTrue(store.observations(self.vault)['events'][-1]['account_recovered'])
        log = (store.root(self.vault) / 'session-events.jsonl').read_text()
        for secret in ('synthetic-account', 'synthetic-signing-seed', 'Cookie', 'ZYBUSS'):
            self.assertNotIn(secret, log)

    def test_account_wait_does_not_hold_global_lock_and_stale_profile_is_rejected(self):
        session.import_profile(self.vault, profile())
        def verify(client):
            self.assertFalse(locking.held_by_current_thread())
            with lifecycle.exclusive(self.vault, timeout=.2):
                pass
            session.import_profile(self.vault, dict(profile(), session_token='replacement'))
            return {'server_verified': True}
        with patch.object(AccountClient, 'verify', verify):
            with self.assertRaises(store.ZybError) as caught:
                session.account_operation(self.vault, 'verify')
        self.assertEqual(caught.exception.code, 'session_changed')
        self.assertEqual(store.observations(self.vault)['account']['state'], 'unknown')

    def test_qr_cancel_blocks_late_login(self):
        session.import_profile(self.vault, profile())
        def request(operation, _profile, *_args, **_kwargs):
            if operation == 'qr_create': return {'errNo': 0, 'data': {'uuid': 'synthetic-qr'}}
            if operation == 'userinfo': return {'errNo': 0, 'data': {'user': {'uid': 1}}}
            if operation == 'qr_check':
                session.account_operation(self.vault, 'qr_cancel', flow['flow_id'])
                return {'errNo': 0, 'data': {'zybuss': 'late-account'}}
        with patch.object(AccountClient, 'request', side_effect=request):
            flow = session.account_operation(self.vault, 'qr_start')
            self.assertTrue(flow['qr_image'].startswith('data:image/png'))
            with self.assertRaises(store.ZybError) as caught:
                session.account_operation(self.vault, 'qr_poll', flow['flow_id'])
        self.assertEqual(caught.exception.code, 'session_changed')
        self.assertNotIn('late-account', store.profile_bytes(self.vault).decode())

    def test_sanitizer_preserves_content_and_rejects_unsafe_image(self):
        clean = sanitize('<script>evil()</script><p onclick="evil()">文字<a href="javascript:evil()">保留</a><span style="display:none">完整</span></p>')
        self.assertEqual(clean, '<p>文字保留<span>完整</span></p>')
        for src in ('file:///etc/passwd', 'http://127.0.0.1/a.png', 'https://qbimg.com.evil/a', 'https://u:p@qbimg.com/a'):
            with self.assertRaises(store.ZybError): sanitize('<img src="' + src + '">')
        for content in ('<svg><text>必要图形</text></svg>', '<math><mi>x</mi></math>', '<canvas>附图</canvas>'):
            with self.assertRaises(store.ZybError) as caught:
                sanitize(content)
            self.assertEqual(caught.exception.code, 'render_unsupported')
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 443))]):
            with self.assertRaises(store.ZybError): fetch_image('https://qbimg.com/a.png')

    def test_missing_image_fails_without_erasing_source(self):
        source = {'question': {'content': '<p>原题</p><img src="https://qbimg.com/absent.png">'}, 'answer': []}
        with patch('omrs.zuoyebang.jobs.candidate_html', side_effect=store.ZybError('缺图', 'image_missing')):
            with self.assertRaises(store.ZybError): self.render_record(source)
        record = store.read(self.vault, jobs.history(self.vault)[0]['id'])
        self.assertEqual(record['source'], source)
        self.assertEqual(record['status'], 'failed')

    def test_real_1080_render_has_full_answer_and_image_formula(self):
        record = self.render_record()
        for role in ('question', 'answer'):
            raw = jobs.image(self.vault, record['id'], role)
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.width, 1080)
                self.assertEqual(image.height, record['images'][role]['height'])
        self.assertGreater(record['images']['answer']['height'], 3000)
        self.assertEqual(record['images']['question']['images'], 1)
        self.assertEqual(record['images']['answer']['images'], 1)
        self.assertIn('解析末尾', record['images']['answer']['html'])
        self.assertNotIn('data:image', record['images']['answer']['html'])
        self.assertEqual(len(list(store.location(self.vault, record['id']).glob('answer*.png'))), 1)

    def test_physical_limit_and_empty_answer(self):
        with patch('omrs.zuoyebang.render.PIXEL_BUDGET', 100):
            with self.assertRaises(store.ZybError) as caught:
                self.render_record()
            self.assertEqual(caught.exception.code, 'render_resource')
        record = self.render_record(candidates()[2])
        self.assertTrue(record['images']['answer']['empty'])

    def test_partial_extraction_keeps_success_and_retry_only_failed(self):
        record = self.render_record()
        calls = []
        def extract(_vault, _image, role, judge):
            calls.append(role)
            self.assertTrue(judge)
            if role == 'answer' and calls.count(role) == 1: raise TimeoutError('模拟超时')
            return {'convertible': role == 'answer', 'text': '完整原答案' if role == 'answer' else '', 'reason': '图片保真'}
        with patch.object(ai_assist, 'extract_region', side_effect=extract), patch.object(ai_assist, 'recognize_question', return_value={'subject': '数学'}):
            result = jobs.extract(self.vault, {'render_id': record['id']})
            self.assertEqual(result['extraction']['question']['mode'], 'image')
            self.assertEqual(result['extraction']['answer']['status'], 'failed')
            result = jobs.extract(self.vault, {'render_id': record['id']})
        self.assertEqual(calls, ['question', 'answer', 'answer'])
        self.assertEqual(result['extraction']['answer']['text'], '完整原答案')

    def test_creation_is_idempotent_and_recovers_after_receipt_save_failure(self):
        record = self.render_record()
        data = self.commit_data()
        original = store.save
        def save(vault, identity, value):
            if value.get('commit', {}).get('result'): raise OSError('模拟回执发布中断')
            return original(vault, identity, value)
        with patch.object(store, 'save', side_effect=save):
            with self.assertRaises(OSError): commit(self.vault, record['id'], data)
        result = commit(self.vault, record['id'], data)
        self.assertTrue(result['reused'])
        self.assertEqual(len(list(Path(self.vault).rglob('几何[0-9]*.md'))), 1)
        with self.assertRaises(store.ZybError):
            commit(self.vault, record['id'], {**data, 'form': {'subject': '数学', 'category': '另一个分类'}})

    def test_pending_uid_cannot_be_taken_by_quick_create(self):
        record = self.render_record()
        with patch.object(creation, 'create_question', side_effect=RuntimeError('模拟创建前中断')):
            with self.assertRaises(RuntimeError): commit(self.vault, record['id'], self.commit_data())
        result = creation.create_question(self.vault, '数学', '几何', 5, question_text='其它题目')
        self.assertEqual(result['uid'], '几何2')
        first = commit(self.vault, record['id'], self.commit_data())
        self.assertEqual(first['uid'], '几何1')

    def test_scan_does_not_import_pending_file_as_external_question(self):
        record = self.render_record()
        with patch.object(creation, 'append_commit_in_db', side_effect=OSError('模拟 Ledger 提交前中断')):
            with self.assertRaises(OSError):
                commit(self.vault, record['id'], self.commit_data())
        self.assertEqual(len(list(Path(self.vault).rglob('几何[0-9]*.md'))), 1)
        scanned = workspace_sync.scan_workspace(self.vault)
        self.assertEqual(scanned['changes'], 0)
        result = commit(self.vault, record['id'], self.commit_data())
        self.assertEqual(result['uid'], '几何1')
        with creation.connect(self.vault) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM commits WHERE commit_type LIKE 'question.create%'").fetchone()[0], 1)

    def test_new_vault_generation_prevents_late_render_publication(self):
        source = candidates()[1]
        original = jobs.candidate_html
        def changed(candidate):
            with lifecycle.exclusive(self.vault): lifecycle.advance_generation(self.vault)
            return original(candidate)
        with lifecycle.task(self.vault), patch.object(jobs, 'candidate_html', side_effect=changed):
            with self.assertRaises(lifecycle.VaultChanged): self.render_record(source)

    def test_restarted_job_is_explicit_failure(self):
        identity = 'job-' + 'b' * 32
        store.save(self.vault, identity, {'id': identity, 'kind': 'job', 'status': 'running', 'instance': 'old'})
        self.assertEqual(jobs.get_job(self.vault, identity)['code'], 'job_interrupted')

    def test_restored_running_job_is_interrupted_even_in_same_process(self):
        identity = 'job-' + 'c' * 32
        store.save(self.vault, identity, {'id': identity, 'kind': 'job', 'status': 'running',
                                         'instance': jobs.INSTANCE, 'generation': lifecycle.generation(self.vault)})
        with lifecycle.exclusive(self.vault): lifecycle.advance_generation(self.vault)
        result = jobs.get_job(self.vault, identity)
        self.assertEqual(result['code'], 'job_interrupted')
        self.assertNotIn('generation', result)

    def test_truncated_ai_output_is_not_accepted_even_if_json_is_closed(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self): return json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': '{"convertible":true,"text":"不完整"}'}}]}).encode()
        with patch.object(ai_assist, '_ai_config', return_value=('https://example.org', 'fake', 'fake')), patch.object(ai_assist, '_apply_thinking'), patch('urllib.request.urlopen', return_value=Response()):
            with self.assertRaisesRegex(ValueError, '长度限制'): ai_assist.extract_region(self.vault, 'data:image/png;base64,aA==')


if __name__ == '__main__': unittest.main()
