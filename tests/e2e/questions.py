"""P5 E2E：题库页 features/questions 主路径 + 共享题目视图 domain/question 与题目弹窗。

    python3 tests/e2e/questions.py        # 全部通过退出码 0；没有 playwright 退出码 2

自建 fixture Vault 与隔离实例，不碰真实数据；认 OMRS_TEST_CDP_URL。覆盖：
- 题库主路径：搜索（/ 聚焦、Esc 清空）→ 筛选抽屉（F、科目下拉、标记、双滑块键盘拖动、分段按钮）→ 条件 chips 逐条撤销 →
  计数条快捷筛选 → 排序 → 切换视图（V）→ 列设置 → 键盘游标（↑↓ / 空格勾选 / Enter 打开详情）→ 翻页 → 行内「⋯」菜单打标记 →
  批量打标记（当场新建）→ 批量停用 → 视图预设存取 → 旧入口预设（仪表盘跳转、「在题目库打开」）；
- 题目弹窗（ui/dialog）：点行打开（模态、焦点陷阱、桌面双栏）→ ←/→ 翻页 → Esc 关闭、焦点回到行；挂载点 < 680px 单栏；
  超宽公式块内横滚；题图缺失降级；弹窗上叠标记选择器 / 选板浮层（进对话框、可操作、Esc / 点外面只关浮层）；
  Markdown 编辑器（第二个模态对话框：未保存时 Esc 不关、Ctrl+Enter 保存写回文件、焦点回到「编辑」）；
- 画廊缩略卡：截断走 data-clamp、不写行内样式、详情到齐后脚注换成战绩带；
- 手机：表格降级为卡片列表（D4）、可点目标 ≥40、弹窗单栏、无横向滚动；
- 审计：桌面 / 手机 × 浅 / 深 × 表格 / 抽屉 / 画廊，字号 ≤6、小目标 0、无横向溢出；题目弹窗打开状态小目标 0（手机 40）、
  无横向溢出、不写行内样式；全程脚本错误为 0。
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
ROWS = "() => [...document.querySelectorAll('#panel-questions tr[data-q-row]')].map(r => r.dataset.qRow)"
AUDIT = """() => {
  const root = document.getElementById('panel-questions');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('[data-qv-host]'));
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))];
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button'
    || (e.tagName === 'A' && e.hasAttribute('href')) || e.hasAttribute('onclick') || e.hasAttribute('data-action');
  const small = shown.filter(hit).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < 28; }).map(e => e.className);
  return { sizes: sizes.length, list: sizes, small, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""
OPEN = "uid => document.querySelector('dialog#modal[open] #modal-stage [data-qv-uid]')?.dataset.qvUid === uid"
CLOSED = "() => !document.querySelector('dialog#modal')"
DIALOG_AUDIT = """() => {
  const d = document.getElementById('modal');
  if (!d) return null;
  const shown = [...d.querySelectorAll('*')].filter(e => e.getClientRects().length && !e.closest('.katex'));
  const txt = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(txt).map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a, b) => a - b);
  const min = innerWidth <= 760 ? 40 : 28;
  const hit = e => e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button' || (e.tagName === 'A' && e.hasAttribute('href'));
  const small = shown.filter(hit).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height < min - 0.5; }).map(e => e.className || e.tagName);
  const inline = shown.filter(e => e.hasAttribute('style')).map(e => e.className || e.tagName);
  const panel = d.querySelector('.ui-dialog__panel').getBoundingClientRect();
  return { sizes: sizes.length, list: sizes, small, inline, overflow: document.documentElement.scrollWidth > innerWidth + 1 || panel.right > innerWidth + 1 };
}"""
COLS = "sel => { const el = document.querySelector(sel); return el ? getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean).length : 0; }"
WIDE = "$$" + " + ".join(f"\\frac{{a_{{{i}}}^2+b_{{{i}}}^2}}{{c_{{{i}}}}}" for i in range(1, 26)) + "$$"
PROBE = """async ([uid, question]) => {
  const mount = await import('/assets/app/domain/question/mount.js');
  mount.detailCacheObject()[uid] = { uid, subject: '数学', category: '测试', difficulty: 5, question, answer: '答案', notes: '', records: [] };
  let box = document.getElementById('qv-probe');
  if (!box) { box = document.createElement('div'); box.id = 'qv-probe'; document.body.appendChild(box); }
  box.style.width = '420px';
  return mount.qvRender(box, uid, { layout: 'split', showHistory: false }).then(() => true);
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


def http(port, path):
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10))


def guarded(results, name, fn, *args):
    """某一段中途抛错时记一条失败并继续后面的段落。"""
    try:
        return fn(*args)
    except Exception as error:  # noqa: BLE001 — E2E 汇总用
        results.append((f"{name}：中途出错", False, str(error).splitlines()[0][:200]))
        return None


def run_modal(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.goto(f"{base}/#/questions")
    check("题库表格就绪", wait(page, READY, 15000))
    first = page.locator("#panel-questions tr[data-q-row]").first
    uid = first.get_attribute("data-q-row")
    first.locator("td").nth(1).click()
    check("点行打开题目弹窗（ui/dialog，模态）", wait(page, OPEN, arg=uid) and page.evaluate("() => document.getElementById('modal').matches(':modal')"))
    check("初始焦点在题面区，背景拿不到焦点（焦点陷阱）", page.evaluate("""() => { const start = document.activeElement?.id;
      document.getElementById('qlb-search').focus(); return start === 'modal-stage' && document.getElementById('modal').contains(document.activeElement); }"""))
    check("挂载点带 data-qv-mount", page.evaluate("() => document.getElementById('modal-stage').dataset.qvMount === '1'"))
    cols = page.evaluate(COLS, "#modal-stage .qv-split")
    check("桌面弹窗：题面 | 答案双栏", cols == 2, f"列数 {cols}")
    check("翻页位置显示", wait(page, "() => /第 1 \\/ \\d+ 题/.test(document.getElementById('qv-nav-pos').textContent)"))
    page.keyboard.press("ArrowRight")
    check("→ 翻到下一题", wait(page, "() => document.getElementById('qv-nav-pos').textContent.startsWith('第 2 /')"))
    moved = wait(page, "uid => { const cur = document.querySelector('#modal-stage [data-qv-uid]')?.dataset.qvUid; return cur && cur !== uid; }", arg=uid)
    second = page.evaluate("() => document.querySelector('#modal-stage [data-qv-uid]')?.dataset.qvUid")
    check("→ 之后题面换成第二题", moved, f"{uid} → {second}")
    page.keyboard.press("ArrowLeft")
    check("← 翻回第一题", wait(page, "uid => document.querySelector('#modal-stage [data-qv-uid]')?.dataset.qvUid === uid", arg=uid))
    page.keyboard.press("Escape")
    check("Esc 关闭弹窗", wait(page, CLOSED))
    check("关闭后焦点回到被点的行", wait(page, "uid => document.activeElement?.dataset?.qRow === uid", arg=uid))
    return uid


def run_container(page, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    ok = page.evaluate(PROBE, ["__qv_wide", "前言。\n" + WIDE + "\n结论。![[不存在的图.png|300]]"])
    check("420px 挂载点渲染完成", ok and wait(page, "() => document.querySelector('#qv-probe [data-qv-uid]')"))
    cols = page.evaluate(COLS, "#qv-probe .qv-split")
    check("挂载点 < 680px：题面塌成单栏", cols == 1, f"列数 {cols}")
    wide = page.evaluate("""() => { const box = document.getElementById('qv-probe'); const k = box.querySelector('.katex-display');
      return { box: box.scrollWidth - box.clientWidth, formula: k ? k.scrollWidth - k.clientWidth : -1, scroll: k ? getComputedStyle(k).overflowX : '' }; }""")
    check("超宽公式在自己的块里横滚", wide["formula"] > 0 and wide["scroll"] == "auto", json.dumps(wide))
    check("挂载点本身不被撑宽", wide["box"] <= 1, json.dumps(wide))
    check("题图缺失降级为文件名提示", wait(page, "() => document.querySelector('#qv-probe .md-img-missing')?.textContent.includes('不存在的图.png')"))
    page.evaluate("() => { const b = document.getElementById('qv-probe'); b.style.width = '900px'; }")
    check("挂载点放宽到 900px：恢复双栏", wait(page, "() => getComputedStyle(document.querySelector('#qv-probe .qv-split')).gridTemplateColumns.split(' ').length === 2"))
    page.evaluate("() => document.getElementById('qv-probe')?.remove()")


def run_gallery(page, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.click("[data-action='questions.view'][data-arg='gallery']")
    check("画廊缩略卡题面就绪", wait(page, "() => document.querySelector('.qlb-gcard__preview .qv-clamp .q-md[data-clamp]')", 10000))
    inline = page.evaluate("() => document.querySelectorAll('.qlb-gcard [style]:not(.katex *), .q-streak i[style]').length")
    check("缩略卡与战绩带不写行内样式（KaTeX 输出与标记芯片颜色变量除外，后者第 3 轮随 domain/labels 去掉）", inline == 0, f"{inline} 处")
    clamp = page.evaluate("() => getComputedStyle(document.querySelector('.qlb-gcard__preview .q-md[data-clamp]')).webkitLineClamp")
    check("截断行数由 data-clamp 生效", clamp not in ("", "none"), clamp)
    check("详情到齐后脚注换成战绩带（不额外请求）", wait(page, "() => document.querySelectorAll('.qlb-gcard .qlb-streak .q-streak').length > 0", 8000))
    page.keyboard.press("v")
    check("V 切回表格", wait(page, "() => document.querySelector('#panel-questions .qlb-table') && !document.querySelector('.qlb-gallery')"))


def run_mobile(browser, base, uid, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/#/questions", wait_until="networkidle")
    wait(page, READY, 15000)
    cards = page.evaluate("""() => { const row = document.querySelector('#panel-questions tr[data-q-row]'); const r = row.getBoundingClientRect();
      const heads = getComputedStyle(document.querySelector('.qlb-table thead')).position;
      const small = [...document.querySelectorAll('#panel-questions button, #panel-questions select, .qlb-check')].filter(e => e.offsetParent)
        .filter(e => e.getBoundingClientRect().height < 40).map(e => e.className);
      return { display: getComputedStyle(row).display, width: r.width, heads, small, label: getComputedStyle(row.querySelector('td[data-col="mastery"]'), '::before').content }; }""")
    check("手机：表格降级为卡片列表（D4），每格带小标题", cards["display"] == "grid" and cards["heads"] == "absolute" and "熟练度" in cards["label"], json.dumps(cards, ensure_ascii=False))
    check("手机：可点目标都 ≥40px", not cards["small"], ", ".join(cards["small"][:4]))
    ph = page.evaluate("() => { const i = document.getElementById('qlb-search'); return i.scrollWidth <= i.clientWidth + 1 && i.clientWidth > 200; }")
    check("手机：搜索框占满一行，提示文字不截断", ph)
    page.evaluate("uid => viewQ(uid, 'q')", uid)
    check("手机：弹窗打开", wait(page, "() => document.querySelector('dialog#modal[open] #modal-stage [data-qv-uid]')"))
    page.wait_for_timeout(400)   # 面板入场动画（scale .98）结束后再量尺寸
    head = page.evaluate("() => [...document.querySelectorAll('#modal .qv-dialog__head button')].filter(b => b.getClientRects().length).map(b => { const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })")
    check("手机：弹窗翻页与关闭按钮 ≥40×40", head and all(w >= 40 and h >= 40 for w, h in head), json.dumps(head))
    cols = page.evaluate(COLS, "#modal-stage .qv-split")
    check("手机：弹窗题面单栏", cols == 1, f"列数 {cols}")
    over = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
    check("手机：页面无横向滚动", over <= 1, f"{over}px")
    check("手机：页面脚本错误为 0", not errors, "; ".join(errors[:3]))
    ctx.close()


def run_mobile_question_scroll(browser, base, results, viewport):
    """长题详情在窄屏中保持面板边界，并把纵向滚动交给题面区。"""
    width, height = viewport
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(f"{base}/?unlocked=1#/questions", wait_until="networkidle")
        page.wait_for_function("() => window.__p8TestReady", timeout=15000)
        page.evaluate("""async () => { await window.__p8TestReady; await viewQ('三角函数3'); }""")
        opened = wait(page, "() => document.querySelector('dialog#modal[open] #modal-stage [data-qv-uid]')", 10000)
        check(f"手机 {width}×{height}：长题弹窗打开", opened)
        if not opened:
            return
        page.wait_for_timeout(400)
        metrics = page.evaluate("""() => {
          const panel = document.querySelector('#modal .ui-dialog__panel');
          const stage = document.getElementById('modal-stage');
          const p = panel.getBoundingClientRect();
          return {
            panelTop: p.top, panelBottom: p.bottom,
            stageClient: stage.clientHeight, stageScroll: stage.scrollHeight,
            overflowY: getComputedStyle(stage).overflowY,
            pageOverflowX: document.documentElement.scrollWidth - innerWidth,
          };
        }""")
        bounded = metrics["panelTop"] >= -1 and metrics["panelBottom"] <= height + 1
        scrollable = metrics["stageScroll"] > metrics["stageClient"] and metrics["overflowY"] in ("auto", "scroll")
        check(f"手机 {width}×{height}：面板在视口内、题面区可滚动", bounded and scrollable, json.dumps(metrics))
        page.locator("#modal-stage").hover()
        page.mouse.wheel(0, max(400, height // 2))
        moved = wait(page, "() => document.getElementById('modal-stage').scrollTop > 0")
        check(f"手机 {width}×{height}：滚动题面区不会滚动背景", moved and page.evaluate("() => document.documentElement.scrollTop === 0"))
        page.evaluate("() => { const s = document.getElementById('modal-stage'); s.scrollTop = s.scrollHeight; }")
        end = page.evaluate("""() => {
          const stage = document.getElementById('modal-stage');
          const last = stage.querySelector('.qv-creation');
          const sr = stage.getBoundingClientRect();
          const lr = last?.getBoundingClientRect();
          return { atEnd: stage.scrollTop + stage.clientHeight >= stage.scrollHeight - 1,
            lastVisible: !!lr && lr.bottom <= sr.bottom + 1,
            pageOverflowX: document.documentElement.scrollWidth - innerWidth };
        }""")
        check(f"手机 {width}×{height}：长题可滚到创建信息末尾", end["atEnd"] and end["lastVisible"] and end["pageOverflowX"] <= 1, json.dumps(end))
        page.keyboard.press("Escape")
        check(f"手机 {width}×{height}：滚动后仍可关闭弹窗", wait(page, CLOSED))
        check(f"手机 {width}×{height}：页面脚本错误为 0", not errors, "; ".join(errors[:3]))
    finally:
        ctx.close()


def run_library(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.goto(f"{base}/?t=lib#/questions")
    wait(page, READY, 15000)
    total = len(page.evaluate(ROWS))
    page.keyboard.press("/")
    check("/ 聚焦搜索框", wait(page, "() => document.activeElement?.id === 'qlb-search'"))
    page.keyboard.type("三角")
    check("搜索即时筛选", wait(page, "() => { const r = [...document.querySelectorAll('#panel-questions tr[data-q-row]')]; return r.length > 0 && r.every(x => x.dataset.qRow.includes('三角')); }"))
    check("搜索条件出现在 chips 里", wait(page, "() => [...document.querySelectorAll('.qlb-chip')].some(c => c.textContent.includes('搜索：三角'))"))
    page.keyboard.press("Escape")
    check("搜索框里 Esc 清空", wait(page, f"() => document.querySelectorAll('#panel-questions tr[data-q-row]').length === {total} && !document.getElementById('qlb-search').value"))
    page.click(".qlb-total")
    page.keyboard.press("f")
    check("F 打开筛选抽屉", wait(page, "() => document.getElementById('qlb-drawer')"))
    subject = page.evaluate("() => [...document.querySelectorAll('#qlb-f-subject option')].map(o => o.value).filter(Boolean)[0]")
    page.select_option("#qlb-f-subject", subject)
    check("科目下拉筛选", wait(page, "s => { const r = [...document.querySelectorAll('#panel-questions tr[data-q-row] .qlb-meta')]; return r.length > 0 && r.every(x => x.textContent.startsWith(s)); }", arg=subject))
    check("筛选按钮徽标显示条件数 1", wait(page, "() => document.querySelector('.qlb-filter-btn .ui-badge')?.textContent.trim() === '1'"))
    page.locator(".qlb-chip", has_text="科目").click()
    check("点 chip 撤销单个条件", wait(page, f"() => document.querySelectorAll('#panel-questions tr[data-q-row]').length === {total} && !document.querySelector('.qlb-filter-btn .ui-badge')"))
    lo = page.locator(".qlb-dual[data-dual='diff'] input").first
    lo.focus()
    for _ in range(4):
        page.keyboard.press("ArrowRight")
    check("双滑块键盘拖动：条件与文案随动", wait(page, "() => [...document.querySelectorAll('.qlb-chip')].some(c => c.textContent.includes('难度 5–10'))"))
    fill = page.evaluate("() => getComputedStyle(document.querySelector('.qlb-dual[data-dual=\"diff\"] .qlb-dual__fill')).left")
    check("双滑块填充条位置由 CSS 变量给出", fill not in ("", "0px"), fill)
    diffs = page.evaluate("() => DATA.items.filter(i => !i.suspended && Number(i.difficulty) >= 5).length")
    check("难度下限生效（命中数一致）", wait(page, f"() => document.querySelectorAll('#panel-questions tr[data-q-row]').length === {diffs}"), str(diffs))
    page.click("[data-action='questions.clearAll'] >> nth=0")
    page.click("[data-action='questions.seg'][data-arg='suspended|all']")
    check("分段按钮：含停用全部", wait(page, f"() => document.querySelectorAll('#panel-questions tr[data-q-row]').length === {total + 1}"))
    page.click("[data-action='questions.seg'][data-arg='suspended|']")
    label = page.evaluate("() => document.querySelector('.qlb-lblf__btn')?.dataset.arg")
    page.click(".qlb-lblf__btn >> nth=0")
    check("标记芯片点亮即筛", wait(page, "n => { const r = [...document.querySelectorAll('#panel-questions tr[data-q-row]')]; return r.length > 0 && r.every(x => x.querySelector(`[data-lbl-name=\"${n}\"]`)); }", arg=label), label)
    page.click(".qlb-lblf__btn >> nth=0")
    page.click("[data-action='questions.drawer'][data-arg='0'] >> nth=0")
    check("关闭抽屉", wait(page, "() => !document.getElementById('qlb-drawer')"))
    page.click("[data-action='questions.quick'][data-arg='suspended']")
    check("计数条快捷筛选：停用", wait(page, "() => document.querySelectorAll('#panel-questions tr[data-q-row]').length === 1"))
    page.click("[data-action='questions.quick'][data-arg='suspended']")
    check("再点一次取消快捷筛选", wait(page, f"() => document.querySelectorAll('#panel-questions tr[data-q-row]').length === {total}"))
    page.select_option("#qlb-sort", "diff-desc")
    order = page.evaluate("() => [...document.querySelectorAll('#panel-questions tr[data-q-row]')].map(r => DATA.items.find(i => i.uid === r.dataset.qRow).difficulty)")
    check("排序：难度 ↓", all(float(a) >= float(b) for a, b in zip(order, order[1:])), str(order[:6]))
    page.click("#qlb-layout-btn")
    page.check("[data-change='questions.column'][data-arg='ef']")
    check("列设置：打开 EF 列并记住", wait(page, "() => document.querySelector('.qlb-table th[data-col=\"ef\"]') && localStorage.getItem('omrs-qb-columns').includes('ef')"))
    page.mouse.click(700, 20)
    check("点浮层外关闭显示设置", wait(page, "() => !document.getElementById('qlb-layout')"))


def run_keyboard(page, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.click(".qlb-total")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    second = page.evaluate("() => document.querySelectorAll('#panel-questions tr[data-q-row]')[1].dataset.qRow")
    check("↓ 移动行游标", wait(page, "u => document.querySelector('#panel-questions tr[data-cursor]')?.dataset.qRow === u", arg=second))
    page.keyboard.press(" ")
    check("空格勾选游标行，批量条出现", wait(page, "() => document.querySelector('.qlb-batch') && document.querySelector('#panel-questions tr[data-cursor]').getAttribute('aria-selected') === 'true'"))
    check("全选框显示半选", page.evaluate("() => document.getElementById('qlb-select-all').indeterminate"))
    page.keyboard.press("Enter")
    check("Enter 打开游标行详情", wait(page, OPEN, arg=second))
    third = page.evaluate("() => document.querySelectorAll('#panel-questions tr[data-q-row]')[2].dataset.qRow")
    page.keyboard.press("ArrowRight")
    check("弹窗翻页沿用题库当前顺序", wait(page, "() => document.getElementById('qv-nav-pos').textContent.startsWith('第 3 /')"))
    page.keyboard.press("Escape")
    wait(page, CLOSED)
    check("Esc 关弹窗时不清勾选", page.evaluate("() => !!document.querySelector('.qlb-batch')"))
    check("关弹窗后游标与焦点落在翻到的那一题", wait(page, "u => document.activeElement?.dataset?.qRow === u && document.querySelector('#panel-questions tr[data-cursor]')?.dataset.qRow === u", arg=third))
    page.locator("#panel-questions tr[data-q-row] .qlb-more").first.click()
    check("行内「⋯」打开 ui/menu", wait(page, "() => document.querySelector('.ui-menu.is-floating')"))
    page.locator(".ui-menu.is-floating [role=menuitem]", has_text="打标记").click()
    check("菜单「打标记」打开标记选择器", wait(page, "() => !!document.querySelector('.label-picker-pop')"))
    page.keyboard.press("Escape")
    check("Esc 先关标记选择器（core/keys 全局键），勾选保留", wait(page, "() => !document.querySelector('.label-picker-pop')") and page.evaluate("() => !!document.querySelector('.qlb-batch')"))
    page.click(".qlb-total")
    page.keyboard.press("Escape")
    check("再按 Esc 清空勾选", wait(page, "() => !document.querySelector('.qlb-batch')"))


def run_batch(page, base, results):
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    rows = page.evaluate(ROWS)
    boxes = page.locator("#panel-questions tr[data-q-row] [data-change='questions.select']")
    boxes.nth(0).check()
    boxes.nth(1).check()
    check("勾选两题", wait(page, "() => document.querySelector('.qlb-batch__count')?.textContent.includes('2')"))
    page.click("[data-action='questions.batchLabels']")
    wait(page, "() => document.querySelector('dialog[open] #qlb-lbl-new')")
    page.fill("#qlb-lbl-new", "E2E批量")
    page.click("dialog[open] [data-dialog-ok]")
    check("批量打标记（当场新建）写回两题", wait(page, "us => us.every(u => DATA.items.find(i => i.uid === u)?.labels?.includes('E2E批量'))", 8000, rows[:2]))
    check("表格芯片随之更新", wait(page, "u => !!document.querySelector(`#panel-questions tr[data-q-row=\"${u}\"] [data-lbl-name=\"E2E批量\"]`)", arg=rows[0]))
    page.click("[data-action='questions.clearSelection']")
    boxes.nth(0).check()
    page.click("[data-action='questions.batchSuspend']")
    page.click("dialog[open] [data-dialog-ok]")
    check("批量停用：该题从活动列表消失、停用计数 +1", wait(page, "u => !document.querySelector(`#panel-questions tr[data-q-row=\"${u}\"]`) && document.querySelector('[data-arg=\"suspended\"] b').textContent === '2'", 8000, rows[0]))
    check("批量停用后清空勾选", wait(page, "() => !document.querySelector('.qlb-batch')"))
    page.click("[data-action='questions.drawer']")
    page.click("[data-action='questions.seg'][data-arg='due|today']")
    page.click("#qlb-drawer [data-action='questions.saveView']")
    wait(page, "() => document.querySelector('dialog[open] input.ui-input')")
    page.fill("dialog[open] input.ui-input", "E2E视图")
    page.click("dialog[open] [data-dialog-ok]")
    check("存为视图", wait(page, "() => [...document.querySelectorAll('.qlb-views__btn')].some(b => b.textContent === 'E2E视图' && b.getAttribute('aria-pressed') === 'true')"))
    page.click("#qlb-drawer [data-action='questions.clearAll']")
    page.click(".qlb-views__btn")
    check("应用视图恢复筛选", wait(page, "() => document.querySelector('[data-arg=\"due|today\"]').getAttribute('aria-pressed') === 'true'"))
    page.click("[data-action='questions.drawer'][data-arg='0'] >> nth=0")
    page.evaluate("() => { window.__omrs.router.go('dashboard'); questionsLoadPreset({'q-filter-suspended': 'suspended'}); }")
    check("仪表盘旧入口预设：切到题库并整体替换条件", wait(page, "u => location.hash === '#/questions' && document.querySelectorAll('#panel-questions tr[data-q-row]').length === 2 && !!document.querySelector(`tr[data-q-row=\"${u}\"]`)", arg=rows[0]))
    page.evaluate("u => questionsLoadPreset({'q-search': u})", rows[1])
    check("「在题目库打开」预设按 UID 搜索", wait(page, "u => { const r = [...document.querySelectorAll('#panel-questions tr[data-q-row]')]; return r.length >= 1 && r[0].dataset.qRow === u; }", arg=rows[1]))
    page.evaluate("() => questionsLoadPreset({})")


def run_layers(page, base, results):
    """题目弹窗上叠的旧浮层放进对话框、可真实操作；Markdown 编辑器是叠上去的第二个 ui/dialog。"""
    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
    page.goto(f"{base}/#/questions", wait_until="networkidle")
    wait(page, READY, 15000)
    uid = page.evaluate("() => [...document.querySelectorAll('#panel-questions tr[data-q-row]')].pop().dataset.qRow")
    page.evaluate("uid => viewQ(uid, 'q')", uid)
    wait(page, OPEN, arg=uid)
    page.click("#modal-stage [data-qv-act='labels']")
    check("弹窗里点「标记」：选择器放进对话框、搜索框拿到焦点", wait(page, "() => !!document.querySelector('.label-picker-pop') && document.getElementById('modal').contains(document.querySelector('.label-picker-pop')) && document.activeElement === document.querySelector('.label-picker-pop .label-picker-search')"))
    page.keyboard.type("弹窗里新建")
    page.keyboard.press("Enter")
    wait(page, "() => [...document.querySelectorAll('.label-picker-pop .label-picker-option.selected')].some(o => o.textContent.includes('弹窗里新建'))")
    page.click(".label-picker-pop [data-lbl-save]")
    check("选择器里新建并保存标记（真实点击，不被 inert）", wait(page, "async uid => ((await import('/assets/app/domain/data.js')).itemsNow().find(i => i.uid === uid)?.labels || []).includes('弹窗里新建')", arg=uid, timeout=8000))
    check("保存后弹窗仍开着，芯片重绘", wait(page, "() => !!document.querySelector('dialog#modal[open] #modal-stage .lbl[data-lbl-name=\"弹窗里新建\"]')"))
    chip = page.evaluate("""() => { const c = document.querySelector('#modal-stage .lbl[data-lbl-name="弹窗里新建"]');
      return c ? { key: c.dataset.lblC || '', css: getComputedStyle(c).getPropertyValue('--lbl-c').trim(), styled: document.querySelectorAll('.lbl[style], .sw[style], .label-swatch[style]').length } : null; }""")
    check("芯片颜色走 data-lbl-c + 运行时样式表，全页芯片不写 style=", bool(chip) and bool(chip["key"]) and chip["css"] == "#" + chip["key"] and chip["styled"] == 0, json.dumps(chip))
    page.click("#modal-stage [data-qv-act='labels']")
    wait(page, "() => !!document.querySelector('.label-picker-pop')")
    page.keyboard.press("Escape")
    check("Esc 只关选择器，弹窗仍在，焦点回到「标记」按钮", wait(page, "() => !document.querySelector('.label-picker-pop') && !!document.querySelector('dialog#modal[open]') && document.activeElement?.matches('[data-qv-act=\"labels\"]')"))
    page.click("#modal-stage [data-qv-act='board']")
    check("弹窗里点「加入展示板」：选板浮层放进对话框", wait(page, "() => !!document.querySelector('.bpicker') && document.getElementById('modal').contains(document.querySelector('.bpicker'))"))
    page.click("#modal-stage .qv-q", position={"x": 4, "y": 4})
    check("点浮层外（对话框内）只关浮层，弹窗仍在", wait(page, "() => !document.querySelector('.bpicker') && !!document.querySelector('dialog#modal[open]')"))
    page.click("#modal-stage [data-qv-act='edit']")
    check("「编辑」打开 Markdown 编辑器：第二个模态对话框，焦点在文本框", wait(page, "() => { const d = document.getElementById('md-editor'); return !!d?.open && d.matches(':modal') && document.activeElement?.id === 'md-edit-text'; }"))
    page.evaluate("""() => { const t = document.getElementById('md-edit-text'); const lines = t.value.split('\\n');
      const i = Math.max(0, lines.findIndex(l => /^#{1,6}\\s/.test(l))); const end = lines.slice(0, i + 1).join('\\n').length; t.setSelectionRange(end, end); }""")
    marker = "E2E 编辑器写回"
    page.keyboard.press("Enter")
    page.keyboard.type(marker)
    check("多行文本里 Enter 是换行，不提交", page.evaluate("m => document.getElementById('md-editor')?.open && document.getElementById('md-edit-text').value.includes('\\n' + m)", marker))
    page.keyboard.press("Escape")
    check("有未保存修改时 Esc 不关编辑器，状态行提示", wait(page, "() => document.getElementById('md-editor')?.open && document.getElementById('md-edit-status')?.dataset.tone === 'warn'"))
    with page.expect_response(lambda r: r.url.endswith("/api/question/markdown") and r.request.method == "POST"):
        page.keyboard.press("Control+Enter")
    check("Ctrl+Enter 保存并关闭编辑器，题目弹窗仍在", wait(page, "() => !document.getElementById('md-editor') && !!document.querySelector('dialog#modal[open]')", timeout=8000))
    md = page.evaluate("uid => fetch('/api/question/raw?uid=' + encodeURIComponent(uid)).then(r => r.json()).then(d => d.markdown || '')", uid)
    check("Markdown 写回了文件", marker in md)
    check("关闭后焦点回到弹窗里（重绘后）的「编辑」按钮", wait(page, "() => document.activeElement?.matches('#modal-stage [data-qv-act=\"edit\"]')"))
    page.keyboard.press("Escape")
    check("再按 Esc 关题目弹窗", wait(page, CLOSED))


def audit_states(page, base, tag, results):
    bad = []
    page.goto(f"{base}/#/questions", wait_until="networkidle")
    wait(page, READY, 15000)
    states = {"表格": page.evaluate(AUDIT)}
    page.locator("#panel-questions tr[data-q-row]").first.locator("td").nth(1).click()
    wait(page, "() => document.querySelector('dialog#modal[open] #modal-stage .qv-q')")
    page.wait_for_timeout(400)
    dlg = page.evaluate(DIALOG_AUDIT)
    page.keyboard.press("Escape")
    wait(page, CLOSED)
    ok = bool(dlg) and not dlg["small"] and not dlg["inline"] and not dlg["overflow"]
    results.append((f"{tag}：题目弹窗打开状态小目标 0、无横向溢出、不写行内样式（字号 {dlg['sizes'] if dlg else '?'} 种）", ok, json.dumps(dlg, ensure_ascii=False)[:300]))
    page.click("[data-action='questions.drawer']")
    wait(page, "() => document.getElementById('qlb-drawer')")
    states["筛选抽屉"] = page.evaluate(AUDIT)
    page.click("[data-action='questions.drawer'][data-arg='0'] >> nth=0")
    page.click("[data-action='questions.view'][data-arg='gallery']")
    wait(page, "() => document.querySelector('.qlb-gcard .qlb-streak .q-streak')", 10000)
    states["画廊"] = page.evaluate(AUDIT)
    page.click("[data-action='questions.view'][data-arg='table']")
    for name, a in states.items():
        if a["sizes"] > 6 or a["small"] or a["overflow"]:
            bad.append(f"{name}:{json.dumps(a, ensure_ascii=False)[:240]}")
    results.append((f"{tag}：表格 / 抽屉 / 画廊字号 ≤6、小目标 0、无横向溢出", not bad, "; ".join(bad[:2])))


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没有安装 playwright")
        return 2
    work = tempfile.mkdtemp(prefix="omrs-e2e-questions-")
    vault = os.path.join(work, "vault")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault],
                   check=True, capture_output=True)
    proc, port = visual.start_server(ROOT, vault, os.path.join(work, "server.log"))
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        http(port, "/api/stats")
        with sync_playwright() as p:
            browser = launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
            page = ctx.new_page()
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            uid = guarded(results, "题目弹窗", run_modal, page, base, results)
            guarded(results, "挂载点容器", run_container, page, results)
            guarded(results, "画廊缩略卡", run_gallery, page, results)
            guarded(results, "题库主路径", run_library, page, base, results)
            guarded(results, "键盘与行内菜单", run_keyboard, page, results)
            guarded(results, "批量与视图预设", run_batch, page, base, results)
            guarded(results, "弹窗上的浮层与编辑器", run_layers, page, base, results)
            results.append(("桌面：页面脚本错误为 0", not errors, "; ".join(errors[:3])))
            ctx.close()
            if uid:
                guarded(results, "手机", run_mobile, browser, base, uid, results)
            for viewport in ((390, 844), (320, 640)):
                guarded(results, f"手机长题滚动 {viewport[0]}×{viewport[1]}", run_mobile_question_scroll, browser, base, results, viewport)
            for theme in ("light", "dark"):
                for label, size in (("桌面", (1440, 900)), ("手机", (390, 844))):
                    c = browser.new_context(viewport={"width": size[0], "height": size[1]})
                    c.add_init_script(path=os.path.join(ROOT, "tests/e2e/p8_test_modules.js"))
                    c.add_init_script(f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}")
                    tag = f"审计 {label} · {'浅色' if theme == 'light' else '深色'}"
                    guarded(results, tag, audit_states, c.new_page(), base, tag, results)
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
    print(f"E2E questions：{len(results) - len(failed)} 通过 / {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
