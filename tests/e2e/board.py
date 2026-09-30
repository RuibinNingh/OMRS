"""展示板改版 E2E：常驻纸面、题目面板、版式、保存、锁定与补印续排。"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)


def http(port, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))


def board(port, bid):
    return http(port, f"/api/board?id={urllib.parse.quote(bid)}")["board"]


def order(port, bid):
    return [entry["uid"] for entry in board(port, bid)["items"]]


def poll(fn, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(.15)
    return fn()


def wait(page, expression, timeout=12000):
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:
        return False


def record(results, name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:250]))


def seed(port):
    items = http(port, "/api/stats")["items"]
    used = set(http(port, "/api/boards")["boards"][0]["uids"])
    uids = [item["uid"] for item in items if item["uid"] not in used and not item.get("suspended")][:18]
    folder = http(port, "/api/board/folder/create", {"name": "高三复习"})["folder"]["id"]
    first = http(port, "/api/board/create", {"name": "E2E 甲", "uids": uids[:12], "folder_id": folder})["board"]["id"]
    second = http(port, "/api/board/create", {"name": "E2E 乙", "uids": []})["board"]["id"]
    return folder, first, second


def board_row(page, name):
    return page.locator(".brd-item", has=page.locator(".brd-item__name", has_text=name)).first


def add_items(page, count):
    page.locator('[data-action="board.add"]').first.click()
    page.wait_for_selector("dialog#bd-add-dialog[open] [data-bdadd-uid]")
    boxes = page.locator("dialog#bd-add-dialog [data-bdadd-uid]:not(:disabled)")
    picked = []
    for index in range(count):
        box = boxes.nth(index)
        picked.append(box.get_attribute("data-bdadd-uid"))
        box.check()
    page.click("dialog#bd-add-dialog [data-dialog-ok]")
    wait(page, "() => !document.querySelector('dialog#bd-add-dialog')")
    return picked


def run_path(page, base, port, ids, results):
    folder, first, second = ids
    page.goto(f"{base}/#/board")
    page.wait_for_function("() => window.__p8TestReady && window.__omrs && !!document.querySelector('#bd-stage > iframe')", timeout=20000)
    ready = wait(page, "() => boardPreviewIsReady() && boardPreviewLayout()?.pages > 0", 20000)
    shape = page.evaluate("""() => ({
      stage: document.querySelectorAll('#bd-stage[data-morph="skip"] > iframe').length,
      list: !!document.querySelector('#bd-content-body .brd-row'),
      views: document.querySelectorAll('[data-board-view]').length,
      detail: !!document.querySelector('#bd-inspector'),
      layout: !!document.querySelector('[data-action="board.layoutPop"]') })""")
    record(results, "进页：常驻纸面与题目面板并列，视图切换已移除", ready and shape == {
        "stage": 1, "list": True, "views": 0, "detail": True, "layout": True}, shape)

    board_row(page, "E2E 甲").locator(".brd-item__main").click()
    switched = wait(page, f"() => document.querySelector('.brd-title')?.textContent === 'E2E 甲' && boardPreviewLayout()?.board_id === {json.dumps(first)}", 20000)
    page.evaluate("() => { window.__boardFrame = boardPreviewFrame(); boardPreviewFrame().contentWindow.__keep = 1; }")
    page.locator(f'.brd-folder[data-board-folder-drag="{folder}"] .brd-fold').click()
    collapsed = board_row(page, "E2E 甲").count() == 0
    page.locator(f'.brd-folder[data-board-folder-drag="{folder}"] .brd-fold').click()
    preserved = wait(page, "() => boardPreviewFrame() === window.__boardFrame && boardPreviewFrame().contentWindow.__keep === 1")
    record(results, "切板、折叠树、重绘：预览 iframe 不移动也不重载", switched and collapsed and preserved)

    page.locator('[data-action="board.layoutPop"]').click()
    layout_pop = page.locator('.brd-pop [data-board-print="note_ratio"]').is_visible()
    page.locator('[data-action="board.closePop"]').last.click()
    record(results, "版式从工具条打开浮层", layout_pop)

    # 纸面切换动效：设置只保存在浏览器本地，下一次预览消息带上当前配置。
    page.locator('[data-action="board.motionPop"]').click()
    motion = page.locator('.brd-pop[data-kind="motion"]')
    menu_open = motion.is_visible() and motion.locator('[data-action="board.motionKind"]').count() == 4
    motion.locator('[data-action="board.motionKind"][data-arg="slide"]').click()
    duration = motion.locator('[data-input="board.motionDuration"]')
    duration.fill('450')
    duration.dispatch_event('input')
    pref = poll(lambda: page.evaluate("""() => {
      const value = JSON.parse(localStorage.getItem('omrs-board-motion') || '{}');
      return value.kind === 'slide' && value.duration === 450;
    }"""), 3)
    host_motion = page.evaluate("() => boardPreviewView().motion")
    page.locator('[data-action="board.closePop"]').last.click()
    record(results, "动效菜单：四种模式、时长滑杆和本地保存", menu_open and pref and host_motion == {"kind": "slide", "duration": 450}, host_motion)

    # 连续翻页不排队；最终页码以最后一次操作为准。单页板没有下一页时仍检查配置不报错。
    page_count = page.evaluate("() => boardPreviewLayout()?.page_numbers?.length || 0")
    if page_count > 1:
        next_button = page.locator('[data-action="board.page"][data-arg="next"]')
        next_button.click()
        next_button.click()
        latest = page.evaluate("() => boardPreviewLayout()?.page_numbers?.slice(-1)[0]")
        settled = wait(page, f"() => boardPreviewView().page === {latest}", 5000)
        frame_motion = page.evaluate("""() => {
          const frame = document.querySelector('#bd-stage > iframe');
          return frame?.contentDocument?.body?.classList.contains('embedded') &&
            frame?.contentDocument?.querySelector('#stage.motion-layer') !== null;
        }""")
        settled_layout = wait(page, f"""() => {{
          if (boardPreviewView().page !== {latest}) return false;
          const frame = document.querySelector('#bd-stage > iframe');
          const doc = frame?.contentDocument;
          const target = doc?.querySelector('#stage .page[data-page="{latest}"]');
          return !!target && !doc.querySelector('#stage.motion-layer') &&
            target.getAnimations().length === 0 && getComputedStyle(target).transform === 'none';
        }}""", 5000)
        record(results, "连续翻页：取消旧动效并停在最新目标页", settled and settled_layout and (frame_motion or page.evaluate("() => boardPreviewView().page") == latest), latest)
    else:
        record(results, "单页板：翻页按钮无效时不抛错", True)

    page.reload()
    page.wait_for_function("() => window.__p8TestReady && !!document.querySelector('#bd-stage > iframe')", timeout=20000)
    restored = wait(page, "() => boardPreviewIsReady() && boardPreviewView().motion?.kind === 'slide'", 20000)
    record(results, "刷新后恢复动效偏好", restored and page.evaluate("() => boardPreviewView().motion.duration") == 450)

    board_row(page, "E2E 乙").locator(".brd-item__main").click()
    blank = wait(page, "() => document.querySelector('.brd-title')?.textContent === 'E2E 乙' && !!document.querySelector('.brd-placeholder')")
    record(results, "空板：纸面和题目列表给空状态", blank)

    labels = [entry["name"] for entry in http(port, "/api/labels")["labels"] if not entry.get("archived")]
    if labels:
        linked = labels[0]
        page.locator('[data-action="board.linkLabel"]').click()
        page.locator('.ui-menu__item', has_text=linked).first.click()
        local = poll(lambda: page.evaluate("id => JSON.parse(localStorage.getItem('omrs-board-linked-labels') || '{}')[id]", second), 3)
        record(results, "关联标记：按板存本机浏览器，不改板的服务端字段", local == linked
               and not board(port, second).get("source_labels"), local)

    picked = add_items(page, 3)
    saved = poll(lambda: order(port, second) == picked)
    rows = wait(page, "() => document.querySelectorAll('#bd-content-body .brd-row').length === 3")
    record(results, "加题：三题落盘并出现在常驻列表", saved and rows, picked)

    uid = picked[1]
    row = page.locator(f'.brd-row[data-board-row="{uid}"]')
    before = board(port, second)["items"][1].get("gap_lines")
    row.locator('[data-action="board.gapStep"][data-arg$=":1"]').click()
    stepped = poll(lambda: board(port, second)["items"][1].get("gap_lines") == (before or 2) + 1)
    echoed = wait(page, f"() => document.querySelector('.brd-row[data-board-row={json.dumps(uid)}] [data-board-gap-view]')?.textContent.includes('3')")
    record(results, "行内留白步进：保存后列表读数同步", stepped and echoed)

    row.locator(".brd-row__uid").click()
    opened = wait(page, f"() => document.querySelector('.brd-questions')?.hasAttribute('data-detail') && document.querySelector('#bd-inspector [data-qv-host]')?.dataset.uid === {json.dumps(uid)}")
    hydrated = wait(page, "() => !!document.querySelector('#bd-inspector [data-qv-host] .qv')", 15000)
    page.locator('[data-action="board.detailStep"][data-arg="1"]').click()
    next_uid = picked[2]
    navigated = wait(page, f"() => document.querySelector('#bd-inspector [data-qv-host]')?.dataset.uid === {json.dumps(next_uid)}")
    page.locator('[data-action="board.gapPreset"][data-arg$=":6"]').click()
    preset = poll(lambda: board(port, second)["items"][2].get("gap_lines") == 6)
    page.locator('[data-action="board.back"]').click()
    record(results, "详情层：题面与记录加载、前后导航、预设留白、返回列表", opened and hydrated and navigated and preset)

    # 详情层是「固定头 + 独立滚动的正文 + 固定脚」；答案先折叠；导航条上的「打开题目」打开共享题目弹窗。
    row.locator(".brd-row__uid").click()
    wait(page, "() => !!document.querySelector('#bd-inspector [data-qv-host] .qv .qv-locked')", 15000)
    page.locator("#bd-inspector .qv-locked .ui-btn").click()
    revealed = wait(page, "() => !!document.querySelector('#bd-inspector [data-qv-host] .q-answer-md')")
    box = page.evaluate("""() => { const b=document.querySelector('.brd-detail-body'), q=document.querySelector('.brd-questions');
      const f=document.querySelector('.brd-detail-foot').getBoundingClientRect();
      return { scroll: getComputedStyle(b).overflowY, footIn: f.height > 0 && f.bottom <= q.getBoundingClientRect().bottom + 1,
        rec: !!document.querySelector('#bd-inspector [data-board-rec] p') }; }""")
    page.locator("#bd-inspector .brd-open-q").click()
    modal = wait(page, f"() => document.querySelector('dialog#modal[open] .qv')?.dataset.qvUid === {json.dumps(uid)}", 15000)
    page.keyboard.press("Escape")
    closed = wait(page, "() => !document.querySelector('dialog#modal[open]')")
    page.locator('[data-action="board.back"]').click()
    record(results, "详情层：正文独立滚动、脚常驻、答案先折叠、「打开题目」打开题目弹窗", revealed and modal and closed
           and box == {"scroll": "auto", "footIn": True, "rec": True}, box)

    # 宽屏收起左栏：纸面宽度变大，「适应宽度」自动重算；板头按钮再展开。
    before = page.evaluate("() => boardPreviewView().scale")
    page.locator('#bd-list [data-action="board.toggleBoards"]').click()
    hidden = wait(page, "() => !!document.querySelector('.brd[data-list-hidden]') && !document.querySelector('#bd-list').offsetParent")
    grown = wait(page, f"() => boardPreviewView().scale > {before}")
    page.locator(".brd-bar .brd-open-list").click()
    shown = wait(page, "() => !document.querySelector('.brd[data-list-hidden]') && !!document.querySelector('#bd-list').offsetParent")
    record(results, "宽屏收起 / 展开左栏：纸面按新宽度自动适配", hidden and grown and shown, before)

    page.locator('[data-action="board.sortMenu"]').first.click()
    page.locator(".ui-menu__item", has_text="反转顺序").click()
    reversed_order = poll(lambda: order(port, second) == list(reversed(picked)))
    rows_now = page.locator(".brd-row")
    rows_now.first.drag_to(rows_now.last)
    dragged = poll(lambda: order(port, second) != list(reversed(picked)))
    record(results, "排序菜单与拖动行：顺序落盘", reversed_order and dragged, order(port, second))

    # 连续改留白后立刻切板，加载新板必须先排空保存队列。
    latest = order(port, second)[0]
    snapshot = board(port, second)
    initial_gap = next(x for x in snapshot["items"] if x["uid"] == latest).get("gap_lines")
    initial_gap = initial_gap if initial_gap is not None else snapshot["print"].get("gap_lines", 2)
    page.locator(f'.brd-row[data-board-row="{latest}"] [data-action="board.gapStep"][data-arg$=":1"]').click()
    page.locator(f'.brd-row[data-board-row="{latest}"] [data-action="board.gapStep"][data-arg$=":1"]').click()
    board_row(page, "E2E 甲").locator(".brd-item__main").click()
    switched_back = wait(page, "() => document.querySelector('.brd-title')?.textContent === 'E2E 甲'")
    board_row(page, "E2E 乙").locator(".brd-item__main").click()
    preserved_gap = poll(lambda: next(x for x in board(port, second)["items"] if x["uid"] == latest).get("gap_lines") == initial_gap + 2)
    record(results, "快速连改后切板：改动先保存且重载不丢", switched_back and preserved_gap)

    page.locator('[data-action="board.layoutPop"]').click()
    page.evaluate("""() => { const r=document.querySelector('[data-board-print="note_ratio"]');
      r.value='40'; r.dispatchEvent(new Event('input',{bubbles:true})); r.dispatchEvent(new Event('change',{bubbles:true})); }""")
    ratio = poll(lambda: abs(board(port, second)["print"].get("note_ratio", 0) - .4) < .001)
    page.locator('[data-board-seg="answers"] [data-value="append"]').click()
    answers = poll(lambda: board(port, second)["print"].get("answers") == "append")
    page.locator('[data-board-seg="answers"] [data-value="none"]').click()
    poll(lambda: board(port, second)["print"].get("answers") == "none")
    page.locator('[data-action="board.closePop"]').last.click()
    record(results, "版式浮层：右侧留白和答案写入并更新纸面", ratio and answers)

    page.evaluate("() => configureBoardDetail({ confirm: async () => true })")
    with page.expect_popup() as opening:
        page.locator("[data-board-primary]").click()
    popup = opening.value
    popup.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'", timeout=25000)
    confirmed = wait(page, "() => !!document.querySelector('.brd-confirm:not([hidden])')")
    page.locator('[data-action="board.markPrinted"]').click()
    recorded = poll(lambda: board(port, second).get("printed_summary", {}).get("pages", 0) > 0, 20)
    popup.close()
    record(results, "打印 → 确认条 → 记录纸面：服务端保存页数", confirmed and recorded,
           board(port, second).get("printed_summary"))

    page.locator('[data-action="board.layoutPop"]').click()
    page.locator('[data-board-print="locked"]').check()
    poll(lambda: board(port, second)["print"].get("locked") is True)
    page.evaluate("() => configureBoardDetail({ confirm: async () => false })")
    page.evaluate("""() => { const r=document.querySelector('[data-board-print="note_ratio"]');
      r.value='44'; r.dispatchEvent(new Event('change',{bubbles:true})); }""")
    time.sleep(.5)
    unchanged = abs(board(port, second)["print"].get("note_ratio", 0) - .4) < .001
    paper_kept = board(port, second).get("printed_summary", {}).get("pages", 0) > 0
    page.locator('[data-action="board.closePop"]').last.click()
    record(results, "锁定版式：拒绝真实版式变更后保留纸面记录与旧比例", unchanged and paper_kept)

    extra = add_items(page, 1)[0]
    new_item = poll(lambda: extra in order(port, second))
    mode = page.locator('[data-board-mode="new"]')
    mode.click()
    scoped = wait(page, "() => boardPreviewLayout()?.mode === 'new' && boardPreviewLayout()?.rendered_pages > 0", 25000)
    label = page.locator('[data-board-primary]').inner_text()
    paper = board(port, second)["printed_summary"]
    continuation = page.evaluate("""() => ({ pages: boardPreviewLayout()?.page_numbers || [],
      partial: boardPreviewLayout()?.partial_page || 0 })""")
    cursor = paper.get("cursor", {}).get("page", paper["pages"])
    starts_at_cursor = bool(continuation["pages"]) and min(continuation["pages"]) >= cursor
    record(results, "打印 → 记录 → 加题 → 只印新增：按旧纸续排位置预览", new_item and scoped
           and "补印新增 1 题" in label and starts_at_cursor, continuation)
    page.locator('[data-action="board.paperPop"]').click()
    pop_text = page.locator('.brd-pop').inner_text()
    record(results, "纸面记录浮层：已印数、续排位置、清空操作可见",
           str(paper["pages"]) in pop_text and "续排位置" in pop_text and "清空纸面记录" in pop_text)


def audit(page, base, theme, size, results):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
    page.goto(f"{base}/#/board")
    wait(page, "() => !!document.querySelector('#bd-stage > iframe')")
    data = page.evaluate("""() => {
      const root=document.querySelector('#panel-board .brd'), stage=root.querySelector('#bd-stage');
      const frame=stage.querySelector('iframe'), work=root.querySelector('.brd-work');
      const list=root.querySelector('#bd-content-body'), q=root.querySelector('.brd-questions');
      const r=x=>{const b=x.getBoundingClientRect();return [b.x,b.y,b.width,b.height]};
      return { stage:r(stage), questions:r(q), work:r(work), list:r(list),
        overflow:document.documentElement.scrollWidth>innerWidth+1,
        frame:!!frame, inline:root.querySelectorAll('[style]').length,
        views:root.querySelectorAll('[data-board-view]').length,
        theme:getComputedStyle(root.querySelector('.brd-bar')).backgroundColor };
    }""")
    mobile = size[0] <= 760
    aligned = data["questions"][1] > data["stage"][1] if mobile else data["questions"][0] > data["stage"][0]
    record(results, f"{theme} · {size[0]}：纸面和题目面板布局、无横向溢出与行内样式",
           data["frame"] and not data["overflow"] and data["inline"] == 0 and data["views"] == 0 and aligned, data)
    if mobile:
        page.locator('.brd-open-list').first.click()
        opened = page.locator('#bd-list[data-open]').is_visible()
        page.locator('#bd-list [data-action="board.toggleBoards"]').click()
        record(results, f"{theme} · 手机：板列表以抽屉打开并能收起",
               opened and not page.locator('#bd-list[data-open]').count())
    return data["theme"]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    os.environ.pop("OMRS_SYSTEMD_SERVICE", None)
    work = tempfile.mkdtemp(prefix="omrs-e2e-board-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        ids = seed(port)
        with sync_playwright() as p:
            url = os.environ.get("OMRS_TEST_CDP_URL")
            browser = p.chromium.connect_over_cdp(url) if url else p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(10000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                run_path(page, base, port, ids, results)
            except Exception as error:
                record(results, "主路径中途出错", False, str(error).splitlines()[0])
            record(results, "主路径页面脚本错误为 0", not errors, "; ".join(errors[:3]))
            ctx.close()
            colors = {}
            for theme in ("light", "dark"):
                for size in ((1440, 900), (390, 844)):
                    c = browser.new_context()
                    colors[(theme, size[0])] = audit(c.new_page(), base, theme, size, results)
                    c.close()
            record(results, "深浅主题的板头颜色不同", colors[("light", 1440)] != colors[("dark", 1440)])
            if not url:
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [entry for entry in results if not entry[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E board：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
