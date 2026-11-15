"""提醒库真实闭环：只替换模型网络，业务HTTP、下载、历史快照与浏览器均实跑。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from omrs.common import save_config
from omrs.creation import create_question
from omrs.data_repository import resolve_question
from tests.browser_runtime import launch_chromium, open_app
from tests.test_schedule_banner import SVG
from tests.visual.run import free_port

AI_SVG = SVG.replace('作答流程', '先读题').replace('读题 → 独立作答 → 核对 → 记录错因', '先读题 → 写思路 → 再计算')


class ModelBoundary(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(payload)
        data = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': AI_SVG},
                                       'finish_reason': 'stop'}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    shots = Path(os.environ.get('OMRS_REMINDER_SHOTS', tempfile.mkdtemp(prefix='omrs-reminder-shots-')))
    shots.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(label, value):
        assert value, label
        checks.append(label)
        print('通过：' + label, flush=True)

    model = ThreadingHTTPServer(('127.0.0.1', 0), ModelBoundary)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='omrs-reminder-e2e-') as temp:
        vault = Path(temp) / 'vault'
        questions = []
        for n, cause in enumerate(('', '计算时漏看区间端点')):
            q = create_question(str(vault), '数学', '合成提醒', 5,
                                question_text=f'已知 x={n + 1}，求 x+1。', answer_text=str(n+2), cause=cause)
            questions.append(resolve_question(str(vault), q['uid']))
        save_config(str(vault), {'agent_enabled': True, 'agent_compat': 'custom', 'agent_model': 'synthetic',
                                'agent_base_url': f'http://127.0.0.1:{model.server_port}/v1', 'agent_api_key': 'synthetic'})
        env = dict(os.environ)
        for key in ('OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL', 'OMRS_AGENT_FAUX_SCRIPT'):
            env.pop(key, None)
        port = free_port()
        base = f'http://127.0.0.1:{port}'
        log = (shots / 'server.log').open('w')
        proc = subprocess.Popen([sys.executable, str(ROOT/'omrs_engine.py'), '--vault', str(vault), 'serve', '-p', str(port)],
                                cwd=ROOT, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    urllib.request.urlopen(base+'/api/auth/session', timeout=1).close()
                    break
                except OSError:
                    time.sleep(.1)
            with sync_playwright() as runtime:
                browser = launch_chromium(runtime)
                ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' and msg.text.startswith(('[bus]', '[shell]')) else None)

                def api(path, data=None):
                    response = ctx.request.post(base+path, data=data) if data is not None else ctx.request.get(base+path)
                    assert response.ok, response.text()
                    return response.json()

                def catalog():
                    return api('/api/schedule-reminders')

                def cancel(panel):
                    panel.locator('[data-dialog-cancel]').first.click()
                    panel.wait_for(state='detached')

                open_app(page, base, 'settings?section=appearance')
                page.click('[data-banner-manage]')
                page.locator('#sch-reminders').wait_for()
                check('设置入口直达提醒素材，无路由事件丢失', page.locator('#sch-tab-reminders').get_attribute('aria-selected') == 'true')
                page.click('[data-action="schedule.rcreate"][data-arg="import"]')
                create = page.locator('#schedule-reminder-create')
                create.locator('#reminderName').fill('导入流程')
                create.locator('#reminderSvg').fill(SVG.replace('<text ', '<text onclick="bad()" '))
                create.locator('[data-reminder-preview]').click()
                create.locator('[role="alert"]').wait_for()
                check('不安全SVG被拒绝，名称与源码保留', create.locator('#reminderName').input_value() == '导入流程'
                      and 'onclick' in create.locator('#reminderSvg').input_value() and create.locator('[data-dialog-ok]').is_disabled())
                create.locator('#reminderFile').set_input_files({'name': '流程.svg', 'mimeType': 'image/svg+xml', 'buffer': SVG.encode()})
                page.wait_for_function('document.querySelector("#reminderSvg").value.includes("记录错因")')
                create.locator('[data-reminder-preview]').click()
                create.locator('.rem-image').wait_for()
                create.locator('#reminderDefault').check()
                create.locator('[data-dialog-ok]').click()
                create.wait_for(state='detached')
                page.locator('.rem-card').wait_for()
                original = catalog()['items'][0]
                check('SVG文件校验预览后保存，并设为新计划默认', catalog()['default']['enabled']
                      and catalog()['default']['reminder_id'] == original['id'])
                session = api('/api/confirm-schedule', {'persist': True, 'selected': [
                    {'question_id': q['question_id'], 'source': 'due'} for q in questions]})['session_id']
                page.click('[data-action="schedule.rcreate"][data-arg="ai"]')
                create.locator('#reminderName').fill('AI步骤')
                create.locator('#reminderPrompt').fill('提醒我先读题，再写思路，最后计算。')
                create.locator('[data-reminder-preview]').click()
                create.locator('.rem-image').wait_for()
                check('AI真实客户端请求模型边界，生成仅为预览', len(ModelBoundary.calls) == 1
                      and not ModelBoundary.calls[0]['stream'] and len(catalog()['items']) == 1)
                create.locator('[data-dialog-ok]').click()
                create.wait_for(state='detached')
                page.wait_for_function('document.querySelectorAll(".rem-card").length === 2')
                ai = next(x for x in catalog()['items'] if x['id'] != original['id'])
                check('AI素材保存不会自动替换默认', catalog()['default']['reminder_id'] == original['id'])
                page.click(f'[data-action="schedule.rset"][data-arg="{ai["id"]}"]')
                page.wait_for_function('id => document.querySelector(`[data-key="${id}"] .ui-badge`)', arg=ai['id'])
                page.click(f'[data-action="schedule.rdelete"][data-arg="{ai["id"]}"]')
                page.locator('.ui-dialog [data-dialog-ok]').click()
                page.wait_for_function('document.querySelectorAll(".rem-card").length === 1')
                check('删除默认素材清空新计划默认，旧计划仍保留快照', not catalog()['default']['enabled']
                      and api('/api/schedule-reminders?session_id='+session)['plan_snapshot']['src'] == original['src'])

                page.click('#sch-tab-plans')
                page.click('[data-action="schedule.refresh"]')
                page.click(f'.schd-plan[data-arg="{session}"]')
                page.locator('[data-action="schedule.export"]').wait_for()
                check('计划详情只有一个导出入口', page.locator('[data-action="schedule.export"]').count() == 1)
                page.click('[data-action="schedule.export"]')
                export = page.locator('#schedule-export-dialog')
                check('默认不标缺错因，并显示计划原提醒', not export.locator('#markMissingCause').is_checked()
                      and export.locator('.exd-banner .rem-image').get_attribute('src') == original['src'])
                before = catalog()
                export.locator('[data-export-banner-pick]').click()
                picker = page.locator('#schedule-reminder-picker')
                picker.locator('[data-reminder-id="off"]').click()
                cancel(picker)
                check('取消画廊选择保留面板状态，服务端无写入', catalog() == before
                      and export.locator('.exd-banner .rem-image').get_attribute('src') == original['src'])
                export.locator('#markMissingCause').check()
                with page.expect_download() as downloading:
                    export.locator('[data-dialog-ok]').click()
                a4 = shots/'marked-a4.html'
                downloading.value.save_as(str(a4))
                export.wait_for(state='detached')
                printed = ctx.new_page()
                printed.goto(a4.as_uri())
                printed.wait_for_function('window.__OMRS_RESULT && !document.getElementById("btnPrint").disabled')
                check('A4只标没有有效错因的题目，原提醒实际渲染', printed.locator('#stage .missing-cause').count() == 1
                      and printed.evaluate('OMRS_DATA.questions.map(q => q.missing_cause)') == [True, False]
                      and printed.evaluate('OMRS_DATA.meta.schedule_banner.src') == original['src'])
                check('错因正文留在反馈区', all('错因' not in q['notes'] for q in printed.evaluate('OMRS_DATA.questions')))
                (shots/'marked-a4.pdf').write_bytes(printed.pdf(prefer_css_page_size=True))
                printed.locator('.page').first.screenshot(path=str(shots/'marked-a4.png'))
                printed.close()

                # 画廊选用另一张后，在另一个客户端删除，导出须报错且保留用户选项。
                made = api('/api/schedule-reminders/create', {'name': '临时选用', 'svg': AI_SVG, 'request_id': 'delete-selection'})['item']
                page.click('[data-action="schedule.export"]')
                check('成功导出后记住缺错因开关', export.locator('#markMissingCause').is_checked())
                export.locator('[data-export-banner-pick]').click()
                picker.locator(f'[data-reminder-id="{made["id"]}"]').click()
                picker.locator('[data-dialog-ok]').click()
                picker.wait_for(state='detached')
                check('画廊选择回填真实预览', export.locator('.exd-banner .rem-image').get_attribute('src') == made['src'])
                export.locator('[name="variant"][value="screen"] + span').click()
                with page.expect_download() as downloading:
                    export.locator('[data-dialog-ok]').click()
                chosen = shots/'chosen-screen.html'
                downloading.value.save_as(str(chosen))
                export.wait_for(state='detached')
                downloaded = ctx.new_page()
                downloaded.goto(chosen.as_uri())
                check('画廊素材实际进入屏幕版文件', downloaded.evaluate('OMRS_DATA.meta.schedule_banner.src') == made['src'])
                downloaded.close()
                page.click('[data-action="schedule.export"]')
                check('重新打开只记参数，本次提醒重新沿用计划', export.locator('.exd-banner .rem-image').get_attribute('src') == original['src'])
                export.locator('[data-export-banner-pick]').click()
                picker.locator(f'[data-reminder-id="{made["id"]}"]').click()
                picker.locator('[data-dialog-ok]').click()
                picker.wait_for(state='detached')
                api('/api/schedule-reminders/delete', {'id': made['id'], 'expected_revision': made['revision']})
                export.locator('[data-dialog-ok]').click()
                export.locator('[role="alert"]').wait_for()
                check('选中素材被删除后导出明确失败并保留设置', '删除' in export.locator('[role="alert"]').inner_text()
                      and export.locator('#markMissingCause').is_checked())
                export.locator('[data-export-banner-off]').click()
                export.locator('[name="variant"][value="screen"] + span').click()
                with page.expect_download() as downloading:
                    export.locator('[data-dialog-ok]').click()
                screen = shots/'marked-screen.html'
                downloading.value.save_as(str(screen))
                export.wait_for(state='detached')
                downloaded = ctx.new_page()
                downloaded.goto(screen.as_uri())
                check('屏幕版同样标记缺错因，本次关闭提醒', downloaded.locator('.missing-cause').count() == 1
                      and downloaded.evaluate('OMRS_DATA.meta.schedule_banner') is None)
                downloaded.close()

                page.click('#sch-tab-reminders')
                for width in (320, 390, 1440):
                    page.set_viewport_size({'width': width, 'height': 844 if width < 760 else 1000})
                    for theme in ('light', 'dark'):
                        page.evaluate('t => document.documentElement.dataset.theme = t', theme)
                        page.locator('.rem-card').wait_for()
                        page.screenshot(path=str(shots/f'library-{width}-{theme}.png'), full_page=True)
                        check(f'{width}px {theme} 素材库无横向溢出', page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                        page.click('[data-action="schedule.rcreate"][data-arg="ai"]')
                        check(f'{width}px {theme} 新增面板无溢出和重复ID', create.evaluate('''e => {
                            const p=e.querySelector('.ui-dialog__panel'), ids=[...document.querySelectorAll('[id]')].map(x=>x.id);
                            return p.scrollWidth<=p.clientWidth+1 && new Set(ids).size===ids.length;
                        }'''))
                        create.locator('.ui-dialog__panel').screenshot(path=str(shots/f'create-{width}-{theme}.png'))
                        cancel(create)
                check('页面脚本错误为零', not errors)
                ctx.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            log.close()
            model.shutdown()
    (shots/'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(f'{len(checks)} 项通过；证据：{shots}', flush=True)


if __name__ == '__main__':
    main()
