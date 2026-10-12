"""最后自审的两个回归：错误审计筛选与非法 HTTP target。"""
import http.client
from .support import HttpCase

class ReviewTests(HttpCase):
    def test_malformed_absolute_target_is_400_with_redacted_audit(self):
        self.login()
        try:
            response=self.request('GET','http://[SYNTHETIC-TARGET-SECRET',headers={'Host':self.base.removeprefix('http://')})
        except http.client.HTTPException:
            response=(0,{}, {})
        self.assertEqual(response[0],400)
        self.assertEqual(response[1]['code'],'path_invalid')
        self.assertEqual(self.request('GET','http://untrusted.example/api/v1/status',headers={'Host':self.base.removeprefix('http://')})[0],400)
        rows=self.admin('GET','/api/admin/history')[1]['items']
        invalid=[r for r in rows if r['result']=='path_invalid']
        self.assertEqual(len(invalid),2)
        self.assertTrue(all(r['path']=='/[unknown]' for r in invalid))
        self.assertNotIn('SYNTHETIC-TARGET-SECRET',str(rows))

    def test_management_failure_codes_can_be_filtered(self):
        self.login()
        cases=[({'operation':'bad'},'operation_invalid'),({'operation':'qr_poll','flow_id':'bad'},'flow_invalid')]
        for body,code in cases:
            self.assertEqual(self.admin('POST','/api/admin/account',body)[1]['code'],code)
            with self.subTest(code=code):
                status,data,_=self.admin('GET','/api/admin/history?result='+code)
                self.assertEqual(status,200)
                self.assertGreaterEqual(data['total'],1)
                self.assertTrue(all(r['result']==code for r in data['items']))
        self.assertEqual(self.admin('POST','/api/admin/credential',{'credential':''})[1]['code'],'credential_invalid')
        self.assertEqual(self.admin('GET','/api/admin/history?result=credential_invalid')[0],200)
