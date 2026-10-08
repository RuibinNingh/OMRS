"""MCP 原生题图与 OMRS 草稿区真实 SDK / 浏览器验收。

脚本在临时 Vault 内启动同进程 Web + MCP，先由官方 MCP SDK 按题目图片
下标读取原生图片并比对原字节，再创建草稿、打开 OMRS 草稿区确认人工审核
入口、MCP 来源和完整原图。生产服务和真实 ``错题/`` 永远不会被访问；
缺少可选 SDK 或浏览器时会清楚地打印 SKIP，交付验收不能以 SKIP 代替通过。
"""

import asyncio
import base64
import datetime
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 脚本也叫 mcp.py；移除自身目录，避免它遮蔽官方 mcp SDK 包。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0]) == _SCRIPT_DIR:
    sys.path.pop(0)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    PlaywrightTimeoutError = Exception

from browser_runtime import launch_chromium

# 截图是合成验收产物，使用遵守 TMPDIR 的唯一目录，不覆盖共享 /tmp 文件。
_SCREENSHOT_DIR = tempfile.mkdtemp(prefix="omrs-mcp-e2e-")
from omrs.agent.tools import read as read_tools
from omrs.creation import create_question
from omrs.ledger import read_commits
from omrs.mcp.keys import create_key, verify_key
try:
    from test_mcp_protocol import MCP_AVAILABLE, MCPServerProcess, _gif, _jpeg, _json_result, _png, _session
except ImportError:
    from tests.test_mcp_protocol import MCP_AVAILABLE, MCPServerProcess, _gif, _jpeg, _json_result, _png, _session


