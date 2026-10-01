"""AI 草稿工作区 E2E：真实临时 Vault 与 HTTP API，审核、保存、通过、丢弃及四档页面审计。"""
import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from browser_runtime import launch_chromium
from omrs import drafts

SHOTS = '/tmp/omrs-ai-draft-p2-shots'
P3_SHOTS = '/tmp/omrs-ai-draft-p3-shots'
SERVER = r'''
import http.server, sys
from omrs import ai_assist
from omrs.server import OMRSHandler
vault, port = sys.argv[1:]
def extract(*_args, **kwargs):
    if kwargs.get("role") == "answer":
        return {"convertible": False, "reason": "测试替身拒绝解析", "text": ""}
    return {"convertible": True, "reason": "", "text": "局部提取结果 $f(2)=4$。"}
ai_assist.extract_region = extract
class Handler(OMRSHandler):
    vault_path = vault
    def log_message(self, *_args):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(port)), Handler).serve_forever()
'''


def png(shade):
    """本地生成带题目/解析内容的数学测试截图，不读取用户图片。"""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (560, 330), '#ffffff')
    draw = ImageDraw.Draw(image)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    label_font = ImageFont.truetype(font_path, 24) if os.path.exists(font_path) else ImageFont.load_default()
    math_font = ImageFont.truetype(font_path, 38) if os.path.exists(font_path) else ImageFont.load_default()
    heading = 'QUESTION 1' if shade < 200 else 'SOLUTION 1'
    lines = ('f(x) = x^2', 'Find f(2).') if shade < 200 else ('f(2) = 2^2', 'Answer: 4')
    draw.rounded_rectangle((22, 20, 538, 310), radius=18, outline='#9ca3af', width=3)
    draw.text((48, 48), heading, fill='#334155', font=label_font)
    draw.line((48, 93, 510, 93), fill='#cbd5e1', width=2)
    draw.text((48, 125), lines[0], fill='#111827', font=math_font)
    draw.text((48, 204), lines[1], fill='#111827', font=math_font)
    draw.text((430, 280), str(shade), fill='#64748b', font=label_font)
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def seed(vault):
    conv = 'draft-e2e-conversation'
    images = [drafts.add_image(vault, 'data:image/png;base64,' + base64.b64encode(png(shade)).decode(), conv, 'run-test')
              for shade in (180, 220)]
    first = drafts.create_draft(vault, {
        'subject': '数学', 'category': '函数', 'knowledge_points': ['导数'], 'cause': '审题不清',
        'cause_statement': '审题不清', 'source_images': [image['sha256'] for image in images],
        'blocks': [
            {'section': '题目', 'kind': 'text', 'text': '已知 $f(x)=x^2$，求 $f(2)$。'},
            {'section': '题目', 'kind': 'image', 'image_sha': images[0]['sha256'], 'note': '图像证据'},
            {'section': '答案', 'kind': 'text', 'text': '答案是 4。'},
        ],
    }, {'conversation_id': conv, 'run_id': 'run-test', 'tool_call_id': 'tool-first'})
    second = drafts.create_draft(vault, {
        'subject': '数学', 'category': '代数', 'knowledge_points': [], 'cause': '', 'cause_statement': '',
        'source_images': [], 'blocks': [{'section': '题目', 'kind': 'text', 'text': '求 1+1。'}],
    }, {'conversation_id': conv, 'run_id': 'run-test', 'tool_call_id': 'tool-second'})
    old = drafts.create_draft(vault, {
        'subject': '数学', 'category': '几何', 'knowledge_points': [], 'cause': '', 'cause_statement': '',
        'blocks': [{'section': '题目', 'kind': 'text', 'text': '旧草稿来源待补。'}],
    }, {'conversation_id': conv, 'run_id': 'run-test', 'tool_call_id': 'tool-old'})
    p3_images = [drafts.add_image(vault, 'data:image/png;base64,' + base64.b64encode(png(shade)).decode(), conv, 'run-p3')
                 for shade in (150, 230)]
    p3 = drafts.create_draft(vault, {
        'subject': '数学', 'category': '应用题', 'source_images': [image['sha256'] for image in p3_images],
        'blocks': [
            {'section': '题目', 'kind': 'text', 'text': '先看图再计算。'},
            {'section': '题目', 'kind': 'image', 'image_sha': p3_images[0]['sha256']},
            {'section': '答案', 'kind': 'image', 'image_sha': p3_images[1]['sha256']},
        ],
    }, {'conversation_id': conv, 'run_id': 'run-p3', 'tool_call_id': 'tool-p3'})
    return first, second, old, images, p3, p3_images


