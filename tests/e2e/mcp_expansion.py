"""真实 SDK 与网页闭环：扩展权限、确认链接、PIN 回跳及重复决定。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)  # 同目录 mcp.py 不得遮蔽官方 SDK。
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
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


async def export_snapshot(server, key, board_id):
    async with _session(server.mcp_port, key['secret']) as client:
        result = await client.call_tool('export_board', {'board_id':board_id,'request_id':'web-snapshot'})
        assert not result.isError, str(result)
        return _json_result(result)


async def operation_status(server, key, operation_id):
    async with _session(server.mcp_port, key['secret']) as client:
        result = await client.call_tool('get_mcp_operation', {'operation_id': operation_id})
        assert not result.isError, str(result)
        return _json_result(result)['status']


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
            open_app(page, base, 'settings')
            page.click('[data-action="settings.mcpCreate"]')
            check('新增写权限默认不勾选，原两个权限保持默认', all(not page.locator('#'+id).is_checked() for id in ('st-mcp-scope-question','st-mcp-scope-update','st-mcp-scope-session','st-mcp-scope-report','st-mcp-scope-board','st-mcp-scope-delete'))
                  and page.locator('#st-mcp-scope-read').is_checked() and page.locator('#st-mcp-scope-draft').is_checked())
            page.click('dialog[open] [data-dialog-cancel]')
            page.click(f'[data-action="settings.mcpEdit"][data-arg="{key["key_id"]}"]')
            for id in ('st-mcp-scope-question','st-mcp-scope-draft','st-mcp-scope-update','st-mcp-scope-session','st-mcp-scope-report','st-mcp-scope-board','st-mcp-scope-delete'):
                page.locator('#'+id).check()
            page.click('dialog[open] [data-dialog-ok]')
            wait(page, "() => !document.querySelector('dialog[open]')")
            check('已有密钥网页编辑全部权限并立即生效', set(next(k for k in http(server, '/api/mcp/keys')['keys'] if k['key_id']==key['key_id'])['scopes']) == set(_SCOPES))
            before_learning = ledger.read_commits(server.vault)
            created, pending = pool.submit(lambda: asyncio.run(prepare(server, key, '网页删除验收', 'web-'))).result(timeout=30)
            check('SDK 预览返回主 Web 链接且未删除板', pending['status']=='pending_confirmation'
                  and pending['confirmation_url'].startswith(base+'/#/ai-review?operation=')
                  and boards.get_board(server.vault, created['board_id']) is not None)
            page.goto(pending['confirmation_url'], wait_until='networkidle')
            wait(page, "() => !!document.querySelector('#panel-ai-review [data-action=\"ai-review.approve\"]')")
            check('确认链接直接打开审核中心与影响预览', page.locator('.arv-operation').get_attribute('data-key') == 'operation-'+pending['operation_id']
                  and '网页删除验收' in page.locator('.arv-operation').inner_text())
            page.click('[data-action="ai-review.reject"]')
            page.locator('dialog[open] [data-dialog-ok]').click()
            wait(page, "() => document.querySelector('.arv-operation')?.textContent.includes('已拒绝')")
            check('网页拒绝后板保留、详情无确认按钮', boards.get_board(server.vault, created['board_id']) is not None
                  and not page.locator('[data-action="ai-review.approve"]').count())
            snapshot = pool.submit(lambda: asyncio.run(export_snapshot(server, key, created['board_id']))).result(timeout=30)
            open_app(page, base, 'history')
            if not page.locator('#history-tab-system').get_attribute('aria-selected') == 'true':
                page.click('[data-tab="system"]')
            seq = next(row['seq'] for row in runtime_records.list_records(server.vault,{})['records'] if row['tool']=='export_board')
            page.click(f'#runtime-timeline [data-seq="{seq}"] .hvw-row')
            link = page.locator('#history-system-panel a[download]')
            link.wait_for()
            with page.expect_download() as downloading:
                link.click()
            download = downloading.value
            with tempfile.TemporaryDirectory(prefix='omrs-snapshot-preview-') as folder:
                path=Path(folder)/'snapshot.html'; download.save_as(path)
                check('运行详情关联导出，浏览器下载自包含HTML', path.read_bytes().startswith(b'<!DOCTYPE html>')
                      and snapshot['export_id'] in link.get_attribute('href'))
                preview=ctx.new_page(); preview.on('pageerror',lambda err:errors.append(str(err)))
                preview.goto(path.as_uri(),wait_until='networkidle')
                wait(preview,'() => !!window.OMRS_LAYOUT')
                check('下载文件可脱离服务排版打印，且没有已打印写入入口', preview.evaluate('window.OMRS_LAYOUT.items.length')==2
                      and not preview.locator('#btnDone').count())
                preview.close()
            created2, pending2 = pool.submit(lambda: asyncio.run(prepare(server, key, 'PIN确认验收', 'pin-'))).result(timeout=30)
            http(server, '/api/auth/pin', {'pin': '2468', 'idle_minutes': 30})
            # 重启真实同进程服务，沿用本测试 Vault/端口/Key，不重建操作或导出。
            server.process.terminate(); server.process.wait(timeout=10); server._log.close()
            server.start()
            pending_status = pool.submit(lambda: asyncio.run(operation_status(server, key, pending2['operation_id']))).result(timeout=30)
            check('真实服务重启后仍待网页确认，板保持未删除', pending_status == 'pending_confirmation'
                  and boards.get_board(server.vault, created2['board_id']) is not None)
            snapshot_file = Path(server.vault)/'错题/.omrs/mcp_exports'/f'{snapshot["export_id"]}.html'
            snapshot_file.unlink()
            recovered = urllib.request.urlopen(snapshot['download_url']).read()
            check('重启后丢失的导出文件按SQLite原字节恢复', snapshot_file.read_bytes() == recovered
                  and hashlib.sha256(recovered).hexdigest() == snapshot['sha256'])
            for headers, expected in (({'X-Real-IP':'192.0.2.15'},401),({'Authorization':'Bearer '+key['secret']},403)):
                try:
                    urllib.request.urlopen(urllib.request.Request(snapshot['download_url'],headers=headers))
                    check('导出登录/凭据边界',False)
                except urllib.error.HTTPError as exc:
                    check(f'导出下载拒绝未登录或MCP凭据：{expected}',exc.code==expected)
            remote = browser.new_context(extra_http_headers={'X-Real-IP':'192.0.2.15'}, viewport={'width':390,'height':844})
            rp = remote.new_page(); rp.on('pageerror', lambda err: errors.append(str(err)))
            rp.goto(pending2['confirmation_url'], wait_until='networkidle')
            rp.wait_for_selector('#pin')
            rp.fill('#pin','2468')
            rp.locator('form button[type="submit"]').click()
            wait(rp, "() => !!document.querySelector('#panel-ai-review [data-action=\"ai-review.approve\"]')")
            check('远端 PIN 登录后回到同一确认操作，手机显示详情', rp.locator('.arv-operation').get_attribute('data-key') == 'operation-'+pending2['operation_id']
                  and rp.locator('.arv-operation').is_visible())
            response=remote.request.get(snapshot['download_url'])
            check('PIN网页会话可下载快照，响应禁止缓存',response.status==200 and response.headers.get('cache-control')=='no-store')
            rp.click('[data-action="ai-review.approve"]')
            wait(rp, "() => document.querySelector('.arv-operation')?.textContent.includes('已执行')")
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
        import traceback
        traceback.print_exception(exc)
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
