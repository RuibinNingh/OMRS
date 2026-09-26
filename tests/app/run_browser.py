"""浏览器层单测与 gallery 截图（P2 起的门禁之一）。

    python3 tests/app/run_browser.py               # 跑 tests/app/browser_tests.js：全部通过退出码 0，有失败退出码 1
    python3 tests/app/run_browser.py --shots DIR   # 另存 gallery 截图：浅/深 × 舒适/紧凑（1440 宽）+ 浅色手机（390 宽）

自带静态服务器（以仓库根目录为根），不需要启动 OMRS 实例、不读 Vault。
没有 playwright 或 Chromium 时打印原因并以退出码 2 结束（tests/test_app_browser.py 据此跳过）。
"""
import argparse
import functools
import http.server
import os
import sys
import threading

def launch_browser(p):
    """设了 OMRS_TEST_CDP_URL 时连接已开着的 Chromium（本机直接启动会崩溃的环境用），否则自行启动。"""
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHOTS = (("light", "comfortable", 1440), ("dark", "comfortable", 1440),
         ("light", "compact", 1440), ("dark", "compact", 1440), ("light", "comfortable", 390))
FREEZE = "*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important}"


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
        ".html": "text/html; charset=utf-8", ".woff2": "font/woff2", ".svg": "image/svg+xml",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


def _serve():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Handler, directory=ROOT))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _shoot(browser, base, out):
    os.makedirs(out, exist_ok=True)
    problems = []
    for theme, density, width in SHOTS:
        context = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=1)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base}/assets/app/gallery.html?theme={theme}&density={density}", wait_until="networkidle")
        page.wait_for_function("document.documentElement.dataset.ready === '1'", timeout=15000)
        page.add_style_tag(content=FREEZE)
        page.wait_for_timeout(300)
        name = f"gallery-{theme}-{density}-{width}.png"
        page.screenshot(path=os.path.join(out, name), full_page=True)
        print(f"  截图 {name}" + (f"（页面错误 {len(errors)} 条）" if errors else ""))
        problems += errors
        context.close()
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="ui 组件浏览器单测与 gallery 截图")
    parser.add_argument("--shots", metavar="DIR", help="把 gallery 的 5 种组合截图存到 DIR")
    args = parser.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright（pip install playwright，再 python3 -m playwright install chromium）")
        return 2
    httpd = _serve()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with sync_playwright() as p:
            try:
                browser = launch_browser(p)
            except Exception as exc:  # 浏览器未安装或沙箱不允许
                print(f"跳过：Chromium 启动失败（{exc.__class__.__name__}: {str(exc).splitlines()[0]}）")
                return 2
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}/tests/app/browser.html")
            page.wait_for_function("window.__done === true", timeout=60000)
            results = page.evaluate("window.__results")
            failed = [r for r in results if not r["ok"]]
            for r in results:
                print(("  ok    " if r["ok"] else "  FAIL  ") + r["name"])
                if not r["ok"]:
                    print("        " + r["error"])
            for e in errors:
                print("  页面错误：" + e)
            print(f"浏览器单测：{len(results) - len(failed)} 通过 / {len(failed)} 失败"
                  + (f"，页面错误 {len(errors)} 条" if errors else ""))
            if args.shots:
                errors += _shoot(browser, base, args.shots)
            context.close()
    finally:
        httpd.shutdown()
    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(main())
