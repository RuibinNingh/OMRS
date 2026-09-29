"""训练面板的文件契约、路径边界与隔离 HTTP 路由。"""
import datetime
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

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

    def test_online_model_and_training_default_are_separate(self):
        self.write('models/current/model.json', {'name': 'old', 'run': 'old', 'sha256': 'old-sha'})
        self.write('runs/new/export.json', {'onnx_sha256': 'online-sha'})
        self.write('runs/new/status.json', {'state': 'done'})
        with patch.object(trainpanel, 'service', return_value={'state': 'online',
                'model': {'name': 'new', 'sha256': 'online-sha'}}):
            overview = trainpanel.overview(str(self.vault))
        self.assertEqual(overview['training_model']['name'], 'old')
        self.assertEqual(overview['online_model']['name'], 'new')
        self.assertTrue(overview['runs'][0]['online'])
        self.assertFalse(overview['runs'][0]['current'])

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
        annotate.save(str(self.vault), image['id'], [], status='done',
                      expected_revision=image['revision'])
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

    def test_structurally_corrupt_file_isolated(self):
        self.write('runs/r1/status.json', self.status())
        self.write('runs/r1/eval.json', {'overlays':None})
        self.write('datasets/d1/manifest.json', {'samples':None})
        result = trainpanel.overview(str(self.vault))
        self.assertIn('dataset', result['errors'])
        self.assertIsNotNone(result['latest']['eval_error'])
        self.assertEqual(result['latest']['status']['state'], 'running')

    def test_commands_use_fresh_paths_and_exact_resume_identity(self):
        self.write('runs/r1/status.json', self.status())
        self.write('runs/r1/identity.json', {'epochs':3,'imgsz':960,'batch':2,'threads':4,'weights':'/tmp/a b.pt'})
        self.write('datasets/d1/manifest.json', {'version':'d1'})
        value = trainpanel.overview(str(self.vault))['commands']
        self.assertIn('--epochs 3', value['resume'])
        self.assertIn('--imgsz 960', value['resume'])
        self.assertNotIn('--run ' + str(self.root / 'runs/r1'), value['train'])
        self.assertNotIn('--out ' + str(self.root / 'datasets/d1'), value['build'])
        self.assertIn('--run ' + str(self.root / 'runs/r1'), value['evaluate'])

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


class TryTests(unittest.TestCase):
    setUp = PanelTests.setUp
    start_http = PanelTests.start_http

    def fake(self, invalid=False):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class Fake(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body = b'bad-json' if invalid else json.dumps({'boxes': [
                    {'label':'question', 'bbox_2d':[.1,.1,.9,.4], 'confidence':.9},
                    {'label':'answer', 'bbox_2d':[.1,.5,.9,.95], 'confidence':.85}]}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"sha256":"fake"}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        save_config(str(self.vault), {'inbox_local_detect_url':f'http://127.0.0.1:{server.server_port}/detect'})
        return server

    def png(self):
        from tests.test_annotate import make_png
        return make_png(100, 650)

    def test_try_off_multistrip_no_persistence(self):
        self.fake()
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.vault.rglob('*') if p.is_file()}
        result = trainpanel.try_image(str(self.vault), [('x.png', self.png())])
        self.assertGreater(result['strips'], 1)
        self.assertEqual({b['role'] for b in result['boxes']}, {'question','answer'})
        self.assertNotIn('collected', result)
        self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.vault.rglob('*') if p.is_file()})
        self.assertEqual(trainpanel.service(str(self.vault))['state'], 'online')

    def test_collect_todo_and_duplicate_keeps_human_boxes(self):
        from omrs import annotate
        self.fake(); save_config(str(self.vault), {'train_try_collect':True})
        result = trainpanel.try_image(str(self.vault), [('x.png', self.png())])
        image_id = result['collected']['id']
        image = annotate.list_images(str(self.vault))[0]
        self.assertEqual(image['status'], 'todo')
        self.assertGreater(len(image['boxes']), 0)
        human = [{'role':'answer','x':0,'y':0,'w':1,'h':1}]
        annotate.save(str(self.vault), image_id, human, status='done',
                      expected_revision=image['revision'])
        again = trainpanel.try_image(str(self.vault), [('same.png', self.png())])
        self.assertTrue(again['collected']['duplicate'])
        images = annotate.list_images(str(self.vault))
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]['boxes'], human)
        self.assertEqual(images[0]['status'], 'done')

    def test_collect_failure_keeps_result(self):
        from unittest.mock import patch
        self.fake(); save_config(str(self.vault), {'train_try_collect':True})
        with patch('omrs.annotate.upload', side_effect=OSError('disk full')):
            result = trainpanel.try_image(str(self.vault), [('x.png', self.png())])
        self.assertIn('积累失败', result['collect_error'])
        self.assertGreater(len(result['boxes']), 0)

    def test_service_missing_offline_invalid_json(self):
        with self.assertRaisesRegex(ValueError, '尚未配置'):
            trainpanel.try_image(str(self.vault), [('x.png', self.png())])
        server = self.fake(invalid=True)
        with self.assertRaisesRegex(ValueError, '未返回 JSON'):
            trainpanel.try_image(str(self.vault), [('x.png', self.png())])
        server.shutdown(); server.server_close()
        with self.assertRaisesRegex(ValueError, '检测服务未启动'):
            trainpanel.try_image(str(self.vault), [('x.png', self.png())])
        self.assertEqual(trainpanel.service(str(self.vault))['state'], 'offline')

    def test_reject_bad_image_count_and_size(self):
        self.fake()
        for files in [[], [('a',b'broken')], [('a',self.png()),('b',self.png())], [('a',b'x'*(15*1024*1024+1))]]:
            with self.assertRaises(ValueError):
                trainpanel.try_image(str(self.vault), files)

    def test_http_try_origin_and_payload_limit(self):
        self.fake(); port = self.start_http()
        body = b'--test\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\nContent-Type: image/png\r\n\r\n'+self.png()+b'\r\n--test--\r\n'
        for origin, expected in [(f'http://127.0.0.1:{port}',200), ('https://elsewhere.invalid',403)]:
            conn = http.client.HTTPConnection('127.0.0.1',port)
            conn.request('POST','/api/trainpanel/try',body,{'Content-Type':'multipart/form-data; boundary=test','Origin':origin})
            response = conn.getresponse(); response.read(); self.assertEqual(response.status,expected); conn.close()
        conn = http.client.HTTPConnection('127.0.0.1',port)
        conn.request('POST','/api/trainpanel/try',b'',{'Content-Length':str(20*1024*1024),'Content-Type':'multipart/form-data; boundary=test'})
        response = conn.getresponse(); response.read(); self.assertEqual(response.status,400); conn.close()

    def test_detection_outside_write_lock_collection_inside(self):
        from unittest.mock import patch
        from omrs import annotate, locking
        save_config(str(self.vault), {'inbox_local_detect_url':'http://127.0.0.1:1', 'train_try_collect':True})
        original = annotate.upload
        def detect(*args, **kwargs):
            self.assertFalse(locking.held_by_current_thread())
            return []
        def collect(*args, **kwargs):
            self.assertTrue(locking.held_by_current_thread())
            return original(*args, **kwargs)
        self.assertTrue(locking.post_exempt('/api/trainpanel/try'))
        with patch('omrs.ai_assist.detect_regions_local', side_effect=detect), patch('omrs.annotate.upload', side_effect=collect):
            trainpanel.try_image(str(self.vault), [('x.png',self.png())])
