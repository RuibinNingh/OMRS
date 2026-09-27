"""录入题目 E2E：工作区导航、上传与收件箱网格、框选、题卡创建、AI 训练与策略、快速录入主路径，以及五个工作区的四种审计。"""
import os
import json
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from browser_runtime import launch_chromium

AUDIT = """target => {
  const root = document.querySelector('#ib-stage-quick');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('.katex'));
  const text = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(text)
    .map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a,b) => a-b);
  const hit = e => ['BUTTON','INPUT','SELECT','SUMMARY'].includes(e.tagName) || e.getAttribute('role') === 'button';
  const tappable = e => e.matches('input[type="file"], input[type="checkbox"]') && e.closest('label') ? e.closest('label') : e;
  const small = shown.filter(hit).filter(e => { const r=tappable(e).getBoundingClientRect(); return r.width && r.height < target; })
    .map(e => `${e.tagName}#${e.id}.${e.className}:${Math.round(tappable(e).getBoundingClientRect().height)}`);
  const inline = shown.filter(e => (e.getAttribute('style') || '').trim()).length;
  const handlers = shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length;
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible')
    .map(e => `${e.tagName}#${e.id}.${e.className}: ${e.scrollWidth}/${e.clientWidth}`);
  return { sizes, small, inline, handlers, over, overflow: document.documentElement.scrollWidth > innerWidth + 1, shown: shown.length };
}"""
AUDIT_UPLOAD = AUDIT.replace("'#ib-stage-quick'", "'#ib-stage-upload'")
AUDIT_CARDS = AUDIT.replace("'#ib-stage-quick'", "'#ib-stage-create'")
AUDIT_TRAIN = AUDIT.replace("'#ib-stage-quick'", "'#ib-stage-train'")
AUDIT_PROCESS = AUDIT.replace("'#ib-stage-quick'", "'#ib-stage-process'").replace(
  "return { sizes, small, inline, handlers, over, overflow:",
  "const tiny = shown.filter(text).filter(e => parseFloat(getComputedStyle(e).fontSize) < 12).map(e => `${e.tagName}.${e.className}:${e.textContent.trim().slice(0, 24)}`); return { tiny, sizes, small, inline, handlers, over, overflow:")


