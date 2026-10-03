"""真实 SDK 创建正式调度，网页授权/反馈/撤销与 MCP 查询闭环。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from browser_runtime import launch_chromium, open_app
from omrs.creation import create_question
from omrs.ledger import read_commits
from omrs.mcp.keys import create_key
from test_mcp_protocol import MCPServerProcess, _session, _json_result


async def tools(server, secret):
    async with _session(server.mcp_port, secret) as client:
        return [tool.name for tool in (await client.list_tools()).tools]


async def call(server, secret, name, args):
    async with _session(server.mcp_port, secret) as client:
        result = await client.call_tool(name, args)
        if result.isError:
            raise AssertionError(str(result))
        return _json_result(result)


def http(server, path, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{server.web_port}' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main():
    from playwright.sync_api import sync_playwright
    server, checks = MCPServerProcess(), []
    def check(name, value):
        checks.append((name, bool(value)))
    try:
        created_questions = [create_question(server.vault, '数学', '网页调度', 5,
                                             question_text='网页调度题', answer_text='答案') for _ in range(2)]
        server.start()
        key = create_key(server.vault, '网页调度授权', ['omrs:read'])
        base = f'http://127.0.0.1:{server.web_port}'
        with sync_playwright() as playwright, ThreadPoolExecutor(max_workers=1) as pool:
            sdk = lambda fn, *args: pool.submit(asyncio.run, fn(server, key['secret'], *args)).result(timeout=30)
            check('旧只读密钥不发现创建调度', 'create_review_session' not in sdk(tools))
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.add_init_script("localStorage.setItem('omrs-settings-section','access')")
            open_app(page, base, 'settings')
            page.click('[data-action="settings.mcpCreate"]')
            check('创建窗口的调度写权限默认关闭', not page.locator('#st-mcp-scope-session').is_checked())
            page.click('dialog[open] [data-dialog-cancel]')
            page.wait_for_function("() => !document.querySelector('dialog[open]:not(.is-closing)')")
            page.click(f'[data-action="settings.mcpEdit"][data-arg="{key["key_id"]}"]')
            check('旧密钥编辑窗口不自动勾选调度权限', not page.locator('#st-mcp-scope-session').is_checked())
            page.check('#st-mcp-scope-session')
            page.click('dialog[open] [data-dialog-ok]')
            page.wait_for_function("() => !document.querySelector('dialog[open]:not(.is-closing)')")
            check('网页授权后 SDK 实时发现创建工具', 'create_review_session' in sdk(tools))
            recommendations = sdk(call, 'get_recommendations', {'category': '网页调度', 'count': 2})['selection']
            check('推荐清单提供稳定身份', {item['question_id'] for item in recommendations} == {q['question_id'] for q in created_questions})
            request = {'items': recommendations, 'request_id': 'web-sdk-plan'}
            made = sdk(call, 'create_review_session', request)
            sid = made['session_id']
            check('SDK 创建两题正式 EXP 计划', sid.startswith('EXP-') and made['count'] == 2 and not made['reused'])
            open_app(page, base, 'schedule')
            page.click('#sch-tab-plans')
            page.wait_for_selector(f'.schd-plan[data-arg="{sid}"]')
            page.click(f'.schd-plan[data-arg="{sid}"]')
            page.wait_for_function("id => document.getElementById('sch-plan-detail').textContent.includes(id)", arg=sid)
            check('网页已有计划展示 MCP 创建的计划和题目', page.locator('#sch-plan-detail .schd-q').count() == 2)
            check('网页显示初始反馈进度', '已录入 0 / 共 2 题' in page.locator('#sch-plan-detail').inner_text())
            repeated = sdk(call, 'create_review_session', request)
            check('SDK 重试复用网页中的计划', repeated['session_id'] == sid and repeated['reused'])
            response = http(server, '/api/feedback', {'session_id': sid,
                'feedbacks': [{'question_id': recommendations[0]['question_id'], 'sub_score': 5, 'is_correct': True}]})
            check('既有网页反馈接口可录入 MCP 计划', response['results'][0]['status'] == 'ok')
            open_app(page, base, 'schedule')
            page.click('#sch-tab-plans')
            page.click(f'.schd-plan[data-arg="{sid}"]')
            page.wait_for_function("() => document.getElementById('sch-plan-detail').textContent.includes('已录入 1 / 共 2 题')")
            detail = sdk(call, 'get_session', {'session_id': sid})
            check('网页和 MCP 反馈进度一致', detail['feedback_count'] == 1 and detail['pending_count'] == 1 and detail['status'] == 'active')
            page.click('[data-action="schedule.remove"]')
            page.click('dialog[open] [data-dialog-ok]')
            page.wait_for_function("id => !document.querySelector(`.schd-plan[data-arg=\"${id}\"]`)", arg=sid)
            check('网页撤销后 MCP 重试不复活计划', sdk(call, 'create_review_session', request)['status'] == 'retracted')
            check('重复与撤销重试仅一份创建事实', sum(c['commit_type'] == 'session.create' and c['payload'].get('session', {}).get('session_id') == sid
                                                     for c in read_commits(server.vault)) == 1)
            check('完整闭环无页面脚本错误', not errors)
            context.close()
            browser.close()
    finally:
        server.stop()
    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    print(f'{sum(ok for _, ok in checks)}/{len(checks)}')
    return 0 if checks and all(ok for _, ok in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
