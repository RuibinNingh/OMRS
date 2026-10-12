"""真实 CLI 子进程及安全配置；全部数据写隔离目录。"""
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from .support import ROOT
from zyb_gateway.config import Config

class CliTests(unittest.TestCase):
    def test_init_rotate_never_print_secret_and_invalidate_session(self):
        self.assertIsNotNone(importlib.util.find_spec('zyb_gateway.__main__'),'可运行 CLI 尚未交付')
        with tempfile.TemporaryDirectory(dir=ROOT/'docs') as tmp:
            data=Path(tmp)/'private'
            command=[sys.executable,'-m','zyb_gateway','init','--data-dir',str(data)]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            secret=(data/'admin-secret.txt').read_text().strip()
            self.assertNotIn(secret,result.stdout+result.stderr)
            self.assertIn(str(data/'admin-secret.txt'),result.stdout)
            again=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=5)
            self.assertEqual(again.returncode,0)
            self.assertEqual((data/'admin-secret.txt').read_text().strip(),secret)
            rotation=subprocess.run([sys.executable,'-m','zyb_gateway','rotate-admin','--data-dir',str(data)],cwd=ROOT,capture_output=True,text=True,timeout=5)
            self.assertEqual(rotation.returncode,0,rotation.stderr)
            new=(data/'admin-secret.txt').read_text().strip()
            self.assertNotEqual(new,secret)
            self.assertNotIn(new,rotation.stdout+rotation.stderr)

    def test_serve_real_health_default_binding_and_clean_sigterm(self):
        self.assertIsNotNone(importlib.util.find_spec('zyb_gateway.__main__'),'可运行 CLI 尚未交付')
        with tempfile.TemporaryDirectory(dir=ROOT/'docs') as tmp:
            process=subprocess.Popen([sys.executable,'-u','-m','zyb_gateway','serve','--port','0','--data-dir',str(Path(tmp)/'private')],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                lines=[];port=None;deadline=time.monotonic()+6;pending=b''
                while time.monotonic()<deadline:
                    ready=select.select([process.stdout],[],[],0.2)[0]
                    if ready:
                        # readline 的文本缓冲会提前读走后续行，select 无法再看到它们。
                        pending+=os.read(process.stdout.fileno(),4096)
                        while b'\n' in pending:
                            raw,pending=pending.split(b'\n',1)
                            line=raw.decode('utf-8')+'\n';lines.append(line)
                            if '监听：http://127.0.0.1:' in line:
                                port=int(line.strip().split(':')[-1]);break
                        if port is not None:break
                    if process.poll() is not None:break
                self.assertIsNotNone(port,lines)
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz') as response:
                    self.assertEqual(json.load(response)['service'],'zuoyebang-gateway')
                self.assertFalse((Path(tmp)/'private/session.json').exists())
                process.terminate();stdout,stderr=process.communicate(timeout=6)
                self.assertEqual(process.returncode,0,stderr)
                sock=socket.socket();sock.settimeout(1)
                try:self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)
                finally:sock.close()
            finally:
                if process.poll() is None:process.kill();process.wait()
                process.stdout.close();process.stderr.close()

    def test_config_rejects_invalid_proxy_host_origin_and_budgets(self):
        invalid=[{'trusted_proxies':('0.0.0.0/0',)}, {'trusted_proxies':('127.0.0.2/24',)}, {'public_origin':'https://user:password@example.com'}, {'public_origin':'https://example.com/?secret=x'}, {'public_origin':'https://example.com#x'}, {'public_origin':'file:///private'}, {'allowed_hosts':('*',)}, {'allowed_hosts':('example.com/path',)}, {'search_concurrency':0}, {'session_seconds':0}, {'upstream_timeout':1000}]
        for change in invalid:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):Config(data_dir=ROOT/'docs'/'unused',**change)

    def test_data_dir_symlink_ancestor_and_sqlite_sidecar_refused(self):
        self.assertIsNotNone(importlib.util.find_spec('zyb_gateway.__main__'),'可运行 CLI 尚未交付')
        from zyb_gateway.server import create_server
        with tempfile.TemporaryDirectory(dir=ROOT/'docs') as tmp:
            root=Path(tmp);actual=root/'actual';actual.mkdir();linked=root/'linked';linked.symlink_to(actual,target_is_directory=True)
            with self.assertRaises(ValueError):create_server(Config(data_dir=linked/'private',port=0))
            private=root/'private';private.mkdir();(private/'gateway.sqlite3-journal').symlink_to(actual/'outside')
            with self.assertRaises(ValueError):create_server(Config(data_dir=private,port=0))
