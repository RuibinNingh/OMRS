"""入口锁屏页桌面 / 手机背景回归：黑洞默认、自定义图片、模糊和窄屏溢出。"""
import base64
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium
from omrs.common import save_config
from tests.visual import run as visual


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwnwEIAgIBV7n3WQAAAABJRU5ErkJggg==")


def main():
    os.environ.pop("OMRS_SYSTEMD_SERVICE", None)
    with tempfile.TemporaryDirectory(prefix="omrs-e2e-entry-") as work:
        vault = os.path.join(work, "vault")
        subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault], check=True, capture_output=True)
        proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
        base = f"http://127.0.0.1:{port}"
        results = []
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                for mobile, viewport in ((False, {"width": 1440, "height": 900}), (True, {"width": 390, "height": 844})):
                    context = browser.new_context(viewport=viewport)
                    page = context.new_page()
                    page.goto(base + "/", wait_until="networkidle")
                    page.wait_for_function("() => ['ready','fallback'].includes(document.querySelector('#gravity')?.dataset.status)")
                    results.append((f"{'手机' if mobile else '桌面'}默认黑洞入口", page.locator('#gravity').get_attribute('data-status') in ('ready', 'fallback')))
                    context.close()
                media_id = "0123456789abcdef0123456789abcdef"
                media = os.path.join(vault, "错题", ".omrs", "entry-background", media_id + ".png")
                os.makedirs(os.path.dirname(media), exist_ok=True)
                open(media, "wb").write(PNG)
                save_config(vault, {"entry_background": {"mode": "custom", "style": "gaussian-blur", "blur_px": 7,
                    "asset": {"id": media_id, "kind": "image", "mime": "image/png", "bytes": len(PNG)}}})
                for mobile, viewport in ((False, {"width": 1440, "height": 900}), (True, {"width": 390, "height": 844})):
                    context = browser.new_context(viewport=viewport)
                    page = context.new_page()
                    page.goto(base + "/", wait_until="networkidle")
                    page.wait_for_function("() => document.querySelector('#gravity')?.dataset.status === 'custom-ready'")
                    results.append((f"{'手机' if mobile else '桌面'}自定义图片入口", page.locator('.entry-custom-media').count() == 1 and page.evaluate("() => getComputedStyle(document.querySelector('.entry-custom-media')).filter.includes('blur(7px)')")))
                    if mobile:
                        results.append(("手机自定义背景无横向溢出", page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")))
                    context.close()
                browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
        for label, ok in results:
            print(('PASS' if ok else 'FAIL') + ' ' + label)
        print(f"入口背景 E2E：{sum(ok for _, ok in results)}/{len(results)}")
        return 0 if results and all(ok for _, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
