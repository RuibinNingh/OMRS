"""作业帮网关目标策略；严格URL、有界DNS与连接阶段地址核验。"""
import ipaddress
import queue
import re
import socket
import threading
from urllib.parse import urlsplit
from .store import ZybError

_DNS_SLOTS = threading.BoundedSemaphore(4)
_PRIVATE = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7'))
_METADATA = {'metadata.google.internal', 'metadata.goog', 'instance-data', 'instance-data.ec2.internal'}


def check_ip(address, mode, scheme, allow_private):
    ip = ipaddress.ip_address(address)
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast or (ip.is_reserved and not ip.is_loopback) or getattr(ip, 'ipv4_mapped', None):
        raise ZybError('服务目标地址不安全', 'service_target')
    trusted = ip.is_loopback or any(ip.version == net.version and ip in net for net in _PRIVATE)
    if mode == 'local':
        allowed = ip.is_loopback
    else:
        allowed = (ip.is_global and scheme == 'https') or (trusted and allow_private)
    if not allowed:
        raise ZybError('服务目标不属于允许的公网HTTPS或显式可信内网', 'service_target')
    return ip


def parse_target(mode, base_url, allow_private_targets=False):
    if mode not in ('local', 'external') or type(allow_private_targets) is not bool:
        raise ZybError('作业帮服务模式或可信内网开关不合法', 'service_config')
    if not isinstance(base_url, str) or not base_url or len(base_url) > 2048 or any(
            c.isspace() or ord(c) < 32 or c in '\\?#@' for c in base_url):
        raise ZybError('服务地址不允许凭据、查询、片段或控制字符', 'service_url')
    try:
        url = urlsplit(base_url)
        host, port = url.hostname, url.port
        if url.scheme not in ('http', 'https') or not host or (port is not None and not 1 <= port <= 65535):
            raise ValueError()
        if (not re.fullmatch(r'(?:/[A-Za-z0-9._~-]+)*/?', url.path)
                or any(part in ('.', '..') for part in url.path.split('/'))
                or host in _METADATA):
            raise ValueError()
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
            if host != 'localhost' and '.' not in host or re.fullmatch(r'[0-9.]+', host) or host.startswith('0x'):
                raise ValueError()
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host) or any(
                    not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.')):
                raise ValueError()
        if mode == 'local' and not (host == 'localhost' or ip and ip.is_loopback):
            raise ValueError()
        if mode == 'external' and url.scheme != 'https' and not allow_private_targets:
            raise ValueError()
        if ip:
            check_ip(str(ip), mode, url.scheme, allow_private_targets)
    except ValueError:
        raise ZybError('服务地址不合法：本地仅限回环，外部默认HTTPS，内网HTTP须显式信任', 'service_url') from None
    return url


def resolve_target(mode, base_url, allow_private_targets=False, *, timeout=3):
    url = parse_target(mode, base_url, allow_private_targets)
    port = url.port or (443 if url.scheme == 'https' else 80)
    try:
        ip = ipaddress.ip_address(url.hostname)
        return (socket.AF_INET6, (str(ip), port, 0, 0)) if ip.version == 6 else (socket.AF_INET, (str(ip), port))
    except ValueError:
        pass
    if not _DNS_SLOTS.acquire(blocking=False):
        raise ZybError('服务DNS解析繁忙，请稍后重试', 'gateway_busy', 429)
    result = queue.Queue(maxsize=1)
    def resolve():
        try:
            result.put((True, socket.getaddrinfo(url.hostname, port, type=socket.SOCK_STREAM)))
        except Exception:
            result.put((False, None))
        finally:
            _DNS_SLOTS.release()
    threading.Thread(target=resolve, daemon=True, name='omrs-gateway-dns').start()
    try:
        ok, rows = result.get(timeout=max(.001, min(timeout, 3)))
    except queue.Empty:
        raise ZybError('服务DNS解析超时', 'gateway_network', 502) from None
    if not ok or not rows or len(rows) > 32:
        raise ZybError('服务DNS解析失败', 'gateway_network', 502)
    for family, _kind, _protocol, _canon, address in rows:
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise ZybError('服务地址类型不受支持', 'service_target')
        check_ip(address[0], mode, url.scheme, allow_private_targets)
    # 核验全部结果后只选一个地址；不自动重试或二次DNS解析。
    return rows[0][0], rows[0][4]
