"""AI 草稿 P4：临时 Vault、假本地检测提供方与真实页面/API 联调。"""
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from browser_runtime import launch_chromium
from omrs import drafts as store
from omrs.common import save_config
import drafts as support

SHOTS = '/tmp/omrs-ai-draft-p4-shots'
SERVER = r'''
import http.server, sys, time
from pathlib import Path
from omrs import ai_assist
from omrs.server import OMRSHandler
vault, port = sys.argv[1:]
def detect(*_args, **_kwargs):
    mode_file = Path(vault, 'detect-mode')
    mode = mode_file.read_text() if mode_file.exists() else 'normal'
    if mode == 'hold':
        Path(vault, 'detect-entered').touch()
        deadline = time.monotonic() + 12
        while not Path(vault, 'detect-release').exists() and time.monotonic() < deadline:
            time.sleep(.02)
    if mode == 'error':
        raise ValueError('本地检测测试失败')
    if mode == 'ambiguous':
        return [{'role': 'question', 'card': 1, 'x': .08, 'y': .12, 'w': .35, 'h': .38, 'conf': .82},
                {'role': 'question', 'card': 1, 'x': .48, 'y': .2, 'w': .4, 'h': .48, 'conf': .74}]
    return [{'role': 'question', 'card': 1, 'x': .1, 'y': .15, 'w': .6, 'h': .55, 'conf': .96}]
ai_assist.detect_regions_local = detect
class Handler(OMRSHandler):
    vault_path = vault
    def log_message(self, *_args):
        pass
http.server.ThreadingHTTPServer(('127.0.0.1', int(port)), Handler).serve_forever()
'''


def seed(vault):
    conv = 'draft-p4-browser'
    def image(shade):
        data = 'data:image/png;base64,' + base64.b64encode(support.png(shade)).decode()
        return store.add_image(vault, data, conv, 'p4-run')
    def create(name, source, kind='image'):
        block = {'section': '题目', 'kind': kind}
        if kind == 'image':
            block['image_sha'] = source['sha256']
        else:
            block['text'] = f'{name}：求 $f(2)$。'
        return store.create_draft(vault, {'subject': '数学', 'category': name,
            'source_images': [source['sha256']], 'blocks': [block]},
            {'conversation_id': conv, 'run_id': 'p4-run', 'tool_call_id': f'tool-{name}'})
    save_config(vault, {'draft_force_crop': False, 'inbox_detect_provider': 'local_http',
                        'inbox_local_detect_url': 'http://127.0.0.1:9/detect'})
    old = create('旧文字', image(111), 'text')
    save_config(vault, {'draft_force_crop': True})
    applied = create('自动填框', image(112))
    shared_image = image(113)
    shared = create('共用图', shared_image)
    create('共用图另一题', shared_image, 'text')
    ambiguous = create('歧义候选', image(114))
    failure = create('检测错误', image(115))
    conflict = create('版本冲突', image(116))
    force = create('强制训练', image(117), 'text')
    touch = create('手机补标', image(118), 'text')
    touch = store.commit_draft(vault, touch['id'], touch['revision'])['draft']
    return {'old': old, 'applied': applied, 'shared': shared, 'ambiguous': ambiguous,
            'failure': failure, 'conflict': conflict, 'force': force, 'touch': touch}


