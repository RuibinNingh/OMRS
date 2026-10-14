"""真实 MCP → 草稿审核 → 题库 → 离线导出；全部使用合成正文与临时 Vault。"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).parent:
    sys.path.pop(0)  # 同目录 mcp.py 不能遮蔽官方 SDK。
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from playwright.sync_api import sync_playwright
from browser_runtime import launch_chromium, open_app
from test_mcp_protocol import MCPServerProcess, _session, _json_result
from omrs import content_history, drafts, exporting
from omrs.boards import create_board
from omrs.creation import create_question
from omrs.mcp.keys import create_key


def main():
    case = json.loads((ROOT / 'tests/fixtures/math_delimiters.json').read_text())[0]
    output = Path(tempfile.mkdtemp(prefix='omrs-math-e2e-'))
    server = MCPServerProcess()
    checks = []

    def check(label, valid):
        checks.append({'name': label, 'ok': bool(valid)})
        print(('PASS ' if valid else 'FAIL ') + label, flush=True)
        if not valid:
            raise AssertionError(label)

    try:
        legacy_uid = create_question(server.vault, '物理', '旧公式', 5,
                                     question_text=r'求 \(t\)。', answer_text=case['source'])['uid']
        legacy_row = content_history.projection_row(server.vault, uid=legacy_uid)
        original = content_history.read_question_file(server.vault, legacy_row)
        server.start()
        key = create_key(server.vault, scopes=['omrs:read', 'draft:create', 'draft:update'])

        async def prepare():
            async with _session(server.mcp_port, key['secret']) as session:
                args = {'subject': '物理', 'category': '公式兼容', 'request_id': 'e2e-math-create',
                        'blocks': [{'section': '题目', 'kind': 'text', 'text': r'求 \(t\)。'},
                                   {'section': '答案', 'kind': 'text', 'text': case['source']}]}
                result = _json_result(await session.call_tool('create_draft', args))
                draft = drafts.get_draft(server.vault, result['draft_id'])
                check('MCP 写入题目和完整答案时转换美元符号', draft['blocks'][0]['text'] == '求 $t$。'
                      and draft['blocks'][1]['text'] == case['expected'])
                retry = _json_result(await session.call_tool('create_draft', args))
                check('MCP 原请求重试复用同一草稿', retry['draft_id'] == draft['id'] and retry['reused'])
                update = _json_result(await session.call_tool('update_draft', {
                    'draft_id': draft['id'], 'expected_revision': draft['revision'], 'request_id': 'e2e-math-update',
                    'block_patches': [{'block_id': draft['blocks'][0]['id'], 'text': r'求 \(h\)。'}]}))
                check('MCP 草稿修订转换美元符号', update['wrote']
                      and drafts.get_draft(server.vault, draft['id'])['blocks'][0]['text'] == '求 $h$。')
                return draft['id']

        draft_id = asyncio.run(prepare())
        base = f'http://127.0.0.1:{server.web_port}'
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            open_app(page, base, 'ai-review?draft=' + draft_id)
            page.wait_for_selector('.drf-detail [data-action="ai-review.draftCommit"]')
            answer = page.locator('.drf-block[aria-label^="答案"] .drf-md')
            check('审核预览呈现全部 16 个公式和 7 个行间公式', answer.locator('.katex').count() == 16
                  and answer.locator('.katex-display').count() == 7 and '故选 AD。' in answer.inner_text())
            for theme in ('light', 'dark'):
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
                    page.evaluate('theme => document.documentElement.dataset.theme = theme', theme)
                    page.evaluate('document.fonts.ready')
                    check(f'审核 {theme} {width}px 无页面横向溢出',
                          page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                    page.screenshot(path=str(output / f'review-{theme}-{width}.png'), full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 900})
            page.locator('[data-action="ai-review.draftCommit"]').click()
            for _ in range(100):
                committed = drafts.get_draft(server.vault, draft_id)
                if committed['status'] == 'done':
                    break
                time.sleep(.1)
            check('网页批准后正式 Markdown 保存美元公式', committed['status'] == 'done'
                  and case['expected'] in content_history.read_question_file(server.vault,
                      content_history.projection_row(server.vault, uid=committed['uid'])))
            for name, uid in (('新题', committed['uid']), ('旧题', legacy_uid)):
                open_app(page, base, 'questions')
                page.locator(f'tr[data-q-row="{uid}"] td').nth(1).click()
                page.wait_for_selector('#modal .qv-a .katex')
                answer = page.locator('#modal .qv-a')
                check(name + '题库详情显示完整公式', answer.locator('.katex').count() == 16
                      and answer.locator('.katex-display').count() == 7 and '故选 AD。' in answer.inner_text())
                page.keyboard.press('Escape')
            check('旧题预览保持原 Markdown 文件', content_history.read_question_file(server.vault, legacy_row) == original)

            board = create_board(server.vault, '公式导出验收', [legacy_uid])
            board_data = exporting.build_board_export_data(server.vault, board['id'], include_answers=True)
            check('展示板导出数据包含完整美元公式', '$$' in json.dumps(board_data, ensure_ascii=False)
                  and r'\[' not in json.dumps(board_data, ensure_ascii=False))
            exports = [(variant, exporting.export_schedule_html(server.vault, uids=[legacy_uid],
                        include_answers=True, variant=variant)[0]) for variant in ('a4', 'screen')]
            exports.append(('board', exporting.export_board_html(server.vault, board['id'], include_answers=True)))
            for variant, payload in exports:
                path = output / (variant + '.html')
                path.write_bytes(payload)
                page.goto(path.as_uri(), wait_until='networkidle')
                if variant == 'a4':
                    page.wait_for_function('window.__OMRS_RESULT', timeout=30000)
                    check(variant + ' 离线排版无错误', not page.evaluate('window.__OMRS_RESULT.errors.length'))
                elif variant == 'board':
                    page.wait_for_function('document.documentElement.dataset.omrsLayoutReady === "1"', timeout=30000)
                    check(variant + ' 离线排版可打印', page.locator('#btnPrint').is_enabled())
                else:
                    page.locator('.reveal').click()
                check(variant + ' 离线导出呈现所有公式', page.locator('.katex').count() >= 17
                      and page.locator('.katex-display').count() >= 7)
                page.screenshot(path=str(output / (variant + '.png')), full_page=True)
            check('浏览器页面无脚本错误', not errors)
            context.close()
            browser.close()
    finally:
        server.stop()
        (output / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
        print('产物：' + str(output), flush=True)
    print(f'公式 MCP / 浏览器验收：{len(checks)}/{len(checks)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
