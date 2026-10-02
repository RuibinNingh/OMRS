import contextlib
import base64
import io
import json
import os
import sqlite3
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
            with self.assertRaisesRegex(ValueError, "未提取"):
                inbox.update_item(vault, item["id"], {"regions": [dict(regions[0], convert="auto")], "status": "ready"})
            ready = inbox.update_item(vault, item["id"], {"status": "ready"})
            self.assertEqual(ready["status"], "ready")

            committed = inbox.commit_item(vault, item["id"], card=1,
                                          form={"subject": "数学", "category": "集合", "difficulty": 6, "tags": "集合相等, 判别式"})
            self.assertEqual(committed["uid"], "集合1")
            self.assertEqual(committed["answer_images"], [f"集合1-{committed['question_id'].split('-')[-1]}-a-1.png"])
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

            with open(os.path.join(vault, "错题", ".omrs", "inbox", "annotations.jsonl"), encoding="utf-8") as stream:
                events = [json.loads(l) for l in stream]
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


class ExtractionReviewTests(unittest.TestCase):
    def setup_item(self, vault):
        item = inbox.upload_images(vault, [("extract.png", make_png(10, 10))])["items"][0]
        return inbox.update_item(vault, item["id"], {"regions": [
            {"id": "q", "role": "question", "x": 0, "y": 0, "w": 1, "h": 1, "convert": "auto"}]})

    def test_single_call_judges_even_after_manual_image_override(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            ai = mock.Mock()
            ai.extract_region.return_value = {"convertible": True, "text": "完整题面", "reason": "纯文字"}
            inbox._run_extract(vault, ai, {"region_id": "q"})
            ai.extract_region.assert_called_once()
            self.assertTrue(ai.extract_region.call_args.kwargs["judge"])
            item = inbox.get_item(vault, item["id"])
            self.assertEqual(item["status"], "boxed")
            item["regions"][0]["convert"] = "image"
            item["regions"][0]["judge_overridden"] = True
            inbox.update_item(vault, item["id"], {"regions": item["regions"]})
            ai.extract_region.return_value = {"convertible": False, "text": "部分文字不应采纳", "reason": "含图形"}
            result = inbox._run_extract(vault, ai, {"region_id": "q"})
            self.assertEqual(result["convert"], "image")
            self.assertEqual(result["text"], "完整题面")
            self.assertTrue(ai.extract_region.call_args.kwargs["judge"])
            self.assertFalse(inbox.get_item(vault, item["id"])["regions"][0]["judge_overridden"])
            self.assertEqual(inbox.update_item(vault, item["id"], {"status": "ready"})["status"], "ready")

    def test_failure_does_not_become_image_success_and_can_retry(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            ai = mock.Mock()
            ai.extract_region.side_effect = TimeoutError("模拟超时")
            with self.assertRaises(TimeoutError):
                inbox._run_extract(vault, ai, {"region_id": "q"})
            failed = inbox.get_item(vault, item["id"])["regions"][0]
            self.assertEqual(failed["text_status"], "error")
            self.assertIsNone(failed["judge"])
            self.assertEqual(failed["convert"], "auto")
            with self.assertRaisesRegex(ValueError, "提取失败"):
                inbox.update_item(vault, item["id"], {"status": "ready"})
            ai.extract_region.side_effect = None
            ai.extract_region.return_value = {"convertible": False, "text": "", "reason": "含图形"}
            inbox._run_extract(vault, ai, {"region_id": "q"})
            self.assertEqual(inbox.get_item(vault, item["id"])["regions"][0]["convert"], "image")

    def test_late_result_preserves_edited_box_and_other_regions(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            def extract(*args, **kwargs):
                fresh = inbox.get_item(vault, item["id"])
                fresh["regions"][0]["w"] = .5
                fresh["regions"].append({"id": "a", "role": "answer", "x": 0, "y": 0, "w": 1, "h": 1})
                inbox.update_item(vault, item["id"], {"regions": fresh["regions"]})
                return {"convertible": True, "text": "过期结果"}
            with self.assertRaisesRegex(ValueError, "区域已修改"):
                inbox._run_extract(vault, mock.Mock(extract_region=extract), {"region_id": "q"})
            fresh = inbox.get_item(vault, item["id"])
            self.assertEqual(len(fresh["regions"]), 2)
            self.assertEqual(fresh["regions"][0]["w"], .5)
            self.assertFalse(fresh["regions"][0]["text"])

    def test_reset_clears_progress_and_rejects_late_extract(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            before = inbox.get_item(vault, item["id"])
            inbox.update_item(vault, item["id"], {"cards": {"1": {"subject": "数学"}}, "layout": "photo"})
            inbox.save_crop(vault, "q", data_url(make_png(2, 2)))
            def extract(*_args, **_kwargs):
                fresh = inbox.reset_item(vault, item["id"])
                self.assertEqual((fresh["status"], fresh["regions"], fresh["cards"]), ("pending", [], {}))
                return {"convertible": True, "text": "过期题面"}
            with self.assertRaisesRegex(ValueError, "已重置"):
                inbox._run_extract(vault, mock.Mock(extract_region=extract), {"region_id": "q"})
            fresh = inbox.get_item(vault, item["id"])
            self.assertEqual(fresh["sha256"], before["sha256"])
            self.assertEqual(fresh["layout"], "zuoyebang")
            self.assertEqual(fresh["reset_epoch"], before["reset_epoch"] + 1)
            self.assertIsNone(inbox._crop_data_url(vault, "q"))
            with self.assertRaisesRegex(ValueError, "已重置"):
                inbox.update_item(vault, item["id"], {"reset_epoch": before["reset_epoch"], "regions": before["regions"]})
            with self.assertRaisesRegex(ValueError, "已重置"):
                inbox.update_item(vault, item["id"], {"regions": before["regions"]}, require_epoch=True)
            self.assertEqual(inbox.get_item(vault, item["id"])["regions"], [])

    def test_reset_rejects_late_detect_and_classify(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            def detect(*_args):
                inbox.reset_item(vault, item["id"])
                return ([{"role": "question", "card": 1, "x": 0, "y": 0, "w": 1, "h": 1, "conf": .9}], 1)
            with mock.patch.object(inbox, "_detect_with_provider", side_effect=detect):
                with self.assertRaisesRegex(ValueError, "已重置"):
                    inbox._run_detect(vault, mock.Mock(), {"item_id": item["id"]})
            self.assertEqual(inbox.get_item(vault, item["id"])["regions"], [])
            fresh = inbox.update_item(vault, item["id"], {"regions": [{"id": "q2", "role": "question",
                "x": 0, "y": 0, "w": 1, "h": 1, "convert": "image"}]})
            def classify(*_args, **_kwargs):
                inbox.reset_item(vault, item["id"])
                return {"subject": "过期科目"}
            with self.assertRaisesRegex(ValueError, "已重置"):
                inbox._run_classify(vault, mock.Mock(classify_question=classify),
                                    {"item_id": item["id"], "reset_epoch": fresh["reset_epoch"], "card": 1})
            self.assertEqual(inbox.get_item(vault, item["id"])["cards"], {})

    def test_late_detect_and_classify_do_not_overwrite_human_revision(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            def detect(*_args):
                current = inbox.get_item(vault, item["id"])
                inbox.update_item(vault, item["id"], {"layout": "photo",
                    "expected_revision": current["revision"], "reset_epoch": current["reset_epoch"]},
                    require_version=True)
                return ([{"role":"question","card":1,"x":0,"y":0,"w":1,"h":1,"conf":.9}],1)
            with mock.patch.object(inbox, "_detect_with_provider", side_effect=detect):
                with self.assertRaises(inbox.InboxConflict):
                    inbox._run_detect(vault, mock.Mock(), {"item_id": item["id"]})
            current = inbox.get_item(vault, item["id"])
            self.assertEqual(current["layout"], "photo")
            self.assertEqual(len(current["regions"]), 1)
            def classify(*_args, **_kwargs):
                fresh = inbox.get_item(vault, item["id"])
                inbox.update_item(vault, item["id"], {"cards": {"1": {"subject": "人工科目"}},
                    "expected_revision": fresh["revision"], "reset_epoch": fresh["reset_epoch"]},
                    require_version=True)
                return {"subject": "过期科目"}
            with self.assertRaises(inbox.InboxConflict):
                inbox._run_classify(vault, mock.Mock(classify_question=classify), {"item_id": item["id"]})
            self.assertEqual(inbox.get_item(vault, item["id"])["cards"]["1"]["subject"], "人工科目")

    def test_classify_preserves_manual_default_difficulty_and_old_page_is_inactive(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            edited = inbox.update_item(vault, item["id"], {"cards": {"1": {
                "subject": "", "category": "", "difficulty": 5, "tags": ["人工知识点"],
                "manual_fields": {"difficulty": True, "tags": True}, "page": "p.23",
            }}})
            self.assertNotIn("page", edited["cards"]["1"])
            ai = mock.Mock(classify_question=lambda *_args, **_kwargs: {
                "subject": "数学", "category": "函数", "difficulty": 9,
                "knowledge_tags": ["模型知识点"], "labels": ["模型标记"],
            })
            result = inbox._run_classify(vault, ai, {"item_id": item["id"], "card": 1})["form"]
            self.assertEqual(result["difficulty"], 5)
            self.assertEqual(result["tags"], ["人工知识点"])
            self.assertEqual(result["subject"], "数学")
            self.assertEqual(result["field_sources"]["subject"]["image_sha"], item["sha256"])
            self.assertNotIn("page", result)

    def test_auto_forwards_reset_epoch_to_detect(self):
        from unittest import mock
        with mock.patch.object(inbox, "_run_detect", return_value={}) as detect:
            inbox._run_auto("/unused", mock.Mock(), {"item_id": "image", "reset_epoch": 7})
            self.assertEqual(detect.call_args.args[2]["reset_epoch"], 7)

    def test_reset_refuses_partially_committed_image(self):
        with tempfile.TemporaryDirectory() as vault:
            item = self.setup_item(vault)
            inbox.update_item(vault, item["id"], {"cards": {"1": {"subject": "数学"}}})
            db = inbox.connect(vault)
            try:
                db.execute("UPDATE cards SET created_uid='已录入-1' WHERE item_id=?", (item["id"],))
                db.commit()
            finally:
                db.close()
            with self.assertRaisesRegex(ValueError, "已有题卡录入"):
                inbox.reset_item(vault, item["id"])
            self.assertEqual(len(inbox.get_item(vault, item["id"])["regions"]), 1)

    def test_judged_model_protocol_requires_explicit_boolean(self):
        from unittest import mock
        from omrs import ai_assist
        for response in ('不能提取', '{"convertible":"false","text":""}', '{"convertible":true,"text":""}'):
            with self.subTest(response=response), mock.patch.object(ai_assist, '_call_model', return_value=response):
                with self.assertRaises(ValueError):
                    ai_assist.extract_region('/unused', 'data:image/png;base64,AA==')
        with mock.patch.object(ai_assist, '_call_model', return_value='{"convertible":false,"reason":"含图形"}') as call:
            result = ai_assist.extract_region('/unused', 'data:image/png;base64,AA==')
            self.assertFalse(result['convertible'])
            call.assert_called_once()


class RevisionContractTests(unittest.TestCase):
    def test_discarded_item_cannot_be_committed_even_with_current_revision(self):
        with tempfile.TemporaryDirectory() as vault:
            item = inbox.upload_images(vault, [("a.png", make_png(10, 10))])["items"][0]
            prepared = inbox.update_item(vault, item["id"], {"regions": [
                {"id": "q", "role": "question", "x": 0, "y": 0, "w": 1, "h": 1, "convert": "image"}]})
            inbox.discard_item(vault, item["id"], prepared["revision"], prepared["reset_epoch"], True)
            current = inbox.get_item(vault, item["id"])
            with self.assertRaisesRegex(ValueError, "已经结束"):
                inbox.commit_item(vault, item["id"], form={"subject": "数学", "category": "函数"},
                                  expected_revision=current["revision"], reset_epoch=current["reset_epoch"],
                                  require_version=True)
            self.assertEqual(inbox.get_item(vault, item["id"])["status"], "discarded")

    def test_old_database_migrates_once_and_rejects_stale_writes(self):
        with tempfile.TemporaryDirectory() as vault:
            path = os.path.join(inbox.inbox_dir(vault), "inbox.db")
            with contextlib.closing(sqlite3.connect(path)) as legacy, legacy:
                legacy.executescript(inbox._SCHEMA)
            with inbox.connect(vault) as db:
                self.assertIn("revision", {row[1] for row in db.execute("PRAGMA table_info(items)")})
            item = inbox.upload_images(vault, [("a.png", make_png(10, 10))])["items"][0]
            version = {"expected_revision": item["revision"], "reset_epoch": item["reset_epoch"]}
            changed = inbox.update_item(vault, item["id"], {"layout": "photo", **version}, require_version=True)
            self.assertEqual(changed["revision"], item["revision"] + 1)
            self.assertEqual(changed["regions"], [])
            with self.assertRaises(inbox.InboxConflict) as stale:
                inbox.update_item(vault, item["id"], {"layout": "zuoyebang", **version}, require_version=True)
            self.assertEqual(stale.exception.current_revision, changed["revision"])
            self.assertEqual(inbox.get_item(vault, item["id"])["layout"], "photo")
            with self.assertRaises(inbox.InboxConflict):
                inbox.update_item(vault, item["id"], {"layout": "zuoyebang"}, require_version=True)
            reset = inbox.reset_item(vault, item["id"], changed["revision"], changed["reset_epoch"], True)
            self.assertEqual((reset["revision"], reset["reset_epoch"]),
                             (changed["revision"] + 1, changed["reset_epoch"] + 1))
            with self.assertRaises(inbox.InboxConflict):
                inbox.discard_item(vault, item["id"], reset["revision"], changed["reset_epoch"], True)
            self.assertEqual(inbox.get_item(vault, item["id"])["status"], "pending")

    def test_http_conflict_returns_409_and_current_revision_without_mutation(self):
        import http.client
        import threading
        from omrs.cli import OMRSTCPServer
        from omrs.server import OMRSHandler
        with tempfile.TemporaryDirectory() as vault:
            item = inbox.upload_images(vault, [("a.png", make_png(10, 10))])["items"][0]
            class Handler(OMRSHandler):
                vault_path = vault
                def log_message(self, *_args):
                    pass
            server = OMRSTCPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            def post(path, data):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
                conn.request("POST", path, json.dumps(data), {"Content-Type": "application/json"})
                response = conn.getresponse()
                result = response.status, json.loads(response.read())
                conn.close()
                return result
            version = {"id": item["id"], "expected_revision": item["revision"],
                       "reset_epoch": item["reset_epoch"]}
            status, body = post("/api/inbox/item/update", {**version, "layout": "photo"})
            self.assertEqual(status, 200)
            self.assertEqual(body["item"]["revision"], item["revision"] + 1)
            status, body = post("/api/inbox/item/update", {**version, "regions": []})
            self.assertEqual(status, 409)
            self.assertEqual(body["current_revision"], item["revision"] + 1)
            status, _ = post("/api/inbox/item/reset", {"id": item["id"]})
            self.assertEqual(status, 409)
            self.assertEqual(inbox.get_item(vault, item["id"])["layout"], "photo")


class ProviderPolicyTests(unittest.TestCase):
    def test_removed_template_provider_and_local_http(self):
        with tempfile.TemporaryDirectory() as vault:
            item = inbox.upload_images(vault, [("a.png", make_png(20, 100))])["items"][0]
            inbox.update_item(vault, item["id"], {"layout": "zuoyebang"})
            fake = FakeAI()
            with self.assertRaisesRegex(ValueError, "提供方"):
                inbox._run_detect(vault, fake, {"item_id": item["id"], "provider": "template"})
            with self.assertRaisesRegex(ValueError, "提供方"):
                write_config(vault, inbox_detect_provider="template")
            self.assertEqual(inbox.detect_provider(vault), "vlm")
            # local_http：走配置里的地址，宽高随条带传给服务
            write_config(vault, inbox_detect_provider="local_http", inbox_local_detect_url="http://127.0.0.1:1/detect")
            res = inbox._run_detect(vault, fake, {"item_id": item["id"], "replace": True})
            self.assertEqual(res["provider"], "local_http")
            self.assertEqual(fake.local_calls[0][0], "http://127.0.0.1:1/detect")
            self.assertEqual(fake.local_calls[0][2], 20)
            with open(os.path.join(vault, "错题", ".omrs", "inbox", "annotations.jsonl"), encoding="utf-8") as stream:
                events = [json.loads(l) for l in stream]
            detects = [e for e in events if e["event"] == "ai.detect"]
            self.assertEqual([e["provider"] for e in detects], ["local_http"])

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
            with open(os.path.join(vault, "错题", ".omrs", "inbox", "annotations.jsonl"), encoding="utf-8") as stream:
                events = [json.loads(l) for l in stream]
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

    def test_auto_policy_extracts_and_waits_for_review(self):
        with tempfile.TemporaryDirectory() as vault:
            write_config(vault, inbox_auto_ready_conf=0.8)
            item = inbox.upload_images(vault, [("a.png", make_png(10, 10))])["items"][0]
            # 全图框：无 Pillow 也能取到区域图（整图）
            fake = FakeAI(boxes=[{"role": "question", "card": 1, "x": 0, "y": 0, "w": 1, "h": 1, "conf": 0.9}])
            res = inbox._run_detect(vault, fake, {"item_id": item["id"]})
            self.assertFalse(res["auto"]["ready"])
            after = inbox.get_item(vault, item["id"])
            self.assertEqual(after["status"], "boxed")
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
