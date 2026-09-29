"""临时Vault、随机HTTP端口与受管服务替身，验证页面控制主路径。"""
import json
import os
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_traincontrol import ControlTests
from browser_runtime import launch_chromium
from omrs.cli import OMRSTCPServer
from omrs.server import OMRSHandler
from playwright.sync_api import sync_playwright


def main():
    fixture=ControlTests();fixture.setUp();vault=str(fixture.vault)
    class Handler(OMRSHandler):
        vault_path=vault
        def log_message(self,*args):pass
    server=OMRSTCPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_address[1]}';shots=Path('/tmp/omrs-control-e2e');shots.mkdir(exist_ok=True)
    checks=[]
    try:
        with sync_playwright() as p:
            browser=launch_chromium(p)
            for width in (1440,390):
                for theme in ('light','dark'):
                    context=browser.new_context(viewport={'width':width,'height':1000})
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
                    page.goto(base+'/train',wait_until='networkidle');
                    try:page.wait_for_selector('#tc-model',timeout=10000)
                    except Exception:
                        print('浏览器错误',errors,flush=True);print(page.locator('body').inner_text()[:1800],flush=True);raise
                    def act(label):
                        page.locator('#tp-control').get_by_role('button',name=label,exact=True).click()
                        confirm = ('确认应用未通过验收模型' if label == '应用到框选'
                                   else '确认' + label)
                        page.get_by_role('button',name=confirm,exact=True).click()
                        page.wait_for_function("()=>document.querySelector('#tc-result')?.textContent.includes('已完成') && !document.querySelector('#tp-control').textContent.includes('操作进行中')")
                    page.locator('#tc-model').select_option('new')
                    assert fixture.control.backend.health()['name']=='old';checks.append('查看模型不应用')
                    act('应用到框选');assert fixture.control.backend.health()['name']=='new';checks.append('切换新模型')
                    page.reload(wait_until='networkidle');page.wait_for_selector('#tc-model');assert '实际在线：new' in page.locator('#tp-control').inner_text();checks.append('刷新保留在线模型')
                    act('恢复上一模型');assert fixture.control.backend.health()['name']=='old';checks.append('恢复旧模型')
                    act('停止服务');assert fixture.control.backend.health() is None;checks.append('停止')
                    act('启动服务');assert fixture.control.backend.health()['name']=='old';checks.append('启动')
                    act('重启服务');checks.append('重启')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1');assert not errors,errors
                    page.locator('#tp-control').screenshot(path=str(shots/f'{width}-{theme}.png'));checks.append('尺寸/主题/无脚本错误')
                    context.close()
            if not os.environ.get('OMRS_TEST_CDP_URL'):browser.close()
        print(f'{len(checks)}/{len(checks)} 通过；四种尺寸/主题服务控制主路径')
    finally:
        server.shutdown();server.server_close();fixture.doCleanups()

if __name__=='__main__':main()
