"""验收自审发现的真实输入边界，先保留 RED 再修复。"""
import base64
import io
import json
import time
from unittest.mock import patch
from .support import HttpCase
from zyb_gateway.vendor.direct import decode_response,UpstreamError,DirectClient
from zyb_gateway.transport import bounded_read,ResponseBudget

class AdversarialTests(HttpCase):
    def test_non_ascii_csrf_and_unhashable_operation_are_input_errors(self):
        self.login()
        with self.subTest(case='csrf'):
            self.assertEqual(self.admin('POST','/api/admin/keys',{'name':'bad'},{'X-CSRF-Token':'é'})[0],403)
        for operation in ([],{},None,False):
            with self.subTest(case=operation):
                self.assertEqual(self.admin('POST','/api/admin/account',{'operation':operation})[0],400)

    def test_duplicate_json_and_excessive_query_fail_400_without_write(self):
        self.login()
        raw=b'{"allow_external":false,"allow_external":true}'
        self.assertEqual(self.admin('POST','/api/admin/settings',raw,{'Content-Type':'application/json'})[0],400)
        self.assertFalse(self.admin('GET','/api/admin/settings')[1]['allow_external'])

    def test_excessive_history_query_is_400(self):
        self.login()
        query='&'.join('page=1' for _ in range(21))
        self.assertEqual(self.admin('GET','/api/admin/history?'+query)[0],400)

    def test_unknown_methods_are_json_404_local_and_403_external(self):
        for method in ('PUT','PATCH','DELETE','OPTIONS'):
            self.assertEqual(self.request(method,'/api/v1/status',{})[0],404)
            self.assertEqual(self.request(method,'/api/v1/status',{}, {'Host':self.base.removeprefix('http://')},host=self.lan_ip())[0],403)

    def test_login_notice_is_account_failure_not_valid_search(self):
        page=base64.b64encode('<p>登录提醒，请在个人中心登录，重新登录。</p>'.encode()).decode()
        body={'errNo':0,'data':{'encode':1,'answers':{'gzip':0,'mainPageInfo':[page]}}}
        with self.assertRaises(UpstreamError) as raised:decode_response(body,'synthetic')
        self.assertEqual(raised.exception.kind,'login_required')

    def test_response_wire_budget_stream_length_and_no_redirect(self):
        # 已实现读取器的回归覆盖；这项不宣称新 RED 行为。
        class Stream(io.BytesIO):
            headers={}
        with self.assertRaises(ResponseBudget):bounded_read(Stream(b'x'*10),9,time.monotonic()+1)
        stream=Stream(b'x');stream.headers={'Content-Length':'100000000'}
        with self.assertRaises(ResponseBudget):bounded_read(stream,9,time.monotonic()+1)
        with self.assertRaises(TimeoutError):bounded_read(Stream(b'x'),9,time.monotonic()-1)
        from zyb_gateway.vendor.direct import NoRedirect
        with self.assertRaises(UpstreamError):NoRedirect().redirect_request(None,None,None,None,None,None)
