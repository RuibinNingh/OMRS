"""P6 主路径 E2E：仪表盘（assets/app/features/dashboard）与统计数据所有权（assets/app/domain/data.js）。

    python3 tests/e2e/dashboard.py        # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault（full 与 empty 两档）与隔离实例，不碰真实数据；用 /api/confirm-schedule 建 Session。覆盖：
数据所有权（旧 DATA 是 store.data 的镜像、reloadData 并发合并、失败保留旧快照、详情缓存只读全局）；「今天」卡与概览的数字；
D8（「今天」是独立卡片、与行动推荐之间有间距、主按钮不再通栏）；行动推荐展开 / 收起与跳转（题库预设、复习调度、反馈录入带 Session、
即时练习）；最薄弱科目跳题库；最近动态与「完整时间线」；空库与首次加载失败；手机单栏；桌面 / 手机 × 浅 / 深审计
（字号 ≤6 种、可点目标桌面 ≥28 / 手机 ≥40、无行内样式、无横向溢出）。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)

AUDIT = """(minTarget) => {
  const root = document.getElementById('panel-dashboard');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent);
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a, b) => a - b);
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button'
    || (e.tagName === 'A' && e.hasAttribute('href')) || e.hasAttribute('onclick') || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < minTarget; })
    .map(e => `${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  return { sizes, small, inline: root.querySelectorAll('[style]').length, handlers: root.querySelectorAll('[onclick]').length,
           overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""
READY = "() => document.querySelector('#panel-dashboard [data-dash-ready]') && window.__omrs && window.__omrs.store.get().data"


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


def home(page, base):
    page.goto(f"{base}/?t={os.urandom(3).hex()}#/dashboard", wait_until="networkidle")
    return wait(page, READY)


def run_ownership(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    check("首屏就绪（data-dash-ready）", home(page, base))
    check("旧 DATA 是 store.data 的镜像（同一对象），reloadData 是 domain 的实现",
          ev("DATA === __omrs.store.get().data && typeof reloadData === 'function' && !('demo' in window)"))
    stats = []
    page.on("request", lambda r: stats.append(r.url) if "/api/stats" in r.url else None)
    ev("Promise.all([reloadData(), reloadData(), reloadData()])")
    check("并发三次 reloadData 只发两次 /api/stats（一次进行中 + 一次补拉）", len(stats) == 2, stats)
    before = ev("DATA.total")
    page.route("**/api/stats", lambda route: route.fulfill(status=503, content_type="application/json", body='{"msg":"服务重启中"}'))
    res = ev("reloadData().then(r => ({ ok: r.ok, msg: r.error && r.error.message, total: DATA.total, same: DATA === __omrs.store.get().data }))")
    page.unroute("**/api/stats")
    check("加载失败保留上一份快照（不再换成演示数据），页面仍显示原数字",
          res == {"ok": False, "msg": "服务重启中", "total": before, "same": True}
          and ev("document.querySelector('.dsh-kpi[data-key=\"total\"] .dsh-kpi__value').textContent") == str(before), res)
    uid = ev("DATA.items[0].uid")
    ev(f"viewQ({json.dumps(uid)})")
    got = wait(page, "u => !!QUESTION_CACHE[u]", arg=uid)
    ev("closeModal()")
    check("详情缓存归 domain：QUESTION_CACHE 是只读全局，看过的题在里面", got and ev("Object.getOwnPropertyDescriptor(window, 'QUESTION_CACHE').set === undefined"))


def run_numbers(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    home(page, base)
    want = ev("""() => { const act = DATA.items.filter(i => !i.suspended && !(Number(i.mastery) >= 1 || String(i.tag || '').includes('已击杀')));
      return act.filter(i => { const d = getDueDays(i); return d !== null && d <= 0; }).length; }""")
    got = ev("Number(document.querySelector('.dsh-today__value').textContent)")
    check("「今天」的待复习数 = 未停用、未击杀、逾期或今日到期的题数（与旧 getDueDays 同口径）", got == want, [got, want])
    kp = ev("[...document.querySelectorAll('.dsh-kpi__value')].map(e => e.textContent)")
    check("概览五个数字与 /api/stats 一致", kp[:3] == [str(ev("DATA.total")), str(ev("DATA.killed")), str(ev("DATA.attacking"))]
          and kp[4] == str(ev("DATA.suspended || 0")), kp)
    geo = ev("""() => { const t = document.querySelector('.dsh-today'), p = document.querySelector('.dsh-plan'),
        b = t.querySelector('.dsh-today__acts .ui-btn--primary'), cs = getComputedStyle(t);
      return { gap: Math.round(p.getBoundingClientRect().top - t.getBoundingClientRect().bottom), card: cs.borderTopWidth !== '0px' && cs.backgroundColor !== getComputedStyle(document.body).backgroundColor,
               btn: b.getBoundingClientRect().width / t.getBoundingClientRect().width }; }""")
    check("D8：「今天」是独立卡片，与行动推荐间距 16px，主按钮不再通栏", geo["gap"] == 16 and geo["card"] and geo["btn"] < 0.3, geo)
    check("行动推荐图标是 SVG（不再用字符当图标）", ev("[...document.querySelectorAll('.dsh-act__icon')].every(e => e.querySelector('svg') && !e.textContent.trim())"))
    rows = ev("document.querySelectorAll('.dsh-act').length")
    total = ev("__omrs.store.get().data && document.querySelector('.dsh-plan__more') ? document.querySelector('.dsh-plan__more').textContent : ''")
    page.click(".dsh-plan__more button")
    opened = wait(page, "n => document.querySelectorAll('.dsh-act').length > n", arg=rows)
    page.click(".dsh-plan__more button")
    closed = wait(page, "n => document.querySelectorAll('.dsh-act').length === n", arg=rows)
    check("行动推荐默认 4 条，「还有 N 条建议」展开、「收起」收回", rows == 4 and "还有" in total and opened and closed, [rows, total])
    heat = ev("""() => { const cells = [...document.querySelectorAll('.dsh-heat__grid .dsh-heat__cell')];
      const today = new Date(), key = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
      return [cells.length, cells.at(-1)?.dataset.level, Number(DATA.recent_activity?.[key] || 0),
              cells.some(cell => cell.dataset.level !== '0')]; }""")
    check("近 30 天热力 30 格，末格按浏览器当地日期与统计快照着色", heat[0] == 30
          and (heat[1] != "0") == (heat[2] > 0) and heat[3], heat)
    rec = wait(page, "() => document.querySelectorAll('.dsh-recent__row').length > 0")
    check("最近动态加载出行（最多 4 条，按 seq 倒序）", rec and 0 < ev("document.querySelectorAll('.dsh-recent__row').length") <= 4)


def run_navigation(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    home(page, base)
    subject, count = ev("(() => { const b = document.querySelector('.dsh-weak__row'); return [b.dataset.arg, b.querySelector('.dsh-weak__count').textContent]; })()")
    page.click(".dsh-weak__row")
    ok = wait(page, "() => location.hash === '#/questions' && document.querySelector('.qlb-total')")
    shown = ev("document.querySelectorAll('.qlb-total b')[1]?.textContent")
    check("最薄弱科目的一行 → 题库只显示该科目（未停用）", ok and f"{shown} 题" == count, [subject, count, shown])
    home(page, base)
    page.locator(".dsh-today__acts .ui-btn--primary").click()
    check("「开始复习」→ 复习调度的「安排」视图",
          wait(page, "() => location.hash === '#/schedule' && typeof SCH_VIEW !== 'undefined' && SCH_VIEW === 'arrange'"))
    uids = [i["uid"] for i in http(port, "/api/stats")["items"] if not i.get("suspended")][:3]
    http(port, "/api/confirm-schedule", {"selected": [{"uid": u, "source": "due"} for u in uids], "persist": True})
    home(page, base)
    ok = wait(page, "() => document.querySelector('.dsh-act[data-key=\"pending_feedback\"]') && document.querySelector('.dsh-today__split').textContent.includes('未录反馈')")
    sid = ev("SESSIONS.find(s => (s.status || 'active') === 'active').session_id")
    page.click('.dsh-act[data-key="pending_feedback"] .ui-btn--primary')
    check("建了 Session 后出现「未录反馈」；「去录反馈」→ 反馈录入并选中该 Session",
          ok and wait(page, "id => location.hash === '#/feedback' && ACTIVE_FB_SESSION === id", arg=sid), sid)
    home(page, base)
    page.click('.dsh-recent .dsh-recent__row >> nth=0')  # 行本身不可点：点了不跳转
    page.get_by_role("button", name="完整时间线", exact=True).click()
    check("「完整时间线」→ 历史记录", wait(page, "() => location.hash === '#/history'"))
    home(page, base)
    ev("__omrs.emit('ledger:tz')")
    check("Ledger 时区变化（bus 'ledger:tz'）后最近动态仍在", wait(page, "() => document.querySelectorAll('.dsh-recent__row').length > 0"))


def run_empty_and_error(browser, base_empty, results):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    home(page, base_empty)
    t = page.evaluate("[document.querySelector('.dsh-today__unit').textContent, document.querySelectorAll('.dsh-act').length, document.querySelector('.dsh-act').dataset.key, !!document.querySelector('[data-key=\"weak\"] .ui-empty')]")
    page.locator(".dsh-today__acts .ui-btn--primary").click()
    results.append(("空库：「题库还是空的」、行动推荐只剩「去录入」、最薄弱科目是空状态；主按钮 → 录入题目",
                    t == ["题库还是空的", 1, "empty", True] and wait(page, "() => location.hash === '#/create'"), str(t)))
    page.route("**/api/stats", lambda route: route.fulfill(status=500, content_type="application/json", body='{"msg":"磁盘不可读"}'))
    page.goto(f"{base_empty}/?e=1#/dashboard", wait_until="networkidle")
    shown = wait(page, "() => document.querySelector('.dsh-today--error') && document.querySelector('.dsh-today--error').textContent.includes('磁盘不可读')")
    page.unroute("**/api/stats")
    page.click('[data-action="dashboard.retry"]')
    results.append(("首次加载失败：「今天」位置显示原因与「重新加载」，恢复后点它回到正常",
                    shown and wait(page, "() => !document.querySelector('.dsh-today--error') && document.querySelector('.dsh-today__unit')"), ""))
    results.append(("空库与错态：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
    ctx.close()


def run_mobile(browser, base, results):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    home(page, base)
    m = page.evaluate("""() => { const t = document.querySelector('.dsh-today'), g = getComputedStyle(t).gridTemplateColumns.split(' ').length,
        b = [...t.querySelectorAll('.dsh-today__acts .ui-btn')].map(x => Math.round(x.getBoundingClientRect().height)),
        k = getComputedStyle(document.querySelector('.dsh-kpis__list')).gridTemplateColumns.split(' ').length;
      return { cols: g, btn: b, kpi: k, overflow: document.documentElement.scrollWidth > innerWidth + 1 }; }""")
    results.append(("手机：「今天」单栏、按钮 40px、概览两列、无横向溢出",
                    m["cols"] == 1 and m["btn"] and all(h == 40 for h in m["btn"]) and m["kpi"] == 2 and not m["overflow"], str(m)))
    ctx.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-dashboard-")
    make = os.path.join(ROOT, "tests", "fixtures", "make_vault.py")
    subprocess.run([sys.executable, make, "--out", os.path.join(work, "full")], check=True, capture_output=True)
    subprocess.run([sys.executable, make, "--out", os.path.join(work, "empty"), "--profile", "empty"], check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, os.path.join(work, "full"), os.path.join(work, "full.log"))
    proc2, port2 = visual.start_server(ROOT, os.path.join(work, "empty"), os.path.join(work, "empty.log"))
    base, base_empty = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{port2}"
    results = []
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            guarded(results, "数据所有权", lambda: run_ownership(page, base, results))
            guarded(results, "数字与版式", lambda: run_numbers(page, base, results))
            guarded(results, "跳转", lambda: run_navigation(page, base, port, results))
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            guarded(results, "空库与错态", lambda: run_empty_and_error(browser, base_empty, results))
            guarded(results, "手机", lambda: run_mobile(browser, base, results))
            for theme in ("light", "dark"):
                for label, size, target in (("桌面", (1440, 900), 28), ("手机", (390, 844), 40)):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    pg = c.new_page()
                    home(pg, base)
                    wait(pg, "() => document.querySelectorAll('.dsh-recent__row').length > 0")
                    a = pg.evaluate(AUDIT, target)
                    ok = len(a["sizes"]) <= 6 and not a["small"] and not a["inline"] and not a["handlers"] and not a["overflow"]
                    results.append((f"审计 {label} · {'浅色' if theme == 'light' else '深色'}：字号 ≤6、可点目标 ≥{target}、无行内样式与 onclick、无横向溢出", ok, str(a)))
                    c.close()
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
    finally:
        for pr in (proc, proc2):
            pr.terminate()
            pr.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E dashboard：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
