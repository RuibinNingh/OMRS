"""真实 Chromium 面板回归：合成官方边界、隔离私有目录与随机端口。
仅关闭自建 context；默认复用本机 9222，不关闭共享浏览器。
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path(os.environ.get('ZYB_TEST_EVIDENCE_DIR', str(ROOT / 'docs')))
EVIDENCE.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from tests.support import HttpCase
from tests.test_accounts import SYNTHETIC_PROFILE
from zyb_gateway.vendor.account import AccountClient
from zyb_gateway.vendor.direct import UpstreamError


# 按真实文字与祖先背景计算 WCAG 对比度；禁用控件不参与。
CONTRAST = r"""() => {
  const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
  const blend = (front, back) => {
    const a = front.length > 3 ? front[3] : 1;
    return front.slice(0,3).map((v,i) => v*a + back[i]*(1-a));
  };
  const luminance = color => color.map(c => c/255).map(c => c<=.04045 ? c/12.92 : ((c+.055)/1.055)**2.4)
    .reduce((a,c,i) => a+c*[.2126,.7152,.0722][i],0);
  const failures = [], ratios = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (el.closest('svg, [hidden], :disabled') || !el.checkVisibility() || !el.getClientRects().length) continue;
    const open = document.querySelector('dialog[open]');
    if (open && !open.contains(el)) continue;
    const hasText = [...el.childNodes].some(n => n.nodeType===3 && n.textContent.trim());
    if (!hasText && !el.matches('input,textarea,select')) continue;
    const chain = []; for (let p=el;p;p=p.parentElement) chain.unshift(p);
    let bg=[255,255,255]; for (const p of chain) bg=blend(rgb(getComputedStyle(p).backgroundColor),bg);
    const style=getComputedStyle(el), fg=blend(rgb(style.color),bg);
    const a=luminance(fg), b=luminance(bg), ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    const size=parseFloat(style.fontSize), large=size>=24 || (size>=18.66 && parseInt(style.fontWeight)>=700);
    const threshold=large ? 3 : 4.5;
    ratios.push(ratio);
    if (ratio+.01<threshold) failures.push({tag:el.tagName,id:el.id,class:el.className,ratio:+ratio.toFixed(2),threshold});
  }
  return {minimum:Math.min(...ratios), checked:ratios.length, failures};
}"""


class BrowserAcceptance(HttpCase):
    @contextmanager
    def panel(self):
        from playwright.sync_api import sync_playwright
        self.official_kind = 'ok'
        self.official_calls = []
        self.errors = []

        def official(operation, profile, params=None, **kwargs):
            self.official_calls.append(operation)
            if self.official_kind != 'ok':
                raise UpstreamError('SYNTHETIC-不可回显官方原文', 6, self.official_kind)
            if operation == 'qr_create':
                return {'errNo': 0, 'data': {'uuid': 'SYNTHETIC-BROWSER-CHALLENGE'}}
            if operation == 'qr_check':
                return {'errNo': 0, 'data': {'zybuss': 'SYNTHETIC-BROWSER-CONFIRMED'}}
            if operation == 'relogin':
                return {'errNo': 0, 'data': {'zybuss': 'SYNTHETIC-BROWSER-REFRESHED'}}
            if operation == 'userinfo':
                return {'errNo': 0, 'data': {'user': {'uid': 42}}}
            raise AssertionError(operation)

        with sync_playwright() as playwright, patch.object(AccountClient, 'request', side_effect=official):
            browser = playwright.chromium.connect_over_cdp(os.environ.get('ZYB_TEST_CDP_URL', 'http://127.0.0.1:9222'))
            context = browser.new_context(viewport={'width': 1280, 'height': 900}, color_scheme='dark')
            try:
                context.grant_permissions(['clipboard-read', 'clipboard-write'])
                page = context.new_page()
                page.on('pageerror', lambda error: self.errors.append(str(error)))
                page.set_default_timeout(10000)
                self.assertEqual(page.goto(self.base + '/', wait_until='networkidle').status, 200)
                yield context, page
                self.assertEqual(self.errors, [])
            finally:
                context.close()

    def login_panel(self, page):
        page.fill('#admin-password', self.password)
        page.click('#login-submit')
        page.locator('#dashboard').wait_for(state='visible')
        page.wait_for_function("() => !document.querySelector('#reload-state').disabled")
        self.assertTrue(page.locator('#tab-overview').is_visible())

    def import_panel(self, page, file=False):
        page.click('[data-tab="account"]')
        page.click('#open-profile')
        if file:
            page.locator('#profile-file').set_input_files({'name': 'SYNTHETIC-session.json', 'mimeType': 'application/json', 'buffer': json.dumps(SYNTHETIC_PROFILE).encode()})
        else:
            page.locator('#profile-paste summary').click()
            page.fill('#profile-json', json.dumps(SYNTHETIC_PROFILE))
        page.click('#import-profile')
        page.wait_for_function("() => !document.querySelector('#profile-dialog').open && !document.querySelector('#verify-account').disabled")
        self.assertEqual(page.input_value('#profile-json'), '')
        self.assertEqual(page.input_value('#profile-file'), '')

    def verify_panel(self, page):
        page.click('[data-tab="account"]')
        page.click('#verify-account')
        page.wait_for_function("() => !document.querySelector('#verify-account').disabled")

    def create_key(self, page, name='SYNTHETIC OMRS'):
        page.click('[data-tab="keys"]')
        page.click('#open-key')
        page.fill('#key-name', name)
        page.click('#create-key')
        page.locator('#new-key-secret').wait_for(state='visible')
        page.wait_for_function("() => !document.querySelector('#create-key').disabled")
        key = page.input_value('#new-key-secret')
        self.assertTrue(key.startswith('zyb_'))
        return key

    def test_real_workflow_states_keys_qr_access_and_history(self):
        with self.panel() as (context, page):
            page.screenshot(path=str(EVIDENCE / 'browser-login.png'), full_page=True)
            self.login_panel(page)
            self.assertIn('先配置设备', page.inner_text('#hero-title'))
            self.assertEqual(self.official_calls, [], '状态读取联系了官方')
            self.assertTrue(page.locator('[data-command="verify"]').first.is_disabled())
            page.click('#hero-action')
            page.locator('#profile-paste summary').click()
            page.fill('#profile-json', '{不是JSON}')
            page.click('#import-profile')
            page.wait_for_function("() => document.querySelector('#profile-dialog .dialog-notice').textContent.includes('JSON 不合法')")
            self.assertEqual(page.input_value('#profile-json'), '{不是JSON}')
            page.press('#profile-json', 'Escape')
            self.assertEqual(page.input_value('#profile-json'), '')
            self.assertEqual(page.evaluate('document.activeElement.id'), 'hero-action')
            self.import_panel(page, file=True)
            self.assertEqual(page.inner_text('#account-badge'), '待核对')
            self.assertEqual(page.inner_text('#signing-badge'), '待核对')
            self.assertEqual(self.official_calls, [], '导入联系了官方')
            page.click('#open-credential')
            page.fill('#account-credential', 'SYNTHETIC-manual-new-credential')
            page.click('#import-credential')
            page.wait_for_function("() => !document.querySelector('#credential-dialog').open")
            self.assertEqual(page.input_value('#account-credential'), '')
            self.verify_panel(page)
            self.assertEqual(page.inner_text('#account-badge'), '已验证')
            self.assertEqual(page.inner_text('#signing-badge'), '已验证')
            verified_at = page.inner_text('#summary-verified')
            self.official_kind = 'network'
            self.verify_panel(page)
            self.assertEqual(page.inner_text('#summary-verified'), verified_at)
            self.assertEqual(page.inner_text('#account-badge'), '已验证')
            self.assertIn('最近请求失败', page.inner_text('#hero-title'))
            self.assertNotIn('不可回显官方原文', page.inner_text('body'))
            self.official_kind = 'signing_session'
            self.verify_panel(page)
            self.assertEqual(page.inner_text('#account-badge'), '已验证')
            self.assertEqual(page.inner_text('#signing-badge'), '已确认失效')
            self.assertIn('签名会话需要更新', page.inner_text('#hero-title'))
            self.official_kind = 'ok'
            self.import_panel(page)
            self.verify_panel(page)
            self.official_kind = 'login_required'
            self.verify_panel(page)
            self.assertEqual(page.inner_text('#account-badge'), '已确认失效')
            self.assertEqual(page.inner_text('#signing-badge'), '已验证')
            self.assertIn('重新登录', page.inner_text('#hero-title'))
            self.official_kind = 'ok'
            page.click('#refresh-account')
            page.wait_for_function("() => !document.querySelector('#refresh-account').disabled")
            self.assertEqual(page.inner_text('#account-badge'), '已验证')
            hostile = '<img src=x onerror="window.PWNED=1">'
            key = self.create_key(page, hostile)
            page.click('#copy-key')
            self.assertEqual(page.evaluate('navigator.clipboard.readText()'), key)
            page.click('#dismiss-key')
            self.assertEqual(page.input_value('#new-key-secret'), '')
            self.assertIn(hostile, page.inner_text('#key-list'))
            self.assertIsNone(page.evaluate('window.PWNED'))
            self.assertEqual(self.request('GET', '/api/v1/status', headers={'Authorization': 'Bearer ' + key})[0], 200)
            page.reload(wait_until='networkidle')
            page.wait_for_function("() => !document.querySelector('#reload-state').disabled")
            self.assertEqual(page.input_value('#new-key-secret'), '')
            self.assertNotIn(key, page.content())
            self.assertIn('最近核对正常', page.inner_text('#hero-title'))
            self.assertEqual(page.input_value('#service-address'), self.base)
            page.click('[data-tab="account"]')
            page.click('#start-qr')
            page.locator('#qr-image').wait_for(state='visible')
            page.wait_for_function("() => !document.querySelector('#poll-qr').disabled")
            self.assertTrue(page.locator('#qr-image').get_attribute('src').startswith('data:image/png;base64,'))
            self.assertNotIn('qr_check', self.official_calls, '扫码被自动轮询')
            page.click('#poll-qr')
            page.wait_for_function("() => document.querySelector('#qr-state').textContent.includes('登录成功')")
            self.assertIsNone(page.locator('#qr-image').get_attribute('src'))
            self.assertTrue(page.locator('#poll-qr').is_disabled())
            self.assertTrue(page.locator('#cancel-qr').is_disabled())
            page.press('#qr-dialog', 'Escape')
            page.click('#start-qr')
            page.locator('#qr-image').wait_for(state='visible')
            page.click('#cancel-qr')
            page.wait_for_function("() => document.querySelector('#qr-state').textContent.includes('已取消')")
            self.assertTrue(page.locator('#poll-qr').is_disabled())
            page.press('#qr-dialog', 'Escape')
            page.click('[data-tab="settings"]')
            page.check('#allow-external')
            page.click('#save-settings')
            page.locator('#confirm-dialog').wait_for(state='visible')
            self.assertEqual(page.evaluate('document.activeElement.id'), 'confirm-cancel')
            page.click('#confirm-cancel')
            self.assertFalse(page.locator('#allow-external').is_checked())
            page.check('#allow-external')
            page.click('#save-settings')
            page.click('#confirm-submit')
            page.wait_for_function("() => document.querySelector('#access-state').textContent.includes('外部')")
            self.assertEqual(self.request('GET', '/api/v1/status', headers={'Host': self.base.removeprefix('http://')}, host=self.lan_ip())[0], 401)
            page.uncheck('#allow-external')
            page.click('#save-settings')
            page.wait_for_function("() => document.querySelector('#access-state').textContent.includes('仅本机')")
            page.click('[data-tab="history"]')
            page.select_option('#history-source', 'external')
            page.click('#history-filter')
            page.wait_for_function("() => document.querySelector('#history-rows').textContent.includes('external')")
            self.assertIn('客户端 ', page.inner_text('#history-rows'))
            self.assertIn('对端 ', page.inner_text('#history-rows'))
            page.select_option('#history-source', '')
            page.click('#history-filter')
            page.wait_for_function("() => !document.querySelector('#history-filter').disabled")
            self.assertFalse(page.locator('#next-page').is_disabled())
            page.click('#next-page')
            page.wait_for_function("() => document.querySelector('#history-page').textContent.includes('第 2 页')")
            page.click('#previous-page')
            page.wait_for_function("() => document.querySelector('#history-page').textContent.includes('第 1 页')")
            page.click('[data-tab="keys"]')
            page.locator('[data-revoke]').first.click()
            page.click('#confirm-cancel')
            self.assertEqual(self.request('GET', '/api/v1/status', headers={'Authorization': 'Bearer ' + key})[0], 200)
            page.locator('[data-revoke]').first.click()
            page.click('#confirm-submit')
            page.wait_for_function("() => document.querySelector('#key-list').textContent.includes('已吊销')")
            self.assertEqual(self.request('GET', '/api/v1/status', headers={'Authorization': 'Bearer ' + key})[0], 401)
            page.click('#logout')
            page.locator('#login-view').wait_for(state='visible')
            self.assertEqual(page.input_value('#admin-password'), '')
            self.assertEqual(page.input_value('#new-key-secret'), '')
            self.assertEqual(page.inner_text('#key-list'), '')

    def test_close_and_logout_discard_delayed_secrets_and_qr(self):
        with self.panel() as (context, page):
            self.login_panel(page)
            self.import_panel(page)
            pending = []

            def hold_key(route):
                if route.request.method == 'POST':
                    pending.append((route, route.fetch()))
                    page.evaluate("window.__heldResponse = 'key'")
                else:
                    route.continue_()

            page.route('**/api/admin/keys', hold_key)
            page.click('[data-tab="keys"]')
            page.click('#open-key')
            page.fill('#key-name', 'SYNTHETIC-close-during-create')
            page.click('#create-key')
            page.wait_for_function("() => window.__heldResponse === 'key'")
            self.assertEqual(len(pending), 1)
            route, response = pending.pop()
            missed_key = response.json()['key']
            page.press('#key-name', 'Escape')
            route.fulfill(response=response)
            page.wait_for_function("() => document.querySelector('#notice').textContent.includes('完整值已丢弃')")
            self.assertEqual(page.input_value('#new-key-secret'), '')
            self.assertNotIn(missed_key, page.content())
            self.assertFalse(page.locator('#key-dialog').is_visible())
            page.wait_for_function("() => !document.querySelector('#open-key').disabled")
            self.assertIn('SYNTHETIC-close-during-create', page.inner_text('#key-list'))
            page.unroute('**/api/admin/keys', hold_key)

            def hold_qr(route):
                if route.request.method == 'POST' and route.request.post_data_json.get('operation') == 'qr_start':
                    pending.append((route, route.fetch()))
                    page.evaluate("window.__heldResponse = 'qr'")
                else:
                    route.continue_()

            page.route('**/api/admin/account', hold_qr)
            page.click('[data-tab="account"]')
            page.click('#start-qr')
            page.locator('#qr-dialog').wait_for(state='visible')
            page.wait_for_function("() => window.__heldResponse === 'qr'")
            self.assertEqual(len(pending), 1)
            route, response = pending.pop()
            page.press('#qr-dialog', 'Escape')
            route.fulfill(response=response)
            page.wait_for_function("() => !document.querySelector('#start-qr').disabled")
            self.assertFalse(page.locator('#qr-dialog').is_visible())
            self.assertIsNone(page.locator('#qr-image').get_attribute('src'))
            stored_flow = json.loads(self.server.accounts.flow_path.read_text())
            self.assertEqual(stored_flow['state'], 'cancelled')
            page.unroute('**/api/admin/account', hold_qr)

            page.route('**/api/admin/keys', hold_key)
            page.evaluate('window.__heldResponse = null')
            page.click('[data-tab="keys"]')
            page.click('#open-key')
            page.fill('#key-name', 'SYNTHETIC-logout-during-create')
            page.click('#create-key')
            page.wait_for_function("() => window.__heldResponse === 'key'")
            self.assertEqual(len(pending), 1)
            route, response = pending.pop()
            late_key = response.json()['key']
            # 用另一个页面按钮发起退出，等同会话在弹窗期间失效。
            page.evaluate("document.querySelector('#logout').click()")
            page.locator('#login-view').wait_for(state='visible')
            route.fulfill(response=response)
            page.wait_for_load_state('networkidle')
            self.assertFalse(page.locator('#key-dialog').is_visible())
            self.assertEqual(page.input_value('#new-key-secret'), '')
            self.assertNotIn(late_key, page.content())
            self.assertEqual(page.inner_text('#key-list'), '')
            self.assertEqual(page.evaluate('Object.keys(localStorage).length'), 0)
            self.assertEqual(page.evaluate('Object.keys(sessionStorage).length'), 0)

    def test_read_failures_preserve_snapshot_and_session_expiry_clears_dialog(self):
        with self.panel() as (context, page):
            self.login_panel(page)
            self.import_panel(page)
            self.verify_panel(page)
            key = self.create_key(page)
            page.click('#dismiss-key')
            page.click('[data-tab="overview"]')

            def fail_account(route):
                route.fulfill(status=503, json={'status': 'error', 'msg': 'SYNTHETIC 读取失败'})

            page.route('**/api/admin/account', fail_account)
            page.click('#reload-state')
            page.wait_for_function("() => document.querySelector('#hero-title').textContent.includes('状态读取失败')")
            self.assertEqual(page.inner_text('#account-badge'), '已验证')
            self.assertEqual(page.inner_text('#signing-badge'), '已验证')
            self.assertIn('保留上次结果', page.inner_text('#last-read'))
            page.unroute('**/api/admin/account', fail_account)
            page.wait_for_function("() => !document.querySelector('#reload-state').disabled")
            page.click('#hero-action')
            page.wait_for_function("() => document.querySelector('#hero-title').textContent.includes('最近核对正常')")
            page.wait_for_function("() => !document.querySelector('#reload-state').disabled")

            def fail_keys(route):
                route.fulfill(status=503, json={'status': 'error', 'msg': 'SYNTHETIC 密钥读取失败'})

            page.route('**/api/admin/keys', fail_keys)
            page.click('#reload-state')
            page.wait_for_function("() => document.querySelector('#hero-title').textContent.includes('密钥状态读取失败')")
            self.assertIn('SYNTHETIC OMRS', page.inner_text('#key-list'))
            page.unroute('**/api/admin/keys', fail_keys)
            page.wait_for_function("() => !document.querySelector('#reload-state').disabled")
            page.click('#hero-action')
            page.wait_for_function("() => document.querySelector('#hero-title').textContent.includes('最近核对正常')")

            # 足够的合成请求使分页成立；下一页读取失败不能跳过该页。
            for _ in range(22):
                self.assertEqual(self.request('GET', '/api/v1/status', headers={'Authorization': 'Bearer ' + key})[0], 200)
            page.click('[data-tab="history"]')
            page.wait_for_function("() => !document.querySelector('#history-filter').disabled")
            first_rows = page.inner_text('#history-rows')

            def fail_history(route):
                route.fulfill(status=503, json={'status': 'error', 'msg': 'SYNTHETIC 记录读取失败'})

            page.route('**/api/admin/history?*', fail_history)
            page.click('#next-page')
            page.locator('#history-error').wait_for(state='visible')
            page.wait_for_function("() => !document.querySelector('#history-filter').disabled")
            self.assertEqual(page.inner_text('#history-rows'), first_rows)
            self.assertIn('第 1 页', page.inner_text('#history-page'))
            self.assertTrue(page.locator('#previous-page').is_disabled())
            page.unroute('**/api/admin/history?*', fail_history)
            page.click('#next-page')
            page.wait_for_function("() => document.querySelector('#history-page').textContent.includes('第 2 页')")
            page.click('[data-tab="overview"]')
            page.click('#hero-action')  # 账号页入口
            page.click('#open-credential')
            page.fill('#account-credential', 'SYNTHETIC-should-be-cleared')

            def expire_session(route):
                route.fulfill(status=401, json={'status': 'error', 'msg': '管理会话已过期'})

            page.route('**/api/admin/credential', expire_session)
            page.click('#import-credential')
            page.locator('#login-view').wait_for(state='visible')
            self.assertFalse(page.locator('#credential-dialog').is_visible())
            self.assertEqual(page.input_value('#account-credential'), '')
            self.assertEqual(page.inner_text('#key-list'), '')
            self.assertNotIn(key, page.content())

    def test_light_dark_desktop_mobile_focus_and_contrast(self):
        checks = []
        with self.panel() as (context, page):
            self.login_panel(page)
            self.import_panel(page)
            self.verify_panel(page)
            self.create_key(page)
            page.click('#dismiss-key')
            for theme in ('light', 'dark'):
                page.emulate_media(color_scheme=theme, reduced_motion='reduce')
                for width in (1280, 780, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 900 if width > 780 else 844})
                    for tab in ('overview', 'account', 'keys', 'history', 'settings'):
                        page.click('[data-tab="' + tab + '"]')
                        page.wait_for_function("() => !document.querySelector('#history-filter').disabled")
                        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme, width, tab))
                        contrast = page.evaluate(CONTRAST)
                        self.assertEqual(contrast['failures'], [], (theme, width, tab, contrast['failures']))
                        checks.append({'theme': theme, 'width': width, 'page': tab, 'contrast': contrast})
                        if tab == 'overview' and width in (1280, 390):
                            page.screenshot(path=str(EVIDENCE / f'panel-{theme}-{width}.png'), full_page=True)
                    if width in (1280, 320):
                        for tab, trigger, dialog in [('account', '#open-profile', 'profile-dialog'), ('account', '#open-credential', 'credential-dialog'), ('account', '#start-qr', 'qr-dialog'), ('keys', '#open-key', 'key-dialog')]:
                            page.click('[data-tab="' + tab + '"]')
                            page.click(trigger)
                            if dialog == 'qr-dialog':
                                page.locator('#qr-image').wait_for(state='visible')
                                page.wait_for_function("() => !document.querySelector('#poll-qr').disabled")
                            self.assertTrue(page.evaluate('id => document.querySelector("#"+id).contains(document.activeElement)', dialog))
                            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                            self.assertEqual(page.evaluate(CONTRAST)['failures'], [])
                            page.screenshot(path=str(EVIDENCE / f'{dialog}-{theme}-{width}.png'), full_page=True)
                            page.press('#' + dialog, 'Escape')
                            self.assertEqual(page.evaluate('document.activeElement.id'), trigger[1:])
                            page.wait_for_function("() => !document.querySelector('#open-profile').disabled")
            (EVIDENCE / 'panel-layout-evidence.json').write_text(json.dumps({'states': checks, 'shared_browser_closed': False, 'own_context_closed': True, 'official_boundary': 'SYNTHETIC only'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    unittest.main(verbosity=2)