def png(shade=255):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = b''.join(b'\0' + bytes([shade]) * 3 * 64 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


def wait(page, expr, timeout=8000):
    try:
        page.wait_for_function(expr, timeout=timeout)
        return True
    except Exception:
        return False


def guarded(results, name, action):
    try:
        action()
    except Exception as error:
        results.append((name + '：执行出错', False, repr(error)[:300]))


def run(page, base, results):
    def check(name, ok):
        results.append((name, bool(ok), ''))

    page.goto(base + '/#/create', wait_until='networkidle')
    check('录入页由 features/create 注册并显示五个工作区',
          wait(page, "() => document.querySelectorAll('#create-flow button[data-ib-stage]').length === 5")
          and page.locator('#create-flow [aria-current="step"]').count() == 1)
    check('工作区导航与上传区没有行内事件和样式',
          page.locator('#create-flow [onclick]').count() == 0
          and page.locator('#create-flow button svg').count() == 2
          and page.locator('#create-upload [onclick], #create-upload [style]').count() == 0)
    page.locator('#ib-file').set_input_files({'name': '说明.txt', 'mimeType': 'text/plain', 'buffer': b'not an image'})
    check('非图片文件在上传区就地提示', wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('请选择图片文件')"))
    page.locator('#ib-file').set_input_files({'name': '题图.png', 'mimeType': 'image/png', 'buffer': png()})
    check('上传进入暂存收件箱并更新待处理数',
          wait(page, "() => document.querySelector('#ib-c-pending')?.textContent === '1'")
          and page.locator('.crw-inbox__grid [data-action="create.gridOpen"]').count() == 1)
    page.evaluate("""bytes => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], '题图.png', { type: 'image/png' }));
      document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    }""", list(png()))
    check('上传区粘贴图片走同一暂存入口，重复图自动合并',
          wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('已合并')")
          and page.locator('.crw-inbox__grid [data-action="create.gridOpen"]').count() == 1)
    page.route('**/api/inbox/upload', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"上传服务暂不可用"}'))
    page.locator('#ib-file').set_input_files({'name': '另一张.png', 'mimeType': 'image/png', 'buffer': png()})
    check('上传失败保留已有收件箱并在控件旁显示原因',
          wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('上传服务暂不可用')")
          and page.locator('.crw-inbox__grid [data-action="create.gridOpen"]').count() == 1)
    page.unroute('**/api/inbox/upload')
    page.locator('[data-action="create.gridFilter"][data-arg="boxed"]').click()
    check('收件箱状态筛选显示空态', page.locator('.crw-inbox__empty').count() == 1)
    page.locator('[data-action="create.gridFilter"][data-arg="all"]').click()
    page.locator('[data-change="create.gridAll"]').check()
    check('全选当前筛选后显示批量操作', page.locator('.crw-inbox__batch.is-open').count() == 1
          and page.locator('.crw-inbox__batch strong').inner_text() == '1 张已选')
    page.locator('[data-action="create.gridClear"]').click()
    check('清空选择后批量操作收起', page.locator('.crw-inbox__batch.is-open').count() == 0
          and not page.locator('[data-change="create.gridAll"]').is_checked())
    page.locator('[data-change="create.gridAll"]').check()
    page.locator('[data-action="create.gridWhole"]').click()
    check('整图批量框选写回旧处理队列并显示框位预览',
          wait(page, "() => !!document.querySelector('.crw-grid-item__status [data-status=\"boxed\"]') && !!document.querySelector('.crw-grid-item__thumb svg rect[data-role=\"question\"]')"))
    page.locator('[data-action="create.gridOpenSelected"]').click()
    check('批量去处理打开所选图片', page.locator('#ib-stage-process').evaluate('(e) => getComputedStyle(e).display !== "none"')
          and page.locator('#ib-pc-fname').inner_text().startswith('题图.png'))
    page.locator('[data-action="create.processClearBoxes"]').click()
    stage = page.locator('#ib-stage-img').bounding_box()
    def draw(x0, y0, x1, y1):
        page.mouse.move(stage['x'] + stage['width'] * x0, stage['y'] + stage['height'] * y0)
        page.mouse.down()
        page.mouse.move(stage['x'] + stage['width'] * x1, stage['y'] + stage['height'] * y1, steps=4)
        page.mouse.up()
    draw(.08, .12, .40, .42)
    check('指针框选生成题目区域与区域卡片',
          wait(page, "() => !!document.querySelector('.crp-box[data-role=\"question\"]') && document.querySelectorAll('#ib-ps-body [data-ib-rg]').length === 1"))
    page.keyboard.press('Escape')
    page.locator('[data-action="create.processRole"][data-arg="answer"]').click()
    draw(.52, .55, .88, .84)
    check('切换角色后框选答案区域',
          wait(page, "() => !!document.querySelector('.crp-box[data-role=\"answer\"]') && document.querySelectorAll('#ib-ps-body [data-ib-rg]').length === 2"))
    page.keyboard.press('Delete')
    check('处理工作区 Delete 只删除当前选中框',
          wait(page, "() => document.querySelectorAll('#ib-ps-body [data-ib-rg]').length === 1 && !document.querySelector('.crp-box[data-role=\"answer\"]')"))
    page.locator('#ib-layout').select_option('photo')
    page.evaluate("window.__omrs.router.go('settings')")
    check('离开框选工作区前写出未到防抖时间的版式', wait(page, """async () => {
      const data = await (await fetch('/api/inbox/items')).json();
      return data.items.some(item => item.file === '题图.png' && item.layout === 'photo');
    }"""))
    page.evaluate("window.__omrs.router.go('create')")
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('[data-action="create.gridOpen"]').click()
    check('点击图片进入对应处理队列', page.locator('#ib-stage-process').evaluate('(e) => getComputedStyle(e).display !== "none"')
          and page.locator('#ib-pc-fname').inner_text().startswith('题图.png'))
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('#create-flow [data-ib-stage="process"]').focus()
    page.keyboard.press('Enter')
    check('键盘可进入处理工作区', page.locator('#ib-stage-process').evaluate('(e) => getComputedStyle(e).display !== "none"')
          and page.locator('#create-flow [data-ib-stage="process"]').get_attribute('aria-current') == 'step')
    page.locator('#create-flow [data-ib-stage="quick"]').click()
    check('快速录入工作区可打开', page.locator('#ib-stage-quick').evaluate('(e) => getComputedStyle(e).display !== "none"'))
    page.evaluate("window.__omrs.router.go('settings'); window.__omrs.router.go('create')")
    check('离开再返回仍停在原工作区', page.locator('#create-flow [data-ib-stage="quick"]').get_attribute('aria-current') == 'step'
          and page.locator('#ib-stage-quick').evaluate('(e) => getComputedStyle(e).display !== "none"'))
    page.fill('#cr-subject', '数学')
    page.fill('#cr-category', '函数')
    page.fill('#cr-question', '求函数的定义域')
    page.fill('#cr-answer', '全体实数')
    page.click('[data-action="create.submit"]')
    check('快速录入成功写入题库', wait(page, "() => !!document.querySelector('#cr-result .crw-result.is-success')"))
    check('提交后保留科目分类并清空题目内容',
          page.locator('#cr-subject').input_value() == '数学'
          and page.locator('#cr-category').input_value() == '函数'
          and page.locator('#cr-question').input_value() == ''
          and page.locator('#cr-answer').input_value() == '')
    page.locator('#cr-q-file').set_input_files({'name': '题目.png', 'mimeType': 'image/png', 'buffer': png()})
    page.locator('#cr-a-file').set_input_files({'name': '答案.png', 'mimeType': 'image/png', 'buffer': png()})
    check('题目与答案图片区各自暂存图片',
          wait(page, "() => document.querySelectorAll('#cr-q-images img').length === 1 && document.querySelectorAll('#cr-a-images img').length === 1"))
    page.evaluate("""bytes => {
      document.querySelector('#cr-a-paste').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], '粘贴答案.png', { type: 'image/png' }));
      document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    }""", list(png()))
    check('切换粘贴目标后图片进入答案区',
          wait(page, "() => document.querySelectorAll('#cr-a-images img').length === 2")
          and page.locator('#cr-q-images img').count() == 1)
    calls = []

    def ai_result(route):
        body = route.request.post_data_json
        calls.append(body)
        mode = body.get('mode')
        if mode == 'classify':
            data = {'subject': '物理', 'category': '动力学', 'difficulty': 7, 'knowledge_tags': ['定义域'], 'labels': []}
        elif mode == 'question_text':
            data = {'mode': mode, 'question_text': '求 $f(x)$ 的定义域'}
        else:
            data = {'mode': mode, 'answer': '答案：全体实数'}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data, ensure_ascii=False))

    page.route('**/api/ai-recognize', ai_result)
    page.click('#cr-classify-btn')
    check('分类识别保留已填科目分类并合并知识点',
          wait(page, "() => document.querySelector('#cr-related')?.value.includes('定义域')")
          and page.locator('#cr-subject').input_value() == '数学'
          and page.locator('#cr-category').input_value() == '函数'
          and page.locator('#cr-diff').input_value() == '7')
    page.click('#cr-question-text-btn')
    page.click('#cr-extract-btn')
    check('题面和答案提取使用各自第一张图片',
          wait(page, "() => document.querySelector('#cr-question')?.value === '求 $f(x)$ 的定义域' && document.querySelector('#cr-answer')?.value === '答案：全体实数'")
          and page.locator('#cr-question').input_value() == '求 $f(x)$ 的定义域'
          and page.locator('#cr-answer').input_value() == '答案：全体实数'
          and [call['mode'] for call in calls] == ['classify', 'question_text', 'answer']
          and all(call.get('image', call.get('question_image', '')).startswith('data:image/png;base64,') for call in calls))
    page.click('[data-action="create.submit"]')
    check('含图提交后上下文仍保留、图片已清空且可加入展示板',
          wait(page, "() => !!document.querySelector('#cr-result .crw-result.is-success') && document.querySelectorAll('#cr-q-images img, #cr-a-images img').length === 0")
          and page.locator('#cr-subject').input_value() == '数学'
          and page.locator('#cr-category').input_value() == '函数'
          and page.locator('#cr-related').input_value() == '定义域'
          and page.locator('[data-action="create.boardAdd"]').count() == 1)
    page.unroute('**/api/ai-recognize')
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('[data-change="create.gridSelect"]').check()
    page.route('**/api/inbox/discard', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"模拟丢弃故障"}'))
    page.locator('[data-action="create.gridDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('批量丢弃失败保留选择并就地提示', wait(page, "() => document.querySelector('.crw-inbox__error')?.textContent.includes('模拟丢弃故障')")
          and page.locator('[data-change="create.gridSelect"]').is_checked())
    page.unroute('**/api/inbox/discard')
    page.locator('[data-action="create.gridDiscard"]').click()
    page.locator('dialog[open] [data-dialog-cancel]').last.click()
    check('取消批量丢弃保留图片', page.locator('[data-action="create.gridOpen"]').count() == 1)
    page.locator('[data-action="create.gridDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('确认批量丢弃后网格与选择同步清空', wait(page, "() => document.querySelectorAll('.crw-inbox__grid [data-action=\"create.gridOpen\"]').length === 0")
          and page.locator('.crw-inbox__batch.is-open').count() == 0)


