"""临时 Vault + 真实页面 + 真实 Chromium 渲染；仅替换作业帮及模型网络边界。"""
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from tests.zuoyebang_fixtures import profile, png

SERVER = r'''
import http.server,json,sys,time
from unittest.mock import patch
from omrs import ai_assist
from omrs.server import OMRSHandler
from omrs.zuoyebang import service_config,jobs
from omrs.zuoyebang.html import candidate_html
from tests.zuoyebang_gateway import SyntheticGateway, KEY
from tests.zuoyebang_fixtures import candidates,data_url,png
vault,port=sys.argv[1:]
gateway = SyntheticGateway().__enter__()
gateway.account['observations']['events'] = [{'event':'login','kind':'ok','at':time.time()}]
source=candidates()
question_url='https://img.cdnjtzy.com/synthetic-question.png'
answer_url='https://new-answer-images.example/synthetic-answer.png'
source[0]['question']['content']=source[0]['question']['content'].replace(data_url(),question_url)
source[0]['answer'][0]['content']=source[0]['answer'][0]['content'].replace(data_url('formula'),answer_url)
gateway.responses['/api/v1/search']=(200,{'status':'ok','result':{'data':{'answers':{'mainPageInfo':[json.dumps(source)]}}}}, {})
image_sources={question_url:png(),answer_url:png('formula')}
# 仅替代远程附图下载；地址校验、本地化和真实 Chromium 渲染照常执行。
jobs.candidate_html=lambda candidate:candidate_html(candidate,fetcher=image_sources.__getitem__)
service_config.save(vault, {'base_url':gateway.url, 'api_key':KEY})
original=ai_assist.extract_region
answer_attempts=0
def extract(vault,image,role='question',judge=True,**kwargs):
    global answer_attempts
    time.sleep(2 if role=='answer' else .8)
    if role=='answer':
        answer_attempts+=1
        if answer_attempts==1: raise TimeoutError('模拟答案首次超时')
    reply={'convertible':role=='answer','reason':'纯文字与公式，可完整转录' if role=='answer' else '题目依赖几何位置关系，保留整图',
           'text':'由中线及勾股定理，$AD=4$，面积 $S=12$。完整原解析。' if role=='answer' else ''}
    with patch.object(ai_assist,'_call_model',return_value=json.dumps(reply,ensure_ascii=False)):
        return original(vault,image,role=role,judge=judge)
ai_assist.extract_region=extract
ai_assist.recognize_question=lambda *args,**kwargs: {'subject':'数学','category':'平面几何','difficulty':5,'knowledge_tags':['勾股定理']}
class Handler(OMRSHandler):
    vault_path=vault
    def log_message(self,*args): pass
http.server.ThreadingHTTPServer(('127.0.0.1',int(port)),Handler).serve_forever()
'''

AUDIT = '''() => {
 const root=document.querySelector('#ib-stage-zuoyebang');
 const shown=[...root.querySelectorAll('*')].filter(el=>el.offsetParent);
 return {inline:shown.filter(el=>(el.getAttribute('style')||'').trim()).length,
 handlers:shown.filter(el=>[...el.attributes].some(a=>/^on/i.test(a.name))).length,
 overflow:document.documentElement.scrollWidth>innerWidth+1,
 small:shown.filter(el=>el.matches('button,summary')).filter(el=>el.getBoundingClientRect().height<28).map(el=>el.textContent)};
}'''

