"""审核录入工作台：原图框选、题答自适应双栏、暂存、入库与窄抽屉。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tests/e2e'))
from browser_runtime import launch_chromium, open_app
import drafts as support


def verify_columns(page, base, first, second, shots, check):
    """在真实草稿上核对容器断点、编辑不中断、公式滚动及共享抽屉。"""
    def layout(root=page):
        return root.locator('.drf-blocks').evaluate("""el =>
          ['.drf-review-question', '.drf-review-answer'].map(selector => {
            const { x, y, width, height } = el.querySelector(selector).getBoundingClientRect();
            return { x, y, width, height };
          })""")

    def side_by_side(root=page):
        question, answer = layout(root)
        return (abs(question['y'] - answer['y']) < 1
                and question['x'] + question['width'] <= answer['x'] + 1
                and abs(question['width'] - answer['width']) <= 1)

    def stacked(root=page):
        question, answer = layout(root)
        return abs(question['x'] - answer['x']) < 1 and question['y'] + question['height'] <= answer['y'] + 1

    def content_width(width):
        actual = page.locator('.drf-review-content').bounding_box()['width']
        page.set_viewport_size({'width': round(page.viewport_size['width'] + width - actual), 'height': 1000})
        page.wait_for_function("width => Math.abs(document.querySelector('.drf-review-content').getBoundingClientRect().width - width) < .1", arg=width)

    page.set_viewport_size({'width': 1440, 'height': 1000})
    open_app(page, base, 'ai-review?draft=' + second['id'])
    page.locator('.drf-review-question .drf-md').wait_for()
    content_width(999)
    check('正文999px时题答上下排列', stacked())
    content_width(1000)
    check('正文1000px时题答等宽并排且顶部对齐', side_by_side())
    check('空答案保留提示和新增入口', page.locator('.drf-review-answer').get_by_text('可以没有答案。').is_visible()
          and page.locator('.drf-review-answer [data-action="ai-review.draftAddText"]').is_visible())
    info = page.locator('.drf-review-info').bounding_box()
    question, answer = layout()
    check('题目信息位于两栏上方且占满正文', info['y'] + info['height'] <= question['y']
          and abs(info['width'] - question['width'] - answer['width']) < 1)

    long_formula = '$$' + r' + '.join(r'\frac{x_{%d}^{2}+1}{\sqrt{x_{%d}+2}}' % (index, index) for index in range(16)) + '$$'
    long_answer = '【答案】2。\n\n' + long_formula + '\n\n' + '\n\n'.join(f'第{index + 1}步：保留题目条件并核对计算过程。' for index in range(12))
    page.locator('[data-action="ai-review.draftAddText"][data-arg="答案"]').click()
    page.locator('.drf-review-answer textarea').fill(long_answer)
    page.locator('.drf-review-answer [data-action="ai-review.draftEditBlock"]').click()
    formula = page.locator('.drf-review-answer .katex-display')
    formula.wait_for()
    check('长公式在答案栏内局部横向滚动', formula.evaluate("el => el.scrollWidth > el.clientWidth && getComputedStyle(el).overflowX === 'auto'")
          and not page.evaluate('document.documentElement.scrollWidth > innerWidth'))

    page.locator('[data-action="ai-review.draftAddText"][data-arg="题目"]').click()
    editor = page.locator('.drf-review-question textarea')
    editor.fill('补充条件 $x>0$，窗口缩放后保留正在编辑的内容。')
    editor.evaluate('el => { window.__columnEditor = el; el.setSelectionRange(3, 7); }')
    for width in (999, 1000):
        content_width(width)
        check(f'编辑中缩放至{width}px保留节点、焦点、选区和未保存输入', editor.evaluate("el => el === window.__columnEditor && el === document.activeElement && el.selectionStart === 3 && el.selectionEnd === 7")
              and editor.input_value() == '补充条件 $x>0$，窗口缩放后保留正在编辑的内容。'
              and '未保存' in page.locator('.drf-detail h2').inner_text())
    body = page.locator('.drf-block.is-editing .drf-block-body').bounding_box()
    actions = page.locator('.drf-block.is-editing .drf-block-actions').bounding_box()
    check('双栏块操作位于内容下方', actions['y'] >= body['y'] + body['height'] - 1)
    page.locator('.drf-block.is-editing [data-action="ai-review.draftEditBlock"]').click()
    with page.expect_response('**/api/drafts/update') as response:
        page.locator('[data-action="ai-review.draftSave"]').click()
    saved = support.api(base, '/api/drafts/item?id=' + second['id'])['draft']
    check('双栏编辑通过真实接口保留全部题答块', response.value.ok and len(saved['blocks']) == 3
          and saved['blocks'][-1]['text'] == long_answer)
    check('长解析共用详情滚动且仅有一个底部操作栏', page.evaluate("""() => {
      const parent = element => {
        for (let node = element; node; node = node.parentElement)
          if (/auto|scroll/.test(getComputedStyle(node).overflowY) && node.scrollHeight > node.clientHeight) return node;
      };
      const question = document.querySelector('.drf-review-question'), answer = document.querySelector('.drf-review-answer');
      const scroll = parent(question);
      return scroll?.matches('.arv-detail') && scroll === parent(answer)
        && document.querySelectorAll('.drf-footer').length === 1;
    }"""))
    for theme in ('light', 'dark'):
        page.evaluate('theme => document.documentElement.dataset.theme = theme', theme)
        for width in (320, 390, 1024, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            audit = page.evaluate(support.AUDIT)
            check(f'{theme}/{width}长题答无横溢并自适应排列', not audit['overflow'] and not audit['tiny']
                  and (side_by_side() if width == 1440 else stacked()))
            page.screenshot(path=str(shots / f'columns-{theme}-{width}.png'), full_page=True)

    page.set_viewport_size({'width': 1440, 'height': 1000})
    open_app(page, base, 'ai-review?draft=' + first['id'])
    page.locator('canvas[data-draft-crop]').first.wait_for()
    check('保留原图后按剩余正文空间上下排列', stacked() and page.locator('.drf-entry-source').is_visible())
    page.set_viewport_size({'width': 2560, 'height': 1440})
    check('带原图的超宽正文仍按自身空间并排', side_by_side() and page.locator('.drf-entry-source').is_visible())
    check('已入库只读配图不超栏宽且没有编辑操作', page.locator('canvas[data-draft-crop]').evaluate_all("nodes => nodes.length === 2 && nodes.every(el => el.getBoundingClientRect().right <= el.closest('.drf-section').getBoundingClientRect().right + 1)")
          and page.locator('[data-action="ai-review.draftEditBlock"]').count() == 0)
    page.screenshot(path=str(shots / 'columns-source-wide-readonly.png'), full_page=True)

    open_app(page, base, 'dashboard')
    await_panel = """async id => {
      const entry = document.querySelector('script[type="module"][src*="app/main.js"]');
      const { createReviewPanel } = await import(new URL('./domain/ai-review.js', entry.src));
      window.__columnReviewPanel = createReviewPanel(window.__omrs);
      await window.__columnReviewPanel.open(id);
    }"""
    page.evaluate(await_panel, second['id'])
    drawer = page.locator('.ast-review-panel[open]')
    drawer.locator('.drf-review-answer .katex-display').wait_for()
    drawer.evaluate("el => Promise.all(el.getAnimations({subtree: true}).map(animation => animation.finished))")
    check('超宽屏中的窄抽屉仍使用上下排列', stacked(drawer)
          and drawer.locator('.drf-review-content').bounding_box()['width'] < 1000
          and drawer.evaluate('el => el.scrollWidth <= el.clientWidth'))
    page.screenshot(path=str(shots / 'columns-drawer.png'), full_page=True)
    drawer.locator('[data-drawer-close]').click()
    drawer.wait_for(state='detached')


def main():
    from playwright.sync_api import sync_playwright
    checks = []
    shots = Path(os.environ.get('OMRS_ENTRY_SHOTS') or os.environ.get('OMRS_E2E_SHOTS')
                 or tempfile.mkdtemp(prefix='omrs-review-entry-'))
    shots.mkdir(parents=True, exist_ok=True)

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        assert passed, name

    with tempfile.TemporaryDirectory(prefix='omrs-entry-vault-') as vault:
        subprocess.run([sys.executable, str(ROOT / 'tests/fixtures/make_vault.py'), '--out', vault,
                        '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        first, second, _, images, _, _ = support.seed(vault)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = os.environ.copy()
        env.pop('OMRS_SYSTEMD_SERVICE', None)
        env.pop('OMRS_BOXDETECT_CONTROL', None)
        with (shots / 'server.log').open('w') as log:
            proc = subprocess.Popen([sys.executable, '-c', support.SERVER, vault, str(port)], cwd=ROOT,
                                    env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        support.api(base, '/api/status')
                        break
                    except OSError:
                        time.sleep(.1)
                with sync_playwright() as playwright:
                    browser = launch_chromium(playwright)
                    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))

                    def current():
                        return support.api(base, '/api/drafts/item?id=' + first['id'])['draft']

                    def ready():
                        page.wait_for_function("""() => {
                          const image = document.querySelector('#drf-stage-src');
                          return image?.complete && image.naturalWidth && document.querySelector('.drf-review-question');
                        }""")

                    def draw():
                        stage = page.locator('#drf-stage-img')
                        stage.scroll_into_view_if_needed()
                        stage.hover(position={'x': 10, 'y': 10})
                        bounds = stage.bounding_box()
                        page.mouse.move(bounds['x'] + bounds['width'] * .10, bounds['y'] + bounds['height'] * .12)
                        page.mouse.down()
                        page.mouse.move(bounds['x'] + bounds['width'] * .86,
                                        bounds['y'] + bounds['height'] * .82, steps=8)
                        page.mouse.up()
                        page.wait_for_function("() => !!document.querySelector('canvas[data-draft-crop]')")

                    try:
                        open_app(page, base, 'ai-review?draft=' + first['id'])
                        ready()
                        content = page.locator('.drf-review-content').bounding_box()
                        source = page.locator('.drf-entry-source').bounding_box()
                        check('桌面正文与原图同时可见且左右排列', content['x'] + content['width'] <= source['x'])
                        check('草稿队列收进顶部选择器', page.locator('#arv-entry-select').is_visible()
                              and not page.locator('.arv-queue').is_visible())
                        page.locator('[data-action="ai-review.toggleQueue"]').click()
                        check('桌面可展开完整审核队列', page.locator('.arv-queue').is_visible()
                              and page.locator('.arv-row').count() == 4)
                        page.locator('[data-action="ai-review.toggleQueue"]').click()
                        check('未框图片显示明确占位并阻止入库', page.locator('.drf-image-pending').is_visible()
                              and page.locator('[data-action="ai-review.draftCommit"]').is_disabled())
                        page.locator('[data-action="ai-review.draftEditFields"]').click()
                        note = page.locator('[data-input="ai-review.draftField"][data-arg="note"]')
                        note.fill('并排工作台未保存保护')
                        page.locator('#arv-entry-select').select_option(second['id'])
                        page.get_by_role('button', name='留在当前', exact=True).click()
                        page.wait_for_function("id => document.querySelector('#arv-entry-select')?.value === id", arg=first['id'])
                        check('取消队列切换保留原目标与未保存输入', note.input_value() == '并排工作台未保存保护')
                        page.locator('[data-action="ai-review.draftEditFields"]').click()
                        page.locator(f'[data-action="ai-review.draftCanvasImage"][data-arg="{images[1]["sha256"]}"]').click()
                        ready()
                        page.locator('[data-action="ai-review.draftAddSourceImage"][data-arg="答案"]').click()
                        local_key = page.locator('#drf-canvas-block').input_value()
                        check('来源图可直接添加答案图片并选中新块', local_key.startswith('local-'))
                        page.locator(f'[data-action="ai-review.draftCanvasImage"][data-arg="{images[0]["sha256"]}"]').click()
                        page.locator(f'[data-action="ai-review.draftCanvasImage"][data-arg="{images[1]["sha256"]}"]').click()
                        check('切换来源图后仍按本地稳定键选中新图片区块', page.locator('#drf-canvas-block').input_value() == local_key)
                        ready()
                        draw()
                        check('画框实时回填正文裁图预览', page.locator('canvas[data-draft-crop]').is_visible()
                              and '未保存' in page.locator('.drf-detail h2').inner_text())
                        check('画框尚未写入服务端', len(current()['blocks']) == 3)
                        page.locator(f'[data-action="ai-review.draftCanvasImage"][data-arg="{images[0]["sha256"]}"]').click()
                        ready()
                        draw()
                        page.wait_for_function("() => !document.querySelector('[data-action=\"ai-review.draftCommit\"]')?.disabled")
                        with page.expect_response('**/api/drafts/update') as response:
                            page.locator('[data-action="ai-review.draftSave"]').click()
                        check('暂存通过真实接口保存题目和答案两个裁框', response.value.ok
                              and all(block['box'] for block in current()['blocks'] if block['kind'] == 'image'))
                        page.reload(wait_until='networkidle')
                        ready()
                        check('刷新后正文配图和完整来源均保留', page.locator('canvas[data-draft-crop]').count() == 2
                              and page.locator('[data-action="ai-review.draftCanvasImage"]').count() == 2)
                        page.locator('.drf-source-trigger').click()
                        check('放大框选仍可操作既有画布', page.locator('.drf-source-workspace').is_visible())
                        page.locator('.drf-source-trigger').click()
                        check('返回并排核对保留已存裁框', page.locator('.drf-entry-grid').is_visible()
                              and page.locator('canvas[data-draft-crop]').count() == 2)
                        for theme in ('light', 'dark'):
                            for width in (320, 390, 1024, 1440):
                                page.set_viewport_size({'width': width, 'height': 1000})
                                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                                audit = page.evaluate(support.AUDIT)
                                check(f'{theme}/{width}无横溢、过小目标或行内事件', not audit['overflow']
                                      and not audit['tiny'] and not audit['inline'] and not audit['handlers'])
                                page.screenshot(path=str(shots / f'{theme}-{width}.png'), full_page=True)
                        page.set_viewport_size({'width': 1440, 'height': 1000})
                        page.evaluate("document.documentElement.dataset.theme = 'light'")
                        with page.expect_response('**/api/drafts/commit') as response:
                            page.locator('[data-action="ai-review.draftCommit"]').click()
                        page.wait_for_function("id => { const label = document.querySelector('.drf-id'); return label && !label.textContent.includes(id); }", arg=first['id'])
                        check('核对后实际入库并推进下一份', response.value.ok and current()['status'] == 'done')
                        open_app(page, base, 'ai-review?draft=' + first['id'])
                        ready()
                        check('已入库正文只读且不能新增配图', page.locator('[data-action="ai-review.draftAddSourceImage"]').count() == 0
                              and page.locator('[data-action="ai-review.draftCommit"]').count() == 0)
                        verify_columns(page, base, first, second, shots, check)
                        check('真实页面没有脚本错误', not errors)
                    finally:
                        page.screenshot(path=str(shots / 'final.png'), full_page=True)
                        (shots / 'final.json').write_text(json.dumps({'url': page.url, 'errors': errors,
                            'text': page.locator('#panel-ai-review').inner_text()}, ensure_ascii=False, indent=2))
                        context.close()
            finally:
                proc.terminate()
                proc.wait(timeout=15)
                (shots / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(f'{len(checks)}/{len(checks)} 审核录入检查通过；截图：{shots}')


if __name__ == '__main__':
    main()
