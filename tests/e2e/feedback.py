"""P4 主路径 E2E：反馈录入工作台（assets/app/features/feedback）。

    python3 tests/e2e/feedback.py        # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault（tests/fixtures/make_vault.py）与隔离实例，不碰真实数据；用 /api/confirm-schedule 建两个 Session。覆盖：
选 Session → 粘贴 OMR /result 自动填写 → 判定不重建题面（挂载点与 KaTeX 节点复用、焦点与滚动保留）→ 滑杆 / 备注 → 纯键盘
→ ⌘/Ctrl+Enter 提交、结果弹窗（ui/dialog）与重开 → 已录入只读；手动行、导入框、提交失败；旧入口（复习调度「录入结果」、
标记重绘、删除计划清表单）；离开再回来；手机单栏（题面单栏、题目列表横条）；桌面 / 手机 × 浅 / 深审计。
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

AUDIT = """() => {
  const root = document.getElementById('panel-feedback');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('[data-qv-host]'));
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))];
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button'
    || (e.tagName === 'A' && e.hasAttribute('href')) || e.hasAttribute('onclick') || e.hasAttribute('data-action');
  const small = [...root.querySelectorAll('*')].filter(e => e.offsetParent && hit(e) && !e.closest('[data-qv-host]'))
    .filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < 28; }).map(e => e.className);
  return { sizes: sizes.length, list: sizes, small, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""
READY = "() => document.querySelector('#panel-feedback .fbw') && window.__omrs && typeof SESSIONS !== 'undefined' && SESSIONS.length > 0"
QV = "() => document.querySelector('#panel-feedback [data-qv-host] [data-qv-uid]')"
CUR = "document.querySelector('.fbw-q[aria-current]')?.dataset.arg"


def launch_browser(p):
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()


def wait(page, expression, timeout=6000):
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:  # playwright TimeoutError
        return False


def http(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))


def make_session(port, uids):
    before = {s["session_id"] for s in http(port, "/api/sessions")["sessions"]}
    http(port, "/api/confirm-schedule", {"selected": [{"uid": u, "source": "due"} for u in uids], "persist": True})
    after = [s for s in http(port, "/api/sessions")["sessions"] if s["session_id"] not in before]
    return after[0]["session_id"]


def omr_json(questions, unresolved=(), status="ready"):
    return json.dumps({"recognition_id": 7, "template_id": "omrs-2col-normal-30q-tm-v2", "mode": "omrs", "status": status,
                       "questions": questions, "unresolved": list(unresolved)})


def paste(page, text):
    page.evaluate("""text => { const dt = new DataTransfer(); dt.setData('text/plain', text);
      document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""", text)


def pick(page, sid):
    page.select_option("#fb-session-picker", sid)
    return wait(page, f"() => ACTIVE_FB_SESSION === {sid!r} && document.querySelectorAll('.fbw-q').length > 0")


