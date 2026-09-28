"""框选标注页 E2E：/annotate 独立页的上传（选择、粘贴、拖入含非图片）、画框与快捷键、完成跳转、沿用上一张、撤销、
长图拖动自动滚动、缩放、删除、刷新后保留、导出 zip、AI 训练页入口，以及桌面 / 手机 × 浅 / 深四种审计。"""
import io
import os
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'e2e'))
from browser_runtime import launch_chromium  # noqa: E402
from create import AUDIT, guarded, wait  # noqa: E402

AUDIT_PAGE = AUDIT.replace("document.querySelector('#ib-stage-quick')", "document.querySelector('#an-app')")


def png(width, height, shade):
    """用 Pillow 生成指定尺寸的纯色 PNG（每张颜色不同，内容哈希不同）。"""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (width, height), (shade, 255 - shade, 200)).save(buf, 'PNG')
    return buf.getvalue()


def api(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return json.loads(resp.read())


def boxes_of(base, name):
    return next(i for i in api(base, '/api/annotate/images')['images'] if i['file'] == name)


def run(page, base, results):
    def check(name, ok, detail=''):
        results.append((name, bool(ok), detail))

    page.goto(base + '/annotate', wait_until='networkidle')
    check('独立页显示空态与上传入口', wait(page, "() => document.querySelector('.an-empty__title')?.textContent.includes('粘贴')")
          and page.locator('#an-file').count() == 1 and page.locator('#an-folder').count() == 1)
    page.locator('#an-file').set_input_files([
        {'name': 'shot_1.png', 'mimeType': 'image/png', 'buffer': png(400, 1600, 10)},
        {'name': 'shot_2.png', 'mimeType': 'image/png', 'buffer': png(400, 1800, 60)},
        {'name': 'shot_3.png', 'mimeType': 'image/png', 'buffer': png(400, 1000, 110)},
    ])
    check('选择文件上传后进入队列并打开第一张',
          wait(page, "() => document.querySelectorAll('.an-item').length === 3 && document.querySelector('.an-img')?.complete")
          and 'shot_1.png' in page.locator('.an-foot__file').inner_text())

    def draw(x0, y0, x1, y1, shift=False):
        box = page.locator('.an-img').bounding_box()
        page.mouse.move(box['x'] + box['width'] * x0, box['y'] + 300 * y0)
        if shift:
            page.keyboard.down('Shift')
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] * x1, box['y'] + 300 * y1, steps=5)
        page.mouse.up()
        if shift:
            page.keyboard.up('Shift')

    draw(.1, .1, .9, .5)
    page.keyboard.press('a')
    draw(.1, .6, .9, .9)
    check('Q 默认画题目框，按 A 后画答案框',
          wait(page, "() => document.querySelectorAll('.an-box--question').length === 1 && document.querySelectorAll('.an-box--answer').length === 1"))
    draw(.2, .93, .5, 1.0, shift=True)
    check('Shift 拖动画另一种角色', wait(page, "() => document.querySelectorAll('.an-box--question').length === 2"))
    page.keyboard.press('Control+z')
    check('Ctrl+Z 撤销上一个框', wait(page, "() => document.querySelectorAll('.an-box').length === 2"))
    page.keyboard.press('Control+Shift+z')
    page.keyboard.press('Control+z')
    page.keyboard.press('Tab')
    page.keyboard.press('Tab')
    page.keyboard.press('q')
    check('Tab 选中答案框后按 Q 改成题目', wait(page, "() => document.querySelector('.an-box.is-selected.an-box--question') && document.querySelectorAll('.an-box--question').length === 2"))
    page.keyboard.press('a')
    check('再按 A 改回答案', wait(page, "() => document.querySelectorAll('.an-box--answer').length === 1"))
    page.keyboard.press('Escape')
    check('Esc 取消选中', wait(page, "() => !document.querySelector('.an-box.is-selected') && !document.querySelector('.an-handle')"))
    page.keyboard.press('Enter')
    check('Enter 完成并跳到下一张未完成', wait(page, "() => document.querySelector('.an-foot__file')?.textContent === 'shot_2.png'"))
    time.sleep(.6)
    first = boxes_of(base, 'shot_1.png')
    check('完成的图写入服务端：状态 done，一个题目框一个答案框',
          first['status'] == 'done' and sorted(b['role'] for b in first['boxes']) == ['answer', 'question'], str(first))

    page.keyboard.press('c')
    check('C 沿用上一张的框', wait(page, "() => document.querySelectorAll('.an-box').length === 2"))
    page.keyboard.press('Enter')
    check('第二张完成后到第三张', wait(page, "() => document.querySelector('.an-foot__file')?.textContent === 'shot_3.png'"))
    page.keyboard.press('Enter')
    check('没有框时 Enter 不完成并提示', wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('Shift + Enter'))")
          and page.locator('.an-foot__status').inner_text() == '未完成')
    page.keyboard.press('Shift+Enter')
    check('Shift+Enter 标为空白样本并提示全部完成',
          wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('全部图片都已完成'))"))
    page.keyboard.press('ArrowLeft')
    check('← 回到上一张', wait(page, "() => document.querySelector('.an-foot__file')?.textContent === 'shot_2.png'"))
    page.locator('.an-box--answer .an-box__rect').first.click()
    page.keyboard.press('Delete')
    check('点选框后 Delete 删除', wait(page, "() => document.querySelectorAll('.an-box').length === 1"))
    page.keyboard.press('f')
    check('F 整张图一个框', wait(page, "() => document.querySelectorAll('.an-box').length === 2"))
    zoom_before = page.locator('.an-foot__dim').inner_text()
    page.keyboard.press('-')
    check('- 缩小并在状态行显示比例', wait(page, f"() => document.querySelector('.an-foot__dim')?.textContent !== {json.dumps(zoom_before)}"))
    page.keyboard.press('0')

    page.evaluate("""bytes => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], 'image.png', { type: 'image/png' }));
      document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    }""", list(png(300, 3000, 160)))
    check('Ctrl+V 粘贴截图上传', wait(page, "() => document.querySelectorAll('.an-item').length === 4"))
    page.evaluate("""([a, b]) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(a)], 'drop_10.png', { type: 'image/png' }));
      transfer.items.add(new File([new Uint8Array(b)], 'drop_2.png', { type: 'image/png' }));
      transfer.items.add(new File(['x'], 'notes.txt', { type: 'text/plain' }));
      const target = document.querySelector('.an-scroll');
      for (const type of ['dragenter', 'dragover', 'drop']) target.dispatchEvent(new DragEvent(type, { dataTransfer: transfer, bubbles: true, cancelable: true }));
    }""", [list(png(300, 900, 200)), list(png(300, 900, 220))])
    check('拖入画布区：只收图片、按序号自然排序并提示跳过的文件',
          wait(page, "() => document.querySelectorAll('.an-item').length === 6 && [...document.querySelectorAll('.ui-toast')].some(t => t.textContent.includes('跳过 1 个'))")
          and page.locator('.an-item__name').nth(4).inner_text() == 'drop_2.png'
          and not page.evaluate("document.querySelector('#an-app').classList.contains('is-dropping')"))

    page.locator('.an-item', has_text='paste-').first.click()
    wait(page, "() => document.querySelector('.an-foot__file')?.textContent.startsWith('paste-')")
    wait(page, "() => document.querySelector('.an-img')?.complete")
    scroller = page.locator('#an-scroll').bounding_box()
    img = page.locator('.an-img').bounding_box()
    page.mouse.move(img['x'] + 20, img['y'] + 40)
    page.mouse.down()
    page.mouse.move(img['x'] + img['width'] - 20, scroller['y'] + scroller['height'] - 10, steps=5)
    time.sleep(1.0)
    page.mouse.up()
    scrolled = page.evaluate("document.querySelector('#an-scroll').scrollTop")
    height = page.evaluate("(() => { const r = document.querySelector('.an-box__rect'); return r ? r.getBoundingClientRect().height : 0; })()")
    check('长图拖到底边自动滚动，框跟着延伸到可视区外', scrolled > 200 and height > scroller['height'], f'scrollTop={scrolled} h={height}')

    page.keyboard.press('Shift+Delete')
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('Shift+Delete 确认后删除当前图', wait(page, "() => document.querySelectorAll('.an-item').length === 5 && ![...document.querySelectorAll('.an-item__name')].some(n => n.textContent.startsWith('paste-'))"))
    page.keyboard.press('?')
    check('? 打开快捷键表', wait(page, "() => document.querySelector('dialog[open] .an-help__grid')"))
    page.keyboard.press('Escape')
    wait(page, "() => !document.querySelector('dialog[open]')")

    page.locator('[data-action="filter"][data-arg="done"]').click()
    check('已完成筛选只列完成的图', wait(page, "() => document.querySelectorAll('.an-item').length === 3"))
    time.sleep(.6)
    page.reload(wait_until='networkidle')
    check('刷新后进度与框都还在', wait(page, "() => document.querySelector('.an-progress__num')?.textContent.replace(/\\s/g, '') === '3/5'")
          and len(boxes_of(base, 'shot_2.png')['boxes']) == 2)
    page.locator('#an-format').select_option('omrs_jsonl')
    check('导出格式切换更新链接', page.locator('#an-export').get_attribute('href').endswith('format=omrs_jsonl'))
    with urllib.request.urlopen(base + '/api/annotate/export?format=yolo', timeout=20) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    labels = archive.read('labels.jsonl').decode().strip().split('\n')
    check('YOLO 导出只含已完成的 3 张，空白样本有空标签文件',
          len(labels) == 3 and sum(n.startswith('labels/') for n in archive.namelist()) == 3
          and any(archive.read(n) == b'' for n in archive.namelist() if n.startswith('labels/')), str(archive.namelist()))


