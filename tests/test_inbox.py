import base64
import io
import json
import os
import struct
import tempfile
import unittest
import zipfile
import zlib

from omrs import inbox
from omrs.ai_assist import parse_detect_output


def make_png(width, height, color=(255, 255, 255)):
    """用标准库生成最小 PNG，避免测试依赖 Pillow。"""
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def data_url(data, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


class ImageSizeTests(unittest.TestCase):
    def test_png_and_gif_and_jpeg_headers(self):
        self.assertEqual(inbox.image_size(make_png(12, 34)), ("image/png", 12, 34))
        gif = b"GIF89a" + struct.pack("<HH", 7, 9) + b"\x00" * 10
        self.assertEqual(inbox.image_size(gif), ("image/gif", 7, 9))
        # 手工拼一个只含 SOF0 段的 JPEG 头
        sof = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", 6209, 1080) + b"\x03" + b"\x00" * 9
        jpeg = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00" + sof + b"\xff\xd9"
        self.assertEqual(inbox.image_size(jpeg), ("image/jpeg", 1080, 6209))
        with self.assertRaises(ValueError):
            inbox.image_size(b"not an image")


class SliceAndMergeTests(unittest.TestCase):
    def test_slice_plan_keeps_normal_images_whole(self):
        self.assertEqual(inbox.slice_plan(1080, 2400), [(0.0, 1.0)])

    def test_slice_plan_covers_tall_image_with_overlap(self):
        plan = inbox.slice_plan(1080, 6209)
        self.assertGreater(len(plan), 1)
        self.assertEqual(plan[0][0], 0.0)
        self.assertEqual(plan[-1][1], 1.0)
        for (a0, a1), (b0, b1) in zip(plan, plan[1:]):
            self.assertLess(b0, a1)  # 相邻条带重叠
            self.assertLess(a0, b0)

    def test_merge_strip_boxes_maps_and_unions_split_box(self):
        strips = [
            {"y0": 0.0, "y1": 0.4, "boxes": [{"role": "question", "x": 0.05, "y": 0.25, "w": 0.9, "h": 0.3, "conf": 0.9}]},
            {"y0": 0.3, "y1": 0.7, "boxes": [{"role": "answer", "x": 0.05, "y": 0.5, "w": 0.9, "h": 0.5, "conf": 0.8}]},
            {"y0": 0.6, "y1": 1.0, "boxes": [{"role": "answer", "x": 0.05, "y": 0.0, "w": 0.9, "h": 0.6, "conf": 0.85}]},
        ]
        merged = inbox.merge_strip_boxes(strips)
        roles = sorted(b["role"] for b in merged)
        self.assertEqual(roles, ["answer", "question"])
        answer = next(b for b in merged if b["role"] == "answer")
        self.assertAlmostEqual(answer["y"], 0.5, places=3)
        self.assertAlmostEqual(answer["y"] + answer["h"], 0.84, places=3)
        self.assertAlmostEqual(answer["conf"], 0.8)


class DetectParsingTests(unittest.TestCase):
    def test_parses_qwen3_relative_1000(self):
        text = '```json\n[{"label":"question","card":1,"bbox_2d":[50,95,960,222],"confidence":0.94},' \
               '{"label":"答案","bbox_2d":[40,435,960,985]}]\n```'
        boxes = parse_detect_output(text)
        self.assertEqual([b["role"] for b in boxes], ["question", "answer"])
        self.assertAlmostEqual(boxes[0]["x"], 0.05)
        self.assertAlmostEqual(boxes[0]["h"], 0.127)
        self.assertAlmostEqual(boxes[0]["conf"], 0.94)
        self.assertEqual(boxes[1]["card"], 1)

    def test_parses_absolute_pixels_and_fractions(self):
        boxes = parse_detect_output('[{"label":"question","bbox_2d":[108,600,972,1400]}]', 1080, 6209)
        self.assertAlmostEqual(boxes[0]["x"], 0.1)
        self.assertAlmostEqual(boxes[0]["y"], 600 / 6209)
        boxes = parse_detect_output('[{"label":"question","bbox_2d":[0.1,0.2,0.9,0.4]}]')
        self.assertAlmostEqual(boxes[0]["w"], 0.8)
        self.assertEqual(parse_detect_output("没有找到"), [])


class InboxFlowTests(unittest.TestCase):
    def test_upload_dedup_update_ready_commit_and_dataset(self):
        with tempfile.TemporaryDirectory() as vault:
            png = make_png(20, 10)
            result = inbox.upload_images(vault, [("a.png", png), ("b.png", png), ("c.png", make_png(5, 5))], source="phone")
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(len(result["duplicates"]), 1)
            item = result["items"][0]
            self.assertEqual((item["width"], item["height"], item["status"], item["source"]), (20, 10, "pending", "phone"))
            self.assertEqual(item["layout"], "zuoyebang")
            self.assertTrue(os.path.exists(os.path.join(vault, "错题", ".omrs", "inbox", "raw", item["sha256"] + ".png")))

            mime, data = inbox.raw_file(vault, item["id"])
            self.assertEqual((mime, data), ("image/png", png))

            # 画框 → boxed；文本区 + 整图图片区
            regions = [
                {"card": 1, "role": "question", "x": 0, "y": 0, "w": 1, "h": 1, "convert": "text",
                 "text": "题目 $x^2$", "text_status": "done", "origin": "ai", "conf": 0.9,
                 "ai_box": {"x": 0, "y": 0, "w": 1, "h": 1}},
                {"card": 1, "role": "answer", "x": 0, "y": 0, "w": 1, "h": 1, "convert": "image"},
            ]
            updated = inbox.update_item(vault, item["id"], {"regions": regions, "layout": "zuoyebang"})
            self.assertEqual(updated["status"], "boxed")
            self.assertEqual(updated["layout"], "zuoyebang")
            self.assertEqual(len(updated["regions"]), 2)

            # 未决定转换方式时不能就绪
            with self.assertRaisesRegex(ValueError, "转文本"):
                inbox.update_item(vault, item["id"], {"regions": [dict(regions[0], convert="auto")], "status": "ready"})
            ready = inbox.update_item(vault, item["id"], {"status": "ready"})
            self.assertEqual(ready["status"], "ready")

            committed = inbox.commit_item(vault, item["id"], card=1,
                                          form={"subject": "数学", "category": "集合", "difficulty": 6, "tags": "集合相等, 判别式"})
            self.assertEqual(committed["uid"], "集合1")
            self.assertEqual(committed["answer_images"], [f"集合1-{committed['question_id'][-4:]}-a-1.png"])
            with open(os.path.join(vault, committed["file_path"]), encoding="utf-8") as file:
                raw_md = file.read()
            self.assertIn("题目 $x^2$", str(raw_md))
            self.assertIn("![[集合1-", str(raw_md))
            done = inbox.get_item(vault, item["id"])
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["link"]["uid"], "集合1")
            self.assertEqual(done["cards"]["1"]["created_uid"], "集合1")
            with self.assertRaises(ValueError):
                inbox.update_item(vault, item["id"], {"layout": "photo"})

            stats = inbox.dataset_stats(vault)
            self.assertEqual(stats["images"], 2)
            self.assertEqual(stats["done"], 1)
            self.assertEqual(stats["boxes"]["question"], 1)
            self.assertEqual(stats["ai"]["adopted"], 1)
            self.assertEqual(stats["layouts"].get("zuoyebang"), 2)

            blob = inbox.export_dataset(vault, fmt="yolo")
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                names = zf.namelist()
                self.assertIn("labels.jsonl", names)
                self.assertIn("classes.txt", names)
                self.assertIn("annotations.jsonl", names)
                labels = [json.loads(l) for l in zf.read("labels.jsonl").decode("utf-8").splitlines() if l]
                self.assertEqual(len(labels), 2)
                yolo = zf.read(f"labels/{item['sha256']}.txt").decode("utf-8").splitlines()
                self.assertEqual(yolo[0].split()[0], "0")

            events = [json.loads(l) for l in open(os.path.join(vault, "错题", ".omrs", "inbox", "annotations.jsonl"), encoding="utf-8")]
            self.assertEqual([e["event"] for e in events][:2], ["item.upload", "item.upload"])
            self.assertIn("item.commit", [e["event"] for e in events])

            other = result["items"][1]
            inbox.discard_item(vault, other["id"])
            self.assertEqual([i["id"] for i in inbox.list_items(vault)], [item["id"]])

    def test_region_image_requires_crop_when_partial_and_no_pillow(self):
        with tempfile.TemporaryDirectory() as vault:
            item = inbox.upload_images(vault, [("a.png", make_png(8, 8))])["items"][0]
            region = {"id": "r_x", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}
            supplied = data_url(make_png(4, 4))
            self.assertEqual(inbox.region_image(vault, item, region, supplied), supplied)
            self.assertTrue(inbox._crop_data_url(vault, "r_x"))  # 已缓存到 crops/