def main():
    from playwright.sync_api import sync_playwright
    output = Path(os.environ.get('OMRS_ZYB_SHOTS', Path(os.environ.get('TMPDIR', str(ROOT / '.venv'))) / 'omrs-zuoyebang-e2e'))
    output.mkdir(parents=True, exist_ok=True)
    results = []
    def check(name, condition):
        results.append({'name': name, 'ok': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
        if not condition: raise AssertionError(name)
    with tempfile.TemporaryDirectory(prefix='omrs-zyb-e2e-') as temporary:
        vault = Path(temporary) / 'vault'; vault.mkdir()
        photo = Path(temporary) / 'photo.webp'
        with Image.open(io.BytesIO(png())) as image: image.save(photo, 'WEBP')

        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = dict(os.environ); env.pop('OMRS_SYSTEMD_SERVICE', None); env.pop('OMRS_BOXDETECT_CONTROL', None)
        log = open(output / 'server.log', 'w')
        server = subprocess.Popen([sys.executable, '-u', '-c', SERVER, str(vault), str(port)], cwd=ROOT, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + '/api/auth/session', timeout=1).close(); break
                except OSError: time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, permissions=['camera'])
                page = context.new_page(); errors = []; page.on('pageerror', lambda error: errors.append(str(error))); page.on('console', lambda msg: print('BROWSER '+msg.text,flush=True) if msg.type=='error' else None)
                open_app(page, base, 'create')
                if errors: raise AssertionError(errors)
                page.wait_for_selector('#create-flow [data-stage]', timeout=5000)
                page.locator('[data-action="create.stage"][data-arg="zuoyebang"]').click()
                page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).wait_for()
                check('导航新增作业帮并移除AI草稿按钮', page.locator('#create-flow [data-stage="drafts"]').count() == 0)
                check('服务初始收为单行入口', page.locator('#zyb-account-panel').count() == 0 and page.locator('#zyb-account').evaluate('(el)=>el.getBoundingClientRect().height') <= 40)
                page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).click()
                check('网关状态显示有效账号签名且不再导入扫码', '账号：有效；签名：有效' in page.locator('#zyb-account').inner_text() and page.locator('#zyb-profile, [data-action="create.zybLogin"]').count() == 0)
                check('独立管理面板链接无token且开启新tab', page.get_by_role('link', name='打开独立管理面板').get_attribute('target') == '_blank' and 'token=' not in page.get_by_role('link', name='打开独立管理面板').get_attribute('href'))
                page.get_by_role('button', name='会话有效期记录', exact=True).click()
                check('有效期记录子页显示网关观察并获得焦点', '扫码登录' in page.locator('#zyb-account-panel').inner_text() and page.get_by_role('button', name='返回服务菜单', exact=True).evaluate('(el)=>el===document.activeElement'))
                page.get_by_role('button', name='返回服务菜单', exact=True).click()
                check('返回菜单恢复记录入口焦点', page.get_by_role('button', name='会话有效期记录', exact=True).evaluate('(el)=>el===document.activeElement'))
                page.keyboard.press('Escape')
                check('Escape关闭服务菜单并恢复焦点', page.locator('#zyb-account-panel').count() == 0 and page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).evaluate('(el)=>el===document.activeElement'))
                page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).click()
                page.get_by_role('heading', name='取图搜题', exact=True).click()
                check('点击外部关闭服务菜单', page.locator('#zyb-account-panel').count() == 0)
                page.get_by_role('button', name='打开摄像头', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-video').srcObject?.active")
                page.evaluate("() => window.zybTestTrack=document.querySelector('#zyb-video').srcObject.getVideoTracks()[0]")
                page.locator('[data-action="create.stage"][data-arg="quick"]').click()
                check('切工作区关闭真实MediaStream', page.evaluate("() => window.zybTestTrack.readyState==='ended'"))
                page.locator('[data-action="create.stage"][data-arg="zuoyebang"]').click()
                page.get_by_role('button', name='打开摄像头', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-video').readyState>=2 && document.querySelector('#zyb-video').videoWidth>0")
                dimensions = page.locator('#zyb-video').evaluate('(el)=>[el.videoWidth,el.videoHeight]')
                page.evaluate("() => window.zybTestTrack=document.querySelector('#zyb-video').srcObject.getVideoTracks()[0]")
                page.get_by_role('button', name='拍照搜题', exact=True).click()
                page.locator('.zyb-candidate').first.wait_for()
                page.wait_for_function("() => document.querySelector('.zyb-source-image')?.naturalWidth>0")
                check('拍照直接搜题并保留原始分辨率照片', page.locator('.zyb-source-image').evaluate('(el)=>[el.naturalWidth,el.naturalHeight]') == dimensions)
                check('拍照后关闭摄像头且不预选候选', page.evaluate("() => window.zybTestTrack.readyState==='ended'") and page.locator('.zyb-candidate.on').count() == 0)
                page.get_by_role('button', name='重拍', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-video').srcObject?.active")
                page.evaluate("() => window.zybTestTrack=document.querySelector('#zyb-video').srcObject.getVideoTracks()[0]")
                page.get_by_role('button', name='上传图片', exact=True).click()
                check('切上传模式释放摄像头并保留已拍原图', page.evaluate("() => window.zybTestTrack.readyState==='ended'") and page.locator('.zyb-source-image').is_visible() and page.locator('#zyb-camera-source').is_hidden())
                page.evaluate('''data => {
                  window.zybClipboardFile = new File([new Uint8Array(data)], 'pasted.png', {type:'image/png'});
                  const transfer = new DataTransfer(); transfer.items.add(window.zybClipboardFile);
                  document.querySelector('[data-action="create.zybPaste"]').dispatchEvent(new ClipboardEvent('paste', {clipboardData:transfer,bubbles:true,cancelable:true}));
                }''', list(png()))
                page.wait_for_function("() => document.querySelector('#zyb-source-preview').textContent.includes('pasted.png')")
                check('粘贴图片共用上传模式并清除旧候选', page.locator('[data-action="create.zybSource"][data-arg="upload"]').get_attribute('aria-pressed') == 'true' and page.locator('.zyb-candidate').count() == 0)
                page.evaluate("() => Object.defineProperty(navigator,'clipboard',{configurable:true,value:{read:async()=>{throw new Error('denied')}}})")
                page.get_by_role('button', name='粘贴图片', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-status').textContent.includes('Ctrl / ⌘ + V')")
                check('剪贴板拒绝时保留图片并提供键盘粘贴', 'pasted.png' in page.locator('#zyb-source-preview').inner_text())
                page.evaluate("() => Object.defineProperty(navigator,'clipboard',{configurable:true,value:{read:()=>new Promise(resolve=>window.zybClipboardResolve=resolve)}})")
                page.get_by_role('button', name='粘贴图片', exact=True).click()
                page.get_by_role('button', name='摄像头', exact=True).click()
                page.evaluate("() => window.zybClipboardResolve([{types:['image/png'],getType:async()=>window.zybClipboardFile}])")
                page.wait_for_timeout(100)
                check('迟到剪贴板不切回已离开的来源模式', page.locator('[data-action="create.zybSource"][data-arg="camera"]').get_attribute('aria-pressed') == 'true')
                page.evaluate("() => Object.defineProperty(navigator,'clipboard',{configurable:true,value:{read:async()=>[{types:['image/png'],getType:async()=>window.zybClipboardFile}]}})")
                page.get_by_role('button', name='粘贴图片', exact=True).click()
                page.wait_for_function("() => document.querySelector('[data-action=\"create.zybSource\"][data-arg=\"upload\"]').getAttribute('aria-pressed')==='true'")
                check('粘贴按钮读取图片后自动切上传模式', 'clipboard-' in page.locator('#zyb-source-preview').inner_text())
                page.evaluate("() => delete navigator.clipboard")
                page.locator('#zyb-image').set_input_files(str(photo))
                page.evaluate('''() => {
                  const original = window.fetch;
                  window.fetch = async (...args) => {
                    const response = await original(...args);
                    if (new URL(args[0], location.href).pathname === '/api/zuoyebang/jobs' && !window.zybDelayedJob) {
                      window.zybDelayedJob = true;
                      await new Promise(resolve => setTimeout(resolve, 1200));
                    }
                    return response;
                  };
                }''')
                page.get_by_role('button', name='开始搜题', exact=True).click()
                page.wait_for_function('() => window.zybDelayedJob === true')
                page.evaluate("() => window.__omrs.router.go('questions')")
                page.wait_for_selector('#panel-questions.active')
                page.evaluate("() => window.__omrs.router.go('create')")
                page.wait_for_selector('#ib-stage-zuoyebang.on')
                page.locator('.zyb-candidate').first.wait_for()
                check('任务创建响应迟到新挂载仍恢复后台搜题', page.locator('#zyb-status').inner_text().startswith('找到'))
                check('WebP原图通过专用分块上传完成搜题', page.locator('#zyb-status').inner_text().startswith('找到'))
                check('候选按位置独立返回并保留题干答案对应', page.locator('.zyb-candidate').count() == 3)
                check('返回候选后不自动选择第一条', page.locator('.zyb-candidate.on').count() == 0)
                page.locator('.zyb-candidate').first.click()
                page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalWidth===1080", timeout=60000)
                check('预览图片来自真实后端1080渲染', page.locator('#zyb-rendered-image').get_attribute('src').startswith('/api/zuoyebang/image'))
                check('点选候选自动生成预览且没有额外渲染按钮', page.get_by_role('button', name='渲染所选题目', exact=True).count() == 0)
                render_id = page.evaluate("() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace')).render_id")
                record = context.request.get(base + '/api/zuoyebang/record?id=' + render_id).json()['record']
                check('任意域名的题目与答案附图均经本地化并完整渲染', record['source_images'] == 2 and all(record['images'][role]['images'] == 1 for role in ('question', 'answer')))
                layout = page.evaluate('''() => {
                  const width = selector => document.querySelector(selector).getBoundingClientRect().width;
                  return {workspace:width('.zyb-workspace'),host:width('#ib-stage-zuoyebang'),left:width('.zyb-source'),right:width('.zyb-renderer'),editor:width('#zyb-editor')};
                }''')
                check('右侧预览440px且剩余空间分配左侧来源与识别核对', layout['right'] <= 440 and layout['left'] > layout['right'] and abs(layout['left'] - layout['editor']) < 1)
                check('工作区铺满可用宽度不留整体右侧空白', abs(layout['workspace'] - layout['host']) < 1)
                page.get_by_role('button', name='答案与解析', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalHeight>3000")
                image_url = page.locator('#zyb-rendered-image').get_attribute('src')
                raw = context.request.get(base + image_url).body()
                with Image.open(io.BytesIO(raw)) as image:
                    check('答案单张长图宽1080且覆盖长正文', image.width == 1080 and image.height > 3000)
                    image.save(output / 'answer.png')
                page.get_by_role('button', name='100%', exact=True).click()
                check('100%只改变显示比例不改变原图', page.locator('#zyb-rendered-image').evaluate('(el)=>el.getBoundingClientRect().width') == 1080)
                page.get_by_role('button', name='适应宽度', exact=True).click()
                page.get_by_role('button', name='HTML', exact=True).click()
                check('HTML含原答案末尾且图片已本地化', '解析末尾' in page.locator('.zyb-code').inner_text() and '[已本地化' in page.locator('.zyb-code').inner_text())
                page.get_by_role('button', name='HTML', exact=True).click()
                page.locator('.zyb-viewport').evaluate('(el)=>el.scrollTop=el.scrollHeight')
                page.locator('.zyb-renderer').screenshot(path=str(output / 'answer-tail.png'))
                page.get_by_role('button', name='展开', exact=True).click()
                check('展开完整长图复用已生成图片', page.locator('.ui-image-viewer img').get_attribute('src') == image_url)
                page.get_by_role('button', name='关闭预览', exact=True).click()
                page.evaluate('''() => {
                  const original = window.fetch; window.zybRenderRequests = [];
                  window.fetch = async (...args) => {
                    const payload = args[1]?.body ? JSON.parse(args[1].body) : {};
                    const tracked = new URL(args[0],location.href).pathname === '/api/zuoyebang/jobs' && payload.type === 'render';
                    if (tracked) window.zybRenderRequests.push(payload.candidate_index);
                    const response = await original(...args);
                    if (tracked && payload.candidate_index === 1) await new Promise(resolve=>setTimeout(resolve,700));
                    return response;
                  };
                }''')
                page.locator('[data-action="create.zybSelect"][data-arg="1"]').click()
                page.locator('[data-action="create.zybSelect"][data-arg="2"]').click()
                page.locator('[data-action="create.zybSelect"][data-arg="0"]').click()
                page.wait_for_function("() => {const s=JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'));return s.selected===0 && s.render_id && !s.job}", timeout=60000)
                check('快速切换串行处理且只渲染最后选择', page.evaluate('() => window.zybRenderRequests') == [1, 0] and page.locator('.zyb-candidate.on').get_attribute('data-arg') == '0')
                latest_id = page.evaluate("() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace')).render_id")
                latest = context.request.get(base + '/api/zuoyebang/record?id=' + latest_id).json()['record']
                check('快速切换最终恢复正确题目预览', latest['candidate']['index'] == 0 and latest['source_images'] == 2)
                page.get_by_role('button', name='AI 识别题目与答案', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-status').textContent.includes('项提取失败')")
                check('部分失败保留题图与完整答案图片并允许重试', page.locator('[data-arg="question:image"]').get_attribute('aria-pressed') == 'true' and page.locator('[data-arg="answer:image"]').get_attribute('aria-pressed') == 'true')
                page.get_by_role('button', name='AI 识别题目与答案', exact=True).click()
                page.locator('[data-arg="answer:text"]').click()
                page.locator('[data-zyb-text="answer"]').fill('人工在识别期间核对的完整答案 $AD=4$，面积12。')
                job_id = page.evaluate("() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace')).job.id")
                check('刷新前AI任务确实仍在运行', context.request.get(base + '/api/zuoyebang/job?id=' + job_id).json()['job']['status'] == 'running')
                open_app(page, base, 'create')
                page.locator('[data-action="create.stage"][data-arg="zuoyebang"]').click()
                page.wait_for_function("() => document.querySelector('[data-zyb-text=\"answer\"]')?.value.startsWith('人工在识别期间')")
                page.wait_for_function("() => document.querySelector('#zyb-status').textContent.includes('识别完成')")
                check('识别在途刷新后AI完成仍不覆盖人工正文', page.locator('[data-zyb-text="answer"]').input_value().startswith('人工在识别期间'))
                check('科目分类复用AI补空流程', page.locator('[data-zyb-field="subject"]').input_value() == '数学' and page.locator('[data-zyb-field="category"]').input_value() == '平面几何')
                page.get_by_role('button', name='题目', exact=True).click()
                page.locator('.zyb-viewport').evaluate('(el)=>el.scrollTop=0')
                for theme in ('light', 'dark'):
                    for width in (1440, 1024, 390, 320):
                        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
                        page.set_viewport_size({'width': width, 'height': 1000})
                        page.add_style_tag(content='*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}')
                        page.evaluate('() => document.fonts.ready')
                        page.locator('#zyb-account').scroll_into_view_if_needed()
                        audit = page.evaluate(AUDIT)
                        check(f'{theme}/{width}无横溢、行内样式和过小目标', not audit['overflow'] and not audit['inline'] and not audit['handlers'] and not audit['small'])
                        page.get_by_role('button', name='作业帮服务 · 已连接', exact=True).click()
                        page.get_by_role('button', name='会话有效期记录', exact=True).click()
                        panel = page.locator('#zyb-account-panel').bounding_box()
                        check(f'{theme}/{width}账号记录菜单在视口内', panel['x'] >= 0 and panel['x'] + panel['width'] <= width + 1 and not page.evaluate(AUDIT)['overflow'])
                        page.screenshot(path=str(output / f'menu-{theme}-{width}.png'), full_page=True)
                        page.keyboard.press('Escape')
                        page.screenshot(path=str(output / f'{theme}-{width}.png'), full_page=True)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.get_by_role('button', name='录入 OMRS', exact=True).click()
                page.locator('.zyb-result').wait_for()
                markdown = next((vault / '错题' / '数学').rglob('平面几何[0-9]*.md')).read_text()
                (output / 'created-synthetic.md').write_text(markdown)
                check('创建题目保存完整题图及人工核对答案', '人工在识别期间' in markdown and '![[平面几何1-' in markdown and '-q-1.png' in markdown and 'synthetic-account' not in markdown)
                check('正式题目只有一份', len(list((vault / '错题').rglob('平面几何[0-9]*.md'))) == 1)
                open_app(page, base, 'create')
                page.locator('[data-action="create.stage"][data-arg="zuoyebang"]').click()
                page.locator('.zyb-result').wait_for()
                check('刷新恢复渲染、首次提交内容和已入库回执', page.get_by_role('button', name='已录入题库', exact=True).is_disabled())
                page.locator('[data-action="create.zybSelect"][data-arg="1"]').click()
                check('切候选清空上一题渲染结果', page.locator('#zyb-rendered-image').count() == 0 and page.locator('.zyb-result').count() == 0)
                page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalWidth===1080", timeout=60000)
                page.get_by_role('button', name='答案与解析', exact=True).click()
                page.get_by_role('button', name='HTML', exact=True).click()
                check('新候选答案没有混入上一题解析', '候选二答案' in page.locator('.zyb-code').inner_text() and '三角形' not in page.locator('.zyb-code').inner_text())
                def fail_render(route):
                    if route.request.post_data_json.get('type') == 'render':
                        route.fulfill(status=503, json={'error': '模拟渲染暂不可用'})
                    else: route.continue_()
                page.route('**/api/zuoyebang/jobs', fail_render)
                page.locator('[data-action="create.zybSelect"][data-arg="2"]').click()
                page.get_by_role('button', name='重试渲染', exact=True).wait_for()
                check('渲染失败保留候选并清空旧题预览', page.locator('.zyb-candidate').count() == 3 and page.locator('#zyb-rendered-image').count() == 0 and page.locator('.zyb-candidate.on').get_attribute('data-arg') == '2')
                page.unroute('**/api/zuoyebang/jobs', fail_render)
                page.get_by_role('button', name='重试渲染', exact=True).click()
                page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalWidth===1080", timeout=60000)
                check('失败可重试所选候选并恢复自动预览', page.locator('.zyb-candidate.on').get_attribute('data-arg') == '2')
                page.evaluate("() => window.__omrs.router.go('ai-review?type=draft')")
                page.wait_for_selector('#panel-ai-review.active')
                check('审核中心草稿仍可访问', page.locator('#panel-ai-review.active').count() == 1)
                check('浏览器没有脚本错误', not errors)
                log_text = '\n'.join(path.read_text() for path in (vault / '错题' / '.omrs' / 'zuoyebang').rglob('record.json'))
                check('来源任务与渲染记录不含凭据及Cookie', 'synthetic-account' not in log_text and 'synthetic-gateway-call-key' not in log_text and 'Cookie' not in log_text)
                check('不迁移或生成OMRS旧账号会话', not (vault / '错题' / '.omrs' / 'zuoyebang' / 'session.json').exists())
                response = context.request.post(base + '/api/zuoyebang/profile', headers={'Origin': 'https://evil.example'}, data={'profile': profile()})
                check('新写接口继承OMRS来源校验', response.status == 403)
                context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'): browser.close()
            (output / 'checks.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(f'{len(results)}/{len(results)} 项通过；产物 {output}', flush=True)
        finally:
            server.terminate(); server.wait(timeout=10); log.close()


if __name__ == '__main__': main()
