"""/assets/ 静态资源的条件请求：弱 ETag + Last-Modified，文件未变时回 304（v1.21.0 起）。"""
import http.client
import gzip
import os
import re
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

    def get(self, path, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        conn.request(method, path, headers=headers or {})
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

    def test_gzip_negotiation_and_conditional_request(self):
        status, headers, plain = self.get(ASSET)
        self.assertEqual(status, 200)
        status, packed_headers, packed = self.get(ASSET, {"Accept-Encoding": "br, gzip;q=0.8"})
        self.assertEqual(status, 200)
        self.assertEqual(packed_headers["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(packed), plain)
        self.assertLess(len(packed), len(plain))
        self.assertEqual(int(packed_headers["Content-Length"]), len(packed))
        self.assertEqual(packed_headers["Vary"], "Accept-Encoding")
        self.assertEqual(packed_headers["ETag"], headers["ETag"])
        status, cached_headers, body = self.get(ASSET, {"Accept-Encoding": "gzip", "If-None-Match": headers["ETag"]})
        self.assertEqual((status, body), (304, b""))
        self.assertEqual(cached_headers["Vary"], "Accept-Encoding")
        for encoding in ("gzip;q=0, *;q=1", "br", "gzip;q=invalid"):
            _, identity_headers, body = self.get(ASSET, {"Accept-Encoding": encoding})
            self.assertNotIn("Content-Encoding", identity_headers)
            self.assertEqual(body, plain)

    def test_gzip_head_has_get_length_without_body(self):
        headers = {"Accept-Encoding": "gzip"}
        _, get_headers, body = self.get(ASSET, headers)
        status, head_headers, head_body = self.get(ASSET, headers, method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(head_body, b"")
        self.assertEqual(head_headers["Content-Encoding"], "gzip")
        self.assertEqual(int(head_headers["Content-Length"]), len(body))
        self.assertEqual(head_headers["Content-Length"], get_headers["Content-Length"])

    def test_dashboard_versioned_graph_and_combined_css(self):
        status, headers, page = self.get("/?unlocked=1", {"Accept-Encoding": "gzip"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Encoding"], "gzip")
        page = gzip.decompress(page).decode("utf-8-sig")
        main = re.search(r'src="(/assets/_v/[a-f0-9]+/app/main.js)"', page).group(1)
        self.assertIn('rel="modulepreload"', page)
        _, module_headers, module = self.get(main)
        self.assertEqual(module_headers["Cache-Control"], "private, max-age=31536000, immutable")
        self.assertEqual(module, self.get("/assets/app/main.js")[2])
        prefix = main.removesuffix("app/main.js")
        status, _, stylesheet = self.get(prefix + "app/styles/index.css")
        self.assertEqual(status, 200)
        self.assertNotIn(b"@import", stylesheet)
        self.assertIn(b"@layer vendor {", stylesheet)
        self.assertIn(b"@layer ui {", stylesheet)
        font = re.search(rb'url\("(/assets/_v/[^\x22]+\.woff2)"\)', stylesheet).group(1).decode()
        self.assertEqual(self.get(font)[0], 200)
        self.assertEqual(self.get(prefix + "../../omrs/server.py")[0], 404)
        self.assertEqual(self.get(main.replace("/_v/", "/_v/0", 1))[0], 404)

    def test_versioned_assets_still_require_remote_authorization(self):
        page = self.get("/?unlocked=1")[2].decode("utf-8-sig")
        main = re.search(r'src="(/assets/_v/[a-f0-9]+/app/main.js)"', page).group(1)
        headers = {"Host": "omrs.example", "X-Real-IP": "192.0.2.15", "X-Forwarded-Proto": "https"}
        self.assertEqual(self.get(main, headers)[0], 401)


if __name__ == "__main__":
    unittest.main()
