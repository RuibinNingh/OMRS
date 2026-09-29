"""历史记录页：隔离 Vault 上验证列表、修正与四种主题/尺寸审计。"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium
from omrs.ledger import append_commit

_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)

AUDIT = """target => {
  const root = document.getElementById('hist-app');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('.katex'));
  const text = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(text).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a,b) => a-b);
  const hit = e => ['BUTTON','INPUT','SELECT','SUMMARY'].includes(e.tagName) || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r=e.getBoundingClientRect(); return r.width && r.height < target; })
    .map(e => `${e.tagName}.${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const inline = shown.filter(e => (e.getAttribute('style') || '').trim()).length;
  const handlers = shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length;
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible').length;
  return { sizes, small, inline, handlers, over, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""


def http(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
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


def open_history(page, base):
    page.goto(f"{base}/?t={os.urandom(3).hex()}#/history", wait_until="networkidle")
    return wait(page, "() => document.querySelector('#hist-app .hvw-node')")


def run_main(page, base, port, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)))

    before = http(port, "/api/history?limit=240")
    review = next(row for row in reversed(before["commits"]) if row["commit_type"] == "review.batch_submit")
    commit_id, seq = review["commit_id"], review["seq"]
    latest = max(row["seq"] for row in before["commits"])
    check("首屏：Ledger 主时间线已渲染且无旧全局", open_history(page, base)
          and page.locator(".hvw-node").count() == len(before["commits"])
          and page.evaluate("typeof loadHist === 'undefined' && typeof renderLedgerTimeline === 'undefined'"))
    page.select_option("#history-sort", "desc")
    check("排序切换为新到旧，偏好写入本地存储", wait(page, "seq => document.querySelector('.hvw-node')?.dataset.seq === String(seq)", latest)
          and page.evaluate("localStorage.getItem('omrs-history-sort')") == "desc")
    page.click('[data-action="history.mode"]')
    check("修正模式默认关闭，开启后才出现操作面板", page.locator(f'.hvw-node[data-seq="{seq}"] .hvw-ops').count() == 1
          and page.evaluate("localStorage.getItem('omrs-history-edit-mode')") == "1")

    page.click(f'.hvw-node[data-seq="{seq}"] .hvw-ops summary')
    page.route("**/api/history/review/retract", lambda route: route.fulfill(
        status=500, content_type="application/json", body='{"msg":"模拟写入失败"}'))
    page.click(f'.hvw-node[data-seq="{seq}"] [data-action="history.review"][data-arg="{seq}:retract"]')
    page.click('dialog[open] [data-dialog-ok]')
    check("写入失败：列表保留，错误原因显示在操作位置且按钮恢复", wait(page, "() => document.querySelector('#hist-app .ui-status--danger')?.textContent.includes('模拟写入失败')")
          and page.locator(f'.hvw-node[data-seq="{seq}"]').count() == 1
          and not page.locator(f'.hvw-node[data-seq="{seq}"] [data-action="history.review"][aria-busy]').count())
    check("请求失败后操作面板仍展开", page.locator(f'.hvw-node[data-seq="{seq}"] .hvw-ops').evaluate("el => el.open"))
    page.unroute("**/api/history/review/retract")

    page.click(f'.hvw-node[data-seq="{seq}"] [data-action="history.review"][data-arg="{seq}:retract"]')
    page.click('dialog[open] [data-dialog-ok]')
    key = f"{commit_id}:0"
    check("撤销反馈追加 Ledger 节点并更新主时间线", wait(page, "() => document.querySelector('#hist-app .ui-status--success')?.textContent.includes('已追加历史节点')")
          and key in http(port, "/api/history?limit=240")["retraction_state"]["retracted_reviews"])

    page.evaluate("location.hash = '#/dashboard'")
    expected = review["payload"]["feedbacks"]
    correct = sum(bool(fb["is_correct"]) for fb in expected[1:])
    wrong = len(expected) - 1 - correct
    chip = f"{correct} 对 · {wrong} 错"
    check("仪表盘最近动态读取撤销后的批次统计", wait(page, "a => document.querySelector(`.dsh-recent__row[data-key='${a.id}'] .ui-tag`)?.textContent === a.chip",
                                                   {"id": commit_id, "chip": chip}), chip)
    page.evaluate("location.hash = '#/history'")
    check("切页回来仍保留排序与修正模式", wait(page, "() => document.querySelector('#hist-app .hvw-node')")
          and page.locator("#history-sort").input_value() == "desc"
          and page.locator(f'.hvw-node[data-seq="{seq}"] .hvw-ops').count() == 1)

    page.click('[data-action="history.corrections"]')
    correction = next(row for row in reversed(http(port, "/api/history?limit=240")["commits"])
                      if row["commit_type"] == "review.retract")
    page.click(f'[data-action="history.directRestore"][data-arg="{correction["seq"]}"]')
    page.fill('dialog[open] input', '端到端恢复')
    page.click('dialog[open] [data-dialog-ok]')
    check("修正记录中的直接恢复追加 restore 节点", wait(page, "() => document.querySelector('#hist-app .ui-status--success')?.textContent.includes('已追加历史节点')")
          and key not in http(port, "/api/history?limit=240")["retraction_state"]["retracted_reviews"])

    page.route("**/api/history?view=summary&limit=60", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"msg":"历史暂不可用"}'))
    count = page.locator(".hvw-node").count()
    page.click('[data-action="history.refresh"]')
    failed = wait(page, "() => document.querySelector('#hist-app .ui-status--danger')?.textContent.includes('历史暂不可用')")
    page.unroute("**/api/history?view=summary&limit=60")
    page.click('[data-action="history.refresh"]')
    check("刷新失败保留旧列表并给原因；恢复后重试清除错误", failed and page.locator(".hvw-node").count() == count
          and wait(page, "() => !document.querySelector('#hist-app .ui-status--danger')"))

    uid = http(port, "/api/stats")["items"][0]["uid"]
    http(port, "/api/confirm-schedule", {"selected": [{"uid": uid, "source": "due"}], "persist": True})
    created = next(row for row in reversed(http(port, "/api/history?limit=240")["commits"])
                   if row["commit_type"] == "session.create")
    page.click('[data-action="history.refresh"]')
    check("外部新建 Session 后刷新可见节点", wait(page, "seq => !!document.querySelector(`.hvw-node[data-seq='${seq}']`)", created["seq"]))
    page.click(f'.hvw-node[data-seq="{created["seq"]}"] .hvw-ops summary')
    page.click(f'[data-action="history.session"][data-arg="{created["seq"]}:retract"]')
    page.fill('dialog[open] input', '端到端撤销 Session')
    page.click('dialog[open] [data-dialog-ok]')
    page.click('dialog[open] [data-dialog-ok]')
    sid = created["payload"].get("session_id") or created["payload"]["session"]["session_id"]
    state = http(port, "/api/history?limit=240")["retraction_state"]
    check("Session 撤销隐藏主节点并出现可恢复的修正记录", sid in state["retracted_sessions"]
          and wait(page, "seq => !document.querySelector(`.hvw-node[data-seq='${seq}']`)", created["seq"]))
    session_retract = next(row for row in reversed(http(port, "/api/history?limit=240")["commits"])
                           if row["commit_type"] == "session.retract")
    page.click(f'[data-action="history.directRestore"][data-arg="{session_retract["seq"]}"]')
    page.fill('dialog[open] input', '端到端恢复 Session')
    page.click('dialog[open] [data-dialog-ok]')
    check("Session 恢复后主节点重新出现", wait(page, "seq => !!document.querySelector(`.hvw-node[data-seq='${seq}']`)", created["seq"])
          and sid not in http(port, "/api/history?limit=240")["retraction_state"]["retracted_sessions"])

    page.click(f'.hvw-node[data-seq="{created["seq"]}"] .hvw-ops summary')
    page.click(f'[data-action="history.restoreState"][data-arg="{created["seq"]}"]')
    page.click('dialog[open] [data-dialog-ok]')
    check("结构化状态还原追加 Ledger 节点", wait(page, "() => document.querySelector('#hist-app .ui-status--success')?.textContent.includes('已追加历史节点')")
          and http(port, "/api/history?limit=240")["commits"][-1]["commit_type"] == "state.restore")

    page.evaluate("localStorage.setItem('omrs-ledger-time-zone', 'UTC'); __omrs.emit('ledger:tz')")
    utc = page.locator(f'.hvw-node[data-seq="{seq}"] .hvw-time').inner_text()
    page.evaluate("localStorage.setItem('omrs-ledger-time-zone', 'Asia/Shanghai'); __omrs.emit('ledger:tz')")
    shanghai = page.locator(f'.hvw-node[data-seq="{seq}"] .hvw-time').inner_text()
    check("Ledger 时区设置变化后时间重新投影", utc != shanghai, [utc, shanghai])
    page.click(f'.hvw-node[data-seq="{seq}"] .hvw-details summary')
    check("详情按需读取并保持展开", wait(page, "seq => { const detail = document.querySelector(`.hvw-node[data-seq='${seq}'] .hvw-details`); return detail?.open && detail.querySelector('pre')?.textContent.includes('feedbacks'); }", seq))


def run_empty_error(browser, base, results):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/history?view=summary&limit=60", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"msg":"测试离线"}'))
    page.goto(f"{base}/#/history", wait_until="networkidle")
    shown = wait(page, "() => document.querySelector('#hist-app .ui-empty')?.textContent.includes('测试离线')")
    page.unroute("**/api/history?view=summary&limit=60")
    page.click('#hist-app .ui-empty [data-action="history.refresh"]')
    results.append(("首次加载失败：空态说明原因并提供重试", shown and wait(page, "() => document.querySelector('#hist-app .hvw-node')"), ""))
    results.append(("错误态无页面脚本错误", not errors, "; ".join(errors[:3])))
    ctx.close()


def run_pagination(browser, base, port, vault, results):
    """真实浏览器加载 240 条以外的反馈；撤销状态仍取完整链。"""
    original = next(row for row in http(port, "/api/history?limit=240")["commits"]
                    if row["commit_type"] == "review.batch_submit")
    feedbacks = original["payload"]["feedbacks"][:2]
    if len(feedbacks) < 2:
        results.append(("跨页夹具至少两条反馈", False, ""))
        return
    review = append_commit(vault, "api", "review.batch_submit", "跨页练习", {
        "session_id": "EXP-PAGE", "feedbacks": feedbacks})
    for index in range(245):
        append_commit(vault, "system", "system.test", f"分页填充 {index}", {"index": index})
    append_commit(vault, "api", "review.retract", "跨页撤销", {
        "target_commit_id": review["commit_id"], "target_review_index": 0})
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/#/history", wait_until="networkidle")
    results.append(("超过 240 条时首屏只加载一批摘要", page.locator(".hvw-node").count() <= 60
                    and page.locator('[data-action="history.more"]').count() == 1, ""))
    initial = page.locator(".hvw-node").count()
    page.route("**/api/history?view=summary&limit=60&before_seq=*", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"msg":"分页暂不可用"}'))
    page.click('[data-action="history.more"]')
    failed = wait(page, "() => document.querySelector('#hist-app .ui-status--danger')?.textContent.includes('分页暂不可用')")
    results.append(("分页读取失败保留已加载节点", failed and page.locator(".hvw-node").count() == initial, ""))
    page.unroute("**/api/history?view=summary&limit=60&before_seq=*")
    anchor = page.evaluate("""() => {
      const box = document.querySelector('#history-timeline');
      box.scrollTop = 100;
      const top = box.getBoundingClientRect().top;
      const row = [...box.querySelectorAll('.hvw-node')].find(el => el.getBoundingClientRect().bottom > top + 5);
      return { seq: row?.dataset.seq, y: row?.getBoundingClientRect().top };
    }""")
    page.click('[data-action="history.more"]')
    wait(page, "old => document.querySelectorAll('.hvw-node').length > old", initial)
    new_y = page.locator(f'.hvw-node[data-seq="{anchor["seq"]}"]').evaluate("el => el.getBoundingClientRect().top")
    results.append(("升序前插分页维持可见节点滚动锚点", abs(new_y - anchor["y"]) < 4,
                    f"前 {anchor['y']:.1f} 后 {new_y:.1f}"))
    for _ in range(6):
        if page.locator(f'.hvw-node[data-seq="{review["seq"]}"]').count():
            break
        page.click('[data-action="history.more"]')
        page.wait_for_load_state("networkidle")
    node = page.locator(f'.hvw-node[data-seq="{review["seq"]}"]')
    results.append(("跨页反馈保留完整链撤销状态", node.count() == 1 and
                    node.locator('.hvw-mark[data-result="off"]').count() == 1 and
                    page.locator(".hvw-node").count() > 240, ""))
    results.append(("摘要卡默认不外露技术提交 ID", node.count() == 1 and
                    review["commit_id"] not in node.inner_text(), ""))
    results.append(("跨页路径无脚本错误", not errors, "; ".join(errors[:3])))
    ctx.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-history-")
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
            guarded(results, "首次错态", lambda: run_empty_error(browser, base, results))
            guarded(results, "跨页路径", lambda: run_pagination(browser, base, port, os.path.join(work, "vault"), results))
            for theme in ("light", "dark"):
                for label, viewport, target in (("桌面", (1440, 900), 28), ("手机", (390, 844), 40)):
                    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
                    ctx.add_init_script(f"localStorage.setItem('omrs-theme','{theme}');localStorage.setItem('omrs-history-edit-mode','1')")
                    pg = ctx.new_page()
                    open_history(pg, base)
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
    print(f"E2E history：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