def run_desktop(page, base, port, sid, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    page.goto(f"{base}/#/feedback", wait_until="networkidle")
    wait(page, READY)
    check("首次进入：未选 Session 时 rail / 判定区是空状态，提交按钮禁用，全页只有一个「提交反馈」",
          ev("!!document.querySelector('.fbw-rail .ui-empty') && !!document.querySelector('.fbw-panel .ui-empty')")
          and page.get_by_role("button", name="提交反馈", exact=True).count() == 1
          and ev("document.querySelector('[data-action=\"feedback.submit\"]').disabled"))
    paste(page, omr_json([{"seq": 1, "page": 1, "result": "C", "level": "9"}]))
    check("未选 Session 时粘贴答题卡被拒，导入面板自动展开并说明原因",
          wait(page, "() => document.querySelector('.fbw-import__status')?.textContent.includes('请先在上面选中')")
          and ev("document.querySelector('.fbw-import__toggle').getAttribute('aria-expanded')") == "true")
    ok = pick(page, sid)
    check("选中 Session：rail 列出 6 题、题面挂上、进度行 0/6、UID 输入框隐藏",
          ok and wait(page, QV) and ev("document.querySelectorAll('.fbw-q').length") == 6
          and "0/6" in ev("document.querySelector('.fbw-bar__info').textContent") and not ev("!!document.querySelector('.fbw-field input[list]')"))
    paste(page, omr_json([{"seq": 1, "page": 1, "result": "C", "level": "9"}, {"seq": 2, "page": 1, "result": "W", "level": "3"},
                          {"seq": 3, "page": 1, "result": "C", "level": "8"}],
                         unresolved=[{"seq": 3, "field": "q3_result", "status": "multi_marked"}], status="needs_review"))
    got = ev("""[document.querySelector('.fbw-import__status')?.textContent || '',
      [...document.querySelectorAll('.fbw-q')].slice(0, 3).map(b => b.className.match(/is-(ok|no|up|done)/)[1])]""")
    check("粘贴 OMR /result：按题号填对错，unresolved 留给人工，报告写明待复核",
          "自动填写 2 题" in got[0] and "待复核" in got[0] and got[1] == ["ok", "no", "up"], got)
    check("导入后光标落在第一道未判定题", ev(CUR) == "2")
    # 找一道未判定、有 KaTeX 的题（fixture 里有 LaTeX 题）；判定不应重建题面
    at = ev("""async () => { const qs = [...document.querySelectorAll('.fbw-q')];
      for (const [i, b] of qs.entries()) { if (!b.classList.contains('is-up')) continue; b.click();
        for (let t = 0; t < 20; t++) { await new Promise(r => setTimeout(r, 50)); if (document.querySelector('[data-qv-host] [data-qv-uid]')) break; }
        if (document.querySelector('[data-qv-host] .katex')) return i; } return -1; }""")
    probe = ev("""async () => {
      const stage = document.querySelector('.fbw-stage'); stage.scrollTop = stage.scrollHeight;
      const host = document.querySelector('[data-qv-host]'); const kx = [...host.querySelectorAll('.katex')];
      const top = stage.scrollTop; const btn = document.querySelector('.fbw-verdict__btn--no'); btn.focus(); btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const now = document.querySelector('.fbw-verdict__btn--no');
      return { host: host === document.querySelector('[data-qv-host]'), katex: kx.length, kept: kx.filter(k => k.isConnected).length,
               focus: document.activeElement === now, scroll: Math.abs(stage.scrollTop - top) <= 1, pressed: now.getAttribute('aria-pressed'),
               score: document.querySelector('.fbw-score__value').textContent };
    }""")
    check("判定不重建题面：挂载点与 KaTeX 节点复用，焦点与滚动保留，判错默认 4 分",
          at >= 0 and probe["host"] and probe["katex"] > 0 and probe["kept"] == probe["katex"] and probe["focus"]
          and probe["scroll"] and probe["pressed"] == "true" and probe["score"] == "4", {"at": at, **probe})
    page.focus(".fbw-score__input")
    page.keyboard.press("ArrowRight")
    check("拖分数滑杆：分值更新，滑杆仍有焦点",
          ev("[document.querySelector('.fbw-score__value').textContent, document.activeElement.className]") == ["5", "fbw-score__input"])
    page.fill('.fbw-field input[data-input="feedback.note"]', "p.12 符号错")
    here = ev(CUR)
    page.click(".fbw-panel__title")
    page.keyboard.press("j")
    after_j = ev(CUR)
    page.keyboard.press("k")
    kept = ev("document.querySelector('.fbw-field input[data-input=\"feedback.note\"]').value")
    check("备注写入行数据：J / K 切走再回来仍在，题面随切题换挂载点", int(after_j) == int(here) + 1 and ev(CUR) == here and kept == "p.12 符号错",
          f"{here}->{after_j} note={kept!r}")
    page.click('.fbw-q[data-arg="2"]')
    wait(page, QV)
    page.click(".fbw-panel__title")
    page.keyboard.press("1")
    page.keyboard.press("7")
    k1 = ev("[document.querySelector('.fbw-q[data-arg=\"2\"]').className, document.querySelector('.fbw-score__value').textContent]")
    page.keyboard.press("Enter")
    after_enter = ev(CUR)
    page.keyboard.press("2")
    check("键盘：1 判对、数字打分、Enter 跳到下一道未判定、2 判错",
          "is-ok" in k1[0] and k1[1] == "7" and after_enter not in ("0", "1", "2")
          and "is-no" in ev(f"document.querySelector('.fbw-q[data-arg=\"{after_enter}\"]').className"), f"{k1} enter->{after_enter}")
    page.keyboard.press("e")
    opened = wait(page, "() => document.getElementById('md-editor')?.open === true")
    ev("closeMarkdownEditor()")
    wait(page, "() => !document.getElementById('md-editor')")
    check("E 打开当前题的 Markdown 编辑器", opened)
    ready = ev("document.querySelectorAll('.fbw-q.is-ok, .fbw-q.is-no').length")
    with page.expect_response(lambda r: r.url.endswith("/api/feedback") and r.request.method == "POST") as fb:
        page.keyboard.press("Control+Enter")
    dlg = wait(page, "() => document.querySelector('dialog[open]')?.textContent.includes('本次处理结果')")
    rows = ev("document.querySelectorAll('dialog[open] .fbw-result__row.is-ok').length")
    check("⌘/Ctrl+Enter 提交：结果进 ui/dialog 弹窗，逐题写入成功", fb.value.status == 200 and dlg and rows == ready, f"ready={ready} rows={rows}")
    page.locator("dialog[open] [data-dialog-ok]").click()
    status = wait(page, "() => document.querySelector('.fbw-panel__submit')?.textContent.includes('本次已提交')")
    server = len(next(s for s in http(port, "/api/sessions")["sessions"] if s["session_id"] == sid).get("feedback_uids") or [])
    done = ev("document.querySelectorAll('.fbw-q.is-done').length")
    check("提交后：状态行报剩余题数、rail 标出已录入、后端进度一致、未判定题保留",
          status and done == ready == server and ev("document.querySelectorAll('.fbw-q.is-up').length") == 6 - ready,
          f"done={done} server={server}")
    page.click(".fbw-q.is-done")
    check("已录入的题只读，不再给判定按钮", wait(page, "() => document.querySelector('.fbw-readonly') && !document.querySelector('.fbw-verdict')"))
    page.click('[data-action="feedback.reopenResults"]')
    again = wait(page, "() => document.querySelector('dialog[open] .fbw-result__row')")
    page.keyboard.press("Escape")
    check("状态行「查看本次结果」重开弹窗，Esc 关闭", again and wait(page, "() => !document.querySelector('dialog[open]')"))
    page.click('a.tab[data-tab="dashboard"]')
    page.click('a.tab[data-tab="feedback"]')
    check("离开再回来：Session 选择与已录入进度都还在",
          wait(page, f"() => document.getElementById('fb-session-picker').value === {sid!r}") and ev("document.querySelectorAll('.fbw-q.is-done').length") == ready)
    return ready


def run_manual(page, base, uid, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    page.goto(f"{base}/?fresh=1#/feedback", wait_until="networkidle")
    wait(page, READY)
    page.click('[data-action="feedback.addRow"]')
    page.fill(".fbw-field input[list]", uid)
    page.dispatch_event(".fbw-field input[list]", "change")
    check("手动录入：添加行 → 填 UID 后题面挂上", wait(page, QV) and ev("document.querySelector('[data-qv-host]').dataset.uid") == uid)
    page.click(".fbw-verdict__btn--ok")
    page.route("**/api/feedback", lambda route: route.fulfill(status=500, content_type="application/json", body='{"status":"error","msg":"模拟故障"}'))
    page.click('[data-action="feedback.submit"]')
    err = wait(page, "() => document.querySelector('.fbw-panel__submit .ui-status--danger')?.textContent.includes('提交失败')")
    page.unroute("**/api/feedback")
    check("提交失败：状态行给出原因，判定保留、按钮可再点", err and ev("document.querySelectorAll('.fbw-q.is-ok').length") == 1
          and not ev("document.querySelector('[data-action=\"feedback.submit\"]').disabled"))
    page.click(".fbw-import__toggle")
    page.fill("#fb-json", json.dumps({"type": "omrs-feedback", "items": [{"uid": uid, "is_correct": "错", "sub_score": 2}, {"uid": "", "is_correct": True}]}))
    page.click('[data-action="feedback.importBox"]')
    imp = wait(page, "() => document.querySelector('.fbw-import__status')?.textContent.includes('已导入 1 条作答，跳过 1 条无效')")
    check("导入框：反馈 JSON 替换当前行，无效条目计数，文本框清空",
          imp and ev("document.querySelectorAll('.fbw-q.is-no').length") == 1 and ev("document.getElementById('fb-json').value") == "")
    page.fill("#fb-json", "{不是 JSON")
    page.click(".fbw-panel__title")   # 失焦后状态重绘不能吞掉文本框里的草稿
    ev("window.__omrs.emit('feedback:render')")
    check("导入框草稿在重绘后保留；坏 JSON 给出可读报错",
          ev("document.getElementById('fb-json').value") == "{不是 JSON"
          and (page.click('[data-action="feedback.importBox"]') or wait(page, "() => document.querySelector('.fbw-import__status')?.textContent.includes('JSON 解析失败')")))


def run_legacy_entries(page, base, sid2, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))
    ev = page.evaluate
    page.goto(f"{base}/?fresh=2#/schedule", wait_until="networkidle")
    wait(page, "() => typeof SESSIONS !== 'undefined' && SESSIONS.length > 0")
    page.click("#sch-tab-plans")
    page.click(f'.schd-plan[data-arg="{sid2}"]')  # 复习调度迁到 features/schedule（P6 第 3 轮）：计划按钮是 .schd-plan
    wait(page, "() => document.querySelector('#sch-plan-detail [data-action=\"schedule.feedback\"]')")
    page.get_by_role("button", name="录入结果", exact=True).click()
    check("复习调度「录入结果」：切到 #/feedback 并选中该计划",
          wait(page, f"() => location.hash === '#/feedback' && document.getElementById('fb-session-picker').value === {sid2!r} && document.querySelectorAll('.fbw-q').length === 3"),
          ev("[location.hash, document.getElementById('fb-session-picker')?.value]"))
    ev("LABELS.unshift({ id: 'e2e', name: 'E2E新标记', color: '#2f6fde' }); renderFb(); 0")
    check("旧代码改了标记定义：经过渡桥 renderFb → bus 重绘快捷标记", wait(page, "() => !!document.querySelector('.fbw-lblq[data-arg=\"E2E新标记\"]')"))
    ev("resetFeedbackForm(); fbClearResults(); 0")
    check("删除计划时的旧入口 resetFeedbackForm / fbClearResults：回到手动录入的空状态",
          wait(page, "() => document.getElementById('fb-session-picker').value === '' && document.querySelector('.fbw-rail .ui-empty') && ACTIVE_FB_SESSION === ''"))
    check("fbSessionProgress 仍是全局（过渡桥再导出，实现在 domain/sessions）", ev("fbSessionProgress({uids:['a','b'],feedback_uids:['a']}).pending_count") == 1)


def run_mobile(browser, base, sid2, results):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/#/feedback", wait_until="networkidle")
    wait(page, READY)
    pick(page, sid2)
    wait(page, QV)
    page.wait_for_timeout(300)
    m = page.evaluate("""() => { const list = document.querySelector('.fbw-rail__list'), stage = document.querySelector('.fbw-stage'),
        rail = document.querySelector('.fbw-rail'), split = document.querySelector('[data-qv-host] .qv-split');
      const panel = document.querySelector('.fbw-panel');
      return { row: getComputedStyle(list).flexDirection, strip: rail.getBoundingClientRect().bottom <= panel.getBoundingClientRect().top,
               panelFirst: panel.getBoundingClientRect().bottom <= stage.getBoundingClientRect().top,
               qvcols: split ? getComputedStyle(split).gridTemplateColumns.split(' ').length : -1,
               verdict: [...document.querySelectorAll('.fbw-verdict__btn')].map(b => Math.round(b.getBoundingClientRect().height)),
               overflow: document.documentElement.scrollWidth > innerWidth + 1 }; }""")
    results.append(("手机：单栏竖排，题目列表横条在最上、判定面板在题面之前，题面单栏（qview 容器查询生效），无横向溢出",
                    m["row"] == "row" and m["strip"] and m["panelFirst"] and m["qvcols"] == 1 and all(h >= 32 for h in m["verdict"]) and not m["overflow"], str(m)))
    ctx.close()
    ctx = browser.new_context(viewport={"width": 1000, "height": 800})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/#/feedback", wait_until="networkidle")
    wait(page, READY)
    pick(page, sid2)
    wait(page, QV)
    got = page.evaluate("""[document.querySelector('[data-qv-host]').getBoundingClientRect().width,
      getComputedStyle(document.querySelector('[data-qv-host] .qv-split')).gridTemplateColumns.split(' ').length,
      getComputedStyle(document.querySelector('.fbw-rail__list')).flexDirection]""")
    results.append(("窄桌面（1000px，≤1160 单栏竖排）：题目列表横条；题面按挂载点宽度决定单 / 双栏（≤680 单栏）",
                    got[2] == "row" and got[1] == (1 if got[0] <= 680 else 2), str(got)))
    results.append(("手机 / 窄桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
    ctx.close()


def audit_states(page, base, sid2, tag, results):
    bad = []
    page.goto(f"{base}/#/feedback", wait_until="networkidle")
    wait(page, READY)
    states = {"空": page.evaluate(AUDIT)}
    pick(page, sid2)
    wait(page, QV)
    page.click(".fbw-import__toggle")
    states["已选 Session + 导入面板"] = page.evaluate(AUDIT)
    page.click(".fbw-verdict__btn--ok")
    states["已判定"] = page.evaluate(AUDIT)
    for name, a in states.items():
        if a["sizes"] > 6 or a["small"] or a["overflow"]:
            bad.append(f"{name}:{a}")
    results.append((f"{tag}：三种状态字号 ≤6、小目标 0、无横向溢出", not bad, "; ".join(bad[:2])))


def guarded(results, name, fn, *args):
    """某一段中途抛错时记一条失败并继续后面的段落，免得一处超时吞掉全部结果。"""
    try:
        return fn(*args)
    except Exception as error:  # noqa: BLE001 — E2E 汇总用
        results.append((f"{name}：中途出错", False, str(error).splitlines()[0][:200]))
        return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-feedback-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        uids = [item["uid"] for item in http(port, "/api/stats")["items"]]
        sid = make_session(port, uids[:6])
        sid2 = make_session(port, uids[6:9])
        with sync_playwright() as p:
            browser = launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            guarded(results, '桌面主路径', run_desktop, page, base, port, sid, results)
            guarded(results, '手动录入', run_manual, page, base, uids[20], results)
            guarded(results, '旧入口', run_legacy_entries, page, base, sid2, results)
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            guarded(results, '手机', run_mobile, browser, base, sid2, results)
            for theme in ("light", "dark"):
                for label, size in (("桌面", (1440, 900)), ("手机", (390, 844))):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    tag = f"审计 {label} · {'浅色' if theme == 'light' else '深色'}"
                    guarded(results, tag, audit_states, c.new_page(), base, sid2, tag, results)
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
    print(f"E2E feedback：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
