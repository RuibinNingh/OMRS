import json
import os
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request

from omrs.cli import OMRSTCPServer
from omrs.server import OMRSHandler

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NoopHandler(socketserver.BaseRequestHandler):
    def handle(self):
        pass


class RestartLifecycleTests(unittest.TestCase):
    def test_listener_enables_so_reuseaddr_before_bind(self):
        with OMRSTCPServer(("127.0.0.1", 0), NoopHandler) as server:
            self.assertEqual(
                server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR),
                1,
            )


class InstanceIdEndpointTests(unittest.TestCase):
    """GET /api/auth/session carries a per-process generation id for restart probing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self._tmp.name, "错题"))
        self._old_vault = OMRSHandler.vault_path
        OMRSHandler.vault_path = self._tmp.name
        self.server = OMRSTCPServer(("127.0.0.1", 0), OMRSHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        OMRSHandler.vault_path = self._old_vault
        self._tmp.cleanup()

    def _session_state(self):
        with urllib.request.urlopen(self.base + "/api/auth/session", timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def test_instance_id_is_present_and_stable_within_one_process(self):
        first = self._session_state()
        second = self._session_state()
        self.assertIsInstance(first.get("instance_id"), str)
        self.assertTrue(first["instance_id"])
        self.assertEqual(first["instance_id"], second["instance_id"])

    def test_session_state_exposes_no_auth_secrets(self):
        state = self._session_state()
        for forbidden in ("pin", "pin_hash", "salt", "token", "session_token"):
            self.assertNotIn(forbidden, state)

    def test_status_reports_actual_listen_scope(self):
        with urllib.request.urlopen(self.base + "/api/status", timeout=5) as response:
            state = json.loads(response.read().decode("utf-8"))
        self.assertIs(state.get("listen_external"), False)

    def test_instance_id_differs_between_processes(self):
        probe = "from omrs.server import OMRS_INSTANCE_ID; print(OMRS_INSTANCE_ID)"
        ids = [
            subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, check=True,
                           capture_output=True, text=True, timeout=30).stdout.strip()
            for _ in range(2)
        ]
        self.assertTrue(all(ids))
        self.assertNotEqual(ids[0], ids[1])


if __name__ == "__main__":
    unittest.main()
