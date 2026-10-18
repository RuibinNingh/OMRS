"""临时Vault与固定服务替身：设置中的本机控制、审计和训练分工。"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_traincontrol import ControlTests
from browser_runtime import launch_chromium,open_app
from omrs import traincontrol
from omrs.boxdetect import config
from omrs.cli import OMRSTCPServer
from omrs.server import OMRSHandler
from playwright.sync_api import sync_playwright


def main():
    fixture=ControlTests();fixture.setUp();vault=str(fixture.vault)
    config.save(vault,{'mode':'local','base_url':'http://127.0.0.1:18991','api_key':'box_test'})
    registered=patch.object(traincontrol,'registration',return_value=fixture.config);registered.start()
    class Handler(OMRSHandler):
        vault_path=vault
        def log_message(self,*args):pass
    server=OMRSTCPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_address[1]}';shots=Path(os.environ.get('OMRS_E2E_SHOTS') or tempfile.mkdtemp(prefix='omrs-control-e2e-'));shots.mkdir(parents=True,exist_ok=True)
    checks=[]
    try:
        with sync_playwright() as p:
            browser=launch_chromium(p)
            for width in (1440,390):
                for theme in ('light','dark'):
                    context=browser.new_context(viewport={'width':width,'height':1000})
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
                    open_app(page,base,'settings?section=boxdetect')
                    page.locator('#st-box-controls:not([hidden])').wait_for()
                    def act(action,label):
                        page.locator(f'[data-action="settings.boxControl"][data-arg="{action}"]').click()
                        page.locator('dialog[open] [data-dialog-ok]').last.click()
                        page.get_by_text('本机服务操作已完成，请测试连接核对状态。',exact=True).wait_for()
                        checks.append(label)
                    act('stop','停止');assert not fixture.control.backend.active()
                    act('start','启动');assert fixture.control.backend.active()
                    act('restart','重启');assert fixture.control.backend.health()['name']=='old'
                    page.reload(wait_until='networkidle');page.locator('#st-box-controls:not([hidden])').wait_for()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1');assert not errors,errors
                    page.locator('#st-sec-boxdetect').screenshot(path=str(shots/f'{width}-{theme}.png'));checks.append('刷新/尺寸/主题/无脚本错误')
                    page.goto(base+'/train',wait_until='networkidle');page.locator('#tp-progress').wait_for()
                    assert page.locator('#tp-control,#tp-try').count()==0;checks.append('训练不再控制在线模型')
                    context.close()
            if not os.environ.get('OMRS_TEST_CDP_URL'):browser.close()
        records=[json.loads(p.read_text()) for p in (fixture.root/'managed/service-operations').glob('*.json')]
        assert len(records)==12 and all(r['state']=='done' and r['actor']['client_ip']=='127.0.0.1' for r in records)
        checks.append('12次进程操作均有发起者与结果记录')
        print(f'{len(checks)}/{len(checks)} 通过；四种尺寸/主题设置控制主路径')
    finally:
        server.shutdown();server.server_close();registered.stop();fixture.doCleanups()

if __name__=='__main__':main()
