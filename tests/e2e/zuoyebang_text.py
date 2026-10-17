"""正文预览／源码与图片占位符：真实编辑、切题、刷新和提交回归。"""
from urllib.parse import urlsplit


SAVED = "() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'))"
QUESTION = '核对公式 $E=mc^2$。\n![[几何示意图.png|320]]'
IMAGES = '''![示意图](https://preview-placeholder.invalid/a(b).png)
![[原图.png|320]]
<img src="data:image/png;base64,AAAA" onerror="window.zybUnsafeImage=1">
data:image/webp;base64,BBBB'''
FORMULA = r'$$\sum_{n=1}^{100} n^2 + \frac{1}{2} + \frac{1}{3} + \frac{1}{4} + \frac{1}{5} + \frac{1}{6} = S$$'


def verify_text(page, output, check):
    answer = page.locator('[data-key="section-answer"]')
    question = page.locator('[data-key="section-question"]')
    requests = []
    def track(request):
        if urlsplit(request.url).path == '/api/image' or 'preview-placeholder.invalid' in request.url:
            requests.append(request.url)
    page.on('request', track)
    original = page.locator('[data-zyb-text="answer"]').input_value()
    text = original + '\n\n' + FORMULA + '\n\n' + IMAGES + '\n<script>window.zybUnsafeImage=1</script>'
    page.locator('[data-zyb-text="answer"]').fill(text)
    page.locator('[data-arg="question:text"]').click()
    check('题目文本默认预览，空正文提供源码入口', '暂无正文' in question.inner_text() and question.locator('[data-zyb-preview]').count() == 1)
    question.get_by_role('button', name='源码', exact=True).click()
    page.locator('[data-zyb-text="question"]').fill(QUESTION)
    before = page.evaluate(SAVED)
    answer.get_by_role('button', name='预览', exact=True).click()
    after = page.evaluate(SAVED)
    preview = answer.locator('[data-zyb-preview="answer"]')
    check('正文预览实际渲染行内与块级公式', preview.locator('.katex').count() >= 2 and preview.locator('.katex-display').count() == 1)
    check('切换视图不更改入库方式、脏状态和编辑版本', after['versions'] == before['versions'] and after['dirty'] == before['dirty'] and after['sections']['answer']['mode'] == before['sections']['answer']['mode'])
    check('两区显示方式独立且切换按钮保留键盘焦点', question.locator('textarea').count() == 1 and answer.get_by_role('button', name='源码', exact=True).evaluate('(el)=>el===document.activeElement'))
    check('预览图片全部缩写且不加载图片或执行HTML', preview.locator('img,script').count() == 0 and '[图片 4]' in preview.inner_text() and 'AAAA' not in preview.inner_text() and page.evaluate('window.zybUnsafeImage === undefined') and not requests)
    answer.get_by_role('button', name='源码', exact=True).click()
    source = page.locator('[data-zyb-text="answer"]')
    compact = source.input_value()
    check('源码缩写图片地址并保留可编辑公式', '[图片 1]' in compact and '$AD=4$' in compact and 'preview-placeholder.invalid' not in compact and 'data:image' not in compact)
    source.fill(compact.replace('[图片 1]\n', ''))
    source.fill(compact + '\n人工补充核对。')
    expected = text + '\n人工补充核对。'
    check('删除后恢复占位符仍保留所有原图片和人工编辑', page.evaluate(SAVED)['sections']['answer']['text'] == expected)
    page.reload(wait_until='networkidle')
    source.wait_for()
    check('刷新恢复源码显示和完整图片原文', source.input_value().endswith('人工补充核对。') and page.evaluate(SAVED)['sections']['answer']['text'] == expected)
    page.locator('[data-action="zuoyebang.zybSelect"][data-arg="1"]').click()
    page.wait_for_function("() => {const s=JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'));return s.selected===1 && s.render_id && !s.job}", timeout=60000)
    page.locator('[data-action="zuoyebang.zybSelect"][data-arg="0"]').click()
    source.wait_for()
    check('切题返回独立恢复两区正文和显示方式', page.evaluate(SAVED)['sections']['question']['text'] == QUESTION and page.evaluate(SAVED)['sections']['answer']['text'] == expected and question.locator('textarea').count() == 1)
    question.get_by_role('button', name='预览', exact=True).click()
    for theme in ('light', 'dark'):
        for width in (1440, 1024, 390, 320):
            page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
            page.set_viewport_size({'width': width, 'height': 1000})
            answer.get_by_role('button', name='预览', exact=True).click()
            page.evaluate('document.fonts.ready')
            check(f'{theme}/{width}正文预览公式可局部滚动且页面不横溢', not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1') and preview.evaluate('(el)=>getComputedStyle(el).overflowX') == 'auto')
            answer.screenshot(path=str(output / f'text-preview-{theme}-{width}.png'))
            answer.get_by_role('button', name='源码', exact=True).click()
            check(f'{theme}/{width}源码编辑无页面横溢且保留图片占位符', not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1') and '[图片 4]' in source.input_value())
            answer.screenshot(path=str(output / f'text-source-{theme}-{width}.png'))
    page.set_viewport_size({'width': 1440, 'height': 1000})
    answer.get_by_role('button', name='预览', exact=True).click()
    page.locator('[data-arg="question:image"]').click()
    check('保留图片和正文显示切换互相独立', question.locator('[data-zyb-preview]').count() == 0 and answer.locator('[data-zyb-preview]').count() == 1 and page.evaluate(SAVED)['sections']['answer']['text'] == expected)
    check('编辑和往返视图未触发任何图片加载', not requests)
    page.remove_listener('request', track)
    return expected


def verify_submitted_text(page, expected, check):
    answer = page.locator('[data-key="section-answer"]')
    answer.get_by_role('button', name='源码', exact=True).click()
    source = answer.locator('textarea')
    check('已入库可切源码复制但不可编辑', source.get_attribute('readonly') is not None and not source.is_editable() and '[图片 4]' in source.input_value())
    answer.get_by_role('button', name='预览', exact=True).click()
    check('已入库可切回公式预览且保存内容仍完整', answer.locator('.katex').count() >= 2 and page.evaluate(SAVED)['sections']['answer']['text'] == expected)
