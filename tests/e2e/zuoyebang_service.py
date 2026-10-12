"""临时 Vault 与两个真实 HTTP 服务：设置/切换/拒绝/面板/录入入口。"""
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from omrs.server import OMRSHandler
from omrs.zuoyebang import service_config, store
from tests.browser_runtime import launch_chromium, open_app
from tests.zuoyebang_gateway import SyntheticGateway, KEY
from tests.zuoyebang_fixtures import png


def main():
    from playwright.sync_api import sync_playwright
    output = Path(os.environ.get('OMRS_ZYB_SHOTS', Path(os.environ.get('TMPDIR', str(ROOT / '.venv'))) / 'omrs-service-e2e'))
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def check(name, valid):
        checks.append({'name': name, 'ok': bool(valid)})
        print(('PASS ' if valid else 'FAIL ') + name, flush=True)
        if not valid: raise AssertionError(name)
    def wait(page, text):
        page.wait_for_function('(text) => document.querySelector("#st-zyb-status")?.textContent.includes(text)', arg=text, timeout=8000)
    with tempfile.TemporaryDirectory(prefix='omrs-service-e2e-') as temp, SyntheticGateway() as gateway:
        gateway.responses['/'] = 200, '<!doctype html><title>合成管理面板</title><h1>合成管理面板</h1>'.encode(), {'Content-Type': 'text/html; charset=utf-8'}
        handler = type('TestServiceHandler', (OMRSHandler,), {'vault_path': temp, 'log_message': lambda *_: None})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        context = None
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page(); errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                open_app(page, base, 'settings')
                page.locator('#st-tab-zuoyebang').click(); wait(page, '已读取')
                check('七分区独立服务面板与密码框', page.locator('.st-nav-item').count() == 7 and page.locator('#st-zyb-key').get_attribute('type') == 'password')
                check('默认本地是独立8745网关', page.locator('#st-zyb-mode').input_value() == 'local' and page.locator('#st-zyb-base').input_value() == 'http://127.0.0.1:8745')
                page.fill('#st-zyb-base', gateway.url); page.fill('#st-zyb-key', KEY)
                page.locator('[data-action="settings.zybSave"]').click(); wait(page, '已保存')
                saved = service_config.snapshot(temp)
                check('保存回读真实私有配置且成功清空Key', saved.base_url == gateway.url and saved.api_key == KEY and page.locator('#st-zyb-key').input_value() == '')
                public = page.evaluate('async () => (await (await fetch("/api/zuoyebang/service")).json())')
                generic = page.evaluate('async () => (await (await fetch("/api/config")).json())')
                check('GET/通用配置/网页无Key泄漏', KEY not in json.dumps([public, generic]) and KEY not in page.content())
                page.locator('[data-action="settings.zybTest"]').click(); wait(page, '已连接')
                check('连接测试只GET网关状态且展示独立账号签名', [row['path'] for row in gateway.calls] == ['/api/v1/status'] and '账号：有效；签名：有效' in page.locator('#st-zyb-account').inner_text())
                with page.expect_popup() as popup:
                    page.locator('#st-zyb-panel').click()
                panel = popup.value; panel.wait_for_load_state()
                check('管理面板在新tab无Key且无opener', panel.url == gateway.url + '/' and panel.evaluate('window.opener === null') and page.url.startswith(base))
                panel.close()
                page.locator('[data-action="settings.zybSave"]').click(); wait(page, '已保存')
                check('留空保存保留Key', service_config.snapshot(temp).api_key == KEY)
                before = (store.root(temp) / 'service.json').read_bytes()
                page.fill('#st-zyb-base', 'http://169.254.169.254'); page.fill('#st-zyb-key', 'synthetic-edited')
                page.locator('[data-action="settings.zybSave"]').click()
                page.wait_for_function('() => document.querySelector("#st-zyb-status").dataset.tone === "danger"')
                check('拒绝元数据目标并保留地址/Key编辑与旧配置', page.locator('#st-zyb-base').input_value() == 'http://169.254.169.254' and page.locator('#st-zyb-key').input_value() == 'synthetic-edited' and (store.root(temp) / 'service.json').read_bytes() == before)
                page.locator('[data-action="settings.zybLoad"]').click(); wait(page, '已读取')
                page.select_option('#st-zyb-mode', 'external')
                page.locator('[data-action="settings.zybSave"]').click()
                page.wait_for_function('() => document.querySelector("#st-zyb-status").dataset.tone === "danger"')
                check('外部私网HTTP必须显式信任', service_config.snapshot(temp).mode == 'local')
                page.locator('#st-zyb-private').check(); page.locator('[data-action="settings.zybSave"]').click(); wait(page, '已保存')
                page.locator('[data-action="settings.zybTest"]').click(); wait(page, '已连接')
                check('外部模式经同一真实HTTP网关鉴权契约', service_config.snapshot(temp).mode == 'external' and gateway.calls[-1]['headers']['Authorization'] == 'Bearer ' + KEY)
                gateway.responses['/api/v1/status'] = 401, {'status': 'error', 'msg': KEY}, {}
                page.locator('[data-action="settings.zybTest"]').click(); wait(page, '密钥无效')
                check('吊销/错误Key不泄漏上游错误或判账号过期', '账号：有效' in page.locator('#st-zyb-account').inner_text() and KEY not in page.content())
                gateway.responses.pop('/api/v1/status')
                page.locator('[data-action="settings.zybClearKey"]').click(); page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
                check('清除Key取消无写入', bool(service_config.snapshot(temp).api_key))
                page.locator('[data-action="settings.zybClearKey"]').click(); page.locator('dialog[open] [data-dialog-ok]').click(); wait(page, '已清除')
                check('清除Key二次确认真实生效', not service_config.snapshot(temp).api_key)
                page.locator('dialog').wait_for(state='detached')
                page.fill('#st-zyb-key', KEY)
                page.locator('[data-action="settings.zybSave"]').click(); wait(page, '已保存')
                check('清除后重新保存Key', bool(service_config.snapshot(temp).api_key))
                for theme in ('light', 'dark'):
                    for width in (1440, 390, 320):
                        page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                        page.set_viewport_size({'width': width, 'height': 1000})
                        check(f'设置 {theme}/{width}无横溢', page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                        page.screenshot(path=str(output / f'service-{theme}-{width}.png'), full_page=True, animations='disabled')
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.locator('#st-tab-appearance').click()
                page.evaluate('window.__omrs.router.go("create")')
                page.locator('[data-action="create.stage"][data-arg="zuoyebang"]').click()
                try:
                    page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).wait_for(timeout=8000)
                except Exception:
                    print('DIAGNOSTIC', page.locator('#zyb-account').inner_text(), 'errors', errors,
                          'status', context.request.get(base + '/api/zuoyebang/status').json(), flush=True)
                    raise
                page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).click()
                check('录入服务菜单不再导入/扫码管理账号', page.locator('#zyb-profile, [data-action="create.zybLogin"]').count() == 0)
                gateway.responses['/api/v1/status'] = 401, {'status': 'error', 'msg': KEY}, {}
                page.evaluate('window.__omrs.router.go("questions"); window.__omrs.router.go("create")')
                page.get_by_role('button', name='作业帮服务 · 连接失败', exact=True).wait_for(timeout=8000)
                page.get_by_role('button', name='作业帮服务 · 连接失败', exact=True).click()
                check('同一配置连接失败保留此前观察且不宣称账号过期', '账号：有效；签名：有效' in page.locator('#zyb-account-panel').inner_text() and '账号：已过期' not in page.locator('#zyb-account-panel').inner_text())
                gateway.responses.pop('/api/v1/status')
                page.get_by_role('button', name='打开服务设置', exact=True).click()
                page.wait_for_selector('#st-sec-zuoyebang.active')
                check('录入入口直达作业帮设置分区', page.locator('#st-tab-zuoyebang').get_attribute('aria-selected') == 'true')
                page.fill('#st-zyb-key', 'synthetic-replacement-key')
                page.locator('[data-action="settings.zybSave"]').click(); wait(page, '已保存')
                page.evaluate('window.__omrs.router.go("create")')
                page.get_by_role('button', name='作业帮服务 · 连接失败', exact=True).wait_for(timeout=8000)
                page.get_by_role('button', name='作业帮服务 · 连接失败', exact=True).click()
                check('切换服务配置后连接失败不沿用旧网关账号观察', '账号：未知；签名：未知' in page.locator('#zyb-account-panel').inner_text())
                check('切换配置后连接失败仍可独立本地取图', page.get_by_role('button', name='打开摄像头', exact=True).is_enabled())
                page.get_by_role('button', name='上传图片', exact=True).click()
                calls_before = len(gateway.calls)
                page.locator('#zyb-image').set_input_files({'name': 'synthetic-source.png', 'mimeType': 'image/png', 'buffer': png()})
                page.locator('#zyb-source-preview img').wait_for()
                check('连接失败保留原图但不能沿用旧网关观察搜题', page.get_by_role('button', name='开始搜题', exact=True).is_disabled() and len(gateway.calls) == calls_before)
                page.screenshot(path=str(output / 'service-switched-error.png'), full_page=True, animations='disabled')
                check('无浏览器脚本错误', not errors)
                context.close(); context = None
                if not os.environ.get('OMRS_TEST_CDP_URL'): browser.close()
            print(f'{len(checks)}/{len(checks)} 项通过', flush=True)
        finally:
            (output / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
            server.shutdown(); server.server_close(); thread.join(2)


if __name__ == '__main__': main()