def run_key_ui(page, base, server, checks):
    def check(label, ok):
        checks.append((label, bool(ok)))

    page.goto(base + "/#/settings", wait_until="networkidle")
    page.click('[data-action="settings.section"][data-arg="access"]')
    page.wait_for_selector('.st-mcp-key')
    check("MCP 首屏为密钥管理，创建表单按需打开", page.locator('#st-mcp-name').count() == 0)
    page.click('.st-mcp-intro [data-action="settings.mcpCreate"]')
    page.wait_for_selector('#st-mcp-dialog')
    check("创建窗口聚焦名称，权限控件尺寸紧凑", page.locator('#st-mcp-name').evaluate('el => el === document.activeElement')
          and page.locator('#st-mcp-scope-read').evaluate('el => el.getBoundingClientRect().height < 28'))
    page.locator('#st-mcp-scope-read').uncheck()
    page.locator('#st-mcp-scope-draft').uncheck()
    page.locator('#st-mcp-dialog [data-dialog-ok]').click()
    page.wait_for_function("() => document.querySelector('#st-mcp-create-status')?.textContent.includes('至少选择')")
    check("至少一项权限校验留在创建窗口", page.locator('#st-mcp-dialog').is_visible())
    page.locator('#st-mcp-scope-read').check()
    page.locator('#st-mcp-scope-draft').check()
    page.select_option('#st-mcp-expiry-kind', 'custom')
    page.fill('#st-mcp-expires', '2000-01-01T00:00')
    page.locator('#st-mcp-dialog [data-dialog-ok]').click()
    page.wait_for_function("() => document.querySelector('#st-mcp-create-status')?.textContent.includes('晚于当前')")
    check("过去的到期时间原地拒绝", page.locator('#st-mcp-dialog').is_visible())
    page.select_option('#st-mcp-expiry-kind', 'never')
    page.fill('#st-mcp-name', '浏览器创建 Key')

    def create_failure(route):
        if route.request.method == 'POST':
            route.fulfill(status=500, content_type='application/json', body=json.dumps({'msg': '模拟创建失败'}))
        else:
            route.continue_()
    page.route('**/api/mcp/keys', create_failure)
    page.locator('#st-mcp-dialog [data-dialog-ok]').click()
    page.wait_for_function("() => document.querySelector('#st-mcp-create-status')?.textContent.includes('创建失败')")
    check("创建失败保留名称和权限，可继续重试", page.locator('#st-mcp-name').input_value() == '浏览器创建 Key'
          and page.locator('#st-mcp-scope-draft').is_checked())
    page.unroute('**/api/mcp/keys', create_failure)
    page.locator('#st-mcp-dialog [data-dialog-ok]').click()
    page.wait_for_function("() => document.querySelector('#st-mcp-secret-value')?.value.startsWith('omrs_mcp_')")
    secret = page.locator('#st-mcp-secret-value').input_value()
    row = verify_key(server.vault, secret)
    check("设置 UI 创建真实 Key 且仅创建时显示明文", bool(row) and page.locator('#st-mcp-secret').is_visible())
    check("浏览器未持久化明文 Key", page.evaluate("secret => !JSON.stringify([localStorage,sessionStorage]).includes(secret)", secret))
    page.click('[data-action="settings.mcpCopy"]')
    page.wait_for_function("() => !!document.querySelector('#st-mcp-secret-status')?.textContent")
    check("复制密钥有可见结果反馈", bool(page.locator('#st-mcp-secret-status').inner_text()))
    secret_input = page.locator('#st-mcp-secret-value').element_handle()
    page.locator('#st-mcp-dialog [data-dialog-ok]').click()
    page.wait_for_selector('#st-mcp-dialog', state='detached')
    check("关闭窗口同时清空输入值与 value 属性", secret_input.evaluate("el => el.value === '' && !el.hasAttribute('value')"))
    page.reload(wait_until='networkidle')
    page.wait_for_selector(f'.st-mcp-key[data-key="{row["key_id"]}"]')
    check("刷新只能看到 Key 元数据", page.locator('#st-mcp-secret-value').count() == 0)

    page.click(f'[data-action="settings.mcpRevoke"][data-arg="{row["key_id"]}"]')
    page.wait_for_selector('#st-mcp-revoke-dialog')
    check("吊销确认显示名称并默认聚焦保留", '浏览器创建 Key' in page.locator('#st-mcp-revoke-dialog').inner_text()
          and page.locator('#st-mcp-revoke-dialog .ui-dialog__foot [data-dialog-cancel]').evaluate('el => el === document.activeElement'))
    page.locator('#st-mcp-revoke-dialog .ui-dialog__foot [data-dialog-cancel]').click()
    page.wait_for_selector('#st-mcp-revoke-dialog', state='detached')
    check("取消吊销没有改变 Key", verify_key(server.vault, secret) is not None)
    page.click(f'[data-action="settings.mcpRevoke"][data-arg="{row["key_id"]}"]')
    page.route('**/api/mcp/keys/revoke', lambda route: route.fulfill(status=500,
        content_type='application/json', body=json.dumps({'msg': '模拟吊销失败'})))
    page.locator('#st-mcp-revoke-dialog [data-dialog-ok]').click()
    page.wait_for_function("() => document.querySelector('#st-mcp-revoke-status')?.textContent.includes('吊销失败')")
    check("吊销失败保留确认窗口且原 Key 可用", page.locator('#st-mcp-revoke-dialog').is_visible()
          and verify_key(server.vault, secret) is not None)
    page.unroute('**/api/mcp/keys/revoke')
    page.locator('#st-mcp-revoke-dialog [data-dialog-ok]').click()
    page.wait_for_selector('#st-mcp-revoke-dialog', state='detached')
    check("设置 UI 吊销立即使 Key 无效", verify_key(server.vault, secret) is None)
    check("失效记录默认折叠且可用列表无已吊销项", not page.locator('#st-mcp-history').evaluate('el => el.open')
          and page.locator(f'.st-mcp-active [data-key="{row["key_id"]}"]').count() == 0)
    page.locator('#st-mcp-history > summary').click()
    details = page.locator(f'[data-key-details="{row["key_id"]}"]')
    details.locator('summary').click()
    page.click('[data-action="settings.mcpRefresh"]')
    page.wait_for_load_state('networkidle')
    check("刷新保留失效记录和详情展开状态", page.locator('#st-mcp-history').evaluate('el => el.open') and details.evaluate('el => el.open'))
    count = page.locator('.st-mcp-key').count()
    page.route('**/api/mcp/keys', lambda route: route.fulfill(status=500,
        content_type='application/json', body=json.dumps({'msg': '模拟列表失败'})))
    page.click('[data-action="settings.mcpRefresh"]')
    page.wait_for_function("() => document.querySelector('#st-mcp-status')?.textContent.includes('无法读取')")
    check("列表读取失败保留上次成功数据", page.locator('.st-mcp-key').count() == count)
    page.unroute('**/api/mcp/keys')

    expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=3)
    expiring = create_key(server.vault, '即将到期验收', ['omrs:read'], expiry.isoformat())
    page.click('[data-action="settings.mcpRefresh"]')
    page.wait_for_function("id => !!document.querySelector(`.st-mcp-key[data-key='${id}'] [data-state='expired']`)",
        arg=expiring['key_id'], timeout=8000)
    check("到期时自动移入失效记录并移除吊销按钮", page.locator(f'.st-mcp-active [data-key="{expiring["key_id"]}"]').count() == 0
          and verify_key(server.vault, expiring['secret']) is None)
    page.locator('#st-mcp-history > summary').click()
    page.locator('.st-mcp-card').screenshot(path=os.path.join(_SCREENSHOT_DIR, 'ui-desktop.png'))

    page.click('.st-mcp-intro [data-action="settings.mcpCreate"]')
    page.fill('#st-mcp-name', '离开页面验收')
    page.select_option('#st-mcp-expiry-kind', 'custom')
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
    local_future = page.evaluate("iso => {const d=new Date(iso), p=v=>String(v).padStart(2,'0'); return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;}", future.isoformat())
    page.fill('#st-mcp-expires', local_future)
    page.locator('#st-mcp-dialog [data-dialog-ok]').click()
    page.wait_for_function("() => document.querySelector('#st-mcp-secret-value')?.value.startsWith('omrs_mcp_')")
    next_key = verify_key(server.vault, page.locator('#st-mcp-secret-value').input_value())
    check("指定到期时间创建为真实有期限的 Key", bool(next_key and next_key['expires_at']))
    page.evaluate("window.__omrs.router.go('questions')")
    page.wait_for_selector('#st-mcp-dialog', state='detached')
    page.evaluate("window.__omrs.router.go('settings')")
    page.wait_for_selector('.st-mcp-card')
    page.click('[data-action="settings.section"][data-arg="access"]')
    check("离开设置页卸载弹窗并清空完整 Key", page.locator('#st-mcp-secret-value').count() == 0 and page.locator('#st-mcp-secret').count() == 0)
    for theme in ('light', 'dark'):
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            page.click('.st-mcp-intro [data-action="settings.mcpCreate"]')
            page.fill('#st-mcp-name', '长名称布局验收' * 9)
            ok = page.locator('#st-mcp-dialog .ui-dialog__panel').evaluate("el => {const r=el.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight;}")
            ok = ok and page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            check(f"MCP 创建窗口 {theme} {width}px 布局与长名称正常", ok)
            page.keyboard.press('Escape')
            page.wait_for_selector('#st-mcp-dialog', state='detached')
            if width == 390 and theme == 'light':
                page.locator('.st-mcp-card').screenshot(path=os.path.join(_SCREENSHOT_DIR, 'ui-mobile.png'))


