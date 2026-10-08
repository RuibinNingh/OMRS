"""对话内审批：真实回执、原位详情、草稿未保存保护和单份入库；只使用临时 Vault。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from fixtures.make_vault import free_port
from omrs.agent.tools.write import set_question_labels
from omrs.labels import list_label_defs
from omrs.common import save_config

spec = importlib.util.spec_from_file_location('assistant_support', ROOT / 'tests/e2e/assistant.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def main():
    from playwright.sync_api import sync_playwright
    checks = []
    def check(name, passed, detail=''):
        checks.append(name)
        print(('PASS ' if passed else 'FAIL ') + name + (': ' + str(detail) if detail else ''), flush=True)
        if not passed:
            raise AssertionError(name)
    vault, port = support.make_vault(), free_port()
    uids = ['三角函数1', '三角函数2', '三角函数3']
    set_question_labels({'vault': vault}, {'uids': uids, 'remove': [row['name'] for row in list_label_defs(vault)]})
    set_question_labels({'vault': vault}, {'uids': [uids[0]], 'add': ['考前必看']})
    save_config(vault, {'agent_enabled': True, 'draft_mode': 'silent', 'draft_crop_mode': 'manual'})
    faux = Path(vault) / 'review-faux.json'
    faux.write_text(json.dumps({'scenarios': [
        {'match': '聊天标记', 'rounds': [
            {'tool_calls': [{'name': 'set_question_labels', 'arguments': {'uids': uids, 'add': ['考前必看']}}]},
            {'text': '标记处理完成。'}]},
        {'match': '聊天草稿', 'rounds': [
            {'tool_calls': [{'name': 'create_draft', 'arguments': {'subject': '数学', 'category': '函数',
                'blocks': [{'section': '题目', 'kind': 'text', 'text': '求 $x^2$ 的最小值。'},
                           {'section': '答案', 'kind': 'text', 'text': '最小值为 0。'}]}}]},
            {'text': '草稿已创建。'}]},
    ]}, ensure_ascii=False))
    support.FAUX = str(faux)
    proc = support.start(vault, port)
    base = f'http://127.0.0.1:{port}'
    shots = Path(os.environ.get('OMRS_REVIEW_SHOTS', '/tmp/omrs-chat-review-shots'))
    shots.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            open_app(page, base, 'assistant')
            page.fill('#ast-input', '聊天标记'); page.click('[data-action="assistant.send"]')
            pending = page.locator('.ast-op.is-waiting')
            pending.locator('[data-action="assistant.approve"]').wait_for()
            check('确认前列出三道题和明确变更数量', '2 道将变更' in pending.inner_text() and pending.locator('.ast-op__row').count() == 3)
            page.fill('#ast-input', '这段输入保留，暂时不发送')
            pending.locator('[data-action="assistant.gate"]').click()
            drawer = page.locator('.ast-review-panel[open]')
            drawer.locator('.arv-operation').wait_for()
            check('完整预览原位打开且URL仍是聊天', '#/assistant' in page.url and drawer.locator('.arv-change').count() == 3)
            drawer.locator('[data-drawer-close]').click()
            drawer.wait_for(state='detached')
            check('关闭详情保留输入并把焦点还给入口', page.input_value('#ast-input') == '这段输入保留，暂时不发送'
                  and page.evaluate("document.activeElement.dataset.action") == 'assistant.gate')
            for width in (1440, 390):
                page.set_viewport_size({'width': width, 'height': 900 if width > 760 else 844})
                for theme in ('light', 'dark'):
                    page.evaluate('theme => document.documentElement.dataset.theme = theme', theme)
                    page.screenshot(path=str(shots / f'pending-{width}-{theme}.png'), animations='disabled')
                    check(f'{width}px/{theme}确认卡没有横向溢出', not page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            page.set_viewport_size({'width': 1440, 'height': 900})
            pending.locator('[data-action="assistant.approve"]').click()
            page.locator('.ast-op.is-done').wait_for()
            page.wait_for_function("() => !document.querySelector('.ast-turn.is-live')")
            card = page.locator('.ast-op').first
            check('确认后原位完成且回执解释修改与跳过', '#/assistant' in page.url and '已修改 2 道 · 1 道无需变更' in card.inner_text())
            check('成功卡片收起详情且不保留待确认状态', card.locator('.ast-op__preview').count() == 0 and '需确认' not in card.inner_text() and '你已允许' not in card.inner_text())
            card.locator('[data-action="assistant.toggleReview"]').click()
            card.locator('.ast-op__row').nth(2).wait_for()
            check('可直接展开真实逐题变更及无变更题目', card.locator('.ast-op__row').count() == 3 and '修改前' in card.inner_text())
            card.locator('[data-action="assistant.toggleReview"]').click()
            page.reload(wait_until='networkidle')
            page.locator('.ast-op.is-done').wait_for()
            check('刷新重放仍保持真实结果且不提供重复批准', '已修改 2 道 · 1 道无需变更' in page.locator('.ast-op').first.inner_text()
                  and page.locator('[data-action="assistant.approve"]').count() == 0)
            page.fill('#ast-input', '聊天草稿'); page.click('[data-action="assistant.send"]')
            page.locator('.ast-draft-card [data-action="assistant.openDraft"]').wait_for()
            page.wait_for_function("() => !document.querySelector('.ast-turn.is-live')")
            page.fill('#ast-input', '审核草稿时也保留聊天输入')
            page.locator('.ast-draft-card [data-action="assistant.openDraft"]').click()
            drawer = page.locator('.ast-review-panel[open]')
            drawer.locator('[data-action="ai-review.draftEditFields"]').click()
            note = drawer.locator('[data-input="ai-review.draftField"][data-arg="note"]')
            note.fill('对话内人工备注')
            drawer.locator('[data-drawer-close]').click()
            page.locator('.ui-dialog[open]').get_by_role('button', name='留在当前', exact=True).click()
            page.locator('.ui-dialog').wait_for(state='detached')
            check('关闭草稿时保护未保存输入，取消后原文仍在', note.input_value() == '对话内人工备注')
            for name, close in [('Esc', lambda: page.keyboard.press('Escape')),
                                ('遮罩', lambda: page.mouse.click(8, 400)),
                                ('离页', lambda: page.evaluate("location.hash = '#/settings'"))]:
                close()
                page.locator('.ui-dialog[open]').get_by_role('button', name='留在当前', exact=True).click()
                page.locator('.ui-dialog').wait_for(state='detached')
                check(f'{name}同样保护未保存草稿和聊天路由', note.input_value() == '对话内人工备注' and '#/assistant' in page.url)
            page.route('**/api/drafts/update', lambda route: route.abort())
            drawer.locator('[data-action="ai-review.draftSave"]').click()
            drawer.locator('.drf-message').filter(has_text='失败').wait_for()
            check('保存失败仍保留人工备注', note.input_value() == '对话内人工备注')
            page.unroute('**/api/drafts/update')
            drawer.locator('[data-action="ai-review.draftSave"]').click()
            drawer.locator('.drf-message').filter(has_text='已保存').wait_for()
            draft_id = drawer.locator('.drf-id').inner_text().split(' · ')[-1].strip()
            check('局部草稿动作写入真实存储', support.api(base, '/api/drafts/item?id=' + draft_id)['draft']['note'] == '对话内人工备注')
            for width in (320, 390, 1024, 1440):
                page.set_viewport_size({'width': width, 'height': 900})
                for theme in ('light', 'dark'):
                    page.evaluate('theme => document.documentElement.dataset.theme = theme', theme)
                    page.evaluate('() => Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => {})))')
                    page.screenshot(path=str(shots / f'draft-{width}-{theme}.png'), animations='disabled')
                    check(f'{width}px/{theme}草稿详情没有横向溢出', not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                          and drawer.evaluate('el => el.scrollWidth <= el.clientWidth'),
                          drawer.evaluate('el => ({scroll: el.scrollWidth, width: el.clientWidth, overflow: [...el.querySelectorAll("*")].filter(n => n.getBoundingClientRect().right > el.getBoundingClientRect().right + 1).map(n => n.className).slice(0, 12)})'))
            drawer.get_by_role('button', name='确认入库', exact=True).click()
            drawer.locator('.drf-success').wait_for()
            check('聊天抽屉只处理当前草稿，入库后保留当前回执', support.api(base, '/api/drafts/item?id=' + draft_id)['draft']['status'] == 'done'
                  and draft_id in drawer.locator('.drf-id').inner_text())
            drawer.locator('[data-drawer-close]').click(); drawer.wait_for(state='detached')
            check('完成草稿审核后保持聊天和输入', '#/assistant' in page.url and page.input_value('#ast-input') == '审核草稿时也保留聊天输入')
            check('所有新路径没有脚本错误', not errors, errors)
            browser.close()
    finally:
        proc.terminate(); proc.wait(timeout=5)
        proc._omrs_test_log.close()
        shutil.rmtree(vault)
    print(f'{len(checks)}/{len(checks)} 通过', flush=True)


if __name__ == '__main__':
    main()
