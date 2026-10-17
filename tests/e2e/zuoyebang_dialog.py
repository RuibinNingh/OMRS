"""大屏并排预览与识别工作窗的真实浏览器回归。"""


def open_review(page):
    page.locator('[data-action="zuoyebang.zybReview"]').click()
    page.locator('.zyb-recognition[open]').wait_for()
    page.wait_for_function("() => !JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace')).job && !document.querySelector('#zyb-dialog-foot [aria-busy=true]')")


def close_review(page):
    page.get_by_role('button', name='关闭识别窗口', exact=True).click()
    page.locator('.zyb-recognition').wait_for(state='detached')


def verify_wide_preview(page, output, check):
    for width in (1500, 1501, 1920, 2550):
        page.set_viewport_size({'width': width, 'height': 1000})
        cards = page.locator('.zyb-preview-card:visible')
        check(f'{width}px预览按可用屏宽切换单双栏', cards.count() == (2 if width > 1500 else 1) and page.locator('.zyb-preview-tabs').is_visible() == (width <= 1500))
        if width > 1500:
            left, right = [cards.nth(i).bounding_box() for i in range(2)]
            check(f'{width}px题目答案并排且页面无横溢', abs(left['y'] - right['y']) < 1 and left['x'] + left['width'] < right['x'] and not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'))
        check(f'{width}px确认前页面只显示单一识别入口', page.locator('#zyb-confirm button').count() == 1 and page.locator('[data-zyb-field]').count() == 0)
    question = page.locator('[data-preview-role=question] .zyb-viewport')
    answer = page.locator('[data-preview-role=answer] .zyb-viewport')
    before = question.evaluate('(el)=>el.scrollTop')
    answer.evaluate('(el)=>el.scrollTop=400')
    check('并排长图独立滚动，答案不带动题目', answer.evaluate('(el)=>el.scrollTop') > 0 and question.evaluate('(el)=>el.scrollTop') == before)
    answer.evaluate('(el)=>el.scrollTop=0')
    page.screenshot(path=str(output / 'wide-preview-2550.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1000})


def verify_review_dialog(page, output, check):
    dialog = page.locator('.zyb-recognition[open]')
    requests = []
    def track(request):
        if request.url.endswith('/api/zuoyebang/jobs') and request.method == 'POST':
            requests.append(request.post_data_json['type'])
    page.on('request', track)
    check('识别窗口具备标题描述与初始焦点', dialog.get_attribute('aria-labelledby') == 'zyb-dialog-title' and page.get_by_role('button', name='关闭识别窗口', exact=True).evaluate('(el)=>el===document.activeElement'))
    page.locator('[data-zyb-field=cause]').fill('识别窗口暂存核对')
    page.locator('[data-zyb-field=subject]').fill('数')
    check('分类建议位于模态顶层内，可点击且不会被背景隔离', dialog.locator('.ui-combobox-menu:not([hidden])').count() == 1)
    page.keyboard.press('Escape')
    check('Escape优先关闭建议，不关闭识别窗口', dialog.count() == 1 and dialog.locator('.ui-combobox-menu:not([hidden])').count() == 0)
    page.locator('[data-zyb-field=subject]').fill('数学')
    dialog.get_by_role('option').filter(has_text='数学').first.click()
    check('建议可选择且不触发入库', page.locator('[data-zyb-field=subject]').input_value() == '数学' and not page.locator('.zyb-result').count())
    page.keyboard.press('Escape')
    page.locator('.zyb-recognition').wait_for(state='detached')
    check('关闭识别窗口返回确认按钮焦点并保留草稿', page.locator('[data-action="zuoyebang.zybReview"]').evaluate('(el)=>el===document.activeElement'))
    open_review(page)
    check('重新打开保留人工内容和识别失败结果', page.locator('[data-zyb-field=cause]').input_value() == '识别窗口暂存核对' and '提取失败' in page.locator('#zyb-dialog-status').inner_text())
    page.reload(wait_until='networkidle')
    dialog.wait_for()
    check('刷新恢复识别窗口和草稿，重开不重复发起识别', page.locator('[data-zyb-field=cause]').input_value() == '识别窗口暂存核对' and not requests)
    page.get_by_role('button', name='关闭识别窗口', exact=True).focus()
    page.keyboard.press('Shift+Tab')
    # Chromium允许从首控件进入浏览器工具栏，此时activeElement为body；背景仍须inert。
    page.locator('.zyb-candidate').first.evaluate('(el)=>el.focus()')
    background_focused = page.evaluate("() => document.activeElement.matches('.zyb-candidate')")
    page.keyboard.press('Tab')
    check('背景控件不可抢焦点，Tab返回识别窗口', not background_focused and page.evaluate("() => document.querySelector('.zyb-recognition').contains(document.activeElement)"))
    for theme in ('light', 'dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
        for width in (1920, 1440, 1024, 390, 320):
            page.set_viewport_size({'width': width, 'height': 900})
            page.evaluate('document.fonts.ready')
            footer = page.locator('#zyb-dialog-foot').bounding_box()
            check(f'{theme}/{width}px识别窗口无横溢，底部操作始终可见', not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1') and footer['y'] >= 0 and footer['y'] + footer['height'] <= 900)
            page.screenshot(path=str(output / f'dialog-{theme}-{width}.png'))
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.remove_listener('request', track)
