"""训练面板的文件契约、路径边界与隔离 HTTP 路由。"""
import datetime
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from omrs import trainpanel
from omrs.cli import OMRSTCPServer
from omrs.common import save_config
from omrs.server import OMRSHandler


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-trainpanel-')
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / 'vault'
        self.root = Path(self.temp.name) / 'train'
        save_config(str(self.vault), {'train_dir': str(self.root)})

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def status(self, **kwargs):
        return dict(state='running', epoch=3, epochs=120, started_at='2026-09-29T00:00:00+08:00',
                    updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    epoch_seconds=8, pid=os.getpid(), dataset='d1', **kwargs)

    def test_empty_directory_no_writes(self):
        before = sorted(self.vault.rglob('*'))
        result = trainpanel.overview(str(self.vault))
        self.assertEqual(result['runs'], [])
        self.assertIsNone(result['dataset'])
        self.assertFalse(self.root.exists())
        self.assertEqual(before, sorted(self.vault.rglob('*')))
        self.assertEqual(trainpanel.service(str(self.vault))['state'], 'unconfigured')

    def test_running_done_failed_and_interrupted(self):
        value = self.status()
        self.assertEqual(trainpanel.status_view(value)['state'], 'running')
        for state in ('done', 'failed'):
            self.assertEqual(trainpanel.status_view(dict(value, state=state))['state'], state)
        self.assertEqual(trainpanel.status_view(dict(value, pid=999999999))['state'], 'interrupted')
        self.assertEqual(trainpanel.status_view(dict(value, updated_at='2000-01-01'))['state'], 'interrupted')
        self.assertEqual(value['state'], 'running')

    def test_files_isolate_errors(self):
        self.write('runs/r1/status.json', self.status())
        self.write('runs/r1/eval.json', {}).write_text('{bad')
        path = self.root / 'runs/r1/metrics.jsonl'
        path.write_text('{"epoch":1,"loss":2}\n{"epoch":2')
        result = trainpanel.run_detail(str(self.vault), 'r1')
        self.assertEqual(result['metrics'], [{'epoch': 1, 'loss': 2}])
        self.assertIn('evaluation', result['errors'])
        self.assertEqual(result['status']['epoch'], 3)
        overview = trainpanel.overview(str(self.vault))
        self.assertEqual(overview['latest']['name'], 'r1')
        self.assertIsNotNone(overview['latest']['eval_error'])

    def test_corrupt_status_keeps_other_runs(self):
        self.write('runs/r1/status.json', self.status())
        self.write('runs/r2/status.json', {}).write_text('[')
        self.assertEqual(len(trainpanel.overview(str(self.vault))['runs']), 2)

    def test_path_traversal_and_symlink(self):
        self.root.mkdir()
        (self.root / 'runs').mkdir()
        (self.root / 'runs' / 'escape').symlink_to(self.vault, target_is_directory=True)
        for run in ('../vault', '/etc', '..', 'escape', 'a/b', 'a\\b'):
            with self.assertRaises(ValueError):
                trainpanel.run_detail(str(self.vault), run)

    def test_overlay_only_registered_image(self):
        self.write('runs/r1/eval.json', {'overlays': [{'name': 'a.jpg'}]})
        folder = self.root / 'runs/r1/overlays'
        folder.mkdir()
        (folder / 'a.jpg').write_bytes(b'image')
        (folder / 'b.jpg').write_bytes(b'private')
        self.assertEqual(trainpanel.overlay_path(str(self.vault), 'r1', 'a.jpg'), folder / 'a.jpg')
        for name in ('b.jpg', '../status.json'):
            with self.assertRaises(ValueError):
                trainpanel.overlay_path(str(self.vault), 'r1', name)

    def test_additional_excludes_previously_rejected(self):
        from omrs import annotate
        from tests.test_annotate import make_png
        image = annotate.upload(str(self.vault), [('x.png', make_png(10, 20))])['images'][0]
        annotate.save(str(self.vault), image['id'], [], status='done')
        self.write('datasets/d1/manifest.json', {'version': 'd1', 'samples': [], 'excluded': [{'id':'annotate:'+image['id'], 'reason':'缺类'}]})
        self.assertEqual(trainpanel.overview(str(self.vault))['live']['additional'], 0)

    def start_http(self):
        vault = str(self.vault)
        class Handler(OMRSHandler):
            vault_path = vault
            def log_message(self, *args):
                pass
        server = OMRSTCPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_http_routes_and_error(self):
        self.write('runs/r1/status.json', self.status())
        port = self.start_http()
        for path, code in [('/api/trainpanel/overview', 200), ('/api/trainpanel/run?name=r1', 200),
                           ('/api/trainpanel/run?name=..', 400), ('/api/trainpanel/overlay?run=r1&name=a.jpg', 400),
                           ('/api/trainpanel/service', 200)]:
            conn = http.client.HTTPConnection('127.0.0.1', port)
            conn.request('GET', path)
            response = conn.getresponse(); response.read()
            self.assertEqual(response.status, code, path)
            conn.close()
