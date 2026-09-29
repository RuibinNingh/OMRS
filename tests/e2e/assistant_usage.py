"""P6 用量入口：隔离 Vault、假模型和真实 Chromium 页面。"""
import shutil
import sys

from assistant import make_vault, start
from browser_runtime import launch_chromium
from fixtures.make_vault import free_port


def main():
    from playwright.sync_api import sync_playwright
    vault, port = make_vault(), free_port()
    process = start(vault, port)
    base = f"http://127.0.0.1:{port}"
    results, errors = [], []

    def check(label, value):
        results.append((label, bool(value)))

    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{base}/#/assistant", wait_until="networkidle")
            page.wait_for_selector("#ast-input")
            page.fill("#ast-input", "找一下和「周期」有关的题")
            page.locator('[data-action="assistant.send"]').click()
            page.wait_for_selector(".ast-turn:not(.is-live)", timeout=30000)
            page.locator('[data-action="assistant.pop"]').click()
            page.wait_for_selector('.ast-pop__modes')
            check("弹层同时提供上下文和缓存指标", page.locator('.ast-pop__modes button').count() == 2)
            page.locator('[data-action="assistant.meterMode"][data-arg="cache"]').click()
            page.wait_for_function("() => document.querySelector('.ast-meter')?.getAttribute('aria-label')?.startsWith('缓存命中率')")
            check("缓存圆环标明指标及比例", "缓存命中率" in page.locator('.ast-meter').get_attribute('aria-label')
                  and "缓存" in page.locator('.ast-pop__h').inner_text())
            page.reload(wait_until="networkidle")
            page.wait_for_selector(".ast-turn:not(.is-live)")
            check("缓存模式刷新后保留", "缓存命中率" in page.locator('.ast-meter').get_attribute('aria-label'))
            page.locator('[data-action="assistant.selectRun"]').last.click()
            page.wait_for_selector('.ast-insp .ast-usage')
            detail = page.locator('.ast-insp .ast-usage').inner_text()
            check("运行详情区分主对话、图片辅助和总量", all(word in detail for word in ('主对话输入', '主对话输出', '图片辅助', '本次总量', '主对话缓存')))
            page.locator('[data-action="assistant.pop"]').click()
            page.wait_for_selector('.ast-pop__modes')
            page.locator('[data-action="assistant.meterMode"][data-arg="context"]').click()
            page.wait_for_function("() => document.querySelector('.ast-meter')?.getAttribute('aria-label')?.startsWith('上下文占用')")
            check("上下文指标使用独立分母", '上下文占用' in page.locator('.ast-meter').get_attribute('aria-label')
                  and '最近请求' in page.locator('.ast-pop__h').inner_text())
            page.set_viewport_size({"width": 360, "height": 780})
            check("360px 无页面横向溢出", page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
            browser.close()
    except Exception as error:  # noqa: BLE001
        results.append((f"执行出错：{error!r}", False))
    finally:
        process.terminate()
        process.wait(timeout=10)
        shutil.rmtree(vault, ignore_errors=True)
    check("无页面脚本错误", not errors)
    for label, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(f"{sum(ok for _, ok in results)}/{len(results)} 通过")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
