"""MCP 原图 URL 下载回归；保留真实 HTTPS 连接与 HTTP 解析。

只替换 DNS、底层 socket 和 TLS I/O，不替换 _download 或连接类。
固定 HTTP 图片是测试夹具，不访问公网、生产服务或真实题库。
"""
import asyncio
import hashlib
import io
from pathlib import Path
import socket
import ssl
import struct
import tempfile
import unittest
import zlib
from contextlib import contextmanager
from unittest.mock import Mock, patch

try:
    from omrs.mcp import server as mcp_server
except ImportError:
    mcp_server = None


def _png(width=16, height=12):
    pixels = b"".join(b"\x00" + b"\x00\xff\x00" * width for _ in range(height))
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


@contextmanager
def image_network(raw):
    """让真实 HTTPSConnection 从底层受控流读取完整 HTTP 响应。"""
    assert mcp_server is not None
    public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    tcp = Mock()
    tls = Mock()
    tls.makefile.side_effect = lambda *args, **kwargs: io.BytesIO(
        b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: "
        + str(len(raw)).encode() + b"\r\nConnection: close\r\n\r\n" + raw)
    context = Mock()
    context.wrap_socket.return_value = tls
    with patch.object(mcp_server.socket, "getaddrinfo", return_value=public_dns), \
            patch.object(mcp_server.socket, "create_connection", return_value=tcp) as connect, \
            patch.object(mcp_server.ssl, "create_default_context", return_value=context):
        yield connect, context, tcp


@unittest.skipUnless(mcp_server, "可选 MCP SDK 未安装")
class MCPDownloadConnectionTests(unittest.TestCase):
    def test_https_download_uses_pinned_ip_with_hostname_sni(self):
        assert mcp_server is not None
        raw = _png(16, 12)
        with image_network(raw) as (connect, context, tcp):
            self.assertEqual(mcp_server._download("https://fixture.example/original.png"), raw)
            connect.assert_called_once_with(("93.184.216.34", 443), 10)
            context.wrap_socket.assert_called_once_with(tcp, server_hostname="fixture.example")

    def test_default_tls_context_requires_hostname_and_certificate_verification(self):
        assert mcp_server is not None
        connection = mcp_server._PinnedHTTPSConnection("fixture.example", "93.184.216.34", 10)
        context = getattr(connection, "_context")
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        connection.close()

    def test_tls_certificate_failure_rejects_download(self):
        assert mcp_server is not None
        with image_network(_png()) as (_, context, _):
            context.wrap_socket.side_effect = ssl.SSLCertVerificationError("fixture certificate rejected")
            with self.assertRaises(ssl.SSLCertVerificationError):
                mcp_server._download("https://fixture.example/original.png")

    def test_url_file_creates_draft_with_unchanged_original_bytes(self):
        assert mcp_server is not None
        from mcp.server.auth.provider import AccessToken
        from omrs import drafts
        from omrs.mcp.keys import create_key

        raw = _png()
        with tempfile.TemporaryDirectory(prefix="omrs-mcp-url-image-") as vault:
            key = create_key(vault, "隔离下载回归", ["omrs:read", "draft:create"])
            token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=key["scopes"])
            server = mcp_server.build_server(vault)
            payload = {
                "subject": "物理", "category": "运动学", "request_id": "original-url-image",
                "blocks": [{"section": "题目", "kind": "image", "image": 0}],
                "images": [{"download_url": "https://fixture.example/original.png", "file_id": "fixture-file"}],
            }
            with patch.object(mcp_server, "get_access_token", return_value=token), image_network(raw):
                asyncio.run(server.call_tool("create_draft", payload))
            rows = drafts.list_drafts(vault, readonly=True)
            self.assertEqual(len(rows), 1)
            draft = drafts.get_draft(vault, rows[0]["id"], readonly=True)
            self.assertEqual(draft["status"], "review")
            self.assertEqual(len(draft["source_images"]), 1)
            block = draft["blocks"][0]
            self.assertEqual(block["box_origin"], "original")
            self.assertEqual(block["box"], {"x": 0, "y": 0, "w": 1, "h": 1})
            sha = hashlib.sha256(raw).hexdigest()
            self.assertEqual(block["image_sha"], sha)
            saved = Path(vault) / "错题/.omrs/drafts/images" / (sha + ".png")
            self.assertEqual(saved.read_bytes(), raw)

    def test_failed_url_download_does_not_create_a_draft(self):
        assert mcp_server is not None
        from mcp.server.auth.provider import AccessToken
        from mcp.server.fastmcp.exceptions import ToolError
        from omrs import drafts
        from omrs.mcp.keys import create_key

        with tempfile.TemporaryDirectory(prefix="omrs-mcp-url-failure-") as vault:
            key = create_key(vault, "隔离下载失败回归", ["draft:create"])
            token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=key["scopes"])
            server = mcp_server.build_server(vault)
            payload = {
                "subject": "物理", "category": "运动学", "request_id": "failed-original-url",
                "blocks": [{"section": "题目", "kind": "image", "image": 0}],
                "images": [{"download_url": "https://fixture.example/original.png"}],
            }
            with patch.object(mcp_server, "get_access_token", return_value=token), image_network(_png()) as (_, context, _):
                context.wrap_socket.side_effect = ssl.SSLCertVerificationError("fixture certificate rejected")
                with self.assertRaises(ToolError):
                    asyncio.run(server.call_tool("create_draft", payload))
            self.assertEqual(drafts.list_drafts(vault, readonly=True), [])


if __name__ == "__main__":
    unittest.main()