def main():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        print("SKIP MCP 浏览器验收：可选依赖 playwright 未安装")
        return 0
    if not MCP_AVAILABLE:
        print("SKIP MCP 浏览器验收：可选依赖 mcp 未安装")
        return 0

    server = MCPServerProcess()
    question_images = [_png(80, 40) + b"QUESTION-PNG-ORIGINAL-TAIL",
                       _jpeg() + b"QUESTION-JPEG-ORIGINAL-TAIL", _gif()]
    question_mimes = ["image/png", "image/jpeg", "image/gif"]
    question = create_question(server.vault, "物理", "题图闭环", 5,
        question_text="题目与答案的图片分别按列表下标读取。",
        question_images=["data:" + mime + ";base64," + base64.b64encode(raw).decode()
                         for raw, mime in zip(question_images[:2], question_mimes[:2])],
        answer_images=["data:image/gif;base64," + base64.b64encode(question_images[2]).decode()])
    try:
        server.start()
    except BaseException:
        server.stop()
        raise
    raw_images = [_png(480, 240), _png(360, 240) + b"MCP-ORIGINAL-TAIL",
                  _jpeg() + b"MCP-JPEG-TAIL", _gif()]

    async def create():
        async with _session(server.mcp_port, server.keys["all"]["secret"]) as session:
            result = await session.call_tool("create_draft", {
                "subject": "数学", "category": "浏览器验收", "request_id": "browser-e2e-1",
                "blocks": [{"section": "题目", "kind": "text", "text": "浏览器审核题干"},
                           {"section": "题目", "kind": "image", "image": 0}],
                "images": [{"data_base64": base64.b64encode(item).decode(), "file_name": f"mcp-{i}.png",
                            "file_id": f"browser-file-{i}", "download_url": "https://example.com/image"}
                           for i, item in enumerate(raw_images)],
            })
            return _json_result(result)

    result = None
    browser = None
    checks = []
    try:
        async def read_images():
            before = read_commits(server.vault)
            async with _session(server.mcp_port, server.keys["read"]["secret"]) as session:
                tools = (await session.list_tools()).tools
                checks.append(("SDK 读取权限发现查询工具且包含题图工具", len(tools) == sum(s == "omrs:read" for s in __import__("omrs.mcp.server", fromlist=["TOOL_SCOPES"]).TOOL_SCOPES.values())
                               and "get_question_image" in {tool.name for tool in tools}))
                remote = _json_result(await session.call_tool("get_question", {"uid": question["uid"]}))
                expected = read_tools.get_question({"vault": server.vault}, {"uid": question["uid"]})["result"]
                checks.append(("SDK 题目结果与共享读取一致并保留题目/答案图片顺序",
                               remote == expected and remote.get("images") == question["images"]))
                for index, (raw, mime) in enumerate(zip(question_images, question_mimes)):
                    image = await session.call_tool("get_question_image",
                                                    {"uid": remote["uid"], "image_index": index})
                    ok = (not image.isError and image.structuredContent is None
                          and len(image.content) == 1 and image.content[0].type == "image"
                          and image.content[0].mimeType == mime
                          and base64.b64decode(image.content[0].data) == raw)
                    checks.append(("SDK 原生题图 MIME 与原字节一致：" + mime, ok))
            checks.append(("SDK 读取题图不新增学习 Ledger 提交", read_commits(server.vault) == before))
        asyncio.run(read_images())
        result = asyncio.run(create())
        draft_id = result["draft_id"]
        base = f"http://127.0.0.1:{server.web_port}"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(10000)
            page.goto(base + "/#/ai-review", wait_until="networkidle")
            page.wait_for_selector(".arv-row")
            row = page.locator(f'.arv-row[data-arg="{draft_id}"]')
            checks.append(("审核队列展示 MCP 来源草稿", row.count() == 1 and "MCP" in row.inner_text()))
            row.click()
            # .drf-detail 也用于加载占位；业务控件出现后才检查来源与正文。
            page.wait_for_selector('.drf-detail [data-action="ai-review.draftCommit"]')
            checks.append(("详情保持 review/来源 MCP", "来源：MCP" in page.locator(".drf-detail").inner_text()
                           and "浏览器验收" in page.locator(".drf-detail").inner_text()))
            page.locator(".drf-source-trigger").click()
            page.wait_for_selector(".drf-source-workspace")
            checks.append(("来源工作区显示完整原图列表", page.locator(".drf-source img").count() == len(raw_images)))
            checks.append(("MCP 原始来源禁止取消关联", page.locator('[data-action="ai-review.draftSourceRemove"]').count() == 0))
            # 草稿区通过普通 Web 图片端点取原件；MCP Key 没有带到浏览器请求。
            for image in page.locator(".drf-source img").all():
                src = image.get_attribute("src") or ""
                response = page.request.get(base + src) if src.startswith("/") else None
                if response is not None:
                    body = response.body()
                    checks.append(("原图下载字节完全相等", body in raw_images
                                   and response.status == 200))
            screenshot = os.path.join(_SCREENSHOT_DIR, "draft-desktop.png")
            page.screenshot(path=screenshot, full_page=True)
            print(f"截图：{screenshot}")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(250)
            checks.append(("手机草稿区来源可见且无横向溢出", page.locator(".drf-source img").count() == len(raw_images)
                           and page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")))
            page.screenshot(path=os.path.join(_SCREENSHOT_DIR, "draft-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 900})

            run_key_ui(page, base, server, checks)
            context.close()
    except (PlaywrightTimeoutError, KeyError, AssertionError) as exc:
        checks.append(("浏览器路径无异常", False, repr(exc)))
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        server.stop()
    for check in checks:
        print(("PASS " if check[1] else "FAIL ") + check[0] + (f": {check[2]}" if len(check) > 2 else ""))
    print(f"MCP SDK / 浏览器验收：{sum(item[1] for item in checks)}/{len(checks)}")
    return 0 if checks and all(item[1] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
