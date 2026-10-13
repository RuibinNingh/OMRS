"""兼容旧检测服务命令；实现位于 services/boxdetect。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.boxdetect._service import module

_server = module('server')
make_server = _server.make_server
main = _server.main
MAX_BODY = _server.MAX_BODY
ROLES = _server.ROLES
sha256 = _server.sha256
Detector = _server.Detector

if __name__ == '__main__':
    main()
