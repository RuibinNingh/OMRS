"""P8 browser integration: CSS layers, native UI, label manager, and 12 page mounts."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)


def main():
    from playwright.sync_api import sync_playwright
    work = tempfile.mkdtemp(prefix="omrs-e2e-ui-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault], check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    results = []
    try:
        with sync_playwright() as p:
            browser = visual.launch_chromium(p)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            layers = page.evaluate("""() => [...document.styleSheets].filter(s => (s.href || '').includes('/app/styles/index.css')).flatMap(s => [...s.cssRules].filter(r => r.layerName).map(r => r.layerName)).filter((v,i,a) => a.indexOf(v) === i)""")
            results.append(("样式层", layers == ['vendor', 'base', 'ui', 'shell', 'domain', 'features']))
            page.evaluate("""async () => { const { toast } = await import('/assets/app/ui/toast.js'); toast('本机集成提示'); }""")
            results.append(("原生提示", page.locator('.ui-toast').filter(has_text='本机集成提示').count() == 1))
            page.evaluate("""async () => { const { openLabelManager } = await import('/assets/app/domain/labels/index.js'); openLabelManager(); }""")
            page.wait_for_selector('dialog.ui-dialog[open] .label-manager-modal')
            results.append(("标记管理原生对话框", page.locator('dialog.ui-dialog[open] .label-manager-modal').count() == 1))
            page.keyboard.press('Escape')
            page.wait_for_selector('dialog.ui-dialog[open] .label-manager-modal', state='detached')
            page.evaluate("window.__omrs.router.go('questions')")
            heights = page.locator('#panel-questions .qlb-bar :is(.qlb-search, button, select)').evaluate_all("els => [...new Set(els.filter(e => e.offsetParent).map(e => Math.round(e.getBoundingClientRect().height)))]")
            results.append(("题库工具栏控件等高", len(heights) == 1))
            page.evaluate("window.__omrs.router.go('instant')")
            pads = page.locator('#panel-instant .inst-bar select').evaluate_all("els => [...new Set(els.map(e => getComputedStyle(e).paddingTop))]")
            results.append(("即时练习选择框不裁字", pads == ['0px']))
            tabs = page.locator('.sidebar-nav a.tab[data-tab]').evaluate_all("els => [...new Set(els.map(e => e.dataset.tab))]")
            for name in tabs:
                page.evaluate("name => window.__omrs.router.go(name)", name)
                page.wait_for_function("name => document.querySelector('.content > .panel.active')?.id === 'panel-' + name", arg=name)
            results.append(("12 页切换无脚本错误", len(tabs) == 12 and not errors))
            if not os.environ.get('OMRS_TEST_CDP_URL'):
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    for name, ok in results:
        print(('  ok    ' if ok else '  FAIL  ') + name)
    print(f"E2E ui_bridge：{sum(ok for _, ok in results)} 通过 / {sum(not ok for _, ok in results)} 失败")
    return int(any(not ok for _, ok in results))


if __name__ == '__main__':
    sys.exit(main())