def api(base, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def wait(page, expr, timeout=10000):
    try:
        page.wait_for_function(expr, timeout=timeout)
        return True
    except Exception:
        return False


AUDIT = """() => {
  const host = document.querySelector('#ib-stage-drafts');
  const shown = [...host.querySelectorAll('*')].filter(e => e.getClientRects().length && !e.closest('.katex'));
  const clickables = shown.filter(e => ['BUTTON','INPUT','SELECT','TEXTAREA'].includes(e.tagName));
  const tiny = clickables.filter(e => { const r=e.getBoundingClientRect(); return r.height < 28; }).map(e => `${e.tagName}:${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const overflow = document.documentElement.scrollWidth > innerWidth + 1;
  return { overflow, tiny, inline: shown.filter(e => (e.getAttribute('style') || '').trim()).length,
    handlers: shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length,
    image: shown.filter(e => e.matches('.drf-source img')).length };
}"""


def run(page, base, first, second, old, images, results):
    def check(name, passed, detail=''):
        results.append((name, bool(passed), detail))

    page.goto(base + '/?unlocked=1#/create', wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    check('工作区显示四份待审核草稿', wait(page, "() => document.querySelectorAll('.drf-item').length === 4"))
    page.locator(f'.drf-item[data-arg="{first["id"]}"]').click()
    check('审核首屏先显示题目且来源默认收起', wait(page, "() => !!document.querySelector('.drf-review-question') && document.querySelector('.drf-source-trigger')?.getAttribute('aria-expanded') === 'false'")
          and page.locator('[data-input="create.draftBlockText"]').count() == 0)
    page.locator('.drf-source-trigger').click()
    check('来源模式显示两图和主画布', wait(page, "() => document.querySelectorAll('.drf-source img').length === 2 && !!document.querySelector('.drf-source-workspace .drf-canvas')"))
    page.locator('[data-action="create.draftPreviewSource"]').first.click()
    check('来源图使用站内预览且保持两图顺序', page.locator('dialog.ui-image-viewer[open] img').count() == 1
          and page.locator('dialog.ui-image-viewer[open] .ui-image-viewer__count').text_content().startswith('1 / 2'))
    page.locator('dialog.ui-image-viewer [data-image-action="next"]').click()
    check('来源图可切换下一张', page.locator('dialog.ui-image-viewer[open] .ui-image-viewer__count').text_content().startswith('2 / 2'))
    page.keyboard.press('Escape')
    page.wait_for_selector('dialog.ui-image-viewer', state='detached')
    check('来源图关闭后回到审核页原按钮', page.locator('[data-action="create.draftPreviewSource"]').first.evaluate('e => document.activeElement === e'))
    page.locator('.drf-source-trigger').click()
    check('未框图片阻止通过', page.locator('[data-action="create.draftCommit"]').is_disabled())
    page.locator('[data-action="create.draftEditFields"]').click()
    page.locator('[data-input="create.draftField"][data-arg="cause"]').fill('计算时漏看平方')
    page.locator('.drf-block [data-action="create.draftWhole"]').click()
    check('整图框使通过可选且显示未保存', wait(page, "() => !document.querySelector('[data-action=\"create.draftCommit\"]')?.disabled && document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
    page.locator('[data-action="create.draftSave"]').click()
    check('显式保存把框和错因写入真实 API', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存')")
          and (lambda item: item['draft']['cause'] == '计算时漏看平方' and item['draft']['blocks'][1]['box'] == {'x': 0, 'y': 0, 'w': 1, 'h': 1}
               and item['draft']['status'] == 'review')(api(base, '/api/drafts/item?id=' + first['id'])))
    lost_responses = []
    def lose_commit_response(route):
        lost_responses.append(route.fetch().status)
        route.abort()
    page.route('**/api/drafts/commit', lose_commit_response, times=1)
    page.locator('[data-action="create.draftCommit"]').click()
    check('通过只创建一次并进入下一题', wait(page, f"() => !!document.querySelector('.drf-detail .drf-id') && !document.querySelector('.drf-detail .drf-id')?.textContent.includes('{first['id']}')")
          and api(base, '/api/drafts/item?id=' + first['id'])['draft']['status'] == 'done'
          and page.locator('[data-action="create.draftCommit"]').count() == 1)
    check('入库响应丢失后同一操作安全重试', lost_responses == [200]
          and api(base, '/api/drafts/item?id=' + first['id'])['draft']['status'] == 'done')
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    page.locator('[data-change="create.draftFilter"]').select_option('pending')
    page.locator(f'.drf-item[data-arg="{second["id"]}"]').click()
    page.locator('[data-action="create.draftDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('丢弃状态持久且留在待审核队列继续下一题', wait(page, f"() => document.querySelector('.drf-id') && !document.querySelector('.drf-id').textContent.includes('{second['id']}') && document.querySelector('[data-change=\"create.draftFilter\"]')?.value === 'pending'")
          and api(base, '/api/drafts/item?id=' + second['id'])['draft']['status'] == 'discarded'
          and api(base, '/api/drafts/counts')['counts']['discarded'] == 1)
    page.locator('[data-change="create.draftFilter"]').select_option('pending')
    page.locator(f'.drf-item[data-arg="{old["id"]}"]').click()
    page.locator('.drf-source-trigger').click()
    check('旧来源不完整提示与可补关联图片', wait(page, "() => document.querySelector('.drf-sources .drf-hint')?.textContent.includes('来源未完整恢复') && document.querySelectorAll('#drf-source-select option').length === 5"))
    page.locator('#drf-source-select').select_option(images[1]['sha256'])
    page.locator('[data-action="create.draftSourceAdd"]').click()
    page.locator('[data-action="create.draftSave"]').click()
    check('补关联按 SHA 保存且来源完整', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存') && !document.querySelector('.drf-detail [aria-busy=true]')")
          and (lambda item: item['draft']['sources_complete'] and images[1]['sha256'] in [image['sha256'] for image in item['draft']['source_images']])
              (api(base, '/api/drafts/item?id=' + old['id'])))
    page.locator('.drf-source-trigger').click()
    page.locator('[data-action="create.draftEditFields"]').click()
    page.locator('[data-input="create.draftField"][data-arg="note"]').fill('未保存的临时笔记')
    check('编辑备注进入未保存状态', wait(page, "() => document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    check('离开工作区出现三动作对话框', wait(page, "() => !!document.querySelector('dialog[open]')")
          and page.locator('dialog[open] button').filter(has_text='保存并离开').count() == 1
          and page.locator('dialog[open] button').filter(has_text='放弃修改并离开').count() == 1
          and page.locator('dialog[open] button').filter(has_text='留在当前').count() == 1)
    page.locator('dialog[open] button').filter(has_text='留在当前').click()
    check('选择留在当前保留本地修改', page.locator('#ib-stage-drafts').is_visible()
          and page.locator('[data-input="create.draftField"][data-arg="note"]').input_value() == '未保存的临时笔记')
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('dialog[open] button').filter(has_text='保存并离开').click()
    check('保存后离开且刷新仍可读取', wait(page, "() => document.querySelector('#ib-stage-upload')?.classList.contains('on')")
          and api(base, '/api/drafts/item?id=' + old['id'])['draft']['note'] == '未保存的临时笔记')
    page.reload(wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    check('刷新恢复上次选中的草稿', wait(page, f"() => document.querySelector('.drf-detail .drf-id')?.textContent.includes('{old['id']}')"))
    page.locator('[data-action="create.draftEditFields"]').click()
    current = api(base, '/api/drafts/item?id=' + old['id'])['draft']
    fields = {name: current[name] for name in ('subject', 'category', 'difficulty', 'knowledge_points', 'labels', 'cause', 'note')}
    fields['note'] = '另一标签页已修改'
    api(base, '/api/drafts/update', {'id': old['id'], 'revision': current['revision'], 'fields': fields,
                                     'blocks': current['blocks'], 'source_images': [image['sha256'] for image in current['source_images']]})
    page.locator('[data-input="create.draftField"][data-arg="note"]').fill('本地修改不能丢')
    page.locator('[data-action="create.draftSave"]').click()
    check('409 显示冲突并保留本地编辑', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('冲突')")
          and page.locator('[data-input="create.draftField"][data-arg="note"]').input_value() == '本地修改不能丢')
    page.locator('[data-action="create.draftReloadDetail"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('显式重读后采用服务端版本', wait(page, "() => document.querySelector('[data-input=\"create.draftField\"][data-arg=\"note\"]')?.value === '另一标签页已修改'"))
    latest = api(base, '/api/drafts/item?id=' + old['id'])['draft']
    api(base, '/api/drafts/update', {'id': old['id'], 'revision': latest['revision'],
                                     'fields': {'note': '入库前被其他窗口修改'}, 'blocks': latest['blocks']})
    page.locator('[data-action="create.draftCommit"]').click()
    check('入库前版本复核拦截旧草稿', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('新版本')")
          and api(base, '/api/drafts/item?id=' + old['id'])['draft']['status'] != 'done')
    page.locator('[data-action="create.draftReloadDetail"]').click()
    page.route('**/api/drafts/list?status=pending&limit=500', lambda route: route.fulfill(
        status=503, content_type='application/json', body='{"status":"error","msg":"列表暂不可用"}'))
    page.locator('[data-action="create.draftQueueMenu"]').click()
    page.get_by_role('menuitem', name='刷新列表', exact=True).click()
    check('列表读取失败与空态区分', wait(page, "() => document.querySelector('.drf-list .drf-error')?.textContent.includes('列表暂不可用')"))
    page.unroute('**/api/drafts/list?status=pending&limit=500')
    page.locator('.drf-list .drf-error [data-action="create.draftReload"]').click()
    check('列表失败后可重试', wait(page, "() => !document.querySelector('.drf-list .drf-error') && !!document.querySelector('.drf-item')"))


def run_discard_queue(browser, base, vault, results):
    """丢弃的队列连续性、失败保护与空队列记忆，全部经过真实浏览器和 HTTP。"""
    for number in range(3):
        drafts.create_draft(vault, {
            'subject': '数学', 'category': '丢弃队列回归',
            'blocks': [{'section': '题目', 'kind': 'text', 'text': f'队列回归题 {number + 1}。'}],
        }, {'conversation_id': 'discard-queue', 'run_id': 'discard-run', 'tool_call_id': str(number)})
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def check(name, passed, detail=''):
        results.append((name, bool(passed), detail))
        if not passed:
            raise AssertionError(name + ': ' + detail)
    def queue():
        return page.locator('.drf-item').evaluate_all('els => els.map(el => el.dataset.arg)')
    def selected(id):
        return wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{id}') && !document.querySelector('[data-action=\"create.draftDiscard\"]')?.disabled")
    def discard():
        page.locator('[data-action="create.draftDiscard"]').click()
        page.locator('dialog[open] [data-dialog-ok]').click()
    def remembered():
        return page.evaluate("sessionStorage.getItem('omrs-selected-draft')")
    try:
        page.goto(base + '/?unlocked=1#/create', wait_until='networkidle')
        page.locator('#create-flow [data-ib-stage="drafts"]').click()
        check('丢弃回归队列至少有三份', wait(page, "() => document.querySelectorAll('.drf-item').length >= 3"))
        ids = queue()
        current, next_id = ids[1:3]
        page.locator(f'.drf-item[data-arg="{current}"]').click()
        check('丢弃前可打开队列中间草稿', selected(current))
        page.locator('[data-action="create.draftEditFields"]').click()
        note = page.locator('[data-input="create.draftField"][data-arg="note"]')
        note.fill('丢弃取消或失败时保留这段未保存备注')
        page.locator('[data-action="create.draftDiscard"]').click()
        page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
        check('取消丢弃保留当前草稿、分类和未保存编辑', selected(current)
              and page.locator('[data-change="create.draftFilter"]').input_value() == 'pending'
              and note.input_value() == '丢弃取消或失败时保留这段未保存备注' and remembered() == current)
        page.route('**/api/drafts/discard', lambda route: route.fulfill(
            status=503, content_type='application/json', body='{"status":"error","msg":"丢弃暂不可用"}'))
        discard()
        check('丢弃请求失败保留当前草稿和未保存编辑', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('丢弃失败')")
              and selected(current) and remembered() == current
              and page.locator('[data-change="create.draftFilter"]').input_value() == 'pending'
              and note.input_value() == '丢弃取消或失败时保留这段未保存备注'
              and api(base, '/api/drafts/item?id=' + current)['draft']['status'] != 'discarded')
        page.unroute('**/api/drafts/discard')
        discard()
        check('丢弃中间草稿后留在待审核并选择原下一份', selected(next_id)
              and page.locator('[data-change="create.draftFilter"]').input_value() == 'pending'
              and queue() == [id for id in ids if id != current] and remembered() == next_id
              and api(base, '/api/drafts/item?id=' + current)['draft']['status'] == 'discarded')
        check('丢弃后计数同步且下一份没有继承本地修改', wait(page, f"() => document.querySelector('.drf-count')?.textContent.includes('{len(ids) - 1} 份待审核') && !document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
        ids = queue()
        page.locator(f'.drf-item[data-arg="{ids[-1]}"]').click()
        check('可选择队列最后一份', selected(ids[-1]))
        discard()
        check('丢弃最后一份自动选择上一份', selected(ids[-2]) and remembered() == ids[-2]
              and page.locator('[data-change="create.draftFilter"]').input_value() == 'pending')
        failed_id = ids[-2]
        page.route('**/api/drafts/list?status=pending&limit=500', lambda route: route.fulfill(
            status=503, content_type='application/json', body='{"status":"error","msg":"列表暂不可用"}'))
        discard()
        check('丢弃成功但列表刷新失败时留在待审核且清除旧选择', wait(page, "() => document.querySelector('.drf-list .drf-error')?.textContent.includes('列表暂不可用')")
              and page.locator('[data-change="create.draftFilter"]').input_value() == 'pending'
              and page.locator('.drf-id').count() == 0 and remembered() is None
              and api(base, '/api/drafts/item?id=' + failed_id)['draft']['status'] == 'discarded')
        page.unroute('**/api/drafts/list?status=pending&limit=500')
        page.locator('.drf-list [data-action="create.draftReload"]').click()
        check('列表刷新失败后可重试且不恢复已丢弃草稿', wait(page, "() => !document.querySelector('.drf-list .drf-error') && !!document.querySelector('.drf-item')")
              and failed_id not in queue() and remembered() is None)
        while queue():
            ids = queue()
            page.locator(f'.drf-item[data-arg="{ids[-1]}"]').click()
            check(f'连续丢弃前可打开剩余 {len(ids)} 份中的最后一份', selected(ids[-1]))
            discard()
            check(f'连续丢弃后剩余 {len(ids) - 1} 份且分类保持待审核', wait(page, f"() => document.querySelectorAll('.drf-item').length === {len(ids) - 1} && document.querySelector('[data-change=\"create.draftFilter\"]')?.value === 'pending'")
                  and api(base, '/api/drafts/item?id=' + ids[-1])['draft']['status'] == 'discarded')
        check('最后一份丢弃后显示空队列并清空选中记忆', wait(page, "() => document.querySelector('.drf-list')?.textContent.includes('没有待审核草稿') && !document.querySelector('.drf-id')")
              and remembered() is None and api(base, '/api/drafts/counts')['counts']['review'] == 0)
        page.locator('#create-flow [data-ib-stage="upload"]').click()
        page.locator('#create-flow [data-ib-stage="drafts"]').click()
        check('离开工作区后返回仍是空的待审核分类', wait(page, "() => document.querySelector('[data-change=\"create.draftFilter\"]')?.value === 'pending' && !document.querySelector('.drf-id')"))
        page.reload(wait_until='networkidle')
        page.locator('#create-flow [data-ib-stage="drafts"]').click()
        check('刷新页面不会重新打开最后丢弃的草稿', wait(page, "() => document.querySelector('.drf-list')?.textContent.includes('没有待审核草稿') && document.querySelector('[data-change=\"create.draftFilter\"]')?.value === 'pending' && !document.querySelector('.drf-id')")
              and remembered() is None)
        page.locator('[data-change="create.draftFilter"]').select_option('discarded')
        page.locator(f'.drf-item[data-arg="{current}"]').click()
        check('手动进入已丢弃分类仍可查看只读正文', wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{current}') && document.querySelector('.drf-detail h2')?.textContent.includes('已丢弃')")
              and page.locator('[data-action="create.draftEditBlock"], [data-action="create.draftDiscard"]').count() == 0)
        page.locator('[data-change="create.draftFilter"]').select_option('pending')
        page.evaluate("id => import('/assets/app/domain/drafts.js').then(module => module.openDraft(id))", current)
        check('指定草稿导航仍能自动匹配已丢弃分类', wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{current}') && document.querySelector('[data-change=\"create.draftFilter\"]')?.value === 'discarded'"))
        check('丢弃队列回归没有页面脚本错误', not errors, str(errors))
    finally:
        context.close()


def run_p3(page, base, draft, images, results):
    def check(name, passed, detail=''):
        results.append((name, bool(passed), detail))

    def drag(x0, y0, x1, y1):
        stage = page.locator('#drf-stage-img')
        stage.scroll_into_view_if_needed()
        bounds = stage.bounding_box()
        target_y = bounds['y'] + bounds['height'] * y1
        page.evaluate("y => { const foot = document.querySelector('.drf-footer')?.getBoundingClientRect(); if (foot && y > foot.top - 24) document.querySelector('#ib-stage-drafts').scrollTop += y - foot.top + 110; }", target_y)
        bounds = stage.bounding_box()
        page.mouse.move(bounds['x'] + bounds['width'] * x0, bounds['y'] + bounds['height'] * y0)
        page.mouse.down()
        page.mouse.move(bounds['x'] + bounds['width'] * x1, bounds['y'] + bounds['height'] * y1, steps=6)
        page.mouse.up()

    page.locator(f'.drf-item[data-arg="{draft["id"]}"]').click()
    page.locator('.drf-source-trigger').click()
    check('P3 多图草稿显示逐图画布', wait(page, "() => document.querySelectorAll('.drf-canvas-tabs [data-action=\"create.draftCanvasImage\"]').length === 2 && !!document.querySelector('#drf-stage-src')"))
    drag(.12, .18, .66, .65)
    check('手动画框使正文可保存', wait(page, "() => document.querySelectorAll('#drf-stage-img .crp-box').length === 1 && document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
    first_box = page.locator('#drf-stage-img .crp-box').bounding_box()
    page.mouse.move(first_box['x'] + first_box['width'] / 2, first_box['y'] + first_box['height'] / 2)
    page.mouse.down(); page.mouse.move(first_box['x'] + first_box['width'] / 2 + 18, first_box['y'] + first_box['height'] / 2 + 12, steps=5); page.mouse.up()
    moved = page.locator('#drf-stage-img .crp-box').get_attribute('x')
    check('正文框可移动', float(moved) > 560 * .12)
    handle = page.locator('#drf-stage-img .crp-handle[data-h="se"]')
    point = handle.bounding_box()
    before_width = float(page.locator('#drf-stage-img .crp-box').get_attribute('width'))
    page.mouse.move(point['x'] + point['width'] / 2, point['y'] + point['height'] / 2)
    page.mouse.down(); page.mouse.move(point['x'] + point['width'] / 2 + 20, point['y'] + point['height'] / 2 + 12, steps=5); page.mouse.up()
    check('正文框可缩放', float(page.locator('#drf-stage-img .crp-box').get_attribute('width')) > before_width)
    page.locator('[data-action="create.draftSave"]').click()
    check('首张框保存完成后才继续操作', wait(page, "() => !document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
    check('局部正文框通过真实 API 持久化', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存')")
          and api(base, '/api/drafts/item?id=' + draft['id'])['draft']['blocks'][1]['box'] is not None)
    page.locator('[data-action="create.draftClearBox"]').click()
    check('正文框可删除', wait(page, "() => !document.querySelector('#drf-stage-img .crp-box')"))
    drag(.1, .2, .55, .6)
    redrawn = wait(page, "() => !!document.querySelector('#drf-stage-img .crp-box') && !!document.querySelector('[data-action=\"create.draftSave\"]:not([disabled])')", 3000)
    check('删除后重画框可再次保存', redrawn, '' if redrawn else str(page.evaluate("() => { const stage = document.querySelector('#drf-stage-img'); const r = stage.getBoundingClientRect(); return {box: stage.querySelector('.crp-box')?.outerHTML, heading: document.querySelector('.drf-detail h2')?.textContent, hit: document.elementFromPoint(r.x + r.width * .1, r.y + r.height * .2)?.outerHTML.slice(0, 180), stage: r.toJSON(), footer: document.querySelector('.drf-footer')?.getBoundingClientRect().toJSON()}; }")))
    if not redrawn:
        return
    page.locator('[data-action="create.draftSave"]').click()
    wait(page, "() => !document.querySelector('.drf-detail h2')?.textContent.includes('未保存')")
    page.locator(f'[data-action="create.draftCanvasImage"][data-arg="{images[1]["sha256"]}"]').click()
    drag(.2, .18, .78, .7)
    page.locator('[data-action="create.draftSave"]').click()
    wait(page, "() => !document.querySelector('.drf-detail h2')?.textContent.includes('未保存')")
    current = api(base, '/api/drafts/item?id=' + draft['id'])['draft']
    check('两张来源图的框均已保存', current['status'] == 'review'
          and all(row['box'] for row in current['blocks'] if row['kind'] == 'image'))
    page.locator(f'[data-action="create.draftCanvasImage"][data-arg="{images[0]["sha256"]}"]').click()
    page.locator('[data-action="create.draftTrainToggle"]').click()
    page.locator('[data-action="create.draftCanvasMode"][data-arg="training"]').click()
    trained = api(base, '/api/drafts/item?id=' + draft['id'])['draft']
    check('训练开关写入来源图', next(image for image in trained['source_images'] if image['sha256'] == images[0]['sha256'])['train']
          and page.locator('[data-action="create.draftCanvasMode"][data-arg="training"]').get_attribute('aria-pressed') == 'true')
    initial = page.locator('.drf-training-box').count()
    drag(.55, .1, .86, .35)
    check('训练框与正文框分开展示', wait(page, f"() => document.querySelectorAll('.drf-training-box').length === {initial + 1}"))
    page.locator('.drf-training-box').last.locator('[data-action="create.draftTrainingRemove"]').click()
    check('训练框可单独删除', page.locator('.drf-training-box').count() == initial)
    drag(.55, .1, .86, .35)
    page.locator('[data-action="create.draftSave"]').click()
    wait(page, "() => !document.querySelector('.drf-detail h2')?.textContent.includes('未保存')")
    current = api(base, '/api/drafts/item?id=' + draft['id'])['draft']
    task = next(row for row in current['training_tasks'] if row['image_sha'] == images[0]['sha256'])
    check('训练框单独保存且不改正文', len(task['boxes']) == initial + 1 and current['blocks'][1]['kind'] == 'image')
    page.locator('[data-action="create.draftCanvasMode"][data-arg="body"]').click()
    page.locator('[data-action="create.draftExtract"]').click()
    check('局部裁图提交真实提取任务并转文字', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('转文字完成')", 20000)
          and api(base, '/api/drafts/item?id=' + draft['id'])['draft']['blocks'][1]['kind'] == 'text')
    current = api(base, '/api/drafts/item?id=' + draft['id'])['draft']
    check('转文字后原图与训练框仍在', current['blocks'][1]['kind'] == 'text'
          and len(current['source_images']) == 2
          and next(row for row in current['training_tasks'] if row['image_sha'] == images[0]['sha256'])['boxes'])
    page.locator(f'[data-action="create.draftCanvasImage"][data-arg="{images[1]["sha256"]}"]').click()
    page.locator('[data-action="create.draftExtract"]').click()
    check('提取失败保留原图片块和框', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('转文字未完成')", 20000)
          and (lambda row: row['kind'] == 'image' and row['box'] is not None)(
              api(base, '/api/drafts/item?id=' + draft['id'])['draft']['blocks'][2]))
    page.locator('[data-action="create.draftCommit"]').click()
    check('入库后训练图登记且进入下一题', wait(page, f"() => !document.querySelector('.drf-detail .drf-id')?.textContent.includes('{draft['id']}')", 20000)
          and next(row for row in api(base, '/api/drafts/item?id=' + draft['id'])['draft']['training_tasks']
                   if row['image_sha'] == images[0]['sha256'])['status'] == 'registered')
    page.locator('[data-action="create.draftQueueMenu"]').click()
    page.get_by_role('menuitem', name='清理过期草稿', exact=True).click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('清理接口结果按对象字段展示', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已清理')"))


def run_touch(browser, base, vault, results):
    raw = 'data:image/png;base64,' + base64.b64encode(png(123)).decode()
    image = drafts.add_image(vault, raw, 'draft-e2e-conversation', 'run-touch')
    draft = drafts.create_draft(vault, {
        'subject': '数学', 'category': '触摸测试', 'source_images': [image['sha256']],
        'blocks': [{'section': '题目', 'kind': 'image', 'image_sha': image['sha256']}],
    }, {'conversation_id': 'draft-e2e-conversation', 'run_id': 'run-touch', 'tool_call_id': 'tool-touch'})
    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(error.stack or str(error)))
    try:
        page.goto(base + '/?unlocked=1#/create', wait_until='networkidle')
        page.locator('#create-flow [data-ib-stage="drafts"]').click()
        results.append(('手机队列默认收起', not page.locator('.drf-item').first.is_visible(), ''))
        page.locator('[data-action="create.draftToggleQueue"]').click()
        page.locator(f'.drf-item[data-arg="{draft["id"]}"]').click()
        results.append(('手机信息与题目连续阅读', wait(page, "() => !!document.querySelector('.drf-review-question')")
                        and page.locator('.drf-review-question').is_visible()
                        and page.locator('.drf-review-info').is_visible(), ''))
        page.locator('.drf-source-trigger').click()
        results.append(('手机来源入口进入独立工作区', page.locator('.drf-source-workspace').is_visible(), ''))
        stage = page.locator('#drf-stage-img')
        stage.scroll_into_view_if_needed()
        box = stage.bounding_box()
        session = context.new_cdp_session(page)
        x0, y0 = box['x'] + box['width'] * .15, box['y'] + box['height'] * .2
        x1, y1 = box['x'] + box['width'] * .7, box['y'] + box['height'] * .65
        session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'id': 1, 'x': x0, 'y': y0}]})
        for step in range(1, 7):
            session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{
                'id': 1, 'x': x0 + (x1 - x0) * step / 6, 'y': y0 + (y1 - y0) * step / 6}]})
        session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        drawn = wait(page, "() => document.querySelectorAll('#drf-stage-img .crp-box').length === 1")
        if drawn:
            page.locator('[data-action="create.draftSave"]').click()
        saved = api(base, '/api/drafts/item?id=' + draft['id'])['draft']['blocks'][0]['box'] if drawn else None
        results.append(('手机触摸画框并经真实 API 保存', bool(drawn and saved and not errors), str(errors[:2])))
        page.screenshot(path=os.path.join(P3_SHOTS, 'touch-mobile.png'), full_page=True)
    finally:
        context.close()


def main():
    from playwright.sync_api import sync_playwright
    results = []
    os.makedirs(SHOTS, exist_ok=True)
    os.makedirs(P3_SHOTS, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='omrs-drafts-e2e-') as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        first, second, old, images, p3, p3_images = seed(vault)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, '-c', SERVER, vault, str(port)], cwd=ROOT,
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    api(base, '/api/status')
                    break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(error.stack or str(error)))
                try:
                    run(page, base, first, second, old, images, results)
                    run_p3(page, base, p3, p3_images, results)
                    run_touch(browser, base, vault, results)
                    run_discard_queue(browser, base, vault, results)
                except Exception as error:
                    results.append(('草稿主路径执行', False, repr(error)[:500]))
                results.append(('主路径页面脚本无错误', not errors, str(errors[:3])))
                context.close()
                for theme in ('light', 'dark'):
                    for label, width, height in (('desktop', 1440, 900), ('mobile', 390, 844)):
                        audit_context = browser.new_context(viewport={'width': width, 'height': height})
                        audit_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        audit_page = audit_context.new_page()
                        audit_errors = []
                        audit_page.on('pageerror', lambda error: audit_errors.append(str(error)))
                        audit_page.goto(base + '/?unlocked=1#/create', wait_until='networkidle')
                        audit_page.locator('#create-flow [data-ib-stage="drafts"]').click()
                        if width < 760:
                            audit_page.locator('[data-action="create.draftToggleQueue"]').click()
                        first_filter = 'done' if api(base, '/api/drafts/item?id=' + first['id'])['draft']['status'] == 'done' else 'pending'
                        audit_page.locator('[data-change="create.draftFilter"]').select_option(first_filter)
                        if width < 760 and not audit_page.locator(f'.drf-item[data-arg="{first["id"]}"]').is_visible():
                            audit_page.locator('[data-action="create.draftToggleQueue"]').click()
                        audit_page.locator(f'.drf-item[data-arg="{first["id"]}"]').click()
                        wait(audit_page, "() => !!document.querySelector('.drf-review-question')")
                        shot = os.path.join(SHOTS, f'{theme}-{label}.png')
                        audit_page.screenshot(path=shot, full_page=True)
                        findings = audit_page.evaluate(AUDIT)
                        results.append((f'草稿界面 {theme}·{label} 审计与截图',
                                        not audit_errors and not findings['overflow'] and not findings['inline']
                                        and not findings['handlers'] and findings['image'] == 0,
                                        str(findings) + ' ' + shot))
                        p3_filter = 'done' if api(base, '/api/drafts/item?id=' + p3['id'])['draft']['status'] == 'done' else 'pending'
                        if p3_filter != first_filter:
                            if width < 760 and not audit_page.locator('[data-change="create.draftFilter"]').is_visible():
                                audit_page.locator('[data-action="create.draftToggleQueue"]').click()
                            audit_page.locator('[data-change="create.draftFilter"]').select_option(p3_filter)
                        if width < 760 and not audit_page.locator(f'.drf-item[data-arg="{p3["id"]}"]').is_visible():
                            audit_page.locator('[data-action="create.draftToggleQueue"]').click()
                        audit_page.locator(f'.drf-item[data-arg="{p3["id"]}"]').click()
                        audit_page.locator('.drf-source-trigger').click()
                        wait(audit_page, "() => document.querySelectorAll('#drf-stage-img .crp-box').length === 1")
                        p3_shot = os.path.join(P3_SHOTS, f'{theme}-{label}.png')
                        audit_page.screenshot(path=p3_shot, full_page=True)
                        p3_findings = audit_page.evaluate(AUDIT)
                        results.append((f'P3 画布 {theme}·{label} 审计与截图',
                                        not audit_errors and not p3_findings['overflow'] and not p3_findings['inline']
                                        and not p3_findings['handlers'] and p3_findings['image'] == 2,
                                        str(p3_findings) + ' ' + p3_shot))
                        audit_context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    for name, passed, detail in results:
        print(('PASS' if passed else 'FAIL') + ' ' + name + (': ' + detail if detail else ''))
    print(f'{sum(ok for _, ok, _ in results)} / {len(results)}')
    return 0 if results and all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
