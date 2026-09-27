"""P2 主路径 E2E：旧页面经过渡桥接入新 ui 组件后，在真实浏览器里仍然正常。

    python3 tests/e2e/ui_bridge.py            # 全部通过退出码 0；没有 playwright 退出码 2

自己生成 fixture Vault（tests/fixtures/make_vault.py），在临时端口起一个隔离实例，不碰真实数据。检查：
过渡桥安装与排队补发、旧 uiToast / uiConfirm / uiPrompt / uiDialog、新对话框叠在旧弹层之上且 Esc 只关上层、
「有弹层时不响应」的守卫能看到新对话框、题库工具栏同一行同一高度（D2）、即时练习筛选 select 不裁字（D3）、12 页无报错。
"""
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


def launch_browser(p):
    """设了 OMRS_TEST_CDP_URL 时连接已开着的 Chromium（本机直接启动会崩溃的环境用），否则自行启动。"""
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()

EARLY = "window.addEventListener('DOMContentLoaded', () => { if (typeof uiToast === 'function') uiToast('早期提示'); });"
HEIGHTS = """sel => [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null)
  .map(e => Math.round(e.getBoundingClientRect().height))"""


def check_all(page):
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    ev = page.evaluate
    check("过渡桥已安装，排队的早期调用已补发", ev("!!window.__omrsUi && window.__omrsUiPending === null")
          and ev("[...document.querySelectorAll('.ui-toast')].some(t => t.dataset.text === '早期提示')"))
    check("样式分层 vendor / legacy / base / ui / shell / domain / features / legacy-bridge", ev("""[...document.styleSheets].filter(s => (s.href || '').includes('/app/styles/index.css'))
        .flatMap(s => [...s.cssRules].filter(r => r.layerName).map(r => r.layerName))
        .filter((name, i, all) => all.indexOf(name) === i).join(',')""") == "vendor,legacy,base,ui,shell,domain,features,legacy-bridge")  # 每迁一页多一条 layer(features) 的 @import，只比顺序；P5 起 domain 层有 qview.css
    ev("uiToast('已复制')")
    check("旧 uiToast 不传 kind 为成功样式", ev("[...document.querySelectorAll('.ui-toast')].find(t => t.dataset.text === '已复制')?.dataset.kind") == "ok")
    ev("window.__acted = 0; uiToast('已移出展示板', {kind: 'warn', actions: [{label: '撤销', onClick: () => { window.__acted = 1; }}]})")
    page.click(".ui-toast--warn .ui-toast__action")
    check("toast 操作按钮回调", ev("window.__acted") == 1)
    ev("window.__leak = 0; document.addEventListener('keydown', e => { if (e.key === 'Escape') window.__leak++; }); window.__c = uiConfirm('删除？', {danger: true}); 0")
    page.wait_for_selector("dialog.ui-dialog[open]")
    check("危险确认默认聚焦「取消」", ev("document.activeElement?.matches('.ui-dialog__foot [data-dialog-cancel]')"))
    check("守卫能看到新对话框", ev("!!document.querySelector('.modal-overlay.open, dialog[open]')"))
    page.keyboard.press("Escape")
    check("Esc 取消且不外泄", ev("window.__c") is False and ev("window.__leak") == 0)
    ev("window.__p = uiPrompt('新分组名称', '旧名字'); 0")
    page.wait_for_selector("dialog.ui-dialog[open] input")
    page.keyboard.type("第三章")
    page.keyboard.press("Enter")
    check("uiPrompt 预选中、Enter 提交", ev("window.__p") == "第三章")
    ev("window.__d = uiDialog({title: '同步', body: '<label><input type=\"checkbox\" id=\"e2e-chk\" checked> 板 A</label>'}); 0")
    page.wait_for_selector("dialog.ui-dialog[open]")
    page.click("dialog.ui-dialog[open] [data-dialog-ok]")
    check("uiDialog 按 id 收集值", ev("window.__d") == {"ok": True, "values": {"e2e-chk": True}})
    page.wait_for_timeout(400)
    ev("openLabelManager()")
    page.wait_for_selector(".modal-overlay.open")
    ev("window.__c2 = uiConfirm('叠在旧弹层上'); 0")
    page.wait_for_selector("dialog.ui-dialog[open]")
    check("新对话框在旧弹层之上", ev("""(() => { const r = document.querySelector('dialog.ui-dialog[open] .ui-dialog__panel').getBoundingClientRect();
        return !!document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).closest('dialog.ui-dialog'); })()"""))
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    check("Esc 只关新对话框，旧弹层仍在", ev("!!document.querySelector('.modal-overlay.open')"))
    page.keyboard.press("Escape")
    ev("switchTab('questions')")
    page.wait_for_timeout(500)
    bar = ev(HEIGHTS, "#panel-questions .qlb-bar :is(.qlb-search, button, select)")  # P5 起题库工具栏在 features/questions
    check("D2 题库工具栏同一行同一高度", bar and len(set(bar)) == 1, f"高度 {sorted(set(bar))}")
    ev("switchTab('instant')")
    page.wait_for_timeout(500)
    pads = ev("[...document.querySelectorAll('#panel-instant .inst-bar select')].map(s => getComputedStyle(s).paddingTop)")
    check("D3 即时练习 select 无上下内边距（不裁字）", pads and set(pads) == {"0px"}, f"padding-top {sorted(set(pads))}")
    return results


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-ui-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            context.add_init_script(EARLY)
            page = context.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("response", lambda r: r.status >= 400 and errors.append(f"{r.status} {r.url}"))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            results = check_all(page)
            tabs = page.evaluate("[...new Set([...document.querySelectorAll('.sidebar-nav a.tab[data-tab]')].map(e => e.dataset.tab))]")
            for name in tabs:
                page.evaluate("n => switchTab(n)", name)
                page.wait_for_timeout(300)
            results.append((f"{len(tabs)} 个页面切换无报错", len(tabs) >= 12 and not errors, "; ".join(errors[:3])))
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + (f"（{detail}）" if detail else ""))
    print(f"E2E ui_bridge：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
