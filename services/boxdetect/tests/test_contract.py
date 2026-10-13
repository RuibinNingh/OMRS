"""真实 HTTP 验证模型身份、返回坐标与非法输入；推理用确定性替身。"""
import base64
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
from boxdetect_service import model, server
from boxdetect_service.inference import nms, restore_box


class FakeDetector:
    def __init__(self, path, conf):
        self.size = 640
        self.conf = conf

    def __call__(self, image):
        return [{'role': 'answer', 'x': .25, 'y': .4, 'w': .8, 'h': .7, 'conf': .9}]


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'model.onnx').write_bytes(b'model')
        self.meta = {'name': 'fixed', 'sha256': model.sha256(self.folder / 'model.onnx'),
                     'classes': ['question', 'answer'], 'imgsz': 640, 'conf': .1}
        self.save_meta()

    def save_meta(self):
        (self.folder / 'model.json').write_text(json.dumps(self.meta))

    def start(self):
        with patch.object(server, 'Detector', FakeDetector):
            self.http = server.make_server(self.folder, 0)
        self.addCleanup(self.http.server_close)
        thread = threading.Thread(target=lambda: self.http.serve_forever(poll_interval=.02), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.http.shutdown)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.http.server_address, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_health_comes_from_loaded_model_and_binds_loopback(self):
        self.start()
        self.assertEqual(self.http.server_address[0], '127.0.0.1')
        self.assertEqual(self.request('GET', '/health'), (200, {'file': 'model.onnx', **self.meta}))
        self.meta['name'] = 'changed-on-disk'
        self.save_meta()
        self.assertEqual(self.request('GET', '/health')[1]['name'], 'fixed')

    def test_unknown_get_is_404(self):
        self.start()
        self.assertEqual(self.request('GET', '/other')[0], 404)

    def test_real_image_post_keeps_role_coordinates_and_confidence(self):
        self.start()
        image = io.BytesIO()
        Image.new('RGB', (32, 48), 'white').save(image, 'PNG')
        payload = {'image': 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()}
        status, result = self.request('POST', '/detect', json.dumps(payload))
        self.assertEqual(status, 200)
        self.assertEqual(result, {'boxes': [{'label': 'answer', 'bbox_2d': [.25, .4, 1., 1.], 'confidence': .9}]})

    def test_empty_predictions_are_successful(self):
        self.start()
        image = io.BytesIO()
        Image.new('RGB', (8, 8)).save(image, 'PNG')
        body = json.dumps({'image': 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()})
        with patch.object(FakeDetector, '__call__', return_value=[]):
            self.assertEqual(self.request('POST', '/detect', body), (200, {'boxes': []}))

    def test_malformed_payloads_fail_without_loading_an_image(self):
        self.start()
        for body in ['{', '[]', '{}', '{"image":12}', '{"image":"data:image/webp;base64,YQ=="}',
                     '{"image":"data:image/png;base64,###"}', '{"image":"data:image/png;base64,YQ=="}']:
            with self.subTest(body=body):
                self.assertEqual(self.request('POST', '/detect', body)[0], 400)

    def test_request_size_is_rejected_before_reading_body(self):
        self.start()
        self.assertEqual(self.request('POST', '/detect', '{}',
                                     {'Content-Length': str(server.MAX_BODY + 1)})[0], 400)

    def test_corrupted_hash_classes_and_actual_size_never_start_a_server(self):
        for changes in [{'sha256': 'bad'}, {'classes': ['answer', 'question']}, {'imgsz': 960}]:
            with self.subTest(changes=changes):
                original = dict(self.meta)
                self.meta.update(changes)
                self.save_meta()
                with patch.object(server, 'Detector', FakeDetector), self.assertRaises(ValueError):
                    server.make_server(self.folder, 0)
                self.meta = original

    def test_probe_metadata_validation_rejects_invalid_models(self):
        self.assertEqual(model.model_info(self.folder), self.meta)
        for changes in [{'conf': 0}, {'conf': 1.1}, {'conf': '0.1'}, {'imgsz': 320}, {'sha256': 'bad'}]:
            with self.subTest(changes=changes):
                original = dict(self.meta)
                self.meta.update(changes)
                self.save_meta()
                with self.assertRaises(ValueError):
                    model.model_info(self.folder)
                self.meta = original
        (self.folder / 'model.onnx').unlink()
        with self.assertRaises(ValueError):
            model.model_info(self.folder)

    def test_geometry_keeps_class_specific_nms_and_padding_clamp(self):
        a = {'role': 'question', 'x': 0, 'y': 0, 'w': .5, 'h': .5, 'conf': .9}
        self.assertEqual(nms([dict(a, conf=.1), dict(a, role='answer', conf=.8), a]),
                         [a, dict(a, role='answer', conf=.8)])
        self.assertEqual(restore_box([320, 320, 1000, 1000], 200, 100, 640),
                         {'x': 0., 'y': 0., 'w': 1., 'h': 1.})
