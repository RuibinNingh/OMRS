"""真实 Chromium 验收。合成官方边界仅供测试，永不接触真实账户。
默认复用 localhost:9222，只关闭本测试自建 context，不关闭共享 Chrome。
"""
import copy
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=Path(os.environ.get('ZYB_TEST_EVIDENCE_DIR',str(ROOT/'docs')))
EVIDENCE.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from tests.support import HttpCase
from tests.test_accounts import SYNTHETIC_PROFILE

class BrowserAcceptance(HttpCase):
    def test_panel_full_workflow_desktop_and_390px(self):
        from playwright.sync_api import sync_playwright
        from zyb_gateway.vendor.account import AccountClient
        def synthetic_official(operation,profile,params=None,**kwargs):
            if operation=='qr_create':return {'errNo':0,'data':{'uuid':'SYNTHETIC-BROWSER-OFFICIAL-CHALLENGE'}}
            if operation=='qr_check':return {'errNo':0,'data':{'zybuss':'SYNTHETIC-BROWSER-CONFIRMED'}}
            if operation=='relogin':return {'errNo':0,'data':{'zybuss':'SYNTHETIC-BROWSER-REFRESHED'}}
            if operation=='userinfo':return {'errNo':0,'data':{'user':{'uid':42}}}
            raise AssertionError(operation)
        with sync_playwright() as p, patch.object(AccountClient,'request',side_effect=synthetic_official):
            browser=p.chromium.connect_over_cdp(os.environ.get('ZYB_TEST_CDP_URL','http://127.0.0.1:9222'))
            context=browser.new_context(viewport={'width':1280,'height':850})
            errors=[]
            try:
                context.grant_permissions(['clipboard-read','clipboard-write'])
                page=context.new_page();page.on('pageerror',lambda exc:errors.append(str(exc)))
                response=page.goto(self.base+'/',wait_until='networkidle')
                self.assertEqual(response.status,200,'浏览器面板入口尚未实现')
                page.screenshot(path=str(EVIDENCE/'browser-login.png'),full_page=True)
                page.locator('#admin-password').fill(self.password)
                page.locator('#login-submit').click()
                page.locator('#dashboard').wait_for(state='visible')
                self.assertIn('未配置',page.locator('#account-state').inner_text())
                page.locator('[data-tab="keys"]').click()
                page.locator('#key-name').fill('<img src=x onerror="window.PWNED=1">')
                page.locator('#create-key').click()
                page.locator('#new-key-secret').wait_for(state='visible')
                key=page.locator('#new-key-secret').input_value()
                self.assertTrue(key.startswith('zyb_'))
                page.locator('#copy-key').click()
                self.assertEqual(page.evaluate('navigator.clipboard.readText()'),key)
                page.locator('#dismiss-key').click()
                self.assertEqual(page.locator('#new-key-secret').input_value(),'')
                self.assertIsNone(page.evaluate('window.PWNED'))
                self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],200)
                page.reload(wait_until='networkidle')
                page.locator('#dashboard').wait_for(state='visible')
                self.assertNotIn(key,page.locator('body').inner_text())
                self.assertEqual(page.locator('#new-key-secret').input_value(),'')
                page.locator('[data-tab="account"]').click()
                page.locator('#profile-json').fill(json.dumps(SYNTHETIC_PROFILE))
                page.locator('#import-profile').click()
                page.wait_for_function("() => document.querySelector('#account-state').textContent.includes('已配置')")
                self.assertEqual(page.locator('#profile-json').input_value(),'')
                page.locator('#verify-account').click()
                page.wait_for_function("() => document.querySelector('#observations').textContent.includes('已验证')")
                page.locator('#refresh-account').click()
                page.wait_for_function("() => document.querySelector('#notice').textContent.includes('完成')")
                page.locator('#start-qr').click()
                page.locator('#qr-image').wait_for(state='visible')
                self.assertTrue(page.locator('#qr-image').get_attribute('src').startswith('data:image/png;base64,'))
                page.locator('#poll-qr').click()
                page.wait_for_function("() => document.querySelector('#qr-state').textContent.includes('登录成功')")
                self.assertEqual(page.locator('#qr-image').get_attribute('src'),None)
                self.assertTrue(page.locator('#poll-qr').is_disabled(),'扫码终态仍允许再次检查')
                self.assertTrue(page.locator('#cancel-qr').is_disabled(),'扫码终态仍允许取消')
                page.locator('#start-qr').click();page.locator('#qr-image').wait_for(state='visible')
                page.locator('#cancel-qr').click()
                page.wait_for_function("() => document.querySelector('#qr-state').textContent.includes('已取消')")
                self.assertTrue(page.locator('#poll-qr').is_disabled())
                self.assertTrue(page.locator('#cancel-qr').is_disabled())
                page.locator('[data-tab="settings"]').click()
                page.once('dialog',lambda dialog:dialog.accept())
                page.locator('#allow-external').check();page.locator('#save-settings').click()
                page.wait_for_function("() => document.querySelector('#access-state').textContent.includes('外部')")
                self.assertEqual(self.request('GET','/api/v1/status',headers={'Host':self.base.removeprefix('http://')},host=self.lan_ip())[0],401)
                page.locator('#allow-external').uncheck();page.locator('#save-settings').click()
                page.wait_for_function("() => document.querySelector('#access-state').textContent.includes('仅本机')")
                page.locator('[data-tab="history"]').click()
                page.locator('#history-source').select_option('external');page.locator('#history-filter').click()
                page.wait_for_function("() => document.querySelector('#history-rows').textContent.includes('external')")
                page.screenshot(path=str(EVIDENCE/'browser-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                page.locator('[data-tab="keys"]').click()
                page.once('dialog',lambda dialog:dialog.accept())
                page.locator('[data-revoke]').first.click()
                page.wait_for_function("() => document.querySelector('#key-list').textContent.includes('已吊销')")
                self.assertEqual(self.request('GET','/api/v1/status',headers={'Authorization':'Bearer '+key})[0],401)
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                page.screenshot(path=str(EVIDENCE/'browser-mobile.png'),full_page=True)
                page.locator('#logout').click();page.locator('#login-view').wait_for(state='visible')
                self.assertEqual(page.locator('#admin-password').input_value(),'')
                self.assertEqual(errors,[])
                (EVIDENCE/'browser-evidence.json').write_text(json.dumps({'tests':1,'assertions':['独立管理员登录/登出','Key一次展示/复制/刷新无回显/吊销','XSS名称转义','设备导入/检查/刷新','官方扫码合成确认/取消及终态按钮禁用','外部开关真实非loopback','历史来源过滤','390px无横溢出','零pageerror'],'screenshots':['browser-login.png','browser-desktop.png','browser-mobile.png'],'shared_browser_closed':False,'own_context_closed':True,'official_boundary':'SYNTHETIC only'},ensure_ascii=False,indent=2))
            finally:context.close()

if __name__=='__main__':unittest.main(verbosity=2)
