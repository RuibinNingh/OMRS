"""独立网关接入：私有配置及真实合成HTTP，不使用生产凭据。"""
import importlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from omrs import vault_lifecycle as lifecycle
from omrs.zuoyebang import store


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-service-')
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name

    def config(self):
        name = 'omrs.zuoyebang.service_config'
        self.assertIsNotNone(importlib.util.find_spec(name), '独立网关私有配置尚未实现')
        return importlib.import_module(name)

    def test_private_config_roundtrip_preserves_blank_key_and_explicit_clear(self):
        config = self.config()
        initial = config.public(self.vault)
        self.assertEqual(initial['base_url'], 'http://127.0.0.1:8745')
        self.assertEqual(initial['mode'], 'local')
        self.assertFalse(initial['api_key_configured'])
        saved = config.save(self.vault, {'base_url': 'http://127.0.0.1:9876', 'api_key': 'synthetic-call-key'})
        self.assertTrue(saved['api_key_configured'])
        self.assertNotIn('synthetic-call-key', json.dumps(saved))
        snapshot = config.snapshot(self.vault)
        self.assertEqual(snapshot.api_key, 'synthetic-call-key')
        config.save(self.vault, {'api_key': ''})
        self.assertEqual(config.snapshot(self.vault).api_key, snapshot.api_key)
        path = store.root(self.vault) / 'service.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn('api_key', config.public(self.vault))
        config.save(self.vault, {'clear_api_key': True})
        self.assertFalse(config.public(self.vault)['api_key_configured'])
        self.assertEqual(config.snapshot(self.vault).api_key, '')

    def test_invalid_updates_leave_saved_config_unchanged(self):
        config = self.config()
        config.save(self.vault, {'api_key': 'synthetic-key'})
        path = store.root(self.vault) / 'service.json'
        before = path.read_bytes()
        invalid = [{'mode': 'direct'}, {'base_url': 'https://u:p@example.org'},
                   {'base_url': 'http://192.168.1.2:8745'}, {'api_key': 'bad\r\nheader'},
                   {'allow_private_targets': 'yes'}, {'unknown': 1}, {'revision': 'forged'},
                   {'clear_api_key': True, 'api_key': 'conflict'}, {'api_key': None}]
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(store.ZybError): config.save(self.vault, data)
                self.assertEqual(path.read_bytes(), before)

    def test_stale_config_and_vault_generation_cannot_publish(self):
        config = self.config()
        self.assertTrue(callable(getattr(config, 'assert_current', None)), '缺少配置发布屏障')
        old = config.snapshot(self.vault)
        config.save(self.vault, {'base_url': 'http://localhost:9876'})
        with self.assertRaises(store.ZybError) as caught: config.assert_current(self.vault, old)
        self.assertEqual(caught.exception.code, 'service_changed')
        old = config.snapshot(self.vault)
        with lifecycle.exclusive(self.vault): lifecycle.advance_generation(self.vault)
        with self.assertRaises(lifecycle.VaultChanged): config.assert_current(self.vault, old)

    def test_proxy_prefix_roundtrip_and_unsafe_paths_do_not_change_config(self):
        config = self.config()
        saved = config.save(self.vault, {'mode': 'external', 'base_url': 'https://example.org/zuoyebang/'})
        self.assertEqual(saved['panel_url'], 'https://example.org/zuoyebang/')
        snapshot = config.snapshot(self.vault)
        for path in ('/../admin', '/./admin', '/a//b', '/%2e%2e/admin', '/a%2fb', '/a;param'):
            with self.subTest(path=path), self.assertRaises(store.ZybError):
                config.save(self.vault, {'base_url': 'https://example.org' + path})
            self.assertEqual(config.snapshot(self.vault), snapshot)

    def test_corrupt_oversize_or_symlink_config_is_refused(self):
        config = self.config()
        path = store.root(self.vault) / 'service.json'
        for raw in ('{}' + ' ' * (17 * 1024), '{invalid', '{"mode":"direct"}'):
            path.write_text(raw)
            with self.subTest(raw=raw[:30]), self.assertRaises(store.ZybError): config.snapshot(self.vault)
        path.unlink()
        target = Path(self.vault, 'outside.json'); target.write_text('{}')
        path.symlink_to(target)
        with self.assertRaises(store.ZybError): config.save(self.vault, {'api_key': 'synthetic-key'})
        self.assertEqual(target.read_text(), '{}')


