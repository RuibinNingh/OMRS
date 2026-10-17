"""日志导出：真实文件、只读边界、追加快照与 Web 鉴权。"""
import contextlib
import datetime as dt
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import zipfile

from omrs import locking, log_export
from omrs.server import OMRSHandler


class LogFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-log-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, body='日志\r\n'.encode()):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path


class LogExportTests(LogFixture, unittest.TestCase):
    def test_empty_read_does_not_create_log_directories_or_business_databases(self):
        self.assertEqual(log_export.list_logs(self.root)['files'], [])
        self.assertFalse((self.root / 'logs').exists())
        self.assertFalse((self.root / '错题').exists())

    def test_list_has_only_regular_logs_in_fixed_roots_and_shanghai_dates(self):
        old = self.write('logs/omrs_old.log')
        os.utime(old, (0, 0))
        recent = self.write('错题/.omrs/logs/agent-llm.jsonl')
        stamp = dt.datetime(2026, 10, 16, 17, tzinfo=dt.timezone.utc).timestamp()
        os.utime(recent, (stamp, stamp))
        self.write('logs/omrs.log.1.gz')
        self.write('logs/not-a-log.json')
        self.write('logs/sub/nested.log')
        self.write('AI/logs/2026-10-17_task.md')
        self.write('错题/.omrs/config.json')
        (self.root / 'logs' / 'linked.log').symlink_to(recent)
        (self.root / 'logs' / 'directory.log').mkdir()
        if hasattr(os, 'mkfifo'):
            os.mkfifo(self.root / 'logs' / 'pipe.log')
        files = log_export.list_logs(self.root)['files']
        self.assertEqual({item['id'] for item in files}, {'runtime:omrs_old.log', 'runtime:omrs.log.1.gz', 'ai:agent-llm.jsonl'})
        self.assertEqual(files[-1]['id'], 'runtime:omrs_old.log')
        self.assertEqual(next(item for item in files if item['kind'] == 'ai')['modified_day'], '2026-10-17')

    def test_zip_contains_only_selected_files_with_exact_bytes_and_deduplicates(self):
        expected = b'\xe6\x97\xa5\xe5\xbf\x97\r\n\x00raw'
        self.write('logs/中文.log', expected)
        self.write('错题/.omrs/logs/agent-llm.jsonl', b'{"request":"synthetic"}\n')
        self.write('logs/unselected.log', b'not-selected')
        artifact, name = log_export.create_log_export(self.root, ['runtime:中文.log', 'ai:agent-llm.jsonl', 'runtime:中文.log'])
        self.addCleanup(lambda: os.unlink(artifact))
        self.assertRegex(name, r'^OMRS-logs-\d{8}-\d{6}\.zip$')
        with zipfile.ZipFile(artifact) as archive:
            self.assertEqual(set(archive.namelist()), {'运行日志/中文.log', 'AI请求日志/agent-llm.jsonl'})
            self.assertEqual(archive.read('运行日志/中文.log'), expected)
            self.assertNotEqual(archive.getinfo('运行日志/中文.log').date_time[0], 1980)

    def test_invalid_selection_and_paths_are_rejected(self):
        self.write('logs/valid.log')
        for files in (None, [], 'runtime:valid.log', [3], ['runtime:../secret.log'], ['runtime:/tmp/a.log'],
                      ['ai:..\\secret.log'], ['runtime:a.log\x00'], ['unknown:a.log'], ['runtime:.hidden.log'],
                      ['runtime:config.json'], ['runtime:C:a.log'], ['AI/logs/task.md']):
            with self.subTest(files=files), self.assertRaises(ValueError):
                log_export.create_log_export(self.root, files)

    def test_symlinked_directory_components_are_excluded(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'private.log').write_bytes(b'private')
        for prefix, child in (('', 'logs'), ('错题', '.omrs'), ('错题/.omrs', 'logs')):
            with self.subTest(prefix=prefix):
                vault = self.root / ('vault-' + str(len(prefix)))
                parent = vault / prefix
                parent.mkdir(parents=True)
                (parent / child).symlink_to(outside, target_is_directory=True)
                self.assertEqual(log_export.list_logs(vault)['files'], [])
                kind = 'runtime' if not prefix else 'ai'
                with self.assertRaises(log_export.LogUnavailable):
                    log_export.create_log_export(vault, [f'{kind}:private.log'])

    def test_deleted_or_replaced_file_fails_instead_of_partial_zip(self):
        path = self.write('logs/safe.log')
        log_export.list_logs(self.root)
        path.unlink()
        with self.assertRaises(log_export.LogUnavailable):
            log_export.create_log_export(self.root, ['runtime:safe.log'])
        target = self.write('secret.log', b'secret')
        path.symlink_to(target)
        with self.assertRaises(log_export.LogUnavailable):
            log_export.create_log_export(self.root, ['runtime:safe.log'])

    def test_size_and_count_limits_clean_up_temporary_archives(self):
        self.write('logs/large.log', b'12345')
        original = tempfile.mkstemp
        with patch.object(log_export, 'MAX_EXPORT_BYTES', 3), patch.object(log_export.tempfile, 'mkstemp', side_effect=lambda **kw: original(dir=self.root, **kw)):
            with self.assertRaises(ValueError):
                log_export.create_log_export(self.root, ['runtime:large.log'])
        self.assertEqual(list(self.root.glob('omrs-logs-*.zip')), [])
        with patch.object(log_export, 'MAX_EXPORT_FILES', 1), self.assertRaises(ValueError):
            log_export.create_log_export(self.root, ['runtime:one.log', 'runtime:two.log'])

    def test_append_exports_opening_length_and_truncation_reports_conflict(self):
        path = self.write('logs/active.log', b'original')
        original = log_export._open_log

        @contextlib.contextmanager
        def append_after_open(*args):
            with original(*args) as value:
                with path.open('ab') as target:
                    target.write(b' appended')
                yield value

        with patch.object(log_export, '_open_log', append_after_open):
            artifact, _ = log_export.create_log_export(self.root, ['runtime:active.log'])
        try:
            with zipfile.ZipFile(artifact) as archive:
                self.assertEqual(archive.read('运行日志/active.log'), b'original')
        finally:
            os.unlink(artifact)

        @contextlib.contextmanager
        def truncate_after_open(*args):
            with original(*args) as value:
                path.write_bytes(b'')
                yield value

        with patch.object(log_export, '_open_log', truncate_after_open), self.assertRaises(log_export.LogUnavailable):
            log_export.create_log_export(self.root, ['runtime:active.log'])


