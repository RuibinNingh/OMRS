"""管理面板静态入口与账号凭据导入纵向契约。"""
import json
from .support import HttpCase
from .test_accounts import SYNTHETIC_PROFILE

class PanelTests(HttpCase):
    def test_panel_static_assets_chinese_dark_no_build_no_inline_handlers(self):
        code,html,headers=self.request('GET','/')
        self.assertEqual(code,200,html)
        self.assertIn('作业帮网关',html)
        self.assertIn('lang="zh-CN"',html)
        self.assertIn('src="assets/panel.js"',html)
        self.assertIn('href="assets/panel.css"',html)
        self.assertNotIn('onclick=',html)
        self.assertNotIn(self.password,html)
        self.assertEqual(self.request('GET','/assets/panel.js')[0],200)
        self.assertEqual(self.request('GET','/assets/panel.css')[0],200)
        self.assertEqual(self.request('GET','/assets/../storage.py')[0],404)
        self.assertEqual(self.request('GET','/admin-secret.txt')[0],404)

    def test_separate_credential_import_requires_real_device_template(self):
        self.login()
        self.assertEqual(self.admin('POST','/api/admin/credential',{'credential':'SYNTHETIC-manual-credential'})[0],503)
        self.assertEqual(self.admin('POST','/api/admin/profile',{'profile':SYNTHETIC_PROFILE})[0],200)
        code,data,_=self.admin('POST','/api/admin/credential',{'credential':'SYNTHETIC-manual-credential'})
        self.assertEqual(code,200,data)
        self.assertNotIn('SYNTHETIC-manual',str(data))
        self.assertEqual(json.loads((self.cfg.data_dir/'session.json').read_bytes())['fields']['ZYBUSS'],'SYNTHETIC-manual-credential')
        for value in ('',None,'line\nSECRET','spaces SECRET','semi;SECRET'):
            self.assertEqual(self.admin('POST','/api/admin/credential',{'credential':value})[0],400)
