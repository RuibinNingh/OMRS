"""AI 草稿区存储层（omrs/drafts.py）与只读接口（/api/drafts/*）测试。"""
import base64
import http.client
import json
import os
from pathlib import Path
import socketserver
import struct
import tempfile
import threading
import unittest
import zlib

from omrs import drafts
from omrs.server import OMRSHandler


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


def basic_blocks(image_sha=None):
    blocks = [{"section": "题目", "kind": "text", "text": "1+1=?"}]
    if image_sha:
        blocks.append({"section": "题目", "kind": "image", "image_sha": image_sha, "note": "图在中间"})
    blocks.append({"section": "答案", "kind": "text", "text": "2"})
    return blocks


class SchemaTests(unittest.TestCase):
    def test_connect_is_idempotent(self):
        with tempfile.TemporaryDirectory() as vault:
            db1 = drafts.connect(vault)
            db1.close()
            db2 = drafts.connect(vault)  # 第二次 connect 不应报错（CREATE TABLE IF NOT EXISTS）
            tables = {row[0] for row in db2.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            db2.close()
            self.assertTrue({"images", "conv_images", "drafts", "blocks"} <= tables)
            self.assertTrue(os.path.exists(os.path.join(vault, "错题", ".omrs", "drafts", "drafts.db")))


class ImageValidationTests(unittest.TestCase):
    def test_rejects_bad_mime_bad_base64_and_oversize(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "格式不支持"):
                drafts.add_image(vault, "data:image/webp;base64,AAAA", "conv1", "run1")
            with self.assertRaisesRegex(ValueError, "base64"):
                drafts.add_image(vault, "data:image/png;base64,not-base64!!", "conv1", "run1")
            with self.assertRaisesRegex(ValueError, "8MB"):
                oversized = base64.b64encode(b"\x00" * (8 * 1024 * 1024 + 1)).decode("ascii")
                drafts.add_image(vault, f"data:image/png;base64,{oversized}", "conv1", "run1")
            with self.assertRaisesRegex(ValueError, "缺少图片数据"):
                drafts.add_image(vault, "", "conv1", "run1")
            with self.assertRaisesRegex(ValueError, "缺少 conversation_id"):
                drafts.add_image(vault, data_url(make_png(4, 4)), "", "run1")

    def test_bad_pixel_data_reports_size_error(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "无法识别图片尺寸"):
                drafts.add_image(vault, data_url(b"not-a-real-image"), "conv1", "run1")

    def test_jpeg_missing_end_marker_is_completed_for_new_and_old_images(self):
        sof = (b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", 12, 10)
               + b"\x03" + b"\x00" * 9)
        incomplete = b"\xff\xd8\xff\xe0\x00\x04\x00\x00" + sof
        complete = incomplete + b"\xff\xd9"
        with tempfile.TemporaryDirectory() as vault:
            added = drafts.add_image(vault, data_url(incomplete, "image/jpeg"), "conv1", "run1")
            self.assertEqual((added["mime"], added["width"], added["height"]), ("image/jpeg", 10, 12))
            self.assertEqual(Path(drafts.image_path(vault, added["sha256"])).read_bytes(), complete)
            self.assertEqual(base64.b64decode(drafts.image_data_url(vault, added["sha256"]).split(",", 1)[1]), complete)
            same = drafts.add_image(vault, data_url(complete, "image/jpeg"), "conv1", "run2")
            self.assertEqual(same["ref"], added["ref"])
            # 旧版本已保存的缺尾图片在发给模型时也要补全，原件保持不变。
            with open(drafts.image_path(vault, added["sha256"]), "wb") as file:
                file.write(incomplete)
            self.assertEqual(base64.b64decode(drafts.image_data_url(vault, added["sha256"]).split(",", 1)[1]), complete)
            self.assertEqual(Path(drafts.image_path(vault, added["sha256"])).read_bytes(), incomplete)


class DedupeAndNumberingTests(unittest.TestCase):
    def test_same_image_reuses_number_within_conversation_new_conversation_restarts(self):
        with tempfile.TemporaryDirectory() as vault:
            png = make_png(10, 10)
            first = drafts.add_image(vault, data_url(png), "conv1", "run1")
            self.assertEqual((first["n"], first["ref"]), (1, "IMG-1"))
            again = drafts.add_image(vault, data_url(png), "conv1", "run2")
            self.assertEqual(again["n"], 1)  # 同对话贴同一张图沿用旧编号
            self.assertEqual(again["sha256"], first["sha256"])

            other_png = make_png(20, 30)
            second = drafts.add_image(vault, data_url(other_png), "conv1", "run1")
            self.assertEqual(second["n"], 2)  # 新图连续编号

            other_conv = drafts.add_image(vault, data_url(png), "conv2", "run1")
            self.assertEqual(other_conv["n"], 1)  # 不同对话独立编号

            self.assertEqual(first["mime"], "image/png")
            self.assertEqual((first["width"], first["height"]), (10, 10))
            self.assertEqual(first["bytes"], len(png))

    def test_resolve_image_returns_row_and_unknown_ref_raises(self):
        with tempfile.TemporaryDirectory() as vault:
            png = make_png(5, 5)
            added = drafts.add_image(vault, data_url(png), "conv1", "run1")
            resolved = drafts.resolve_image(vault, "conv1", "IMG-1")
            self.assertEqual(resolved["sha256"], added["sha256"])
            with self.assertRaisesRegex(ValueError, r"本对话里没有 IMG-3"):
                drafts.resolve_image(vault, "conv1", "IMG-3")
            with self.assertRaisesRegex(ValueError, r"本对话里没有 IMG-1"):
                drafts.resolve_image(vault, "conv2", "IMG-1")  # 图片属于对话，其他对话看不到
            with self.assertRaisesRegex(ValueError, r"本对话里没有"):
                drafts.resolve_image(vault, "conv1", "not-a-ref")

    def test_image_data_url_and_path_roundtrip(self):
        with tempfile.TemporaryDirectory() as vault:
            png = make_png(6, 6)
            added = drafts.add_image(vault, data_url(png), "conv1", "run1")
            url = drafts.image_data_url(vault, added["sha256"])
            self.assertTrue(url.startswith("data:image/png;base64,"))
            decoded = base64.b64decode(url.split(",", 1)[1])
            self.assertEqual(decoded, png)
            path = drafts.image_path(vault, added["sha256"])
            self.assertTrue(os.path.exists(path))
            with self.assertRaisesRegex(ValueError, "图片不存在"):
                drafts.image_path(vault, "0" * 64)
            with self.assertRaisesRegex(ValueError, "图片不存在"):
                drafts.image_data_url(vault, "0" * 64)


class TranscriptCacheTests(unittest.TestCase):
    def test_cache_hit_and_miss_by_model(self):
        with tempfile.TemporaryDirectory() as vault:
            added = drafts.add_image(vault, data_url(make_png(4, 4)), "conv1", "run1")
            sha = added["sha256"]
            self.assertIsNone(drafts.get_transcript(vault, sha, "model-a"))
            drafts.set_transcript(vault, sha, "model-a", {"summary": "s", "blocks": []})
            self.assertEqual(drafts.get_transcript(vault, sha, "model-a"), {"summary": "s", "blocks": []})
            self.assertIsNone(drafts.get_transcript(vault, sha, "model-b"))  # 换模型缓存不命中
            drafts.set_transcript(vault, sha, "model-b", {"summary": "s2", "blocks": []})
            self.assertIsNone(drafts.get_transcript(vault, sha, "model-a"))  # 单槽缓存，新模型覆盖旧的
            self.assertEqual(drafts.get_transcript(vault, sha, "model-b")["summary"], "s2")

    def test_set_transcript_unknown_image_raises(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "图片不存在"):
                drafts.set_transcript(vault, "0" * 64, "model-a", {"summary": ""})


class CreateDraftTests(unittest.TestCase):
    def test_status_derivation_image_block_cropping_text_only_review(self):
        with tempfile.TemporaryDirectory() as vault:
            added = drafts.add_image(vault, data_url(make_png(8, 8)), "conv1", "run1")
            with_image = drafts.create_draft(vault, {
                "subject": "数学", "category": "函数", "knowledge_points": ["二次函数"],
                "blocks": basic_blocks(added["sha256"]),
                "cause": "粗心", "cause_statement": "我看错符号了",
            }, origin={"conversation_id": "conv1", "run_id": "run1", "tool_call_id": "tc1"})
            self.assertEqual(with_image["status"], "cropping")
            self.assertEqual(len(with_image["blocks"]), 3)
            self.assertEqual(with_image["blocks"][1]["note"], "图在中间")
            self.assertEqual(with_image["difficulty"], 5)
            self.assertTrue(with_image["id"].startswith("DR-"))

            text_only = drafts.create_draft(vault, {
                "subject": "数学", "category": "函数", "blocks": basic_blocks(),
            }, origin={"conversation_id": "conv1"})
            self.assertEqual(text_only["status"], "review")

    def test_requires_subject_category_and_at_least_one_question_block(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "科目不能为空"):
                drafts.create_draft(vault, {"category": "c", "blocks": basic_blocks()}, {})
            with self.assertRaisesRegex(ValueError, "分类不能为空"):
                drafts.create_draft(vault, {"subject": "s", "blocks": basic_blocks()}, {})
            with self.assertRaisesRegex(ValueError, "至少要有一个块"):
                drafts.create_draft(vault, {"subject": "s", "category": "c", "blocks": []}, {})
            with self.assertRaisesRegex(ValueError, "至少要有一个题目块"):
                drafts.create_draft(vault, {"subject": "s", "category": "c",
                                            "blocks": [{"section": "答案", "kind": "text", "text": "只有答案"}]}, {})

    def test_knowledge_points_limit(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "最多 8 个"):
                drafts.create_draft(vault, {
                    "subject": "s", "category": "c", "blocks": basic_blocks(),
                    "knowledge_points": [f"kp{i}" for i in range(9)],
                }, {})

    def test_cause_requires_statement(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "错因只能用用户说过的话"):
                drafts.create_draft(vault, {
                    "subject": "s", "category": "c", "blocks": basic_blocks(), "cause": "粗心",
                }, {})
            # 没有 cause 时不要求 cause_statement
            ok = drafts.create_draft(vault, {"subject": "s", "category": "c", "blocks": basic_blocks()}, {})
            self.assertEqual(ok["cause"], "")

    def test_unknown_section_kind_and_missing_text_or_image_ref(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "section"):
                drafts.create_draft(vault, {"subject": "s", "category": "c",
                                            "blocks": [{"section": "别的", "kind": "text", "text": "x"}]}, {})
            with self.assertRaisesRegex(ValueError, "kind"):
                drafts.create_draft(vault, {"subject": "s", "category": "c",
                                            "blocks": [{"section": "题目", "kind": "video"}]}, {})
            with self.assertRaisesRegex(ValueError, "没有文本"):
                drafts.create_draft(vault, {"subject": "s", "category": "c",
                                            "blocks": [{"section": "题目", "kind": "text", "text": "  "}]}, {})
            with self.assertRaisesRegex(ValueError, "引用的图片不存在"):
                drafts.create_draft(vault, {"subject": "s", "category": "c",
                                            "blocks": [{"section": "题目", "kind": "image",
                                                        "image_sha": "0" * 64}]}, {})

    def test_invalid_draft_does_not_create_row(self):
        with tempfile.TemporaryDirectory() as vault:
            try:
                drafts.create_draft(vault, {
                    "subject": "s", "category": "c", "blocks": basic_blocks(), "cause": "粗心",
                }, {})
            except ValueError:
                pass
            db = drafts.connect(vault)
            count = db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            db.close()
            self.assertEqual(count, 0)

    def test_get_draft_unknown_id_raises(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaisesRegex(ValueError, "没有这份草稿"):
                drafts.get_draft(vault, "DR-20260101-000000")


class ListAndCountsTests(unittest.TestCase):
    def _seed(self, vault):
        d1 = drafts.create_draft(vault, {"subject": "s", "category": "c", "blocks": basic_blocks()},
                                  {"conversation_id": "conv1"})
        d2 = drafts.create_draft(vault, {"subject": "s", "category": "c", "blocks": basic_blocks()},
                                  {"conversation_id": "conv2"})
        added = drafts.add_image(vault, data_url(make_png(4, 4)), "conv1", "run1")
        d3 = drafts.create_draft(vault, {"subject": "s", "category": "c",
                                         "blocks": basic_blocks(added["sha256"])},
                                  {"conversation_id": "conv1"})
        return d1, d2, d3

    def test_list_filters_by_status_and_conversation_default_excludes_discarded_only(self):
        with tempfile.TemporaryDirectory() as vault:
            d1, d2, d3 = self._seed(vault)
            db = drafts.connect(vault)
            db.execute("UPDATE drafts SET status='done' WHERE id=?", (d1["id"],))
            db.execute("UPDATE drafts SET status='discarded' WHERE id=?", (d2["id"],))
            db.commit()
            db.close()

            default_list = drafts.list_drafts(vault)
            ids = {d["id"] for d in default_list}
            self.assertIn(d1["id"], ids)  # done 默认仍列出
            self.assertNotIn(d2["id"], ids)  # discarded 默认排除
            self.assertIn(d3["id"], ids)

            by_conv = drafts.list_drafts(vault, conversation_id="conv1")
            self.assertEqual({d["id"] for d in by_conv}, {d1["id"], d3["id"]})

            by_status = drafts.list_drafts(vault, status="cropping")
            self.assertEqual({d["id"] for d in by_status}, {d3["id"]})  # d3 带图片块 -> cropping

            self.assertEqual(len(drafts.list_drafts(vault, limit=1)), 1)

    def test_counts(self):
        with tempfile.TemporaryDirectory() as vault:
            d1, d2, d3 = self._seed(vault)
            db = drafts.connect(vault)
            db.execute("UPDATE drafts SET status='done' WHERE id=?", (d1["id"],))
            db.execute("UPDATE drafts SET status='discarded' WHERE id=?", (d2["id"],))
            db.commit()
            db.close()
            result = drafts.counts(vault)
            self.assertEqual(result, {"cropping": 1, "review": 0, "done": 1, "discarded": 1})


class EventLogTests(unittest.TestCase):
    def test_events_jsonl_has_add_create_and_transcribe(self):
        with tempfile.TemporaryDirectory() as vault:
            added = drafts.add_image(vault, data_url(make_png(4, 4)), "conv1", "run1")
            drafts.set_transcript(vault, added["sha256"], "model-a", {"summary": "s"})
            drafts.create_draft(vault, {"subject": "s", "category": "c", "blocks": basic_blocks()},
                                {"conversation_id": "conv1", "run_id": "run1"})
            path = os.path.join(vault, "错题", ".omrs", "drafts", "events.jsonl")
            with open(path, encoding="utf-8") as file:
                events = [json.loads(line)["event"] for line in file if line.strip()]
            self.assertEqual(events, ["image.add", "image.transcribe", "draft.create"])


class QuietHandler(OMRSHandler):
    def log_message(self, *_args):
        pass


class HttpRoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        os.makedirs(os.path.join(self.temp.name, "错题"), exist_ok=True)
        QuietHandler.vault_path = self.temp.name
        self.server = socketserver.TCPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.thread.join, 2)
        self.vault = self.temp.name

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        conn.request("GET", path)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_list_item_counts_and_image_routes(self):
        added = drafts.add_image(self.vault, data_url(make_png(9, 9)), "conv1", "run1")
        draft = drafts.create_draft(self.vault, {
            "subject": "数学", "category": "函数", "blocks": basic_blocks(added["sha256"]),
        }, {"conversation_id": "conv1"})

        status, _, body = self.get("/api/drafts/list?status=&conversation=conv1")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual([d["id"] for d in payload["drafts"]], [draft["id"]])

        status, _, body = self.get(f"/api/drafts/item?id={draft['id']}")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["draft"]["id"], draft["id"])
        self.assertEqual(len(payload["draft"]["blocks"]), 3)

        status, _, body = self.get("/api/drafts/item?id=DR-00000000-000000")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["status"], "error")

        status, headers, body = self.get(f"/api/drafts/image?sha={added['sha256']}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(headers["Cache-Control"], "private, max-age=86400")
        self.assertEqual(body, make_png(9, 9))

        status, _, body = self.get("/api/drafts/image?sha=not-hex")
        self.assertEqual(status, 400)
        self.assertIn("不合法", json.loads(body)["msg"])

        status, _, body = self.get("/api/drafts/counts")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["counts"]["cropping"], 1)


if __name__ == "__main__":
    unittest.main()