class LogExportHTTPTests(LogFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write('logs/web.log', b'web-log')
        handler = type('LogHandler', (OMRSHandler,), {'vault_path': str(self.root), 'log_message': lambda *_: None})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, None if data is None else json.dumps(data), {'Content-Type': 'application/json', **(headers or {})})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_web_list_download_no_cache_and_no_business_write_lock(self):
        status, headers, body = self.request('GET', '/api/logs')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(body)['files'][0]['id'], 'runtime:web.log')
        with locking.write_lock():
            status, headers, body = self.request('POST', '/api/logs/export', {'files': ['runtime:web.log']})
        self.assertEqual(status, 200, body)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn('attachment;', headers['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(archive.read('运行日志/web.log'), b'web-log')

    def test_web_auth_mcp_origin_and_stale_selection(self):
        endpoints = [('GET', '/api/logs', None), ('POST', '/api/logs/export', {'files': ['runtime:web.log']})]
        for method, path, data in endpoints:
            self.assertEqual(self.request(method, path, data, {'Host': 'omrs.test', 'X-Real-IP': '198.51.100.77', 'X-Forwarded-Proto': 'https'})[0], 401)
            self.assertEqual(self.request(method, path, data, {'Authorization': 'Bearer synthetic-mcp'})[0], 403)
        self.assertEqual(self.request('POST', '/api/logs/export', {'files': ['runtime:web.log']}, {'Origin': 'https://other.invalid'})[0], 403)
        self.assertEqual(self.request('POST', '/api/logs/export', {'files': []})[0], 400)
        self.assertEqual(self.request('POST', '/api/logs/export', {'files': ['runtime:missing.log']})[0], 409)


if __name__ == '__main__':
    unittest.main()
