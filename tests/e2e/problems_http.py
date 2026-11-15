"""真实非安全 HTTP 源：保留 Host、Origin、PIN 会话并代理到隔离服务。"""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs import security

spec = importlib.util.spec_from_file_location('visual_run', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)
ORIGIN = 'http://omrs-lan.test'


def main():
    evidence = Path(os.environ.get('OMRS_PROBLEM_EVIDENCE', '/worker/evidence/repair-final'))
    evidence.mkdir(parents=True, exist_ok=True)
    checks, errors, writes = [], [], []

    def check(name, value, detail=None):
        checks.append(dict(name=name, ok=bool(value), detail=detail))
        print(name, value, detail or '', flush=True)
        assert value, (name, detail)

    with tempfile.TemporaryDirectory(prefix='problem-http-') as vault:
        create_question(vault, '数学', '合成HTTP测试', 5, question_text='解不等式 -2x > 4')
        before = mastery_rows(vault)
        security.set_pin(vault, '87654321')
        proc, port = visual.start_server(str(ROOT), vault, str(evidence / 'http-server.log'))
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width': 1280, 'height': 960})

                def proxy(route):
                    request = route.request
                    headers = request.all_headers()
                    headers['host'] = 'omrs-lan.test'
                    if request.method == 'POST':
                        writes.append(dict(path=request.url, origin=headers.get('origin'),
                                           cookie=bool(headers.get('cookie'))))
                    # 使用真实回环连接，完整保留浏览器 Host/Origin/Cookie。
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                    conn.request(request.method, request.url[len(ORIGIN):], body=request.post_data_buffer, headers=headers)
                    response = conn.getresponse()
                    body = response.read()
                    if '/api/auth/' in request.url:
                        print('鉴权代理', request.method, request.url, response.status, body[:300], flush=True)
                    route.fulfill(status=response.status, headers=dict(response.getheaders()), body=body)
                    conn.close()

                context.route(ORIGIN + '/**', proxy)
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(ORIGIN + '/login')
                capabilities = page.evaluate('({secure:isSecureContext,uuid:typeof crypto.randomUUID,random:typeof crypto.getRandomValues})')
                check('确为非安全HTTP且仅getRandomValues可用', capabilities == {
                    'secure': False, 'uuid': 'undefined', 'random': 'function'}, capabilities)
                login = page.evaluate("fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:'87654321'})}).then(async r=>({status:r.status,body:await r.text()}))")
                check('真实PIN登录成功', login['status'] == 200, login)
                page.goto(ORIGIN + '/?unlocked=1#/problems')
                auth = page.evaluate("fetch('/api/auth/session').then(r=>r.json())")
                check('真实远端PIN会话通过', auth['remote'] and auth['authenticated'])
                draft_probe = page.evaluate("async()=>{const {ReflectionDraft}=await import('/assets/app/domain/question/reflection-state.js');try{return {id:new ReflectionDraft('HTTP-PROBE').payload().request_id}}catch(e){return {error:String(e)}}}")
                print('真实HTTP错因草稿', draft_probe, flush=True)
                page.locator('[data-prb="new"]').first.click()
                page.wait_for_function("document.querySelector('[data-prb-field=title]') || document.body.textContent.includes('crypto.randomUUID')")
                check('普通HTTP新建问题表单可用', page.locator('[data-prb-field="title"]').count() == 1,
                      {'draft': draft_probe, 'body': page.locator('body').inner_text()[-1800:]})
                page.locator('[data-prb-field="title"]').fill('HTTP局域网问题')
                page.locator('[data-prb-field="description_md"]').fill('除负数前检查符号')
                page.locator('[data-prb="save"]').click()
                page.locator('.prb-detail h1').wait_for()
                saved = page.evaluate("fetch('/api/problems').then(r=>r.json())")
                pid = saved['items'][0]['id']
                check('页面完整创建并HTTP读回问题', saved['total'] == 1 and saved['items'][0]['title'] == 'HTTP局域网问题')
                page.locator('[data-prb="picker"]').click()
                page.locator(f'[data-prb-qid="{before[0]["question_id"]}"]').check()
                page.locator('[data-prb="link"]').click()
                page.locator('[data-prb="question"]').first.click()
                page.locator('#modal .ref-head').wait_for()
                page.locator('[data-qv-reflection]').click()
                textarea = page.locator('#modal [data-ref-input="content_md"]')
                for n, content in enumerate(('第一次：除负数漏变号', '第二次：漏检查端点'), 1):
                    textarea.fill(content)
                    page.locator('#modal [data-ref="save"]').click()
                    page.wait_for_function('n=>document.querySelectorAll("#modal .ref-entry").length===n', arg=n)
                    check(f'第{n}条错因实际保存', textarea.input_value() == '')
                entries = page.evaluate('qid=>fetch("/api/reflections?question_id="+qid).then(r=>r.json())', before[0]['question_id'])
                check('两条错因HTTP读回', len(entries['items']) == 2, entries)
                page.reload()
                page.locator(f'[data-prb="open"][data-id="{pid}"]').click()
                page.locator('[data-prb="question"]').first.click()
                page.wait_for_function('document.querySelectorAll("#modal .ref-entry").length===2')
                check('刷新后问题与两条错因保留', page.locator('#modal .ref-entry').count() == 2)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('[data-qv-reflection]').click()
                textarea.fill('手机草稿')
                check('手机错因表单无横向溢出', page.evaluate('document.documentElement.scrollWidth<=innerWidth+1') and textarea.evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth+1'))
                page.locator('#modal [data-dialog-cancel]').click()
                page.get_by_role('button', name='继续编辑', exact=True).click()
                page.wait_for_function("!document.querySelector('dialog.is-closing')")
                check('取消关闭后焦点恢复关闭按钮且保留草稿', page.locator('#modal [data-dialog-cancel]').evaluate('(e)=>e===document.activeElement') and textarea.input_value() == '手机草稿', page.evaluate('document.activeElement.outerHTML'))
                page.screenshot(path=str(evidence / 'http-mobile-reflections.png'), full_page=True)
                check('学习状态不变', mastery_rows(vault) == before)
                check('写请求保持同源Origin和登录Cookie', all(w['origin'] == ORIGIN and w['cookie'] for w in writes if '/api/problems/write' in w['path']), writes)
                check('无脚本错误', not errors, errors)
                browser.close()
        except BaseException:
            traceback.print_exc()
            return 1
        finally:
            proc.terminate()
            proc.wait(timeout=15)
            (evidence / 'http-e2e.json').write_text(json.dumps(dict(checks=checks, errors=errors, writes=writes), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
