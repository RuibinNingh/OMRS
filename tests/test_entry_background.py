import http.client
import json
import os
import socketserver
import tempfile
import threading
import unittest

from omrs.common import load_config
from omrs.common import save_config
from omrs.server import OMRSHandler


class QuietHandler(OMRSHandler):
    def log_message(self, *_args):
        pass


def multipart(fields, file_part=None):
    boundary = "----omrs-entry-test"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")
    if file_part:
        name, filename, mime, content = file_part
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode())
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", bytes(body)


class EntryBackgroundHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        os.makedirs(os.path.join(self.vault, "错题"), exist_ok=True)
        QuietHandler.vault_path = self.vault
        self.server = socketserver.TCPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.thread.join, 2)

    def request(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_default_is_black_hole_and_config_is_redacted(self):
        status, _, body = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        state = json.loads(body)["entry_background"]
        self.assertEqual(state["mode"], "black-hole")
        self.assertIsNone(state["asset"])
        self.assertEqual(self.request("GET", "/api/entry-background")[0], 404)

    def test_upload_image_then_switch_black_hole_keeps_file_private(self):
        content_type, body = multipart(
            {"mode": "custom", "style": "gaussian-blur", "blur_px": "32"},
            ("file", "wall.png", "image/png", b"\x89PNG\r\n\x1a\nimage"),
        )
        status, _, payload = self.request("POST", "/api/entry-background", {"Content-Type": content_type}, body)
        self.assertEqual(status, 200)
        saved = json.loads(payload)["entry_background"]
        self.assertEqual(saved["mode"], "custom")
        self.assertEqual(saved["blur_px"], 32)
        self.assertEqual(saved["asset"]["mime"], "image/png")
        self.assertEqual(self.request("GET", "/api/entry-background")[0], 200)

        content_type, body = multipart({"mode": "black-hole", "style": "gaussian-blur", "blur_px": "0"})
        self.assertEqual(self.request("POST", "/api/entry-background", {"Content-Type": content_type}, body)[0], 200)
        self.assertEqual(self.request("GET", "/api/entry-background")[0], 404)
        self.assertEqual(load_config(self.vault)["entry_background"]["mode"], "black-hole")
        self.assertEqual(len(os.listdir(os.path.join(self.vault, "错题", ".omrs", "entry-background"))), 1)

    def test_rejects_empty_unknown_mismatch_and_out_of_range(self):
        cases = [
            ("image/png", b"", "入口背景文件不能为空"),
            ("image/png", b"<html>bad</html>", "不支持的入口背景格式"),
            ("image/jpeg", b"\x89PNG\r\n\x1a\nimage", "文件类型与内容不一致"),
        ]
        for mime, data, message in cases:
            content_type, body = multipart({"mode": "custom", "blur_px": "0"}, ("file", "x", mime, data))
            status, _, payload = self.request("POST", "/api/entry-background", {"Content-Type": content_type}, body)
            self.assertEqual(status, 400)
            self.assertIn(message, json.loads(payload)["msg"])
        content_type, body = multipart({"mode": "black-hole", "blur_px": "33"})
        status, _, payload = self.request("POST", "/api/entry-background", {"Content-Type": content_type}, body)
        self.assertEqual(status, 400)
        self.assertIn("0 到 32", json.loads(payload)["msg"])

    def test_upload_video_returns_video_metadata(self):
        content_type, body = multipart(
            {"mode": "custom", "style": "gaussian-blur", "blur_px": "1"},
            ("file", "loop.webm", "video/webm", b"\x1a\x45\xdf\xa3webm"),
        )
        status, _, payload = self.request("POST", "/api/entry-background", {"Content-Type": content_type}, body)
        self.assertEqual(status, 200)
        asset = json.loads(payload)["entry_background"]["asset"]
        self.assertEqual(asset["kind"], "video")
        self.assertEqual(asset["mime"], "video/webm")

    def test_corrupt_selected_file_falls_back_to_black_hole(self):
        media_dir = os.path.join(self.vault, "错题", ".omrs", "entry-background")
        os.makedirs(media_dir, exist_ok=True)
        asset_id = "abcdef0123456789abcdef0123456789"
        with open(os.path.join(media_dir, asset_id + ".png"), "wb") as stream:
            stream.write(b"<html>not-an-image</html>")
        save_config(self.vault, {"entry_background": {"mode": "custom", "style": "gaussian-blur", "blur_px": 2,
                                                       "asset": {"id": asset_id, "kind": "image", "mime": "image/png", "bytes": 25}}})
        state = json.loads(self.request("GET", "/api/config")[2])["entry_background"]
        self.assertEqual(state["mode"], "black-hole")
        self.assertIsNone(state["asset"])
        self.assertEqual(self.request("GET", "/api/entry-background")[0], 404)

    def test_custom_without_current_asset_and_path_traversal_id_are_rejected(self):
        content_type, body = multipart({"mode": "custom", "asset_id": "../secret", "blur_px": "0"})
        status, _, payload = self.request("POST", "/api/entry-background", {"Content-Type": content_type}, body)
        self.assertEqual(status, 400)
        self.assertIn("ID 不合法", json.loads(payload)["msg"])


if __name__ == "__main__":
    unittest.main()
