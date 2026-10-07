"""刷新不闪动：真实隔离服务验证整页动画、正文节点、裁图、滚动与失败重试。"""
import base64
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from browser_runtime import launch_chromium, open_app
from omrs import drafts

spec = importlib.util.spec_from_file_location('refresh_support', ROOT / 'tests/e2e/drafts.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)

WATCH = """() => {
  const host = document.querySelector('#ib-stage-drafts');
  const body = host.querySelector('.drf-review-workspace');
  const crop = host.querySelector('canvas[data-draft-crop]');
  const detail = document.querySelector('.arv-detail');
  const scroll = detail.scrollHeight > detail.clientHeight ? detail : document.scrollingElement;
  scroll.scrollTo({top: 180, behavior: 'instant'});
  window.__refreshWatch?.observer.disconnect();
  const watch = window.__refreshWatch = { body, crop, scroll, scrollTop: scroll.scrollTop, detached: false, loading: false };
  watch.observer = new MutationObserver(() => {
    watch.detached ||= !body.isConnected || !crop.isConnected;
    watch.loading ||= host.textContent.includes('正在读取草稿');
  });
  watch.observer.observe(host, {childList: true, subtree: true});
}"""
KEPT = """() => {
  const w = window.__refreshWatch;
  return !w.detached && !w.loading && w.body === document.querySelector('.drf-review-workspace')
    && w.crop === document.querySelector('canvas[data-draft-crop]') && !!w.crop.dataset.painted;
}"""


def run(ctx, base, vault, check):
    image = drafts.add_image(vault, 'data:image/png;base64,' + base64.b64encode(support.png(180)).decode(), 'refresh', 'refresh')
    body = {'subject': '数学', 'category': '刷新回归', 'source_images': [image['sha256']], 'blocks': [
        {'section': '题目', 'kind': 'text', 'text': '\n'.join(f'第 {n} 行：核对 $f(x)=x^2$。' for n in range(50))},
        {'section': '题目', 'kind': 'image', 'image_sha': image['sha256'], 'box': {'x': .1, 'y': .1, 'w': .7, 'h': .7}, 'box_origin': 'manual'},
        {'section': '答案', 'kind': 'text', 'text': '答案为 4。'}]}
    first, second = [drafts.create_draft(vault, body, {'conversation_id': 'refresh', 'run_id': 'refresh', 'tool_call_id': name})
                     for name in ('first', 'second')]
    for item in (first, second):
        image_block = next(block for block in item['blocks'] if block['kind'] == 'image')
        image_block.update(box={'x': .1, 'y': .1, 'w': .7, 'h': .7}, box_origin='manual')
        updated = drafts.update_draft(vault, item['id'], item['revision'], {}, item['blocks'])
        item.update(updated)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script("window.__panelAnimations=[]; document.addEventListener('animationstart', e => { if(e.target.classList.contains('panel')) window.__panelAnimations.push(e.animationName); }, true)")
    open_app(page, base, 'ai-review?draft=' + first['id'])
    page.locator('.drf-review-workspace').wait_for()
    page.wait_for_function("!!document.querySelector('canvas[data-draft-crop]')?.dataset.painted")
    check('直达草稿没有整页入场动画', page.evaluate("!window.__panelAnimations.length && getComputedStyle(document.querySelector('.panel.active')).animationName === 'none'"))
    page.reload(wait_until='networkidle')
    page.locator('.drf-review-workspace').wait_for()
    check('浏览器刷新仍打开指定草稿且没有整页动画', first['id'] in page.locator('.drf-id').inner_text()
          and page.evaluate('!window.__panelAnimations.length'))
    page.wait_for_function("!!document.querySelector('canvas[data-draft-crop]')?.dataset.painted")
    control = {'fail': False, 'reads': 0, 'check_switch': False, 'switch_loading': False}

    def delayed(route):
        control['reads'] += 1
        if control['check_switch'] and second['id'] in route.request.url:
            control['switch_loading'] = page.evaluate("!document.querySelector('.drf-review-workspace') && document.querySelector('#ib-stage-drafts')?.textContent.includes('正在读取草稿')")
        time.sleep(.18)
        if control['fail']:
            route.fulfill(status=503, json={'msg': '刷新回归：暂时无法读取'})
        else:
            route.continue_()

    page.route('**/api/drafts/item?*', delayed)
    page.evaluate(WATCH)
    page.locator('[data-action="ai-review.refresh"]').evaluate('(el) => el.click()')
    page.wait_for_timeout(650)
    check('慢速手动刷新不清空正文、不重建已绘制裁图', page.evaluate(KEPT))
    scroll = page.evaluate("({before:window.__refreshWatch.scrollTop, after:window.__refreshWatch.scroll.scrollTop})")
    check('手动刷新保持阅读滚动位置', scroll['after'] == scroll['before'] and scroll['before'] > 0, scroll)
    before = control['reads']
    page.wait_for_timeout(3000)
    check('自动轮询实际读取详情并保留原正文及裁图节点', control['reads'] > before and page.evaluate(KEPT))
    control['fail'] = True
    page.locator('[data-action="ai-review.refresh"]').click()
    page.locator('.drf-error').wait_for()
    check('后台读取失败保留正文和裁图并提供重试', page.evaluate(KEPT)
          and page.locator('.drf-error').inner_text().find('当前内容保留') >= 0
          and page.locator('[data-action="ai-review.draftRetry"]').is_visible())
    control['fail'] = False
    page.locator('[data-action="ai-review.draftRetry"]').click()
    page.wait_for_function("!document.querySelector('.drf-error')")
    page.wait_for_timeout(350)
    check('错误重试成功后保留原正文并清除提示', page.evaluate(KEPT))
    drafts.update_draft(vault, first['id'], first['revision'], {'note': '服务端新版本备注'}, first['blocks'])
    page.locator('[data-action="ai-review.refresh"]').click()
    page.wait_for_function("document.querySelector('.drf-review-workspace')?.textContent.includes('服务端新版本备注')")
    check('有新版本时更新内容且正文不消失', page.evaluate(KEPT))
    page.locator('[data-action="ai-review.draftEditFields"]').click()
    note = page.locator('[data-input="ai-review.draftField"][data-arg="note"]')
    note.focus()
    page.evaluate(WATCH)
    page.locator('[data-action="ai-review.refresh"]').click()
    note.focus()
    page.wait_for_timeout(3000)
    check('刷新保留未修改编辑框及其焦点', note.evaluate('(el) => el === document.activeElement') and page.evaluate(KEPT))
    note.fill('未保存的人工备注')
    page.locator('[data-action="ai-review.refresh"]').click()
    page.wait_for_timeout(650)
    check('脏草稿刷新不覆盖本地输入', note.input_value() == '未保存的人工备注' and page.evaluate(KEPT))
    note.fill('服务端新版本备注')
    page.locator('[data-action="ai-review.draftEditFields"]').click()
    control['check_switch'] = True
    if page.viewport_size['width'] <= 760:
        page.locator('[data-action="ai-review.back"]').click()
    page.locator(f'.arv-row[data-arg="{second["id"]}"]').click()
    page.wait_for_function("id => document.querySelector('.drf-id')?.textContent.includes(id)", arg=second['id'])
    check('切换草稿仍显示加载状态且只展示新身份', control['switch_loading'] and second['id'] in page.locator('.drf-id').inner_text())
    control['fail'] = True
    page.reload(wait_until='networkidle')
    page.locator('.drf-error').wait_for()
    check('首次读取失败显示错误和重试，不显示旧草稿', page.locator('.drf-review-workspace').count() == 0 and page.locator('[data-action="ai-review.draftRetry"]').is_visible())
    control['fail'] = False
    page.locator('[data-action="ai-review.draftRetry"]').click()
    page.locator('.drf-review-workspace').wait_for()
    check('首次读取失败后可重试恢复指定草稿', second['id'] in page.locator('.drf-id').inner_text())
    check('刷新主路径无浏览器脚本错误', not errors, errors)
    page.close()


def main():
    from playwright.sync_api import sync_playwright
    checks = []

    def check(label, passed, detail=''):
        checks.append(bool(passed))
        print(('PASS ' if passed else 'FAIL ') + label + (': ' + str(detail) if detail else ''), flush=True)
        assert passed, label

    with tempfile.TemporaryDirectory(prefix='omrs-review-refresh-') as vault:
        subprocess.run([sys.executable, str(ROOT / 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ)
        for key in ('OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL'):
            env.pop(key, None)
        proc = subprocess.Popen([sys.executable, '-c', support.SERVER, vault, str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    support.api(base, '/api/ai-review/counts')
                    break
                except OSError:
                    time.sleep(.1)
            with sync_playwright() as pw:
                browser = launch_chromium(pw)
                for theme, width in (('light', 1440), ('dark', 1440), ('light', 390), ('dark', 390)):
                    ctx = browser.new_context(viewport={'width': width, 'height': 900})
                    ctx.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                    run(ctx, base, vault, check)
                    ctx.close()
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print(f'{sum(checks)} / {len(checks)}', flush=True)


if __name__ == '__main__':
    main()
