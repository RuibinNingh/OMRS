"""P7 E2E：展示板页 features/board/（第 5 轮：状态条、板列表、舞台头、页面快捷键、板列表的数据所有者 domain/board/boards.js；
第 6 轮：列表 / 画廊、检查器、「添加题目」对话框原生，板详情归 features/board/detail.js，旧 assets/board.js 删除）。

    python3 tests/e2e/board.py     # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault 与隔离实例，不碰真实数据；认 OMRS_TEST_CDP_URL。开工时经 HTTP 再建 1 个文件夹、2 块板。覆盖：
- 进页：骨架，舞台 iframe 是唯一 skip 区、检查器原生、状态条、翻页条读数；页面里没有旧 .bd-statusbar / .bd-row / .bd-ins-sec 等；
- 左栏：点板切换（状态条、aria-current、预览换板）；折叠 / 展开文件夹（存本地）；重绘与切视图都不挪动、不重载预览 iframe；
- 列表视图：↑↓ 选行、Ctrl+↓ 换位落盘、Enter 打开题目、Delete 移除与撤销；
- 状态条就地改名（双击 → Enter 保存、Esc 取消）；「＋ 新建」菜单新建板；板 ⋯ 菜单移到文件夹；文件夹 ⋯ 菜单重命名、上移下移禁用；
- 快捷键 N（对话框打开时其它快捷键不触发）、A；左栏拖放把板拖进文件夹；有待保存的改动时切走立即落盘；板 ⋯ 菜单删除；
- 第 6 轮「加题 → 排序 → 版面设置 → 打印预览 → 仅补印新增」：空板空态、A 打开「添加题目」（Esc 关得掉；勾选跨列表 / 画廊
  保持；加入落盘）、点行选中与检查器、行上「留白」把焦点送进检查器并改单题留白、排序菜单、答案分段与滑杆、画廊题面与「回到纸面」、
  打印预览弹窗 → 记录纸面 → 再加一题 → 「仅新增」主按钮与预览范围；
- 审计：桌面 / 手机 × 浅 / 深 × 纸面 / 列表，本页原生部分（含检查器、列表）字号 ≥12、可点目标 ≥28（手机 40；复选框量它的标签）、
  没有 style=、无横向溢出、没有旧类名、深浅底色不同（标记芯片 .lbl 的字号不计，外观 P8 随 styles.css 搬）；全程脚本错误为 0。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("visual_run", os.path.join(ROOT, "tests", "visual", "run.py"))
visual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual)

READY = "() => window.__omrs && !!document.querySelector('#panel-board .brd-title') && typeof boardPreviewIsReady === 'function' && boardPreviewIsReady()"
TITLE = "() => document.querySelector('.brd-title')?.textContent || ''"
DIALOG = "() => !!document.querySelector('dialog[open]:not(.is-closing)')"
NATIVE = """(root => { const skip = [...root.querySelectorAll('[data-morph="skip"]')];
  return [...root.querySelectorAll('*')].filter(e => !skip.some(s => s.contains(e))); })"""
AUDIT = """() => {
  const root = document.querySelector('#panel-board .brd');
  if (!root) return null;
  const all = (%s)(root);
  // 标记芯片 .lbl 的外观仍在旧 styles.css（9.6px，progress §8：P8 随 styles.css 一起搬），字号种数不计它
  const shown = all.filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && !e.closest('.lbl'));
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a, b) => a - b);
  const min = innerWidth <= 760 ? 40 : 28;
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'INPUT' || e.tagName === 'SELECT';
  const box = e => (e.type === 'checkbox' || e.type === 'radio' ? e.closest('label') || e : e);   // 复选框的可点区域是它的标签
  const small = shown.filter(hit).filter(e => { const r = box(e).getBoundingClientRect(); return r.width && r.height < min - 0.5; })
    .map(e => `${e.className || e.tagName}:${Math.round(box(e).getBoundingClientRect().height)}`);
  const inline = [root, ...all].filter(e => e.hasAttribute('style') && e.getAttribute('style').trim()).map(e => e.className || e.tagName);
  return { min: sizes[0] || 0, list: sizes, small: [...new Set(small)], inline,
    overflow: document.documentElement.scrollWidth > innerWidth + 1,
    bg: getComputedStyle(document.querySelector('.brd-bar')).backgroundColor,
    legacy: document.querySelectorAll('.bd-statusbar,.bd-board-item,.bd-folder,.bd-stagebar,.bd-pager,.bd-list-head,.bd-row,.bd-ins-sec,.bd-badge,.bd-field,.bd-gallery-card,.board-add-modal').length };
}""" % NATIVE


def launch_browser(p):
    url = os.environ.get("OMRS_TEST_CDP_URL")
    return p.chromium.connect_over_cdp(url) if url else p.chromium.launch()


def wait(page, expression, timeout=8000, arg=None):
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
    """fixture 自带 1 块板（未归档）；再建文件夹「高三复习」、里面的「E2E 甲」（4 题）与未归档的空板「E2E 乙」。"""
    items = http(port, "/api/stats")["items"]
    used = set(http(port, "/api/boards")["boards"][0]["uids"])
    uids = [item["uid"] for item in items if item["uid"] not in used and not item.get("suspended")][:4]
    folder = http(port, "/api/board/folder/create", {"name": "高三复习"})["folder"]["id"]
    first = http(port, "/api/board/create", {"name": "E2E 甲", "uids": uids, "folder_id": folder})["board"]["id"]
    second = http(port, "/api/board/create", {"name": "E2E 乙", "uids": [], "folder_id": ""})["board"]["id"]
    return folder, first, second, uids


def board(port, bid):
    return http(port, f"/api/board?id={urllib.parse.quote(bid)}")["board"]


def order(port, bid):
    return [entry["uid"] for entry in board(port, bid)["items"]]


def boards(port):
    return {b["name"]: b for b in http(port, "/api/boards")["boards"]}


def poll(fn, tries=40):
    import time
    for _ in range(tries):
        value = fn()
        if value:
            return value
        time.sleep(0.15)
    return fn()


def item(page, name):
    return page.locator(".brd-item", has=page.locator(".brd-item__name", has_text=name)).first


def run_main(page, base, port, ids, results):
    folder, first, second, uids = ids
    page.goto(f"{base}/#/board")
    ok = wait(page, READY, 15000)
    shape = page.evaluate("""() => ({ ids: ['bd-statusbar', 'bd-list', 'bd-content', 'bd-stage', 'bd-content-body', 'bd-inspector'].every(id => document.getElementById(id)),
      skip: [...document.querySelectorAll('#panel-board [data-morph="skip"]')].map(e => e.id).join(','),
      frame: !!document.querySelector('#bd-stage > .bd-preview-frame'), stage: !document.getElementById('bd-stage').hidden,
      legacy: document.querySelectorAll('.bd-statusbar,.bd-board-item,.bd-folder,.bd-stagebar,.bd-pager,.bd-row,.bd-ins-sec,.bd-badge').length,
      est: document.querySelector('.brd-est')?.textContent || '', ins: !document.getElementById('bd-inspector').hidden
        && !!document.querySelector('#bd-inspector .brd-sec[data-sec="layout"] [data-board-print="note_ratio"]'),
      script: !!document.querySelector('script[src*="assets/board.js"]') })""")
    results.append(("进页：骨架、舞台是唯一 skip 区、预览 iframe 在舞台里、检查器原生、旧 board.js 不再加载", ok and shape["ids"] and shape["skip"] == "bd-stage" and shape["frame"] and shape["stage"] and shape["ins"] and not shape["script"], json.dumps(shape, ensure_ascii=False)))
    results.append(("进页：翻页条读数来自预览版面，没有旧类名", wait(page, "() => /预计 \\d+ 页/.test(document.querySelector('.brd-est')?.textContent || '')") and shape["legacy"] == 0, shape["est"]))

    item(page, "E2E 甲").locator(".brd-item__main").click()
    ok = wait(page, f"() => ({TITLE})() === 'E2E 甲' && boardPreviewIsReady() && boardPreviewLayout()?.board_id === {json.dumps(first)}", 15000)
    current = page.evaluate("() => document.querySelector('.brd-item.is-current .brd-item__main')?.getAttribute('aria-current')")
    results.append(("左栏：点板切换，状态条、当前行与预览一起换", ok and current == "true" and "4 题" in page.inner_text(".brd-sub"), page.inner_text(".brd-sub")))

    page.evaluate("() => { window.__frame = boardPreviewFrame(); boardPreviewFrame().contentWindow.__keep = 1; }")
    keep = "() => boardPreviewFrame() === window.__frame && boardPreviewFrame().contentWindow.__keep === 1 && boardPreviewFrame().parentNode.id === 'bd-stage'"
    page.locator(f".brd-folder[data-board-folder-drag='{folder}'] .brd-fold").click()
    folded = wait(page, "() => !document.querySelector('.brd-item [data-board-select]') || ![...document.querySelectorAll('.brd-item__name')].some(n => n.textContent === 'E2E 甲')")
    stored = page.evaluate("() => localStorage.getItem('omrs-board-folders-collapsed') || ''")
    expanded = page.locator(f".brd-folder[data-board-folder-drag='{folder}'] .brd-fold").get_attribute("aria-expanded")
    page.locator(f".brd-folder[data-board-folder-drag='{folder}'] .brd-fold").click()
    unfolded = wait(page, "() => [...document.querySelectorAll('.brd-item__name')].some(n => n.textContent === 'E2E 甲')")
    results.append(("左栏：折叠 / 展开文件夹，折叠状态存本地，aria-expanded 跟着变", folded and unfolded and folder in stored and expanded == "false", stored))

    page.click("[data-board-view='list']")
    listed = wait(page, "() => document.querySelectorAll('#bd-content-body .brd-row').length === 4 && document.getElementById('bd-stage').hidden")
    page.evaluate("() => boardRender()")
    page.click("[data-board-view='paper']")
    shown = wait(page, "() => !document.getElementById('bd-stage').hidden && !document.querySelector('#bd-content-body .brd-row')")
    results.append(("舞台：折叠、重绘、切列表再切回纸面，预览 iframe 没挪、没重载", listed and shown and page.evaluate(keep), ""))

    page.click("[data-board-view='list']")
    wait(page, "() => document.querySelectorAll('#bd-content-body .brd-row').length === 4")
    page.click(".brd-note")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    sel = "() => document.querySelector('.brd-row[aria-current=\"true\"]')?.dataset.boardRow || ''"
    second_uid = uids[1]
    selected = wait(page, f"() => ({sel})() === {json.dumps(second_uid)}")
    page.keyboard.press("Control+ArrowDown")
    moved = poll(lambda: order(port, first)[2] == second_uid)
    results.append(("快捷键：↓↓ 选到第二行，Ctrl+↓ 换位并落盘", selected and moved, json.dumps(order(port, first), ensure_ascii=False)))

    wait(page, f"() => ({sel})() === {json.dumps(second_uid)}")
    page.keyboard.press("Enter")
    opened = wait(page, "() => !!document.querySelector('dialog[open]:not(.is-closing) .qv, dialog[open]:not(.is-closing) [data-qv]') || !!document.querySelector('dialog[open]:not(.is-closing)')")
    page.keyboard.press("Escape")
    closed = wait(page, "() => !document.querySelector('dialog[open]:not(.is-closing)')")
    results.append(("快捷键：Enter 打开选中的题，Esc 关掉", opened and closed, ""))

    page.click(".brd-note")
    page.keyboard.press("ArrowDown")
    wait(page, f"() => !!({sel})()")
    victim = page.evaluate(sel)
    page.keyboard.press("Delete")
    removed = poll(lambda: victim not in order(port, first))
    toast = wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('已移除'))")
    page.locator(".ui-toast", has_text="已移除").get_by_role("button", name="撤销").click()
    back = poll(lambda: victim in order(port, first))
    results.append(("快捷键：Delete 移除选中的题，toast 撤销后回来", bool(victim) and removed and toast and back, victim))
    page.click("[data-board-view='paper']")

    page.dblclick(".brd-title")
    editing = wait(page, "() => document.activeElement?.matches('[data-board-rename]') && document.activeElement.value === 'E2E 甲'")
    page.keyboard.press("Escape")
    cancelled = wait(page, f"() => ({TITLE})() === 'E2E 甲' && !document.querySelector('[data-board-rename]')")
    page.dblclick(".brd-title")
    wait(page, "() => document.activeElement?.matches('[data-board-rename]')")
    page.keyboard.press("Control+a")
    page.keyboard.type("E2E 甲·改")
    page.keyboard.press("Enter")
    saved = poll(lambda: board(port, first)["name"] == "E2E 甲·改")
    results.append(("状态条就地改名：双击进入、Esc 取消、Enter 保存（服务端与左栏同步）", editing and cancelled and saved
                    and wait(page, f"() => ({TITLE})() === 'E2E 甲·改' && [...document.querySelectorAll('.brd-item__name')].some(n => n.textContent === 'E2E 甲·改')"), ""))

    page.click("[data-action='board.newMenu']")
    page.locator(".ui-menu__item", has_text="新建展示板").click()
    wait(page, DIALOG)
    page.keyboard.type("E2E 丙")
    page.keyboard.press("Enter")
    created = wait(page, f"() => ({TITLE})() === 'E2E 丙'", 10000) and "E2E 丙" in boards(port)
    results.append(("「＋ 新建」菜单 → 新建展示板：对话框、新板成为当前板", created, ""))

    third = boards(port)["E2E 丙"]["id"]
    item(page, "E2E 丙").locator(".brd-menu-btn").click()
    labels = page.locator(".ui-menu__item").all_inner_texts()
    page.locator(".ui-menu__item", has_text="移到「高三复习」").click()
    moved = poll(lambda: boards(port)["E2E 丙"].get("folder_id") == folder)
    results.append(("板 ⋯ 菜单：条目齐全，移到文件夹", moved and {"重命名", "备注…", "复制", "导出 HTML", "删除"} <= set(t.strip() for t in labels), json.dumps(labels, ensure_ascii=False)))

    page.locator(f".brd-folder[data-board-folder-drag='{folder}'] .brd-menu-btn").click()
    disabled = page.locator(".ui-menu__item[aria-disabled='true']").all_inner_texts()
    page.locator(".ui-menu__item", has_text="重命名").click()
    wait(page, DIALOG)
    page.keyboard.press("Control+a")
    page.keyboard.type("高三冲刺")
    page.keyboard.press("Enter")
    renamed = poll(lambda: any(f["name"] == "高三冲刺" for f in http(port, "/api/boards")["folders"]))
    results.append(("文件夹 ⋯ 菜单：只有一个文件夹时上移 / 下移禁用；重命名", renamed and sorted(t.strip() for t in disabled) == ["上移", "下移"]
                    and wait(page, "() => [...document.querySelectorAll('.brd-folder__name')].some(n => n.textContent === '高三冲刺')"), json.dumps(disabled, ensure_ascii=False)))

    page.click(".brd-note")
    page.keyboard.press("n")
    dialog = wait(page, DIALOG)
    page.keyboard.press("a")    # 对话框开着：字母进输入框，不触发「添加题目」
    typed = page.evaluate("() => document.querySelector('dialog[open] input')?.value") == "a"
    page.keyboard.press("Escape")
    wait(page, "() => !document.querySelector('dialog[open]')")
    page.click(".brd-note")
    page.keyboard.press("a")
    add = wait(page, "() => !!document.querySelector('dialog#bd-add-dialog[open]:not(.is-closing)')")
    page.keyboard.press("Escape")      # 第 6 轮起「添加题目」是 ui/dialog：Esc 关得掉（原 .modal-overlay 弹层关不掉）
    esc = wait(page, "() => !document.querySelector('dialog#bd-add-dialog')")
    results.append(("快捷键：N 弹新建（对话框里按 A 只是输入），A 打开添加题目，Esc 关掉", dialog and typed and add and esc and "a" not in boards(port), ""))

    src = item(page, "E2E 乙")
    dst = page.locator(f".brd-folder[data-board-folder-drag='{folder}']")
    src.drag_to(dst)
    dropped = poll(lambda: boards(port)["E2E 乙"].get("folder_id") == folder)
    results.append(("左栏拖放：把板拖进文件夹", dropped, str(boards(port)["E2E 乙"].get("folder_id"))))

    page.evaluate("() => boardApplyPrintField('note_ratio', 44)")
    page.click("a.tab[data-tab='dashboard']")
    flushed = poll(lambda: abs(board(port, third)["print"]["note_ratio"] - .44) < 1e-6)
    results.append(("离开展示板页：待保存的版面改动立即落盘", flushed, str(board(port, third)["print"]["note_ratio"])))

    page.goto(f"{base}/#/board")
    wait(page, READY, 15000)
    item(page, "E2E 丙").locator(".brd-menu-btn").click()
    page.locator(".ui-menu__item", has_text="删除").click()
    wait(page, DIALOG)
    page.locator("dialog[open] [data-dialog-ok]").click()
    gone = poll(lambda: "E2E 丙" not in boards(port))
    results.append(("板 ⋯ 菜单删除：确认后删掉，当前板落到别的板上", gone and wait(page, f"() => !!({TITLE})() && ({TITLE})() !== 'E2E 丙'"), ""))


def ev(page, expression, arg=None):
    return page.evaluate(expression, arg)


def add_dialog_pick(page, count, gallery_roundtrip=False):
    """在「添加题目」对话框里勾前 count 个可选的题；可选地切到画廊再切回，确认勾选不丢。返回勾选的 uid。"""
    page.click(".brd-note")
    page.keyboard.press("a")
    wait(page, "() => !!document.querySelector('dialog#bd-add-dialog[open]:not(.is-closing) [data-bdadd-uid]')")
    boxes = page.locator("dialog#bd-add-dialog [data-bdadd-uid]:not(:disabled)")
    picked = []
    for i in range(count):
        box = boxes.nth(i)
        picked.append(box.get_attribute("data-bdadd-uid"))
        box.check()
    kept = True
    if gallery_roundtrip:
        page.click("dialog#bd-add-dialog [data-bdadd-view='gallery']")
        kept = wait(page, f"() => document.querySelectorAll('dialog#bd-add-dialog .brd-gcard [data-bdadd-uid]:checked:not(:disabled)').length === {count}")
        page.click("dialog#bd-add-dialog [data-bdadd-view='list']")
        kept = kept and wait(page, f"() => document.querySelectorAll('dialog#bd-add-dialog .brd-add__row [data-bdadd-uid]:checked:not(:disabled)').length === {count}")
    counted = f"已选 {count} 题" in page.inner_text("dialog#bd-add-dialog [data-bdadd-count]")
    page.click("dialog#bd-add-dialog .ui-dialog__foot [data-dialog-ok]")
    closed = wait(page, "() => !document.querySelector('dialog#bd-add-dialog')")
    return picked, kept and counted and closed


def run_detail(page, base, port, ids, results):
    """第 6 轮：在空板「E2E 乙」上走「加题 → 排序 → 版面设置 → 打印预览 → 仅补印新增」，顺带检查器、列表与画廊。"""
    page.goto(f"{base}/#/board")
    wait(page, READY, 15000)
    second = boards(port)["E2E 乙"]["id"]
    item(page, "E2E 乙").locator(".brd-item__main").click()
    wait(page, f"() => ({TITLE})() === 'E2E 乙'")
    page.click("[data-board-view='list']")
    blank = wait(page, "() => !!document.querySelector('#bd-content-body .ui-empty [data-action=\"board.add\"]')")
    none = wait(page, "() => document.querySelector('#bd-inspector .brd-sec[data-sec=\"item\"] .brd-ins-empty') !== null")
    results.append(("空板：列表视图给空态与「添加题目」，检查器提示先点一道题", blank and none, ""))

    picked, ok = add_dialog_pick(page, 3, gallery_roundtrip=True)
    saved = poll(lambda: order(port, second) == picked)
    rows = wait(page, "() => document.querySelectorAll('#bd-content-body .brd-row').length === 3")
    results.append(("添加题目：勾 3 题，切画廊再切回勾选不丢，加入后落盘、列表 3 行", ok and saved and rows, json.dumps(order(port, second), ensure_ascii=False)))

    page.locator("#bd-content-body .brd-row").nth(0).locator(".brd-row__meta").click()
    first_sel = wait(page, f"() => document.querySelector('.brd-row[aria-current=\"true\"]')?.dataset.boardRow === {json.dumps(picked[0])}"
                          " && /第 1 题/.test(document.querySelector('#bd-inspector .brd-insq')?.textContent || '')")
    page.locator(f"#bd-content-body .brd-row[data-board-row='{picked[1]}'] .brd-gapchip").click()
    focused = wait(page, f"() => document.activeElement?.id === 'bd-ins-gap' && document.activeElement.dataset.boardInspectGap === {json.dumps(picked[1])}")
    page.keyboard.type("5")
    gap_saved = poll(lambda: board(port, second)["items"][1].get("gap_lines") == 5)
    echo = wait(page, f"() => document.querySelector(`.brd-row[data-board-row=\"{picked[1]}\"] .brd-gapchip`)?.textContent.trim() === '留白 5 行'"
                      " && document.activeElement?.id === 'bd-ins-gap'")
    results.append(("检查器：点行选中；行上「留白」把焦点送进检查器，改单题留白后落盘、行上回显跟着变、焦点不丢", first_sel and focused and gap_saved and echo, str(board(port, second)["items"][1].get("gap_lines"))))

    page.click("[data-action='board.sortMenu']")
    page.locator(".ui-menu__item", has_text="反转顺序").click()
    reversed_ok = poll(lambda: order(port, second) == list(reversed(picked)))
    shown = wait(page, f"() => document.querySelector('#bd-content-body .brd-row')?.dataset.boardRow === {json.dumps(picked[2])}")
    results.append(("排序菜单：反转顺序落盘，列表跟着变", reversed_ok and shown, json.dumps(order(port, second), ensure_ascii=False)))

    page.click("[data-board-view='paper']")
    wait(page, f"() => boardPreviewIsReady() && boardPreviewLayout()?.board_id === {json.dumps(second)}", 15000)
    page.locator('[data-board-seg="answers"] [data-value="append"]').click()
    answers = poll(lambda: board(port, second)["print"].get("answers") == "append") and wait(page, "() => boardPreviewLayout()?.answer_pages?.length >= 1", 15000)
    pressed = page.get_attribute('[data-board-seg="answers"] [data-value="append"]', "aria-pressed") == "true"
    page.locator('[data-board-seg="answers"] [data-value="none"]').click()
    poll(lambda: board(port, second)["print"].get("answers") == "none")
    ev(page, "() => { const r = document.querySelector('#bd-ins-ratio'); r.focus(); r.value = 40; r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true })); }")
    readout = wait(page, "() => document.querySelector('[data-board-ratio-value]')?.textContent === '40%' && document.activeElement?.id === 'bd-ins-ratio'")
    ratio = poll(lambda: abs(board(port, second)["print"].get("note_ratio", 0) - .4) < 1e-6)
    relaid = wait(page, "() => Math.abs((boardPreviewLayout()?.print?.note_ratio || 0) - .4) < 1e-6", 15000)
    results.append(("版面设置：答案分段写入并重排预览；滑杆拖动时读数跟着变、焦点留在滑杆上、落盘后预览按新比例", answers and pressed and readout and ratio and relaid,
                    json.dumps(board(port, second)["print"], ensure_ascii=False)))

    page.click("[data-board-view='gallery']")
    cards = wait(page, "() => document.querySelectorAll('#bd-content-body .brd-gcard').length === 3")
    hydrated = wait(page, "() => [...document.querySelectorAll('#bd-content-body .brd-gcard__preview[data-qv-host]')].every(e => e.children.length && !e.querySelector('.qv-loading'))", 15000)
    page.locator("#bd-content-body .brd-gcard").nth(1).locator(".brd-gcard__foot").click()
    card_sel = wait(page, f"() => document.querySelector('.brd-gcard[aria-current=\"true\"]')?.dataset.boardRow === {json.dumps(picked[1])}")
    page.locator("#bd-content-body .brd-gcard").nth(1).locator("[data-action='board.locate']").click()
    located = wait(page, "() => !document.getElementById('bd-stage').hidden && !document.querySelector('#bd-content-body .brd-gcard')")
    results.append(("画廊：3 张卡题面由 qview 填好；点卡选中；「回到纸面」切回纸面视图", cards and hydrated and card_sel and located, ""))

    wait(page, f"() => boardPreviewIsReady() && boardPreviewLayout()?.board_id === {json.dumps(second)}", 15000)
    ev(page, "() => configureBoardDetail({ confirm: async () => true })")
    with page.expect_popup() as opened:
        page.locator("[data-board-primary]").click()
    popup = opened.value
    popup.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'", timeout=20000)
    awaiting = wait(page, "() => document.querySelector('[data-board-primary]')?.dataset.arg === 'mark-printed'")
    page.locator("[data-board-primary]").click()
    recorded = poll(lambda: board(port, second).get("printed_summary", {}).get("pages", 0) > 0, tries=80)
    popup.close()
    results.append(("打印预览：主按钮开打印窗口，随后翻成「记录纸面」，点它写入纸面记录", awaiting and recorded, json.dumps(board(port, second).get("printed_summary"), ensure_ascii=False)))

    extra, ok = add_dialog_pick(page, 1)
    added = poll(lambda: extra[0] in order(port, second))
    new_ready = wait(page, "() => !document.querySelector('[data-board-mode=\"new\"]')?.disabled")
    page.locator('[data-board-mode="new"]').click()
    primary = wait(page, "() => /补印新增 1 题/.test(document.querySelector('[data-board-primary]')?.textContent || '')")
    scoped = wait(page, "() => boardPreviewLayout()?.mode === 'new'", 20000)
    results.append(("仅补印新增：再加 1 题后「仅新增（1）」可选，主按钮「补印新增 1 题」，预览按仅新增排版", ok and added and new_ready and primary and scoped,
                    page.inner_text("[data-board-primary]")))

    page.click("[data-board-view='list']")
    flags = wait(page, f"() => document.querySelector(`.brd-row[data-board-row=\"{extra[0]}\"] .brd-flag[data-tone=\"new\"]`)?.textContent === '新增'"
                       f" && /已印/.test(document.querySelector(`.brd-row[data-board-row=\"{picked[0]}\"] .brd-flag[data-tone=\"paper\"]`)?.textContent || '')")
    results.append(("列表：纸面状态标（已印 / 新增）与纸面记录一致", flags, ""))


def audit(page, base, tag, results, view="paper"):
    page.goto(f"{base}/#/board")
    wait(page, READY, 15000)
    if view != "paper":
        page.click(f"[data-board-view='{view}']")
        wait(page, "() => document.querySelectorAll('#bd-content-body .brd-row').length > 0")
    wait(page, "() => /预计 \\d+ 页/.test(document.querySelector('.brd-est')?.textContent || '')")
    data = page.evaluate(AUDIT)
    ok = data and data["min"] >= 12 and not data["small"] and not data["inline"] and not data["overflow"] and data["legacy"] == 0
    results.append((f"{tag}：字号 ≥12、可点目标达标、无 style=、无横向溢出、无旧类名", ok, json.dumps(data, ensure_ascii=False)))
    if view != "paper":
        page.click("[data-board-view='paper']")   # 视图存本地：审计完放回纸面
    return data and data["bg"]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
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
            browser = launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            guarded(results, "主路径", run_main, page, base, port, ids, results)
            guarded(results, "加题到补印", run_detail, page, base, port, ids, results)
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
                    guarded(results, f"{tag} · 列表", audit, c.new_page(), base, f"{tag} · 列表", results, "list")
                    c.close()
            results.append(("深浅色：状态条底色随主题变化", colors.get(("light", "桌面")) and colors.get(("light", "桌面")) != colors.get(("dark", "桌面")), json.dumps({f"{k[0]}-{k[1]}": v for k, v in colors.items()})))
            if not os.environ.get("OMRS_TEST_CDP_URL"):
                browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"（{detail}）"))
    print(f"E2E board：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
