"""仅外界官方调用为合成；设备样本明确 SYNTHETIC，不可用于真实登录。"""
import copy
import json
import stat
import threading
from unittest.mock import patch
from .support import HttpCase

SYNTHETIC_PROFILE = {
    'url':'https://aisearch.zuoyebang.com/search/submit/whole',
    'fields':{'cuid':'SYNTHETIC-registered-test-device-NOT-REAL','vc':'999','vcname':'SYNTHETIC','ZYBUSS':'SYNTHETIC-account-NOT-REAL'},
    'headers':{'Cookie':'ZYBUSS=SYNTHETIC-account-NOT-REAL'},
    'session_token':'SYNTHETIC-signing-seed-NOT-REAL',
}

class AccountTests(HttpCase):
    def import_profile(self,profile=None):
        if not self.cookie: self.login()
        code,data,_=self.admin('POST','/api/admin/profile',{'profile':profile or copy.deepcopy(SYNTHETIC_PROFILE)})
        self.assertEqual(code,200,data)
        return data

    def op(self,operation,flow_id=''):
        return self.admin('POST','/api/admin/account',{'operation':operation,'flow_id':flow_id})

    def test_import_is_private_offline_and_summary_has_no_credential(self):
        data=self.import_profile()
        self.assertTrue(data['account']['local_session_ready'])
        self.assertTrue(data['account']['has_account_credential'])
        self.assertEqual(data['account']['observations']['account']['state'],'unknown')
        for secret in ('SYNTHETIC-account','SYNTHETIC-signing','SYNTHETIC-registered'):
            self.assertNotIn(secret,str(data))
        self.assertEqual(stat.S_IMODE((self.cfg.data_dir/'session.json').stat().st_mode),0o600)
        key,_=self.make_key()
        with patch('zyb_gateway.vendor.account.AccountClient.request',side_effect=AssertionError('只读状态不能联网')):
            code,data,_=self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})
        self.assertEqual(code,200)
        self.assertTrue(data['account']['local_session_ready'])

    def test_invalid_profile_import_preserves_existing_profile(self):
        self.import_profile()
        original=(self.cfg.data_dir/'session.json').read_bytes()
        for change in ({'url':'http://evil.example'},{'session_token':''},{'fields':{'cuid':'x','vc':True}},{'headers':{'Host':'evil.example'}},{'headers':{'Cookie':'x\r\ninjected: y'}}):
            profile=copy.deepcopy(SYNTHETIC_PROFILE); profile.update(change)
            self.assertEqual(self.admin('POST','/api/admin/profile',{'profile':profile})[0],400)
            self.assertEqual(original,(self.cfg.data_dir/'session.json').read_bytes())
        self.assertEqual(self.admin('POST','/api/admin/profile',{'profile':dict(SYNTHETIC_PROFILE,extra='x'*270000)})[0],400)

    def test_verify_refresh_observations_and_no_raw_upstream_leak(self):
        self.import_profile()
        from zyb_gateway.vendor.account import AccountClient
        from zyb_gateway.vendor.direct import UpstreamError
        def boundary(operation,profile,params=None,**kwargs):
            if operation=='relogin':return {'errNo':0,'data':{'zybuss':'SYNTHETIC-refreshed'}}
            return {'errNo':0,'data':{'user':{'uid':123}}}
        with patch.object(AccountClient,'request',side_effect=boundary):
            self.assertEqual(self.op('verify')[0],200)
            result=self.op('refresh')
            self.assertEqual(result[0],200,result[1])
            self.assertEqual(result[1]['account']['observations']['account']['state'],'valid')
        for kind,state in [('network','valid'),('protocol','valid'),('login_required','invalid'),('signing_session','invalid')]:
            with patch.object(AccountClient,'request',side_effect=UpstreamError('RAW-SENSITIVE-OFFICIAL-RESPONSE',6,kind)):
                code,data,_=self.op('verify')
            self.assertEqual(code,502,data)
            self.assertNotIn('RAW-SENSITIVE',str(data))
            part='signing' if kind=='signing_session' else 'account'
            self.assertEqual(data.get('account',self.admin('GET','/api/admin/account')[1]['account'])['observations'][part]['state'],state)
        with patch.object(AccountClient,'request',side_effect=boundary):
            result=self.op('verify')[1]
        self.assertTrue(result['account']['observations']['events'][-1]['account_recovered'])
        self.assertTrue(result['account']['observations']['events'][-1]['signing_recovered'])

    def test_qr_missing_profile_is_not_fabricated(self):
        self.login()
        self.assertEqual(self.op('qr_start')[0],503)
        self.assertFalse((self.cfg.data_dir/'session.json').exists())

    def test_official_qr_start_poll_confirm_cancel_and_generation(self):
        self.import_profile()
        self.assertEqual(self.op('unknown')[0],400)
        from zyb_gateway.vendor.account import AccountClient
        def boundary(operation,profile,params=None,**kwargs):
            if operation=='qr_create':return {'errNo':0,'data':{'uuid':'SYNTHETIC-official-challenge'}}
            if operation=='qr_check':return {'errNo':0,'data':{'zybuss':'SYNTHETIC-qr-confirmed'}}
            if operation=='userinfo':return {'errNo':0,'data':{'user':{'uid':123}}}
            raise AssertionError(operation)
        with patch.object(AccountClient,'request',side_effect=boundary):
            code,data,_=self.op('qr_start')
            self.assertEqual(code,200,data)
            result=data['result']; flow=result['flow_id']
            self.assertTrue(result['qr_image'].startswith('data:image/png;base64,'))
            self.assertEqual(result['state'],'pending')
            code,data,_=self.op('qr_poll',flow)
            self.assertEqual(code,200,data)
            self.assertEqual(data['result']['state'],'authenticated')
            self.assertNotIn('SYNTHETIC-qr-confirmed',str(data))
            code,data,_=self.op('qr_start'); flow=data['result']['flow_id']
            self.assertEqual(self.op('qr_cancel',flow)[1]['result']['state'],'cancelled')
            self.assertEqual(self.op('qr_poll',flow)[1]['result']['state'],'cancelled')
            code,data,_=self.op('qr_start'); flow=data['result']['flow_id']
            self.import_profile()
            self.assertEqual(self.op('qr_poll',flow)[1]['result']['state'],'missing')
        history=self.admin('GET','/api/admin/history')[1]
        self.assertNotIn('SYNTHETIC-official-challenge',str(history))

    def test_inflight_account_cannot_overwrite_new_import(self):
        self.import_profile()
        self.assertEqual(self.op('unknown')[0],400)
        from zyb_gateway.vendor.account import AccountClient
        entered=threading.Event(); release=threading.Event(); replies=[]
        def boundary(operation,profile,params=None,**kwargs):
            if operation=='relogin':
                entered.set(); release.wait(3)
                return {'errNo':0,'data':{'zybuss':'SYNTHETIC-late-credential'}}
            return {'errNo':0,'data':{'user':{'uid':123}}}
        with patch.object(AccountClient,'request',side_effect=boundary):
            task=threading.Thread(target=lambda:replies.append(self.op('refresh')),daemon=True); task.start()
            self.assertTrue(entered.wait(2))
            replacement=copy.deepcopy(SYNTHETIC_PROFILE);replacement['session_token']='SYNTHETIC-replaced-seed'
            self.import_profile(replacement)
            release.set();task.join(4)
        self.assertEqual(replies[0][0],409)
        self.assertEqual(json.loads((self.cfg.data_dir/'session.json').read_bytes())['session_token'],'SYNTHETIC-replaced-seed')
