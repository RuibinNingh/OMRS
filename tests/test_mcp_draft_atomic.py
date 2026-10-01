"""MCP 草稿图片与 SQLite 事务边界测试。"""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
import http.client
import os
from pathlib import Path
import sqlite3
import socketserver
import struct
import tempfile
import threading
import unittest
from unittest import mock
import zlib

from omrs import drafts
from omrs import locking
from omrs.server import OMRSHandler


class FaultConnection:
    """只在测试事务中注入 SQLite 写入失败。"""

    def __init__(self, db, sql=None, commit=False):
        self.db = db
        self.sql = sql
        self.commit_fault = commit

    def __getattr__(self, name):
        return getattr(self.db, name)

    def execute(self, sql, *args, **kwargs):
        if self.sql and self.sql in sql:
            raise sqlite3.OperationalError("测试写入中断")
        return self.db.execute(sql, *args, **kwargs)

    def commit(self):
        if self.commit_fault:
            raise sqlite3.OperationalError("测试提交中断")
        return self.db.commit()


def png(width=2, height=2):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class MCPAtomicDraftTests(unittest.TestCase):
    def _origin(self, request="req-1", content=None):
        return {"conversation_id": "mcp:key:" + request, "source_key_id": "key",
                "source_request_id": request, "content_hash": content or hashlib.sha256(request.encode()).hexdigest(),
                "stable_hash": "stable-" + request}

    def _data(self, sha):
        return {"subject": "数学", "category": "外部", "blocks": [
            {"section": "题目", "kind": "image", "image_sha": sha},
            {"section": "答案", "kind": "text", "text": "答案"}]}

    def _assert_no_relations(self, vault):
        db = drafts.connect(vault)
        try:
            for table in ("drafts", "blocks", "draft_images", "images", "conv_images", "mcp_requests"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
        finally:
            db.close()

    def test_first_connections_serialize_new_and_old_schema_migration(self):
        """冻结首连接的旧列快照；旧代码第二连接先迁移，首连接随后发生列冲突。"""
        for old_schema in (False, True):
            with self.subTest(old_schema=old_schema), tempfile.TemporaryDirectory() as vault:
                if old_schema:
                    db = sqlite3.connect(Path(drafts.drafts_dir(vault)) / "drafts.db")
                    db.execute("CREATE TABLE drafts(id TEXT PRIMARY KEY,status TEXT,conversation_id TEXT,run_id TEXT,tool_call_id TEXT)")
                    db.execute("INSERT INTO drafts VALUES('old','review','old-conv',NULL,NULL)")
                    db.commit()
                    db.close()
                paused, release, checkpoint = threading.Event(), threading.Event(), threading.Event()
                role = threading.local()
                real_connect, real_lock = sqlite3.connect, locking.write_lock

                class PausedConnection(sqlite3.Connection):
                    def execute(self, sql, *args, **kwargs):
                        cursor = super().execute(sql, *args, **kwargs)
                        if sql == "PRAGMA table_info(drafts)" and getattr(role, "name", "") == "first":
                            snapshot = cursor.fetchall()
                            paused.set()
                            if not release.wait(5):
                                raise AssertionError("首连接未在限时内释放")
                            return snapshot
                        return cursor

                def observed_lock(*args, **kwargs):
                    if getattr(role, "name", "") == "second":
                        # 修复后第二连接会在这里等待；由主线程释放首连接。
                        checkpoint.set()
                    return real_lock(*args, **kwargs)

                def query(name):
                    role.name = name
                    try:
                        return drafts.mcp_request(vault, "key", "missing")
                    finally:
                        if name == "second":
                            # 未修复入口没有取锁，第二连接完成迁移后再释放首连接。
                            checkpoint.set()

                with mock.patch.object(drafts.sqlite3, "connect", side_effect=lambda *a, **kw: real_connect(*a, **kw, factory=PausedConnection)), \
                        mock.patch.object(locking, "write_lock", side_effect=observed_lock), \
                        ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(query, "first")
                    try:
                        self.assertTrue(paused.wait(5), "首连接未到达列快照")
                        second = pool.submit(query, "second")
                        self.assertTrue(checkpoint.wait(5), "第二连接未到达迁移/锁边界")
                    finally:
                        release.set()
                    self.assertIsNone(first.result(timeout=5))
                    self.assertIsNone(second.result(timeout=5))
                for _ in range(2):
                    db = drafts.connect(vault)
                    try:
                        cols = [row["name"] for row in db.execute("PRAGMA table_info(drafts)")]
                        self.assertEqual(len(cols), len(set(cols)))
                        self.assertTrue({"revision", "sources_complete", "source_channel"} <= set(cols))
                        if old_schema:
                            old = db.execute("SELECT id,source_channel FROM drafts WHERE id='old'").fetchone()
                            self.assertEqual(tuple(old), ("old", "legacy"))
                    finally:
                        db.close()

    def test_initialization_failure_closes_connection_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as vault:
            closed = threading.Event()
            real_connect = sqlite3.connect

            class BrokenConnection(sqlite3.Connection):
                def executescript(self, *_args):
                    raise sqlite3.OperationalError("测试迁移中断")

                def close(self):
                    closed.set()
                    super().close()

            with mock.patch.object(drafts.sqlite3, "connect", side_effect=lambda *a, **kw: real_connect(*a, **kw, factory=BrokenConnection)):
                with self.assertRaisesRegex(sqlite3.OperationalError, "迁移中断"):
                    drafts.connect(vault)
            self.assertTrue(closed.is_set())
            db = drafts.connect(vault)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 0)
                self.assertFalse(locking.held_by_current_thread())
                # 连接保持打开时，初始化锁已经释放。
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertEqual(pool.submit(drafts.counts, vault).result(timeout=5)["review"], 0)
            finally:
                db.close()

    def test_initialization_lock_timeout_does_not_open_database(self):
        with tempfile.TemporaryDirectory() as vault:
            with mock.patch.object(locking, "write_lock", side_effect=locking.WriteLockTimeout("测试锁忙")), \
                    mock.patch.object(drafts.sqlite3, "connect") as opened:
                with self.assertRaises(locking.WriteLockTimeout):
                    drafts.connect(vault)
                opened.assert_not_called()

    def test_failure_leaves_no_draft_relation_or_new_file(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            fake = "0" * 64
            with self.assertRaises(ValueError):
                drafts.create_mcp_draft(vault, self._data(fake), self._origin(), [raw])
            db = drafts.connect(vault)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM draft_images").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM conv_images").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM images").fetchone()[0], 0)
            finally:
                db.close()
            self.assertEqual(list(Path(drafts.images_dir(vault)).iterdir()), [])

    def test_bad_subject_after_image_write_rolls_back_every_relation_and_event(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            with mock.patch.object(drafts, "_log") as event:
                with self.assertRaisesRegex(ValueError, "科目不能为空"):
                    drafts.create_mcp_draft(vault, {**self._data(sha), "subject": ""}, self._origin(), [raw])
                event.assert_not_called()
            self._assert_no_relations(vault)
            self.assertEqual(list(Path(drafts.images_dir(vault)).iterdir()), [])

    def test_sql_or_commit_failure_rolls_back_files_and_has_no_create_event(self):
        for query, fail_commit in (("INSERT INTO drafts", False), ("UPDATE mcp_requests", False), (None, True)):
            with self.subTest(query=query, commit=fail_commit), tempfile.TemporaryDirectory() as vault:
                raw = png()
                sha = hashlib.sha256(raw).hexdigest()
                real_connect = drafts.connect
                with mock.patch.object(drafts, "connect", side_effect=lambda v: FaultConnection(real_connect(v), query, fail_commit)):
                    with mock.patch.object(drafts, "_log") as event:
                        with self.assertRaises(sqlite3.OperationalError):
                            drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
                        event.assert_not_called()
                self._assert_no_relations(vault)
                self.assertEqual(list(Path(drafts.images_dir(vault)).iterdir()), [])

    def test_response_failure_after_commit_keeps_original_and_retry_reuses(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            with mock.patch.object(drafts, "get_draft", side_effect=OSError("测试响应中断")):
                with self.assertRaises(OSError):
                    drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            self.assertEqual(Path(drafts.image_path(vault, sha)).read_bytes(), raw)
            record = drafts.mcp_request(vault, "key", "req-1")
            self.assertIsNotNone(record)
            reused = drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            self.assertTrue(reused["reused"])
            self.assertEqual(reused["id"], record["draft_id"])
            self.assertEqual(Path(drafts.image_path(vault, sha)).read_bytes(), raw)

    def test_event_failure_after_commit_keeps_file_and_persisted_draft(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            with mock.patch.object(drafts, "_log", side_effect=OSError("测试事件中断")):
                with self.assertRaises(OSError):
                    drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            record = drafts.mcp_request(vault, "key", "req-1")
            self.assertEqual(Path(drafts.image_path(vault, sha)).read_bytes(), raw)
            self.assertEqual(drafts.get_draft(vault, record["draft_id"])["status"], "review")

    def test_failed_create_preserves_shared_original_and_prior_conversation(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            old = drafts.add_mcp_image(vault, raw, "existing-chat", "existing-run")
            sha = old["sha256"]
            with self.assertRaises(ValueError):
                drafts.create_mcp_draft(vault, {**self._data(sha), "category": ""}, self._origin(), [raw])
            self.assertEqual(Path(drafts.image_path(vault, sha)).read_bytes(), raw)
            self.assertEqual(drafts.resolve_image(vault, "existing-chat", "IMG-1")["sha256"], sha)
            db = drafts.connect(vault)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM images").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM conv_images").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 0)
            finally:
                db.close()

    def test_crashed_partial_same_hash_file_is_restored_and_valid_orphan_is_reused(self):
        for remainder in (b"partial image", png()):
            with self.subTest(remainder=remainder[:10]), tempfile.TemporaryDirectory() as vault:
                raw = png()
                sha = hashlib.sha256(raw).hexdigest()
                path = Path(drafts.images_dir(vault)) / f"{sha}.png"
                path.write_bytes(remainder)
                draft = drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(draft["source_images"][0]["sha256"], sha)
                self.assertEqual([file.name for file in path.parent.iterdir()], [path.name])

    def test_shared_original_missing_on_disk_is_restored_without_losing_db_reference(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            old = drafts.add_mcp_image(vault, raw, "existing-chat", "existing-run")
            sha = old["sha256"]
            path = Path(drafts.image_path(vault, sha))
            path.unlink()
            with self.assertRaises(ValueError):
                drafts.create_mcp_draft(vault, {**self._data(sha), "subject": ""}, self._origin(), [raw])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(drafts.resolve_image(vault, "existing-chat", "IMG-1")["sha256"], sha)

    def test_concurrent_identical_requests_make_one_draft_and_one_image(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            with ThreadPoolExecutor(max_workers=6) as pool:
                calls = [pool.submit(drafts.create_mcp_draft, vault, self._data(sha), self._origin(), [raw])
                         for _ in range(6)]
                results = [call.result() for call in calls]
            self.assertEqual(len({result["id"] for result in results}), 1)
            self.assertEqual(sum(not result["reused"] for result in results), 1)
            db = drafts.connect(vault)
            try:
                for table in ("drafts", "draft_images", "images", "conv_images", "mcp_requests"):
                    self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1, table)
            finally:
                db.close()
            self.assertEqual(Path(drafts.image_path(vault, sha)).read_bytes(), raw)

    def test_old_source_migration_requires_actual_agent_call_context(self):
        with tempfile.TemporaryDirectory() as vault:
            path = Path(drafts.drafts_dir(vault)) / "drafts.db"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE drafts(id TEXT PRIMARY KEY,status TEXT,conversation_id TEXT,run_id TEXT,tool_call_id TEXT)")
            old.executemany("INSERT INTO drafts VALUES(?,?,?,?,?)", [
                ("untraced", "review", "conv", None, None),
                ("asserted", "review", "conv", "fake-run", "fake-call"),
                ("assistant", "review", "conv", "real-run", "real-call"),
                ("wrong-conversation", "review", "other-conv", "real-run", "real-call")])
            old.commit(); old.close()
            agent = sqlite3.connect(path.parent.parent / "agent.db")
            agent.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,conversation_id TEXT)")
            agent.execute("CREATE TABLE tool_calls(run_id TEXT,call_id TEXT,name TEXT)")
            agent.execute("INSERT INTO runs VALUES('real-run','conv')")
            agent.execute("INSERT INTO tool_calls VALUES('real-run','real-call','create_draft')")
            agent.commit(); agent.close()
            db = drafts.connect(vault)
            try:
                channels = {row["id"]: row["source_channel"] for row in db.execute("SELECT id,source_channel FROM drafts")}
            finally:
                db.close()
            self.assertEqual(channels, {"untraced": "legacy", "asserted": "legacy", "assistant": "agent",
                                        "wrong-conversation": "legacy"})

    def test_original_path_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            target = Path(vault) / "unrelated.png"
            target.write_bytes(b"unrelated original")
            path = Path(drafts.images_dir(vault)) / f"{sha}.png"
            os.symlink(target, path)
            with self.assertRaisesRegex(ValueError, "符号链接"):
                drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            self._assert_no_relations(vault)
            self.assertEqual(target.read_bytes(), b"unrelated original")
            self.assertTrue(path.is_symlink())

    def test_jpeg_trailer_is_kept_verbatim_and_text_only_source_keeps_all_images(self):
        # JPEG 标记解析器能定位主图；MCP 保存仍须保留原始相册尾数据。
        sof = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", 12, 10) + b"\x03" + b"\x00" * 9
        jpeg = (b"\xff\xd8" + sof + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00abc"
                + b"\xff\xd9" + b"original-album-trailer")
        with tempfile.TemporaryDirectory() as vault:
            png_raw = png()
            raw_images = [jpeg, png_raw]
            draft = drafts.create_mcp_draft(vault, {"subject": "数学", "category": "外部", "blocks": [
                {"section": "题目", "kind": "text", "text": "整理正文"}]}, self._origin(), raw_images)
            self.assertEqual(len(draft["source_images"]), 2)
            for raw in raw_images:
                sha = hashlib.sha256(raw).hexdigest()
                self.assertEqual(Path(drafts.image_path(vault, sha)).read_bytes(), raw)
                delivered = base64.b64decode(drafts.image_data_url(vault, sha).split(";base64,", 1)[1])
                self.assertEqual(delivered, raw)
            self.assertEqual(draft["training_tasks"], [])

            # 走实际 Web 草稿图像路由，确认它解码 data URL 后也完整返回原件。
            class ImageHandler(OMRSHandler):
                vault_path = vault

                def log_message(self, *_args):
                    pass

            with socketserver.TCPServer(("127.0.0.1", 0), ImageHandler) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    for raw in raw_images:
                        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
                        try:
                            sha = hashlib.sha256(raw).hexdigest()
                            connection.request("GET", f"/api/drafts/image?sha={sha}")
                            response = connection.getresponse()
                            self.assertEqual(response.status, 200)
                            self.assertEqual(int(response.getheader("Content-Length")), len(raw))
                            self.assertEqual(response.read(), raw)
                        finally:
                            connection.close()
                finally:
                    server.shutdown()
                    thread.join(timeout=2)

    def test_atomic_create_preserves_bytes_stable_hash_and_idempotency(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            draft = drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            self.assertEqual(draft["source_channel"], "mcp")
            self.assertEqual(draft["blocks"][0]["box_origin"], "original")
            self.assertEqual(draft["training_tasks"], [])
            with open(drafts.image_path(vault, sha), "rb") as stream:
                self.assertEqual(stream.read(), raw)
            record = drafts.mcp_request(vault, "key", "req-1")
            self.assertEqual(record["content_hash"], self._origin()["content_hash"])
            self.assertEqual(record["stable_hash"], "stable-req-1")
            self.assertEqual(drafts.mcp_request(vault, "key", stable_hash="stable-req-1")["draft_id"], draft["id"])
            reused = drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            self.assertTrue(reused["reused"])
            self.assertEqual(reused["id"], draft["id"])

    def test_original_is_not_accepted_for_partial_or_ai_box_and_set_boxes_does_not_train(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            draft = drafts.create_mcp_draft(vault, self._data(sha), self._origin("req-2"), [raw])
            block = dict(draft["blocks"][0])
            block["box"] = {"x": 0.1, "y": 0.0, "w": 0.9, "h": 1.0}
            with self.assertRaises(drafts.DraftError):
                drafts.update_draft(vault, draft["id"], draft["revision"], {}, [block, draft["blocks"][1]])
            updated = drafts.update_draft(vault, draft["id"], draft["revision"], {}, draft["blocks"])
            cropped = {"id": updated["blocks"][0]["id"], "box_origin": "manual",
                       "box": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}, "ai_box": None}
            result = drafts.set_boxes(vault, updated["id"], updated["revision"], blocks=[cropped])
            self.assertEqual(result["training_tasks"], [])
            enabled = drafts.set_image_training(vault, result["id"], result["revision"], sha, True)
            self.assertEqual(len(enabled["draft"]["training_tasks"]), 1)
            # 显式训练开关生成任务，但原图/正文框不会冒充训练标注。
            self.assertEqual(enabled["draft"]["training_tasks"][0]["boxes"], [])

    def test_mcp_source_update_does_not_enable_global_training_default(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            sha = hashlib.sha256(raw).hexdigest()
            draft = drafts.create_mcp_draft(vault, self._data(sha), self._origin(), [raw])
            with mock.patch("omrs.draft_write.load_config", return_value={"draft_train_default": True}):
                result = drafts.update_draft(vault, draft["id"], draft["revision"], {}, draft["blocks"], [sha])
            self.assertFalse(result["source_images"][0]["train"])
            self.assertEqual(result["training_tasks"], [])


if __name__ == "__main__":
    unittest.main()
