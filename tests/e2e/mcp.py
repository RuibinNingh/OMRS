"""MCP → OMRS 草稿区真实浏览器验收。

脚本在临时 Vault 内启动同进程 Web + MCP，先由官方 MCP SDK 创建草稿，
再打开 OMRS 草稿区确认人工审核入口、MCP 来源和完整原图。生产服务和真实
``错题/`` 永远不会被访问；缺少可选 SDK 或浏览器时会清楚地打印 SKIP。
"""

import asyncio
import base64
import os
import sys

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
from omrs.mcp.keys import verify_key
try:
    from test_mcp_protocol import MCP_AVAILABLE, MCPServerProcess, _gif, _jpeg, _json_result, _png, _session
except ImportError:
    from tests.test_mcp_protocol import MCP_AVAILABLE, MCPServerProcess, _gif, _jpeg, _json_result, _png, _session


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
        result = asyncio.run(create())
        draft_id = result["draft_id"]
        base = f"http://127.0.0.1:{server.web_port}"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(10000)
            page.goto(base + "/#/create", wait_until="networkidle")
            page.locator('#create-flow [data-ib-stage="drafts"]').click()
            page.wait_for_selector(".drf-item")
            checks.append(("pending 列表只读展示 MCP 来源", page.locator(".drf-item").count() == 1
                           and "来源：MCP" in page.locator(".drf-item").inner_text()))
            page.locator(f'.drf-item[data-arg="{draft_id}"]').click()
            page.wait_for_selector(".drf-detail")
            checks.append(("详情保持 review/来源 MCP", "来源：MCP" in page.locator(".drf-detail").inner_text()
                           and "浏览器验收" in page.locator(".drf-detail").inner_text()))
            page.locator(".drf-source-trigger").click()
            page.wait_for_selector(".drf-source-workspace")
            checks.append(("来源工作区显示完整原图列表", page.locator(".drf-source img").count() == len(raw_images)))
            checks.append(("MCP 原始来源禁止取消关联", page.locator('[data-action="create.draftSourceRemove"]').count() == 0))
            # 草稿区通过普通 Web 图片端点取原件；MCP Key 没有带到浏览器请求。
            for image in page.locator(".drf-source img").all():
                src = image.get_attribute("src") or ""
                response = page.request.get(base + src) if src.startswith("/") else None
                if response is not None:
                    body = response.body()
                    checks.append(("原图下载字节完全相等", body in raw_images
                                   and response.status == 200))
            screenshot = "/tmp/omrs-mcp-e2e.png"
            page.screenshot(path=screenshot, full_page=True)
            print(f"截图：{screenshot}")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(250)
            checks.append(("手机草稿区来源可见且无横向溢出", page.locator(".drf-source img").count() == len(raw_images)
                           and page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")))
            page.screenshot(path="/tmp/omrs-mcp-e2e-mobile.png", full_page=True)
            page.set_viewport_size({"width": 1440, "height": 900})

            page.goto(base + "/#/settings", wait_until="networkidle")
            page.click('[data-action="settings.section"][data-arg="access"]')
            page.fill("#st-mcp-name", "浏览器创建 Key")
            page.click('[data-action="settings.mcpCreate"]')
            page.wait_for_function("() => document.querySelector('#st-mcp-secret-value')?.value.startsWith('omrs_mcp_')")
            secret = page.locator("#st-mcp-secret-value").input_value()
            row = verify_key(server.vault, secret)
            checks.append(("设置 UI 创建真实 Key 且仅创建时显示明文", bool(row)
                           and page.locator("#st-mcp-secret").is_visible()))
            checks.append(("浏览器未持久化明文 Key", page.evaluate(
                "secret => !JSON.stringify([localStorage,sessionStorage]).includes(secret)", secret)))
            page.click('[data-action="settings.mcpHide"]')
            checks.append(("隐藏明文清空输入", page.locator("#st-mcp-secret-value").input_value() == ""))
            page.reload(wait_until="networkidle")
            page.wait_for_selector(f'.st-mcp-key[data-key="{row["key_id"]}"]')
            checks.append(("刷新只能看到 Key 元数据", page.locator("#st-mcp-secret-value").input_value() == ""))
            page.click(f'[data-action="settings.mcpRevoke"][data-arg="{row["key_id"]}"]')
            page.wait_for_selector("dialog[open]")
            page.locator("dialog[open] [data-dialog-ok]").click()
            page.wait_for_function("() => document.querySelector('#st-mcp-status')?.textContent.includes('已吊销')")
            checks.append(("设置 UI 吊销立即使 Key 无效", verify_key(server.vault, secret) is None))
            page.fill("#st-mcp-name", "离开页面验收")
            page.click('[data-action="settings.mcpCreate"]')
            page.wait_for_function("() => document.querySelector('#st-mcp-secret-value')?.value.startsWith('omrs_mcp_')")
            page.goto(base + "/#/questions", wait_until="networkidle")
            page.goto(base + "/#/settings", wait_until="networkidle")
            page.click('[data-action="settings.section"][data-arg="access"]')
            checks.append(("离开设置页后完整 Key 清空", page.locator("#st-mcp-secret-value").input_value() == ""
                           and not page.locator("#st-mcp-secret").is_visible()))
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
    print(f"MCP 浏览器验收：{sum(item[1] for item in checks)}/{len(checks)}")
    return 0 if checks and all(item[1] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
