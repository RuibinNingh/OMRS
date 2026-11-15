"""官方MCP创建SVG新题，经真实浏览器暂存、刷新、入库和向量导出。"""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from e2e_navigation import select_review_item
from omrs import drafts, exporting
from omrs.draft_svg import bytes_of
from tests.test_mcp_protocol import MCPServerProcess, _session, _json_result, _png
from tests.test_question_svg import diagram


async def create(server):
    async with _session(server.mcp_port, server.keys['all']['secret']) as client:
        file = {'download_url': 'https://files.example.org/figure.svg', 'file_id': 'browser-svg',
                'file_name': 'figure.svg', 'mime_type': 'image/svg+xml',
                'data_base64': base64.b64encode(diagram('文件原件') + b'\n').decode()}
        original = {'download_url': 'https://files.example.org/source.png', 'file_id': 'browser-source',
                    'data_base64': base64.b64encode(_png(560, 330)).decode()}
        out = []
        for request, images in (('svg-only', [file]), ('svg-mixed', [file, original])):
            blocks = [{'section': '题目', 'kind': 'text', 'text': '阅读受力示意图，求合力。'},
                      {'section': '题目', 'kind': 'image', 'image': 0, 'note': '文件配图说明'},
                      {'section': '题目', 'kind': 'text', 'text': '保留这段图后条件。'},
                      {'section': '答案', 'kind': 'svg', 'svg': diagram('源码答案图').decode()}]
            if len(images) > 1:
                blocks.insert(0, {'section': '题目', 'kind': 'image', 'image': 1, 'note': '完整来源截图'})
            result = await client.call_tool('create_draft', {'subject': '物理', 'category': '浏览器SVG',
                'request_id': request, 'images': images, 'blocks': blocks})
            assert not result.isError, str(result)
            out.append(_json_result(result))
        return out


def main():
    from playwright.sync_api import sync_playwright
    shots = Path(os.environ.get('OMRS_DRAFT_SVG_SHOTS') or tempfile.mkdtemp(prefix='omrs-draft-svg-browser-'))
    shots.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    def check(label, passed):
        checks.append({'label': label, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + label, flush=True)
        if not passed:
            raise AssertionError(label)
    server = MCPServerProcess()
    try:
        server.start()
        only, mixed = asyncio.run(create(server))
        base = f'http://127.0.0.1:{server.web_port}'
        def read(draft_id):
            with urllib.request.urlopen(base + '/api/drafts/item?id=' + draft_id, timeout=10) as response:
                return json.load(response)['draft']
        def open_draft(page, item):
            open_app(page, base, 'ai-review?type=draft&operation=' + item['draft_id'])
            select_review_item(page, item['draft_id'])
            page.wait_for_function('id => document.querySelector(".drf-id")?.textContent.includes(id)', arg=item['draft_id'])
            page.wait_for_function('''() => [...document.querySelectorAll('.drf-review-content img[src^="data:image/svg+xml"]')]
                .filter(img => img.complete && img.naturalWidth > 0).length === 2''')
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            for theme in ('light', 'dark'):
                for width in (390, 1440):
                    context = browser.new_context(viewport={'width': width, 'height': 1000})
                    context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    for label, item in (('only', only), ('mixed', mixed)):
                        open_draft(page, item)
                        check(f'{theme}/{width}/{label}显示两张SVG及检查提示', page.get_by_text('SVG配图 ·', exact=False).count() == 2)
                        check(f'{theme}/{width}/{label}无横向溢出', page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                        page.screenshot(path=str(shots/f'{theme}-{width}-{label}.png'), full_page=True)
                    context.close()
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            open_draft(page, only)
            check('只有SVG时没有来源裁框画布', page.locator('.drf-entry-source').count() == 0)
            draft = read(only['draft_id'])
            key = draft['blocks'][1]['id']
            row = page.locator(f'.drf-block[data-key="{key}"]')
            row.locator('[data-action="ai-review.draftEditBlock"]').click()
            row.locator('[data-input="ai-review.draftBlockNote"]').fill('人工核对图意与标注')
            check('SVG只编辑说明，不显示裁图和源码编辑器', row.locator('[data-action="ai-review.draftEditImage"],textarea').count() == 0)
            with page.expect_response(lambda r: r.url.endswith('/api/drafts/update') and r.request.method == 'POST') as saved:
                page.locator('[data-action="ai-review.draftSave"]').click()
            check('真实HTTP暂存成功', saved.value.json()['status'] == 'ok')
            page.reload(wait_until='networkidle')
            page.wait_for_function("() => document.querySelector('.drf-review-content')?.textContent.includes('人工核对图意与标注')")
            fresh = read(only['draft_id'])
            check('刷新保留SVG原始字节、说明与顺序', bytes_of(fresh['blocks'][1]) == diagram('文件原件') + b'\n'
                  and [b['kind'] for b in fresh['blocks']] == ['text', 'svg', 'text', 'svg'])
            row = page.locator(f'.drf-block[data-key="{key}"]')
            row.locator('[data-action="ai-review.draftBlockMenu"]').click()
            page.get_by_role('menuitem', name='移到答案', exact=True).click()
            with page.expect_response(lambda r: r.url.endswith('/api/drafts/update') and r.request.method == 'POST'):
                page.locator('[data-action="ai-review.draftSave"]').click()
            fresh = read(only['draft_id'])
            check('跨节移动保留稳定编号和源码', fresh['blocks'][-1]['id'] == key and fresh['blocks'][-1]['section'] == '答案'
                  and bytes_of(fresh['blocks'][-1]) == diagram('文件原件') + b'\n')
            with page.expect_response(lambda r: r.url.endswith('/api/drafts/commit') and r.request.method == 'POST') as committed:
                page.locator('[data-action="ai-review.draftCommit"]').click()
            result = committed.value.json()
            check('真实浏览器审核入库成功', result['status'] == 'ok')
            uid = result['result']['uid']
            check('入库保存两张向量原件且可重复查询', read(only['draft_id'])['status'] == 'done'
                  and len(list((Path(server.vault)/'错题'/'附件').glob('*.svg'))) == 2)
            open_draft(page, mixed)
            with page.expect_response(lambda r: r.url.endswith('/api/drafts/commit') and r.request.method == 'POST') as committed:
                page.locator('[data-action="ai-review.draftCommit"]').click()
            check('来源位图与SVG混排可一起入库', committed.value.json()['status'] == 'ok')
            raw, _ = exporting.export_schedule_html(server.vault, [uid], include_answers=True, variant='a4')
            output = shots/'a4.html'
            output.write_bytes(raw)
            page.goto(output.as_uri())
            page.wait_for_function("document.querySelector('#btnPrint') && !document.querySelector('#btnPrint').disabled")
            check('双栏向量导出可以打印且没有丢图', not page.locator('#btnPrint').is_disabled() and page.locator('.slice').count() == 2
                  and b'image/svg+xml' in raw)
            pdf = page.pdf(path=str(shots/'a4.pdf'), prefer_css_page_size=True)
            check('实际生成双栏PDF', pdf.startswith(b'%PDF'))
            check('全部页面没有未捕获脚本错误', not errors)
            context.close()
            browser.close()
    finally:
        server.stop()
        (shots/'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
    print(f'{len(checks)}项通过；证据：{shots}', flush=True)


if __name__ == '__main__':
    main()
