"""合成SVG在真实录入、审核、网页和离线双栏打印中的端到端验收。"""
import base64
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from browser_runtime import launch_chromium, open_app
from tests.test_question_svg import diagram
from omrs import boards, exporting, question_svg
from omrs.ledger import blob_hash
from omrs.mcp.keys import create_key
from omrs.mcp.question_write import propose
from omrs.question_images import read_question_image

SERVER = '''
import base64,http.server,io,json,sys
from PIL import Image
from omrs import ai_assist
from omrs.server import OMRSHandler
ai_assist._ai_config=lambda *_args: ('http://127.0.0.1:'+sys.argv[2]+'/synthetic-model','test-only','synthetic')
class Handler(OMRSHandler):
    vault_path=sys.argv[1]
    def log_message(self,*args): pass
    def do_POST(self):
        if self.path != '/synthetic-model/chat/completions':
            return super().do_POST()
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        images=[part['image_url']['url'] for part in payload['messages'][0]['content'] if part['type']=='image_url']
        if not images or not all(src.startswith('data:image/png;base64,') and
                Image.open(io.BytesIO(base64.b64decode(src.partition(',')[2]))).width >= 1000 for src in images):
            return self._json({'error':'合成模型必须收到高清PNG派生图'},400)
        reply=(json.dumps({'subject':'物理','category':'配图验收','difficulty':5,'knowledge_tags':[]})
               if len(images)==2 else '受力图转录检查完成')
        self._json({'choices':[{'message':{'content':reply}}]})
http.server.ThreadingHTTPServer(('127.0.0.1',int(sys.argv[2])),Handler).serve_forever()
'''


