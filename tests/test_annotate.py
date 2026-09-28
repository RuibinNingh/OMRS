"""框选标注集（omrs/annotate.py）与 /api/annotate/*、/annotate 路由。"""
import http.client
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs import annotate  # noqa: E402
from omrs.cli import OMRSTCPServer  # noqa: E402
from omrs.server import OMRSHandler  # noqa: E402


def make_png(width, height, color=(255, 255, 255)):
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-an-")
        os.makedirs(os.path.join(self.vault, "错题"))

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def test_upload_dedupes_and_rejects_non_images(self):
        png = make_png(10, 30)
        first = annotate.upload(self.vault, [("a.png", png), ("b.png", make_png(10, 31, (0, 0, 0)))])
        self.assertEqual(len(first["images"]), 2)
        self.assertEqual(first["images"][0]["status"], "todo")
        again = annotate.upload(self.vault, [("copy.png", png)])
        self.assertEqual(again["images"], [])
        self.assertEqual(again["duplicates"][0]["id"], first["images"][0]["id"])
        with self.assertRaises(ValueError):
            annotate.upload(self.vault, [("x.txt", b"hello")])
        self.assertEqual(len(annotate.list_images(self.vault)), 2)

    def test_clean_boxes_clamps_and_validates(self):
        boxes = annotate.clean_boxes([
            {"role": "question", "x": -0.1, "y": 0.2, "w": 0.5, "h": 2},
            {"role": "answer", "x": 0.5, "y": 0.5, "w": 0.0001, "h": 0.3},
        ])
        self.assertEqual(boxes, [{"role": "question", "x": 0.0, "y": 0.2, "w": 0.4, "h": 0.8}])
        for bad in ([{"role": "ignore", "x": 0, "y": 0, "w": 1, "h": 1}], [{"role": "question", "x": "a"}], {}):
            with self.assertRaises(ValueError):
                annotate.clean_boxes(bad)

    def test_save_keeps_status_until_given_and_stats(self):
        image = annotate.upload(self.vault, [("a.png", make_png(10, 30))])["images"][0]
        box = {"role": "question", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.3}
        saved = annotate.save(self.vault, image["id"], [box])
        self.assertEqual(saved["status"], "todo")
        saved = annotate.save(self.vault, image["id"], [box, {**box, "role": "answer", "y": 0.5}], "done")
        self.assertEqual(saved["status"], "done")
        self.assertEqual(annotate.save(self.vault, image["id"], [box])["status"], "done")
        self.assertEqual(annotate.stats(self.vault), {"images": 1, "done": 1, "todo": 0,
                                                      "boxes": {"question": 1, "answer": 0}})
        with self.assertRaises(ValueError):
            annotate.save(self.vault, image["id"], [], "maybe")
        with self.assertRaises(ValueError):
            annotate.save(self.vault, "AN-missing", [])

    def test_export_yolo_only_done_by_default(self):
        done, todo = annotate.upload(self.vault, [("a.png", make_png(10, 30)),
                                                  ("b.png", make_png(12, 30))])["images"]
        annotate.save(self.vault, done["id"], [{"role": "answer", "x": 0.2, "y": 0.4, "w": 0.4, "h": 0.2}], "done")
        annotate.save(self.vault, todo["id"], [{"role": "question", "x": 0, "y": 0, "w": 1, "h": 1}])
        with zipfile.ZipFile(io.BytesIO(annotate.export(self.vault, "yolo"))) as zf:
            names = zf.namelist()
            lines = zf.read("labels.jsonl").decode().strip().split("\n")
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["id"], done["id"])
            label = [n for n in names if n.startswith("labels/")][0]
            self.assertEqual(zf.read(label).decode(), "1 0.400000 0.500000 0.400000 0.200000\n")
            self.assertEqual(zf.read("classes.txt").decode(), "question\nanswer\n")
            self.assertEqual(sum(n.startswith("images/") for n in names), 1)
        with zipfile.ZipFile(io.BytesIO(annotate.export(self.vault, "omrs_jsonl", include_todo=True))) as zf:
            self.assertEqual(len(zf.read("labels.jsonl").decode().strip().split("\n")), 2)
            self.assertNotIn("classes.txt", zf.namelist())
        with self.assertRaises(ValueError):
            annotate.export(self.vault, "coco")

    def test_delete_removes_row_and_file(self):
        image = annotate.upload(self.vault, [("a.png", make_png(10, 30))])["images"][0]
        folder = annotate.images_dir(self.vault)
        self.assertEqual(len(os.listdir(folder)), 1)
        annotate.delete(self.vault, image["id"])
        self.assertEqual(os.listdir(folder), [])
        self.assertEqual(annotate.list_images(self.vault), [])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = tempfile.mkdtemp(prefix="omrs-an-http-")
        os.makedirs(os.path.join(cls.vault, "错题"))
        handler = type("H", (OMRSHandler,), {"vault_path": cls.vault})
        cls.server = OMRSTCPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.vault, ignore_errors=True)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers={"Origin": f"http://127.0.0.1:{self.port}", **(headers or {})})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def test_page_upload_save_export_delete(self):
        resp, page = self.call("GET", "/annotate")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"features/annotate/index.js", page)
        boundary = "annotate-boundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"shot.png\"\r\n"
                "Content-Type: image/png\r\n\r\n").encode() + make_png(8, 20) + f"\r\n--{boundary}--\r\n".encode()
        resp, data = self.call("POST", "/api/annotate/upload", body,
                               {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(resp.status, 200, data)
        image = json.loads(data)["images"][0]
        resp, data = self.call("GET", f"/api/annotate/raw?id={image['id']}")
        self.assertEqual((resp.status, resp.getheader("Content-Type")), (200, "image/png"))
        payload = json.dumps({"id": image["id"], "status": "done",
                              "boxes": [{"role": "question", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.4}]})
        resp, data = self.call("POST", "/api/annotate/save", payload, {"Content-Type": "application/json"})
        self.assertEqual(json.loads(data)["image"]["status"], "done")
        resp, data = self.call("GET", "/api/annotate/images")
        listing = json.loads(data)
        self.assertEqual((listing["images"][0]["id"], listing["stats"]["done"]), (image["id"], 1))
        resp, data = self.call("GET", "/api/annotate/export?format=yolo")
        self.assertEqual(resp.getheader("Content-Type"), "application/zip")
        self.assertIn("labels.jsonl", zipfile.ZipFile(io.BytesIO(data)).namelist())
        resp, data = self.call("POST", "/api/annotate/save", json.dumps({"id": image["id"], "boxes": "x"}),
                               {"Content-Type": "application/json"})
        self.assertEqual(resp.status, 400)
        resp, data = self.call("POST", "/api/annotate/delete", json.dumps({"id": image["id"]}),
                               {"Content-Type": "application/json"})
        self.assertEqual(resp.status, 200)
        resp, data = self.call("GET", "/api/annotate/stats")
        self.assertEqual(json.loads(data)["images"], 0)


if __name__ == "__main__":
    unittest.main()
