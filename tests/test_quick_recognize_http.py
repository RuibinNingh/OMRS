"""快速录入 HTTP 边界：恶意识别字段不会变成标记，旧页码请求只给弃用提示。"""
import http.client
import http.server
import json
import tempfile
import threading
import unittest
from unittest import mock

from omrs import server


class QuickRecognizeHttpTests(unittest.TestCase):
    def test_quick_response_filters_labels_and_create_ignores_legacy_page(self):
        with tempfile.TemporaryDirectory() as vault:
            class Handler(server.OMRSHandler):
                vault_path = vault

                def log_message(self, *_args):
                    pass

            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()

            def post(path, body):
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                try:
                    conn.request("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    conn.close()

            try:
                fake = {"mode": "classify", "subject": "数学", "category": "函数", "difficulty": 5,
                        "knowledge_tags": [], "labels": ["恶意标记"], "raw": "模型原文"}
                with mock.patch.object(server, "recognize_question", return_value=fake) as recognize:
                    status, result = post("/api/ai-recognize", {
                        "scope": "quick", "mode": "classify", "question_image": "data:image/png;base64,AA=="})
                self.assertEqual(status, 200, result)
                self.assertNotIn("labels", result)
                self.assertNotIn("raw", result)
                self.assertFalse(recognize.call_args.kwargs["allow_labels"])

                status, created = post("/api/create", {"subject": "数学", "category": "函数", "note": "p.23"})
                self.assertEqual(status, 200, created)
                self.assertEqual(created["deprecated_fields"], ["note"])
                with open(f"{vault}/{created['file_path']}", encoding="utf-8") as file:
                    self.assertNotIn("页码:", file.read())
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                httpd.server_close()
