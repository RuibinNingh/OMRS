"""独立网关v1调用；固定IP、TLS原域、无代理/重定向/自动重试及有界网络。"""
import base64
import http.client
import json
import math
import socket
import ssl
import threading
import time
from .targets import parse_target, resolve_target
from .store import ZybError
from .validation import validate_image

_SLOTS = threading.BoundedSemaphore(4)
MAX_RESPONSE = 24 * 1024 * 1024


def account_summary(value):
    """只投影既有会话脱敏契约，不信任网关额外字段或错误原文。"""
    if not isinstance(value, dict) or any(type(value.get(name)) is not bool for name in ('local_session_ready', 'has_account_credential')):
        raise ZybError('服务状态响应不符合协议', 'gateway_protocol', 502)
    observations = value.get('observations')
    if not isinstance(observations, dict) or not isinstance(observations.get('events', []), list):
        raise ZybError('服务状态响应不符合协议', 'gateway_protocol', 502)
    clean = {'account': {}, 'signing': {}, 'events': []}
    times = ('last_success_at', 'first_invalid_at', 'valid_until_after', 'imported_at')
    for name in ('account', 'signing'):
        part = observations.get(name, {})
        if not isinstance(part, dict):
            raise ZybError('服务状态响应不符合协议', 'gateway_protocol', 502)
        if part.get('state') in ('valid', 'invalid', 'unknown'):
            clean[name]['state'] = part['state']
        for key in times:
            if type(part.get(key)) in (int, float) and math.isfinite(part[key]):
                clean[name][key] = part[key]
    for event in observations.get('events', [])[-100:]:
        if not isinstance(event, dict) or event.get('event') not in ('profile_import', 'login', 'refresh', 'verify', 'search', 'qr_start', 'qr_cancel'):
            continue
        if event.get('kind') not in ('ok', 'login_required', 'signing_session', 'network', 'protocol', 'upstream'):
            continue
        if type(event.get('at')) not in (int, float) or not math.isfinite(event['at']):
            continue
        row = {key: event[key] for key in ('event', 'kind', 'at')}
        if type(event.get('code')) is int:
            row['code'] = event['code']
        for key in ('account_recovered', 'signing_recovered'):
            if type(event.get(key)) is bool: row[key] = event[key]
        clean['events'].append(row)
    return {'local_session_ready': value['local_session_ready'], 'has_account_credential': value['has_account_credential'], 'observations': clean}


class GatewayClient:
    def __init__(self, config):
        self.config = config
        self.target = parse_target(config.mode, config.base_url, config.allow_private_targets)

    def _connection(self, address, timeout):
        target = self.target
        class PinnedConnection(http.client.HTTPConnection):
            def connect(self):
                deadline = time.monotonic() + timeout
                family, destination = address
                sock = socket.socket(family, socket.SOCK_STREAM)
                try:
                    sock.settimeout(timeout)
                    sock.connect(destination)
                    context = ssl.create_default_context() if target.scheme == 'https' else None
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    # TCP与TLS共用剩余预算，握手不能重新获得完整连接超时。
                    sock.settimeout(remaining)
                    if target.scheme == 'https':
                        sock = context.wrap_socket(sock, server_hostname=target.hostname)
                    self.sock = sock
                except BaseException:
                    sock.close()
                    raise
        return PinnedConnection(target.hostname, target.port or (443 if target.scheme == 'https' else 80), timeout=timeout)

    def request(self, method, path, payload=None, *, timeout=15, limit=MAX_RESPONSE):
        if not self.config.api_key:
            raise ZybError('请在作业帮服务设置中配置调用密钥', 'gateway_unconfigured', 503)
        if not _SLOTS.acquire(blocking=False):
            raise ZybError('作业帮服务请求繁忙，请稍后重试', 'gateway_busy', 429)
        connection = timer = None
        deadline = time.monotonic() + min(max(timeout, .001), 45)
        timed_out = threading.Event()
        try:
            address = resolve_target(self.config.mode, self.config.base_url, self.config.allow_private_targets,
                                     timeout=min(3, deadline - time.monotonic()))
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError()
            connection = self._connection(address, remaining)
            connection.connect()
            # 整体截止也约束慢速响应头/分块传输，不能用每次read重置无限延长。
            sock = connection.sock
            def abort():
                timed_out.set()
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            timer = threading.Timer(max(.001, deadline - time.monotonic()), abort)
            timer.daemon = True; timer.start()
            body = json.dumps(payload, separators=(',', ':')).encode() if payload is not None else None
            connection.request(method, self.target.path.rstrip('/') + path, body, {'Authorization': 'Bearer ' + self.config.api_key,
                               'Content-Type': 'application/json', 'Accept': 'application/json', 'Connection': 'close'})
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise ZybError('服务重定向被拒绝，请直接填写服务地址', 'gateway_redirect', 502)
            if response.status != 200:
                failures = {401: ('服务调用密钥无效或已吊销', 'gateway_key'),
                            403: ('服务拒绝访问，请检查网关外部访问开关', 'gateway_forbidden'),
                            429: ('服务请求受限，请稍后重试', 'gateway_busy'),
                            503: ('服务尚未配置或依赖缺失', 'gateway_unavailable')}
                message, code = failures.get(response.status, ('作业帮服务请求失败', 'gateway_upstream'))
                raise ZybError(message, code, 429 if response.status == 429 else 502)
            limit = max(1, min(limit, MAX_RESPONSE))
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdecimal() or int(length) > limit):
                raise ZybError('服务响应超过读取预算', 'gateway_budget', 502)
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise ZybError('服务响应编码不符合协议', 'gateway_protocol', 502)
            data = bytearray()
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError()
                sock.settimeout(remaining)
                chunk = response.read1(min(65536, limit + 1 - len(data)))
                if not chunk: break
                data.extend(chunk)
                if len(data) > limit:
                    raise ZybError('服务响应超过读取预算', 'gateway_budget', 502)
            # 截止触发的本地shutdown也会产生EOF，不能把它当作服务器正常结束。
            if timed_out.is_set() or time.monotonic() >= deadline:
                raise TimeoutError()
            if length is not None and len(data) != int(length):
                raise ZybError('服务响应不完整', 'gateway_protocol', 502)
            result = json.loads(data)
            if not isinstance(result, dict) or result.get('status') != 'ok':
                raise ZybError('服务响应不符合协议', 'gateway_protocol', 502)
            if timed_out.is_set() or time.monotonic() >= deadline:
                raise TimeoutError()
            return result
        except ZybError:
            raise
        except (OSError, http.client.HTTPException):
            raise ZybError('无法连接作业帮服务或网络超时；账号有效期未改变', 'gateway_network', 502) from None
        except (ValueError, TypeError, RecursionError):
            raise ZybError('服务响应不符合协议', 'gateway_protocol', 502) from None
        finally:
            if timer: timer.cancel()
            if connection: connection.close()
            _SLOTS.release()

    def status(self):
        return account_summary(self.request('GET', '/api/v1/status', timeout=10, limit=128 * 1024).get('account'))

    def search(self, image, grade=0):
        validate_image(image)
        if type(grade) is not int or not 0 <= grade <= 12:
            raise ZybError('年级参数不合法')
        result = self.request('POST', '/api/v1/search', {'image_base64': base64.b64encode(image).decode('ascii'), 'grade': grade}, timeout=45)
        if not isinstance(result.get('result'), (dict, list)):
            raise ZybError('服务搜题结果不符合协议', 'gateway_protocol', 502)
        return result['result']
