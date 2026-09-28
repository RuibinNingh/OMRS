"""草稿 P3 的真实 HTTP 与服务重启回归；模型替身只运行在临时服务进程。"""
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

from omrs import drafts
from omrs.ledger import read_commits
from tests.test_drafts import data_url, make_png


ROOT = Path(__file__).resolve().parents[1]
WHOLE = {"x": 0, "y": 0, "w": 1, "h": 1}
SERVER = r'''
import http.server, os, sys, time
from pathlib import Path
from omrs import ai_assist
from omrs.server import OMRSHandler
vault, ready, mode = sys.argv[1:]
def extract(*args, **kwargs):
    Path(vault, "extract-entered").touch()
    if mode == "hold":
        deadline = time.monotonic() + 15
        while not Path(vault, "extract-release").exists() and time.monotonic() < deadline:
            time.sleep(.02)
    return {"convertible": True, "reason": "", "text": "提取结果 $f(2)=4$。"}
ai_assist.extract_region = extract
class Handler(OMRSHandler):
    vault_path = vault
    def log_message(self, *_args):
        pass
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
Path(ready).write_text(str(server.server_port))
server.serve_forever()
'''


class DraftP3HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="omrs-draft-p3-http-")
        self.vault = self.temp.name
        self.addCleanup(self.temp.cleanup)
        self.process = None
        self.output = None
        self.addCleanup(self.stop_server)
        self.image_url = data_url(make_png(16, 12))
        self.image = drafts.add_image(self.vault, self.image_url, "http-conv", "http-run")
        self.draft = drafts.create_draft(self.vault, {
            "subject": "数学", "category": "函数", "source_images": [self.image["sha256"]],
            "blocks": [{"section": "题目", "kind": "image", "image_sha": self.image["sha256"]}],
        }, {"conversation_id": "http-conv", "run_id": "http-run"})

    def start_server(self, mode="normal"):
        self.stop_server()
        ready = Path(self.vault, "server-port")
        ready.unlink(missing_ok=True)
        self.output = open(Path(self.vault, "server.log"), "a", encoding="utf-8")
        env = {key: value for key, value in os.environ.items() if key != "OMRS_SYSTEMD_SERVICE"}
        self.process = subprocess.Popen([sys.executable, "-c", SERVER, self.vault, str(ready), mode],
                                        cwd=ROOT, env=env, stdout=self.output, stderr=self.output)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if ready.exists():
                self.port = int(ready.read_text())
                return
            if self.process.poll() is not None:
                self.fail(Path(self.vault, "server.log").read_text())
            time.sleep(.02)
        self.fail("临时服务启动超时")

    def stop_server(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=5)
            self.process = None
        if self.output is not None:
            self.output.close()
            self.output = None

    def request(self, path, body=None, binary=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        try:
            conn.request("GET" if body is None else "POST", path,
                         None if body is None else json.dumps(body).encode(),
                         {} if body is None else {"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read()
            return response.status, raw if binary else json.loads(raw)
        finally:
            conn.close()

    def ok(self, path, body=None):
        status, result = self.request(path, body)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "ok", result)
        return result

    def item(self):
        return self.ok("/api/drafts/item?id=" + self.draft["id"])["draft"]

    def boxed(self):
        current = self.item()
        return self.ok("/api/drafts/boxes", {
            "id": current["id"], "revision": current["revision"],
            "blocks": [{"id": current["blocks"][0]["id"], "box": WHOLE, "box_origin": "manual"}],
        })["draft"]

    def extract(self, current):
        return self.ok("/api/drafts/extract", {
            "id": current["id"], "revision": current["revision"],
            "block_ids": [current["blocks"][0]["id"]],
        })["job"]

    def wait_job(self, job):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            current = self.ok("/api/drafts/job?id=" + job["id"])["job"]
            if current["status"] not in ("queued", "running"):
                return current
            time.sleep(.025)
        self.fail("后台提取没有结束")

    def wait_extract_entered(self):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if Path(self.vault, "extract-entered").exists():
                return
            time.sleep(.02)
        self.fail("后台任务没有进入模型替身")

    def test_boxes_training_errors_and_cleanup_shape(self):
        self.start_server()
        current = self.item()
        body = {"id": current["id"], "revision": current["revision"],
                "blocks": [{"id": current["blocks"][0]["id"],
                            "box": {**WHOLE, "w": -1}, "box_origin": "manual"}]}
        status, result = self.request("/api/drafts/boxes", body)
        self.assertEqual(status, 400, result)
        self.assertEqual(self.item()["revision"], current["revision"])
        saved = self.boxed()
        self.assertEqual(saved["status"], "review")
        status, result = self.request("/api/drafts/image/train", {
            "id": saved["id"], "revision": saved["revision"],
            "sha": self.image["sha256"], "enabled": "true"})
        self.assertEqual(status, 400, result)
        body["blocks"][0]["box"] = WHOLE
        status, result = self.request("/api/drafts/boxes", body)
        self.assertEqual(status, 409, result)
        self.assertEqual(result["current_revision"], saved["revision"])
        sibling = drafts.create_draft(self.vault, {
            "subject": "数学", "category": "代数", "source_images": [self.image["sha256"]],
            "blocks": [{"section": "题目", "kind": "text", "text": "同图另一题"}],
        }, {"conversation_id": "http-conv"})
        enabled = self.ok("/api/drafts/image/train", {
            "id": saved["id"], "revision": saved["revision"],
            "sha": self.image["sha256"], "enabled": True})["draft"]
        self.assertGreater(enabled["revision"], saved["revision"])
        other = self.ok("/api/drafts/item?id=" + sibling["id"])["draft"]
        self.assertGreater(other["revision"], sibling["revision"])
        status, result = self.request("/api/drafts/commit", {
            "id": saved["id"], "revision": saved["revision"]})
        self.assertEqual(status, 409, result)
        cleaned = self.ok("/api/drafts/cleanup", {})
        self.assertTrue({"cleaned", "retained"} <= cleaned.keys())
        self.assertEqual(self.request("/api/drafts/image?sha=" + self.image["sha256"], binary=True)[0], 200)

    def test_extract_then_train_is_hidden_from_queue_and_upload_promotes(self):
        self.start_server()
        current = self.boxed()
        current = self.ok("/api/drafts/image/train", {
            "id": current["id"], "revision": current["revision"],
            "sha": self.image["sha256"], "enabled": True})["draft"]
        self.assertEqual(self.wait_job(self.extract(current))["status"], "done")
        current = self.item()
        self.assertEqual(current["blocks"][0]["kind"], "text")
        self.assertIn("f(2)=4", current["blocks"][0]["text"])
        self.assertEqual(current["source_images"][0]["sha256"], self.image["sha256"])
        self.assertTrue(current["training_tasks"][0]["boxes"])
        committed = self.ok("/api/drafts/commit", {"id": current["id"], "revision": current["revision"]})
        self.assertEqual(committed["draft"]["status"], "done")
        self.assertIn(self.image["sha256"], committed["training"]["registered"])
        self.assertEqual(self.ok("/api/inbox/items")["items"], [])
        trained = self.item()["source_images"][0]["inbox_item_id"]
        saved_item = self.ok("/api/inbox/item?id=" + trained)["item"]
        self.assertEqual((saved_item["source"], saved_item["layout"], saved_item["status"]), ("chat", "other", "ready"))
        self.assertTrue(saved_item["training_only"])
        status, result = self.request("/api/inbox/commit", {"id": trained})
        self.assertEqual(status, 400, result)
        retried = self.ok("/api/drafts/commit", {"id": current["id"], "revision": current["revision"]})
        self.assertTrue(retried["reused"])
        self.assertEqual(len([c for c in read_commits(self.vault) if c["commit_type"] == "question.create"]), 1)
        status, raw = self.request("/api/inbox/dataset/export?format=yolo", binary=True)
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            records = [json.loads(line) for line in archive.read("labels.jsonl").decode().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["regions"])
            self.assertIn("labels/" + self.image["sha256"] + ".txt", archive.namelist())
        self.ok("/api/inbox/upload", {"images": [{"name": "主动上传.png", "data": self.image_url}], "source": "desktop"})
        normal = self.ok("/api/inbox/items")["items"]
        self.assertEqual(len(normal), 1)
        self.assertFalse(normal[0]["training_only"])
        self.assertEqual(normal[0]["status"], "pending")
        self.assertEqual(self.ok("/api/inbox/dataset/stats")["images"], 1)

    def test_edit_during_extract_does_not_wait_for_model_or_overwrite(self):
        self.start_server("hold")
        current = self.boxed()
        job = self.extract(current)
        self.wait_extract_entered()
        try:
            saved = self.ok("/api/drafts/update", {
                "id": current["id"], "revision": current["revision"],
                "fields": {"note": "模型等待中仍可编辑"}, "blocks": current["blocks"],
            })["draft"]
        finally:
            Path(self.vault, "extract-release").touch()
        self.assertEqual(self.wait_job(job)["status"], "conflict")
        current = self.item()
        self.assertEqual(current["revision"], saved["revision"])
        self.assertEqual(current["note"], "模型等待中仍可编辑")
        self.assertEqual(current["blocks"][0]["kind"], "image")

    def test_restart_reports_interrupted_job_without_changing_content(self):
        self.start_server("hold")
        current = self.boxed()
        job = self.extract(current)
        self.wait_extract_entered()
        self.start_server()
        self.assertEqual(self.wait_job(job)["status"], "interrupted")
        current = self.item()
        self.assertEqual(current["blocks"][0]["kind"], "image")
        self.assertTrue(any(row["id"] == job["id"] for row in current["jobs"]))
        self.assertEqual(self.wait_job(self.extract(current))["status"], "done")


if __name__ == "__main__":
    unittest.main()
