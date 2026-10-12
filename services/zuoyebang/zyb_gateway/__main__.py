"""独立 CLI，不安装或操作 systemd/nginx/防火墙。"""
import argparse
from pathlib import Path
import secrets
import signal
import sys
import threading
from .config import Config
from .server import create_server
from .storage import Store,atomic_private,password_hash


def parser():
    main=argparse.ArgumentParser(description='作业帮独立网关；默认仅本机访问，调用密钥仍必需')
    commands=main.add_subparsers(dest='command',required=True)
    for name,help_text in [('init','生成受限管理员初始密码文件'),('rotate-admin','重置管理员密码并注销所有管理会话'),('serve','前台运行网关')]:
        command=commands.add_parser(name,help=help_text)
        command.add_argument('--data-dir',type=Path,default=Path('.state'),help='私有 SQLite 与会话目录，权限 0700')
        if name!='serve':continue
        command.add_argument('--bind',default='127.0.0.1',help='监听 IP，默认 127.0.0.1')
        command.add_argument('--port',type=int,default=8745,help='监听端口；0 仅用于隔离验收')
        command.add_argument('--allow-host',action='append',default=[],help='额外可信 Host（包含非默认端口），禁止通配符')
        command.add_argument('--public-origin',default='',help='反代公开 Origin，例如 https://zyb.example.com')
        command.add_argument('--trusted-proxy',action='append',default=[],help='明确信任的代理 CIDR，例如 127.0.0.1/32')
        command.add_argument('--secure-cookie',action='store_true',help='外部 HTTPS 面板必须启用')
        command.add_argument('--allow-external',action='store_true',help='显式开启持久化外部开关；不修改网络配置')
        defaults=Config(data_dir=Path('.state'))
        for flag,attribute in [('session-seconds','session_seconds'),('api-per-minute','api_per_minute'),('search-per-minute','search_per_minute'),('daily-budget','search_daily_budget'),('search-concurrency','search_concurrency'),('http-concurrency','http_concurrency'),('history-limit','history_limit'),('history-days','history_days')]:
            command.add_argument('--'+flag,type=int,default=getattr(defaults,attribute),help='资源上限，默认 '+str(getattr(defaults,attribute)))
        command.add_argument('--read-timeout',type=float,default=10,help='请求体总读取期限（秒）')
        command.add_argument('--upstream-timeout',type=float,default=50,help='单次搜题官方请求/响应期限（秒）')
    return main


def main(argv=None):
    arguments=parser().parse_args(argv)
    try:
        if arguments.command in ('init','rotate-admin'):
            config=Config(data_dir=arguments.data_dir)
            store=Store(config)
            if arguments.command=='rotate-admin':
                secret=secrets.token_urlsafe(36)
                with store.lock,store.connect() as db:
                    atomic_private(store.root/'admin-secret.txt',(secret+'\n').encode())
                    db.execute("UPDATE settings SET value=? WHERE name='admin_hash'",(password_hash(secret),))
                    db.execute('DELETE FROM sessions')
                    db.execute('DELETE FROM login_failures')
            print('管理员初始密码文件：'+str(store.root/'admin-secret.txt')+'（0600，不输出秘密）',flush=True)
            return 0
        config=Config(data_dir=arguments.data_dir,bind=arguments.bind,port=arguments.port,allowed_hosts=tuple(arguments.allow_host),public_origin=arguments.public_origin,trusted_proxies=tuple(arguments.trusted_proxy),secure_cookie=arguments.secure_cookie,session_seconds=arguments.session_seconds,api_per_minute=arguments.api_per_minute,search_per_minute=arguments.search_per_minute,search_daily_budget=arguments.daily_budget,search_concurrency=arguments.search_concurrency,http_concurrency=arguments.http_concurrency,read_timeout=arguments.read_timeout,upstream_timeout=arguments.upstream_timeout,history_limit=arguments.history_limit,history_days=arguments.history_days)
        server=create_server(config)
        if arguments.allow_external:server.store.set('allow_external',True)
        stopping=threading.Event()
        def stop(_signum,_frame):
            if not stopping.is_set():
                stopping.set()
                threading.Thread(target=server.shutdown,daemon=True).start()
        for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
        print('管理员初始密码文件：'+str(config.data_dir/'admin-secret.txt')+'（0600，不输出秘密）',flush=True)
        host='['+config.bind+']' if ':' in config.bind else config.bind
        print(f'监听：http://{host}:{server.server_port}',flush=True)
        print('外部访问：'+('允许（仍需独立鉴权）' if server.store.get('allow_external',False) else '关闭'),flush=True)
        try:server.serve_forever(poll_interval=0.1)
        finally:server.server_close()
        return 0
    except (ValueError,OSError):
        print('启动失败：配置、私有存储或监听地址不可用，请检查安全参数。',file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
