"""P6 主路径 E2E：数据复盘（assets/app/features/data）。

    python3 tests/e2e/data.py        # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault（full 档）与隔离实例，不碰真实数据。覆盖：首屏（十二格概览与 /api/analytics 一致、图表卡齐全、标题无 emoji、
旧 loadAnalytics / renderDataCharts 全局已不存在）；「刷新」与统计快照变化时重拉；导出复盘报告（下载 .md、失败原因显示在页首）；
屡练不熟「查看」开题目弹窗、「加入展示板」开选板浮层；首次加载失败与「重试」；手机（概览两列、表格降级为卡片、无横向溢出）；
桌面 / 手机 × 浅 / 深审计（字号 ≤6 种且不小于 12px、可点目标桌面 ≥28 / 手机 ≥40、除 KaTeX 外无行内样式、无横向溢出）。
"""
import importlib.util
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)
from browser_runtime import open_app

AUDIT = """(minTarget) => {
  const root = document.getElementById('panel-data');
  const shown = [...root.querySelectorAll('*')].filter(e => (e.offsetParent || e instanceof SVGElement) && !e.closest('.katex'));
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a, b) => a - b);
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button'
    || (e.tagName === 'A' && e.hasAttribute('href')) || e.hasAttribute('onclick') || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < minTarget; })
    .map(e => `${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  return { sizes, small, inline: [...root.querySelectorAll('[style]')].filter(e => !e.closest('.katex')).length,
           handlers: root.querySelectorAll('[onclick]').length, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""
READY = "() => document.querySelector('#panel-data [data-dat-ready]')"
CARDS = ["question-status", "cycles", "trend", "labels", "subjects", "categories", "scatter", "mastery", "decayed", "ef", "difficulty", "repetition", "interval",
         "score", "weekly", "weekday", "hour", "forecast", "label-acc", "alerts", "leeches", "struggling"]


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


def open_data(page, base, extra=""):
    open_app(page, base, "data")
    return wait(page, READY)


def seed_progress(vault):
    """只在临时题库写真实反馈，构造跨页击杀、休眠、复燃及降级成绩。"""
    from omrs.common import business_today
    from omrs.creation import create_question
    from omrs.feedback import process_feedback
    today = business_today()
    uids = [create_question(vault, "数学" if i % 2 else "物理", "复盘专项", 5,
                            question_text=f"复盘专项第 {i + 1} 题", answer_text="合成答案")["uid"] for i in range(14)]
    with patch("omrs.feedback.business_today", return_value=today - datetime.timedelta(days=8)):
        process_feedback(vault, [{"uid": uid, "sub_score": 9, "is_correct": True} for uid in uids])
    process_feedback(vault, [{"uid": uid, "sub_score": 9, "is_correct": True} for uid in uids[:12]])
    process_feedback(vault, [{"uid": uids[-1], "sub_score": 2, "is_correct": False}])


def run_main(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    check("首屏就绪（data-dat-ready）", open_data(page, base))
    analytics = http(port, "/api/analytics")
    ov = analytics["overview"]
    vals = ev("[...document.querySelectorAll('.dat-kpi__value')].map(e => e.textContent)")
    check("十二格概览与接口一致，含题数、击杀和覆盖率", len(vals) == 12 and vals[:3] == [str(ov[key]) for key in ("total", "killed", "attacking")]
          and vals[3] == f"{round((ov['total'] - ov['never_reviewed']) / ov['total'] * 100)}%" and vals[4] == str(ov["total_reviews"]), vals)
    keys = ev("[...document.querySelectorAll('#panel-data .dat-card')].map(e => e.dataset.key)")
    check("22 张图表卡齐全，新增明细和复核成绩", keys == CARDS, keys)
    expected = [sum(i["is_killed"] and not i["is_revived"] for i in analytics["items"]),
                sum(i["is_revived"] for i in analytics["items"]), sum(i["kill_count"] for i in analytics["items"]),
                sum(i["kill_count"] > 0 for i in analytics["items"])]
    check("休眠、复燃、累计成绩与曾击杀题数分别统计", ev("[...document.querySelectorAll('[data-key=cycles] .dat-mini dd')].map(e => Number(e.textContent))") == expected, expected)
    listing = page.locator('[data-key="question-status"]')
    check("已击杀默认选中且复燃题优先", listing.locator('[data-action="data.filter"][data-arg="killed"]').get_attribute('aria-pressed') == 'true'
          and '复燃待复核' in listing.locator('tbody tr').first.inner_text())
    first_page = listing.locator('tbody tr').first.get_attribute('data-key')
    listing.get_by_role('button', name='下一页', exact=True).click()
    check("已击杀明细可翻页，超出前十题仍能查看", first_page != listing.locator('tbody tr').first.get_attribute('data-key') and '第 2 /' in listing.inner_text())
    listing.locator('[data-action="data.filter"][data-arg="revived"]').click()
    check("切换复燃筛选回到第一页，只显示待复核题", '第 1 /' in listing.inner_text()
          and all('复燃待复核' in text for text in listing.locator('tbody tr').all_inner_texts()))
    listing.locator('[data-action="data.filter"][data-arg="killed"]').click()
    page.select_option('#dat-subject', '数学')
    page.fill('#dat-search', '复盘专项')
    check("科目与搜索共同筛选，输入焦点保留", listing.locator('tbody tr').count() == 6
          and ev("document.activeElement.id === 'dat-search'") and '第 1 /' in listing.inner_text())
    uid = listing.locator('[data-action="data.detail"]').first.get_attribute('data-arg')
    listing.locator('[data-action="data.detail"]').first.click()
    check("击杀明细查看真实题目详情", wait(page, "u => document.querySelector('dialog[open] [data-qv-uid]')?.dataset.qvUid === u", arg=uid)
          and wait(page, "() => document.querySelector('dialog[open]')?.textContent.includes('复盘专项')"))
    page.get_by_role('button', name='下一题', exact=True).click()
    check("详情可在完整筛选结果内切换下一题", wait(page, "u => document.querySelector('dialog[open] [data-qv-uid]')?.dataset.qvUid !== u", arg=uid)
          and '第 2 / 6 题' in page.locator('#qv-nav-pos').inner_text())
    ev("closeModal()")
    wait(page, "() => !document.querySelector('dialog[open]')")
    page.fill('#dat-search', '无匹配结果')
    check("无匹配时显示明确空状态", wait(page, "() => document.querySelector('[data-key=\"question-status\"]')?.textContent.includes('没有符合条件的题目')"), listing.inner_text())
    page.fill('#dat-search', '')
    page.select_option('#dat-subject', '')
    check("卡片标题不带 emoji（D7）", ev("[...document.querySelectorAll('.dat-card__title')].every(e => !/\\p{Extended_Pictographic}/u.test(e.textContent))"))
    check("旧全局 loadAnalytics / renderDataCharts 已删除", ev("typeof loadAnalytics === 'undefined' && typeof renderDataCharts === 'undefined' && typeof exportReview === 'undefined'"))
    want = ev("(() => { const c = {}; DATA.items.filter(i => !i.suspended).forEach(i => (i.labels || []).forEach(l => { c[l] = (c[l] || 0) + 1; })); return Object.values(c).sort((a, b) => b - a); })()")
    got = ev("[...document.querySelectorAll('[data-key=\"labels\"] .dat-bar__val')].map(e => Number(e.textContent))")
    check("标记分布与统计快照一致（未停用题）", got == want, [got, want])
    check("三张 SVG 图都画出来（趋势、雷达、气泡）", ev("['trend','subjects','scatter'].every(k => document.querySelector(`[data-key=\"${k}\"] svg.dat-svg`))"))
    seen = []
    page.on("request", lambda r: seen.append(r.url) if "/api/analytics" in r.url else None)
    page.click('[data-action="data.refresh"]')
    wait(page, "() => !document.querySelector('[data-action=\"data.refresh\"][aria-busy]')")
    check("「刷新」重拉 /api/analytics 一次", len(seen) == 1, seen)
    ev("reloadData()")
    check("统计快照变化后（reloadData）自动重拉", wait(page, "n => true", arg=0) and page.wait_for_timeout(800) is None and len(seen) >= 2, seen)
    page.route("**/api/analytics", lambda route: route.fulfill(status=500, content_type="application/json", body='{"msg":"暂时无法统计"}'))
    page.click('[data-action="data.refresh"]')
    check("刷新失败保留原有击杀数据与筛选结果", wait(page, "() => document.getElementById('data-status').textContent.includes('刷新失败')")
          and listing.locator('[data-action="data.detail"]').count() > 0)
    page.unroute("**/api/analytics")
    page.click('[data-action="data.refresh"]')
    wait(page, "() => !document.querySelector('[data-action=\"data.refresh\"][aria-busy]')")
    with page.expect_download() as info:
        page.click('[data-action="data.export"]')
    name = info.value.suggested_filename
    check("导出复盘报告：下载 Markdown 文件并提示", name.endswith(".md") and wait(page, "() => document.body.textContent.includes('已导出')"), name)
    page.route("**/api/export-review", lambda route: route.fulfill(status=500, content_type="application/json", body='{"msg":"磁盘已满"}'))
    page.click('[data-action="data.export"]')
    check("导出失败：原因显示在页首", wait(page, "() => document.getElementById('data-status').textContent.includes('导出失败：磁盘已满')"))
    page.unroute("**/api/export-review")
    uid = ev("document.querySelector('[data-key=\"struggling\"] [data-action=\"data.view\"]')?.dataset.arg")
    page.click('[data-key="struggling"] [data-action="data.view"]')
    ok = wait(page, "u => document.querySelector('dialog[open] [data-qv-uid]')?.dataset.qvUid === u", arg=uid)
    ev("closeModal()")
    check("屡练不熟「查看」打开题目弹窗", ok, uid)
    wait(page, "() => !document.querySelector('dialog[open]:not(.is-closing)')")
    page.click('[data-key="struggling"] [data-action="data.board"]')
    check("「加入展示板」打开选板浮层", wait(page, "() => [...document.querySelectorAll('[class*=\"picker\"]')].some(e => e.offsetParent)"))
    page.keyboard.press("Escape")


def run_error(browser, base, results):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/api/analytics", lambda route: route.fulfill(status=500, content_type="application/json", body='{"msg":"统计出错"}'))
    open_data(page, base)
    shown = wait(page, "() => document.querySelector('#panel-data .dat-state')?.textContent.includes('统计出错')")
    page.unroute("**/api/analytics")
    page.click('#panel-data .dat-state [data-action="data.refresh"]')
    results.append(("首次加载失败：显示原因与「重试」，恢复后点它回到正常", shown and wait(page, READY), ""))
    results.append(("错态：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
    ctx.close()


def run_mobile(browser, base, results):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    open_data(page, base)
    m = page.evaluate("""() => ({ kpi: getComputedStyle(document.querySelector('.dat-kpis')).gridTemplateColumns.split(' ').length,
      stack: getComputedStyle(document.querySelector('[data-key="categories"] tbody tr')).display,
      overflow: document.documentElement.scrollWidth > innerWidth + 1 })""")
    results.append(("手机：概览两列、表格降级为卡片、无横向溢出", m["kpi"] == 2 and m["stack"] != "table-row" and not m["overflow"], str(m)))
    ctx.close()


def run_empty(browser, work, results):
    vault = os.path.join(work, "empty")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests/fixtures/make_vault.py"), "--out", vault, "--profile", "empty"], check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "empty.log"))
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = ctx.new_page()
        open_data(page, f"http://127.0.0.1:{port}")
        values = page.locator('.dat-kpi__value').all_inner_texts()
        results.append(("空库：题数零，击杀率与覆盖率未知，明细明确空状态", values[:4] == ['0', '0', '0', '—']
                        and '击杀率 —' in page.locator('.dat-kpis').inner_text()
                        and '没有符合条件的题目' in page.locator('[data-key="question-status"]').inner_text(), str(values)))
        results.append(("空库：翻页禁用且无横向溢出", page.get_by_role('button', name='下一页', exact=True).is_disabled()
                        and not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'), ''))
    finally:
        ctx.close()
        proc.terminate()
        proc.wait(timeout=10)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-data-")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", os.path.join(work, "full")], check=True, capture_output=True)
    seed_progress(os.path.join(work, "full"))
    proc, port = visual.start_server(ROOT, os.path.join(work, "full"), os.path.join(work, "full.log"))
    base = f"http://127.0.0.1:{port}"
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
            guarded(results, "主路径", lambda: run_main(page, base, port, results))
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            guarded(results, "错态", lambda: run_error(browser, base, results))
            guarded(results, "手机", lambda: run_mobile(browser, base, results))
            guarded(results, "空库", lambda: run_empty(browser, work, results))
            for theme in ("light", "dark"):
                for label, size, target in (("桌面", (1440, 900), 28), ("手机", (390, 844), 40)):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    pg = c.new_page()
                    open_data(pg, base)
                    a = pg.evaluate(AUDIT, target)
                    shots = os.environ.get("OMRS_DATA_SHOTS")
                    if shots:
                        os.makedirs(shots, exist_ok=True)
                        pg.screenshot(path=os.path.join(shots, f"data-{theme}-{size[0]}.png"), full_page=True)
                    ok = len(a["sizes"]) <= 6 and min(a["sizes"]) >= 12 and not a["small"] and not a["inline"] and not a["handlers"] and not a["overflow"]
                    results.append((f"审计 {label} · {'浅色' if theme == 'light' else '深色'}：字号 ≤6 且 ≥12px、可点目标 ≥{target}、无行内样式与 onclick、无横向溢出", ok, str(a)))
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
    print(f"E2E data：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
