"""真实浏览器：同源设置/管理/密钥/长图历史及浅深色响应布局。"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from browser_runtime import launch_chromium,open_app
from test_boxdetect_panel import IntegrationTests
from services.boxdetect.tests.test_panel import image,model
from playwright.sync_api import sync_playwright


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    fixture=IntegrationTests();fixture.setUp()
    results=[];errors=[]
    def check(name,condition):
        results.append({'name':name,'ok':bool(condition)})
        if not condition:raise AssertionError(name)
    try:
        with sync_playwright() as pw:
            browser=launch_chromium(pw)
            context=browser.new_context(viewport={'width':1280,'height':900})
            try:
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                open_app(page,fixture.base,'settings?section=boxdetect')
                page.locator('#st-box-key-state').get_by_text('已保存 Key',exact=False).wait_for()
                page.locator('[data-action="settings.boxTest"]').click()
                page.get_by_text('已连接且 Key 有效，服务可接收框选。',exact=True).wait_for()
                check('设置连接来自真实服务且不回显Key',page.locator('#st-box-key').input_value()=='' and 'old' in page.locator('#st-box-model').inner_text())
                page.screenshot(path=str(out/'settings-desktop.png'),full_page=True)
                panel=context.new_page();panel.on('pageerror',lambda error:errors.append(str(error)))
                panel.on('response',lambda response:errors.append(f'HTTP {response.status}: {response.url.split("/boxdetect/")[-1]}') if response.status>=400 and not response.url.endswith('/api/admin/session') else None)
                panel.goto(fixture.base+'/boxdetect/',wait_until='networkidle')
                panel.locator('#password').fill((fixture.root/'state/admin-secret.txt').read_text().strip())
                panel.locator('#login-form button[type=submit]').click()
                panel.locator('.stats').wait_for()
                check('管理页与主站共用端口',panel.url==fixture.base+'/boxdetect/')
                panel.locator('[data-page="keys"]').first.click();panel.locator('[data-action="new-key"]').click()
                panel.locator('#key-name').fill('浏览器客户端 <b>安全文本</b>')
                panel.locator('#key-form button[type=submit]').click()
                panel.locator('#key-secret:not([hidden])').wait_for();key=panel.locator('#created-key').input_value()
                check('生成独立调用Key',key.startswith('box_'))
                panel.locator('[data-action="close-key"]').click()
                check('关闭窗口清空明文Key',panel.locator('#created-key').input_value()=='')
                panel.reload(wait_until='networkidle');panel.locator('.stats').wait_for()
                check('刷新保持独立管理会话',panel.locator('#logout').is_visible())
                panel.locator('[data-page="test"]').first.click()
                panel.locator('#test-file').set_input_files({'name':'long.png','mimeType':'image/png','buffer':image()})
                panel.locator('[data-action="detect"]').click();panel.get_by_text('本次已保存到请求历史，未加入训练集。',exact=True).wait_for()
                check('长图实际推理并叠加框',panel.locator('#result-preview svg rect').count()>0)
                panel.locator('[data-page="history"]').first.click();panel.get_by_role('button',name='查看详情').first.click()
                panel.locator('#history-overlay img').wait_for()
                check('历史保留原图和结果',panel.locator('#history-overlay svg rect').count()>0)
                panel.locator('[data-zoom="history-overlay"]').click();check('原图可放大',panel.locator('#history-overlay .preview-inner').evaluate("e=>e.classList.contains('zoom')"))
                panel.locator('[data-action="close-detail"]').click()
                panel.reload(wait_until='networkidle');panel.locator('.stats').wait_for();panel.locator('[data-page="history"]').first.click()
                panel.get_by_role('button',name='查看详情').first.wait_for()
                check('刷新后仍可回看历史',panel.get_by_role('button',name='查看详情').count()==1)
                model(fixture.root/'models/new','new',.2);fixture.box.config.models_dir=fixture.root/'models'
                panel.locator('[data-page="models"]').first.click();panel.locator('[data-model="new"]').wait_for()
                panel.once('dialog',lambda d:d.accept());panel.locator('[data-model="new"]').click();panel.get_by_text('在线模型已更新。',exact=True).wait_for()
                check('浏览器应用实际模型',fixture.box.runtime.metadata['name']=='new')
                panel.locator('[data-page="overview"]').first.click();panel.locator('[data-action="pause"]').wait_for();panel.locator('[data-action="pause"]').click();panel.get_by_role('button',name='恢复接单',exact=True).wait_for()
                check('暂停后管理页仍可访问',fixture.box.store.get('paused') is True)
                panel.locator('[data-action="pause"]').click();panel.get_by_role('button',name='暂停接单',exact=True).wait_for()
                for theme in ('light','dark'):
                    panel.emulate_media(color_scheme=theme)
                    for width in (1280,780,390,320):
                        panel.set_viewport_size({'width':width,'height':900})
                        for name in ('overview','test','keys','history','models','settings'):
                            panel.locator(f'[data-page="{name}"]').first.click()
                            panel.wait_for_selector('#content .card')
                            check(f'{theme}/{width}/{name}无横向溢出',panel.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                            check(f'{theme}/{width}/{name}没有行内事件',panel.locator('[onclick],[onchange]').count()==0)
                            if name=='overview':panel.screenshot(path=str(out/f'overview-{theme}-{width}.png'),full_page=True)
                panel.set_viewport_size({'width':1280,'height':900});panel.locator('[data-page="keys"]').first.click()
                row=panel.locator('tr').filter(has_text='浏览器客户端');panel.once('dialog',lambda d:d.accept());row.get_by_role('button',name='吊销',exact=True).click();panel.get_by_text('已吊销',exact=True).wait_for()
                status,_,_=fixture.request('GET','/boxdetect/api/v1/status',headers={'Authorization':'Bearer '+key})
                check('面板吊销后调用立即失效',status==401)
                panel.locator('[data-action="logout"]').click();panel.get_by_text('管理会话已结束',exact=True).wait_for()
                check('退出清空图片与完整Key',panel.locator('#created-key').input_value()=='' and panel.locator('#detail-content img').count()==0)
                train=context.new_page();train.goto(fixture.base+'/train',wait_until='networkidle')
                check('训练实验入口保留并指向独立面板',train.locator('#tp-progress').count()==1 and train.get_by_role('link',name='AI 框选管理面板').count()==1 and train.locator('#tp-control,#tp-try').count()==0)
                check('浏览器无脚本错误',not errors)
            except Exception:
                if 'panel' in locals():
                    panel.screenshot(path=str(out/'failure.png'),full_page=True)
                    print(panel.locator('#notice').inner_text(),flush=True)
                raise
            finally:
                context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):browser.close()
    finally:
        fixture.doCleanups()
        (out/'result.json').write_text(json.dumps({'results':results,'errors':errors},ensure_ascii=False,indent=2))
    print(f'框选浏览器：{len(results)} 项通过；证据 {out}')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='/tmp/omrs-boxdetect-evidence');args=parser.parse_args();run(Path(args.out))
