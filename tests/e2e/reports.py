"""报告页：隔离 Vault 的上传、下载、删除、沙箱预览与视觉审计。"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium

_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)

AUDIT = """target => {
  const root = document.getElementById('rp-app');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('.katex'));
  const text = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(text).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a,b) => a-b);
  const hit = e => (e.tagName === 'LABEL' && !!e.querySelector('input'))
    || (['BUTTON','INPUT','SELECT','SUMMARY'].includes(e.tagName) && !e.closest('label')) || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r=e.getBoundingClientRect(); return r.width && r.height < target; })
    .map(e => `${e.tagName}.${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const inline = shown.filter(e => (e.getAttribute('style') || '').trim()).length;
  const handlers = shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length;
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible')
    .map(e => `${e.tagName}.${e.className}: ${e.scrollWidth}/${e.clientWidth}`);
  return { sizes, small, inline, handlers, over, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""


def wait(page, expression, timeout=8000):
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:
        return False


def guarded(results, name, action):
    try:
        action()
    except Exception as error:
        results.append((f"{name}：段落执行出错", False, repr(error)[:350]))


def open_reports(page, base):
    page.goto(f"{base}/?t={os.urandom(3).hex()}#/reports", wait_until="networkidle")
    return wait(page, "() => document.querySelector('#rp-app .rpw') && document.querySelector('#rp-list .ui-empty')")


def run_main(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))

    check("首屏载入且旧全局删除", open_reports(page, base)
          and page.evaluate("typeof loadReports === 'undefined' && typeof createReport === 'undefined'"))
    page.click('[data-action="reports.create"]')
    check("缺少名称提示", wait(page, "() => document.querySelector('#rp-status')?.textContent.includes('请填写')"))
    page.fill('#rp-name', '测试报告')
    page.click('[data-action="reports.create"]')
    check("缺少文件提示", wait(page, "() => document.querySelector('#rp-status')?.textContent.includes('请选择')"))

    page.evaluate("""() => { const dt = new DataTransfer(); dt.items.add(new File(['abc'], 'wrong.txt', {type:'text/plain'}));
      document.querySelector('.rpw-upload [data-filedrop]').dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:dt})); }""")
    check("拖入非 HTML 文件就地报错", wait(page, "() => document.querySelector('.rpw-upload [role=alert]')?.textContent.includes('只支持')"))
    page.locator('#rp-file').set_input_files({"name": "empty.html", "mimeType": "text/html", "buffer": b""})
    check("空 HTML 文件就地报错", wait(page, "() => document.querySelector('.rpw-upload [role=alert]')?.textContent.includes('为空')"))

    page.locator('#rp-file').set_input_files({"name": "sample.html", "mimeType": "text/html",
                                              "buffer": b"<!doctype html><meta charset=utf-8><h1>sample report</h1>"})
    check("点击文件选择后显示名称", wait(page, "() => document.querySelector('.rpw-upload')?.textContent.includes('sample.html')"))
    page.evaluate("""() => { window.__realReader = window.FileReader; window.FileReader = class extends window.__realReader {
      readAsText() { this.onerror?.(new Event('error')); }
    }; }""")
    page.click('[data-action="reports.create"]')
    check("文件读取失败在上传区旁显示原因", wait(page, "() => document.querySelector('.rpw-upload [role=alert]')?.textContent.includes('文件读取失败')"))
    page.evaluate("() => { window.FileReader = window.__realReader; }")
    page.click('[data-action="reports.create"]')
    check("上传后列表出现报告且名称清空", wait(page, "() => document.querySelector('.rpw-row')?.textContent.includes('测试报告')")
          and not page.locator('#rp-name').input_value())
    page.click('[data-action="reports.open"]')
    frame = page.locator('.rpw-frame')
    check("报告在无同源权限的 iframe 中浏览", frame.count() == 1
          and 'allow-same-origin' not in (frame.get_attribute('sandbox') or '')
          and wait(page, "() => document.querySelector('.rpw-frame')?.contentWindow"))
    check("预览报告内容可读", wait(page, "() => document.querySelector('.rpw-frame')?.contentDocument === null")
          and frame.content_frame.locator('h1').inner_text() == 'sample report')

    page.locator('#rp-include-images').check()
    check("带图材料提示切换", 'ZIP' in page.locator('#rp-material-hint').inner_text())
    page.evaluate("Object.defineProperty(navigator, 'clipboard', { configurable:true, value:{writeText: async text => { window.__copiedPrompt=text; }} })")
    page.click('[data-action="reports.prompt"]')
    check("复制提示词包含题图规则", wait(page, "() => !!window.__copiedPrompt")
          and '/api/image' in page.evaluate('window.__copiedPrompt'))
    with page.expect_download() as download:
        page.click('[data-action="reports.download"]')
    check("带图分析材料下载 ZIP", download.value.suggested_filename.endswith('.zip'))

    page.click('[data-action="reports.delete"]')
    check("删除前出现确认对话框", wait(page, "() => !!document.querySelector('dialog[open]')"))
    page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
    check("取消删除保留报告", page.locator('.rpw-row').count() == 1)
    page.evaluate("""() => { const original = window.fetch.bind(window); window.__deleteCount = 0;
      window.fetch = (url, options) => {
        if (String(url).includes('/api/report/delete')) {
          window.__deleteCount++;
          return new Promise(resolve => { window.__releaseDelete = () => resolve(original(url, options)); });
        }
        return original(url, options);
      };
    }""")
    page.click('[data-action="reports.delete"]')
    page.locator('dialog[open] [data-dialog-ok]').click()
    check("删除期间禁用按钮并防止重复请求", wait(page, "() => !!document.querySelector('[data-action=\"reports.delete\"][disabled]')")
          and page.evaluate("() => { document.querySelector('[data-action=\"reports.delete\"]').click(); return window.__deleteCount; }") == 1)
    page.evaluate("window.__releaseDelete()")
    check("确认删除后列表恢复空态", wait(page, "() => !!document.querySelector('#rp-list .ui-empty')"))

    page.route("**/api/reports", lambda route: route.fulfill(status=503, content_type="application/json", body='{"msg":"模拟报告失败"}'))
    page.click('[data-action="reports.refresh"]')
    check("列表请求失败显示原因", wait(page, "() => document.querySelector('.rpw-error')?.textContent.includes('模拟报告失败')"))
    page.unroute("**/api/reports")
    page.click('.rpw-error [data-action="reports.refresh"]')
    check("重试清除错误", wait(page, "() => !document.querySelector('.rpw-error')"))


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-reports-")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"),
                    "--out", os.path.join(work, "vault")], check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, os.path.join(work, "vault"), os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            guarded(results, "主路径", lambda: run_main(page, base, results))
            results.append(("桌面主路径无页面脚本错误", not errors, "; ".join(errors[:3])))
            context.close()
            for theme in ("light", "dark"):
                for label, viewport, target in (("桌面", (1440, 900), 28), ("手机", (390, 844), 40)):
                    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
                    ctx.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
                    pg = ctx.new_page()
                    open_reports(pg, base)
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
    print(f"E2E reports：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
