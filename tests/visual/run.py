"""前后截图对比 + 运行时审计：同一份 fixture 分别喂给「基线提交」和「当前工作区」，逐页截图、做像素差分。

    python3 tests/visual/run.py --ref HEAD --out /tmp/omrs-visual        # 前后对比（默认 12 页 × 浅/深 × 桌面/手机）
    python3 tests/visual/run.py --audit-only --out /tmp/omrs-audit       # 只审计当前工作区，不做对比
    python3 tests/visual/run.py --ref HEAD --pages instant,feedback --themes dark --viewports mobile

产物在 --out 目录：report.html（左右对照 + 差异热区 + 每页差异比例 + 审计指标）、shots/、diff/、audit.json。
仓库里不存金标图：基线每次从 --ref 现拍，补丁里没有二进制文件。
稳定性处理：两边用同一份 fixture 副本；页面内冻结 Date；注入样式关闭动效与光标闪烁；等字体就绪后再截。
单次运行约 1–3 分钟，受限模式下放后台并轮询日志（见 AI/environment.md）。
"""
import argparse
import html
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium

PAGES = ["dashboard", "data", "questions", "board", "catalog", "schedule", "instant",
         "feedback", "create", "history", "reports", "settings"]
VIEWPORTS = {"desktop": {"width": 1440, "height": 900}, "mobile": {"width": 390, "height": 844}}
STILL_CSS = "*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}"
DIFF_THRESHOLD = 24  # 单通道差值超过它才算变化，吸收抗锯齿抖动
# 截图时遮住的服务端实时内容（不受页面内冻结 Date 影响）；新增此类元素时在这里登记
MASKS = ["#data-status"]

