"""P3 主路径 E2E：即时练习（assets/app/features/instant）。

    python3 tests/e2e/instant.py        # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault（tests/fixtures/make_vault.py）与隔离实例，不碰真实数据。覆盖：加载 → 翻答案 → 判定 → 打分 → 提交；
判定不重建题面（挂载点与 KaTeX 节点都是原来那个）、焦点与滚动不丢；纯键盘；旧入口（仪表盘「专练」、INSTANT_QUEUE、标记变更）；
空、错、离开再回来；桌面 / 手机 × 浅 / 深的审计：页面自身（不含题面 qview 子树）字号 ≤6 种、小于 28px 的可点目标为 0。
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

AUDIT = """() => {
  const root = document.getElementById('panel-instant');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('[data-qv-host]'));
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))];
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button'
    || (e.tagName === 'A' && e.hasAttribute('href')) || e.hasAttribute('onclick') || e.hasAttribute('data-action');
  const small = [...root.querySelectorAll('*')].filter(e => e.offsetParent && hit(e))
    .filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < 28; }).map(e => e.className);
  return { sizes: sizes.length, small, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""
READY = "() => document.querySelector('#panel-instant .inst') && window.__omrs && window.__omrs.store.get().data"
CARD = "() => document.querySelector('#panel-instant [data-qv-host] [data-qv-uid]')"


def launch_browser(p):
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()


def wait(page, expression, timeout=6000):
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:  # playwright TimeoutError
        return False


def load(page):
    page.click('#panel-instant .inst-bar [data-action="instant.load"]')
    return wait(page, CARD)


def audit_states(page, tag, results):
    bad = []
    page.goto(page.url.split("#")[0] + "#/instant", wait_until="networkidle")
    wait(page, READY)
    states = {"空": page.evaluate(AUDIT)}
    load(page)
    states["已加载"] = page.evaluate(AUDIT)
    page.keyboard.press("Space")
    wait(page, "() => document.querySelector('.inst-grade')")
    states["已翻答案"] = page.evaluate(AUDIT)
    page.keyboard.press("1")
    states["已判定"] = page.evaluate(AUDIT)
    for name, a in states.items():
        if a["sizes"] > 6 or a["small"] or a["overflow"]:
            bad.append(f"{name}:{a}")
    results.append((f"{tag}：四种状态字号 ≤6、小目标 0、无横向溢出", not bad, "; ".join(bad[:2])))


def run_desktop(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    page.goto(f"{base}/#/instant", wait_until="networkidle")
    wait(page, READY)
    check("首次进入是空状态，全页只有一个「加载推荐」",
          ev("!!document.querySelector('#panel-instant .ui-empty')") and page.get_by_role("button", name="加载推荐", exact=True).count() == 1)
    page.fill("#instant-count", "40")
    page.dispatch_event("#instant-count", "change")
    ok = load(page)
    n = ev("document.querySelectorAll('.inst-q').length")
    check("加载推荐：队列与题卡出现；旧 INSTANT_QUEUE 只读兼容", ok and n > 5 and ev("INSTANT_QUEUE.length") == n, f"queue={n}")
    ev("""async () => { for (const [i, b] of [...document.querySelectorAll('.inst-q')].entries()) { b.click();
      await new Promise(r => setTimeout(r, 60)); if (document.querySelector('[data-qv-host] .katex')) return i; } return -1; }""")
    page.keyboard.press("Space")
    check("空格翻答案：出现判定区与答案", wait(page, "() => document.querySelector('.inst-grade') && document.querySelector('[data-qv-host] .q-answer-md')"))
    probe = ev("""async () => {
      const main = document.querySelector('.inst-main'); main.scrollTop = main.scrollHeight;
      const host = document.querySelector('[data-qv-host]'); const kx = [...host.querySelectorAll('.katex')];
      const top = main.scrollTop; const btn = document.querySelector('.inst-verdict__btn--no'); btn.focus(); btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      return { host: host === document.querySelector('[data-qv-host]'), katex: kx.length, kept: kx.filter(k => k.isConnected).length,
               focus: document.activeElement === btn, scroll: Math.abs(main.scrollTop - top) <= 1, pressed: btn.getAttribute('aria-pressed') };
    }""")
    check("判定不重建题面：挂载点与 KaTeX 节点复用，焦点与滚动保留",
          probe["host"] and probe["katex"] > 0 and probe["kept"] == probe["katex"] and probe["focus"] and probe["scroll"] and probe["pressed"] == "true", probe)
    page.focus(".inst-score__input")
    page.keyboard.press("ArrowRight")
    check("拖分数滑杆：分值更新，滑杆仍有焦点", ev("[document.querySelector('.inst-score__value').textContent, document.activeElement.className]")
          == ["5", "inst-score__input"])
    page.click(".inst-card__title")
    page.keyboard.press("8")
    before = ev("document.querySelector('.inst-q[aria-current]').dataset.arg")
    page.keyboard.press("j")
    after_j = ev("document.querySelector('.inst-q[aria-current]').dataset.arg")
    page.keyboard.press("k")
    page.keyboard.press("Enter")
    after_enter = ev("document.querySelector('.inst-q[aria-current]').dataset.arg")
    page.keyboard.press("2")
    verdict2 = ev("document.querySelector('.inst-verdict__btn--no').getAttribute('aria-pressed')")
    check("键盘：数字打分、J / K 切题、Enter 下一道未判定、2 判错",
          ev("document.querySelector('.inst-q.is-no[data-arg=\"%s\"]') !== null" % before) and int(after_j) == int(before) + 1
          and after_enter != before and verdict2 == "true", f"{before}->{after_j}->{after_enter}")
    page.keyboard.press("e")
    opened = wait(page, "() => document.getElementById('md-editor')?.open === true")
    ev("closeMarkdownEditor()")
    wait(page, "() => !document.getElementById('md-editor')")
    check("E 打开当前题的 Markdown 编辑器", opened)
    with page.expect_response(lambda r: r.url.endswith("/api/feedback") and r.request.method == "POST") as fb:
        page.keyboard.press("Control+Enter")
    wait(page, "() => document.querySelectorAll('.inst-res__row').length === 2")
    state = ev("""[document.querySelectorAll('.inst-res__row.is-ok').length, document.querySelectorAll('.inst-q.is-submitted').length,
      document.querySelector('.inst-sum [data-action=\"instant.submit\"]').disabled]""")
    check("⌘/Ctrl+Enter 提交：写入 2 条、结果列表出现、已提交的题锁定", fb.value.status == 200 and state == [2, 2, True], state)
    page.click(f'.inst-q[data-arg="{before}"]')
    locked = ev("[document.querySelector('.inst-verdict__btn--ok').disabled, !!document.querySelector('.inst-grade__note')]")
    check("已提交的题不能改判", locked == [True, True], locked)
    page.click('.inst-q.is-open')
    page.keyboard.press("Space")
    page.keyboard.press("1")
    page.click('#panel-instant .inst-bar [data-action="instant.load"]')
    asked = wait(page, "() => document.querySelector('dialog[open]')")
    page.keyboard.press("Escape")
    check("有未提交判定时重新取题先确认，取消则队列不动",
          asked and wait(page, "() => !document.querySelector('dialog[open]')") and ev("document.querySelectorAll('.inst-q.is-ok').length") == 1)
    page.click('a.tab[data-tab="dashboard"]')
    page.click('a.tab[data-tab="instant"]')
    check("离开再回来：队列与判定都还在", ev("document.querySelectorAll('.inst-q').length") == n and ev("document.querySelectorAll('.inst-q.is-submitted').length") == 2)
    return n


def run_legacy_entries(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    page.goto(f"{base}/?fresh=1#/dashboard", wait_until="networkidle")   # 整页重载：从干净的页面状态开始
    wait(page, READY)
    btn = page.locator('#panel-dashboard button', has_text="专练").first
    subject = (btn.text_content() or "").replace("专练", "").strip()
    btn.click()
    wait(page, CARD)
    got = ev("[location.hash, document.getElementById('instant-subject').value, INSTANT_QUEUE.every(i => i.subject === document.getElementById('instant-subject').value)]")
    check("仪表盘「专练 某科目」：切到 #/instant、带预设取题、队列全是该科目", got == ["#/instant", subject, True], got)
    ev("(window.__omrs.router.go('instant'), instLoadPractice({'inst-subject': '不存在的科目'}))")
    empty = wait(page, "() => document.querySelector('#panel-instant .ui-empty') && document.body.textContent.includes('当前筛选下没有可练的题')")
    with page.expect_response(lambda response: '/api/recommend?' in response.url):
        page.click('#panel-instant [data-action="instant.clear"]')
    check("筛选无结果显示空状态，「清空筛选并重新取题」可恢复", empty and wait(page, CARD))
    name = ev("document.querySelector('.inst-lblf')?.dataset.arg")
    page.click(f'.inst-lblf[data-arg="{name}"]')
    with page.expect_response(lambda response: '/api/recommend?' in response.url):
        page.click('#panel-instant .inst-bar [data-action="instant.load"]')
    wait(page, CARD)
    check("标记筛选：按钮按下、取到的题都带该标记",
          ev(f"document.querySelector('.inst-lblf[data-arg=\"{name}\"]').getAttribute('aria-pressed')") == "true"
          and ev(f"INSTANT_QUEUE.length > 0 && INSTANT_QUEUE.every(i => (i.labels || []).includes({name!r}))"), name)
    ev("LABELS.push({ id: 'e2e', name: 'E2E新标记', color: '#2f6fde' }); renderLabelFilterOptions(); 0")
    check("旧代码改了标记定义：经 bus 的 labels 事件重绘筛选芯片", wait(page, "() => !!document.querySelector('.inst-lblf[data-arg=\"E2E新标记\"]')"))
    page.route("**/api/recommend*", lambda route: route.fulfill(status=500, content_type="application/json", body='{"status":"error","msg":"模拟故障"}'))
    with page.expect_response(lambda response: '/api/recommend?' in response.url):
        page.click('#panel-instant .inst-bar [data-action="instant.load"]')
    load_err = 0
    err = wait(page, "() => document.querySelector('#panel-instant .inst-state[data-key=\"error\"]') && document.querySelector('#panel-instant .inst-state')?.textContent.includes('模拟故障')")
    page.unroute("**/api/recommend*")
    if err:
        page.click('#panel-instant .inst-state [data-action="instant.load"]')
    check("接口出错显示错误状态与原因，「重试」恢复", load_err == 0 and err and wait(page, CARD))


def run_mobile(browser, base, results):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/#/instant", wait_until="networkidle")
    wait(page, READY)
    load(page)
    page.keyboard.press("Space")
    wait(page, "() => document.querySelector('.inst-grade')")
    m = page.evaluate("""() => { const q = document.querySelector('.inst-queue__list'), card = document.querySelector('.inst-card');
      return { row: getComputedStyle(q).flexDirection, strip: q.getBoundingClientRect().bottom <= card.getBoundingClientRect().top,
               verdict: [...document.querySelectorAll('.inst-verdict__btn')].map(b => Math.round(b.getBoundingClientRect().height)),
               overflow: document.documentElement.scrollWidth > innerWidth + 1 }; }""")
    results.append(("手机：单栏，队列是题卡上方的横条，判定按钮 40px，无横向溢出",
                     m["row"] == "row" and m["strip"] and m["verdict"] == [40, 40] and not m["overflow"], str(m)))
    results.append(("手机：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
    ctx.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-instant-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
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
            run_desktop(page, base, results)
            run_legacy_entries(page, base, results)
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            run_mobile(browser, base, results)
            for theme in ("light", "dark"):
                for label, size in (("桌面", (1440, 900)), ("手机", (390, 844))):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    pg = c.new_page()
                    pg.goto(f"{base}/", wait_until="networkidle")
                    audit_states(pg, f"审计 {label} · {'浅色' if theme == 'light' else '深色'}", results)
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
    print(f"E2E instant：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
