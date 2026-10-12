"""真实合成网关搜题任务：原件、无直连、开始冻结配置与迟到发布屏障。"""
import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from omrs import locking, uploads, vault_lifecycle as lifecycle
from omrs.zuoyebang import jobs, service_config, store
from omrs.zuoyebang.direct import DirectClient
from tests.zuoyebang_gateway import SyntheticGateway, KEY
from tests.zuoyebang_fixtures import png


class ServiceJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-service-jobs-')
        self.vault = self.temp.name
        self.gateway = SyntheticGateway().__enter__()
        service_config.save(self.vault, {'base_url': self.gateway.url, 'api_key': KEY})

    def tearDown(self):
        self.gateway.__exit__(); self.temp.cleanup()

    def start(self):
        raw = png()
        started = uploads.start(self.vault, 'source.png', 'image/png', len(raw), 'zuoyebang')
        uploads.chunk(self.vault, started['upload_id'], 0, raw)
        image = uploads.complete(self.vault, started['upload_id'])
        try:
            return jobs.start_job(self.vault, 'search', {'image': image, 'grade': 7})
        except store.ZybError as exc:
            self.fail('独立网关配置仍不能启动搜题：' + exc.code)

    def wait(self, identity):
        for _ in range(200):
            row = jobs.get_job(self.vault, identity)
            if row['status'] != 'running': return row
            time.sleep(.01)
        self.fail('搜题任务未按预算收束')

    def test_search_uses_gateway_only_without_importing_legacy_session(self):
        with patch.object(DirectClient, 'search', side_effect=AssertionError('不能旧直连')):
            job = self.start()
            result = self.wait(job['id'])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(len(result['result']['candidates']), 3)
        call = self.gateway.calls[-1]
        self.assertEqual(call['path'], '/api/v1/search')
        self.assertEqual(base64.b64decode(call['body']['image_base64']), png())
        self.assertEqual(call['body']['grade'], 7)
        self.assertFalse((store.root(self.vault) / 'session.json').exists())
        self.assertNotIn(KEY, json.dumps(result))
        self.assertEqual(result['service']['api_key_fingerprint'], service_config.public(self.vault)['api_key_fingerprint'])

    def test_switch_during_search_rejects_old_publish_without_holding_locks(self):
        entered, release = threading.Event(), threading.Event()
        self.gateway.before = lambda _path: (entered.set(), release.wait(2))
        try:
            job = self.start()
            self.assertTrue(entered.wait(1))
            with locking.write_lock(timeout=.2), lifecycle.exclusive(self.vault, timeout=.2): pass
            service_config.save(self.vault, {'api_key': 'synthetic-new-key'})
        finally:
            release.set()
        result = self.wait(job['id'])
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['code'], 'service_changed')
        self.assertEqual(list(store.root(self.vault).glob('search-*')), [])
        self.assertEqual(self.gateway.calls[0]['headers']['Authorization'], 'Bearer ' + KEY)
        self.assertNotIn(KEY, json.dumps(result))

    def test_vault_restore_during_search_cannot_publish_old_result(self):
        entered, release = threading.Event(), threading.Event()
        self.gateway.before = lambda _path: (entered.set(), release.wait(2))
        try:
            job = self.start()
            self.assertTrue(entered.wait(1))
            with lifecycle.exclusive(self.vault, timeout=.2): lifecycle.advance_generation(self.vault)
        finally:
            release.set()
        time.sleep(.1)
        self.assertEqual(jobs.get_job(self.vault, job['id'])['code'], 'job_interrupted')
        self.assertEqual(list(store.root(self.vault).glob('search-*')), [])

    def test_switch_during_render_prevents_ready_publication(self):
        from tests.zuoyebang_fixtures import candidates
        expected = service_config.snapshot(self.vault)
        def rendering(_bodies, output):
            service_config.save(self.vault, {'api_key': 'synthetic-switched'})
            return {'question': {'empty': True}, 'answer': {'empty': True}, 'engine': 'synthetic-boundary', 'browser': 'test'}
        with patch.object(jobs, 'render_documents', side_effect=rendering), self.assertRaises(store.ZybError) as caught:
            jobs.render(self.vault, {'source': candidates()[1], 'search_id': 'search-' + 'a' * 32,
                                     'candidate': {'index': 1}, 'service_snapshot': expected})
        self.assertEqual(caught.exception.code, 'service_changed')
        self.assertFalse(any(row['status'] == 'ready' for row in jobs.history(self.vault)))

    def test_vault_restore_during_render_does_not_write_failure_into_restored_record(self):
        from tests.zuoyebang_fixtures import candidates
        expected = service_config.snapshot(self.vault)
        replaced = {}
        def rendering(_bodies, _output):
            identity = next(store.root(self.vault).glob('render-*')).name
            with lifecycle.exclusive(self.vault):
                lifecycle.advance_generation(self.vault)
                record = store.read(self.vault, identity)
                record.update(status='ready', marker='恢复后的记录')
                store.save(self.vault, identity, record)
            replaced['identity'] = identity
            return {'question': {'empty': True}, 'answer': {'empty': True}, 'engine': 'synthetic-boundary', 'browser': 'test'}
        with patch.object(jobs, 'render_documents', side_effect=rendering), self.assertRaises(lifecycle.VaultChanged):
            jobs.render(self.vault, {'source': candidates()[1], 'search_id': 'search-' + 'a' * 32,
                                     'candidate': {'index': 1}, 'service_snapshot': expected})
        restored = store.read(self.vault, replaced['identity'])
        self.assertEqual(restored['status'], 'ready')
        self.assertEqual(restored['marker'], '恢复后的记录')

    def test_switch_after_search_before_job_receipt_does_not_expose_late_result(self):
        original = jobs._publish
        def publish(vault, identity, record, config):
            if record.get('kind') == 'job' and record.get('status') == 'done':
                service_config.save(vault, {'api_key': 'synthetic-switch-after-search'})
            return original(vault, identity, record, config)
        with patch.object(jobs, '_publish', side_effect=publish):
            job = self.start()
            result = self.wait(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['code'], 'service_changed')
        self.assertNotIn('result', result)

    def test_switch_during_model_extract_prevents_extraction_publication(self):
        from omrs import ai_assist
        identity = 'render-' + 'f' * 32
        raw = png(); directory = store.location(self.vault, identity); directory.mkdir()
        (directory / 'question.png').write_bytes(raw)
        store.save(self.vault, identity, {'id': identity, 'kind': 'render', 'status': 'ready', 'created_at': 1,
                    'images': {'question': {'sha256': store.fingerprint(raw)}, 'answer': {'empty': True}}, 'extraction': {}})
        expected = service_config.snapshot(self.vault)
        def extract(*_args, **_kwargs):
            service_config.save(self.vault, {'api_key': 'synthetic-switched'})
            return {'convertible': True, 'text': '迟到模型内容', 'reason': '合成模型'}
        with patch.object(ai_assist, 'extract_region', side_effect=extract), patch.object(ai_assist, 'recognize_question', return_value={}), self.assertRaises(store.ZybError) as caught:
            jobs.extract(self.vault, {'render_id': identity, 'service_snapshot': expected})
        self.assertEqual(caught.exception.code, 'service_changed')
        self.assertEqual(store.read(self.vault, identity)['extraction'], {})
