"""审核中心：真实隔离服务、双标签修订冲突、批准写题、迁入草稿及主题宽度审计。"""
import hashlib
import datetime
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from omrs import ai_review, creation, drafts
from omrs.mcp.keys import create_key
from omrs.mcp.question_write import propose

spec = importlib.util.spec_from_file_location('review_support', ROOT / 'tests/e2e/drafts.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
SHOTS = Path('/tmp/omrs-ai-review-shots')


def seed(vault):
    question = creation.create_question(vault, '数学', '审核验收', 5,
                                       question_text='已知 $f(x)=x^2$，求 $f(2)$。', answer_text='答案是 4。')
    path = Path(vault, question['file_path'])
    if not path.exists():
        path = Path(vault, '错题', question['file_path'])
    original = path.read_text()
    key = create_key(vault, '审核浏览器测试', ['omrs:read', 'question:propose'])
    first = propose(vault, key['key_id'], 'browser-first', question['uid'], question['question_id'],
                    hashlib.sha256(original.encode()).hexdigest(), {'question_text': 'AI 建议：求 $f(3)$。', 'note': 'AI 备注', 'difficulty': 6}, reason='浏览器审核测试')
    second = propose(vault, key['key_id'], 'browser-second', question['uid'], question['question_id'],
                     hashlib.sha256(original.encode()).hexdigest(), {'note': '另一项待审备注'}, reason='浏览器拒绝测试')
    draft = drafts.create_draft(vault, {'subject': '数学', 'category': '中心草稿',
        'blocks': [{'section': '题目', 'kind': 'text', 'text': '迁入审核中心的草稿 $1+1$。'}]},
        {'conversation_id': 'browser-review', 'run_id': 'browser-run', 'tool_call_id': 'draft'})
    for number in range(34):
        row = ai_review.create(vault, 'agent', 'create_practice_card', f'browser-auto-{number}', {},
                               actor={'run_id': f'history-{number}'})
        ai_review.set_state(vault, row['operation_id'], 'applied', result={'practice_card_id': f'test-{number}'})
    return first, second, draft, path, original


def run_scoped_queue(ctx, base, vault, original_draft, check):
    body = {'subject': '数学', 'category': '筛选连续审核', 'difficulty': 5,
            'blocks': [{'section': '题目', 'kind': 'text', 'text': '来源与时间范围测试。'}]}
    key = create_key(vault, '筛选范围测试', ['omrs:read', 'draft:create'])
    def create(name, source='agent'):
        origin = {'conversation_id': 'scoped-browser', 'run_id': 'scoped-run', 'tool_call_id': name, 'source_channel': source}
        if source == 'mcp':
            origin.update(source_key_id=key['key_id'], source_request_id=name, content_hash='a' * 64)
        return drafts.create_draft(vault, body, origin)
    first, other_source, second, old, represented = create('first'), create('outside', 'mcp'), create('second'), create('old'), create('represented')
    now = datetime.datetime.now(datetime.timezone.utc)
    db = drafts.connect(vault)
    try:
        for row, age in ((first, 60), (other_source, 120), (second, 180), (old, 864000), (represented, 30), (original_draft, 864000)):
            db.execute('UPDATE drafts SET created_at=? WHERE id=?', ((now - datetime.timedelta(seconds=age)).isoformat(), row['id']))
        db.commit()
    finally:
        db.close()
    operation = ai_review.create(vault, 'agent', 'commit_draft', 'scoped-commit', {'draft_id': represented['id']},
                                actor={'run_id': 'scoped-run'}, pending=True)
    page = ctx.new_page(); errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    open_app(page, base, 'ai-review?type=draft')
    page.locator('[data-change="ai-review.source"]').select_option('agent')
    page.locator('[data-change="ai-review.range"]').select_option('7')
    check('混合来源与时间筛选只显示两份原生草稿和入库提案', support.wait(page, "() => document.querySelectorAll('.arv-row').length === 3")
          and set(page.locator('.arv-row').evaluate_all('els => els.map(el => el.dataset.arg)')) == {first['id'], second['id'], operation['operation_id']})
    page.locator(f'.arv-row[data-arg="{first["id"]}"]').click()
    page.locator('[data-action="ai-review.draftCommit"]').click()
    check('连续入库只推进当前来源和时间范围内的下一份', support.wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{second['id']}')")
          and support.api(base, '/api/drafts/item?id=' + first['id'])['draft']['status'] == 'done')
    page.locator('[data-action="ai-review.draftEditFields"]').click()
    note = page.locator('[data-input="ai-review.draftField"][data-arg="note"]')
    note.fill('显式刷新也必须保留本地草稿。')
    page.locator('[data-action="ai-review.refresh"]').click(); page.wait_for_timeout(300)
    check('草稿显式刷新保留未保存字段和当前身份', note.input_value() == '显式刷新也必须保留本地草稿。'
          and second['id'] in page.locator('.drf-id').inner_text())
    page.locator('[data-action="ai-review.draftDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('筛选内最后草稿丢弃后不重开筛选外或已有入库提案的草稿', support.wait(page, "() => !document.querySelector('.drf-id')")
          and page.locator('[data-change="ai-review.source"]').input_value() == 'agent'
          and page.locator('[data-change="ai-review.range"]').input_value() == '7')
    check('筛选外来源、旧草稿及入库提案对应草稿仍未被处理', all(support.api(base, '/api/drafts/item?id=' + row['id'])['draft']['status'] == 'review'
                                                                  for row in (other_source, old, represented)))
    check('筛选连续审核没有页面脚本错误', not errors, errors)
    page.close()


def main():
    from playwright.sync_api import sync_playwright
    checks = []
    def check(label, passed, detail=''):
        checks.append((label, bool(passed)))
        print(('PASS ' if passed else 'FAIL ') + label + (': ' + str(detail) if detail else ''), flush=True)
        if not passed:
            raise AssertionError(label)
    with tempfile.TemporaryDirectory(prefix='omrs-review-e2e-') as vault:
        subprocess.run([sys.executable, str(ROOT / 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'],
                       check=True, stdout=subprocess.DEVNULL)
        first, second, draft, path, original = seed(vault)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ)
        for key in ('OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL'):
            env.pop(key, None)
        proc = subprocess.Popen([sys.executable, '-c', support.SERVER, vault, str(port)], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    support.api(base, '/api/ai-review/counts'); break
                except OSError:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
                page, other = ctx.new_page(), ctx.new_page()
                errors = []
                for tab in (page, other):
                    tab.on('pageerror', lambda error: errors.append(str(error)))
                    open_app(tab, base, 'ai-review?operation=' + first['id'])
                    tab.locator('.arv-operation').wait_for()
                check('独立中心紧邻助手且待审核包括两项提案和一份草稿',
                      page.locator('[data-tab="assistant"] + [data-tab="ai-review"]').count() == 1
                      and support.api(base, '/api/ai-review/counts')['counts']['pending'] == 3)
                check('未批准文件不变并显示题干前后对照与公式', path.read_text() == original
                      and page.locator('.arv-change').count() == 3 and page.locator('.arv-diff .katex').count() > 0)
                check('来源追溯显示已有MCP密钥编号和请求编号', page.get_by_text('MCP 密钥编号', exact=True).is_visible()
                      and page.get_by_text('browser-first', exact=True).is_visible())
                for tab in (page, other):
                    tab.locator('[data-action="ai-review.edit"]').click()
                check('人工修订只展示原提案允许字段', page.locator('[data-input="ai-review.editField"]').count() == 3)
                other.locator('[data-input="ai-review.editField"][data-arg="note"]').fill('另一窗口未保存内容')
                page.locator('[data-input="ai-review.editField"][data-arg="question_text"]').fill('人工修订：求 $f(4)$。')
                page.locator('[data-action="ai-review.save"]').click()
                check('修订递增版本但未写题库', support.wait(page, "() => document.querySelector('.arv-operation')?.textContent.includes('人工修订：求')")
                      and support.api(base, '/api/ai-review/detail?id=' + first['id'])['item']['revision'] == 2
                      and path.read_text() == original)
                other.wait_for_timeout(2800)
                check('后台刷新保留另一窗口未保存输入', other.locator('[data-input="ai-review.editField"][data-arg="note"]').input_value() == '另一窗口未保存内容')
                other.locator('[data-action="ai-review.save"]').click()
                check('旧版本保存失败保留本地编辑', support.wait(other, "() => document.querySelector('.arv-operation')?.textContent.includes('版本已变化')")
                      and other.locator('[data-input="ai-review.editField"][data-arg="note"]').input_value() == '另一窗口未保存内容')
                other.evaluate("id => { window.__omrs.router.go('ai-review?operation=' + id); }", second['id'])
                other.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
                check('同页换目标取消后保留原地址及编辑', first['id'] in other.url
                      and other.locator('[data-input="ai-review.editField"][data-arg="note"]').input_value() == '另一窗口未保存内容')
                page.locator('[data-action="ai-review.approve"]').click()
                check('批准执行用户修订且真实文件只出现最终内容', support.wait(page, "() => document.querySelector('.arv-operation')?.textContent.includes('当前状态：已执行')")
                      and '人工修订：求 $f(4)$。' in path.read_text() and 'AI 建议：求' not in path.read_text(), {'status': support.api(base, '/api/ai-review/detail?id=' + first['id'])['item']['status']})
                check('已执行操作不再有审批或修订按钮', page.locator('[data-action="ai-review.approve"], [data-action="ai-review.edit"]').count() == 0)
                check('决定追溯显示服务端记录的Web身份和IP', support.wait(page, "() => document.querySelector('.arv-facts')?.textContent.includes('Web · 本机访问')")
                      and page.get_by_text('127.0.0.1', exact=True).is_visible())
                page.evaluate("id => window.__omrs.router.go('ai-review?operation=' + id)", second['id'])
                page.locator('[data-action="ai-review.reject"]').wait_for()
                page.locator('[data-action="ai-review.reject"]').click()
                page.locator('dialog[open] [data-dialog-ok]').click()
                check('拒绝从待审移除并保持题目内容', support.wait(page, "() => document.querySelector('.arv-operation')?.textContent.includes('当前状态：已拒绝')")
                      and '另一项待审备注' not in path.read_text())
                page.locator('[data-action="ai-review.view"][data-arg="records"]').click()
                page.locator('[data-change="ai-review.type"]').select_option('')
                page.locator('[data-action="ai-review.more"]').click()
                check('分页与刷新保留已展开记录范围', support.wait(page, "() => document.querySelectorAll('.arv-row').length > 30"))
                loaded = page.locator('.arv-row').count()
                page.locator('[data-action="ai-review.refresh"]').click()
                page.wait_for_timeout(300)
                check('轮询刷新不丢已加载页', page.locator('.arv-row').count() == loaded)
                page.locator('[data-change="ai-review.source"]').select_option('agent')
                check('来源筛选只显示助手写操作', support.wait(page, "() => [...document.querySelectorAll('.arv-row')].every(el => el.textContent.includes('AI 助手'))"))
                page.evaluate("id => import('/assets/app/domain/drafts.js').then(module => module.openDraft(id))", draft['id'])
                page.locator('.drf-id').wait_for()
                check('草稿跨页入口进入中心并保留完整编辑器', '#/ai-review?draft=' in page.url
                      and page.locator('[data-action="ai-review.draftEditBlock"]').count() == 1)
                page.locator('[data-action="ai-review.draftEditFields"]').click()
                page.locator('[data-input="ai-review.draftField"][data-arg="note"]').fill('草稿本地修改')
                page.locator('[data-change="ai-review.source"]').select_option('mcp')
                page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
                check('中心筛选也保护草稿脏输入', page.locator('[data-input="ai-review.draftField"][data-arg="note"]').input_value() == '草稿本地修改')
                page.locator('[data-action="ai-review.draftSave"]').click()
                check('迁入后的草稿保存真实生效', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存')")
                      and support.api(base, '/api/drafts/item?id=' + draft['id'])['draft']['note'] == '草稿本地修改')
                page.goto(base + '/?unlocked=1#/history?operation=' + first['id'], wait_until='networkidle')
                check('旧网页确认链接兼容跳转中心', support.wait(page, "() => window.__omrs.router.current() === 'ai-review'") and first['id'] in page.url, {'url': page.url, 'errors': errors, 'current': page.evaluate('window.__omrs?.router.current()')})
                maintenance_page = ctx.new_page()
                open_app(maintenance_page, base, 'ai-review?type=category')
                maintenance_page.locator('.arv-queue .ui-empty').wait_for()
                maintenance_page.locator('[data-action="ai-review.draftQueueMenu"]').click()
                maintenance_page.get_by_role('menuitem', name='清理过期草稿').click()
                maintenance_page.locator('dialog[open] [data-dialog-ok]').click()
                check('空待审队列仍可执行草稿资源清理', support.wait(maintenance_page, "() => [...document.querySelectorAll('.ui-toast')].some(el => el.textContent.includes('已清理'))"))
                maintenance_page.close()
                SHOTS.mkdir(exist_ok=True)
                for theme in ('light', 'dark'):
                    for width in (320, 390, 1024, 1440):
                        audit_ctx = browser.new_context(viewport={'width': width, 'height': 844 if width < 760 else 900})
                        audit_ctx.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
                        audit = audit_ctx.new_page()
                        open_app(audit, base, 'ai-review?operation=' + first['id'])
                        audit.locator('.arv-operation').wait_for(); audit.evaluate('document.fonts.ready')
                        findings = audit.evaluate("""() => { const els = [...document.querySelectorAll('#panel-ai-review *')].filter(el => el.getClientRects().length);
                          return {overflow:document.documentElement.scrollWidth > innerWidth + 1,
                            tiny:els.filter(el => ['BUTTON','SELECT','INPUT'].includes(el.tagName) && el.getBoundingClientRect().height < 28).length,
                            inline:els.filter(el => el.getAttribute('style') && !el.closest('.katex')).length}; }""")
                        check(f'{theme}·{width} 中心无横向溢出且控件可点击', not findings['overflow'] and not findings['tiny'] and not findings['inline'], findings)
                        if width < 760:
                            check(f'{theme}·{width} 手机详情隐藏公共列表', audit.locator('.arv-detail').is_visible() and not audit.locator('.arv-queue').is_visible())
                            audit.locator('[data-action="ai-review.back"]').click()
                            check(f'{theme}·{width} 手机返回公共列表', audit.locator('.arv-queue').is_visible() and not audit.locator('.arv-detail').is_visible())
                            audit.locator('.arv-row').first.click()
                            selected = audit.locator('.arv-row[aria-current="true"]').get_attribute('data-arg')
                            audit.locator('[data-action="ai-review.back"]').click()
                            audit.locator(f'.arv-row[data-arg="{selected}"]').click()
                            check(f'{theme}·{width} 返回后可重开当前草稿详情', audit.locator('.arv-detail').is_visible() and not audit.locator('.arv-queue').is_visible())
                        audit.screenshot(path=str(SHOTS / f'{theme}-{width}.png'), full_page=True)
                        audit_ctx.close()
                run_scoped_queue(ctx, base, vault, draft, check)
                check('主路径没有浏览器脚本错误', not errors, errors)
                ctx.close(); browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    print(f'{sum(passed for _, passed in checks)} / {len(checks)}', flush=True)


if __name__ == '__main__':
    main()