def main():
    from PIL import Image
    from playwright.sync_api import sync_playwright
    shots = Path(os.environ.get('OMRS_SVG_SHOTS') or tempfile.mkdtemp(prefix='omrs-svg-browser-'))
    shots.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(label, passed, detail=''):
        checks.append(bool(passed))
        print(('PASS ' if passed else 'FAIL ') + label + (': '+str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='omrs-svg-e2e-') as vault:
        subprocess.run([sys.executable, str(ROOT/'tests/fixtures/make_vault.py'), '--out', vault,
                        '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        for name in ('OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL'):
            env.pop(name, None)
        log = open(shots/'server.log', 'w')
        proc = subprocess.Popen([sys.executable, '-c', SERVER, vault, str(port)], cwd=ROOT, env=env,
                                stdout=log, stderr=log)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base+'/api/status', timeout=.2).close()
                    break
                except OSError:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                open_app(page, base, 'create')
                page.locator('#create-flow [data-ib-stage="quick"]').click()
                page.locator('#cr-q-file').set_input_files({'name': 'tiny.svg', 'mimeType': question_svg.MIME,
                                                           'buffer': diagram(size=6)})
                page.locator('#cr-classify-status').filter(has_text='至少8.5pt').wait_for()
                check('小字配图就地报错且未加入题卡', page.locator('#cr-q-images img').count() == 0)
                page.locator('#cr-q-file').set_input_files({'name': 'question.svg', 'mimeType': question_svg.MIME,
                                                           'buffer': diagram()})
                page.wait_for_function("document.querySelector('#cr-q-images img')?.naturalWidth > 0")
                page.locator('#cr-a-file').set_input_files({'name': 'answer.svg', 'mimeType': question_svg.MIME,
                                                           'buffer': diagram('答案图')})
                page.wait_for_function("document.querySelector('#cr-a-images img')?.naturalWidth > 0")
                with page.expect_response(lambda response: response.url.endswith('/api/ai-recognize')) as response:
                    page.locator('#cr-classify-btn').click()
                classified = response.value.json()
                page.wait_for_function("document.querySelector('#cr-subject').value === '物理'")
                check('真实HTTP多图识别向合成模型发送PNG并回填分类', classified.get('status') == 'ok'
                      and classified.get('category') == '配图验收')
                with page.expect_response(lambda response: response.url.endswith('/api/ai-recognize')) as response:
                    page.locator('#cr-question-text-btn').click()
                recognized = response.value.json()
                page.wait_for_function("document.querySelector('#cr-question').value === '受力图转录检查完成'")
                check('真实HTTP单图转录向合成模型发送PNG并回填题目', recognized.get('status') == 'ok'
                      and recognized.get('question_text') == '受力图转录检查完成')
                page.locator('#cr-subject').fill('物理')
                page.locator('#cr-category').fill('配图验收')
                page.locator('#cr-question').fill('请分析图中物体的受力。')
                page.locator('#cr-answer').fill('合力为零。')
                page.screenshot(path=str(shots/'quick.png'), full_page=True)
                with page.expect_response(lambda response: response.url.endswith('/api/create')) as response:
                    page.locator('[data-action="create.submit"]').click()
                created = response.value.json()
                page.locator('#cr-result .is-success').wait_for()
                check('网页提交实际保存题目和答案两张SVG', len(created['images']) == 2)
                path = Path(vault)/created['file_path']
                before = path.read_bytes()
                image = context.request.get(base+'/api/image?name='+created['images'][0])
                check('读取保留SVG原字节并设置隔离响应头', image.body() == diagram()
                      and image.headers['content-type'].startswith(question_svg.MIME)
                      and image.headers.get('x-content-type-options') == 'nosniff'
                      and 'sandbox' in image.headers.get('content-security-policy', ''))
                open_app(page, base, 'questions')
                page.locator(f'tr[data-q-row="{created["uid"]}"] td').nth(1).click()
                page.wait_for_function("document.querySelectorAll('#modal-stage img.md-img').length === 2 && "
                                       "[...document.querySelectorAll('#modal-stage img.md-img')].every(img => img.naturalWidth > 0)")
                check('共享题目弹窗加载题目和答案原图', page.locator('#modal-stage img.md-img').count() == 2)
                page.keyboard.press('Escape')
                page.locator('dialog#modal').wait_for(state='detached')
                key = create_key(vault, scopes=['omrs:read', 'question:propose'])
                proposed = propose(vault, key['key_id'], 'svg-e2e', created['uid'], created['question_id'],
                                   blob_hash(path.read_text()), {'diagrams': [{'section': '题目',
                                     'svg': diagram('新图').decode(), 'replace': created['images'][0]}]}, reason='简化受力标注')
                page.close()
                review_context = None
                for theme in ('light', 'dark'):
                    for width in (1440, 390):
                        if review_context:
                            review_context.close()
                        review_context = browser.new_context(viewport={'width': width, 'height': 950})
                        review_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        page = review_context.new_page()
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        open_app(page, base, 'ai-review?operation='+proposed['operation_id'])
                        page.wait_for_function("document.querySelectorAll('.arv-diagrams img').length === 2 && "
                                               "[...document.querySelectorAll('.arv-diagrams img')].every(img => img.naturalWidth > 0)")
                        check(f'配图审核当前图与新图 {theme}/{width}px', path.read_bytes() == before
                              and not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'))
                        page.screenshot(path=str(shots/f'review-{theme}-{width}.png'), full_page=True)
                page.locator('[data-action="ai-review.approve"]').click()
                page.wait_for_function("document.querySelector('.arv-operation')?.textContent.includes('当前状态：已执行')")
                check('实际批准后换引用并保留原附件', path.read_bytes() != before
                      and (Path(vault)/'错题'/'附件'/created['images'][0]).read_bytes() == diagram())
                review_context.close()
                png, image_format = read_question_image(vault, created['uid'], 0)
                rendered = Image.open(io.BytesIO(png))
                check('AI读图通过实际Chromium转为可解码PNG', image_format == 'png' and rendered.width >= 1000)
                derived = question_svg.for_model('data:'+question_svg.MIME+';base64,'+base64.b64encode(diagram('新图')).decode())
                check('独立识别模型收到PNG派生图', derived.startswith('data:image/png;base64,'))
                board = boards.create_board(vault, '静态配图验收', [created['uid']])
                offline = context.new_page()
                network = []
                offline.route('http://**/*', lambda route: (network.append(route.request.url), route.abort()))
                offline.route('https://**/*', lambda route: (network.append(route.request.url), route.abort()))
                for variant in ('a4', 'screen', 'board'):
                    raw = (exporting.export_board_html(vault, board['id'], include_answers=True) if variant == 'board'
                           else exporting.export_schedule_html(vault, [created['uid']], include_answers=True, variant=variant)[0])
                    output = shots/(variant+'.html')
                    output.write_bytes(raw)
                    offline.goto(output.as_uri())
                    if variant == 'screen':
                        offline.locator('.qbody img').wait_for()
                        check('屏幕离线版题目可读且答案图默认隐藏', offline.locator('.qbody img').count() == 1
                              and not offline.locator('.ans').is_visible())
                        offline.locator('.reveal').click()
                        offline.wait_for_function("document.querySelector('.ans img')?.naturalWidth > 0")
                        check('显示答案后加载SVG答案图', offline.locator('.ans img').is_visible())
                    else:
                        offline.wait_for_function("!document.querySelector('#btnPrint').disabled")
                        slices = offline.locator('.slice').evaluate_all('''nodes => nodes.map(node => {
                          const img=node.querySelector('img'), col=node.closest('.col') || node.closest('.page');
                          return {width:node.getBoundingClientRect().width, height:node.getBoundingClientRect().height,
                            imageHeight:img.getBoundingClientRect().height, top:parseFloat(img.style.marginTop || '0'),
                            bottom:node.getBoundingClientRect().bottom <= col.getBoundingClientRect().bottom+.1}; })''')
                        check(f'{variant}整图打印未切割且保持90mm宽', len(slices) == 2 and all(
                            abs(s['width']-90*96/25.4) < 1 and abs(s['height']-s['imageHeight']) < 1
                            and s['top'] == 0 and s['bottom'] for s in slices), slices)
                        pdf = offline.pdf(path=str(shots/(variant+'.pdf')), prefer_css_page_size=True)
                        check(f'{variant}实际生成PDF', pdf.startswith(b'%PDF') and len(pdf) > 5000)
                    offline.screenshot(path=str(shots/(variant+'.png')), full_page=True)
                check('所有离线导出不发出网络请求', not network, network)
                boards.update_board(vault, board['id'], print={'note_ratio': .55})
                # 用接近字号下限的图验证过窄栏拒绝，已有题面不变。
                from omrs.creation import create_question
                narrow = create_question(vault, '物理', '配图验收', 5, question_text='窄栏试验',
                    question_images=['data:'+question_svg.MIME+';base64,'+base64.b64encode(diagram(size=11.4)).decode()])
                thin = boards.create_board(vault, '窄栏', [narrow['uid']])
                boards.update_board(vault, thin['id'], print={'note_ratio': .55})
                output = shots/'narrow.html'
                output.write_bytes(exporting.export_board_html(vault, thin['id']))
                offline.goto(output.as_uri())
                offline.wait_for_function("document.documentElement.dataset.omrsLayoutReady === 'error'")
                check('过窄栏明确报错并禁止打印与纸面记录', offline.locator('#btnPrint').is_disabled()
                      and offline.evaluate('window.OMRS_LAYOUT === null') and '过小' in offline.locator('#stage').inner_text())
                offline.evaluate("window.postMessage({type:'omrs-board-relayout',print:{note_ratio:.3}}, '*')")
                offline.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
                check('修正栏宽后可重新排版与打印', not offline.locator('#btnPrint').is_disabled()
                      and offline.evaluate('!!window.OMRS_LAYOUT'))
                check('页面无未捕获脚本错误', not errors, errors)
                context.close()
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            log.close()
    print(f'{sum(checks)} / {len(checks)}；证据：{shots}')
    return 0 if all(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
