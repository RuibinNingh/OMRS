"""搜题真实 HTTP；仅官方边界由本地 HTTP 上游或合成异常替代。"""
import base64
import copy
from email.parser import BytesParser
from email.policy import default
import hashlib
import io
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
import time
import urllib.request
from unittest.mock import patch
from PIL import Image
from .support import HttpCase
from .test_accounts import SYNTHETIC_PROFILE


def image_bytes(format='PNG'):
    data=io.BytesIO();Image.new('RGB',(7,5),(13,51,171)).save(data,format=format)
    return data.getvalue()

class SearchTests(HttpCase):
    def setup_profile_key(self):
        self.login()
        self.assertEqual(self.admin('POST','/api/admin/profile',{'profile':copy.deepcopy(SYNTHETIC_PROFILE)})[0],200)
        self.key,self.kid=self.make_key()

    def search(self,raw=None,grade=3,extra=None):
        return self.request('POST','/api/v1/search',{'image_base64':base64.b64encode(raw or image_bytes()).decode(),'grade':grade,**(extra or {})},{'Authorization':'Bearer '+self.key})

    def test_real_http_jpeg_request_original_history_and_decoded_result(self):
        self.setup_profile_key()
        self.assertNotEqual(self.search(extra={'grade':True})[0],404,'搜题端点尚未实现')
        captured=[]
        class OfficialBoundary(BaseHTTPRequestHandler):
            def log_message(self,*_args):pass
            def do_POST(self):
                raw=self.rfile.read(int(self.headers['Content-Length']))
                message=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\n\r\n').encode()+raw)
                parts={part.get_param('name',header='content-disposition'):part for part in message.iter_parts()}
                image=parts['image'].get_payload(decode=True)
                captured.append((parts,image))
                # 复现官方拒绝直接上传PNG/WebP；错误不能靠自动重试掩盖。
                reply={'errNo':4000}
                if image.startswith(b'\xff\xd8'):
                    reply={'errNo':0,'data':{'encode':1,'answers':{'gzip':0,'mainPageInfo':[base64.b64encode(b'<p>SYNTHETIC-question</p>').decode()]}}}
                body=json.dumps(reply).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        upstream=ThreadingHTTPServer(('127.0.0.1',0),OfficialBoundary)
        worker=threading.Thread(target=upstream.serve_forever,daemon=True);worker.start()
        real_opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        target=f'http://127.0.0.1:{upstream.server_port}/synthetic-official'
        class RedirectToSyntheticOnly:
            def open(self,request,timeout):
                self_url=request.full_url
                assert self_url=='https://aisearch.zuoyebang.com/search/submit/whole'
                return real_opener.open(urllib.request.Request(target,data=request.data,headers=dict(request.headers)),timeout=timeout)
        try:
            with patch('zyb_gateway.vendor.direct.urllib.request.build_opener',return_value=RedirectToSyntheticOnly()):
                originals=[]
                for format in ('PNG','JPEG','WEBP'):
                    raw=image_bytes(format);originals.append(raw)
                    code,data,_=self.search(raw,4)
                    self.assertEqual(code,200,data)
                    self.assertEqual(data,{'status':'ok','result':{'ok':True,'data':{'encode':1,'answers':{'gzip':0,'mainPageInfo':['<p>SYNTHETIC-question</p>']}}}})
                self.assertEqual(len(captured),3)
                for (parts,sent),raw in zip(captured,originals):
                    self.assertEqual(parts['image'].get_content_type(),'image/jpeg')
                    self.assertEqual(parts['image'].get_filename(),'question.jpg')
                    self.assertEqual(parts['picMD5'].get_payload(decode=True).decode(),hashlib.md5(sent).hexdigest())
                    self.assertEqual(parts['gradeId'].get_payload(decode=True),b'4')
                    with Image.open(io.BytesIO(sent)) as image:
                        self.assertEqual(image.format,'JPEG')
                        self.assertEqual(image.size,(7,5))
                    if raw.startswith(b'\xff\xd8'):
                        self.assertEqual(sent,raw)
                    else:
                        self.assertNotEqual(sent,raw)
                rows=self.admin('GET','/api/admin/history?action=search')[1]['items']
                for row,raw in zip(rows, reversed(originals)):
                    self.assertEqual(self.server.store.history_image(row['id'])[0],raw)
        finally:
            upstream.shutdown();upstream.server_close();worker.join()
        self.assertNotIn('SYNTHETIC-question',str(self.admin('GET','/api/admin/history')[1]))

    def test_official_image_transparency_and_conversion_budget(self):
        from zyb_gateway.search import prepare_official_image
        for mode,format in (('RGBA','PNG'),('RGBA','WEBP'),('P','PNG')):
            with self.subTest(mode=mode,format=format):
                source=Image.new(mode,(12,10))
                if mode=='P':source.info['transparency']=0
                output=io.BytesIO();source.save(output,format)
                raw=output.getvalue()
                converted=prepare_official_image(raw,8*1024*1024)
                with Image.open(io.BytesIO(converted)) as image:
                    self.assertEqual(image.size,(12,10))
                    self.assertEqual(image.getpixel((0,0)),(255,255,255))
        from zyb_gateway.errors import ApiError
        with self.assertRaises(ApiError) as caught:
            prepare_official_image(image_bytes(),1)
        self.assertEqual(caught.exception.code,'image_invalid')

    def test_requires_key_session_and_strict_base64_grade_image(self):
        self.login();self.key,self.kid=self.make_key()
        self.assertEqual(self.search()[0],503)
        self.admin('POST','/api/admin/profile',{'profile':copy.deepcopy(SYNTHETIC_PROFILE)})
        self.assertEqual(self.request('POST','/api/v1/search',{'grade':0,'image_base64':'aaa='})[0],401)
        for value in (-1,13,True,'3',None,3.5):
            self.assertEqual(self.search(grade=value)[0],400)
        for raw in ('data:image/png;base64,AA==','aGVsbG8=\n','%%%','aGVsbG8=',None):
            self.assertEqual(self.request('POST','/api/v1/search',{'image_base64':raw,'grade':0},{'Authorization':'Bearer '+self.key})[0],400)
        self.assertEqual(self.search(image_bytes()[:30])[0],400)
        self.assertEqual(self.search(extra={'image_base64':'A'*((8*1024*1024+1)*4//3+4)})[0],400)
        old=self.cfg.max_pixels;self.cfg.max_pixels=10
        self.assertEqual(self.search()[0],400)
        self.cfg.max_pixels=old

    def test_upstream_error_generic_no_retries_observation_and_response_cap(self):
        self.setup_profile_key()
        self.assertNotEqual(self.search(grade=True)[0],404)
        from zyb_gateway.vendor.direct import DirectClient,UpstreamError
        for kind in ('network','signing_session','login_required','protocol','upstream'):
            with patch.object(DirectClient,'search',side_effect=UpstreamError('SECRET-OFFICIAL-BODY',6,kind)) as boundary:
                code,data,_=self.search()
                self.assertEqual(code,502,data)
                self.assertEqual(boundary.call_count,1)
                self.assertNotIn('SECRET-OFFICIAL',str(data))
        self.cfg.max_response_bytes=128
        with patch.object(DirectClient,'search',return_value={'ok':True,'data':{'oversized':'x'*200}}):
            code,data,_=self.search()
            self.assertEqual(code,502,data)
            self.assertEqual(data['code'],'response_budget')

    def test_concurrency_budget_and_late_result_rejected(self):
        self.setup_profile_key();self.cfg.search_concurrency=1
        self.assertNotEqual(self.search(grade=True)[0],404)
        from zyb_gateway.vendor.direct import DirectClient
        entered=threading.Event();release=threading.Event();replies=[]
        def boundary(*_args,**_kwargs):
            entered.set();release.wait(3);return {'ok':True,'data':{}}
        self.server.search_slots=threading.BoundedSemaphore(1)
        with patch.object(DirectClient,'search',side_effect=boundary):
            worker=threading.Thread(target=lambda:replies.append(self.search()),daemon=True);worker.start()
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.search()[0],429)
            profile=copy.deepcopy(SYNTHETIC_PROFILE);profile['session_token']='SYNTHETIC-later'
            self.assertEqual(self.admin('POST','/api/admin/profile',{'profile':profile})[0],200)
            release.set();worker.join(4)
        self.assertEqual(replies[0][0],409)

class DailyBudgetTests(HttpCase):
    config_overrides={'search_daily_budget':1}
    def test_daily_search_budget_charged_once_and_persistent(self):
        self.login();self.admin('POST','/api/admin/profile',{'profile':copy.deepcopy(SYNTHETIC_PROFILE)})
        key,kid=self.make_key()
        payload={'image_base64':base64.b64encode(image_bytes()).decode(),'grade':0}
        headers={'Authorization':'Bearer '+key}
        self.assertNotEqual(self.request('POST','/api/v1/search',dict(payload,grade=True),headers)[0],404)
        from zyb_gateway.vendor.direct import DirectClient,UpstreamError
        with patch.object(DirectClient,'search',side_effect=UpstreamError('synthetic',kind='network')) as boundary:
            self.assertEqual(self.request('POST','/api/v1/search',payload,headers)[0],502)
            self.assertEqual(self.request('POST','/api/v1/search',payload,headers)[0],429)
            self.assertEqual(boundary.call_count,1)
