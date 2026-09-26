"""/assets/ 静态资源的条件请求：弱 ETag + Last-Modified，文件未变时回 304（v1.21.0 起）。"""
import http.client
import os
import socketserver
import tempfile
import threading
import unittest

from omrs.server import OMRSHandler

ASSET = "/assets/app/styles/tokens.css"


class QuietHandler(OMRSHandler):
    def log_message(self, *_args):
        pass


class AssetCacheTests(unittest.TestCase):
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

    def get(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_first_request_carries_validators(self):
        status, headers, body = self.get(ASSET)
        self.assertEqual(status, 200)
        self.assertTrue(headers["ETag"].startswith('W/"'))
        self.assertIn("GMT", headers["Last-Modified"])
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        self.assertTrue(body)

    def test_matching_etag_returns_304_without_body(self):
        etag = self.get(ASSET)[1]["ETag"]
        for value in (etag, etag[2:], f'"other", {etag}', "*"):
            status, headers, body = self.get(ASSET, {"If-None-Match": value})
            self.assertEqual(status, 304, value)
            self.assertEqual(body, b"")
            self.assertEqual(headers["ETag"], etag)

    def test_changed_etag_returns_full_body(self):
        status, _, body = self.get(ASSET, {"If-None-Match": 'W/"0-0"'})
        self.assertEqual(status, 200)
        self.assertTrue(body)

    def test_if_modified_since(self):
        last_modified = self.get(ASSET)[1]["Last-Modified"]
        self.assertEqual(self.get(ASSET, {"If-Modified-Since": last_modified})[0], 304)
        self.assertEqual(self.get(ASSET, {"If-Modified-Since": "Thu, 01 Jan 1970 00:00:00 GMT"})[0], 200)
        self.assertEqual(self.get(ASSET, {"If-Modified-Since": "not a date"})[0], 200)
        # If-None-Match 存在时以它为准，不看 If-Modified-Since
        self.assertEqual(self.get(ASSET, {"If-None-Match": 'W/"0-0"', "If-Modified-Since": last_modified})[0], 200)

    def test_html_and_module_types(self):
        status, headers, _ = self.get("/assets/app/gallery.html")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(self.get("/assets/app/main.js")[1]["Content-Type"], "application/javascript; charset=utf-8")

    def test_traversal_still_blocked(self):
        self.assertEqual(self.get("/assets/../omrs/server.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