class FakeAI:
    """替代 ai_assist：detect 返回固定框，extract 返回可转文本，local_http 记录请求。"""
    def __init__(self, boxes=None, convertible=True):
        self.boxes = boxes if boxes is not None else [
            {"role": "question", "card": 1, "x": 0.05, "y": 0.1, "w": 0.9, "h": 0.2, "conf": 0.95},
            {"role": "answer", "card": 1, "x": 0.05, "y": 0.5, "w": 0.9, "h": 0.4, "conf": 0.9}]
        self.convertible = convertible
        self.local_calls = []

    def detect_regions(self, vault, image, layout="other"):
        return list(self.boxes)

    def detect_regions_local(self, url, image, layout="other", image_width=0, image_height=0):
        self.local_calls.append((url, layout, image_width, image_height))
        return list(self.boxes)

    def extract_region(self, vault, image, role="question", judge=True):
        return {"convertible": self.convertible, "reason": "纯文字", "text": f"{role} 文本"}


def write_config(vault, **kwargs):
    from omrs.common import save_config
    save_config(vault, kwargs)


class ProviderPolicyTests(unittest.TestCase):
    def test_template_boxes_default_and_reference_transfer(self):
        item = {"id": "b", "width": 1080, "height": 6000, "layout": "zuoyebang"}
        boxes = inbox.template_boxes(item)
        self.assertEqual([b["role"] for b in boxes], ["question", "answer"])
        self.assertAlmostEqual(boxes[0]["y"], 0.20 * 1080 / 6000, places=4)   # 题目框按像素锚定顶部
        self.assertAlmostEqual(boxes[1]["y"] + boxes[1]["h"], 1.0)             # 答案框一直到底
        ref = {"id": "a", "width": 1080, "height": 3000, "layout": "zuoyebang", "regions": [
            {"role": "question", "card": 1, "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "origin": "manual"},
            {"role": "answer", "card": 1, "x": 0.1, "y": 0.5, "w": 0.8, "h": 0.3, "origin": "manual"},
            {"role": "ignore", "card": 1, "x": 0, "y": 0, "w": 1, "h": 0.05, "origin": "manual"}]}
        boxes = inbox.template_boxes(item, ref)
        self.assertEqual(len(boxes), 2)
        self.assertAlmostEqual(boxes[0]["y"], 0.1 * 3000 / 6000)   # 300px → 归一化到新图高度
        self.assertAlmostEqual(boxes[0]["h"], 0.2 * 3000 / 6000)
        self.assertAlmostEqual(boxes[1]["y"], 0.5)
        self.assertAlmostEqual(boxes[1]["y"] + boxes[1]["h"], 1.0)
        self.assertEqual(inbox.template_boxes({"id": "c", "width": 10, "height": 10, "layout": "photo"}), [])

    def test_detect_provider_template_and_local_http(self):
        with tempfile.TemporaryDirectory() as vault:
            item = inbox.upload_images(vault, [("a.png", make_png(20, 100))])["items"][0]
            inbox.update_item(vault, item["id"], {"layout": "zuoyebang"})
            fake = FakeAI()
            res = inbox._run_detect(vault, fake, {"item_id": item["id"], "provider": "template"})
            self.assertEqual((res["provider"], res["boxes"]), ("template", 2))
            self.assertTrue(all(r["origin"] == "ai" for r in res["regions"]))
            # 未知提供方报错
            with self.assertRaisesRegex(ValueError, "提供方"):
                inbox._run_detect(vault, fake, {"item_id": item["id"], "provider": "nope"})
            # local_http：走配置里的地址，宽高随条带传给服务
            write_config(vault, inbox_detect_provider="local_http", inbox_local_detect_url="http://127.0.0.1:1/detect")
            res = inbox._run_detect(vault, fake, {"item_id": item["id"], "replace": True})
            self.assertEqual(res["provider"], "local_http")
            self.assertEqual(fake.local_calls[0][0], "http://127.0.0.1:1/detect")
            self.assertEqual(fake.local_calls[0][2], 20)
            events = [json.loads(l) for l in open(os.path.join(vault, "错题", ".omrs", "inbox", "annotations.jsonl"), encoding="utf-8")]
            detects = [e for e in events if e["event"] == "ai.detect"]
            self.assertEqual([e["provider"] for e in detects], ["template", "local_http"])

    def test_blind_every_hides_boxes_and_pairs_on_ready(self):
        with tempfile.TemporaryDirectory() as vault:
            write_config(vault, inbox_blind_every=2)
            items = inbox.upload_images(vault, [("a.png", make_png(10, 10)), ("b.png", make_png(12, 12))])["items"]
            fake = FakeAI()
            first = inbox._run_detect(vault, fake, {"item_id": items[0]["id"]})
            second = inbox._run_detect(vault, fake, {"item_id": items[1]["id"]})
            self.assertFalse(first["blind"]); self.assertEqual(first["boxes"], 2)
            self.assertTrue(second["blind"]); self.assertEqual(second["boxes"], 0); self.assertEqual(second["hidden"], 2)
            blind = inbox.get_item(vault, items[1]["id"])
            self.assertTrue(blind["blind"])
            self.assertEqual(blind["regions"], [])          # 不展示 AI 框
            self.assertNotIn("blind_boxes", blind)          # 隐藏框不进响应
            # 人工手画后标记就绪：事件里成对出现，评估集统计能算出 IoU
            regions = [{"card": 1, "role": "question", "x": 0.05, "y": 0.1, "w": 0.9, "h": 0.2, "convert": "image"},
                       {"card": 1, "role": "answer", "x": 0.05, "y": 0.55, "w": 0.9, "h": 0.35, "convert": "image"}]
            inbox.update_item(vault, items[1]["id"], {"regions": regions})
            inbox.update_item(vault, items[1]["id"], {"status": "ready"})
            events = [json.loads(l) for l in open(os.path.join(vault, "错题", ".omrs", "inbox", "annotations.jsonl"), encoding="utf-8")]
            ready = [e for e in events if e["event"] == "item.ready"][0]
            self.assertTrue(ready["blind"]); self.assertEqual(len(ready["ai_boxes"]), 2)
            self.assertEqual(ready["blind_eval"]["matched"], 2)
            stats = inbox.dataset_stats(vault)
            self.assertEqual((stats["blind"]["images"], stats["blind"]["evaluated"], stats["blind"]["matched"]), (1, 1, 2))
            self.assertGreater(stats["blind"]["mean_iou"], 0.5)
            # 显式 blind=False 覆盖配置
            self.assertFalse(inbox._run_detect(vault, fake, {"item_id": items[0]["id"], "blind": False, "replace": True})["blind"])
            blob = inbox.export_dataset(vault, fmt="omrs_jsonl", include_raw=False)
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                labels = [json.loads(l) for l in zf.read("labels.jsonl").decode("utf-8").splitlines() if l]
            self.assertEqual(sum(1 for l in labels if l.get("blind")), 1)

    def test_auto_ready_policy_extracts_and_marks_ready(self):
        with tempfile.TemporaryDirectory() as vault:
            write_config(vault, inbox_auto_ready_conf=0.8)
            item = inbox.upload_images(vault, [("a.png", make_png(10, 10))])["items"][0]
            # 全图框：无 Pillow 也能取到区域图（整图）
            fake = FakeAI(boxes=[{"role": "question", "card": 1, "x": 0, "y": 0, "w": 1, "h": 1, "conf": 0.9}])
            res = inbox._run_detect(vault, fake, {"item_id": item["id"]})
            self.assertTrue(res["auto"]["ready"])
            after = inbox.get_item(vault, item["id"])
            self.assertEqual(after["status"], "ready")
            self.assertEqual(after["regions"][0]["convert"], "text")
            self.assertEqual(after["regions"][0]["text"], "question 文本")
            # 置信度不足：不触发
            low = inbox.upload_images(vault, [("b.png", make_png(11, 11))])["items"][0]
            res = inbox._run_detect(vault, FakeAI(boxes=[{"role": "question", "card": 1, "x": 0, "y": 0, "w": 1, "h": 1, "conf": 0.5}]), {"item_id": low["id"]})
            self.assertFalse(res["auto"]["triggered"])
            self.assertEqual(inbox.get_item(vault, low["id"])["status"], "boxed")

    def test_auto_job_on_upload_and_rejected_counter(self):
        with tempfile.TemporaryDirectory() as vault:
            write_config(vault, inbox_auto_on_upload=True)
            result = inbox.upload_images(vault, [("a.png", make_png(10, 10))])
            self.assertIn("job", result)
            self.assertEqual(result["job"]["type"], "auto")
            # 拒绝 AI 框：增量计数进 meta，不必扫描 annotations
            item = result["items"][0]
            inbox.update_item(vault, item["id"], {"regions": [
                {"id": "r_ai", "card": 1, "role": "question", "x": 0, "y": 0, "w": 1, "h": 1, "origin": "ai", "conf": 0.9},
                {"id": "r_me", "card": 1, "role": "answer", "x": 0, "y": 0, "w": 1, "h": 0.5, "origin": "manual"}]})
            inbox.update_item(vault, item["id"], {"regions": [
                {"id": "r_me", "card": 1, "role": "answer", "x": 0, "y": 0, "w": 1, "h": 0.5, "origin": "manual"}]})
            db = inbox.connect(vault)
            self.assertEqual(inbox._meta_get(db, "rejected_ai_boxes"), "1")
            db.close()
            self.assertEqual(inbox.dataset_stats(vault)["ai"]["rejected"], 1)

    def test_cleanup_removes_expired_discarded_raw_and_crops(self):
        with tempfile.TemporaryDirectory() as vault:
            items = inbox.upload_images(vault, [("a.png", make_png(10, 10)), ("b.png", make_png(11, 11))])["items"]
            inbox.discard_item(vault, items[0]["id"])
            inbox.save_crop(vault, "r_1", data_url(make_png(2, 2)))
            raw_path = os.path.join(vault, "错题", ".omrs", "inbox", "raw", items[0]["sha256"] + ".png")
            # 未超期：不删
            self.assertEqual(inbox.cleanup(vault, discarded_days=7)["raw"], 0)
            self.assertTrue(os.path.exists(raw_path))
            res = inbox.cleanup(vault, discarded_days=0, crops=True)
            self.assertEqual((res["raw"], res["crops"]), (1, 1))
            self.assertFalse(os.path.exists(raw_path))
            with self.assertRaisesRegex(ValueError, "清理"):
                inbox.raw_file(vault, items[0]["id"])
            # 未丢弃的原图不受影响
            self.assertEqual(inbox.raw_file(vault, items[1]["id"])[0], "image/png")
            self.assertEqual(inbox.dataset_stats(vault)["storage"]["discarded"], 0)


if __name__ == "__main__":
    unittest.main()
