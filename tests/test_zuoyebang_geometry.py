"""题框解码、旋转映射、原图恢复和无匹配裁图的真实持久化回归。"""
import base64
import copy
import gzip
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from omrs.zuoyebang import jobs, source, store, service_config
from omrs.zuoyebang.commit import commit
from omrs.zuoyebang.direct import decode_response, rc4
from omrs.zuoyebang.geometry import regions, crop_bounds
from omrs.zuoyebang.normalize import normalize_questions
from omrs.zuoyebang.direct import UpstreamError
from tests.zuoyebang_fixtures import png, candidates

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/zuoyebang'))
from zyb_gateway.vendor.direct import decode_response as gateway_decode


class GeometryTests(unittest.TestCase):
    def test_coordinates_use_main_key_without_body_gzip_or_tid_key(self):
        key, tid = 'synthetic-main-key', 'synthetic-question-key'
        def encoded(raw, secret):
            return base64.b64encode(rc4(raw, secret)).decode()
        page = json.dumps({'question': '原题', 'answer': []}).encode()
        nested = encoded(encoded(gzip.compress(page), key).encode(), tid)
        body = {'errNo': 0, 'data': {'rotateAngle': 270, 'answers': {'gzip': 1, 'encryption': 1,
                'mainPageInfo': [nested], 'tids': [encoded(tid.encode(), key)],
                'locs': [encoded(b'295@4@295@207@1487@207@1487@4', key)], 'angles': [encoded(b'0', key)]}}}
        for decoder in (decode_response, gateway_decode):
            decoded = decoder(copy.deepcopy(body), key)['data']['answers']
            self.assertEqual(json.loads(decoded['mainPageInfo'][0])['question'], '原题')
            self.assertEqual(decoded['locs'], ['295@4@295@207@1487@207@1487@4'])
            self.assertEqual(decoded['angles'], ['0'])

    def test_plain_encoding_and_missing_coordinates_remain_compatible(self):
        encode = lambda value: base64.b64encode(value).decode()
        body = {'data': {'encode': 1, 'answers': {'gzip': 1, 'mainPageInfo': [encode(gzip.compress(b'{}'))],
                'locs': [encode(b'1@2@1@8@9@8@9@2')], 'angles': [encode(b'0')]}}}
        for decoder in (decode_response, gateway_decode):
            self.assertEqual(decoder(copy.deepcopy(body), 'unused')['data']['answers']['locs'][0], '1@2@1@8@9@8@9@2')
        boxes, _ = regions({'data': {'answers': {}}}, candidates(), 420, 240)
        self.assertEqual([row['candidate_indices'] for row in boxes], [[0, 1], [2]])
        self.assertTrue(all('bounds' not in row for row in boxes))

    def test_verified_270_degree_mapping_and_location_indices(self):
        value = {'data': {'rotateAngle': 270, 'answers': {'locs': [
            '295@4@295@207@1487@207@1487@4', '204@207@204@1013@1845@1013@1845@207'], 'angles': ['0', '0']}}}
        rows, angle = regions(value, candidates(), 1440, 1920)
        self.assertEqual(angle, 270)
        self.assertEqual(rows[0]['bounds'], {'x': 1233, 'y': 295, 'width': 203, 'height': 1192})
        self.assertEqual(rows[1]['bounds'], {'x': 427, 'y': 204, 'width': 806, 'height': 1641})
        self.assertEqual(rows[0]['candidate_indices'], [0, 1])
        self.assertEqual(rows[1]['candidate_indices'], [2])

    def test_four_rotations_return_same_original_rectangle(self):
        encoded = {0: '10@20@10@60@40@60@40@20', 90: '180@10@140@10@140@40@180@40',
                   180: '90@180@90@140@60@140@60@180', 270: '20@90@60@90@60@60@20@60'}
        for angle, loc in encoded.items():
            with self.subTest(angle=angle):
                result, _ = regions({'data': {'rotateAngle': angle, 'answers': {'locs': [loc]}}}, [], 100, 200)
                self.assertEqual(result[0]['bounds'], {'x': 10, 'y': 20, 'width': 30, 'height': 40})

    def test_bad_coordinates_do_not_fabricate_boxes_or_drop_candidates(self):
        for loc in ('1@2', 'nan@0@1@1@2@2@3@3', '-1@0@0@20@10@20@10@0', '0@0@0@0@0@0@0@0', 'encrypted'):
            rows, _ = regions({'answers': {'locs': [loc]}}, candidates(), 420, 240)
            self.assertNotIn('bounds', rows[0])
            self.assertEqual(rows[0]['candidate_indices'], [0, 1])
        rows, _ = regions({'rotateAngle': 12, 'answers': {'locs': ['1@1@1@20@20@20@20@1']}}, [], 420, 240)
        self.assertNotIn('bounds', rows[0])
        for bounds in ({'x': -1, 'y': 0, 'width': 10, 'height': 10}, {'x': 0, 'y': 0, 'width': float('nan'), 'height': 10},
                       {'x': True, 'y': 0, 'width': 10, 'height': 10}, {'x': 0, 'y': 0, 'width': 421, 'height': 1}):
            with self.assertRaises(ValueError): crop_bounds(bounds, 420, 240)

    def test_optional_angle_and_empty_result_shape(self):
        rows, _ = regions({'answers': {'locs': ['1@2@1@8@9@8@9@2'], 'angles': ['invalid']}}, [], 420, 240)
        self.assertEqual(rows[0]['bounds'], {'x': 1, 'y': 2, 'width': 8, 'height': 6})
        self.assertEqual(normalize_questions({'data': {'answers': {'mainPageInfo': []}}}, allow_empty=True), [])
        for response in ({'unrecognized': 'response'}, None, 'invalid'):
            with self.assertRaises(UpstreamError): normalize_questions(response, allow_empty=True)

    def test_source_restores_exact_bytes_and_unmatched_region_commits_once(self):
        with tempfile.TemporaryDirectory(prefix='omrs-zyb-geometry-') as vault:
            upstream = {'data': {'answers': {'mainPageInfo': [json.dumps(candidates())], 'locs': [
                '0@0@0@80@420@80@420@0', '0@80@0@160@420@160@420@80', '0@160@0@240@420@240@420@160']}}}
            with patch.object(jobs.GatewayClient, 'search', return_value=upstream):
                result = jobs.search(vault, {'image': png(), 'grade': 0})
            restored = jobs.get_record(vault, result['id'])
            self.assertNotIn('source', restored)
            self.assertEqual(source.read(vault, store.read(vault, result['id']))[0], png())
            self.assertEqual(restored['regions'][2]['candidate_indices'], [])
            job = jobs.start_job(vault, 'source', {'search_id': result['id'], 'region_index': 2})
            for _ in range(200):
                done = jobs.get_job(vault, job['id'])
                if done['status'] != 'running': break
                time.sleep(.01)
            self.assertEqual(done['status'], 'done', done)
            record = done['result']
            with Image.open(io.BytesIO(jobs.image(vault, record['id'], 'question'))) as image:
                self.assertEqual(image.size, (420, 80))
                expected = Image.open(io.BytesIO(png())).crop((0, 160, 420, 240))
                self.assertEqual(image.tobytes(), expected.tobytes())
            payload = {'form': {'subject': '物理', 'category': '原题裁图', 'difficulty': 5},
                       'sections': {'question': {'mode': 'image'}, 'answer': {'mode': 'none'}}}
            first = commit(vault, record['id'], payload)
            second = commit(vault, record['id'], payload)
            self.assertEqual(first['uid'], second['uid'])
            self.assertTrue(second['reused'])
            self.assertEqual(len(list((Path(vault) / '错题').rglob('原题裁图[0-9]*.md'))), 1)
            (store.location(vault, result['id']) / 'source.bin').write_bytes(b'changed')
            with self.assertRaises(store.ZybError): source.read(vault, store.read(vault, result['id']))

    def test_exif_preview_has_original_pixel_dimensions_without_reencoding_source(self):
        output = io.BytesIO()
        with Image.open(io.BytesIO(png())) as image:
            exif = Image.Exif(); exif[274] = 6
            image.save(output, 'JPEG', exif=exif)
        raw = output.getvalue()
        with tempfile.TemporaryDirectory(prefix='omrs-zyb-exif-') as vault:
            with patch.object(jobs.GatewayClient, 'search', return_value={'data': {'answers': {'mainPageInfo': []}}}):
                result = jobs.search(vault, {'image': raw, 'grade': 0})
            record = store.read(vault, result['id'])
            self.assertEqual(source.read(vault, record)[0], raw)
            display, mime = source.read(vault, record, preview=True)
            self.assertEqual(mime, 'image/png')
            with Image.open(io.BytesIO(display)) as image:
                self.assertEqual(image.size, (420, 240))
                self.assertNotIn(274, image.getexif())


if __name__ == '__main__':
    unittest.main()
