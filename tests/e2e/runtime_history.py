"""隔离 Web + MCP：真实工具记录、人工入库关联、筛选竞争与响应式详情。"""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
# 同目录 mcp.py 不能遮蔽官方 SDK。
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium
from omrs import runtime_records
from omrs.mcp.keys import create_key
from test_mcp_protocol import MCP_AVAILABLE, MCPServerProcess, _json_result, _png, _session

spec = importlib.util.spec_from_file_location('history_e2e', ROOT / 'tests/e2e/history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
http, wait = history.http, history.wait

SYSTEM = '#history-system-panel'
LIST = SYSTEM + ' .hvw-node'
PANEL = SYSTEM + ' .hvw-detail-panel'


def system_page(page, base):
    page.goto(base + '/#/history', wait_until='networkidle')
    page.click('[data-tab="system"]')
    page.wait_for_load_state('networkidle')


def select(page, seq):
    page.locator(f'{LIST}[data-seq="{seq}"] .hvw-row').click()
    wait(page, "seq => document.querySelector('#history-system-panel .hvw-detail-panel')?.dataset.key === `detail-system-${seq}`", seq)


async def make_calls(server):
    args = {'subject': '数学', 'category': '运行关联验收', 'request_id': 'runtime-e2e',
            'blocks': [{'section': '题目', 'kind': 'text', 'text': '机密正文仅用于脱敏验证'},
                       {'section': '题目', 'kind': 'image', 'image': 0}],
            'images': [{'download_url': 'https://example.test/image?signature=private', 'file_id': 'runtime-image',
                        'data_base64': base64.b64encode(_png(20, 10)).decode()}], 'client_name': 'PRIVATE_CLIENT_NAME'}
    async with _session(server.mcp_port, server.keys['all']['secret']) as client:
        await client.list_tools()
        await client.call_tool('get_overview', {'subject': '数学'})
        await client.call_tool('get_overview', {'subject': '物理'})
        first = _json_result(await client.call_tool('create_draft', args))
        reused = _json_result(await client.call_tool('create_draft', args))
        await client.call_tool('get_draft', {'draft_id': first['draft_id']})
        for _ in range(64):
            await client.call_tool('get_overview', {'subject': '数学'})
    async with _session(server.mcp_port, server.keys['read']['secret']) as client:
        denied = await client.call_tool('create_draft', args)
    assert first['draft_id'] == reused['draft_id'] and reused['reused'] and denied.isError
    return first['draft_id'], args


def run_main(page, base, server, checks):
    check = lambda label, ok: checks.append((label, bool(ok)))
    system_page(page, base)
    check('空系统页有真实空态且读取不创建运行库', '暂无记录' in page.locator(SYSTEM).inner_text()
          and not Path(runtime_records.path(server.vault)).exists())
    # 同步 Playwright 自己持有事件循环，SDK 客户端在独立测试线程运行。
    with ThreadPoolExecutor(max_workers=1) as pool:
        draft_id, args = pool.submit(lambda: asyncio.run(make_calls(server))).result(timeout=60)
    all_data = http(server.web_port, '/api/runtime/records?limit=200')
    calls = all_data['records']
    created = next(row for row in reversed(calls) if row['tool'] == 'create_draft' and row['status'] == 'success')
    failed = next(row for row in calls if row['status'] == 'failure')
    check('官方 SDK 每次工具调用留下终态，握手和工具发现不冒充调用', len(calls) == 70
          and all_data['summary']['success'] == 69 and all_data['summary']['failure'] == 1)
    with sqlite3.connect(runtime_records.path(server.vault)) as db:
        stored = str(db.execute('SELECT * FROM records').fetchall())
    forbidden = [args['blocks'][0]['text'], args['images'][0]['download_url'], args['images'][0]['data_base64'],
                 args['client_name'], *(key['secret'] for key in server.keys.values())]
    check('真实调用的数据库没有密钥、正文、原图、签名 URL 或客户端自由文字', all(value not in stored for value in forbidden))
    page.click('#hist-app > .hvw .hvw-toolbar [data-action="history.refresh"]')
    check('首屏分页和汇总覆盖全部真实调用', wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 60")
          and '70 次调用' in page.locator(SYSTEM).inner_text())
    page.select_option('[data-change="history.key"]', failed['key_id'])
    check('密钥筛选在分页前执行', wait(page, "seq => document.querySelectorAll('#history-system-panel .hvw-node').length === 1 && document.querySelector('#history-system-panel .hvw-node')?.dataset.seq === String(seq)", failed['seq']))
    page.select_option('[data-change="history.status"]', 'failure')
    check('权限失败显示稳定原因，系统记录没有修正操作', wait(page, "() => document.querySelector('#history-system-panel .hvw-outcome')?.textContent.includes('缺少权限')")
          and not page.locator(PANEL + ' .hvw-ops').count())
    page.select_option('[data-change="history.key"]', '')
    page.select_option('[data-change="history.status"]', '')
    page.fill('[data-input="history.query"]', '运行关联验收')
    check('搜索能找到首屏以外的草稿调用', wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 3"))
    # 相同参数的被拒绝请求也匹配搜索；选择成功创建记录。
    select(page, created['seq'])
    check('调用详情包含耗时、密钥和当前草稿', wait(page, "() => !!document.querySelector('#history-system-panel [data-action=\"history.openDraft\"]')")
          and '待审核' in page.locator(PANEL).inner_text() and '创建待审核草稿' in page.locator(PANEL).inner_text())
    page.locator(PANEL + ' .hvw-details').first.locator('summary').click()
    detail_route = f'**/api/runtime/records/detail?seq={created["seq"]}'
    page.route(detail_route, lambda route: route.fulfill(status=503, json={'msg': '详情暂时离线'}))
    page.click('.hvw-toolbar [data-action="history.refresh"]')
    check('详情刷新失败保留已有信息和展开状态，可单独重试', wait(page, "() => document.querySelector('#history-system-panel .ui-status--danger')?.textContent.includes('详情暂时离线')")
          and page.locator(PANEL + ' .hvw-details').first.evaluate('el => el.open')
          and page.locator(PANEL + ' .hvw-details[open]').count() == 1
          and page.locator(PANEL + ' [data-action="history.openDraft"]').count() == 1)
    page.unroute(detail_route)
    page.locator(PANEL + ' [data-action="history.select"]').click()
    check('详情重试清除错误', wait(page, "() => !document.querySelector('#history-system-panel .ui-status--danger')"))
    page.locator(PANEL + ' [data-action="history.openDraft"]').click()
    page.wait_for_selector('.drf-detail')
    check('查看草稿跨页定位对应 MCP 草稿', '运行关联验收' in page.locator('.drf-detail').inner_text()
          and '来源：MCP' in page.locator('.drf-detail').inner_text())
    page.click('[data-action="create.draftCommit"]')
    check('从已有审核页人工入库成功', wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(el => el.textContent.includes('草稿已入库'))")
          and http(server.web_port, f'/api/drafts/item?id={draft_id}')['draft']['status'] == 'done')
    system_page(page, base)
    page.fill('[data-input="history.query"]', '运行关联验收')
    wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 3")
    select(page, created['seq'])
    check('重新读取详情能显示草稿已入库及后续人工操作', wait(page, "() => !!document.querySelector('#history-system-panel [data-action=\"history.learningRelated\"]')")
          and '已入库' in page.locator(PANEL).inner_text())
    linked = runtime_records.detail(server.vault, created['seq'])['related_commits'][0]['seq']
    page.click(PANEL + ' [data-action="history.learningRelated"]')
    check('调用跳转至人工入库节点并显示来源调用', wait(page, "seq => document.querySelector('#history-learning-panel .hvw-detail-panel')?.dataset.key === `detail-learning-${seq}` && !!document.querySelector('#history-learning-panel [data-action=\"history.runtimeRelated\"]')", linked))
    page.locator('#history-learning-panel [data-action="history.runtimeRelated"]').last.click()
    check('学习节点能返回首屏以外的来源调用，自动清除筛选', wait(page, "seq => document.querySelector('#history-system-panel .hvw-detail-panel')?.dataset.key === `detail-system-${seq}`", created['seq'])
          and page.locator('[data-input="history.query"]').input_value() == '')
    page.click(SYSTEM + ' [data-action="history.more"]')
    check('加载更早记录无重复且保留当前详情', wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 70")
          and page.locator(PANEL).get_attribute('data-key') == f'detail-system-{created["seq"]}')
    page.route('**/api/runtime/records?*', lambda route: route.fulfill(status=503, json={'msg': '运行记录离线'}))
    page.click('.hvw-toolbar [data-action="history.refresh"]')
    check('列表刷新失败保留全部翻页结果并显示原因', wait(page, "() => document.querySelector('#history-system-panel .ui-status--danger')?.textContent.includes('运行记录离线')")
          and page.locator(LIST).count() == 70)
    page.unroute('**/api/runtime/records?*')
    page.click('.hvw-toolbar [data-action="history.refresh"]')
    check('恢复刷新保留已加载范围', wait(page, "() => !document.querySelector('#history-system-panel .ui-status--danger')")
          and page.locator(LIST).count() == 70)
    return created


def run_race(page, server, checks):
    delayed = []
    def route_query(route):
        if 'q=%E6%95%B0%E5%AD%A6' in route.request.url:
            response = route.fetch()
            delayed.append((route, response.body()))
        else:
            route.continue_()
    page.route('**/api/runtime/records?*', route_query)
    initial = page.locator(LIST).count()
    page.fill('[data-input="history.query"]', '数学')
    page.wait_for_timeout(450)
    assert delayed, '搜索请求没有到达拦截器'
    page.fill('[data-input="history.query"]', '物理')
    delayed[0][0].fulfill(status=200, content_type='application/json', body=delayed[0][1])
    page.wait_for_timeout(60)
    checks.append(('搜索防抖期间旧响应失效，不覆盖正在输入的新条件', page.locator(LIST).count() == initial
                   and page.locator('[data-input="history.query"]').input_value() == '物理'))
    checks.append(('新条件完成后仅显示对应结果', wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 1 && document.querySelector('#runtime-timeline')?.textContent.includes('物理')")))
    page.unroute('**/api/runtime/records?*', route_query)
    page.select_option('[data-change="history.range"]', 'today')
    checks.append(('时间与搜索筛选可组合', wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 1")))
    page.fill('[data-input="history.query"]', '找不到的记录')
    checks.append(('筛选无匹配有明确空态', wait(page, "() => document.querySelector('#runtime-timeline .ui-empty')?.textContent.includes('没有匹配')")))
    page.fill('[data-input="history.query"]', '')
    page.select_option('[data-change="history.range"]', 'all')
    wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 60")


def run_live(page, server, checks):
    page.click(SYSTEM + ' [data-action="history.more"]')
    wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 70")
    # 长调用夹具：公开记录生命周期驱动真实页面轮询，不用假 API 响应。
    seq = runtime_records.begin(server.vault, 'get_overview', {'subject': '数学'}, server.keys['all'])
    page.click('.hvw-toolbar [data-action="history.refresh"]')
    wait(page, "seq => !!document.querySelector(`#runtime-timeline .hvw-node[data-seq='${seq}']`)", seq)
    select(page, seq)
    checks.append(('进行中状态可见', wait(page, "() => document.querySelector('#history-system-panel .hvw-detail-panel .hvw-state')?.textContent === '进行中'")))
    runtime_records.finish(server.vault, seq, 1800, {'total': 2})
    checks.append(('自动轮询更新列表和详情终态，保留已加载旧页', wait(page, "() => document.querySelector('#history-system-panel .hvw-detail-panel .hvw-state')?.textContent === '成功'", timeout=8000)
                   and page.locator(LIST).count() == 71))


def run_audits(browser, base, server, checks, output):
    created = next(row for row in reversed(runtime_records.list_records(server.vault, {'q': '运行关联验收'})['records'])
                   if row['status'] == 'success')
    for theme in ('light', 'dark'):
        for width, height, target in ((1440, 900, 28), (390, 844, 40)):
            ctx = browser.new_context(viewport={'width': width, 'height': height})
            ctx.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
            page = ctx.new_page()
            system_page(page, base)
            page.fill('[data-input="history.query"]', '运行关联验收')
            wait(page, "() => document.querySelectorAll('#history-system-panel .hvw-node').length === 3")
            first = created['seq']
            select(page, first)
            back_focused = page.locator(PANEL + ' .is-back').evaluate('el => el === document.activeElement')
            page.wait_for_selector(PANEL + ' .hvw-details')
            page.locator(PANEL + ' .hvw-details').first.locator('summary').click()
            audit = page.evaluate(history.AUDIT, target)
            ok = len(audit['sizes']) <= 6 and min(audit['sizes']) >= 12 and not any(
                audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
            checks.append((f'系统详情 {theme} {width}px 字号、目标、样式与溢出审计', ok))
            page.screenshot(path=str(output / f'system-{theme}-{width}.png'), full_page=True)
            if width == 390:
                checks.append((f'手机 {theme} 选择后切换至详情并聚焦返回按钮', not page.locator(SYSTEM + ' .hvw-list-column').is_visible()
                               and back_focused
                               and page.locator(PANEL).is_visible()))
                page.locator(PANEL + ' .is-back').click()
                checks.append((f'手机 {theme} 返回列表并还焦点', page.locator(SYSTEM + ' .hvw-list-column').is_visible()
                               and not page.locator(PANEL).is_visible()
                               and page.locator(f'{LIST}[data-seq="{first}"] .hvw-row').evaluate('el => el === document.activeElement')))
            ctx.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('SKIP 运行记录 E2E：可选依赖 playwright 未安装')
        return 0
    if not MCP_AVAILABLE:
        print('SKIP 运行记录 E2E：可选依赖 MCP SDK 未安装')
        return 0
    output = Path(tempfile.mkdtemp(prefix='omrs-runtime-history-shots-'))
    server, checks = MCPServerProcess(), []
    try:
        server.start()
        server.keys['all'] = create_key(server.vault, '外部助手', ['omrs:read', 'draft:create'])
        server.keys['read'] = create_key(server.vault, '仅查询', ['omrs:read'])
        base = f'http://127.0.0.1:{server.web_port}'
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = ctx.new_page(); page.set_default_timeout(10000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            history.guarded(checks, 'MCP 主路径', lambda: run_main(page, base, server, checks))
            history.guarded(checks, '筛选竞争', lambda: run_race(page, server, checks))
            history.guarded(checks, '状态轮询', lambda: run_live(page, server, checks))
            checks.append(('主路径无页面脚本错误', not errors))
            ctx.close()
            history.guarded(checks, '系统页审计', lambda: run_audits(browser, base, server, checks, output))
            # 验证真实 serve 启动恢复；只停止并重开本测试持有的子进程。
            pending = runtime_records.begin(server.vault, 'create_draft', {}, server.keys['all'])
            server.process.terminate(); server.process.wait(timeout=10); server._log.close()
            server.start()
            checks.append(('真实服务重启把未结束调用标记中断，历史终态保留', runtime_records.detail(server.vault, pending)['status'] == 'interrupted'
                           and runtime_records.list_records(server.vault, {})['summary']['success'] == 70))
            if not os.environ.get('OMRS_TEST_CDP_URL'):
                browser.close()
    finally:
        server.stop()
    failures = [row for row in checks if not row[1]]
    for row in checks:
        print(('  ok    ' if row[1] else '  FAIL  ') + row[0] + (f'：{row[2]}' if not row[1] and len(row) > 2 else ''))
    print(f'运行记录 E2E：{len(checks)-len(failures)} 通过 / {len(failures)} 失败')
    print(f'系统页截图：{output}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
