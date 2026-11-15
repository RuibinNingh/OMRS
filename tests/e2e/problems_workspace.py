"""真实问题工作台：大量浏览、批量操作、删除恢复、草稿与响应式布局。"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import uuid
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from omrs import problems
from omrs.creation import create_question
from omrs.data_repository import mastery_rows

spec = importlib.util.spec_from_file_location('visual_run', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'ok': bool(condition), 'detail': detail})
        print(name, bool(condition), flush=True)
        assert condition, (name, detail)

    with tempfile.TemporaryDirectory(prefix='omrs-problem-workspace-') as vault:
        for n in range(4):
            create_question(vault, '数学', '工作台合成题', 5, question_text=f'求函数 f(x)=x²-{n} 的最小值。', answer_text='先检查定义域。')
        values = visual.seed_problems_fixture(vault)
        baseline = mastery_rows(vault)
        proc, port = visual.start_server(str(ROOT), vault, str(out / 'server.log'))
        base = f'http://127.0.0.1:{port}'
        try:
            with sync_playwright() as pw:
                browser = launch_chromium(pw)
                context = browser.new_context(viewport={'width': 1440, 'height': 960})
                page = context.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda e: errors.append(e.text) if e.type == 'error' and e.text.startswith('[shell]') else None)
                open_app(page, base, 'problems')

                def ready():
                    try:
                        page.wait_for_function("document.querySelector('.prb-items')?.getAttribute('aria-busy') === 'false' || !!document.querySelector('.prb-empty h2')")
                    except Exception:
                        page.screenshot(path=str(out / 'failure.png'))
                        (out / 'failure.txt').write_text(page.locator('body').inner_text())
                        raise

                def filtered(key):
                    page.locator(f'[data-prb="filter"][data-value="{key}"]').click()
                    ready()

                def accept():
                    page.locator('dialog[open]').last.locator('[data-dialog-ok]').click()
                    page.wait_for_function("!document.querySelector('dialog.is-closing')")

                ready()
                check('137个问题使用25条分页', page.locator('[data-prb="open"]').count() == 25 and '137' in page.locator('.prb-pagination').inner_text())
                check('默认列表占满工作区', page.locator('.prb-list').bounding_box()['width'] > 1000)
                page.locator('[data-prb="new"]').first.click()
                check('打开新建表单不立即落库', problems.search(vault)['total'] == 137)
                page.locator('[data-prb="cancel"]').click(); accept()
                page.wait_for_function("!document.querySelector('.prb-detail')")
                check('取消新建不留下占位问题', problems.search(vault)['total'] == 137)
                page.evaluate('document.fonts.ready')
                page.screenshot(path=str(out / 'list-light-desktop.png'))
                box = page.locator('.prb-scroll').bounding_box()
                page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                page.mouse.wheel(0, 600)
                page.wait_for_function("document.querySelector('.prb-scroll').scrollTop > 100")
                check('大量问题可滚轮浏览且分页保持可见', page.locator('.prb-pagination').bounding_box()['y'] < 960 and page.evaluate('window.scrollY') == 0)
                page.locator('.prb-scroll').evaluate('(e)=>e.scrollTop=0')
                first_id = page.locator('[data-prb="open"]').first.get_attribute('data-id')
                page.locator('[data-prb="next"]').click(); ready()
                check('下一页展示不同问题', page.locator('[data-prb="open"]').first.get_attribute('data-id') != first_id)
                page.locator('[data-prb="prev"]').click(); ready()
                check('上一页恢复原列表', page.locator('[data-prb="open"]').first.get_attribute('data-id') == first_id)
                page.locator('[data-prb-field="limit"]').select_option('100'); ready()
                check('可一次查看100个问题', page.locator('[data-prb="open"]').count() == 100)
                page.locator('[data-prb-field="limit"]').select_option('25'); ready()
                page.keyboard.press('/')
                check('斜杠聚焦搜索', page.locator('[data-prb-field="query"]').evaluate('(e)=>e===document.activeElement'))
                page.locator('[data-prb-field="query"]').fill('区间端点'); ready()
                check('搜索覆盖整个问题库', page.locator('[data-prb="open"]').count() == 14)
                page.locator('[data-prb-field="query"]').fill('完全不存在的关键词'); ready()
                check('无匹配结果提供清空入口', page.locator('.prb-empty h2').inner_text() == '没有找到匹配的问题')
                page.locator('[data-prb-field="query"]').fill(''); ready()
                filtered('working')
                check('状态筛选与计数一致', page.locator('[data-prb="filter"][data-value="working"] span').inner_text() == '28' and page.locator('.prb-list-caption').inner_text().startswith('处理中28'))
                filtered('')
                page.locator('[data-prb-field="sort"]').select_option('title'); ready()
                expected = problems.search(vault, sort='title')['items'][0]['id']
                check('标题排序由服务端应用', page.locator('[data-prb="open"]').first.get_attribute('data-id') == expected)
                ids = page.locator('[data-prb-check]').evaluate_all('(es)=>es.slice(0,2).map(e=>e.dataset.prbCheck)')
                for pid in ids:
                    page.locator(f'[data-prb-check="{pid}"]').check()
                check('勾选后出现批量操作栏', '已选 2 项' in page.locator('.prb-bulk').inner_text())
                page.screenshot(path=str(out / 'selection-light-desktop.png'))
                page.locator('[data-prb="next"]').click(); ready()
                check('跨页保留明确勾选', '已选 2 项' in page.locator('.prb-bulk').inner_text())
                page.locator('[data-prb-batch-status]').select_option('verifying')
                page.locator('dialog[open]').last.locator('input').fill('完成针对练习，等待隔时验证')
                accept(); page.get_by_text('已更新 2 个问题的状态', exact=True).wait_for()
                check('批量状态真正持久化', all(problems.get(vault, pid)['status'] == 'verifying' for pid in ids))
                page.locator('[data-prb="prev"]').click(); ready()
                pid = page.locator('[data-prb="open"]').first.get_attribute('data-id')
                page.locator('[data-prb="open"]').first.click(); page.locator('.prb-detail h1').wait_for()
                check('打开详情后保留列表', page.locator('.prb-list').is_visible() and page.locator('.prb-detail').is_visible())
                page.screenshot(path=str(out / 'detail-light-desktop.png'))
                page.locator('[data-prb-field="status"]').select_option('parked')
                check('切换状态立即提示未保存', '有未保存的修改' in page.locator('[data-prb-dirty]').inner_text())
                page.locator('[data-prb-field="reason"]').fill('先搁置，集中处理更常出现的问题')
                page.locator('[data-prb="edit"]').click()
                page.locator('[data-prb-field="title"]').fill('本轮未保存的修改')
                page.locator('[data-prb="back"]').last.click()
                page.get_by_role('button', name='继续编辑', exact=True).click()
                check('关闭详情保护未存草稿', page.locator('[data-prb-field="title"]').input_value() == '本轮未保存的修改')
                page.route('**/api/problems/write', lambda route: route.abort(), times=1)
                page.locator('[data-prb="save"]').click(); page.locator('.prb-message.is-error').wait_for()
                check('保存失败保留输入', page.locator('[data-prb-field="title"]').input_value() == '本轮未保存的修改')
                page.locator('[data-prb="save"]').click(); page.locator('.prb-detail h1').wait_for()
                check('重试保存读回修改', problems.get(vault, pid)['title'] == '本轮未保存的修改')
                page.locator('[data-prb="trash"][data-id]').click(); page.get_by_role('button', name='取消', exact=True).click()
                check('取消删除保留问题', not problems.get(vault, pid).get('deleted_at'))
                page.locator('[data-prb="trash"][data-id]').click(); accept()
                page.get_by_text('已将 1 个问题移入回收站', exact=True).wait_for()
                check('单个删除进入回收站', problems.search(vault)['total'] == 136 and bool(problems.get(vault, pid)['deleted_at']))
                filtered('trash')
                page.locator('[data-prb="open"]').first.click(); page.locator('.prb-trash-note').wait_for()
                check('回收站详情只提供恢复', page.locator('[data-prb="save"]').count() == 0 and page.locator('[data-prb="restore"]').is_visible())
                page.screenshot(path=str(out / 'trash-light-desktop.png'))
                page.locator('[data-prb="restore"]').click(); page.get_by_text('已恢复 1 个问题', exact=True).wait_for()
                check('恢复后原问题重新可见', problems.search(vault)['total'] == 137 and problems.search(vault, deleted='only')['total'] == 0)
                filtered('')
                page.locator('[data-prb-check-all]').check()
                check('全选只包含当前页', '已选 25 项' in page.locator('.prb-bulk').inner_text())
                page.locator('[data-prb="trash"]').click(); accept()
                page.get_by_text('已将 25 个问题移入回收站', exact=True).wait_for()
                check('批量删除真正持久化', problems.search(vault)['total'] == 112 and problems.search(vault, deleted='only')['total'] == 25)
                filtered('trash'); page.locator('[data-prb-check-all]').check(); page.locator('[data-prb="restore"]').click()
                page.get_by_text('已恢复 25 个问题', exact=True).wait_for()
                check('批量恢复真正持久化', problems.search(vault)['total'] == 137)
                filtered('')
                # 竞争修改必须提示冲突，整批保持原状。
                selected = page.locator('[data-prb-check]').first.get_attribute('data-prb-check')
                page.locator('[data-prb-check]').first.check()
                p = problems.get(vault, selected)
                problems.execute(vault, 'update_problem', {'id': selected, 'expected_revision': p['revision'], 'title': p['title'] + ' 外部更新', 'request_id': str(uuid.uuid4())})
                page.locator('[data-prb="trash"]').click(); accept(); page.locator('.prb-message.is-error').wait_for()
                check('并发冲突不误删且保留选择', not problems.get(vault, selected).get('deleted_at') and page.locator('.prb-bulk').is_visible())
                page.locator('[data-prb="clearSelected"]').click(); page.locator('[data-prb="refresh"]').click(); ready()
                for theme in ('light', 'dark'):
                    page.evaluate("t=>{document.documentElement.dataset.theme=t;localStorage.setItem('omrs-theme',t)}", theme)
                    for width in (320, 390, 760, 1024, 1440):
                        page.set_viewport_size({'width': width, 'height': 960 if width > 760 else 844})
                        page.evaluate('document.fonts.ready')
                        audit = page.evaluate(visual.AUDIT_JS)
                        check(f'{theme}/{width}列表布局', not audit['page_overflow_x'] and audit['small_targets'] == 0, audit)
                        if width in (390, 1440): page.screenshot(path=str(out / f'list-{theme}-{width}.png'))
                        page.locator('[data-prb="open"]').first.click(); page.locator('.prb-detail h1').wait_for()
                        audit = page.evaluate(visual.AUDIT_JS)
                        check(f'{theme}/{width}详情布局', not audit['page_overflow_x'] and audit['small_targets'] == 0, audit)
                        if width in (390, 1440): page.screenshot(path=str(out / f'detail-{theme}-{width}.png'))
                        page.locator('[data-prb="back"]:visible').first.click(); ready()
                page.locator('[data-prb="new"]').first.click()
                page.locator('[data-prb-field="title"]').fill('回执已保存但详情刷新失败')
                page.route('**/api/problem?*', lambda route: route.abort(), times=1)
                page.locator('[data-prb="save"]').click()
                page.locator('.prb-message').filter(has_text='问题已保存，详情刷新失败，可重新打开查看。').wait_for()
                check('保存后的刷新失败保留正式身份', problems.search(vault, query='回执已保存')['total'] == 1 and page.locator('[data-prb-field="title"]').count() == 0)
                page.locator('[data-prb="save"]').click(); page.get_by_text('问题已保存', exact=True).wait_for()
                check('刷新失败后重试不重复新建', problems.search(vault, query='回执已保存')['total'] == 1)
                check('问题操作不改变学习状态', mastery_rows(vault) == baseline)
                check('无浏览器脚本错误', not errors, errors)
                context.close()
                if not __import__('os').environ.get('OMRS_TEST_CDP_URL'): browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
            (out / 'report.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
