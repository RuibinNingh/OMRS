"""目录页：隔离 Vault 的树、降级、题目弹窗与四种视觉审计。"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium

_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)

AUDIT = """target => {
  const root = document.getElementById('cat-app');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('.katex'));
  const text = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(text).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a,b) => a-b);
  const hit = e => ['BUTTON','INPUT','SELECT','SUMMARY'].includes(e.tagName) || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r=e.getBoundingClientRect(); return r.width && r.height < target; })
    .map(e => `${e.tagName}.${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const inline = shown.filter(e => (e.getAttribute('style') || '').trim()).length;
  const handlers = shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length;
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible')
    .map(e => `${e.tagName}.${e.className}: ${e.scrollWidth}/${e.clientWidth}`);
  return { sizes, small, inline, handlers, over, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""


def http(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
        return json.load(response)


def wait(page, expression, arg=None, timeout=8000):
    try:
        page.wait_for_function(expression, arg=arg, timeout=timeout)
        return True
    except Exception:
        return False


def guarded(results, name, action):
    try:
        action()
    except Exception as error:
        results.append((f"{name}：段落执行出错", False, repr(error)[:350]))


def open_catalog(page, base):
    page.goto(f"{base}/?t={os.urandom(3).hex()}#/catalog", wait_until="networkidle")
    return wait(page, "() => document.querySelector('#cat-app .catw-folder')")


def run_main(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))

    actual = http(port, "/api/tree")
    check("首屏读取真实目录且旧全局已删除", open_catalog(page, base)
          and page.evaluate("typeof loadCatalog === 'undefined' && typeof renderCatalog === 'undefined'")
          and page.locator('#catalog-stat .ui-stat').count() == 4)
    check("文件夹与题目计数采用服务端 summary", page.locator('#catalog-stat').inner_text().find(str(actual['summary']['questions'])) >= 0)
    root = page.locator('.catw-folder[data-key="dir:错题"]')
    check("大树默认只展开根节点", root.count() == 1 and root.locator('.catw-folder__line').count() > 1
          and page.locator('.catw-file').count() == 0)
    first = page.locator('.catw-folder__line [data-action="catalog.toggle"]').nth(1)
    first.click()
    check("点目录行展开一级", page.locator('.catw-folder__line').count() > 2)

    page.fill('#catalog-search', '向量')
    check("搜索展开命中分支并过滤无关文件", wait(page, "() => document.querySelector('#catalog-tree')?.textContent.includes('向量')")
          and '光学' not in page.locator('#catalog-tree').inner_text())
    page.fill('#catalog-search', '')
    check("清空搜索恢复原展开状态", not page.locator('.catw-file').count())

    start = time.monotonic()
    page.click('[data-action="catalog.expand"]')
    elapsed = time.monotonic() - start
    check("展开全部在最大 fixture 树上 1 秒内响应", elapsed < 1 and page.locator('.catw-file').count() > 0, elapsed)
    question_files = page.locator('.catw-file').count()
    page.locator('#catalog-all-files').check()
    all_files = page.locator('.catw-file').count()
    check("显示全部文件会补出图片等非题目文件", all_files > question_files, [question_files, all_files])
    page.locator('#catalog-all-files').uncheck()
    check("关掉全部文件后恢复题目文件列表", page.locator('.catw-file').count() == question_files)
    page.click('[data-action="catalog.collapse"]')
    check("全部折叠只留根层", page.locator('.catw-file').count() == 0)

    page.click('[data-action="catalog.expand"]')
    question = page.locator('[data-action="catalog.open"]').first
    check("题目文件可通过 domain/question 弹窗打开", question.count() > 0 and question.click() is None
          and wait(page, "() => !!document.querySelector('dialog#modal[open]')"))
    page.locator('dialog#modal [data-dialog-cancel]').click()

    page.evaluate("Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => { window.__copiedPath = text; } } })")
    page.locator('[data-action="catalog.copy"]').first.click()
    check("复制相对路径显示成功提示", wait(page, "() => document.querySelector('#catalog-status')?.textContent.includes('已复制路径')")
          and page.evaluate("window.__copiedPath") == '错题')
    page.evaluate("Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async () => { throw Error('拒绝'); } } })")
    page.locator('[data-action="catalog.copy"]').first.click()
    check("剪贴板被拒绝时提示手动复制", wait(page, "() => document.querySelector('#catalog-status')?.textContent.includes('复制失败')"))

    page.route("**/api/tree", lambda route: route.fulfill(status=503, content_type="application/json", body='{"msg":"树暂不可用"}'))
    count = page.locator('.catw-folder').count()
    page.click('[data-action="catalog.refresh"]')
    check("刷新失败保留旧树并显示原因", wait(page, "() => document.querySelector('#cat-app [role=alert]')?.textContent.includes('树暂不可用')")
          and page.locator('.catw-folder').count() == count)
    page.unroute("**/api/tree")
    page.click('[data-action="catalog.refresh"]')
    check("重试成功清除错误", wait(page, "() => !document.querySelector('#cat-app [role=alert]')"))
    reads = []
    page.on("request", lambda request: reads.append(request.url) if request.url.endswith('/api/tree') else None)
    page.route("**/api/scan", lambda route: route.fulfill(status=200, content_type="application/json",
                                                     body='{"status":"error","msg":"模拟失败"}'))
    page.click('[data-action="app.scan"]')
    check("扫描失败不会重读目录树", wait(page, "() => document.body.textContent.includes('模拟失败') && !document.querySelector('[data-action=\"app.scan\"][aria-busy]')")
          and not reads, reads)
    page.unroute("**/api/scan")
    page.route("**/api/scan", lambda route: route.fulfill(status=200, content_type="application/json",
                                                     body='{"status":"ok","count":8}'))
    with page.expect_request("**/api/tree"):
        page.click('[data-action="app.scan"]')
    check("本页重新扫描成功后重读磁盘树", len(reads) == 1, reads)
    page.unroute("**/api/scan")


def run_fallback(browser, base, results):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/tree", lambda route: route.fulfill(status=503, content_type="application/json", body='{"msg":"模拟树接口失败"}'))
    page.goto(f"{base}/#/catalog", wait_until="networkidle")
    shown = wait(page, "() => document.querySelector('#catalog-status')?.textContent.includes('题库路径推算')")
    results.append(("首次加载失败退回题目路径后备树", shown and page.locator('.catw-folder').count() > 0, ""))
    results.append(("降级态无页面脚本错误", not errors, "; ".join(errors[:3])))
    ctx.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-catalog-")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"),
                    "--out", os.path.join(work, "vault")], check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, os.path.join(work, "vault"), os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            guarded(results, "主路径", lambda: run_main(page, base, port, results))
            results.append(("桌面主路径无页面脚本错误", not errors, "; ".join(errors[:3])))
            context.close()
            guarded(results, "后备树", lambda: run_fallback(browser, base, results))
            for theme in ("light", "dark"):
                for label, viewport, target in (("桌面", (1440, 900), 28), ("手机", (390, 844), 40)):
                    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
                    ctx.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
                    pg = ctx.new_page()
                    open_catalog(pg, base)
                    pg.click('[data-action="catalog.expand"]')
                    audit = pg.evaluate(AUDIT, target)
                    ok = len(audit["sizes"]) <= 6 and min(audit["sizes"]) >= 12 and not any(
                        audit[key] for key in ("small", "inline", "handlers", "over", "overflow"))
                    results.append((f"审计 {label} · {'浅色' if theme == 'light' else '深色'}：字号、目标、行内样式、事件与溢出", ok, str(audit)))
                    ctx.close()
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [row for row in results if not row[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E catalog：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
