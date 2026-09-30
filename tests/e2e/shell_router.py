"""P1 主路径 E2E：hash 路由、刷新停留、前进后退、旧 onclick、外壳（折叠、手机抽屉与标题）、静态资源 304；
DP4：顶栏只留「录入题目」，「重新扫描」在仪表盘 / 题库 / 目录三页。

    python3 tests/e2e/shell_router.py         # 全部通过退出码 0；没有 playwright 退出码 2

自己生成 fixture Vault（tests/fixtures/make_vault.py），在临时端口起隔离实例，不碰真实数据。
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)


def launch_browser(p):
    """设了 OMRS_TEST_CDP_URL 时连接已开着的 Chromium（本机直接启动会崩溃的环境用），否则自行启动。"""
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()

PAGES = {"dashboard": ("仪表盘", False), "data": ("数据复盘", False), "questions": ("题目库", True),
         "board": ("展示板", True), "catalog": ("目录", False), "schedule": ("复习调度", False),
         "instant": ("即时练习", True), "feedback": ("反馈录入", True), "create": ("录入题目", True),
         "history": ("历史记录", False), "reports": ("报告", False), "settings": ("设置", False)}
STATE = """() => ({ hash: location.hash, title: document.getElementById('topbar-title').textContent,
  docTitle: document.title, panel: document.querySelector('.content > .panel.active')?.id,
  current: document.querySelector('.sidebar-nav .tab[aria-current="page"]')?.dataset.tab,
  workbench: document.querySelector('.content').classList.contains('is-workbench') })"""


def settle(page, expression, timeout=3000):
    """等到页面里的条件成立（过渡结束、地址改回等）；超时返回 False，由调用方记为失败而不是直接抛错。"""
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:  # playwright 的 TimeoutError
        return False


def run_checks(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    ev = page.evaluate
    page.goto(f"{base}/", wait_until="networkidle")
    if page.locator("#enter").is_visible():
        page.locator("#enter").click()
        page.wait_for_load_state("networkidle")
    st = ev(STATE)
    check("首次打开落到 #/dashboard", st["hash"] == "#/dashboard" and st["panel"] == "panel-dashboard", str(st))
    check("文档标题与侧栏 aria-current", st["docTitle"] == "仪表盘 · OMRS" and st["current"] == "dashboard")
    check("没有待审核草稿时侧栏角标隐藏", ev("document.getElementById('nav-draft-count').hidden && getComputedStyle(document.getElementById('nav-draft-count')).display === 'none'"))
    check("init() 由 main.js 调用，reloadData 同步到 store", ev("!!window.__omrs && !!window.__omrs.store.get().data")
          and ev("!!document.querySelector('#panel-dashboard [data-dash-ready]')"))
    bad = []
    for pid, (title, workbench) in PAGES.items():
        page.goto(f"{base}/#/{pid}", wait_until="networkidle")
        st = ev(STATE)
        if not (st["panel"] == f"panel-{pid}" and st["title"] == title and st["current"] == pid and st["workbench"] == workbench):
            bad.append(f"{pid}:{st}")
    check("12 个页面都能按地址直接进入（刷新停留）", not bad, "; ".join(bad[:2]))
    page.goto(f"{base}/#/dashboard", wait_until="networkidle")
    page.click('a.tab[data-tab="questions"]')
    check("点侧栏链接同步切页", ev(STATE)["panel"] == "panel-questions" and ev("location.hash") == "#/questions")
    page.click('a.tab[data-tab="board"]')
    page.go_back()
    page.wait_for_function("location.hash === '#/questions'")
    back1 = ev(STATE)["panel"]
    page.go_back()
    page.wait_for_function("location.hash === '#/dashboard'")
    back2 = ev(STATE)["panel"]
    page.go_forward()
    page.wait_for_function("location.hash === '#/questions'")
    check("浏览器后退 / 前进", back1 == "panel-questions" and back2 == "panel-dashboard" and ev(STATE)["panel"] == "panel-questions")
    ev("() => { window.__omrs.router.go('board'); window.__guardDispose = window.__omrs.router.setLeaveGuard(() => new Promise(resolve => { window.__guardResolve = resolve; })); }")
    ev("window.history.back()")
    page.wait_for_function("typeof window.__guardResolve === 'function'")
    waiting = ev(STATE)
    ev("window.__guardResolve(false)")
    settle(page, "location.hash === '#/board' && history.state?.omrsRouteIndex >= 0")
    page.wait_for_timeout(100)
    check("异步离页守卫取消后退时保留页面与地址", waiting["panel"] == "panel-board" and ev(STATE)["hash"] == "#/board")
    ev("window.__guardResolve = null; window.history.back()")
    page.wait_for_function("typeof window.__guardResolve === 'function'")
    ev("window.__guardResolve(true)")
    settle(page, "location.hash === '#/questions' && document.querySelector('.content > .panel.active')?.id === 'panel-questions'")
    check("取消后再次允许后退仍到原上一页", ev(STATE)["panel"] == "panel-questions" and ev(STATE)["hash"] == "#/questions")
    ev("window.__guardDispose(); delete window.__guardDispose; delete window.__guardResolve")
    page.reload(wait_until="networkidle")
    check("刷新后停在原页", ev(STATE)["panel"] == "panel-questions")
    ev("window.__omrs.router.go('history')")
    check("旧 window.__omrs.router.go() 仍可用并写地址", ev(STATE)["panel"] == "panel-history" and ev("location.hash") == "#/history")
    page.click('a.tab[data-tab="dashboard"]')
    page.click("#panel-dashboard [data-action=\"dashboard.go\"][data-arg=\"history\"]")
    check("仪表盘「完整时间线」按钮（data-action）切到历史记录", ev(STATE)["panel"] == "panel-history")
    page.goto(f"{base}/#/nope", wait_until="networkidle")
    check("未知地址回到仪表盘", ev(STATE)["panel"] == "panel-dashboard" and ev("location.hash") == "#/dashboard")
    page.click('a.tab[data-tab="board"]')
    ev("location.hash = '#'")
    settle(page, "location.hash === '#/board'")
    check("非路由 hash 不切页并恢复地址", ev(STATE)["panel"] == "panel-board" and ev("location.hash") == "#/board")
    # 展示板使用独立窄导航；侧栏折叠控件在普通页面验证。
    ev("window.__omrs.router.go('questions')")
    width = "Math.round(document.querySelector('.sidebar').getBoundingClientRect().width)"
    page.click(".sidebar-collapse")
    settle(page, f"{width} === 58")
    collapsed = ev("[document.documentElement.dataset.sidebar, Math.round(document.querySelector('.sidebar').getBoundingClientRect().width), document.querySelector('.tab[data-tab=\"board\"]').dataset.tooltip]")
    page.click(".sidebar-collapse")
    settle(page, f"{width} === 232")
    expanded = ev("[Math.round(document.querySelector('.sidebar').getBoundingClientRect().width), document.querySelector('.tab[data-tab=\"board\"]').hasAttribute('data-tooltip')]")
    check("侧栏折叠为 58px 图标栏并挂提示，展开恢复", collapsed == ["collapsed", 58, "展示板"] and expanded == [232, False], f"{collapsed} / {expanded}")
    # DP4：顶栏只剩「录入题目」；三页工具栏各有一个「重新扫描」，点击走 /api/scan，期间按钮置忙
    ev("window.__omrs.router.go('dashboard')")
    top = ev("[...document.querySelectorAll('.topbar-actions .topbar-action')].map(b => b.textContent.trim())")
    where = {}
    for pid in ("dashboard", "questions", "catalog"):
        ev(f"window.__omrs.router.go('{pid}')")
        where[pid] = ev(f"[...document.querySelectorAll('#panel-{pid} [data-action=\"app.scan\"]')].filter(b => b.offsetParent).map(b => Math.round(b.getBoundingClientRect().height))")
    check("DP4：顶栏只剩「录入题目」，三页各有一个可见的「重新扫描」", top == ["录入题目"] and all(len(v) == 1 for v in where.values()), f"{top} {where}")
    with page.expect_response(lambda r: r.url.endswith("/api/scan") and r.request.method == "POST") as scan:
        page.click('#panel-catalog [data-action="app.scan"]')
        busy = ev("document.querySelector('#panel-catalog [data-action=\"app.scan\"]').getAttribute('aria-busy')")
    done = settle(page, "!document.querySelector('[data-action=\"app.scan\"][aria-busy]') && [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('扫描完成'))", 8000)
    check("DP4：点「重新扫描」调用 /api/scan、期间置忙、完成后提示", scan.value.status == 200 and busy == "true" and done, f"busy={busy} done={done}")


def run_mobile(browser, base, results):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/#/questions", wait_until="networkidle")
    title = page.evaluate("(() => { const t = document.getElementById('topbar-title'); return [t.textContent, t.clientWidth >= t.scrollWidth, Math.round(t.getBoundingClientRect().width)]; })()")
    buttons = page.evaluate("[...document.querySelectorAll('.topbar-action')].map(b => [Math.round(b.getBoundingClientRect().width), Math.round(b.getBoundingClientRect().height)])")
    results.append(("手机：标题完整不被按钮挤压", title[0] == "题目库" and title[1] and title[2] >= 120, str(title)))
    results.append(("手机：顶栏只有一个 40×40 图标按钮（录入题目）", buttons == [[40, 40]], str(buttons)))
    page.click(".topbar-hamburger")
    settle(page, "document.body.classList.contains('drawer-open') && getComputedStyle(document.querySelector('.sidebar')).visibility === 'visible'")
    opened = page.evaluate("[document.body.classList.contains('drawer-open'), getComputedStyle(document.querySelector('.sidebar')).visibility]")
    page.click('a.tab[data-tab="schedule"]')
    settle(page, "location.hash === '#/schedule' && !document.body.classList.contains('drawer-open')")
    after = page.evaluate("[location.hash, document.body.classList.contains('drawer-open')]")
    results.append(("手机：抽屉打开、点导航切页后自动关闭", opened == [True, "visible"] and after == ["#/schedule", False], f"{opened} / {after}"))
    results.append(("手机：页面无脚本错误", not errors, "; ".join(errors[:2])))
    context.close()


def check_etag(base, results):
    url = f"{base}/assets/app/main.js"
    etag = urllib.request.urlopen(url, timeout=10).headers.get("ETag")
    request = urllib.request.Request(url, headers={"If-None-Match": etag or ""})
    try:
        status = urllib.request.urlopen(request, timeout=10).status
    except urllib.error.HTTPError as error:
        status = error.code
    results.append(("静态资源带 ETag，未变时回 304", bool(etag) and status == 304, f"{etag} → {status}"))


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-shell-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("response", lambda r: r.status >= 400 and errors.append(f"{r.status} {r.url}"))
            run_checks(page, base, results)
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            context.close()
            run_mobile(browser, base, results)
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
        check_etag(base, results)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E shell_router：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
