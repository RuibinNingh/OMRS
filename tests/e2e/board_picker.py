"""P7 第 4 轮 E2E：选板浮层 domain/board/picker.js（原 assets/board_picker.js）。

    python3 tests/e2e/board_picker.py     # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault 与隔离实例，不碰真实数据；认 OMRS_TEST_CDP_URL。开工时经 HTTP 再建 1 个文件夹、7 块板（共 8 块，出现「最近」）。覆盖：
- 题目库行内「⋯ → 加入展示板」：锚定弹出、进顶层、焦点在搜索框、「最近」与文件夹组、默认高亮与 aria-activedescendant；
  ↑↓ 移动；打字过滤（行带文件夹名、新建按钮带板名）；焦点不在搜索框时打字进搜索框、背后页面的快捷键（V）不触发；
  ←/→ 与点组标题折叠 / 展开（折叠状态存本地）；Ctrl+Enter 连加（浮层不关、✓、底栏计数）→ ⌘ 点击撤回；Enter 加入并关闭；
  Esc 关闭、焦点回到「⋯」；点外面关闭；「已全部在板中」的行点了打开该板；「新建板并加入」对话框（板名带入、文件夹选择）；
- 题目弹窗上叠浮层：进对话框、↑↓ 可用、Esc 只关浮层、焦点回到「加入展示板」按钮；
- 无锚点（toast 按钮、批量）居中弱模态；
- 审计：桌面 / 手机 × 浅 / 深，浮层字号 ≥12、可点目标 ≥28（手机 40）、只有定位用的自定义属性写在 style 上、完整在视口内、
  无横向溢出、深浅底色不同；全页没有旧 .bd-picker-*；全程脚本错误为 0。
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

READY = "() => window.__omrs && typeof DATA !== 'undefined' && DATA && document.querySelectorAll('#panel-questions [data-q-row]').length > 0"
OPENED = "() => !!document.querySelector('.bpicker .bpicker-opt')"
CLOSED = "() => !document.querySelector('.bpicker')"
STATE = """() => { const p = document.querySelector('.bpicker'); if (!p) return null;
  const s = p.querySelector('[data-bpk="search"]'); const a = p.querySelector('.bpicker-opt.is-active');
  return { active: a?.dataset.key || '', activeId: a?.id || '', desc: s.getAttribute('aria-activedescendant') || '', focus: document.activeElement === s,
    query: s.value, rows: [...p.querySelectorAll('.bpicker-opt')].map(o => o.dataset.key), hint: p.querySelector('.bpicker-hint').textContent,
    newLabel: p.querySelector('[data-bpk="new"]').textContent, groups: [...p.querySelectorAll('.bpicker-group')].map(g => g.textContent.trim()) }; }"""
AUDIT = """() => {
  const p = document.querySelector('.bpicker');
  if (!p) return null;
  const shown = [...p.querySelectorAll('*')].filter(e => e.getClientRects().length);
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a, b) => a - b);
  const min = innerWidth <= 760 ? 40 : 28;
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'INPUT' || e.tagName === 'SELECT';
  const small = shown.filter(hit).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < min - 0.5; }).map(e => e.className || e.tagName);
  const inline = [p, ...p.querySelectorAll('*')].filter(e => e.hasAttribute('style'))
    .filter(e => e !== p || [...e.style].some(name => !name.startsWith('--bpicker-'))).map(e => e.className || e.tagName);
  const r = p.getBoundingClientRect();
  return { sizes: sizes.length, list: sizes, small, inline, top: p.matches(':popover-open'),
    inside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 0.5 && r.bottom <= innerHeight + 0.5,
    overflow: document.documentElement.scrollWidth > innerWidth + 1 || p.scrollWidth > p.clientWidth + 1,
    bg: getComputedStyle(p).backgroundColor, legacy: document.querySelectorAll('[class*="bd-picker"]').length };
}"""


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
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))


def guarded(results, name, fn, *args):
    """某一段中途抛错时记一条失败并继续后面的段落。"""
    try:
        return fn(*args)
    except Exception as error:  # noqa: BLE001 — E2E 汇总用
        results.append((f"{name}：中途出错", False, str(error).splitlines()[0][:200]))
        return None


def seed(port):
    """在 fixture 的 1 块板之外再建 1 个文件夹、7 块板：「高三复习」里 3 块，未归档 4 块。"""
    folder = http(port, "/api/board/folder/create", {"name": "高三复习"})["folder"]["id"]
    for i in range(7):
        http(port, "/api/board/create", {"name": f"E2E 板 {i + 1}", "uids": [], "folder_id": folder if i < 3 else ""})
    return folder


def board_uids(port, name):
    boards = http(port, "/api/boards")["boards"]
    board = next(b for b in boards if b["name"] == name)
    return board["id"], board.get("uids", [])


def open_from_row(page, index=0):
    page.locator("#panel-questions tr[data-q-row] .qlb-more").nth(index).click()
    wait(page, "() => document.querySelector('.ui-menu.is-floating')")
    page.locator(".ui-menu.is-floating [role=menuitem]", has_text="加入展示板").click()
    return wait(page, OPENED)


def run_main(page, base, port, folder, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.goto(f"{base}/#/questions")
    check("题库表格就绪", wait(page, READY, 15000))
    uid = page.evaluate("() => document.querySelector('#panel-questions tr[data-q-row]').dataset.qRow")
    check("⋯ →「加入展示板」打开选板浮层", open_from_row(page))
    info = page.evaluate("""() => { const p = document.querySelector('.bpicker');
      return { parent: p.parentElement === document.body, top: p.matches(':popover-open'), centered: p.classList.contains('is-centered'), label: p.getAttribute('aria-label') }; }""")
    check("浮层进 body 与顶层、锚定弹出", info["parent"] and info["top"] and not info["centered"] and info["label"] == "加入展示板", json.dumps(info, ensure_ascii=False))
    check("焦点在搜索框", wait(page, "() => document.activeElement?.matches('.bpicker [data-bpk=\"search\"]')"))
    s = page.evaluate(STATE)
    check("8 块板：有「最近」、文件夹组与未归档组", s["groups"][:1] == ["最近"] and any(g.startswith("高三复习") for g in s["groups"]) and any(g.startswith("未归档") for g in s["groups"]), json.dumps(s["groups"], ensure_ascii=False))
    check("默认高亮一行，aria-activedescendant 指向它", bool(s["active"]) and s["desc"] == s["activeId"], json.dumps(s, ensure_ascii=False)[:200])
    first = s["active"]
    page.keyboard.press("ArrowDown")
    moved = wait(page, "k => document.querySelector('.bpicker-opt.is-active')?.dataset.key !== k", arg=first)
    page.keyboard.press("ArrowUp")
    check("↓ / ↑ 移动高亮", moved and wait(page, "k => document.querySelector('.bpicker-opt.is-active')?.dataset.key === k", arg=first))
    page.keyboard.type("高三")
    s = page.evaluate(STATE)
    folders = page.evaluate("() => [...document.querySelectorAll('.bpicker-opt .bpicker-name small')].map(e => e.textContent)")
    check("打字过滤：只剩文件夹里的 3 块板、行带文件夹名、新建按钮带板名",
          len(s["rows"]) == 3 and folders == ["高三复习"] * 3 and "《高三》" in s["newLabel"] and not s["groups"], json.dumps([s["rows"], folders, s["newLabel"]], ensure_ascii=False))
    page.keyboard.press("Control+a")
    page.keyboard.press("Backspace")
    wait(page, "() => document.querySelectorAll('.bpicker-group').length > 0")
    page.evaluate("() => document.querySelector('.bpicker-opt').focus()")
    page.keyboard.press("v")
    s = page.evaluate(STATE)
    gallery = page.evaluate("() => !!document.querySelector('.qlb-gcard')")
    check("焦点在行上时打字进搜索框，背后题库的 V（切视图）不触发", s["focus"] and s["query"] == "v" and not gallery, json.dumps([s["focus"], s["query"], gallery]))
    page.keyboard.press("Backspace")
    wait(page, "() => document.querySelectorAll('.bpicker-group').length > 0")
    steps = page.evaluate("""() => { const items = [...document.querySelectorAll('.bpicker-list > *')];
      const g = items.findIndex(e => e.matches('button.bpicker-group')); const opts = [...document.querySelectorAll('.bpicker-opt')];
      const target = items.slice(g + 1).find(e => e.matches('.bpicker-opt')); const now = opts.findIndex(o => o.classList.contains('is-active'));
      return opts.indexOf(target) - now; }""")
    for _ in range(max(0, steps)):
        page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowLeft")
    folded = wait(page, "() => document.querySelector('button.bpicker-group')?.getAttribute('aria-expanded') === 'false'")
    stored = page.evaluate("f => (localStorage.getItem('omrs-board-folders-collapsed') || '').includes(f)", folder)
    after = page.evaluate("() => document.querySelector('.bpicker-opt.is-active')?.dataset.key")
    page.keyboard.press("ArrowRight")
    check("← 折叠高亮行所在的文件夹（存本地，高亮移到组后第一行）、紧接 → 展开同一个组", folded and stored and (after or "").startswith("b:")
          and wait(page, "() => document.querySelector('button.bpicker-group')?.getAttribute('aria-expanded') === 'true'"), json.dumps([steps, folded, stored, after]))
    page.click("button.bpicker-group")
    clicked = wait(page, "() => document.querySelector('button.bpicker-group')?.getAttribute('aria-expanded') === 'false'")
    page.click("button.bpicker-group")
    check("点组标题折叠 / 展开", clicked and wait(page, "() => document.querySelector('button.bpicker-group')?.getAttribute('aria-expanded') === 'true'"))
    target = page.evaluate("() => document.querySelector('.bpicker-opt.is-active .bpicker-name').firstChild.textContent")
    page.keyboard.press("Control+Enter")
    ok = wait(page, "() => document.querySelector('.bpicker-opt.is-added') && document.querySelector('.bpicker-hint').textContent.includes('已加入 1 个板')")
    bid, uids = board_uids(port, target)
    check("Ctrl+Enter 连加：浮层不关、行打 ✓、底栏计数、服务端已加入", ok and uid in uids
          and page.evaluate("() => document.querySelector('.bpicker-opt.is-added .bpicker-cue').textContent === '✓'"), json.dumps([target, uids], ensure_ascii=False))
    page.locator(".bpicker-opt.is-added").first.click(modifiers=["ControlOrMeta"])
    undone = wait(page, "() => !document.querySelector('.bpicker-opt.is-added') && document.querySelector('.bpicker-hint').textContent.startsWith('Enter')")
    check("⌘ / Ctrl 点击撤回本次加入", undone and uid not in board_uids(port, target)[1])
    target = page.evaluate("() => document.querySelector('.bpicker-opt.is-active .bpicker-name')?.firstChild?.textContent || ''")
    bid, _ = board_uids(port, target)
    page.keyboard.press("Enter")
    closed = wait(page, CLOSED)
    present = uid in board_uids(port, target)[1]
    toasted = wait(page, "n => [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('已加入《' + n + '》'))", arg=target)
    check("Enter 加入并关闭，toast 报告结果", closed and present and toasted,
          json.dumps({"closed": closed, "present": present, "toasted": toasted,
                      "toasts": page.locator('.ui-toast').all_inner_texts()}, ensure_ascii=False))
    open_from_row(page)
    page.keyboard.press("Escape")
    check("Esc 关闭，焦点回到「⋯」", wait(page, CLOSED) and wait(page, "() => document.activeElement?.classList.contains('qlb-more')"))
    open_from_row(page)
    page.click(".qlb-total")
    check("点外面关闭", wait(page, CLOSED))
    open_from_row(page)
    full = page.locator(".bpicker-opt.is-full", has_text=target).first
    cue = full.locator(".bpicker-cue").text_content()
    full.click()
    check("「已全部在板中」的行显示 ↗，点了打开该板", cue == "↗" and wait(page, CLOSED)
          and wait(page, "id => location.hash === '#/board' && typeof boardCurrentId === 'function' && boardCurrentId() === id", arg=bid), json.dumps({"cue": cue, "hash": page.evaluate("location.hash"), "current": page.evaluate("typeof boardCurrentId === 'function' ? boardCurrentId() : null"), "type": page.evaluate("typeof boardCurrentId"), "title": page.evaluate("document.querySelector('.brd-title')?.textContent"), "want": bid}))
    page.goto(f"{base}/#/questions")
    wait(page, READY, 15000)
    open_from_row(page)
    page.keyboard.type("E2E 新板")
    page.click(".bpicker [data-bpk='new']")
    dlg = wait(page, "() => document.querySelector('dialog[open] #bpk-new-name')?.value === 'E2E 新板' && !!document.querySelector('dialog[open] #bpk-new-folder')")
    check("「新建板并加入」：浮层关闭、对话框带入板名与文件夹选择", dlg and page.evaluate(CLOSED))
    page.click("dialog[open] [data-dialog-ok]")
    ok = wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('已新建《E2E 新板》'))")
    check("新建并加入：服务端新板含该题", ok and uid in board_uids(port, "E2E 新板")[1])


def run_modal(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.goto(f"{base}/#/questions")
    wait(page, READY, 15000)
    page.locator("#panel-questions tr[data-q-row]").first.locator("td").nth(1).click()
    wait(page, "() => document.querySelector('dialog#modal[open] #modal-stage [data-qv-act=\"board\"]')")
    page.click("#modal-stage [data-qv-act='board']")
    check("题目弹窗里打开：浮层放进对话框", wait(page, "() => document.getElementById('modal')?.contains(document.querySelector('.bpicker'))"))
    first = page.evaluate("() => document.querySelector('.bpicker-opt.is-active')?.dataset.key")
    page.keyboard.press("ArrowDown")
    check("对话框里 ↓ 也移动高亮（弹窗不翻页）", wait(page, "k => document.querySelector('.bpicker-opt.is-active')?.dataset.key !== k", arg=first)
          and page.evaluate("() => /第 1 \\//.test(document.getElementById('qv-nav-pos')?.textContent || '第 1 /')"))
    page.keyboard.press("Escape")
    check("Esc 只关浮层，弹窗仍在，焦点回到「加入展示板」", wait(page, CLOSED) and page.evaluate("() => !!document.querySelector('dialog#modal[open]')")
          and wait(page, "() => document.activeElement?.matches('[data-qv-act=\"board\"]')"))
    page.keyboard.press("Escape")
    check("再按 Esc 关题目弹窗", wait(page, "() => !document.querySelector('dialog#modal')"))


def run_centered(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.goto(f"{base}/#/questions")
    wait(page, READY, 15000)
    uids = page.evaluate("() => [...document.querySelectorAll('#panel-questions tr[data-q-row]')].slice(0, 2).map(r => r.dataset.qRow)")
    page.evaluate("u => boardChooseAndAdd(u)", uids)
    wait(page, OPENED)
    page.wait_for_timeout(300)   # 等入场动画（位移 --sp-1_5）结束再量
    box = page.evaluate("""() => { const p = document.querySelector('.bpicker'); const r = p.getBoundingClientRect();
      return { centered: p.classList.contains('is-centered'), dx: Math.abs(r.left + r.width / 2 - innerWidth / 2), dy: Math.abs(r.top + r.height / 2 - innerHeight / 2),
        count: p.querySelector('.bpicker-count').textContent }; }""")
    check("无锚点：居中弱模态，标题显示题数", box["centered"] and box["dx"] < 2 and box["dy"] < 2 and box["count"] == "2 道题", json.dumps(box, ensure_ascii=False))
    page.keyboard.press("Escape")
    check("Esc 关闭居中浮层", wait(page, CLOSED))


def audit(page, base, tag, results):
    page.goto(f"{base}/#/questions", wait_until="networkidle")
    wait(page, READY, 15000)
    page.evaluate("""() => { const uid = document.querySelector('#panel-questions [data-q-row]').dataset.qRow;
      const anchor = [...document.querySelectorAll('.qlb-more')].find(e => e.getClientRects().length) || document.getElementById('qlb-search');
      boardQuickAdd(uid, { anchor }); }""")
    wait(page, OPENED)
    page.wait_for_timeout(300)
    a = page.evaluate(AUDIT)
    ok = bool(a) and a["top"] and a["inside"] and not a["small"] and not a["inline"] and not a["overflow"] and a["list"][0] >= 12 and a["legacy"] == 0
    results.append((f"{tag}：浮层字号 ≥12（{a['sizes'] if a else '?'} 种）、小目标 0、不写行内样式、在视口内、无横向溢出", ok, json.dumps(a, ensure_ascii=False)[:300]))
    page.keyboard.press("Escape")
    return a["bg"] if a else None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-picker-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        folder = seed(port)
        with sync_playwright() as p:
            browser = launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            guarded(results, "题目库入口", run_main, page, base, port, folder, results)
            guarded(results, "题目弹窗上", run_modal, page, base, results)
            guarded(results, "无锚点", run_centered, page, base, results)
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            colors = {}
            for theme in ("light", "dark"):
                for label, size in (("桌面", (1440, 900)), ("手机", (390, 844))):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    tag = f"审计 {label} · {'浅色' if theme == 'light' else '深色'}"
                    colors[(theme, label)] = guarded(results, tag, audit, c.new_page(), base, tag, results)
                    c.close()
            results.append(("深浅色：浮层底色随主题变化", colors.get(("light", "桌面")) and colors.get(("light", "桌面")) != colors.get(("dark", "桌面")), json.dumps({f"{k[0]}-{k[1]}": v for k, v in colors.items()})))
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E board_picker：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