class GatewayTests(unittest.TestCase):
    def client_class(self):
        name = 'omrs.zuoyebang.gateway'
        self.assertIsNotNone(importlib.util.find_spec(name), '尚无独立网关客户端')
        return importlib.import_module(name).GatewayClient

    def test_local_and_explicit_private_external_send_original_bytes(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        from tests.zuoyebang_fixtures import png
        import base64
        Client = self.client_class()
        with SyntheticGateway() as gateway:
            for mode in ('local', 'external'):
                client = Client(ServiceSnapshot(mode=mode, base_url=gateway.url, api_key=KEY, allow_private_targets=mode == 'external'))
                self.assertTrue(client.status()['local_session_ready'])
                self.assertIn('data', client.search(png(), 12))
                call = gateway.calls[-1]
                self.assertEqual(base64.b64decode(call['body']['image_base64']), png())
                self.assertEqual(call['body']['grade'], 12)
                self.assertEqual(call['headers']['Authorization'], 'Bearer ' + KEY)
            self.assertEqual([call['path'] for call in gateway.calls], ['/api/v1/status', '/api/v1/search'] * 2)

    def test_strict_targets_reject_metadata_ambiguous_and_non_loopback_urls(self):
        from omrs.zuoyebang.targets import parse_target
        invalid = ['http://169.254.169.254', 'http://100.100.100.200', 'http://0.0.0.0',
                   'http://[::]', 'https://metadata.google.internal', 'http://224.0.0.1',
                   'https://example.org:0', 'https://u:p@example.org', 'https://example.org?q=1',
                   'https://example.org#', 'https://example.org/a/../api', 'http://127.1',
                   'http://2130706433', 'http://0x7f000001', 'http://127.0.0.1./',
                   'http://[::ffff:169.254.169.254]', 'https://example.org\\evil']
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(store.ZybError): parse_target('external', url, True)
        for url in ['http://192.168.1.1', 'https://example.org', 'http://localhost.evil']:
            with self.subTest(local=url), self.assertRaises(store.ZybError): parse_target('local', url)
        self.assertEqual(parse_target('local', 'http://[::1]:9876').port, 9876)

    def test_status_and_original_image_search_keep_reverse_proxy_prefix(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        from tests.zuoyebang_fixtures import png
        import base64
        with SyntheticGateway(prefix='/zuoyebang') as gateway:
            client = self.client_class()(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            self.assertTrue(client.status()['local_session_ready'])
            self.assertIn('data', client.search(png(), 12))
            self.assertEqual([call['path'] for call in gateway.calls],
                             ['/zuoyebang/api/v1/status', '/zuoyebang/api/v1/search'])
            self.assertEqual(base64.b64decode(gateway.calls[-1]['body']['image_base64']), png())

    def test_public_https_dns_mixed_or_private_addresses_rejected(self):
        from omrs.zuoyebang import targets
        self.assertTrue(callable(getattr(targets, 'resolve_target', None)), '缺少连接阶段IP核验')
        from unittest.mock import patch
        for addresses in [('127.0.0.1',), ('93.184.216.34', '10.0.0.1'), ('169.254.169.254',)]:
            rows = [(2, 1, 6, '', (ip, 443)) for ip in addresses]
            with self.subTest(addresses=addresses), patch('socket.getaddrinfo', return_value=rows), self.assertRaises(store.ZybError):
                targets.resolve_target('external', 'https://gateway.example.org', False, timeout=.3)
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]):
            result = targets.resolve_target('external', 'https://gateway.example.org', False, timeout=.3)
            self.assertEqual(result[1], ('93.184.216.34', 443))

    def test_dns_wait_has_a_deadline(self):
        from omrs.zuoyebang import targets
        self.assertTrue(callable(getattr(targets, 'resolve_target', None)), '缺少有界DNS解析')
        from unittest.mock import patch
        import time
        def slow(*_args, **_kwargs): time.sleep(.15); return []
        started = time.monotonic()
        with patch('socket.getaddrinfo', side_effect=slow), self.assertRaises(store.ZybError):
            targets.resolve_target('external', 'https://gateway.example.org', False, timeout=.03)
        self.assertLess(time.monotonic() - started, .12)
        time.sleep(.2)

    def test_fixed_ip_connection_does_not_repeat_dns_and_tls_uses_original_host(self):
        from unittest.mock import patch, MagicMock
        from omrs.zuoyebang.service_config import ServiceSnapshot
        Client = self.client_class()
        client = Client(ServiceSnapshot(mode='external', base_url='https://gateway.example.org', api_key='synthetic'))
        self.assertTrue(callable(getattr(client, '_connection', None)), '缺少固定IP连接')
        sock = MagicMock(); tls = MagicMock(); tls.wrap_socket.return_value = sock
        with patch('socket.socket', return_value=sock), patch('socket.getaddrinfo', side_effect=AssertionError('DNS重绑定')), patch('ssl.create_default_context', return_value=tls):
            connection = client._connection((2, ('93.184.216.34', 443)), .3)
            connection.connect()
            sock.connect.assert_called_once_with(('93.184.216.34', 443))
            tls.wrap_socket.assert_called_once_with(sock, server_hostname='gateway.example.org')
            connection.close()

    def test_tls_handshake_only_receives_remaining_connection_budget(self):
        from unittest.mock import patch, MagicMock
        from omrs.zuoyebang.service_config import ServiceSnapshot
        client = self.client_class()(ServiceSnapshot(mode='external', base_url='https://gateway.example.org', api_key='synthetic'))
        sock = MagicMock(); tls = MagicMock(); tls.wrap_socket.return_value = sock
        # TCP已耗时1.5秒时，TLS不能再拿到完整2秒，避免总等待超出预算。
        with patch('socket.socket', return_value=sock), patch('ssl.create_default_context', return_value=tls), patch('time.monotonic', side_effect=[10, 11.5]):
            connection = client._connection((2, ('93.184.216.34', 443)), 2)
            connection.connect()
            self.assertEqual(sock.settimeout.call_args.args[0], .5)
            connection.close()

    def test_tls_is_not_started_after_tcp_exhausts_connection_budget(self):
        from unittest.mock import patch, MagicMock
        from omrs.zuoyebang.service_config import ServiceSnapshot
        client = self.client_class()(ServiceSnapshot(mode='external', base_url='https://gateway.example.org', api_key='synthetic'))
        sock = MagicMock(); tls = MagicMock()
        with patch('socket.socket', return_value=sock), patch('ssl.create_default_context', return_value=tls), patch('time.monotonic', side_effect=[10, 12.1]):
            connection = client._connection((2, ('93.184.216.34', 443)), 2)
            with self.assertRaises(TimeoutError): connection.connect()
            tls.wrap_socket.assert_not_called()
            sock.close.assert_called_once()

    def test_invalid_key_redirect_and_protocol_errors_are_sanitized(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        Client = self.client_class()
        with SyntheticGateway() as gateway:
            client = Client(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            for status, body, headers, expected in [
                    (401, {'status': 'error', 'code': 'invalid_key', 'msg': KEY}, {}, 'gateway_key'),
                    (403, {'status': 'error', 'msg': KEY}, {}, 'gateway_forbidden'),
                    (302, b'', {'Location': 'http://169.254.169.254/?key=' + KEY}, 'gateway_redirect'),
                    (200, b'not-json ' + KEY.encode(), {}, 'gateway_protocol'),
                    (200, {'status': 'ok', 'account': {'secret': KEY}}, {}, 'gateway_protocol')]:
                gateway.responses['/api/v1/status'] = status, body, headers
                with self.subTest(status=status, expected=expected), self.assertRaises(store.ZybError) as caught: client.status()
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn(KEY, str(caught.exception))
            self.assertEqual(len(gateway.calls), 5)

    def test_bounded_response_timeout_and_no_proxy(self):
        from unittest.mock import patch
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        Client = self.client_class()
        with SyntheticGateway() as gateway, patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'HTTPS_PROXY': 'http://127.0.0.1:1', 'ALL_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            client = Client(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            self.assertTrue(client.status()['local_session_ready'])
            gateway.responses['/api/v1/status'] = 200, b'x' * 100, {}
            with self.assertRaises(store.ZybError) as caught: client.request('GET', '/api/v1/status', limit=16)
            self.assertEqual(caught.exception.code, 'gateway_budget')
            gateway.responses.clear()
            import time
            gateway.before = lambda _path: time.sleep(.15)
            with self.assertRaises(store.ZybError) as caught: client.request('GET', '/api/v1/status', timeout=.03)
            self.assertEqual(caught.exception.code, 'gateway_network')

    def test_search_accepts_gateway_response_up_to_shared_24_mib_budget(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        from tests.zuoyebang_fixtures import png
        with SyntheticGateway() as gateway:
            client = self.client_class()(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            # 网关允许24MiB，合法16MiB以上响应不能在OMRS中被更小预算拒绝。
            text = 'x' * (16 * 1024 * 1024)
            gateway.responses['/api/v1/search'] = 200, {'status': 'ok', 'result': {'content': text}}, {}
            self.assertEqual(client.search(png())['content'], text)
            gateway.responses['/api/v1/search'] = 200, b'', {'Content-Length': 24 * 1024 * 1024 + 1}
            with self.assertRaises(store.ZybError) as caught: client.search(png())
            self.assertEqual(caught.exception.code, 'gateway_budget')

    def test_unframed_keepalive_deadline_eof_cannot_be_accepted_as_success(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        import time
        with SyntheticGateway(framing='keep-open') as gateway:
            client = self.client_class()(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            started = time.monotonic()
            with self.assertRaises(store.ZybError) as caught:
                client.request('GET', '/api/v1/status', timeout=.08)
            self.assertEqual(caught.exception.code, 'gateway_network')
            self.assertNotIn(KEY, str(caught.exception))
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(len(gateway.calls), 1)

    def test_unframed_response_with_normal_server_eof_is_accepted(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        with SyntheticGateway(framing='close') as gateway:
            client = self.client_class()(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            self.assertTrue(client.status()['local_session_ready'])
            self.assertEqual(len(gateway.calls), 1)

    def test_missing_key_and_invalid_search_are_refused_without_http(self):
        from omrs.zuoyebang.service_config import ServiceSnapshot
        from tests.zuoyebang_gateway import SyntheticGateway, KEY
        from tests.zuoyebang_fixtures import png
        Client = self.client_class()
        with SyntheticGateway() as gateway:
            with self.assertRaises(store.ZybError): Client(ServiceSnapshot(base_url=gateway.url)).status()
            client = Client(ServiceSnapshot(base_url=gateway.url, api_key=KEY))
            for grade in (True, -1, 13, '1'):
                with self.subTest(grade=grade), self.assertRaises(store.ZybError): client.search(png(), grade)
            self.assertEqual(gateway.calls, [])
