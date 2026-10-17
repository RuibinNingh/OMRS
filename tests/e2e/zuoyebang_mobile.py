"""手机题图与旧预览升级回归；仅在调用方的临时Vault修改合成记录。"""
from omrs.zuoyebang import store


def verify_mobile(page, context, base, vault, output, check):
    saved = "() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'))"
    page.locator('[data-action="zuoyebang.zybRegion"][data-arg="0"]').click()
    page.locator('.zyb-result').wait_for()
    check('已入库预览没有重新生成入口', page.get_by_role('button', name='重新生成手机版', exact=True).count() == 0)
    page.locator('[data-action="zuoyebang.zybSelect"][data-arg="1"]').click()
    page.wait_for_function("() => {const s=JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'));return s.selected===1 && s.render_id && !s.job}")
    identity = page.evaluate(saved)['render_id']
    record = store.read(vault, identity)
    check('新候选记录保存手机排版和高清倍率', record['layout'] == {'version': 'mobile-360-v1', 'css_width': 360, 'device_scale_factor': 3})
    # 无layout字段是已保存旧记录的兼容形态；PNG和原搜索正文保留原样。
    record.pop('layout')
    store.save(vault, identity, record)
    original_record = (store.location(vault, identity) / 'record.json').read_bytes()
    original_png = (store.location(vault, identity) / 'question.png').read_bytes()
    page.reload(wait_until='networkidle')
    upgrade = page.get_by_role('button', name='重新生成手机版', exact=True)
    upgrade.wait_for()
    check('刷新后旧预览仍可读取并提供主动升级入口', page.evaluate(saved)['render_id'] == identity)
    for width in (320, 390):
        page.set_viewport_size({'width': width, 'height': 1000})
        upgrade.scroll_into_view_if_needed()
        check(f'{width}px旧预览升级入口无横向溢出', not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'))
        page.screenshot(path=str(output / f'legacy-mobile-entry-{width}.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.locator('[data-zyb-field="subject"]').fill('数学')
    page.locator('[data-zyb-field="category"]').fill('手机排版核对')
    page.locator('[data-action="zuoyebang.zybMode"][data-arg="answer:text"]').click()
    page.locator('[data-key="section-answer"]').get_by_role('button', name='源码', exact=True).click()
    page.locator('[data-zyb-text="answer"]').fill('重新生成前核对的答案：5。')
    page.locator('[data-zyb-field="cause"]').fill('保留人工错因')
    requests = []
    def track(request):
        if request.url.endswith('/api/zuoyebang/jobs') and request.method == 'POST':
            requests.append(request.post_data_json['type'])
    page.on('request', track)
    held = []
    def hold_once(route):
        if held:
            route.continue_()
            return
        held.append(True)
        response = route.fetch()
        payload = response.json()
        payload['job']['status'] = 'running'
        route.fulfill(response=response, json=payload)
    page.route('**/api/zuoyebang/job?*', hold_once)
    upgrade.click()
    page.wait_for_function("() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace')).job?.type==='render'")
    page.locator('[data-zyb-text="answer"]').fill('重新生成期间补写的完整答案：5。')
    page.unroute('**/api/zuoyebang/job?*', hold_once)
    page.reload(wait_until='networkidle')
    page.wait_for_function("id => {const s=JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'));return s.render_id && s.render_id!==id && !s.job}", arg=identity, timeout=60000)
    check('重新生成期间刷新仍恢复新版预览与最新人工正文', page.locator('[data-zyb-text="answer"]').input_value() == '重新生成期间补写的完整答案：5。')
    check('重新生成保留科目分类错因及保存方式', page.locator('[data-zyb-field="category"]').input_value() == '手机排版核对' and page.locator('[data-zyb-field="cause"]').input_value() == '保留人工错因' and page.locator('[data-arg="answer:text"]').get_attribute('aria-pressed') == 'true')
    check('升级复用已有搜题正文且只启动一次渲染', requests == ['render'])
    current_id = page.evaluate(saved)['render_id']
    current = context.request.get(base + '/api/zuoyebang/record?id=' + current_id).json()['record']
    check('新版记录包含排版版本且不再提示升级', current['layout']['version'] == 'mobile-360-v1' and upgrade.count() == 0)
    check('旧预览记录和图片未被替换', (store.location(vault, identity) / 'record.json').read_bytes() == original_record and (store.location(vault, identity) / 'question.png').read_bytes() == original_png)
    for role in ('question', 'answer'):
        (output / f'mobile-{role}.png').write_bytes(context.request.get(base + current['images'][role]['url']).body())
    page.locator('#zyb-preview').screenshot(path=str(output / 'mobile-preview.png'))
    page.remove_listener('request', track)