def run_train(page, base, results):
    page.goto(base + '/#/create', wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="train"]').click()
    ok = wait(page, "() => document.querySelector('#ib-tr-annotate')?.textContent.includes('完成 3 张')")
    link = page.locator('#ib-tr-annotate-open')
    results.append(('AI 训练页有新标签页打开的标注页入口并显示进度',
                    ok and link.get_attribute('href') == '/annotate' and link.get_attribute('target') == '_blank', ''))
    with page.context.expect_page() as popup:
        link.click()
    opened = popup.value
    opened.wait_for_load_state('networkidle')
    results.append(('点击入口在新标签页打开 /annotate', opened.url.endswith('/annotate') and wait(opened, "() => document.querySelectorAll('.an-item').length === 5"), opened.url))
    opened.close()


def main():
    from playwright.sync_api import sync_playwright
    results = []
    with tempfile.TemporaryDirectory(prefix='omrs-annotate-e2e-') as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'omrs_engine.py'), '--vault', vault, 'serve', '--port', str(port)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + '/api/status', timeout=.2).close()
                    break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={'width': 1440, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                guarded(results, '标注页主路径', lambda: run(page, base, results))
                guarded(results, 'AI 训练页入口', lambda: run_train(page, base, results))
                results.append(('页面脚本错误为零', not errors, str(errors[:3])))
                context.close()
                for theme in ('light', 'dark'):
                    for label, viewport, target in (('桌面', (1440, 900), 28), ('手机', (390, 844), 40)):
                        ctx = browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]})
                        ctx.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        audit_page = ctx.new_page()
                        audit_page.goto(base + '/annotate', wait_until='networkidle')
                        wait(audit_page, "() => document.querySelector('.an-img')?.complete && document.querySelector('.an-foot')")
                        audit = audit_page.evaluate(AUDIT_PAGE, target)
                        ok = audit['shown'] >= 40 and len(audit['sizes']) <= 6 and min(audit['sizes']) >= 12 and not any(
                            audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'标注页审计 {label}·{theme}', ok, str(audit)))
                        if os.environ.get('OMRS_SHOTS'):
                            audit_page.screenshot(path=os.path.join(os.environ['OMRS_SHOTS'], f'annotate-{label}-{theme}.png'))
                        ctx.close()
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok or not detail else f'  → {detail}'))
    print(f'\n{len(results) - len(failed)}/{len(results)} 通过')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
