"""框选训练的数据隔离与坐标边界，不需要 torch/onnxruntime。"""
import unittest
from tools.boxdetect.common import clip_box, group_samples, split_groups


class HistoricalBaselineTests(unittest.TestCase):
    def test_offline_template_baseline_keeps_previous_geometry(self):
        from tools.boxdetect.evaluate import template_boxes
        item = {"width": 1080, "height": 6000, "layout": "zuoyebang"}
        boxes = template_boxes(item)
        self.assertEqual([box["role"] for box in boxes], ["question", "answer"])
        self.assertAlmostEqual(boxes[0]["y"], 0.20 * 1080 / 6000)
        self.assertAlmostEqual(boxes[1]["y"] + boxes[1]["h"], 1)
        reference = {"height": 3000, "regions": [
            {"role": "question", "card": 1, "x": .1, "y": .1, "w": .8, "h": .2},
            {"role": "answer", "card": 1, "x": .1, "y": .5, "w": .8, "h": .3},
        ]}
        transferred = template_boxes(item, reference)
        self.assertAlmostEqual(transferred[0]["y"], .05)
        self.assertAlmostEqual(transferred[1]["y"] + transferred[1]["h"], 1)


class DatasetTests(unittest.TestCase):
    def test_clip_spanning_boundary(self):
        box = dict(role='answer', x=.1, y=.4, w=.8, h=.5)
        clipped = clip_box(box, .5, 1)
        self.assertEqual(clipped['y'], 0)
        self.assertAlmostEqual(clipped['h'], .8)
        self.assertEqual(box['h'], .5)

    def test_drop_small_residual_and_outside(self):
        for y, h in [(.499, .001), (.495, .3), (.6, .2)]:
            self.assertIsNone(clip_box(dict(x=0, y=y, w=1, h=h), 0, .5))

    def test_group_transitive_and_exact_hash(self):
        rows = [dict(id=str(i), sha256=sha, dhash=f'{dh:016x}')
                for i, (sha, dh) in enumerate([('a', 0), ('b', 1), ('c', 3), ('a', 255)])]
        self.assertEqual(group_samples(rows, 1), [['0', '1', '2', '3']])
        self.assertEqual(group_samples(rows[::-1], 1), group_samples(rows, 1))

    def test_split_reproducible_and_group_disjoint(self):
        groups = [[str(i), str(i) + 'b'] for i in range(30)]
        result = split_groups(groups)
        self.assertEqual(result, split_groups(groups[::-1]))
        for group in groups:
            self.assertEqual(sum(bool(set(group) & set(ids)) for ids in result.values()), 1)

    def test_frozen_and_near_new_images_quarantined(self):
        result = split_groups([['old-test', 'new-near'], ['new1'], ['new2'], ['old-train']], frozen=['old-test'])
        self.assertEqual(result['test'], ['old-test'])
        self.assertEqual(result['quarantine'], ['new-near'])
        self.assertEqual(set(result['train'] + result['val']), {'new1', 'new2', 'old-train'})

    def test_missing_frozen_image_rejected(self):
        with self.assertRaises(ValueError):
            split_groups([['new']], frozen=['missing'])


class SourceTests(unittest.TestCase):
    def test_readonly_source_filtering(self):
        import hashlib
        import io
        import json
        from pathlib import Path
        import sqlite3
        import tempfile
        from PIL import Image
        from tools.boxdetect.build_dataset import inspect_sources
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / '错题' / '.omrs' / 'annotate'
            (root / 'images').mkdir(parents=True)
            db = sqlite3.connect(root / 'annotate.db')
            db.execute('CREATE TABLE images(id, sha256, mime, width, height, boxes, status, updated_at)')
            buf = io.BytesIO()
            Image.new('RGB', (32, 64), 'white').save(buf, format='PNG')
            data = buf.getvalue()
            sha = hashlib.sha256(data).hexdigest()
            (root / 'images' / (sha + '.png')).write_bytes(data)
            boxes = [dict(role=r, x=0, y=i*.5, w=1, h=.5) for i, r in enumerate(['question', 'answer'])]
            for name, status, labels, width, digest in [
                ('valid', 'done', boxes, 32, sha), ('todo', 'todo', boxes, 32, sha),
                ('missing-class', 'done', boxes[:1], 32, sha),
                ('dimensions', 'done', boxes, 31, sha), ('missing-file', 'done', boxes, 32, 'missing')]:
                db.execute('INSERT INTO images VALUES (?,?,?,?,?,?,?,?)', (name, digest, 'image/png', width, 64, json.dumps(labels), status, '2026'))
            db.commit(); db.close()
            before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob('*') if p.is_file()}
            samples, excluded = inspect_sources(temp)
            self.assertEqual([s['id'] for s in samples], ['annotate:valid'])
            self.assertEqual(len(excluded), 3)
            self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob('*') if p.is_file()})
