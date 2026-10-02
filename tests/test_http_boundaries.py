"""HTTP 鉴权、请求锁段与暂存上传的真实行为回归。"""
import base64
import concurrent.futures
import email.message
import hashlib
import http.client
import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from omrs import http_io, security, uploads, vault_lifecycle
from omrs.exporting import _find_image
from omrs.http.bodies import parse_images
from omrs.server import OMRSHandler
from http.server import ThreadingHTTPServer

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6n0AAAAASUVORK5CYII=")


class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.vault = self.directory.name
        Path(self.vault, "错题", "附件").mkdir(parents=True)
        self.handler = type("BoundaryHandler", (OMRSHandler,), {"vault_path": self.vault,
                           "log_message": lambda *args: None})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.directory.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        status, values, payload = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, values, payload

    def post(self, path, data):
        status, _, payload = self.request("POST", path, json.dumps(data), {"Content-Type": "application/json"})
        return status, json.loads(payload)

    def test_registry_targets_all_exist_on_public_handler(self):
        from omrs.http.registry import ROUTES, PREFIXES
        for identity, target in {**ROUTES, **PREFIXES}.items():
            with self.subTest(route=identity):
                self.assertTrue(callable(getattr(OMRSHandler, target, None)), target)

    def test_head_uses_get_auth_and_resource_allowlist(self):
        remote = {"Host": "omrs.test", "X-Real-IP": "198.51.100.77", "X-Forwarded-Proto": "https"}
        status, headers, body = self.request("HEAD", "/api/config", headers=remote)
        self.assertEqual(status, 401)
        self.assertEqual(body, b"")
        self.assertGreater(int(headers["Content-Length"]), 0)
        self.assertEqual(self.request("HEAD", "/omrs/security.py")[0], 404)
        status, headers, body = self.request("HEAD", "/api/auth/session")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")

    def test_image_absolute_traversal_symlink_and_double_encoding(self):
        outside = Path(self.vault, "outside.png")
        outside.write_bytes(PNG)
        root = Path(self.vault, "错题", "附件")
        (root / "safe.png").write_bytes(PNG)
        (root / "linked.png").symlink_to(outside)
        for name in (str(outside), "../outside.png", "linked.png", "%2e%2e/outside.png"):
            from urllib.parse import urlencode
            self.assertEqual(self.request("GET", "/api/image?" + urlencode({"name": name}))[0], 404)
            self.assertIsNone(_find_image(self.vault, name))
        status, _, body = self.request("GET", "/api/image?name=safe.png")
        self.assertEqual((status, body), (200, PNG))
        (root / "%41.png").write_bytes(PNG)
        self.assertEqual(self.request("GET", "/api/image?name=%2541.png")[2], PNG)
        (root / "nested").mkdir()
        (root / "nested" / "safe.png").write_bytes(PNG)
        self.assertEqual(self.request("GET", "/api/image?name=safe.png")[0], 404)
        self.assertEqual(self.request("GET", "/api/image?name=nested%2Fsafe.png")[2], PNG)

    def test_length_and_json_errors_have_stable_status(self):
        for value in ("-1", "wat", "3, 3"):
            status, _, _ = self.request("POST", "/api/config", b"", {"Content-Length": value})
            self.assertEqual(status, 400)
        self.assertEqual(self.request("POST", "/api/config", b"[]")[0], 400)
        self.assertEqual(self.request("POST", "/api/config", b"\xff")[0], 400)
        self.assertEqual(self.request("POST", "/api/config", b"", {"Content-Length": str(2 * http_io.MIB + 1)})[0], 413)

    def test_json_body_limit_can_be_lowered_and_raised_through_http(self):
        status, changed = self.post("/api/config", {"http_json_mib": 1})
        self.assertEqual(status, 200, changed)
        for endpoint in ("/api/config", "/api/inbox/upload-refs", "/api/annotate/upload-refs"):
            status, _, body = self.request("POST", endpoint, b"", {"Content-Length": str(http_io.MIB + 1)})
            self.assertEqual(status, 413, json.loads(body))
        status, changed = self.post("/api/config", {"http_json_mib": 3})
        self.assertEqual(status, 200, changed)
        padding = "大" * (http_io.MIB // 3 * 2 + 100)
        payload = json.dumps({"limit_probe": padding}, ensure_ascii=False).encode()
        self.assertGreater(len(payload), 2 * http_io.MIB)
        self.assertLess(len(payload), 3 * http_io.MIB)
        status, _, body = self.request("POST", "/api/config", payload, {"Content-Type": "application/json"})
        self.assertEqual(status, 200, json.loads(body))
        status, _, body = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        current = json.loads(body)
        self.assertEqual(current["http_json_mib"], 3)
        self.assertEqual(current["limit_probe"], padding)
        self.assertEqual(self.request("POST", "/api/config", b"[]")[0], 400)
        self.assertEqual(http_io.policy("/api/auth/login", json_mib=3)[0], 4096)
        self.assertEqual(http_io.policy("/api/mcp/keys", json_mib=3)[0], 16 * 1024)
        self.assertEqual(http_io.policy("/api/uploads/chunk", json_mib=3)[0], http_io.CHUNK_BYTES)
        self.assertEqual(http_io.policy("/api/inbox/upload-refs", json_mib=3)[0], 3 * http_io.MIB)

    def test_json_limit_rejects_invalid_types_without_changing_active_config(self):
        for value in (True, "3", 1.5, 0, 8193, None, {}):
            with self.subTest(value=value):
                status, response = self.post("/api/config", {"http_json_mib": value})
                self.assertEqual(status, 400, response)
                self.assertIn("http_json_mib", response["msg"])
        from omrs.common import load_config
        self.assertEqual(load_config(self.vault).get("http_json_mib", 2), 2)

    def test_backup_reference_metadata_limit_rejects_before_body_or_prepare(self):
        status, saved = self.post("/api/config", {"http_json_mib": 1})
        self.assertEqual(status, 200, saved)
        for endpoint, content_type in (("/api/backup/import", "application/json"),
                                       ("/api/backup/import", "Application/JSON; charset=utf-8"),
                                       ("/api/config", "multipart/form-data; boundary=unused")):
            with patch.object(http_io.tempfile, "TemporaryFile", side_effect=AssertionError("超限元数据不应暂存或读取正文")), patch("omrs.server.prepare_backup_import") as prepare:
                status, _, body = self.request("POST", endpoint, b"", {
                    "Content-Type": content_type, "Content-Length": str(http_io.MIB + 1)})
            self.assertEqual(status, 413, json.loads(body))
            prepare.assert_not_called()
        for content_type in ("application/zip", "multipart/form-data; boundary=backup"):
            self.assertEqual(http_io.policy("/api/backup/import", content_type, json_mib=1)[0], 8 * 1024 * http_io.MIB)

    def test_slow_body_does_not_hold_write_lock(self):
        slow = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=3)
        with patch.object(http_io, "IDLE_TIMEOUT", 0.4):
            slow.sendall(b"POST /api/config HTTP/1.0\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{")
            time.sleep(0.04)
            started = time.monotonic()
            status, body = self.post("/api/config", {"test_boundary": True})
            elapsed = time.monotonic() - started
            self.assertEqual(status, 200, body)
            self.assertLess(elapsed, 0.3)
            response = slow.recv(4096)
            self.assertIn(b"408", response)
        slow.close()

    def test_body_from_previous_generation_never_reaches_dispatch(self):
        receive = http_io.receive
        def replaced_vault(handler, path):
            spool = receive(handler, path)
            with vault_lifecycle.exclusive(self.vault):
                vault_lifecycle.advance_generation(self.vault)
            return spool
        with patch.object(http_io, "receive", side_effect=replaced_vault), patch.object(self.handler, "_dispatch_post") as dispatch:
            status, response = self.post("/api/config", {"old_generation_write": True})
        self.assertEqual(status, 409, response)
        self.assertEqual(response["code"], "vault_changed")
        dispatch.assert_not_called()
        from omrs.common import load_config
        self.assertNotIn("old_generation_write", load_config(self.vault))

    def test_review_archive_stream_is_outside_lease_and_removed(self):
        artifact = Path(self.vault, "review.zip")
        artifact.write_bytes(b"archive-evidence")
        download = self.handler._download_file
        def send(handler, path, filename, content_type, headers=None):
            with vault_lifecycle.exclusive(self.vault, timeout=.1):
                pass
            return download(handler, path, filename, content_type, headers)
        with patch("omrs.server.build_review_export", return_value=(str(artifact), "复盘.zip", "application/zip")) as build, patch.object(self.handler, "_download_file", new=send):
            status, headers, payload = self.request("GET", "/api/export-review?include_images=1")
        self.assertEqual((status, payload), (200, b"archive-evidence"))
        self.assertEqual(headers["Content-Type"], "application/zip")
        build.assert_called_once_with(self.vault, include_images=True, file_artifact=True)
        self.assertFalse(artifact.exists())

    def test_failed_download_discards_captured_success_headers(self):
        artifact = Path(self.vault, "review.zip")
        artifact.write_bytes(b"archive")
        def fail(handler, path, filename, content_type, headers=None):
            handler._download_headers(7, filename, content_type)
            handler.wfile.write(b"partial")
            raise OSError("测试磁盘读取失败")
        with patch("omrs.server.build_review_export", return_value=(str(artifact), "复盘.zip", "application/zip")), patch.object(self.handler, "_download_file", new=fail):
            status, headers, payload = self.request("GET", "/api/export-review?include_images=1")
        self.assertEqual(status, 500)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("测试磁盘读取失败", json.loads(payload)["msg"])
        self.assertFalse(artifact.exists())

    def test_restore_http_rebases_only_exclusive_maintenance(self):
        from omrs.backup_store import create_backup
        from omrs.creation import create_question
        from omrs.data_repository import mastery_rows
        create_question(self.vault, "数学", "旧题库", 5, question_text="旧题")
        with tempfile.TemporaryDirectory() as source:
            create_question(source, "数学", "恢复题库", 5, question_text="备份题")
            archive, _, _, _ = create_backup(source)
            try:
                status, _, body = self.request("POST", "/api/backup/import", Path(archive).read_bytes(), {"Content-Type": "application/zip"})
                preview = json.loads(body)
                self.assertEqual(status, 200, preview)
                original_generation = vault_lifecycle.generation(self.vault)
                for invalid in ("false", "true", 1, 0, None, False):
                    status, rejected = self.post("/api/backup/restore", {"restore_id": preview["restore_id"], "confirm": invalid})
                    self.assertEqual(status, 400, rejected)
                    self.assertEqual(vault_lifecycle.generation(self.vault), original_generation)
                    self.assertEqual([row["Category"] for row in mastery_rows(self.vault)], ["旧题库"])
                status, restored = self.post("/api/backup/restore", {"restore_id": preview["restore_id"], "confirm": True})
                self.assertEqual(status, 200, restored)
                self.assertTrue(restored["restored"])
                self.assertEqual([row["Category"] for row in mastery_rows(self.vault)], ["恢复题库"])
            finally:
                os.unlink(archive)

    def test_backup_upload_reference_rejects_same_length_valid_zip_tampering(self):
        from omrs.backup_store import create_backup
        from omrs.creation import create_question
        with tempfile.TemporaryDirectory() as source:
            create_question(source, "数学", "备份", 5, question_text="原题")
            archive, _, _, _ = create_backup(source)
            try:
                with zipfile.ZipFile(archive, "a") as file:
                    file.comment = b"one"
                raw = Path(archive).read_bytes()
            finally:
                os.unlink(archive)
        status, begin = self.post("/api/uploads/start", {"filename": "backup.zip", "purpose": "backup", "total_bytes": len(raw)})
        self.assertEqual(status, 200, begin)
        status, _, body = self.request("POST", "/api/uploads/chunk?upload_id=" + begin["upload_id"] + "&index=0", raw,
                                       {"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 200, json.loads(body))
        status, completed = self.post("/api/uploads/complete", {"upload_id": begin["upload_id"]})
        self.assertEqual(status, 200, completed)
        with uploads.request_owner("direct:127.0.0.1"):
            state = uploads.resolve(self.vault, completed, purpose="backup")
        status, _, body = self.request("POST", "/api/backup/import", json.dumps({"upload_ref": completed["upload_ref"]}),
                                       {"Content-Type": "Application/JSON; charset=utf-8"})
        self.assertEqual(status, 200, json.loads(body))
        altered = raw[:-3] + b"two"
        self.assertEqual(len(altered), len(raw))
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(altered)))
        Path(state["path"]).write_bytes(altered)
        with patch("omrs.server.prepare_backup_import") as prepare:
            status, rejected = self.post("/api/backup/import", {"upload_ref": completed["upload_ref"]})
        self.assertEqual(status, 400, rejected)
        self.assertIn("校验", rejected["msg"])
        prepare.assert_not_called()

    def test_backup_reference_copy_allows_maintenance_and_rechecks_generation(self):
        with uploads.request_owner("stream-copy"):
            begin = uploads.start(self.vault, "backup.zip", "application/zip", len(PNG), "backup")
            uploads.chunk(self.vault, begin["upload_id"], 0, PNG)
            completed = uploads.complete(self.vault, begin["upload_id"])
            vault = self.vault
            class RestoreDuringWrite(io.BytesIO):
                def write(self, value):
                    with vault_lifecycle.exclusive(vault, timeout=.1):
                        vault_lifecycle.advance_generation(vault)
                    return super().write(value)
            with self.assertRaises(vault_lifecycle.VaultChanged):
                uploads.copy_to(self.vault, completed, RestoreDuringWrite(), purpose="backup")

    def test_backup_reference_copy_rejects_growth_before_writing_excess_bytes(self):
        with uploads.request_owner("stream-growth"):
            begin = uploads.start(self.vault, "backup.zip", "application/zip", len(PNG), "backup")
            uploads.chunk(self.vault, begin["upload_id"], 0, PNG)
            completed = uploads.complete(self.vault, begin["upload_id"])
            path = uploads.resolve(self.vault, completed, purpose="backup")["path"]
            class GrowDuringCopy(io.BytesIO):
                def write(self, value):
                    with open(path, "ab") as file:
                        file.write(b"unexpected-growth")
                    return super().write(value)
            target = GrowDuringCopy()
            with self.assertRaisesRegex(ValueError, "长度"):
                uploads.copy_to(self.vault, completed, target, purpose="backup")
            self.assertEqual(target.getvalue(), PNG)

    def test_chunk_protocol_retries_integrity_and_owner(self):
        status, begin = self.post("/api/uploads/start", {"filename": "one.png", "mime": "image/png", "purpose": "inbox", "total_bytes": len(PNG)})
        self.assertEqual(status, 200, begin)
        path = "/api/uploads/chunk?upload_id=" + begin["upload_id"] + "&index=0"
        self.assertEqual(self.request("POST", path, PNG, {"Content-Type": "application/octet-stream"})[0], 200)
        status, _, payload = self.request("POST", path, PNG, {"Content-Type": "application/octet-stream"})
        self.assertTrue(json.loads(payload)["reused"])
        status, complete = self.post("/api/uploads/complete", {"upload_id": begin["upload_id"], "sha256": hashlib.sha256(PNG).hexdigest()})
        self.assertEqual(status, 200, complete)
        with uploads.request_owner("direct:127.0.0.1"):
            self.assertEqual(uploads.read(self.vault, complete), PNG)
            with self.assertRaises(ValueError):
                uploads.resolve(self.vault, complete, purpose="assistant")
        with uploads.request_owner("another-client"):
            with self.assertRaises(ValueError):
                uploads.resolve(self.vault, complete)
        with vault_lifecycle.exclusive(self.vault):
            vault_lifecycle.advance_generation(self.vault)
        with self.assertRaises(ValueError):
            uploads.resolve(self.vault, complete)

    def test_upload_rechecks_chunk_space_and_completion_length(self):
        with uploads.request_owner("space"):
            begin = uploads.start(self.vault, "one.png", "image/png", len(PNG), "inbox")
            class Usage:
                free = 64 * 1024 * 1024
            with patch.object(uploads.shutil, "disk_usage", return_value=Usage()):
                with self.assertRaisesRegex(ValueError, "空间不足"):
                    uploads.chunk(self.vault, begin["upload_id"], 0, PNG)
            uploads.chunk(self.vault, begin["upload_id"], 0, PNG)
            directory = uploads._directory(self.vault, begin["upload_id"])
            with open(directory / "content", "ab") as file:
                file.write(b"unexpected")
            with self.assertRaisesRegex(ValueError, "长度"):
                uploads.complete(self.vault, begin["upload_id"])

    def test_upload_reference_endpoints_accept_filename_contract(self):
        for purpose, endpoint in (("inbox", "/api/inbox/upload-refs"), ("annotate", "/api/annotate/upload-refs")):
            with uploads.request_owner("direct:127.0.0.1"):
                began = uploads.start(self.vault, "题图.png", "image/png", len(PNG), purpose)
                uploads.chunk(self.vault, began["upload_id"], 0, PNG)
                completed = uploads.complete(self.vault, began["upload_id"])
            status, response = self.post(endpoint, {"images": [{"upload_ref": completed["upload_ref"], "filename": "题图.png"}]})
            self.assertEqual(status, 200, response)
            rows = response["items" if purpose == "inbox" else "images"]
            self.assertEqual(rows[0]["file"], "题图.png")

    def test_streaming_legacy_many_images_preserves_bytes_and_metadata(self):
        value = {"question_images": ["data:image/png;base64," + base64.b64encode(PNG).decode()] * 20,
                 "question_text": "data:image/png;base64,保持文字", "labels": ["中文\n标记", "😀"]}
        with uploads.request_owner("parser"):
            parsed = parse_images(io.BytesIO(json.dumps(value, ensure_ascii=True).encode()), self.vault, "create")
            self.assertEqual(parsed["labels"], value["labels"])
            self.assertEqual(parsed["question_text"], value["question_text"])
            self.assertEqual(len(parsed["question_images"]), 20)
            for reference in parsed["question_images"]:
                self.assertEqual(uploads.read(self.vault, reference), PNG)
        for body in (b'{"x":}', b'{"x":"bad\\q"}', b'{"x":1}garbage', b'[{"x":1}]'):
            with self.assertRaises(http_io.BodyError):
                parse_images(io.BytesIO(body), self.vault, "create")

    def test_parallel_wrong_pin_counts_five_and_keeps_vaults_separate(self):
        barrier = threading.Barrier(12)
        def check(_):
            barrier.wait()
            try:
                return security.verify_pin_limited(self.vault, "bad", "198.51.100.55")
            except ValueError:
                return "limited"
        def wrong(*args):
            time.sleep(0.025)
            return False
        with patch.object(security, "verify_pin", side_effect=wrong):
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                result = list(pool.map(check, range(12)))
            self.assertEqual(result.count(False), 5)
            self.assertEqual(result.count("limited"), 7)
            self.assertFalse(security._PIN_CHECKS)
            with tempfile.TemporaryDirectory() as another:
                self.assertFalse(security.verify_pin_limited(another, "bad", "198.51.100.55"))


if __name__ == "__main__":
    unittest.main()