def main():
    from playwright.sync_api import sync_playwright
    checks = []
    os.makedirs(SHOTS, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='omrs-draft-p4-e2e-') as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'],
                       check=True, stdout=subprocess.DEVNULL)
        records = seed(vault)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, '-c', SERVER, vault, str(port)], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        def check(name, passed, detail=''):
            checks.append((name, bool(passed), detail))
        def item(key):
            return support.api(base, '/api/drafts/item?id=' + records[key]['id'])['draft']
        def open_draft(page, key):
            current = item(key)
            button = f'.drf-item[data-arg="{current["id"]}"]'
            target_filter = 'done' if current['status'] == 'done' else 'pending'
            page.locator(f'[data-action="create.draftFilter"][data-arg="{target_filter}"]').click()
            page.locator(button).click()
            page.locator('#drf-stage-src').wait_for()
        def mode(value):
            Path(vault, 'detect-mode').write_text(value)
        try:
            for _ in range(100):
                try:
                    support.api(base, '/api/status'); break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(error.stack or str(error)))
                try:
                    page.goto(base + '/#/create', wait_until='networkidle')
                    page.locator('#create-flow [data-ib-stage="drafts"]').click()
                    counts_equal = """() => {
                      const side = document.querySelector('#nav-draft-count');
                      const top = document.querySelector('#drf-c-pending');
                      const left = document.querySelector('.drf-count');
                      return side && top && left && Number(side.textContent) === Number(top.textContent)
                        && Number(top.textContent) === Number(left.textContent.match(/\\d+/)?.[0]);
                    }"""
                    check('侧栏、工作区与列表待审核数一致', support.wait(page, counts_equal))
                    open_draft(page, 'applied')
                    mode('normal')
                    page.locator('[data-action="create.draftDetect"]').click()
                    applied_ready = support.wait(page, "() => !!document.querySelector('#drf-stage-img .crp-box') && !!document.querySelector('[data-action=\"create.draftDetect\"]') && !document.querySelector('.drf-canvas .drf-message')", 15000)
                    applied_item = item('applied')
                    applied_ok = (applied_ready and applied_item['blocks'][0]['box_origin'] == 'ai'
                                  and page.locator('.drf-canvas').get_by_text('AI 已填入', exact=False).count() > 0)
                    check('明确匹配的 AI 框写入正文并展示结果', applied_ok,
                          '' if applied_ok else str({'job': applied_item['jobs'][0], 'message': page.locator('.drf-message').all_text_contents()}))
                    original = item('applied')['blocks'][0]['ai_box']
                    page.locator('#drf-stage-img').scroll_into_view_if_needed()
                    handle = page.locator('#drf-stage-img .crp-handle[data-h="se"]')
                    point = handle.bounding_box()
                    page.mouse.move(point['x'] + point['width'] / 2, point['y'] + point['height'] / 2)
                    page.mouse.down(); page.mouse.move(point['x'] + point['width'] / 2 + 20, point['y'] + point['height'] / 2 + 10, steps=5); page.mouse.up()
                    support.wait(page, "() => document.querySelector('.drf-detail h2')?.textContent.includes('未保存')", 3000)
                    if not page.locator('[data-action="create.draftSave"]').is_enabled():
                        raise AssertionError('拖动 AI 框后保存仍禁用：' + str({'job': item('applied')['jobs'][0],
                            'message': page.locator('.drf-message').all_text_contents(),
                            'box': page.locator('#drf-stage-img .crp-box').get_attribute('x'),
                            'heading': page.locator('.drf-detail h2').inner_text(),
                            'detect': page.locator('[data-action="create.draftDetect"]').count()}))
                    page.locator('[data-action="create.draftSave"]').click()
                    adjusted = item('applied')['blocks'][0]
                    check('人工移动 AI 框保留 ai_box 与 ai_edited', adjusted['box_origin'] == 'ai_edited' and adjusted['ai_box'] == original)
                    page.locator('[data-action="create.draftDetect"]').click()
                    check('已有人工调整框被跳过', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已跳过')", 15000)
                          and item('applied')['jobs'][0]['result'][0]['reason_code'] == 'manual_box')
                    open_draft(page, 'shared')
                    page.locator('[data-action="create.draftDetect"]').click()
                    check('共用图检测直接跳过', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('共用')", 15000)
                          and item('shared')['jobs'][0]['result'][0]['reason_code'] == 'shared_image')
                    open_draft(page, 'ambiguous'); mode('ambiguous')
                    page.locator('[data-action="create.draftDetect"]').click()
                    check('歧义候选以虚线建议展示且不改正文', support.wait(page, "() => document.querySelectorAll('.drf-suggestion').length === 2", 15000)
                          and item('ambiguous')['blocks'][0]['box'] is None)
                    page.locator('[data-action="create.draftAcceptCandidate"]').first.click()
                    page.locator('[data-action="create.draftSave"]').click()
                    check('明确点击候选后才保存 AI 来源框', item('ambiguous')['blocks'][0]['box_origin'] == 'ai')
                    open_draft(page, 'failure'); mode('error')
                    page.locator('[data-action="create.draftDetect"]').click()
                    check('模型失败保留待框正文并可重试', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('AI 框选失败')", 15000)
                          and item('failure')['blocks'][0]['box'] is None
                          and page.locator('[data-action="create.draftDetect"]').count() == 1)
                    open_draft(page, 'conflict'); mode('hold')
                    page.locator('[data-action="create.draftDetect"]').click()
                    for _ in range(100):
                        if Path(vault, 'detect-entered').exists(): break
                        time.sleep(.05)
                    current = item('conflict')
                    support.api(base, '/api/drafts/update', {'id': current['id'], 'revision': current['revision'],
                        'fields': {'note': '检测期间另一标签页已保存'}, 'blocks': current['blocks']})
                    Path(vault, 'detect-release').touch()
                    check('检测期间版本冲突不覆盖正文', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('冲突')", 15000)
                          and item('conflict')['blocks'][0]['box'] is None)
                    open_draft(page, 'force'); mode('normal')
                    check('全文字强制任务有独立入口且未框不阻入库', item('force')['training_tasks'][0]['force_crop']
                          and page.locator('[data-action="create.draftCommit"]').is_enabled()
                          and page.locator('[data-action="create.draftCanvasMode"][data-arg="training"]').count() == 1)
                    page.locator('[data-action="create.draftCommit"]').click()
                    check('全文字先入库，正文只读而训练框可画', support.wait(page, "() => !!document.querySelector('.drf-success')", 15000)
                          and page.locator('[data-action="create.draftSave"]').count() == 0
                          and page.locator('[data-action="create.draftCanvasMode"][data-arg="training"]').get_attribute('aria-pressed') == 'true')
                    check('入库后三处待审核计数同步减少', support.wait(page, counts_equal)
                          and int(page.locator('#drf-c-pending').inner_text()) == support.api(base, '/api/drafts/counts')['counts']['cropping']
                          + support.api(base, '/api/drafts/counts')['counts']['review'])
                    stage = page.locator('#drf-stage-img'); stage.scroll_into_view_if_needed(); bounds = stage.bounding_box()
                    page.mouse.move(bounds['x'] + bounds['width'] * .15, bounds['y'] + bounds['height'] * .2)
                    page.mouse.down(); page.mouse.move(bounds['x'] + bounds['width'] * .72, bounds['y'] + bounds['height'] * .68, steps=6); page.mouse.up()
                    page.locator('[data-action="create.draftSave"]').click()
                    check('训练关闭仍可保存强制框且不登记', item('force')['training_tasks'][0]['status'] == 'ready'
                          and support.api(base, '/api/inbox/dataset/stats')['chat']['images'] == 0)
                    page.locator('[data-action="create.draftTrainToggle"]').click()
                    check('开启训练后登记 chat 且正文仍只读', support.wait(page, "() => !!document.querySelector('.drf-canvas-meta span:nth-child(2)')?.textContent.includes('已登记')", 15000)
                          and item('force')['training_tasks'][0]['status'] == 'registered'
                          and item('force')['blocks'][0]['kind'] == 'text')
                    page.locator('#create-flow [data-ib-stage="train"]').click()
                    check('AI 训练页显示聊天来源统计', support.wait(page, "() => document.querySelector('#ib-tr-chat')?.textContent.includes('聊天来源图 1 张')", 15000))
                    page.locator('#create-flow [data-ib-stage="drafts"]').click()
                    open_draft(page, 'old')
                    check('普通旧文字草稿不显示强制任务提示', not item('old')['training_tasks'][0]['force_crop']
                          and '独立训练框待核对' not in page.locator('.drf-sources').inner_text())
                    page.locator('[data-action="create.draftDetect"]').click()
                    check('旧文字来源可手动发起独立框任务', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已填入')", 15000)
                          and item('old')['training_tasks'][0]['force_crop']
                          and item('old')['training_tasks'][0]['boxes'])
                except Exception as error:
                    checks.append(('P4 草稿主路径执行', False, repr(error)[:700]))
                checks.append(('P4 主路径页面脚本无错误', not errors, str(errors[:2])))
                context.close()
                touch_context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                touch_page = touch_context.new_page()
                try:
                    touch_page.goto(base + '/#/create', wait_until='networkidle')
                    touch_page.locator('#create-flow [data-ib-stage="drafts"]').click()
                    open_draft(touch_page, 'touch')
                    stage = touch_page.locator('#drf-stage-img'); stage.scroll_into_view_if_needed(); bounds = stage.bounding_box()
                    x0, y0 = bounds['x'] + bounds['width'] * .15, bounds['y'] + bounds['height'] * .2
                    x1, y1 = bounds['x'] + bounds['width'] * .7, bounds['y'] + bounds['height'] * .65
                    session = touch_context.new_cdp_session(touch_page)
                    session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'id': 1, 'x': x0, 'y': y0}]})
                    for step in range(1, 7):
                        session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{
                            'id': 1, 'x': x0 + (x1-x0)*step/6, 'y': y0 + (y1-y0)*step/6}]})
                    session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
                    drawn = support.wait(touch_page, "() => document.querySelectorAll('#drf-stage-img .crp-box').length === 1")
                    if drawn: touch_page.locator('[data-action="create.draftSave"]').click()
                    check('已入库全文字草稿手机触摸补标', drawn and len(item('touch')['training_tasks'][0]['boxes']) == 1)
                    touch_page.screenshot(path=os.path.join(SHOTS, 'touch-mobile.png'), full_page=True)
                except Exception as error:
                    checks.append(('P4 手机触摸执行', False, repr(error)[:700]))
                touch_context.close()
                for theme in ('light', 'dark'):
                    for label, width, height in (('desktop', 1440, 900), ('mobile', 390, 844)):
                        audit_context = browser.new_context(viewport={'width': width, 'height': height})
                        audit_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        audit_page = audit_context.new_page()
                        audit_errors = []
                        audit_page.on('pageerror', lambda error: audit_errors.append(str(error)))
                        try:
                            audit_page.goto(base + '/#/create', wait_until='networkidle')
                            audit_page.locator('#create-flow [data-ib-stage="drafts"]').click()
                            open_draft(audit_page, 'force')
                            support.wait(audit_page, counts_equal)
                            audit_page.locator('[data-action="create.draftCanvasMode"][data-arg="training"]').click()
                            shot = os.path.join(SHOTS, f'{theme}-{label}.png')
                            audit_page.screenshot(path=shot, full_page=True)
                            findings = audit_page.evaluate(support.AUDIT)
                            check(f'P4 画布 {theme}·{label} 审计与截图', not audit_errors and not findings['overflow']
                                  and not findings['inline'] and not findings['handlers'] and findings['image'] == 1,
                                  str(findings) + ' ' + shot)
                        except Exception as error:
                            checks.append((f'P4 画布 {theme}·{label} 审计与截图', False, repr(error)[:500]))
                        audit_context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'): browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    for name, passed, detail in checks:
        print(('PASS' if passed else 'FAIL') + ' ' + name + (': ' + detail if detail else ''))
    print(f'{sum(ok for _, ok, _ in checks)} / {len(checks)}')
    return 0 if checks and all(ok for _, ok, _ in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
