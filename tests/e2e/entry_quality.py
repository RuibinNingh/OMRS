"""入口分档的真实浏览器主路径、资源取消与设备/动态偏好模拟。"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.browser_runtime import launch_chromium
from tests.visual.run import start_server
from omrs import security
from omrs.common import save_config

PIN = '246810'
VIDEO = base64.b64decode(
    'GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQJChYECGFOAZwEAAAAAAAKnEU2bdLpNu4tTq4QVSalmU6yBoU27i1OrhBZUrmtTrIHWTbuMU6uEElTDZ1OsggEjTbuMU6uEHFO7a1OsggKR7AEAAAAAAABZAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVSalmsCrXsYMPQkBNgIxMYXZmNjEuNy4xMDJXQYxMYXZmNjEuNy4xMDJEiYhAn0AAAAAAABZUrmvIrgEAAAAAAAA/14EBc8WITmVDXR2EP7GcgQAitZyDdW5kiIEAhoVWX1ZQOYOBASPjg4QL68IA4JCwgSC6gSCagQJVsIRVuYEBElTDZ0B/c3OfY8CAZ8iZRaOHRU5DT0RFUkSHjExhdmY2MS43LjEwMnNz2mPAi2PFiE5lQ10dhD+xZ8ilRaOHRU5DT0RFUkSHmExhdmM2MS4xOS4xMDEgbGlidnB4LXZwOWfIoUWjiERVUkFUSU9ORIeTMDA6MDA6MDIuMDAwMDAwMDAwAB9DtnVA4+eBAKOhgQAAgIJJg0IAAfAB9gA4JBwYSgAAMGAAABDf//1ZFYAAo5OBAMgAhgBAkpwAUAAAAyAAAENAo5OBAZAAhgBAkpwATuAAAyAAAENAo5OBAlgAhgBAkpwAUAAAAyAAAENAo5OBAyAAhgBAkpwATUAAAyAAAENAo5OBA+gAhgBAkpwAUAAAAyAAAENAo5OBBLAAhgBAkpwATuAAAyAAAENAo5OBBXgAhgBAkpwAUAAAAyAAAENAo5OBBkAAhgBAkpwASiAAAyAAAENAo5OBBwgAhgBAkpwAUAAAAyAAAENAHFO7a5G7j7OBALeK94EB8YIBqPCBAw=='
)


def main():
    from playwright.sync_api import sync_playwright
    for key in ('OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL'):
        os.environ.pop(key, None)
    results = []
    def check(label, ok):
        results.append((label, bool(ok)))
        print(('PASS ' if ok else 'FAIL ') + label, flush=True)

    with tempfile.TemporaryDirectory(prefix='omrs-entry-quality-') as tmp:
        work = Path(tmp); vault = work / 'vault'
        shots = Path(os.environ.get('OMRS_ENTRY_SHOTS', '/tmp/omrs-entry-quality-shots')); shots.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(ROOT / 'tests/fixtures/make_vault.py'), '--out', str(vault)],
                       check=True, capture_output=True)
        security.set_pin(str(vault), PIN)
        proc, port = start_server(str(ROOT), str(vault), str(work / 'server.log'))
        base = f'http://127.0.0.1:{port}'
        try:
            with sync_playwright() as p:
                browser = launch_chromium(p)
                contexts = []
                errors = []
                def page_for(mode='static', **options):
                    ctx = browser.new_context(**options); contexts.append(ctx)
                    ctx.add_init_script(f"if (!localStorage.getItem('omrs-entry-quality')) localStorage.setItem('omrs-entry-quality', {json.dumps(mode)});")
                    page = ctx.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    return page
                def policy_ready(page):
                    page.wait_for_function("!!document.querySelector('#gravity').dataset.preference")
                def has_scene_request(urls):
                    return any('entry-scene.js' in url or 'entry-math-atlas.svg' in url for url in urls)
                try:
                    page = page_for(viewport={'width': 320, 'height': 568})
                    requests = []; page.on('request', lambda req: requests.append(req.url))
                    page.goto(base, wait_until='networkidle'); policy_ready(page)
                    check('静态档不请求WebGL场景或公式图集', not has_scene_request(requests))
                    check('静态档无WebGL画布且小屏无横向溢出', page.locator('canvas[data-engine]').count() == 0
                          and page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                    check('窄屏访问控件与装饰页脚不重叠', page.evaluate("""() => {
                      const access=document.querySelector('.entry-access').getBoundingClientRect();
                      return [...document.querySelectorAll('.layout-footer')].every(el=>{
                        const r=el.getBoundingClientRect();
                        return !r.width || !r.height || r.right<=access.left || r.left>=access.right ||
                          r.bottom<=access.top || r.top>=access.bottom;
                      });
                    }"""))
                    page.screenshot(path=str(shots / 'static-mobile.png'))
                    page.locator('#pin').fill(PIN)
                    page.locator('#submit').click()
                    page.wait_for_function('!!window.__omrs')
                    check('静态档保留真实PIN登录与工作台跳转', page.locator('#panel-dashboard').is_visible())
                    page.set_viewport_size({'width': 1440, 'height': 900})
                    await_settings = page.locator('a[href="#/settings"]')
                    await_settings.click()
                    page.locator('#st-entry-quality').select_option('full')
                    check('设置页即时保存本浏览器偏好', page.evaluate("localStorage.getItem('omrs-entry-quality')") == 'full')
                    page.reload(wait_until='networkidle')
                    check('设置页刷新回读动画偏好', page.locator('#st-entry-quality').input_value() == 'full')
                    page.context.close(); contexts.remove(page.context)

                    page = page_for('full', reduced_motion='reduce')
                    requests = []; page.on('request', lambda req: requests.append(req.url))
                    page.goto(base, wait_until='networkidle'); policy_ready(page)
                    check('系统减少动态效果覆盖手动完整档且跳过场景下载',
                          page.locator('#gravity').get_attribute('data-quality') == 'static' and not has_scene_request(requests))
                    page.context.close(); contexts.remove(page.context)

                    for hints, label in [("Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>2})", '资源有限设备'),
                                         ("Object.defineProperty(navigator,'connection',{get:()=>({saveData:true})})", '省流量设备')]:
                        page = page_for('auto'); page.context.add_init_script(hints)
                        requests = []; page.on('request', lambda req: requests.append(req.url))
                        page.goto(base, wait_until='networkidle'); policy_ready(page)
                        check(label + '自动静态且不下载WebGL', page.locator('#gravity').get_attribute('data-quality') == 'static'
                              and not has_scene_request(requests))
                        page.context.close(); contexts.remove(page.context)

                    page = page_for('light', viewport={'width': 2560, 'height': 1440}, device_scale_factor=2)
                    page.goto(base, wait_until='domcontentloaded')
                    page.wait_for_function("document.querySelector('#gravity').dataset.status === 'ready'", timeout=60000)
                    metrics = page.locator('#gravity-viewport').evaluate('(el) => ({...el.dataset})')
                    check('轻量档真实WebGL受100万像素与1024贴图预算约束',
                          0 < int(metrics['bufferPixels']) <= 1_000_000 and metrics['textureWidth'] == '1024')
                    page.screenshot(path=str(shots / 'light.png'))
                    page.evaluate("window.entryOldGl=document.querySelector('canvas[data-engine]').getContext('webgl2')")
                    page.locator('#entry-quality').select_option('static')
                    check('切静态移除画布并真实丢弃旧GPU上下文', page.locator('canvas[data-engine]').count() == 0
                          and page.evaluate('entryOldGl.isContextLost()'))
                    page.context.close(); contexts.remove(page.context)

                    page = page_for('full', viewport={'width': 390, 'height': 844}, device_scale_factor=3)
                    page.clock.install()
                    page.goto(base, wait_until='domcontentloaded')
                    page.wait_for_function("document.querySelector('#gravity').dataset.status === 'ready'", timeout=60000)
                    metrics = page.locator('#gravity-viewport').evaluate('(el) => ({...el.dataset})')
                    check('完整档真实WebGL保留效果并限制贴图和渲染像素',
                          0 < int(metrics['bufferPixels']) <= 3_000_000 and metrics['textureWidth'] == '2048')
                    page.screenshot(path=str(shots / 'full-mobile.png'))
                    page.clock.fast_forward(16000)
                    check('闲置15秒停止动画循环', page.locator('#gravity').get_attribute('data-paused') == 'true')
                    frames = page.locator('#gravity-viewport').get_attribute('data-rendered-frames')
                    page.clock.fast_forward(2000)
                    check('闲置暂停后不继续绘制', page.locator('#gravity-viewport').get_attribute('data-rendered-frames') == frames)
                    page.keyboard.press('Shift')
                    check('用户活动后恢复动画', page.locator('#gravity').get_attribute('data-paused') == 'false')
                    page.emulate_media(reduced_motion='reduce')
                    page.wait_for_function("document.querySelector('#gravity').dataset.quality === 'static'")
                    check('运行中开启系统减少动态效果立即释放WebGL', page.locator('canvas[data-engine]').count() == 0)
                    page.context.close(); contexts.remove(page.context)

                    page = page_for('light')
                    pending = []
                    page.route('**/assets/vendor/entry-scene.js', lambda route: pending.append(route))
                    with page.expect_request('**/assets/vendor/entry-scene.js', timeout=10000):
                        page.goto(base, wait_until='domcontentloaded')
                    page.locator('#entry-quality').select_option('static')
                    for route in pending: route.continue_()
                    page.evaluate("import('/assets/vendor/entry-scene.js')")
                    check('下载途中切静态后迟到模块不会创建场景', page.locator('canvas[data-engine]').count() == 0)
                    page.context.close(); contexts.remove(page.context)

                    page = page_for('light')
                    page.route('**/assets/app/entry-background.js', lambda route: None)
                    page.goto(base, wait_until='domcontentloaded')
                    page.locator('#pin').fill(PIN); page.locator('#submit').click()
                    page.wait_for_function('!!window.__omrs')
                    check('背景控制模块下载挂起时仍能真实解锁', page.locator('#panel-dashboard').is_visible())
                    page.context.close(); contexts.remove(page.context)

                    page = page_for('auto', viewport={'width': 390, 'height': 844})
                    page.context.add_init_script("""const raf=requestAnimationFrame.bind(window), caf=cancelAnimationFrame.bind(window);
                      let seq=0; const tasks=new Map();
                      window.requestAnimationFrame=callback=>{const id=++seq;
                        const task={timer:setTimeout(()=>{task.frame=raf(t=>{tasks.delete(id);callback(t)})},110)};
                        tasks.set(id,task);return id};
                      window.cancelAnimationFrame=id=>{const task=tasks.get(id);if(task){
                        clearTimeout(task.timer);if(task.frame)caf(task.frame);tasks.delete(id)}};""")
                    page.goto(base, wait_until='domcontentloaded')
                    page.wait_for_function("document.querySelector('#entry-quality-status').textContent.includes('运行持续较慢')", timeout=30000)
                    check('真实场景在模拟持续低帧率时自动释放WebGL并记录短期降级',
                          page.locator('canvas[data-engine]').count() == 0 and
                          page.evaluate("!!JSON.parse(localStorage.getItem('omrs-entry-quality-fallback'))?.at"))
                    requests = []; page.on('request', lambda req: requests.append(req.url))
                    page.reload(wait_until='networkidle'); policy_ready(page)
                    check('短期降级后刷新不再次初始化WebGL', not has_scene_request(requests)
                          and page.locator('#gravity').get_attribute('data-quality') == 'static')
                    page.context.close(); contexts.remove(page.context)

                    page = page_for('auto')
                    page.context.add_init_script("""const get=HTMLCanvasElement.prototype.getContext;
                      HTMLCanvasElement.prototype.getContext=function(kind,...args){
                        return kind==='webgl2'?null:get.call(this,kind,...args)};""")
                    page.goto(base, wait_until='domcontentloaded')
                    page.wait_for_function("document.querySelector('#entry-quality-status').textContent.includes('动画暂不可用')", timeout=20000)
                    check('WebGL不支持时正常回退，PIN仍可输入', page.locator('canvas[data-engine]').count() == 0
                          and page.locator('#pin').is_visible())
                    page.context.close(); contexts.remove(page.context)

                    media_id = '0123456789abcdef0123456789abcdef'
                    folder = vault / '错题/.omrs/entry-background'; folder.mkdir(parents=True, exist_ok=True)
                    from PIL import Image
                    image = folder / (media_id + '.png'); Image.new('RGB', (32, 32), 'white').save(image)
                    for kind, mime, suffix in [('image', 'image/png', '.png'), ('video', 'video/webm', '.webm'), ('image', 'image/gif', '.gif')]:
                        target = folder / (media_id + suffix)
                        if not target.exists(): target.write_bytes(b'not-requested-in-static-mode')
                        if kind == 'video': target.write_bytes(VIDEO)
                        save_config(str(vault), {'entry_background': {'mode': 'custom', 'style': 'gaussian-blur', 'blur_px': 7,
                            'asset': {'id': media_id, 'kind': kind, 'mime': mime, 'bytes': target.stat().st_size}}})
                        page = page_for('static')
                        requests = []; page.on('request', lambda req: requests.append(req.url))
                        page.goto(base, wait_until='networkidle'); policy_ready(page)
                        if mime == 'image/png':
                            page.wait_for_function("!!document.querySelector('#entry-custom canvas')")
                            check('自定义静态图片真实显示首帧画布', page.locator('#entry-custom canvas').is_visible())
                        else:
                            check(mime + '静态档不请求原媒体', not any('/api/entry-background' in url for url in requests))
                        page.context.close(); contexts.remove(page.context)
                        if kind == 'video':
                            page = page_for('light'); page.clock.install()
                            page.goto(base, wait_until='domcontentloaded')
                            page.wait_for_function("document.querySelector('#entry-custom video')?.paused === false")
                            check('轻量档自定义视频实际播放', page.locator('#entry-custom video').count() == 1)
                            page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
                            check('模拟标签页隐藏后视频暂停', page.locator('video').evaluate('(el)=>el.paused'))
                            page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
                            page.wait_for_function("document.querySelector('video').paused === false")
                            check('模拟标签页恢复后视频继续播放', not page.locator('video').evaluate('(el)=>el.paused'))
                            page.clock.fast_forward(16000)
                            check('视频闲置时暂停', page.locator('video').evaluate('(el)=>el.paused'))
                            page.locator('#entry-quality').select_option('static')
                            check('视频切静态后移除媒体且不启动WebGL', page.locator('video,canvas[data-engine]').count() == 0)
                            page.context.close(); contexts.remove(page.context)
                    check('入口主路径无未捕获脚本错误', not errors)
                    if errors: print(json.dumps(errors, ensure_ascii=False))
                finally:
                    for ctx in contexts: ctx.close()
                    if not os.environ.get('OMRS_TEST_CDP_URL'): browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    print(f'入口分档 E2E：{sum(ok for _, ok in results)}/{len(results)}', flush=True)
    return 0 if results and all(ok for _, ok in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
