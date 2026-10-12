"""运行时配置；监听与应用访问开关互相独立。"""
from dataclasses import dataclass
from pathlib import Path
import ipaddress
import re
from urllib.parse import urlsplit

@dataclass
class Config:
    data_dir: Path
    bind: str = '127.0.0.1'
    port: int = 8745
    allowed_hosts: tuple = ()
    public_origin: str = ''
    trusted_proxies: tuple = ()
    secure_cookie: bool = False
    session_seconds: int = 3600
    login_failures: int = 5
    login_window: int = 300
    api_per_minute: int = 60
    search_per_minute: int = 10
    search_daily_budget: int = 200
    search_concurrency: int = 2
    http_concurrency: int = 32
    read_timeout: float = 10
    upstream_timeout: float = 50
    max_image_bytes: int = 8 * 1024 * 1024
    max_pixels: int = 40_000_000
    max_response_bytes: int = 24 * 1024 * 1024
    history_limit: int = 10000
    history_days: int = 30

    def __post_init__(self):
        self.data_dir=Path(self.data_dir).absolute()
        ipaddress.ip_address(self.bind)
        bounds={'port':(0,65535),'session_seconds':(1,86400),'login_failures':(1,20),'login_window':(1,3600),'api_per_minute':(1,10000),'search_per_minute':(1,100),'search_daily_budget':(1,100000),'search_concurrency':(1,8),'http_concurrency':(1,128),'history_limit':(1,100000),'history_days':(1,365),'max_image_bytes':(1,8*1024*1024),'max_pixels':(1,40_000_000),'max_response_bytes':(128,24*1024*1024)}
        for name,(minimum,maximum) in bounds.items():
            value=getattr(self,name)
            if type(value) is not int or not minimum<=value<=maximum:
                raise ValueError('资源预算参数不合法：'+name)
        for name in ('read_timeout','upstream_timeout'):
            value=getattr(self,name)
            if type(value) not in (float,int) or not 0.05<=value<=60:
                raise ValueError('超时参数不合法：'+name)
        if type(self.secure_cookie) is not bool:
            raise ValueError('Secure cookie 参数必须为布尔值')
        for proxy in self.trusted_proxies:
            network=ipaddress.ip_network(proxy,strict=True)
            if network.prefixlen==0:
                raise ValueError('不能信任所有来源为代理')
        for host in self.allowed_hosts:
            validate_host(host)
        if self.public_origin:
            origin=urlsplit(self.public_origin)
            if origin.scheme not in ('http','https') or origin.username or origin.password or origin.path or origin.query or origin.fragment or self.public_origin!=origin.scheme+'://'+origin.netloc:
                raise ValueError('公开 Origin 必须是无路径或凭据的 http(s) Origin')
            validate_host(origin.netloc)
            if origin.scheme=='https' and not self.secure_cookie:
                raise ValueError('HTTPS 公开面板必须启用 --secure-cookie')


def validate_host(host):
    if not isinstance(host,str) or not host or len(host)>255 or any(c.isspace() for c in host) or any(c in host for c in '/?#@*\\'):
        raise ValueError('可信 Host 不合法；不能使用通配符')
    parsed=urlsplit('http://'+host)
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('可信 Host 不合法')
    if parsed.port is not None and not 1<=parsed.port<=65535:
        raise ValueError('可信 Host 端口不合法')
    if ':' in parsed.hostname:
        ipaddress.ip_address(parsed.hostname)
    elif not re.fullmatch(r'[A-Za-z0-9.-]+',parsed.hostname):
        raise ValueError('可信 Host 必须是明确的域名或 IP')
