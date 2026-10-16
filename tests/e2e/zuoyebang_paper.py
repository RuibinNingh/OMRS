"""独立整卷页面的真实题框、候选隔离、刷新与原图裁切路径。"""
import io
from PIL import Image
from omrs.zuoyebang.geometry import crop_bounds


def verify_paper(page, context, base, photo, output, check, cached_id):
    saved = "() => JSON.parse(sessionStorage.getItem('omrs-zuoyebang-workspace'))"
    page.evaluate('''id => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        const url = new URL(args[0], location.href);
        if (url.pathname === '/api/zuoyebang/record' && url.searchParams.get('id') === id && !window.zybCachedRead) {
          window.zybCachedRead = true;
          await new Promise(resolve => window.zybResumeRead = resolve);
        }
        return response;
      };
    }''', cached_id)
    page.locator('[data-action="zuoyebang.zybSelect"][data-arg="0"]').click()
    page.wait_for_function('() => window.zybCachedRead')
    page.evaluate("window.__omrs.router.go('create')")
    page.wait_for_selector('#panel-create.active')
    page.evaluate("window.__omrs.router.go('zuoyebang')")
    page.wait_for_selector('#panel-zuoyebang.active')
    page.evaluate('() => window.zybResumeRead()')
    page.locator('.zyb-result').wait_for()
    check('缓存预览读取中离页再回来可恢复且不锁死', page.evaluate(saved)['render_id'] == cached_id and page.get_by_role('button', name='下一题', exact=True).is_enabled())
    search_id = page.evaluate(saved)['search_id']
    raw = context.request.get(base + '/api/zuoyebang/image?id=' + search_id + '&role=source')
    check('刷新来源接口保留上传的原图字节和媒体类型', raw.body() == photo.read_bytes() and raw.headers['content-type'].startswith('image/webp'))
    check('原图展示三个返回题框', page.locator('#zyb-paper rect.crp-box').count() == 3)
    page.locator('#zyb-paper rect.crp-box[data-rid="1"]').click()
    page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalWidth===1080")
    check('点击第二题框只显示该位置候选', page.locator('.zyb-candidate').count() == 1 and page.locator('.zyb-candidate').get_attribute('data-arg') == '3')
    second_id = page.evaluate(saved)['render_id']
    page.locator('[data-zyb-field="cause"]').fill('第二题人工核对内容')
    page.locator('[data-action="zuoyebang.zybRegion"][data-arg="0"]').click()
    page.locator('.zyb-result').wait_for()
    page.locator('[data-action="zuoyebang.zybRegion"][data-arg="1"]').click()
    page.wait_for_function("() => document.querySelector('[data-zyb-field=cause]')?.value==='第二题人工核对内容'")
    check('逐题返回复用预览并恢复该题人工编辑', page.evaluate(saved)['render_id'] == second_id)
    page.locator('#zyb-paper rect.crp-box[data-rid="2"]').click()
    check('无匹配题框保留原图入口且不沿用上一题', page.locator('.zyb-candidate').count() == 0 and page.locator('#zyb-rendered-image').count() == 0 and page.get_by_role('button', name='保留原题图片', exact=True).is_enabled())
    page.get_by_label('显示题框', exact=True).uncheck()
    check('隐藏题框保留原图和题号', page.locator('#zyb-paper rect.crp-box').count() == 0 and page.locator('#zyb-paper-image').is_visible() and page.locator('[data-action="zuoyebang.zybRegion"]').count() == 3)
    page.get_by_label('显示题框', exact=True).check()
    page.get_by_role('button', name='调整题框', exact=True).click()
    box = page.locator('#zyb-paper rect.crp-box[data-rid="2"]').bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down(); page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2 - 12, steps=4); page.mouse.up()
    moved = page.evaluate(saved)['boxes']['2']
    check('拖动题框更新原图坐标', moved['y'] < 165 and abs(moved['height'] - 70) < .01)
    handle = page.locator('#zyb-paper [data-rid="2"][data-h="se"]').bounding_box()
    hx, hy = handle['x'] + handle['width'] / 2, handle['y'] + handle['height'] / 2
    page.mouse.move(hx, hy); page.mouse.down(); page.mouse.move(hx - 20, hy - 8, steps=4); page.mouse.up()
    bounds = page.evaluate(saved)['boxes']['2']
    check('控制点缩放题框保留正尺寸且小于原范围', 0 < bounds['width'] < moved['width'] and 0 < bounds['height'] < moved['height'])
    page.get_by_role('button', name='完成调整', exact=True).click()
    page.reload(); page.wait_for_selector('#panel-zuoyebang.active')
    page.wait_for_function("() => document.querySelector('#zyb-paper-image')?.naturalWidth===420")
    check('刷新恢复原图、当前题号与人工调整坐标', page.evaluate(saved)['boxes']['2'] == bounds and page.locator('[data-action="zuoyebang.zybRegion"][data-arg="2"]').get_attribute('aria-pressed') == 'true')
    page.get_by_role('button', name='保留原题图片', exact=True).click()
    page.wait_for_function("() => document.querySelector('#zyb-rendered-image')?.naturalWidth>0")
    identity = page.evaluate(saved)['render_id']
    record = context.request.get(base + '/api/zuoyebang/record?id=' + identity).json()['record']
    cropped = context.request.get(base + record['images']['question']['url']).body()
    with Image.open(io.BytesIO(cropped)) as actual, Image.open(photo) as original:
        expected = original.crop(crop_bounds(bounds, original.width, original.height)).convert('RGB')
        check('保留原题按调整后的原始像素裁切且无虚构答案', actual.tobytes() == expected.tobytes() and record['images']['answer']['empty'])
    page.locator('[data-zyb-field="subject"]').fill('数学')
    page.locator('[data-zyb-field="category"]').fill('原图核对')
    page.get_by_role('button', name='录入 OMRS', exact=True).click()
    page.locator('.zyb-result').wait_for()
    page.get_by_role('button', name='保留原题图片', exact=True).click()
    page.locator('.zyb-result').wait_for()
    check('重复保留相同范围复用已入库回执', page.evaluate(saved)['render_id'] == identity and page.get_by_role('button', name='已录入题库', exact=True).is_disabled())
    page.locator('[data-action="zuoyebang.zybRegion"][data-arg="0"]').click()
    page.locator('.zyb-result').wait_for()
    page.locator('[data-action="zuoyebang.zybRegion"][data-arg="2"]').click()
    page.locator('.zyb-result').wait_for()
    check('返回未匹配题框恢复裁图与逐题完成状态', page.evaluate(saved)['render_id'] == identity and '已录入 2 道' in page.locator('#zyb-queue').inner_text())
    page.locator('#zyb-account').scroll_into_view_if_needed()
    page.screenshot(path=str(output / 'paper-crop-committed.png'), full_page=True)