READY_JS = """async ([file, text]) => {
  const items = (await (await fetch('/api/inbox/items')).json()).items;
  const item = items.find(row => row.file === file);
  const regions = [
    { id: 'rq_' + item.id, card: 1, role: 'question', x: 0, y: 0, w: 1, h: .5, origin: 'manual', convert: 'text', text, text_status: 'done' },
    { id: 'ra_' + item.id, card: 1, role: 'answer', x: 0, y: .5, w: 1, h: .5, origin: 'manual', convert: 'image', text_status: 'none' },
  ];
  const res = await fetch('/api/inbox/item/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: item.id, regions, status: 'ready' }) });
  return res.ok;
}"""

INBOX_JS = """async file => (await (await fetch('/api/inbox/items')).json()).items.find(row => row.file === file) || null"""


def quiet(page):
    """等提示条消失再点题卡底部的按钮：右下角的提示条可能正好盖住它们。
    鼠标停在提示条上会暂停计时，所以先把鼠标移开。"""
    page.mouse.move(5, 5)
    wait(page, "() => !document.querySelector('.ui-toast')", 12000)


def upload(page, name, shade):
    page.locator('#ib-file').set_input_files({'name': name, 'mimeType': 'image/png', 'buffer': png(shade)})
    wait(page, f"() => [...document.querySelectorAll('.crw-grid-item strong')].some(e => e.textContent.includes('{name}'))")


