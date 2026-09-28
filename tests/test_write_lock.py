"""A2 / A3：进程级写锁、503、豁免清单，以及 ThreadingMixIn 下慢连接不阻塞其他请求。"""
import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs import locking  # noqa: E402
from omrs.cli import OMRSTCPServer  # noqa: E402
from omrs.creation import create_question  # noqa: E402
from omrs.server import OMRSHandler  # noqa: E402


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = tempfile.mkdtemp(prefix="omrs-wl-")
        os.makedirs(os.path.join(cls.vault, "错题"))
        create_question(cls.vault, "数学", "函数", 5, question_text="求 $f(x)=x^2$ 的最小值")
        handler = type("H", (OMRSHandler,), {"vault_path": cls.vault})
        cls.server = OMRSTCPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.vault, ignore_errors=True)

    def request(self, method, path, body=None, timeout=10):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        data = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=data, headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}"})
        resp = conn.getresponse()
        payload = json.loads(resp.read().decode() or "{}")
        conn.close()
        return resp.status, payload


class WriteLockTest(ServerCase):
    def test_locked_post_returns_503_and_get_still_works(self):
        old = locking.DEFAULT_TIMEOUT
        locking.DEFAULT_TIMEOUT = 0.4
        held, release = threading.Event(), threading.Event()

        def hold():
            with locking.write_lock():
                held.set()
                release.wait(10)
        t = threading.Thread(target=hold)
        t.start()
        try:
            held.wait(5)
            status, payload = self.request("POST", "/api/label/save", {"name": "x", "color": "#2563eb"})
            self.assertEqual(status, 503)
            self.assertIn("写入繁忙", payload["msg"])
            status, _ = self.request("GET", "/api/stats")
            self.assertEqual(status, 200)
            status, _ = self.request("GET", "/api/agent/status")
            self.assertEqual(status, 200)
        finally:
            release.set()
            t.join()
            locking.DEFAULT_TIMEOUT = old
        status, _ = self.request("POST", "/api/label/save", {"name": "x", "color": "#2563eb"})
        self.assertEqual(status, 200)

    def test_lock_is_reentrant_and_exempt_list_is_explicit(self):
        with locking.write_lock():
            with locking.write_lock():
                self.assertTrue(locking.held_by_current_thread())
        self.assertFalse(locking.held_by_current_thread())
        self.assertTrue(locking.post_exempt("/api/auth/login"))
        self.assertTrue(locking.post_exempt("/api/ai-recognize"))
        self.assertFalse(locking.post_exempt("/api/feedback"))
        self.assertFalse(locking.post_exempt("/api/agent/run/revert"))
        for reason in locking.POST_LOCK_EXEMPT.values():
            self.assertTrue(reason)


class ThreadedServerTest(ServerCase):
    def test_slow_client_does_not_block_others(self):
        slow = socket.create_connection(("127.0.0.1", self.port))
        slow.sendall(b"GET /api/stats HTTP/1.1\r\nHost: x\r\n")  # 故意不发完请求头
        try:
            started = time.monotonic()
            status, _ = self.request("GET", "/api/stats", timeout=5)
            self.assertEqual(status, 200)
            self.assertLess(time.monotonic() - started, 3)
        finally:
            slow.close()

    def test_concurrent_writes_serialize(self):
        results = []

        def post(i):
            results.append(self.request("POST", "/api/label/save", {"name": f"L{i}", "color": "#2563eb"})[0])
        threads = [threading.Thread(target=post, args=(i,)) for i in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results, [200] * 6)
        status, payload = self.request("GET", "/api/ledger/verify")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("valid", payload.get("ledger", {}).get("valid", True)))


if __name__ == "__main__":
    unittest.main()
