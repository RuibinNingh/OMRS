"""临时 Vault／随机端口／真实 Chromium 验证日志筛选、下载、重试及卸载。"""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from omrs.common import save_config

spec = importlib.util.spec_from_file_location('visual', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


def main():
    passed = []

    def check(label, condition):
        assert condition, label
        passed.append(label)
        print('PASS ' + label, flush=True)

    with tempfile.TemporaryDirectory(prefix='omrs-e2e-log-export-') as work:
        vault = Path(work) / 'vault'
        vault.mkdir()
        save_config(str(vault), {'train_dir': str(vault / 'empty-training'), 'inbox_local_detect_url': ''})
        long_name = 'sample-' + 'long-name-' * 12 + '.log'
        seeded = {'logs/sample-a.log': b'first\r\n', 'logs/sample-b.log': b'second\n',
                  f'logs/{long_name}': b'long-name\n', '错题/.omrs/logs/sample-agent.jsonl': b'{"synthetic":true}\n'}
        for index, (name, content) in enumerate(seeded.items()):
            path = vault / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            stamp = dt.datetime(2026, 10, 16 if index == 0 else 17, 1, tzinfo=dt.timezone.utc).timestamp()
            os.utime(path, (stamp, stamp))
        (vault / 'AI/logs').mkdir(parents=True)
        (vault / 'AI/logs/private.md').write_text('不在导出范围')
        shots = Path(os.environ.get('OMRS_LOG_EXPORT_SHOTS') or tempfile.mkdtemp(prefix='omrs-log-shots-'))
        shots.mkdir(parents=True, exist_ok=True)
        proc, port = visual.start_server(str(ROOT), str(vault), str(Path(work) / 'server.log'))
        base = f'http://127.0.0.1:{port}'
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = launch_chromium(p)
                context = browser.new_context(viewport={'width': 1440, 'height': 900}, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(10000)
                errors, downloads = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('download', lambda download: downloads.append(download))
                open_app(page, base, 'settings?section=service')

                def open_logs():
                    page.locator('[data-action="settings.logExport"]').click()
                    page.wait_for_function("document.querySelector('#st-log-list')?.getAttribute('aria-busy') === 'false'")

                def count_selected(count):
                    page.wait_for_function('(n) => document.querySelector("#st-log-summary")?.textContent.includes(`已选 ${n} 份`)', arg=count)

                open_logs()
                ok = page.locator('#st-log-dialog [data-dialog-ok]')
                check('日志窗口初始不勾选，导出按钮禁用', ok.is_disabled())
                page.keyboard.press('Enter')
                check('空选择时 Enter 不能绕过禁用状态', ok.is_disabled() and not downloads)
                page.fill('#st-log-query', 'sample')
                check('实际列表按文件名过滤且不含维护日志', page.locator('.st-log-row').count() == 4 and 'private.md' not in page.locator('#st-log-list').inner_text())
                page.select_option('#st-log-kind', 'ai')
                page.locator('[data-log-id="ai:sample-agent.jsonl"]').check()
                count_selected(1)
                page.select_option('#st-log-kind', 'runtime')
                check('跨类型筛选保留勾选并提示筛选外选择', '含筛选外 1 份' in page.locator('#st-log-summary').inner_text())
                page.fill('#st-log-since', '2026-10-16')
                page.fill('#st-log-until', '2026-10-16')
                check('开始与结束日期包含当天', page.locator('.st-log-row').count() == 1)
                page.locator('#st-log-all').check()
                count_selected(2)
                page.fill('#st-log-until', '2026-10-17')
                page.fill('#st-log-since', '2026-10-17')
                page.locator('[data-log-id="runtime:sample-b.log"]').check()
                check('全选复选框正确显示部分选中', page.locator('#st-log-all').evaluate('(el) => el.indeterminate'))
                page.locator('#st-log-all').check()
                count_selected(4)
                page.locator('#st-log-all').uncheck()
                count_selected(2)
                check('取消全选只取消当前筛选结果', '含筛选外 2 份' in page.locator('#st-log-summary').inner_text())
                page.fill('#st-log-query', 'no-match')
                check('筛选为空仍保留用户已选日志', '没有符合筛选条件' in page.locator('#st-log-list').inner_text() and not ok.is_disabled())
                page.click('#st-log-reset')
                check('重置筛选不清空勾选', page.locator('[data-log-id]:checked').count() == 2 and page.input_value('#st-log-since') == '')
                page.route('**/api/logs/export', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"合成打包失败"}'))
                ok.click()
                page.wait_for_function("document.querySelector('#st-log-status')?.textContent.includes('合成打包失败')")
                check('导出失败显示原因并保留选择供重试', page.locator('[data-log-id]:checked').count() == 2 and not ok.is_disabled())
                page.unroute('**/api/logs/export')
                with page.expect_download() as event:
                    ok.click()
                download = event.value
                target = Path(work) / 'download.zip'
                download.save_as(target)
                with zipfile.ZipFile(target) as archive:
                    check('真实 ZIP 只包含所选文件且原始字节不变', set(archive.namelist()) == {'运行日志/sample-a.log', 'AI请求日志/sample-agent.jsonl'}
                          and archive.read('运行日志/sample-a.log') == seeded['logs/sample-a.log']
                          and archive.read('AI请求日志/sample-agent.jsonl') == seeded['错题/.omrs/logs/sample-agent.jsonl'])
                page.locator('#st-log-dialog').wait_for(state='detached')
                check('成功下载后关闭窗口并显示实际导出数', '已导出 2 份日志' in page.locator('#svc-log-status').inner_text())
                page.wait_for_function('document.activeElement?.dataset.action === "settings.logExport"')
                check('关闭后焦点回到导出入口', True)

                page.route('**/api/logs', lambda route: route.fulfill(status=500, content_type='application/json', body='{"msg":"合成读取失败"}'))
                open_logs()
                check('清单初次读取失败提供原地重试且不能导出', '合成读取失败' in page.locator('#st-log-status').inner_text() and ok.is_disabled())
                page.unroute('**/api/logs')
                page.click('#st-log-refresh')
                page.locator('[data-log-id="runtime:sample-a.log"]').wait_for()
                page.locator('[data-log-id="runtime:sample-a.log"]').check()
                (vault / 'logs/sample-a.log').unlink()
                ok.click()
                page.wait_for_function("document.querySelector('#st-log-status')?.textContent.includes('已删除')")
                check('文件被删除时拒绝导出并保留选择', page.locator('[data-log-id]:checked').count() == 1)
                page.click('#st-log-refresh')
                page.wait_for_function("document.querySelector('#st-log-status')?.textContent.includes('已从选择中移除')")
                check('刷新移除不存在的选择并更新按钮', ok.is_disabled() and page.locator('[data-log-id]:checked').count() == 0)
                page.locator('[data-log-id="runtime:sample-b.log"]').check()
                page.route('**/api/logs', lambda route: route.fulfill(status=500, content_type='application/json', body='{"msg":"合成刷新失败"}'))
                page.click('#st-log-refresh')
                page.wait_for_function("document.querySelector('#st-log-status')?.textContent.includes('保留上次列表')")
                check('刷新失败保留已有列表与选择', page.locator('[data-log-id="runtime:sample-b.log"]').is_checked())
                page.unroute('**/api/logs')
                page.keyboard.press('Escape')
                page.locator('#st-log-dialog').wait_for(state='detached')

                page.route('**/api/logs', lambda route: route.fulfill(status=200, content_type='application/json', body='{"files":[],"max_bytes":268435456,"max_files":1000}'))
                open_logs()
                check('空日志列表说明产生条件且禁用选择与导出', '暂无可导出的日志' in page.locator('#st-log-list').inner_text() and ok.is_disabled() and page.locator('#st-log-all').is_disabled())
                page.keyboard.press('Escape')
                page.locator('#st-log-dialog').wait_for(state='detached')
                page.unroute('**/api/logs')

                pending = []
                def delayed_list(route):
                    if not pending:
                        pending.append(route)
                    else:
                        route.continue_()
                page.route('**/api/logs', delayed_list)
                with page.expect_request('**/api/logs'):
                    page.locator('[data-action="settings.logExport"]').click()
                page.wait_for_function("document.querySelector('#st-log-list')?.getAttribute('aria-busy') === 'true'")
                page.keyboard.press('Escape')
                page.locator('#st-log-dialog').wait_for(state='detached')
                open_logs()
                pending[0].fulfill(status=200, content_type='application/json', body=json.dumps({'files': [], 'max_bytes': 1000, 'max_files': 10}))
                check('关闭后迟到清单不覆盖新窗口', page.locator('[data-log-id="runtime:sample-b.log"]').count() == 1)
                page.unroute('**/api/logs')

                for theme in ('light', 'dark'):
                    for width in (1440, 390, 320):
                        page.set_viewport_size({'width': width, 'height': 900})
                        page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                        page.fill('#st-log-query', 'sample')
                        page.fill('#st-log-since', '2026-10-17')
                        page.fill('#st-log-until', '2026-10-17')
                        page.locator('[data-log-id="runtime:sample-b.log"]').check()
                        page.evaluate('document.fonts.ready')
                        audit = page.evaluate("""() => {
                          const panel = document.querySelector('#st-log-dialog .ui-dialog__panel');
                          const footer = document.querySelector('#st-log-dialog .ui-dialog__foot').getBoundingClientRect();
                          const buttons = [...panel.querySelectorAll('button')].filter(e => e.offsetWidth);
                          const list = document.querySelector('#st-log-list');
                          return {overflow: document.documentElement.scrollWidth > innerWidth + 1 || panel.scrollWidth > panel.clientWidth + 1 || list.scrollWidth > list.clientWidth + 1,
                            footer: footer.bottom <= innerHeight && footer.top >= 0,
                            small: buttons.filter(e => e.getBoundingClientRect().height < (innerWidth <= 760 ? 40 : 28)).length,
                            inline: [...panel.querySelectorAll('[style]')].filter(e => e.getAttribute('style').trim()).length};
                        }""")
                        check(f'{theme} {width}px 窗口无横溢、页脚可见且按钮可点', not audit['overflow'] and audit['footer'] and not audit['small'] and not audit['inline'])
                        page.screenshot(path=str(shots / f'logs-{theme}-{width}.png'))
                page.set_viewport_size({'width': 1440, 'height': 900})
                held = []
                page.route('**/api/logs/export', lambda route: held.append(route))
                ok.click()
                page.wait_for_function("document.querySelector('#st-log-dialog [data-dialog-ok]')?.getAttribute('aria-busy') === 'true'")
                check('导出中阻止重复提交与关闭', ok.is_disabled() and page.locator('#st-log-dialog [data-dialog-cancel]').first.is_disabled() and len(held) == 1)
                page.keyboard.press('Escape')
                check('导出中 Esc 不关闭窗口', page.locator('#st-log-dialog').is_visible())
                page.evaluate('window.__omrs.router.go("dashboard")')
                page.locator('#st-log-dialog').wait_for(state='detached')
                held[0].abort()
                check('离开设置页清理窗口且不触发额外下载', len(downloads) == 1)
                check('真实页面全程无脚本异常', not errors)
                context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print(f'日志导出 E2E：{len(passed)}/{len(passed)}；截图：{shots}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
