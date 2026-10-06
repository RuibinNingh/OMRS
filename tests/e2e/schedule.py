"""P6 主路径 E2E：复习调度（assets/app/features/schedule）与 Session 所有权（assets/app/domain/sessions.js）。

    python3 tests/e2e/schedule.py        # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault 与隔离实例，用 /api/confirm-schedule 建 Session。覆盖：标签栏（点击、←/→/Home/End、待完成计数）；
「已有计划」筛选、搜索、详情、预览、录入结果、导出屏幕版、后开的详情不被旧响应覆盖；删除（确认期间不重复请求、取消保留、
业务错误保留、成功移除并刷新）；刷新失败与重试；全题库导出的来处与返回；入口（生成计划后打开它、schedule:open-plan 事件、空推荐「查看已有计划」）；
旧 SESSIONS 是 domain 快照的镜像；手机列表 / 详情切换；桌面 / 手机 × 浅 / 深审计（只审本页原生部分 #sch-app）。
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)

AUDIT = """(minTarget) => {
  const root = document.getElementById('sch-app');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent);
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a, b) => a - b);
  const hit = e => ['BUTTON', 'SELECT', 'INPUT', 'SUMMARY'].includes(e.tagName) || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < minTarget && e.type !== 'checkbox'; })
    .map(e => `${e.tagName}.${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible').length;
  return { sizes, small, inline: root.querySelectorAll('[style]').length, handlers: root.querySelectorAll('[onclick]').length, over,
           overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""
READY = "() => document.querySelector('#sch-tab-plans') && typeof REC_LOADING !== 'undefined' && !REC_LOADING"


def http(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))


def make_session(port, uids):
    before = {s["session_id"] for s in http(port, "/api/sessions")["sessions"]}
    http(port, "/api/confirm-schedule", {"selected": [{"uid": u, "source": "due"} for u in uids], "persist": True})
    return [s for s in http(port, "/api/sessions")["sessions"] if s["session_id"] not in before][0]["session_id"]


def launch_browser(p):
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()


def wait(page, expression, timeout=6000, arg=None):
    try:
        page.wait_for_function(expression, arg=arg, timeout=timeout)
        return True
    except Exception:  # playwright TimeoutError
        return False


def http(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))


def guarded(results, name, fn):
    try:
        fn()
    except Exception as error:  # 一段出错不影响后面的段落
        results.append((f"{name}：段落执行出错", False, repr(error)[:300]))


def open_schedule(page, base):
    page.goto(f"{base}/?t={os.urandom(3).hex()}#/schedule", wait_until="networkidle")
    return wait(page, READY)


def plans(page):
    page.click("#sch-tab-plans")
    return wait(page, "() => !document.getElementById('recommend-panel-v2') && document.getElementById('sch-plans')")


def run_main(page, base, port, sids, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    check("首屏：默认「安排复习」，旧推荐区可见、「已有计划」未渲染", open_schedule(page, base)
          and ev("!!document.getElementById('recommend-panel-v2')?.offsetParent && !document.getElementById('sch-plans') && !document.getElementById('export-panel')"))
    check("待完成计数 = 未结束的 Session 数；旧 SESSIONS 是 domain 快照的镜像",
          ev("document.querySelector('.schd-count').textContent") == f"待完成 {len(sids)}" and ev("Array.isArray(SESSIONS) && SESSIONS.length") == len(sids))
    page.focus("#sch-tab-arrange")
    page.keyboard.press("ArrowRight")
    k1 = wait(page, "() => document.getElementById('sch-tab-plans')?.getAttribute('aria-selected') === 'true' && document.activeElement.id === 'sch-tab-plans'")
    page.keyboard.press("Home")
    k2 = wait(page, "() => SCH_VIEW === 'arrange' && document.activeElement.id === 'sch-tab-arrange'")
    check("标签页键盘：→ 到「已有计划」，Home 回「安排复习」，焦点跟随", k1 and k2)
    plans(page)
    check("「已有计划」列出待完成计划", ev("document.querySelectorAll('.schd-plan').length") == len(sids))
    page.select_option("#sch-plan-filter", "completed")
    empty_ok = wait(page, "() => !document.querySelector('.schd-plan') && document.querySelector('#sch-plans .ui-empty')")
    page.select_option("#sch-plan-filter", "all")
    page.fill("#sch-plan-search", sids[1][-6:])
    one = wait(page, "() => document.querySelectorAll('.schd-plan').length === 1")
    page.fill("#sch-plan-search", "")
    check("筛选「已完成」为空状态；「全部」+ 搜索编号只剩一条", empty_ok and one)
    # 后开的详情不被先发的旧响应覆盖
    def slow(route):
        time.sleep(1.2)
        route.continue_()
    page.route(f"**/api/session?id={sids[0]}", slow)
    page.click(f'.schd-plan[data-arg="{sids[0]}"]')
    page.click(f'.schd-plan[data-arg="{sids[1]}"]')
    wait(page, "id => document.getElementById('sch-plan-detail').textContent.includes(id)", arg=sids[1])
    page.wait_for_timeout(1600)
    sid = ev("document.querySelector('#sch-plan-detail [data-sid]')?.dataset.sid")
    page.unroute(f"**/api/session?id={sids[0]}")
    check("后开的计划详情不被先发的旧响应覆盖", sid == sids[1], [sid, sids])
    page.click(f'.schd-plan[data-arg="{sids[0]}"]')
    wait(page, "() => document.querySelectorAll('#sch-plan-detail .schd-q').length > 0")
    n = ev("document.querySelectorAll('#sch-plan-detail .schd-q').length")
    check("详情：题目行数与计划一致，显示「已录入 0 / 共 N 题」", n == 3 and f"已录入 0 / 共 3 题" in ev("document.getElementById('sch-plan-detail').textContent"), n)
    page.click('#sch-plan-detail [data-action="schedule.preview"] >> nth=0')
    ok = wait(page, "() => document.querySelector('dialog[open] [data-qv-uid]')")
    ev("closeModal()")
    wait(page, "() => !document.querySelector('dialog[open]:not(.is-closing)')")
    check("「预览」打开题目弹窗", ok)
    page.click("#sch-plan-detail summary")
    page.check("#sch-include-answers")
    page.fill("#sch-question-gap", "3")
    ev("__omrs.emit('sessions')")
    kept = ev("[document.getElementById('sch-include-answers').checked, document.getElementById('sch-question-gap').value]")
    check("打印选项在重绘后保留（存在页面状态里）", kept == [True, "3"], kept)
    with page.expect_download() as info:
        page.click('[data-action="schedule.export"][data-arg="screen"]')
    check("导出屏幕版：下载 HTML", info.value.suggested_filename.endswith(".html"), info.value.suggested_filename)
    page.click('[data-action="schedule.feedback"]')
    check("「录入结果」→ 反馈录入并选中该计划", wait(page, "id => location.hash === '#/feedback' && ACTIVE_FB_SESSION === id", arg=sids[0]))


def run_delete(page, base, port, sids, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    open_schedule(page, base)
    plans(page)
    page.click(f'.schd-plan[data-arg="{sids[1]}"]')
    wait(page, "() => document.querySelector('#sch-plan-detail .schd-q')")
    posts = []
    page.on("request", lambda r: posts.append(r.url) if "/api/session/delete" in r.url else None)
    page.click('[data-action="schedule.remove"]')
    wait(page, "() => document.querySelector('dialog[open] [data-dialog-cancel]')")
    busy = ev("document.querySelector('[data-action=\"schedule.remove\"]').disabled")
    page.click("dialog[open] [data-dialog-cancel]")
    wait(page, "() => !document.querySelector('dialog[open]:not(.is-closing)')")
    check("删除确认期间按钮置忙；取消后不发请求、计划保留", busy and not posts and ev("document.querySelectorAll('.schd-plan').length") == len(sids))
    page.route("**/api/session/delete", lambda r: r.fulfill(content_type="application/json", body='{"status":"error","deleted":false}'))
    page.click('[data-action="schedule.remove"]')
    page.click("dialog[open] [data-dialog-ok]")
    err = wait(page, "() => document.body.textContent.includes('删除失败') && !document.querySelector('[data-action=\"schedule.remove\"]').disabled")
    page.unroute("**/api/session/delete")
    check("删除业务错误：提示失败，计划保留、按钮恢复可用", err and ev("document.querySelectorAll('.schd-plan').length") == len(sids))
    page.click('[data-action="schedule.remove"]')
    page.click("dialog[open] [data-dialog-ok]")
    gone = wait(page, "id => !document.querySelector(`.schd-plan[data-arg=\"${id}\"]`) && !SESSIONS.some(s => s.session_id === id)", arg=sids[1])
    check("删除成功：列表与旧 SESSIONS 都去掉该计划，详情回到空状态，服务端也没有了",
          gone and ev("!!document.querySelector('#sch-plan-detail .ui-empty')") and sids[1] not in [s["session_id"] for s in http(port, "/api/sessions")["sessions"]],
          ev("[document.querySelectorAll('.schd-plan').length, SESSIONS.map(s => s.session_id), document.getElementById('sch-plan-detail').textContent.slice(0, 60)]"))
    wait(page, "() => !document.querySelector('[data-action=\"schedule.remove\"]')")
    page.route("**/api/sessions", lambda r: r.fulfill(status=503, content_type="application/json", body='{"msg":"测试离线"}'))
    page.click('[data-action="schedule.refresh"] >> nth=0')
    failed = wait(page, "() => document.getElementById('sch-session-status').textContent.includes('计划加载失败：测试离线')")
    kept = ev("document.querySelectorAll('.schd-plan').length")
    page.unroute("**/api/sessions")
    page.click('#sch-session-status [data-action="schedule.refresh"]')
    check("刷新失败显示原因与「重试」、列表保留；重试后状态行清空", failed and kept >= 1 and wait(page, "() => !document.getElementById('sch-session-status').textContent.trim()"), kept)


def run_legacy(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    open_schedule(page, base)
    plans(page)
    page.click('.schd-top [data-action="schedule.view"][data-arg="export"]')
    e1 = wait(page, "() => document.getElementById('export-panel') && SCH_EXPORT_RETURN === 'plans' && !document.getElementById('sch-plans')")
    page.click('#export-panel [data-action="schedule.view"][data-arg="back"]')
    check("全题库导出：记住来处，「返回」回到「已有计划」", e1 and wait(page, "() => document.getElementById('sch-tab-plans')?.getAttribute('aria-selected') === 'true' && document.getElementById('sch-plans') && !document.getElementById('export-panel')"))
    page.click("#sch-tab-arrange")
    wait(page, "() => !REC_LOADING && REC_DATA_V2 && REC_DATA_V2.length")
    page.fill("#rec-target-count", "1")
    page.click("#rec-suggest")
    page.click("#rec-confirm")
    made = wait(page, "() => document.getElementById('sch-tab-plans')?.getAttribute('aria-selected') === 'true' && document.getElementById('sch-plan-filter').value === 'active' && document.getElementById('sch-plan-detail').textContent.includes('共 1 题')", timeout=10000)
    check("旧入口：安排复习里「生成计划」后切到「已有计划」并打开新计划", made)
    sid = [s for s in http(port, "/api/sessions")["sessions"]][0]["session_id"]
    ev("window.__omrs.router.go('dashboard')")
    ev(f"window.__omrs.router.go('schedule'); window.__omrs.emit('schedule:open-plan', {json.dumps(sid)})")
    check("schedule:open-plan：从别的页切过来并打开该计划",
          wait(page, "id => location.hash === '#/schedule' && document.getElementById('sch-plan-detail').textContent.includes(id)", arg=sid))
    page.route("**/api/recommend?*", lambda r: r.fulfill(content_type="application/json", body='{"due":[],"proficiency":[]}'))
    page.click("#sch-tab-arrange")
    shown = wait(page, "() => !REC_LOADING && document.getElementById('rec-unified-list-v2').textContent.includes('查看已有计划')")
    page.unroute("**/api/recommend?*")
    page.get_by_role("button", name="查看已有计划", exact=True).click()
    check("从别的工作区切回「安排复习」会重拉推荐；空推荐「查看已有计划」切到计划", shown and wait(page, "() => document.getElementById('sch-tab-plans')?.getAttribute('aria-selected') === 'true'"))



def run_arrange(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    page.add_init_script("try{localStorage.removeItem('omrs-schedule-view')}catch(e){}")
    open_schedule(page, base)
    n = ev("REC_DATA_V2.length")
    check("安排复习原生渲染：候选行数 = 可安排题数，摘要一致", ev("document.querySelectorAll('.schd-cand').length") == n
          and ev("document.getElementById('rec-summary-v2').textContent") == f"当前显示 {n} 题 · 可安排 {n} 题", n)
    page.click("#rec-suggest")
    sel = ev("document.getElementById('rec-selected-count-v2').textContent")
    subject = ev("document.querySelector('#rec-subject-v2 option:nth-child(2)').value")
    page.select_option("#rec-subject-v2", subject)
    kept = ev("document.getElementById('rec-selected-count-v2').textContent")
    chip = ev("document.getElementById('rec-filter-chips').textContent")
    page.get_by_role("button", name="清除筛选", exact=True).first.click()
    check("按建议选择 10 题；换科目不丢选择、出现可移除的筛选 chip；清除筛选恢复", sel == "已选 10 题" and kept == sel and f"科目 {subject}" in chip
          and ev("document.querySelectorAll('.schd-cand').length") == n, [sel, kept, chip])
    page.click("#rec-view-gallery")
    g = wait(page, "() => document.querySelector('.schd-cands[data-view=\"gallery\"] .schd-cand__preview .q-md')")
    ev("__omrs.emit('schedule:render')")
    same = ev("!!document.querySelector('.schd-cand__preview .q-md')")
    check("画廊：题面懒加载进挂载点，重绘后题面不丢（data-morph=skip）", g and same)
    page.click("#rec-view-list")
    posts = []
    page.on("request", lambda r: posts.append(r.url) if "/api/confirm-schedule" in r.url else None)
    before = len(http(port, "/api/sessions")["sessions"])
    ev("(() => { const b = document.getElementById('rec-confirm'); b.click(); b.click(); })()")
    made = wait(page, "() => document.getElementById('sch-tab-plans')?.getAttribute('aria-selected') === 'true' && document.getElementById('sch-plan-detail').textContent.includes('共 10 题')", timeout=10000)
    check("生成计划：重复调用只提交一次，切到「已有计划」打开新计划，已选清空", made and len(posts) == 1 and len(http(port, "/api/sessions")["sessions"]) == before + 1, posts)


def run_export(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    open_schedule(page, base)
    page.click('.schd-top [data-action="schedule.view"][data-arg="export"]')
    wait(page, "() => document.getElementById('export-summary')")
    total = len([i for i in http(port, "/api/stats")["items"] if not i.get("suspended")])
    check("全题库导出原生渲染：默认筛出全部未停用题", ev("document.getElementById('export-summary').textContent") == f"已筛出 {total} 题，已选择 0 题。")
    page.click('[data-action="schedule.xexport"]')
    check("没选题就导出：页内提示「请选择至少 1 道题」", wait(page, "() => document.getElementById('export-status').textContent.includes('请选择至少 1 道题')"))
    subject = ev("document.querySelector('#pick-subject option:nth-child(2)').value")
    page.select_option("#pick-subject", subject)
    n = ev("document.querySelectorAll('.schd-xpick .schd-xrow').length")
    page.click('[data-action="schedule.xaddFiltered"]')
    page.select_option("#pick-subject", "")
    m = ev("document.querySelectorAll('.schd-xsel .schd-xrow').length")
    page.click('.schd-xpick .schd-xrow:not(.is-selected) [data-action="schedule.xtoggle"] >> nth=0')
    check("按科目「选择当前筛选」加入该科目全部题；逐题「加入」追加到末尾", m == n and ev("document.querySelectorAll('.schd-xsel .schd-xrow').length") == n + 1, [subject, n, m])
    page.click("#export-view-gallery")
    page.locator(".schd-xgrid").scroll_into_view_if_needed()
    check("画廊式：题面懒加载进卡片", wait(page, "() => document.querySelector('.schd-xcard__preview .q-md')"))
    page.click("#export-view-flat")
    page.click("#export-variant-screen")
    screen = ev("[document.getElementById('export-include-answers').checked, document.getElementById('export-include-answers').disabled, document.getElementById('export-question-gap').disabled]")
    with page.expect_download() as info:
        page.click('[data-action="schedule.xexport"]')
    ok = info.value.suggested_filename
    check("屏幕版：附带答案强制勾选、留白禁用；导出直接下载，页内显示结果", screen == [True, True, True] and ok.endswith(".html")
          and wait(page, "() => document.getElementById('export-status').textContent.includes('已导出')"), [screen, ok])
    page.click("#export-variant-a4")
    page.fill("#export-question-gap", "2")
    with page.expect_download() as info:
        page.click('[data-action="schedule.xexport"]')
        page.click("dialog[open] [data-dialog-cancel]:not(.ui-dialog__close)")
    check("A4：先问单 / 双栏（选单栏也导出），文件名带 a4", "a4" in info.value.suggested_filename, info.value.suggested_filename)
    with tempfile.TemporaryDirectory(prefix="omrs-schedule-a4-") as output:
        path = os.path.join(output, "a4.html")
        info.value.save_as(path)
        printed = page.context.new_page()
        try:
            printed.goto("file://" + path)
            printed.wait_for_function("window.__OMRS_RESULT?.errors?.length || !document.getElementById('btnPrint').disabled")
            layout = printed.evaluate("window.__OMRS_RESULT")
            overflow = printed.evaluate("""() => [...document.querySelectorAll('.col')].some(col =>
                [...col.children].some(node => node.getBoundingClientRect().bottom > col.getBoundingClientRect().bottom + .03))""")
            pdf = printed.pdf(prefer_css_page_size=True)
            check("下载的 A4 离线打开：字体就绪、无栏底溢出、PDF 页数一致",
                  not layout["errors"] and not overflow and not printed.locator("#btnPrint").is_disabled()
                  and len(re.findall(rb"/Type /Page\b", pdf)) == layout["pages"], layout)
        finally:
            printed.close()
    page.route("**/api/export", lambda r: r.fulfill(status=400, content_type="application/json", body='{"msg":"题目不存在"}'))
    page.click("#export-variant-screen")
    page.click('[data-action="schedule.xexport"]')
    check("导出失败：原因显示在导出栏", wait(page, "() => document.getElementById('export-status').textContent.includes('导出失败：题目不存在')"))
    page.unroute("**/api/export")
    page.click('[data-action="schedule.xremoveFiltered"]')
    check("「移除当前筛选」（未筛选时 = 全部）清空已选", ev("document.querySelectorAll('.schd-xsel .schd-xrow').length") == 0)

def run_mobile(browser, base, results):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    open_schedule(page, base)
    plans(page)
    list_only = page.evaluate("() => !!document.querySelector('.schd-list').offsetParent && !document.getElementById('sch-plan-detail').offsetParent")
    page.click(".schd-plan >> nth=0")
    detail = wait(page, "() => !document.querySelector('.schd-list').offsetParent && document.querySelector('#sch-plan-detail .schd-q')")
    page.click('[data-action="schedule.back"]')
    back = wait(page, "() => document.querySelector('.schd-list').offsetParent")
    results.append(("手机：先列表，点计划进详情，「返回计划列表」回来；无横向溢出", list_only and detail and back
                    and not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), ""))
    ctx.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-schedule-")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", os.path.join(work, "full")], check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, os.path.join(work, "full"), os.path.join(work, "full.log"))
    base = f"http://127.0.0.1:{port}"
    uids = [i["uid"] for i in http(port, "/api/stats")["items"] if not i.get("suspended")]
    sids = [make_session(port, uids[0:3]), make_session(port, uids[3:5])]
    results = []
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            guarded(results, "主路径", lambda: run_main(page, base, port, sids, results))
            guarded(results, "删除与刷新", lambda: run_delete(page, base, port, sids, results))
            guarded(results, "旧入口", lambda: run_legacy(page, base, port, results))
            guarded(results, "安排复习", lambda: run_arrange(page, base, port, results))
            guarded(results, "全题库导出", lambda: run_export(page, base, port, results))
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            guarded(results, "手机", lambda: run_mobile(browser, base, results))
            for theme in ("light", "dark"):
                for label, size, target in (("桌面", (1440, 900), 28), ("手机", (390, 844), 40)):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    pg = c.new_page()
                    open_schedule(pg, base)
                    b = pg.evaluate(AUDIT, target)
                    pg.click('.schd-top [data-action="schedule.view"][data-arg="export"]')
                    wait(pg, "() => document.getElementById('export-summary')")
                    pg.click('[data-action="schedule.xaddFiltered"]')
                    c2 = pg.evaluate(AUDIT, target)
                    ok2 = len(c2["sizes"]) <= 6 and min(c2["sizes"]) >= 12 and not c2["small"] and not c2["inline"] and not c2["handlers"] and not c2["over"] and not c2["overflow"]
                    results.append((f"审计「全题库导出」{label} · {'浅色' if theme == 'light' else '深色'}：字号 ≤6 且 ≥12px、可点目标 ≥{target}、无行内样式与 onclick、无溢出", ok2, str(c2)))
                    pg.click('#export-panel [data-action="schedule.view"][data-arg="back"]')
                    ok = len(b["sizes"]) <= 6 and min(b["sizes"]) >= 12 and not b["small"] and not b["inline"] and not b["handlers"] and not b["over"] and not b["overflow"]
                    results.append((f"审计「安排复习」{label} · {'浅色' if theme == 'light' else '深色'}：字号 ≤6 且 ≥12px、可点目标 ≥{target}、无行内样式与 onclick、无溢出", ok, str(b)))
                    plans(pg)
                    pg.click(".schd-plan >> nth=0")
                    wait(pg, "() => document.querySelector('#sch-plan-detail .schd-q')")
                    pg.click("#sch-plan-detail summary")
                    a = pg.evaluate(AUDIT, target)
                    ok = len(a["sizes"]) <= 6 and min(a["sizes"]) >= 12 and not a["small"] and not a["inline"] and not a["handlers"] and not a["over"] and not a["overflow"]
                    results.append((f"审计 {label} · {'浅色' if theme == 'light' else '深色'}：字号 ≤6 且 ≥12px、可点目标 ≥{target}、无行内样式与 onclick、无溢出", ok, str(a)))
                    c.close()
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E schedule：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