AUDIT_JS = r"""() => {
  const root = document.querySelector('.panel.active') || document.body;
  const els = [...root.querySelectorAll('*')].filter(e => e.offsetParent || e === root);
  const sizes = new Set(), heights = new Set();
  let inline = 0, small = 0, overflowX = 0;
  for (const e of els) {
    const s = getComputedStyle(e);
    const math = e.closest('.katex');
    if (!math && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) sizes.add(s.fontSize);
    if (!math && (e.getAttribute('style') || '').trim()) inline++;
    const r = e.getBoundingClientRect();
    const clickable = e.tagName === 'BUTTON' || e.tagName === 'SELECT' || e.getAttribute('role') === 'button'
      || (e.tagName === 'A' && e.hasAttribute('href')) || e.hasAttribute('onclick') || e.hasAttribute('data-action');
    if (clickable && r.width && r.height) { heights.add(Math.round(r.height)); if (r.height < 28) small++; }
    if (e.scrollWidth > e.clientWidth + 1 && s.overflowX === 'visible' && r.width) overflowX++;
  }
  const px = [...sizes].map(v => parseFloat(v)).sort((a, b) => a - b);
  return { elements: els.length, font_sizes: px, font_size_count: px.length,
           min_font_px: px.length ? px[0] : null, control_heights: [...heights].sort((a, b) => a - b),
           small_targets: small, inline_styled: inline, visible_overflow_x: overflowX,
           page_overflow_x: document.documentElement.scrollWidth > window.innerWidth + 1 };
}"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(tree, vault, log_path):
    port = free_port()
    log = open(log_path, "w")
    env = dict(os.environ)
    env.pop("OMRS_SYSTEMD_SERVICE", None)
    env["OMRS_AGENT_FAUX_SCRIPT"] = os.path.join(tree, "tests", "fixtures", "agent_faux.json")
    proc = subprocess.Popen([sys.executable, os.path.join(tree, "omrs_engine.py"), "--vault", vault, "serve", "-p", str(port)],
                            cwd=tree, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                if response.status == 200:
                    return proc, port
        except OSError:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"实例没有起来，见 {log_path}")


def prepare_ref(ref, out):
    tree = os.path.join(out, "ref-tree")
    subprocess.run(["git", "-C", ROOT, "worktree", "remove", "--force", tree], capture_output=True)
    shutil.rmtree(tree, ignore_errors=True)
    subprocess.run(["git", "-C", ROOT, "worktree", "add", "--detach", tree, ref], check=True, capture_output=True)
    return tree


def shoot(side, port, args, out, frozen_ms):
    from playwright.sync_api import sync_playwright
    results = {}
    with sync_playwright() as p:
        browser = launch_chromium(p)
        for theme in args.themes:
            for vp in args.viewports:
                ctx = browser.new_context(viewport=VIEWPORTS[vp], device_scale_factor=1)
                ctx.add_init_script(
                    f"try{{localStorage.setItem('omrs-theme','{theme}')}}catch(e){{}}"
                    f";(()=>{{const T={frozen_ms},D=Date;class F extends D{{constructor(...a){{a.length?super(...a):super(T)}}"
                    f"static now(){{return T}}}};window.Date=F}})();")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                page.add_style_tag(content=STILL_CSS)
                for name in args.pages:
                    if name == 'trainpanel':
                        page.goto(f"http://127.0.0.1:{port}/train", wait_until="networkidle")
                    else:
                        if '/train' in page.url:
                            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                        page.evaluate("n => window.__omrs.router.go(n)", name)
                    page.wait_for_load_state("networkidle")
                    if name == "create" and args.create_stage:
                        page.locator(f'#create-flow [data-ib-stage="{args.create_stage}"]').click()
                        page.wait_for_load_state("networkidle")
                    if name == "settings" and args.settings_section:
                        page.locator(f'[data-st-section="{args.settings_section}"]').click()
                        page.wait_for_load_state("networkidle")
                    page.evaluate("document.fonts.ready")
                    page.wait_for_timeout(args.settle)
                    key = f"{name}-{theme}-{vp}"
                    page.screenshot(path=os.path.join(out, "shots", f"{side}-{key}.png"), full_page=True,
                                    mask=[page.locator(sel) for sel in MASKS])
                    results[key] = page.evaluate(AUDIT_JS)
                results[f"_errors-{theme}-{vp}"] = errors
                ctx.close()
        browser.close()
    return results


def diff_images(a_path, b_path, out_path):
    from PIL import Image, ImageChops
    a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
    w, h = max(a.width, b.width), max(a.height, b.height)
    A, B = _pad(a, w, h), _pad(b, w, h)
    dr, dg, db = ImageChops.difference(A, B).split()
    max_delta = ImageChops.lighter(ImageChops.lighter(dr, dg), db)
    threshold_lut = [0 if value <= DIFF_THRESHOLD else 255 for value in range(256)]
    mask = max_delta.point(threshold_lut)
    changed = mask.histogram()[255]
    ratio = changed / (w * h)
    if changed:
        faded = Image.blend(B, Image.new("RGB", (w, h), (255, 255, 255)), 0.65)
        highlighted = Image.composite(Image.new("RGB", (w, h), (230, 30, 60)), faded, mask)
        highlighted.save(out_path)
    return round(ratio * 100, 3), (a.size != b.size)


def _pad(im, w, h):
    from PIL import Image
    if im.size == (w, h):
        return im
    canvas = Image.new("RGB", (w, h), (255, 0, 255))
    canvas.paste(im, (0, 0))
    return canvas


def write_report(out, keys, audit, diffs, audit_only):
    rows = []
    for key in keys:
        cur = audit["cur"].get(key, {})
        ref = audit.get("ref", {}).get(key, {})
        metric = lambda d: (f"字号 {d.get('font_size_count')} 种（最小 {d.get('min_font_px')}px）· 小目标 {d.get('small_targets')} · "
                            f"行内样式 {d.get('inline_styled')}{' · 页面横向溢出' if d.get('page_overflow_x') else ''}") if d else "—"
        cells = []
        if not audit_only:
            ratio, resized = diffs[key]
            cells.append(f"<td class=r>{ratio}%{' · 尺寸变化' if resized else ''}</td>")
            cells.append(f"<td><img src='shots/ref-{key}.png'><div>{html.escape(metric(ref))}</div></td>")
        cells.append(f"<td><img src='shots/cur-{key}.png'><div>{html.escape(metric(cur))}</div></td>")
        if not audit_only:
            cells.append(f"<td>{f'<img src=diff/{key}.png>' if diffs[key][0] else '无差异'}</td>")
        rows.append(f"<tr><th>{key}</th>{''.join(cells)}</tr>")
    head = "<th>页面</th>" + ("" if audit_only else "<th>差异</th><th>基线</th>") + "<th>当前</th>" + ("" if audit_only else "<th>差异热区</th>")
    doc = ("<!doctype html><meta charset=utf-8><title>OMRS 视觉报告</title><style>"
           "body{font:13px system-ui,sans-serif;margin:16px}table{border-collapse:collapse}td,th{border:1px solid #ccc;"
           "padding:6px;vertical-align:top;text-align:left}img{width:420px;display:block;margin-bottom:4px}.r{white-space:nowrap}"
           f"</style><h1>OMRS 视觉{'审计' if audit_only else '对比'}报告</h1><table><tr>{head}</tr>{''.join(rows)}</table>")
    open(os.path.join(out, "report.html"), "w", encoding="utf-8").write(doc)


def seed_process_fixture(vault):
    """框选对比使用同一张合成题图和两个待提取框，不读取真实收件箱。"""
    import io
    from PIL import Image, ImageDraw
    sys.path.insert(0, ROOT)
    from omrs import inbox
    image = Image.new('RGB', (600, 480), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((48, 70), 'Question: f(x) = x^2. Find f(2).', fill='black', font_size=24)
    draw.text((48, 310), 'Answer: f(2) = 4.', fill='black', font_size=24)
    output = io.BytesIO()
    image.save(output, format='PNG')
    item = inbox.upload_images(vault, [('一键提取示例.png', output.getvalue())])['items'][0]
    inbox.update_item(vault, item['id'], {'regions': [
        {'id': 'visual-q', 'role': 'question', 'x': .05, 'y': .05, 'w': .9, 'h': .4, 'convert': 'auto'},
        {'id': 'visual-a', 'role': 'answer', 'x': .05, 'y': .55, 'w': .9, 'h': .4, 'convert': 'auto'},
    ]})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="HEAD", help="基线提交（默认 HEAD）")
    ap.add_argument("--out", default="/tmp/omrs-visual")
    ap.add_argument("--audit-only", action="store_true", help="只拍当前工作区并审计")
    ap.add_argument("--fixture", choices=["full", "empty"], default="full")
    ap.add_argument("--pages", default=",".join(PAGES))
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--viewports", default="desktop,mobile")
    ap.add_argument("--create-stage", choices=["upload", "process", "create", "train", "quick"], help="录入页截图时切到指定工作区")
    ap.add_argument("--settings-section", choices=["appearance", "access", "ai", "assistant", "data", "service"], help="设置页截图时切到指定分区")
    ap.add_argument("--settle", type=int, default=500, help="每页切换后额外等待毫秒数")
    args = ap.parse_args(argv)
    args.pages, args.themes, args.viewports = (v.split(",") for v in (args.pages, args.themes, args.viewports))
    out = os.path.abspath(args.out)
    shutil.rmtree(out, ignore_errors=True)
    for sub in ("shots", "diff", "logs"):
        os.makedirs(os.path.join(out, sub))

    fixture = os.path.join(out, "fixture")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", fixture,
                    "--profile", args.fixture], check=True, stdout=subprocess.DEVNULL)
    if "assistant" in args.pages:
        sys.path.insert(0, ROOT)
        from omrs.common import save_config
        save_config(fixture, {"agent_enabled": True})
    if args.create_stage == "process":
        seed_process_fixture(fixture)
    sides = [("cur", ROOT)]
    if not args.audit_only:
        sides.insert(0, ("ref", prepare_ref(args.ref, out)))
    frozen_ms = int(time.time() * 1000)
    audit, procs = {}, []
    try:
        for side, tree in sides:
            vault = os.path.join(out, f"vault-{side}")
            shutil.copytree(fixture, vault)
            proc, port = start_server(tree, vault, os.path.join(out, "logs", f"{side}.log"))
            procs.append(proc)
            audit[side] = shoot(side, port, args, out, frozen_ms)
            print(f"[{side}] 截图完成", flush=True)
    finally:
        for proc in procs:
            proc.terminate()
        if not args.audit_only:
            subprocess.run(["git", "-C", ROOT, "worktree", "remove", "--force", os.path.join(out, "ref-tree")], capture_output=True)
    keys = [f"{p}-{t}-{v}" for t in args.themes for v in args.viewports for p in args.pages]
    diffs = {}
    if not args.audit_only:
        for key in keys:
            diffs[key] = diff_images(os.path.join(out, "shots", f"ref-{key}.png"), os.path.join(out, "shots", f"cur-{key}.png"),
                                     os.path.join(out, "diff", f"{key}.png"))
    json.dump({"audit": audit, "diffs": diffs}, open(os.path.join(out, "audit.json"), "w"), ensure_ascii=False, indent=1)
    write_report(out, keys, audit, diffs, args.audit_only)
    errors = {k: v for side in audit.values() for k, v in side.items() if k.startswith("_errors") and v}
    changed = sorted(((r, k) for k, (r, _) in diffs.items() if r), reverse=True)
    print(f"报告：{os.path.join(out, 'report.html')}")
    print(f"页面脚本错误：{errors or '无'}")
    if not args.audit_only:
        print(f"有差异 {len(changed)} / {len(keys)}：" + "，".join(f"{k} {r}%" for r, k in changed[:12]))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
