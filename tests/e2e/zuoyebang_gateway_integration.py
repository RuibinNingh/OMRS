"""独立网关与 OMRS 真正联调；只替换官方网络，数据全为合成。"""
import argparse
import base64
import io
import http.client
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import urllib.request
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-source', type=Path, default=ROOT / 'services/zuoyebang')
    parser.add_argument('--with-prefix', action='store_true', help='在真实服务前加同域 /zuoyebang/ 反代边界')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.gateway_source.resolve()))
    from PIL import Image
    from playwright.sync_api import sync_playwright
    from omrs.server import OMRSHandler
    from omrs.zuoyebang import service_config
    from browser_runtime import launch_chromium, open_app
    from zuoyebang_fixtures import candidates, png, profile
    from zyb_gateway.config import Config
    from zyb_gateway.server import create_server

    args.out.mkdir(parents=True, exist_ok=True)
    checks, captured = [], []
    context = browser = None

    def check(name, condition):
        checks.append({'name': name, 'ok': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
        if not condition:
            raise AssertionError(name)

    def stop(server, thread):
        server.shutdown()
        server.server_close()
        thread.join(2)

    def start(server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        service_cleanup.callback(stop, server, thread)
        return f'http://127.0.0.1:{server.server_port}'

    class OfficialBoundary(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            captured.append(self.rfile.read(int(self.headers['Content-Length'])))
            payload = base64.b64encode(json.dumps(candidates(), ensure_ascii=False).encode()).decode()
            locations = [base64.b64encode(value.encode()).decode() for value in ('5@5@5@115@410@115@410@5', '5@125@5@235@410@235@410@125')]
            raw = json.dumps({'errNo': 0, 'data': {'encode': 1, 'answers': {
                'gzip': 0, 'mainPageInfo': [payload], 'locs': locations}}}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    real_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='dual-service-', dir=args.out) as temporary, ExitStack() as service_cleanup:
        temp = Path(temporary)
        upstream = start(ThreadingHTTPServer(('127.0.0.1', 0), OfficialBoundary))
        gateway = create_server(Config(data_dir=temp / 'gateway', port=0))
        gateway_base = start(gateway)
        if args.with_prefix:
            proxy_calls = []

            class PrefixProxy(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def do_GET(self):
                    self.forward()

                def do_POST(self):
                    self.forward()

                def forward(self):
                    if self.path == '/zuoyebang':
                        self.send_response(301)
                        self.send_header('Location', '/zuoyebang/')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    if not self.path.startswith('/zuoyebang/'):
                        self.send_error(404)
                        return
                    proxy_calls.append(self.path)
                    raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                    headers = {name: value for name, value in self.headers.items()
                               if name.lower() not in ('connection', 'content-length')}
                    headers['X-Forwarded-For'] = self.client_address[0]
                    connection = http.client.HTTPConnection('127.0.0.1', gateway.server_port, timeout=60)
                    try:
                        connection.request(self.command, self.path[len('/zuoyebang'):], raw or None, headers)
                        response = connection.getresponse()
                        body = response.read()
                        self.send_response(response.status)
                        for name, value in response.getheaders():
                            if name.lower() not in ('connection', 'content-length', 'server', 'date'):
                                if name.lower() == 'set-cookie':
                                    value = value.replace('Path=/', 'Path=/zuoyebang/')
                                self.send_header(name, value)
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        try:
                            self.wfile.write(body)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                    finally:
                        connection.close()

            proxy = ThreadingHTTPServer(('127.0.0.1', 0), PrefixProxy)
            proxy_base = start(proxy)
            gateway.allowed_hosts.add(f'127.0.0.1:{proxy.server_port}')
            gateway_base = proxy_base + '/zuoyebang'
        handler = type('IntegrationHandler', (OMRSHandler,), {
            'vault_path': str(temp / 'vault'), 'log_message': lambda *_: None})
        omrs_base = start(ThreadingHTTPServer(('127.0.0.1', 0), handler))

        class SyntheticOfficialOnly:
            def open(self, request, timeout):
                if request.full_url != 'https://aisearch.zuoyebang.com/search/submit/whole':
                    raise AssertionError('验收禁止访问真实官方地址')
                return real_opener.open(urllib.request.Request(
                    upstream + '/synthetic-official', data=request.data,
                    headers=dict(request.headers)), timeout=timeout)

        try:
            with patch('zyb_gateway.vendor.direct.urllib.request.build_opener',
                       return_value=SyntheticOfficialOnly()), sync_playwright() as playwright, ExitStack() as cleanup:
                browser = launch_chromium(playwright)
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    cleanup.callback(browser.close)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                cleanup.callback(context.close)
                panel = context.new_page()
                page = context.new_page()
                errors = []
                for item in (panel, page):
                    item.on('pageerror', lambda error: errors.append(str(error)))
                panel.goto(gateway_base)
                panel.fill('#admin-password', (temp / 'gateway' / 'admin-secret.txt').read_text().strip())
                panel.click('#login-submit')
                panel.wait_for_selector('#dashboard', state='visible')
                check('概览服务地址保留实际入口前缀',
                      panel.input_value('#service-address') == gateway_base)
                if args.with_prefix:
                    check('前缀面板登录Cookie限制到服务路径',
                          any(cookie['name'] == 'zyb_admin' and cookie['path'] == '/zuoyebang/'
                              for cookie in context.cookies()))
                panel.click('#hero-action')
                panel.click('#profile-paste summary')
                panel.fill('#profile-json', json.dumps(profile()))
                panel.click('#import-profile')
                panel.wait_for_function("() => document.querySelector('#notice').textContent.includes('已导入')")
                panel.click('[data-tab="keys"]')
                panel.click('#open-key')
                panel.fill('#key-name', 'SYNTHETIC 双项目验收')
                panel.click('#create-key')
                panel.wait_for_selector('#new-key', state='visible')
                key = panel.input_value('#new-key-secret')
                check('真实面板生成一次性调用密钥', bool(key))
                panel.click('#dismiss-key')
                check('关闭展示后面板清空密钥', panel.input_value('#new-key-secret') == '')

                open_app(page, omrs_base, 'settings')
                page.click('#st-tab-zuoyebang')
                page.wait_for_function("() => document.querySelector('#st-zyb-status').textContent.includes('已读取')")
                page.fill('#st-zyb-base', gateway_base)
                page.fill('#st-zyb-key', key)
                page.click('[data-action="settings.zybSave"]')
                page.wait_for_function("() => document.querySelector('#st-zyb-status').textContent.includes('已保存')")
                page.click('[data-action="settings.zybTest"]')
                page.wait_for_function("() => document.querySelector('#st-zyb-status').textContent.includes('已连接')")
                check('OMRS连接实际网关且测试不搜题', not captured)
                check('OMRS配置读取与页面均不回显Key', key not in page.content()
                      and key not in json.dumps(context.request.get(omrs_base + '/api/zuoyebang/service').json()))
                with page.expect_popup() as opened:
                    page.click('#st-zyb-panel')
                popup = opened.value
                popup.wait_for_load_state()
                check('管理入口打开真实面板且没有Key或opener', popup.url == gateway_base + '/'
                      and popup.title() == '作业帮网关 · 管理面板'
                      and popup.evaluate('window.opener === null'))
                popup.close()

                page.select_option('#st-zyb-mode', 'external')
                page.check('#st-zyb-private')
                page.click('[data-action="settings.zybSave"]')
                page.wait_for_function("() => document.querySelector('#st-zyb-status').textContent.includes('已保存')")
                page.click('[data-action="settings.zybTest"]')
                page.wait_for_function("() => document.querySelector('#st-zyb-status').textContent.includes('已连接')")
                check('外部可信内网模式复用实际网关协议',
                      service_config.snapshot(str(temp / 'vault')).mode == 'external')
                page.evaluate("window.__omrs.router.go('zuoyebang')")
                try:
                    page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).wait_for(timeout=10000)
                except Exception:
                    print('连接诊断', context.request.get(omrs_base + '/api/zuoyebang/status').json(),
                          page.inner_text('#zyb-account'), errors, flush=True)
                    raise
                original = png()
                page.locator('#zyb-image').set_input_files({
                    'name': 'SYNTHETIC-original.png', 'mimeType': 'image/png', 'buffer': original})
                page.get_by_role('button', name='开始搜题', exact=True).click()
                page.locator('.zyb-candidate').first.wait_for(timeout=20000)
                check('实际网关返回3个候选并按2个位置分组', page.locator('.zyb-candidate').count() == 2 and page.locator('[data-action="zuoyebang.zybRegion"]').count() == 2)
                check('网关解码坐标经OMRS归一化后显示两个题框', page.locator('#zyb-paper rect.crp-box').count() == 2)
                check('官方边界只调用一次且保留原图字节', len(captured) == 1 and original in captured[0])
                check('实际请求包含原图摘要、年级及签名而不传签名种子',
                      hashlib.md5(original).hexdigest().encode() in captured[0]
                      and b'name="gradeId"\r\n\r\n0' in captured[0]
                      and b'name="sign"' in captured[0]
                      and b'synthetic-signing-seed' not in captured[0])
                page.locator('.zyb-candidate').first.click()
                # 兼容显式渲染与选中自动渲染，始终等待真实后端生成图。
                render_button = page.locator('[data-action="zuoyebang.zybRender"]')
                if render_button.is_visible() and render_button.is_enabled():
                    render_button.click()
                page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalWidth === 1080", timeout=60000)
                page.get_by_role('button', name='答案与解析', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalHeight > 3000")
                raw = context.request.get(omrs_base + page.locator('#zyb-rendered-image').get_attribute('src')).body()
                with Image.open(io.BytesIO(raw)) as image:
                    check('两服务联调仍生成1080宽完整答案长图', image.width == 1080 and image.height > 3000)
                page.locator('[data-zyb-field="subject"]').fill('数学')
                page.locator('[data-zyb-field="category"]').fill('双服务验收')
                page.get_by_role('button', name='录入 OMRS', exact=True).click()
                page.locator('.zyb-result').wait_for(timeout=20000)
                questions = list((temp / 'vault' / '错题' / '数学').rglob('双服务验收[0-9]*.md'))
                check('人工核对入库只创建一题', len(questions) == 1)
                open_app(page, omrs_base, 'zuoyebang')
                page.get_by_role('button', name='已录入题库', exact=True).wait_for()
                check('刷新恢复回执并防重复创建',
                      page.get_by_role('button', name='已录入题库', exact=True).is_disabled()
                      and len(list((temp / 'vault' / '错题' / '数学').rglob('双服务验收[0-9]*.md'))) == 1)

                panel.click('[data-tab="history"]')
                panel.wait_for_function("() => !document.querySelector('#history-filter').disabled")
                panel.select_option('#history-action', 'search')
                panel.click('#history-filter')
                panel.wait_for_function("() => document.querySelector('#history-rows').textContent.includes('/api/v1/search')")
                check('实际面板可追溯搜题来源与IP', '本机 / local' in panel.inner_text('#history-rows')
                      and '127.0.0.1' in panel.inner_text('#history-rows'))
                panel.bring_to_front()
                panel.screenshot(path=str(args.out / 'gateway-history.png'), full_page=True)
                detail_button = panel.locator('[data-history-id]').first
                history_id = detail_button.get_attribute('data-history-id')
                detail_button.click()
                panel.wait_for_function("() => document.querySelector('#history-detail-image').naturalWidth > 0")
                check('真实面板详情显示搜题年级及题干答案',
                      '未指定' in panel.inner_text('#history-detail-meta')
                      and '等腰三角形' in panel.inner_text('#history-detail-results')
                      and '答案 / 解析' in panel.inner_text('#history-detail-results'))
                raw_reply = context.request.get(gateway_base + '/api/admin/history/' + history_id + '/image')
                check('管理员详情原图逐字节等于OMRS上传原件',
                      raw_reply.status == 200 and raw_reply.body() == original
                      and raw_reply.headers.get('cache-control') == 'no-store')
                panel.click('#history-detail-raw summary')
                panel.wait_for_function("() => document.querySelector('#history-detail-response').textContent.startsWith('{')")
                saved_response = json.loads(panel.inner_text('#history-detail-response'))
                check('详情完整保留真实签名解码返回的三条候选',
                      json.loads(saved_response['result']['data']['answers']['mainPageInfo'][0]) == candidates())
                panel.screenshot(path=str(args.out / 'gateway-search-detail.png'), full_page=True)
                panel.press('#history-dialog', 'Escape')
                check('关闭详情清除图片与返回内容',
                      panel.locator('#history-detail-image').get_attribute('src') is None
                      and not panel.inner_text('#history-detail-response'))
                page.bring_to_front()
                page.screenshot(path=str(args.out / 'omrs-created.png'), full_page=True)
                panel.click('[data-tab="keys"]')
                panel.locator('[data-revoke]').click()
                panel.click('#confirm-submit')
                panel.wait_for_function("() => document.querySelector('#notice').textContent.includes('已吊销')")
                reply = context.request.post(omrs_base + '/api/zuoyebang/service/test',
                                             headers={'Origin': omrs_base}, data={})
                check('面板吊销后OMRS连接立即失败且不泄漏Key', reply.status == 502
                      and '密钥无效' in reply.json()['msg'] and key not in reply.text())
                if args.with_prefix:
                    check('面板资源、管理、状态与原图搜题均保留反代前缀',
                          all('/zuoyebang/' + suffix in proxy_calls for suffix in (
                              'assets/panel.js', 'assets/panel.css', 'api/admin/login',
                              'api/v1/status', 'api/v1/search',
                              'api/admin/history/' + history_id,
                              'api/admin/history/' + history_id + '/image')))
                check('完整路径无浏览器脚本错误', not errors)
                print(f'{len(checks)}/{len(checks)} 项通过', flush=True)
        finally:
            (args.out / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
