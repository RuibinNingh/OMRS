"""设置页：六分区、保存契约、备份与任务轮询、重启拦截和四档审计。"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium

spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)

AUDIT = """target => {
  const root = document.querySelector('#st-app');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('.katex'));
  const sizes = [...new Set(shown.filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
    .map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a,b) => a-b);
  const hit = e => ['BUTTON','INPUT','SELECT','SUMMARY'].includes(e.tagName) || e.getAttribute('role') === 'button';
  const small = shown.filter(hit).filter(e => { const r=e.getBoundingClientRect(); return r.width && r.height < target; })
    .map(e => `${e.tagName}#${e.id}.${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const inline = shown.filter(e => (e.getAttribute('style') || '').trim()).length;
  const handlers = shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length;
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible')
    .map(e => `${e.tagName}#${e.id}.${e.className}: ${e.scrollWidth}/${e.clientWidth}`);
  return { sizes, small, inline, handlers, over, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""


def wait(page, expression, timeout=8000):
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:
        return False


def guarded(results, label, action):
    try:
        action()
    except Exception as error:
        results.append((label + "：执行出错", False, repr(error)[:350]))


def run_tuning(page, results):
    def check(label, ok):
        results.append((label, bool(ok), ''))

    check('学习参数从服务端有效配置读取', wait(page, "() => !document.querySelector('#st-tuning-save')?.disabled")
          and page.locator('#st-tuning-card input[type=number]').count() == 19)
    page.fill('#st-tuning-high_score_threshold', '8')
    pending = []
    page.route('**/api/config', lambda route: pending.append(route) if route.request.method == 'POST' else route.continue_())
    page.click('#st-tuning-save')
    check('调参等待完整历史重算并锁定表单', wait(page, "() => document.querySelector('#st-tuning-status')?.textContent.includes('重算全部历史')")
          and page.locator('#st-tuning-save').is_disabled()
          and page.locator('#st-tuning-high_score_threshold').is_disabled())
    route = pending.pop()
    payload = route.request.post_data_json
    check('调参提交完整合法参数', len(payload['tuning']) == 19 and payload['tuning']['high_score_threshold'] == 8)
    response = route.fetch()
    data = response.json()
    route.fulfill(response=response)
    check('真实重算回执显示数量耗时和发布版本', wait(page, "() => document.querySelector('#st-tuning-status')?.textContent.includes('历史重算完成')")
          and data['recalculation']['status'] == 'complete'
          and str(data['recalculation']['questions']) + ' 题' in page.locator('#st-tuning-status').inner_text()
          and '秒；配置版本' in page.locator('#st-tuning-status').inner_text())
    check('调参保存后立即使用新参数', page.evaluate("async () => (await (await fetch('/api/config')).json()).tuning_effective.high_score_threshold === 8"))
    page.unroute('**/api/config')

    page.fill('#st-tuning-high_score_threshold', '9')
    page.route('**/api/config', lambda route: route.fulfill(status=409, content_type='application/json', body='{"msg":"配置发生变化"}')
               if route.request.method == 'POST' else route.continue_())
    page.click('#st-tuning-save')
    check('调参请求拒绝后保留输入和旧参数', wait(page, "() => document.querySelector('#st-tuning-status')?.textContent.includes('输入已保留')")
          and page.locator('#st-tuning-high_score_threshold').input_value() == '9'
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).tuning_effective.high_score_threshold === 8"))
    page.unroute('**/api/config')

    def mirror_pending(route):
        if route.request.method != 'POST':
            route.continue_()
            return
        response = route.fetch()
        data = response.json()
        route.fulfill(status=response.status, content_type='application/json', body=json.dumps({**data, 'mirror_pending': True}))
    page.route('**/api/config', mirror_pending)
    page.click('#st-tuning-save')
    check('重算已发布但镜像待同步时不误报失败', wait(page, "() => document.querySelector('#st-tuning-status')?.textContent.includes('配置镜像待同步')")
          and page.locator('#st-tuning-status').get_attribute('data-tone') == 'warning'
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).tuning_effective.high_score_threshold === 9"))
    page.unroute('**/api/config')

    page.fill('#st-tuning-high_score_threshold', '10')
    page.route('**/api/config', lambda route: route.abort('failed') if route.request.method == 'POST' else route.continue_())
    page.click('#st-tuning-save')
    check('网络中断未确认时明确待确认且输入保留', wait(page, "() => document.querySelector('#st-tuning-status')?.textContent.includes('结果待确认')")
          and page.locator('#st-tuning-high_score_threshold').input_value() == '10')
    page.unroute('**/api/config')

    def committed_then_disconnected(route):
        if route.request.method == 'POST':
            route.fetch()
            route.abort('failed')
        else:
            route.continue_()
    page.route('**/api/config', committed_then_disconnected)
    page.click('#st-tuning-save')
    check('回包中断后核验服务端实际重算成功', wait(page, "() => document.querySelector('#st-tuning-status')?.textContent.includes('已核验：历史重算完成')")
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).tuning_effective.high_score_threshold === 10"))
    page.unroute('**/api/config')


def run_main(page, base, results):
    def check(label, ok, detail=""):
        results.append((label, bool(ok), str(detail)))

    page.goto(base + '/#/settings', wait_until='networkidle')
    check('六分区首屏渲染且旧入口不在路由表', wait(page, "() => !!document.querySelector('#st-app .st-layout')")
          and page.locator('.st-nav-item').count() == 6)
    check('运行状态从真实隔离实例读取', wait(page, "() => document.querySelector('#st-runtime-state')?.textContent === '运行中'"))
    page.click('[data-action="settings.section"][data-arg="appearance"]')
    page.click('[data-action="settings.theme"][data-arg="light"]')
    check('主题存储与页面属性同步', page.evaluate("localStorage.getItem('omrs-theme') === 'light' && document.documentElement.dataset.theme === 'light'"))
    page.click('[data-action="settings.density"][data-arg="comfortable"]')
    check('密度存储与页面属性同步', page.evaluate("localStorage.getItem('omrs-density') === 'comfortable' && document.documentElement.dataset.density === 'comfortable'"))
    page.locator('#st-invert-img').check()
    check('反色存储与页面属性同步', page.evaluate("localStorage.getItem('omrs-invert-img') === '1' && document.documentElement.dataset.invertImg === '1'"))
    page.select_option('#st-ledger-time-zone', 'UTC')
    check('时区键名保持兼容', page.evaluate("localStorage.getItem('omrs-ledger-time-zone') === 'UTC'"))

    page.click('[data-action="settings.entryBackgroundMode"][data-arg="custom"]')
    png = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000000020001e221bc330000000049454e44ae426082')
    page.locator('#st-entry-background-file').set_input_files({'name': 'entry.png', 'mimeType': 'image/png', 'buffer': png})
    page.locator('#st-entry-background-blur').fill('32')
    check('入口背景本地预览和模糊参数同步', wait(page, "() => document.querySelector('#st-entry-background-preview img') && document.querySelector('#st-entry-background-blur-value')?.textContent === '32px'"))
    page.click('[data-action="settings.saveEntryBackground"]')
    check('入口自定义图片保存', wait(page, "() => document.querySelector('#st-entry-background-status')?.textContent.includes('已保存')")
          and page.evaluate("async () => { const c = await (await fetch('/api/config')).json(); return c.entry_background.mode === 'custom' && c.entry_background.blur_px === 32 && c.entry_background.asset.kind === 'image'; }"))
    page.click('[data-action="settings.entryBackgroundMode"][data-arg="black-hole"]')
    page.click('[data-action="settings.saveEntryBackground"]')
    check('入口背景切回黑洞并隐藏当前媒体', wait(page, "() => document.querySelector('#st-entry-background-status')?.textContent.includes('黑洞')")
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).entry_background.mode === 'black-hole'"))

    page.click('[data-action="settings.section"][data-arg="access"]')
    check('分区切换记忆', page.evaluate("localStorage.getItem('omrs-settings-section') === 'access'"))
    page.fill('#st-pin-new', '1234')
    page.click('[data-action="settings.savePin"]')
    check('PIN 设置成功且输入清空', wait(page, "() => document.querySelector('#st-pin-action-status')?.textContent.includes('PIN 已设置')")
          and page.locator('#st-pin-new').input_value() == '')
    page.fill('#st-lan-pin-exempt-cidrs', 'not-a-cidr')
    page.click('[data-action="settings.saveAccess"]')
    check('非法免 PIN 网段原地显示拒绝原因', wait(page, "() => document.querySelector('#st-net-status')?.textContent.includes('保存失败')"))
    page.fill('#st-lan-pin-exempt-cidrs', '192.168.9.0/24')
    restarts = []
    page.route('**/api/restart', lambda route: (restarts.append(route.request.url), route.fulfill(status=200, content_type='application/json', body='{"status":"ok"}')))
    page.click('[data-action="settings.saveAccess"]')
    check('只改免 PIN 网段保存后不重启', wait(page, "() => document.querySelector('#st-net-status')?.textContent.includes('立即生效')") and not restarts)
    page.unroute('**/api/restart')

    page.click('[data-action="settings.section"][data-arg="ai"]')
    check('AI 识别思考默认关闭', not page.locator('#st-ai-thinking').is_checked())
    page.locator('#st-ai-thinking').check()
    page.fill('#st-ai-key', 'test-only-key')
    page.fill('#st-ai-model', 'test-model')
    page.click('[data-action="settings.saveAi"]')
    check('AI 识别思考开关保存并回显', wait(page, "() => document.querySelector('#st-ai-thinking')?.checked")
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).ai_thinking === true"))
    check('AI Key 保存后不回显', wait(page, "() => document.querySelector('#st-ai-settings-status')?.textContent.includes('已保存')")
          and page.locator('#st-ai-key').input_value() == ''
          and '已配置' in page.locator('#st-ai-key-state').inner_text())
    page.click('[data-action="settings.clearKey"]')
    check('清除 AI Key 前有确认', wait(page, "() => !!document.querySelector('dialog[open]')"))
    page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
    check('取消清除后密钥仍配置', '已配置' in page.locator('#st-ai-key-state').inner_text())
    page.click('[data-action="settings.clearKey"]')
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('确认清除后状态更新', wait(page, "() => document.querySelector('#st-ai-key-state')?.textContent.includes('尚未配置')"))

    page.click('[data-action="settings.section"][data-arg="assistant"]')
    check('助手最大输出 Token 默认 10240', page.locator('#st-agent-max-output-tokens').input_value() == '10240')
    page.fill('#st-agent-max-output-tokens', '16384')
    page.click('[data-action="settings.saveAgent"]')
    check('助手最大输出 Token 保存并回显', wait(page, "() => document.querySelector('#st-agent-status')?.textContent.includes('已保存')")
          and page.locator('#st-agent-max-output-tokens').input_value() == '16384'
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).agent_max_output_tokens === 16384"))
    page.fill('#st-agent-max-output-tokens', '1.5')
    page.click('[data-action="settings.saveAgent"]')
    check('助手最大输出 Token 非整数原地拒绝', wait(page, "() => document.querySelector('#st-agent-status')?.textContent.includes('必须是')")
          and page.evaluate("async () => (await (await fetch('/api/config')).json()).agent_max_output_tokens === 16384"))

    page.click('[data-action="settings.section"][data-arg="data"]')
    check('存储摘要真实加载', wait(page, "() => document.querySelector('#opt-total')?.textContent !== '—'"))
    run_tuning(page, results)
    with page.expect_download() as backup:
        page.click('#svc-a-export')
    check('备份可下载 ZIP', backup.value.suggested_filename.endswith('.zip'))
    restore_calls = []
    page.route('**/api/backup/import', lambda route: route.fulfill(status=200, content_type='application/json',
        body=json.dumps({'restore_id': 'demo-restore', 'preview': {'files': 2, 'bytes': 2048, 'md_files': 1, 'image_files': 1}})))
    page.route('**/api/backup/restore', lambda route: (restore_calls.append(route.request.post_data),
        route.fulfill(status=200, content_type='application/json', body='{"question_count":1}')))
    page.locator('#opt-import-file').set_input_files({'name': 'backup.zip', 'mimeType': 'application/zip', 'buffer': b'PK\x05\x06' + b'\0' * 18})
    check('导入备份先确认上传', wait(page, "() => !!document.querySelector('dialog[open]')"))
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('校验后再确认覆盖', wait(page, "() => document.querySelector('dialog[open]')?.textContent.includes('恢复备份')"))
    page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
    check('取消恢复没有写入数据', wait(page, "() => document.querySelector('#svc-backup-status')?.textContent.includes('已取消')") and not restore_calls)
    page.unroute('**/api/backup/import'); page.unroute('**/api/backup/restore')

    counts = {'scan': 0, 'job': 0}
    def scan_route(route):
        counts['scan'] += 1
        route.fulfill(status=200, content_type='application/json', body=json.dumps({'job': {'job_id': 'demo-scan'}}))
    def job_route(route):
        counts['job'] += 1
        route.fulfill(status=200, content_type='application/json', body=json.dumps({'job': {
            'done': True, 'processed': 2, 'total': 2,
            'result': {'scan_id': 'demo', 'exact': False, 'candidate_count': 1, 'potential_bytes': 1000}}}))
    page.route('**/api/optimize/scan', scan_route)
    page.route('**/api/optimize/job?id=demo-scan', job_route)
    page.evaluate("document.querySelector('#opt-a-scan').classList.remove('disabled')")
    page.click('#opt-a-scan')
    check('图片扫描任务轮询结束并解锁压缩', wait(page, "() => document.querySelector('#opt-status')?.textContent.includes('快扫完成')")
          and counts['scan'] == 1 and counts['job'] >= 1
          and page.locator('#opt-a-compress').get_attribute('aria-disabled') == 'false')
    page.unroute('**/api/optimize/scan'); page.unroute('**/api/optimize/job?id=demo-scan')
    page.evaluate("location.hash = '#/reports'")
    check('离开设置页时卸载', wait(page, "() => document.querySelector('#panel-reports')?.classList.contains('active')"))
    page.evaluate("location.hash = '#/settings'")
    page.click('[data-action="settings.section"][data-arg="data"]')
    check('重新进入设置页仍保留扫描结果', wait(page, "() => document.querySelector('#opt-a-compress')?.getAttribute('aria-disabled') === 'false'"))

    page.click('[data-action="settings.section"][data-arg="service"]')
    package = io.BytesIO()
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('OMRS/SOURCE_EXPORT_MANIFEST.txt', '测试源码包')
    page.route('**/api/source/export', lambda route: route.fulfill(status=200,
        headers={'Content-Type': 'application/zip',
                 'Content-Disposition': 'attachment; filename="OMRS-source-sanitized-test.zip"'},
        body=package.getvalue()))
    with page.expect_download() as source:
        page.click('[data-action="settings.sourceExport"]')
    check('脱敏源码包可下载', source.value.suggested_filename.startswith('OMRS-source-sanitized'))
    page.unroute('**/api/source/export')

    # 主路径前面设置过 PIN；清掉测试凭据，避免后续重启 / 新上下文被入口锁屏挡住。
    page.evaluate("async () => fetch('/api/auth/disable', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})")
    calls = {'restart': 0, 'session': 0}
    page.route('**/api/restart', lambda route: (calls.__setitem__('restart', calls['restart'] + 1),
        route.fulfill(status=200, content_type='application/json', body='{"status":"ok"}')))
    def session_route(route):
        calls['session'] += 1
        instance = 'old' if calls['session'] <= 2 else 'new'
        route.fulfill(status=200, content_type='application/json', body=json.dumps({'status': 'ok', 'instance_id': instance}))
    page.route('**/api/auth/session', session_route)
    with page.expect_navigation(wait_until='domcontentloaded', timeout=12000):
        page.click('[data-action="settings.restart"]')
    check('重启请求被拦截', calls['restart'] == 1)
    check('旧实例未触发刷新，看到新实例才刷新', calls['session'] >= 3
          and wait(page, "() => document.querySelector('#st-app .st-layout') && window.location.hash === '#/settings'"))
    page.unroute('**/api/restart'); page.unroute('**/api/auth/session')


def audit_sections(browser, base, results):
    for theme in ('light', 'dark'):
        for mobile in (False, True):
            viewport = {'width': 390, 'height': 844} if mobile else {'width': 1440, 'height': 900}
            context = browser.new_context(viewport=viewport)
            context.add_init_script(f"localStorage.setItem('omrs-theme','{theme}');localStorage.setItem('omrs-density','comfortable')")
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/#/settings', wait_until='networkidle')
            wait(page, "() => !!document.querySelector('#st-app .st-layout')")
            for name in ('appearance', 'access', 'ai', 'assistant', 'data', 'service'):
                page.click(f'[data-action="settings.section"][data-arg="{name}"]')
                if name == 'data':
                    page.locator('.st-tuning-advanced').evaluate('(el) => { el.open = true; }')
                result = page.evaluate(AUDIT, 40 if mobile else 28)
                ok = len(result['sizes']) <= 6 and min(result['sizes']) >= 12 and not any(
                    result[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                results.append((f'{name} {theme} {"手机" if mobile else "桌面"}审计', ok, str(result)))
            results.append((f'{theme} {"手机" if mobile else "桌面"}无脚本错误', not errors, '; '.join(errors[:2])))
            context.close()


def main():
    os.environ.pop('OMRS_SYSTEMD_SERVICE', None)
    with tempfile.TemporaryDirectory(prefix='omrs-e2e-settings-') as work:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests', 'fixtures', 'make_vault.py'),
                        '--out', os.path.join(work, 'vault')], check=True, capture_output=True)
        proc, port = visual.start_server(ROOT, os.path.join(work, 'vault'), os.path.join(work, 'server.log'))
        base = f'http://127.0.0.1:{port}'
        results = []
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={'width': 1440, 'height': 900}, accept_downloads=True)
                page = context.new_page(); page.set_default_timeout(8000)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                guarded(results, '设置主路径', lambda: run_main(page, base, results))
                results.append(('主路径无脚本错误', not errors, '; '.join(errors[:3])))
                context.close()
                guarded(results, '分区审计', lambda: audit_sections(browser, base, results))
                browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
        for label, ok, detail in results:
            print(('PASS' if ok else 'FAIL') + ' ' + label + (': ' + detail if not ok else ''))
        print(f'设置页 E2E：{sum(ok for _, ok, _ in results)}/{len(results)}')
        return 0 if results and all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    sys.exit(main())
