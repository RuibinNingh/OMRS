"""资源期限、解码累计预算、真实 HTTP 重载与反 CSRF 加固。"""
import base64
import gzip
import http.client
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from .support import HttpCase
from .test_accounts import SYNTHETIC_PROFILE
from .test_search import image_bytes
from zyb_gateway.vendor.direct import decode_response,UpstreamError

class HardeningTests(HttpCase):
    def test_http_thread_budget_rejects_without_new_worker(self):
        self.assertTrue(hasattr(self.server,'http_slots'),'HTTP 工作线程仍无总并发上限')
        slots=self.server.http_slots
        acquired=[]
        while slots.acquire(blocking=False):acquired.append(True)
        try:
            code,data,_=self.request('GET','/healthz')
            self.assertEqual(code,429,data)
            self.assertEqual(data['code'],'concurrency_limited')
        finally:
            for _ in acquired:slots.release()

    def test_api_origin_rejected_without_spending_or_official_network(self):
        key,_=self.make_key()
        code,data,_=self.request('POST','/api/v1/search',{'image_base64':base64.b64encode(image_bytes()).decode(),'grade':0},{'Authorization':'Bearer '+key,'Origin':'https://evil.example'})
        self.assertEqual(code,403,data)

    def test_duplicate_authorization_is_rejected(self):
        key,_=self.make_key()
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        try:
            connection.putrequest('GET','/api/v1/status')
            connection.putheader('Authorization','Bearer '+key)
            connection.putheader('Authorization','Bearer SYNTHETIC-bad')
            connection.endheaders()
            response=connection.getresponse();response.read()
            self.assertEqual(response.status,401)
        finally:connection.close()

    def test_gzip_decode_has_aggregate_not_only_per_page_budget(self):
        encoded=base64.b64encode(gzip.compress(b'x'*(9*1024*1024))).decode()
        body={'errNo':0,'data':{'encode':1,'answers':{'gzip':1,'mainPageInfo':[encoded]*3}}}
        with self.assertRaises(UpstreamError):decode_response(body,'synthetic-unused-key')

    def test_upstream_deadline_is_total_not_each_read(self):
        self.login();self.admin('POST','/api/admin/profile',{'profile':SYNTHETIC_PROFILE});key,_=self.make_key()
        self.cfg.upstream_timeout=0.15
        class SlowSynthetic(BaseHTTPRequestHandler):
            def log_message(self,*_args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Length','12');self.end_headers()
                for _ in range(12):
                    try:self.wfile.write(b' ');self.wfile.flush()
                    except OSError:break
                    time.sleep(0.08)
        upstream=ThreadingHTTPServer(('127.0.0.1',0),SlowSynthetic);upstream.daemon_threads=True
        worker=threading.Thread(target=upstream.serve_forever,daemon=True);worker.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));target=f'http://127.0.0.1:{upstream.server_port}/synthetic'
        class Boundary:
            def open(self,request,timeout):
                return opener.open(urllib.request.Request(target,data=request.data,headers=dict(request.headers)),timeout=timeout)
        try:
            start=time.monotonic()
            with patch('zyb_gateway.vendor.direct.urllib.request.build_opener',return_value=Boundary()):
                code,data,_=self.request('POST','/api/v1/search',{'image_base64':base64.b64encode(image_bytes()).decode(),'grade':0},{'Authorization':'Bearer '+key})
            self.assertEqual(code,502,data)
            self.assertLess(time.monotonic()-start,0.7,'单个慢速响应仍可无限续时')
        finally:upstream.shutdown();upstream.server_close();worker.join()

    def test_chunked_body_denied_and_timed_out_total_body(self):
        self.login()
        headers={'Cookie':self.cookie,'Origin':self.base,'X-CSRF-Token':self.csrf,'Content-Type':'application/json','Transfer-Encoding':'chunked'}
        self.assertEqual(self.request('POST','/api/admin/keys',b'0\r\n\r\n',headers)[0],400)
        self.cfg.read_timeout=0.2
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
        try:
            connection.putrequest('POST','/api/admin/keys')
            for name,value in {k:v for k,v in headers.items() if k!='Transfer-Encoding'}.items():connection.putheader(name,value)
            connection.putheader('Content-Length','100');connection.endheaders()
            start=time.monotonic()
            connection.send(b'{')
            time.sleep(0.12);connection.send(b' ')
            time.sleep(0.12);connection.send(b' ')
            response=connection.getresponse();response.read()
            self.assertEqual(response.status,408)
            self.assertLess(time.monotonic()-start,0.35)
        finally:connection.close()
