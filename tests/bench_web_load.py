"""用隔离 Vault、真实 Chromium 和限速网络测量首屏 / 刷新，不设易波动的耗时门禁。

python3 tests/bench_web_load.py --out /tmp/omrs-web-load.json
python3 tests/bench_web_load.py --tree /tmp/omrs-baseline --out /tmp/omrs-web-before.json
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.browser_runtime import launch_chromium
from tests.visual.run import start_server


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description="公网首屏与缓存刷新实测")
    parser.add_argument("--tree", default=str(ROOT), help="被测源码目录")
    parser.add_argument("--out", required=True, help="结果 JSON 路径")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--latency", type=int, default=100, help="网络延迟，毫秒")
    parser.add_argument("--mbps", type=float, default=5, help="下载带宽，Mbps")
    args = parser.parse_args()
    if args.runs < 1 or args.latency < 0 or args.mbps <= 0:
        parser.error("次数、延迟及带宽超出范围")
    tree = pathlib.Path(args.tree).resolve()
    results = []
    with tempfile.TemporaryDirectory(prefix="omrs-web-load-") as work:
        vault = os.path.join(work, "vault")
        env = dict(os.environ)
        env.pop("OMRS_SYSTEMD_SERVICE", None)
        subprocess.run([sys.executable, str(tree / "tests/fixtures/make_vault.py"), "--out", vault],
                       cwd=tree, env=env, check=True, capture_output=True)
        proc, port = start_server(str(tree), vault, os.path.join(work, "server.log"))
        try:
            with sync_playwright() as p:
                browser = launch_chromium(p)
                try:
                    for iteration in range(args.runs):
                        context = browser.new_context(viewport={"width": 1440, "height": 900})
                        try:
                            context.add_init_script("performance.setResourceTimingBufferSize(3000)")
                            page = context.new_page()
                            errors = []
                            page.on("pageerror", lambda e: errors.append(str(e)))
                            page.on("response", lambda r: errors.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None)
                            session = context.new_cdp_session(page)
                            session.send("Network.enable")
                            session.send("Network.emulateNetworkConditions", {
                                "offline": False, "latency": args.latency,
                                "downloadThroughput": args.mbps * 1_000_000 / 8,
                                "uploadThroughput": 125000, "connectionType": "cellular4g"})
                            for warm in (False, True):
                                errors.clear()
                                if warm:
                                    page.reload(wait_until="domcontentloaded", timeout=120000)
                                else:
                                    page.goto(f"http://127.0.0.1:{port}/?unlocked=1#/dashboard",
                                              wait_until="domcontentloaded", timeout=120000)
                                page.wait_for_function("!!window.__omrs && !!document.querySelector('#panel-dashboard [data-dash-ready]')",
                                                       timeout=120000)
                                ready_ms = page.evaluate("performance.now()")
                                page.wait_for_load_state("networkidle", timeout=120000)
                                page.evaluate("document.fonts.ready")
                                metrics = page.evaluate("""() => {
                                    const r = performance.getEntriesByType('resource');
                                    const n = performance.getEntriesByType('navigation');
                                    return { requests:r.length,
                                      transfer_bytes:[...r,...n].reduce((a,x)=>a+x.transferSize,0),
                                      network_requests:r.filter(x=>x.transferSize>0).length,
                                      js:r.filter(x=>new URL(x.name).pathname.endsWith('.js')).length,
                                      css:r.filter(x=>new URL(x.name).pathname.endsWith('.css')).length,
                                      fonts:r.filter(x=>new URL(x.name).pathname.endsWith('.woff2')).length,
                                      cached_resources:r.filter(x=>x.transferSize===0).length };
                                }""")
                                metrics.update(iteration=iteration, warm=warm, dashboard_ms=round(ready_ms), errors=errors[:])
                                results.append(metrics)
                                print(json.dumps(metrics, ensure_ascii=False), flush=True)
                                if errors:
                                    raise RuntimeError("加载出现错误，见结果中的 errors")
                        finally:
                            context.close()
                finally:
                    if not os.environ.get("OMRS_TEST_CDP_URL"):
                        browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    output = {"latency_ms": args.latency, "download_mbps": args.mbps, "results": results}
    pathlib.Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
