"""真实 SDK 与网页闭环：扩展权限、确认链接、PIN 回跳及重复决定。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)  # 同目录 mcp.py 不得遮蔽官方 SDK。
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium
from omrs import boards, ledger, runtime_records
from omrs.mcp.keys import create_key, _SCOPES
from test_mcp_protocol import MCPServerProcess, _session, _json_result


def http(server, path, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{server.web_port}'+path,
        data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def wait(page, expression, arg=None):
    page.wait_for_function(expression, arg=arg, timeout=12000)


async def prepare(server, key, name, request):
    async with _session(server.mcp_port, key['secret']) as client:
        async def call(tool, args):
            result = await client.call_tool(tool, args)
            assert not result.isError, str(result)
            return _json_result(result)
        listing = await call('list_boards', {})
        created = await call('create_board', {'name': name, 'uids': ['函数1', '力学1'],
            'expected_catalog_revision': listing['catalog_revision'], 'request_id': request+'create'})
        pending = await call('delete_board', {'board_id': created['board_id'], 'expected_revision': created['revision'],
            'expected_catalog_revision': created['catalog_revision'], 'request_id': request+'delete'})
        return created, pending


def main():
    from playwright.sync_api import sync_playwright
    server, checks = MCPServerProcess(), []
    check = lambda name, value: checks.append((name, bool(value)))
    try:
        server.start()
        base = f'http://127.0.0.1:{server.web_port}'
        key = create_key(server.vault, '网页权限验收', ['omrs:read'])
        with sync_playwright() as playwright, ThreadPoolExecutor(max_workers=1) as pool:
            browser = launch_chromium(playwright)
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = ctx.new_page(); errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.add_init_script("localStorage.setItem('omrs-settings-section','access')")
            page.goto(base+'/#/settings', wait_until='networkidle')
            page.click('[data-action="settings.mcpCreate"]')
            check('新增写权限默认不勾选，原两个权限保持默认', all(not page.locator('#'+id).is_checked() for id in ('st-mcp-scope-update','st-mcp-scope-report','st-mcp-scope-board','st-mcp-scope-delete'))
                  and page.locator('#st-mcp-scope-read').is_checked() and page.locator('#st-mcp-scope-draft').is_checked())
            page.click('dialog[open] [data-dialog-cancel]')
            page.click(f'[data-action="settings.mcpEdit"][data-arg="{key["key_id"]}"]')
            for id in ('st-mcp-scope-draft','st-mcp-scope-update','st-mcp-scope-report','st-mcp-scope-board','st-mcp-scope-delete'):
                page.locator('#'+id).check()
            page.click('dialog[open] [data-dialog-ok]')
            wait(page, "() => !document.querySelector('dialog[open]')")
            check('已有密钥网页编辑全部权限并立即生效', set(next(k for k in http(server, '/api/mcp/keys')['keys'] if k['key_id']==key['key_id'])['scopes']) == set(_SCOPES))
            before_learning = ledger.read_commits(server.vault)
            created, pending = pool.submit(lambda: asyncio.run(prepare(server, key, '网页删除验收', 'web-'))).result(timeout=30)
            check('SDK 预览返回主 Web 链接且未删除板', pending['status']=='pending_confirmation'
                  and pending['confirmation_url'].startswith(base+'/#/history?operation=')
                  and boards.get_board(server.vault, created['board_id']) is not None)
            page.goto(pending['confirmation_url'], wait_until='networkidle')
            wait(page, "() => !!document.querySelector('#history-system-panel [data-action=\"history.operationConfirm\"]')")
            check('确认链接直接打开系统运行详情和影响预览', pending['operation_id'] in page.locator('#history-system-panel').inner_text()
                  and '网页删除验收' in page.locator('#history-system-panel').inner_text())
            page.click('[data-action="history.operationReject"]')
            wait(page, "() => document.querySelector('[data-operation] h4')?.textContent.includes('已拒绝')")
            check('网页拒绝后板保留、详情无确认按钮', boards.get_board(server.vault, created['board_id']) is not None
                  and not page.locator('[data-action="history.operationConfirm"]').count())
            created2, pending2 = pool.submit(lambda: asyncio.run(prepare(server, key, 'PIN确认验收', 'pin-'))).result(timeout=30)
            http(server, '/api/auth/pin', {'pin': '2468', 'idle_minutes': 30})
            remote = browser.new_context(extra_http_headers={'X-Real-IP':'192.0.2.15'}, viewport={'width':390,'height':844})
            rp = remote.new_page(); rp.on('pageerror', lambda err: errors.append(str(err)))
            rp.goto(pending2['confirmation_url'], wait_until='networkidle')
            rp.wait_for_selector('#pin')
            rp.fill('#pin','2468')
            rp.locator('form button[type="submit"]').click()
            wait(rp, "() => !!document.querySelector('#history-system-panel [data-action=\"history.operationConfirm\"]')")
            check('远端 PIN 登录后回到同一确认操作，手机显示详情', pending2['operation_id'] in rp.locator('#history-system-panel').inner_text()
                  and rp.locator('#history-system-panel .hvw-detail-panel').is_visible())
            rp.click('[data-action="history.operationConfirm"]')
            wait(rp, "() => document.querySelector('[data-operation] h4')?.textContent.includes('已应用')")
            check('网页确认实际删除，重复确认只执行一次', boards.get_board(server.vault, created2['board_id']) is None
                  and http(server, '/api/mcp/operations/decide', {'operation_id': pending2['operation_id'], 'decision':'confirm'})['operation']['status']=='applied')
            rows = runtime_records.list_records(server.vault, {})['records']
            check('系统记录分开显示拒绝和应用，预览不算完成', {r['status'] for r in rows if r['tool']=='delete_board'}=={'applied','rejected'})
            check('草稿/展示板管理不改变学习 Ledger', ledger.read_commits(server.vault)==before_learning)
            check('网页全程无脚本错误', not errors)
            remote.close(); ctx.close()
            if not os.environ.get('OMRS_TEST_CDP_URL'):
                browser.close()
    except Exception as exc:
        checks.append(('主路径中断：'+str(exc)[:350], False))
    finally:
        server.stop()
    for name, ok in checks:
        print(('  ok    ' if ok else '  FAIL  ')+name)
    failures = sum(not ok for _, ok in checks)
    print(f'MCP 扩展网页 E2E：{len(checks)-failures} 通过 / {failures} 失败')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
