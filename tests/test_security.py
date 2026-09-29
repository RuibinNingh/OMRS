import http.client
import base64
import json
import os
import socketserver
import tempfile
import threading
import unittest
from unittest import mock

from omrs import security
from omrs.common import load_config, save_config
from omrs.path_safety import safe_question_directory, safe_question_path
from omrs.reports import create_report, signed_report_images
from omrs.server import OMRSHandler


class QuietHandler(OMRSHandler):
    def log_message(self, *_args):
        pass


class SecurityTests(unittest.TestCase):
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

    def remote_headers(self, **extra):
        return {"Host": "omrs.example", "X-Real-IP": "192.0.2.15",
                "X-Forwarded-Proto": "https", **extra}

    def test_ai_thinking_config_requires_boolean_and_persists(self):
        self.assertFalse(json.loads(self.request("GET", "/api/config")[2])["ai_thinking"])
        headers = {"Content-Type": "application/json"}
        invalid = self.request("POST", "/api/config", headers, '{"ai_thinking":"false"}')
        self.assertEqual(invalid[0], 400)
        self.assertFalse(load_config(self.vault)["ai_thinking"])
        saved = self.request("POST", "/api/config", headers, '{"ai_thinking":true}')
        self.assertEqual(saved[0], 200)
        self.assertTrue(json.loads(self.request("GET", "/api/config")[2])["ai_thinking"])

    def test_local_bypass_remote_login_proxy_and_config_secret(self):
        save_config(self.vault, {"ai_api_key": "secret"})
        local = self.request("GET", "/api/config")
        self.assertEqual(local[0], 200)
        self.assertNotIn(b"secret", local[2])
        self.assertTrue(json.loads(local[2])["ai_api_key_configured"])

        self.assertEqual(self.request("GET", "/api/config", self.remote_headers())[0], 401)
        self.assertEqual(self.request("GET", "/api/config", {
            "Host": "127.0.0.1", "X-Forwarded-Proto": "https"})[0], 401)
        self.assertEqual(self.request("GET", "/api/source/export", self.remote_headers())[0], 401)
        self.assertEqual(self.request("GET", "/m", self.remote_headers())[0], 302)
        self.assertEqual(self.request("GET", "/api/scan")[0], 405)
        security.set_pin(self.vault, "12345678")
        body = json.dumps({"pin": "12345678"})
        status, headers, _ = self.request("POST", "/api/auth/login", self.remote_headers(
            Origin="https://omrs.example", **{"Content-Type": "application/json"}), body)
        self.assertEqual(status, 200)
        self.assertIn("Secure", headers["Set-Cookie"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        remote = self.request("GET", "/api/config", self.remote_headers(Cookie=cookie))
        self.assertEqual(remote[0], 200)
        self.assertNotIn(b"secret", remote[2])
        self.assertEqual(self.request("GET", "/api/status", self.remote_headers())[0], 401)
        self.assertEqual(self.request("GET", "/api/status", self.remote_headers(Cookie=cookie))[0], 200)
        self.assertEqual(self.request("GET", "/m", self.remote_headers(Cookie=cookie))[0], 200)

        before = load_config(self.vault)
        denied = self.request("POST", "/api/config", self.remote_headers(
            Cookie=cookie, Origin="https://evil.example", **{"Content-Type": "text/plain"}),
            '{"allow_external":true}')
        self.assertEqual(denied[0], 403)
        self.assertEqual(load_config(self.vault), before)

    def test_path_components_and_symlink(self):
        for subject, category in (("../outside", "x"), ("x", "/tmp/outside"), ("x", ".."),
                                  ("x\\y", "z")):
            with self.assertRaises(ValueError):
                safe_question_directory(self.vault, subject, category)
        target, _, _ = safe_question_directory(self.vault, "数学", "函数")
        self.assertTrue(target.endswith("数学/函数"))
        os.symlink(self.temp.name, os.path.join(self.vault, "错题", "link"))
        with self.assertRaises(ValueError):
            safe_question_path(self.vault, os.path.join(self.vault, "错题", "link", "x.md"))

    def test_explicit_direct_lan_exemption(self):
        self.assertEqual(self.request("POST", "/api/config", body='{"allow_external":true}')[0], 400)
        data = '{"allow_external":true,"lan_pin_exempt_cidrs":["192.168.0.0/24"]}'
        self.assertEqual(self.request("POST", "/api/config", body=data)[0], 200)
        self.assertEqual(load_config(self.vault)["lan_pin_exempt_cidrs"], ["192.168.0.0/24"])
        self.assertTrue(security.direct_lan_exempt(self.vault, "192.168.0.42"))
        self.assertFalse(security.direct_lan_exempt(self.vault, "192.168.1.42"))
        self.assertFalse(security.direct_lan_exempt(self.vault, "192.168.0.42", proxy_headers_present=True))
        self.assertEqual(self.request("GET", "/api/config", self.remote_headers())[0], 401)
        self.assertEqual(self.request("POST", "/api/config", body='{"lan_pin_exempt_cidrs":[]}')[0], 400)
        for cidr in ("0.0.0.0/0", "8.8.8.0/24", "192.168.0.1/24"):
            with self.assertRaises(ValueError):
                security.normalize_lan_cidrs([cidr])

    def test_report_sandbox_and_image_grant(self):
        security.set_pin(self.vault, "12345678")
        attachments = os.path.join(self.vault, "错题", "附件")
        os.makedirs(attachments)
        with open(os.path.join(attachments, "a.gif"), "wb") as file:
            file.write(base64.b64decode("R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="))
        _, headers, _ = self.request("POST", "/api/auth/login", self.remote_headers(
            Origin="https://omrs.example", **{"Content-Type": "application/json"}),
            '{"pin":"12345678"}')
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        report = create_report(self.vault, "fixture", '<!doctype html><script>window.ok=1</script><img src="/api/image?name=a.gif">')
        code, headers, body = self.request("GET", "/api/report/view?id=" + report["id"], self.remote_headers(Cookie=cookie))
        self.assertEqual(code, 200)
        self.assertIn("sandbox allow-scripts", headers["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", headers["Content-Security-Policy"])
        self.assertIn(b"window.ok=1", body)
        self.assertIn(b"grant_signature=", body)
        from html import unescape
        import re
        signed_url = unescape(re.search(rb'src="([^"]+)"', body).group(1).decode())
        image_status, image_headers, _ = self.request("GET", signed_url, self.remote_headers())
        self.assertEqual(image_status, 200)
        self.assertEqual(image_headers["Cache-Control"], "no-store")
        token = cookie.split("=", 1)[1]
        session = security.session_for(self.vault, token)
        grant = security.sign_image(session, "a.gif")
        self.assertTrue(security.valid_image_grant(self.vault, "a.gif", *grant))
        security.logout(token)
        self.assertFalse(security.valid_image_grant(self.vault, "a.gif", *grant))
        self.assertEqual(self.request("GET", signed_url, self.remote_headers())[0], 401)

    def test_expiry_and_failed_pin_limit(self):
        security.set_pin(self.vault, "12345678")
        for _ in range(5):
            with self.assertRaisesRegex(ValueError, "PIN 错误"):
                security.login(self.vault, "00000000", "192.0.2.240")
        with self.assertRaisesRegex(ValueError, "尝试次数过多"):
            security.login(self.vault, "12345678", "192.0.2.240")
        token, session = security.login(self.vault, "12345678", "192.0.2.241")
        self.assertIsNotNone(security.session_for(self.vault, token))
        session["last_activity"] -= 31 * 60
        self.assertIsNone(security.session_for(self.vault, token))
        token, session = security.login(self.vault, "12345678", "192.0.2.241")
        session["issued"] -= security.ABSOLUTE_SECONDS + 1
        self.assertIsNone(security.session_for(self.vault, token))

    def test_four_digit_pin_boundary_and_login(self):
        for pin in ("123", "1234567890123", "１２３４", "12a4"):
            with self.assertRaisesRegex(ValueError, "4 到 12 位"):
                security.set_pin(self.vault, pin)
        security.set_pin(self.vault, "1234")
        self.assertTrue(security.verify_pin(self.vault, "1234"))
        status, _, _ = self.request("POST", "/api/auth/login", self.remote_headers(
            Origin="https://omrs.example", **{"Content-Type": "application/json"}),
            '{"pin":"1234"}')
        self.assertEqual(status, 200)
        security.set_pin(self.vault, "123456789012")
        self.assertTrue(security.verify_pin(self.vault, "123456789012"))

    def post_json(self, path, payload, headers):
        return self.request("POST", path, {"Content-Type": "application/json", **headers},
                            json.dumps(payload))

    def remote_login(self, pin, ip):
        status, headers, _ = self.post_json("/api/auth/login", {"pin": pin}, self.remote_headers(
            Origin="https://omrs.example", **{"X-Real-IP": ip}))
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_lan_exempt_device_can_set_first_pin_without_current_pin(self):
        lan = {"Host": "omrs.example", "Origin": "http://omrs.example"}
        with mock.patch.object(security, "direct_lan_exempt", return_value=True):
            status, _, body = self.post_json("/api/auth/pin", {"pin": "2468", "idle_minutes": 30}, lan)
            self.assertEqual(status, 200, body)
            self.assertTrue(security.auth_summary(self.vault)["pin_configured"])
            status, _, body = self.post_json("/api/auth/pin", {"pin": "1357", "idle_minutes": 30}, lan)
            self.assertEqual(status, 400)
            self.assertIn("当前 PIN 错误", json.loads(body)["msg"])
        self.assertTrue(security.verify_pin(self.vault, "2468"))

    def test_idle_minutes_change_keeps_sessions_and_applies_immediately(self):
        security.set_pin(self.vault, "12345678", 60)
        token, session = security.login(self.vault, "12345678", "192.0.2.60")
        security.set_idle_minutes(self.vault, 30)
        self.assertIsNotNone(security.session_for(self.vault, token))
        session["last_activity"] -= 31 * 60
        self.assertIsNone(security.session_for(self.vault, token))

    def test_current_pin_check_shares_failed_attempt_limit(self):
        security._FAILURES.clear()
        security.set_pin(self.vault, "12345678")
        ip = "192.0.2.77"
        cookie = self.remote_login("12345678", ip)
        headers = self.remote_headers(Cookie=cookie, Origin="https://omrs.example", **{"X-Real-IP": ip})
        for _ in range(5):
            status, _, body = self.post_json("/api/auth/pin", {"current_pin": "0000", "idle_minutes": 30}, headers)
            self.assertEqual(status, 400)
            self.assertIn("当前 PIN 错误", json.loads(body)["msg"])
        status, _, body = self.post_json("/api/auth/pin", {"current_pin": "12345678", "idle_minutes": 30}, headers)
        self.assertEqual(status, 400)
        self.assertIn("尝试次数过多", json.loads(body)["msg"])
        security._FAILURES.clear()

    def test_login_page_only_redirects_to_same_origin(self):
        _, _, page = self.request("GET", "/login")
        text = page.decode("utf-8")
        self.assertIn("new URL(", text)
        self.assertIn("origin===location.origin", text)
        self.assertNotIn("startsWith('//')", text)


if __name__ == "__main__":
    unittest.main()
