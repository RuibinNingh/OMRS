"""审核录入并排工作台：真实服务、原图切换、本地新块、裁图暂存及入库。"""
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