def run_cards(page, base, results):
    def check(name, ok):
        results.append((name, bool(ok), ''))

    page.goto(base + '/#/create', wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    upload(page, '题卡.png', 90)
    page.locator('.crw-grid-item', has_text='题卡.png').locator('[data-action="create.gridOpen"]').click()
    page.locator('[data-action="create.processWholeImage"]').click()
    check('整图即题目在区域面板显示题目区域', wait(page, "() => document.querySelectorAll('#ib-ps-body [data-ib-rg]').length === 1"))
    page.locator('#ib-ps-body [data-action="create.processConvert"][data-arg$=":image"]').click()
    check('保留图片的区域画出裁图预览', wait(page, "() => !!document.querySelector('#ib-ps-body canvas[data-crop][data-painted]') && document.querySelector('#ib-ps-body canvas[data-crop]').width > 1"))
    page.locator('[data-action="create.processMarkReady"]').click()
    check('标记就绪后「录入」计数加一', wait(page, "() => document.querySelector('#ib-c-ready')?.textContent === '1'"))
    page.locator('#create-flow [data-ib-stage="create"]').click()
    check('题卡工作区列出就绪题卡并画出裁图', wait(page, "() => document.querySelectorAll('#ib-stage-create .crc-card').length === 1 && !!document.querySelector('#ib-stage-create canvas[data-crop][data-painted]')")
          and '1 张题卡待创建' in page.locator('#ib-cr-count').inner_text())
    check('题卡工作区没有行内样式与行内事件', page.locator('#ib-stage-create [style], #ib-stage-create [onclick], #ib-stage-create [onchange]').count() == 0)
    card = page.locator('#ib-stage-create .crc-card').first
    quiet(page)
    card.locator('[data-action="create.cardCommit"]').click()
    check('缺科目分类时不提交并提示', wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(e => e.textContent.includes('科目和分类是必填项'))")
          and page.locator('#ib-stage-create .crc-card').count() == 1)
    card.locator('input[data-arg$="|subject"]').fill('数学')
    card.locator('input[data-arg$="|category"]').fill('函数')
    card.locator('input[data-arg$="|tags"]').fill('定义域，值域')
    card.locator('input[type="range"]').fill('8')
    check('题卡字段即时更新写入路径与难度', card.locator('.crc-path').inner_text() == '→ 错题/数学/函数/函数N.md'
          and card.locator('.crc-range output').inner_text() == '8')
    check('题卡字段去抖写回收件箱', wait(page, """async () => {
      const item = (await (await fetch('/api/inbox/items')).json()).items.find(row => row.file === '题卡.png');
      const form = item?.cards?.['1'];
      return form?.subject === '数学' && form?.category === '函数' && form?.difficulty === 8 && form?.tags?.join() === '定义域,值域';
    }""", 5000))
    jobs = []

    def job_create(route):
        jobs.append(route.request.post_data_json)
        route.fulfill(status=200, content_type='application/json', body='{"job":{"id":"e2e-job"}}')

    quiet(page)
    page.route('**/api/inbox/jobs', job_create)
    page.route('**/api/inbox/job?*', lambda route: route.fulfill(status=200, content_type='application/json', body='{"job":{"id":"e2e-job","status":"done","errors":[]}}'))
    card.locator('[data-action="create.cardClassify"]').click()
    check('AI 识别题目信息提交 classify 任务并带题目裁图',
          wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(e => e.textContent.includes('只填空缺项'))")
          and jobs and jobs[0].get('type') == 'classify' and jobs[0]['cards'][0]['crop'].startswith('data:image/png;base64,'))
    page.unroute('**/api/inbox/jobs')
    page.unroute('**/api/inbox/job?*')
    quiet(page)
    page.locator('#ib-stage-create .crc-card [data-action="create.cardBack"]').click()
    check('退回处理回到处理区并恢复为已框选', wait(page, "() => document.querySelector('#ib-stage-process')?.classList.contains('on') && document.querySelector('#ib-c-boxed')?.textContent === '1'")
          and page.locator('#ib-pc-fname').inner_text().startswith('题卡.png'))
    page.locator('[data-action="create.processMarkReady"]').click()
    wait(page, "() => document.querySelector('#ib-c-ready')?.textContent === '1'")
    page.locator('#create-flow [data-ib-stage="create"]').click()
    wait(page, "() => document.querySelectorAll('#ib-stage-create .crc-card').length === 1")
    check('退回再就绪后题卡字段仍保留', page.locator('#ib-stage-create input[data-arg$="|subject"]').input_value() == '数学')
    quiet(page)
    page.locator('#ib-stage-create [data-action="create.cardCommit"]').click()
    check('创建题目写入题库并出现「加入展示板」', wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(e => e.textContent.includes('已创建') && e.textContent.includes('加入展示板'))")
          and wait(page, "() => !!document.querySelector('#ib-stage-create .ui-empty') && document.querySelector('#ib-c-ready')?.textContent === '0'"))
    created = page.evaluate(INBOX_JS, '题卡.png')
    check('收件箱图片转为已录入并关联题目', created and created['status'] == 'done' and (created.get('cards') or {}).get('1', {}).get('created_uid'))
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    upload(page, '批量一.png', 120)
    upload(page, '批量二.png', 150)
    check('测试数据：两张图经接口置为就绪', page.evaluate(READY_JS, ['批量一.png', '题面 $x^2$']) and page.evaluate(READY_JS, ['批量二.png', '另一题']))
    page.evaluate("window.__omrs.router.go('settings'); window.__omrs.router.go('create')")
    page.locator('#create-flow [data-ib-stage="create"]').click()
    check('就绪图片重读后出现在题卡工作区', wait(page, "() => document.querySelectorAll('#ib-stage-create .crc-card').length === 2 && !!document.querySelector('#ib-stage-create .crc-text .katex')"))
    for index in range(2):
        row = page.locator('#ib-stage-create .crc-card').nth(index)
        row.locator('input[data-arg$="|subject"]').fill('物理')
        row.locator('input[data-arg$="|category"]').fill('力学')
    page.locator('#ib-cr-all').check()
    check('全选后批量按钮可用', not page.locator('[data-action="create.cardCommitSelected"]').is_disabled())
    page.locator('[data-action="create.cardCommitSelected"]').click()
    check('批量创建只弹一条汇总并可一次加入展示板', wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(e => e.textContent.includes('已创建 2 道题目') && e.textContent.includes('加入展示板（2 题）'))")
          and wait(page, "() => document.querySelectorAll('#ib-stage-create .crc-card').length === 0"))
    stats = page.evaluate("async () => (await (await fetch('/api/stats')).json()).items.filter(item => item.subject === '物理' || item.subject === '数学').length")
    check('三道题都进了题库', stats >= 3)


def run_train(page, base, results):
    def check(name, ok):
        results.append((name, bool(ok), ''))

    page.goto(base + '/#/create', wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="train"]').click()
    check('AI 训练读取数据集统计', wait(page, "() => /^\\d+$/.test(document.querySelector('[data-stat=\"imgs\"] .ui-stat__value')?.textContent.trim() || '') && document.querySelectorAll('#ib-stage-train .crt-bar progress').length >= 2"))
    check('训练工作区没有行内样式与行内事件', page.locator('#ib-stage-train [style], #ib-stage-train [onclick], #ib-stage-train [onchange]').count() == 0)
    check('导出链接默认 OMRS JSONL', page.locator('#ib-tr-export').get_attribute('href').endswith('format=omrs_jsonl'))
    page.locator('#ib-tr-fmt').select_option('yolo')
    check('切换导出格式更新链接', page.locator('#ib-tr-export').get_attribute('href').endswith('format=yolo'))
    check('默认提供方隐藏本地检测地址', wait(page, "() => !!document.querySelector('#ib-pl-provider')") and page.locator('#ib-pl-local-row').is_hidden())
    page.locator('#ib-pl-provider').select_option('local_http')
    check('选本地检测服务后显示地址输入', page.locator('#ib-pl-local-row').is_visible())
    page.locator('#ib-pl-local').fill('http://127.0.0.1:8600/detect')
    page.locator('#ib-pl-blind').fill('3')
    page.locator('#ib-pl-conf').fill('1.5')
    page.locator('label.ui-switch:has(#ib-pl-upload)').click()
    page.locator('[data-action="create.trainSave"]').click()
    check('保存策略就地提示成功', wait(page, "() => document.querySelector('#ib-pl-status')?.textContent.includes('已保存')"))
    config = page.evaluate("async () => (await fetch('/api/config')).json()")
    check('策略写入配置并夹取阈值', config.get('inbox_detect_provider') == 'local_http' and config.get('inbox_local_detect_url') == 'http://127.0.0.1:8600/detect'
          and config.get('inbox_blind_every') == 3 and config.get('inbox_auto_ready_conf') == 1 and config.get('inbox_auto_on_upload') is True)
    page.evaluate("window.__omrs.router.go('settings'); window.__omrs.router.go('create')")
    check('返回训练工作区重读策略', wait(page, "() => document.querySelector('#ib-pl-provider')?.value === 'local_http' && document.querySelector('#ib-pl-blind')?.value === '3'"))
    page.locator('[data-action="create.trainCleanup"][data-arg="crops"]').click()
    page.locator('dialog[open] [data-dialog-cancel]').last.click()
    page.locator('[data-action="create.trainCleanup"][data-arg="crops"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('清空裁图缓存经确认后提示结果', wait(page, "() => [...document.querySelectorAll('.ui-toast')].some(e => e.textContent.includes('裁图缓存'))"))
    page.route('**/api/inbox/dataset/stats', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"统计服务故障"}'))
    page.locator('#ib-stage-train .crt-row [data-action="create.trainRefresh"]').click()
    check('统计读取失败就地显示原因并可重试', wait(page, "() => document.querySelector('#ib-stage-train .crt-error')?.textContent.includes('统计服务故障')"))
    page.unroute('**/api/inbox/dataset/stats')
    page.locator('#ib-stage-train .crt-error [data-action="create.trainRefresh"]').click()
    check('重试成功后错误消失', wait(page, "() => !document.querySelector('#ib-stage-train .crt-error')"))


def main():
    from playwright.sync_api import sync_playwright
    results = []
    with tempfile.TemporaryDirectory(prefix='omrs-create-e2e-') as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'omrs_engine.py'), '--vault', vault, 'serve', '--port', str(port)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=.2).close()
                    break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                guarded(results, '录入题目主路径', lambda: run(page, f'http://127.0.0.1:{port}', results))
                guarded(results, '题卡工作区', lambda: run_cards(page, f'http://127.0.0.1:{port}', results))
                guarded(results, 'AI 训练工作区', lambda: run_train(page, f'http://127.0.0.1:{port}', results))
                results.append(('页面脚本错误为零', not errors, str(errors[:3])))
                context.close()
                for theme in ('light', 'dark'):
                    for label, viewport, target in (('桌面', (1440, 900), 28), ('手机', (390, 844), 40)):
                        audit_context = browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]})
                        audit_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        audit_page = audit_context.new_page()
                        audit_page.goto(f'http://127.0.0.1:{port}/#/create', wait_until='networkidle')
                        wait(audit_page, "() => !!document.querySelector('#create-grid .crw-inbox__filters') && !!document.querySelector('#create-upload .ui-filedrop') && document.querySelector('#panel-create')?.classList.contains('active') && document.querySelector('#ib-stage-upload')?.classList.contains('on')")
                        audit_page.locator('#ib-file').set_input_files({'name': f'审计-{theme}-{label}.png', 'mimeType': 'image/png', 'buffer': png(180 + len(results) % 60)})
                        wait(audit_page, "() => document.querySelectorAll('.crw-inbox__grid .crw-grid-item').length > 0")
                        upload_audit = audit_page.evaluate(AUDIT_UPLOAD, target)
                        upload_ok = upload_audit['shown'] >= 50 and len(upload_audit['sizes']) <= 6 and min(upload_audit['sizes']) >= 12 and not any(
                            upload_audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'收件箱网格审计 {label}·{theme}', upload_ok, str(upload_audit)))
                        audit_page.locator('#create-flow [data-ib-stage="process"]').click()
                        wait(audit_page, "() => !!document.querySelector('#ib-stage-process .ib-pq-row') && !!document.querySelector('#ib-stage-process .crp-overlay')")
                        process_audit = audit_page.evaluate(AUDIT_PROCESS, target)
                        process_ok = len(process_audit['sizes']) <= 6 and min(process_audit['sizes']) >= 12 and not any(
                            process_audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'框选工作区审计 {label}·{theme}', process_ok, str(process_audit)))
                        audit_page.evaluate(READY_JS, [f'审计-{theme}-{label}.png', '已知 $f(x)=x^2$，求 $f(2)$。'])
                        audit_page.evaluate("window.__omrs.router.go('settings'); window.__omrs.router.go('create')")
                        audit_page.locator('#create-flow [data-ib-stage="create"]').click()
                        wait(audit_page, "() => !!document.querySelector('#ib-stage-create .crc-card canvas[data-painted]') && !!document.querySelector('#ib-stage-create .katex')")
                        cards_audit = audit_page.evaluate(AUDIT_CARDS, target)
                        cards_ok = cards_audit['shown'] >= 30 and len(cards_audit['sizes']) <= 6 and min(cards_audit['sizes']) >= 12 and not any(
                            cards_audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'题卡工作区审计 {label}·{theme}', cards_ok, str(cards_audit)))
                        audit_page.locator('#create-flow [data-ib-stage="train"]').click()
                        wait(audit_page, "() => !!document.querySelector('#ib-pl-provider') && !document.querySelector('#ib-stage-train [aria-busy=\"true\"]')")
                        train_audit = audit_page.evaluate(AUDIT_TRAIN, target)
                        train_ok = train_audit['shown'] >= 50 and len(train_audit['sizes']) <= 6 and min(train_audit['sizes']) >= 12 and not any(
                            train_audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'AI 训练审计 {label}·{theme}', train_ok, str(train_audit)))
                        audit_page.locator('#create-flow [data-ib-stage="quick"]').click()
                        audit = audit_page.evaluate(AUDIT, target)
                        ok = len(audit['sizes']) <= 6 and min(audit['sizes']) >= 12 and not any(
                            audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'快速录入审计 {label}·{theme}', ok, str(audit)))
                        audit_context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    for name, passed, detail in results:
        print(('PASS' if passed else 'FAIL') + ' ' + name + (': ' + detail if detail else ''))
    print(f'{sum(ok for _, ok, _ in results)} / {len(results)}')
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
