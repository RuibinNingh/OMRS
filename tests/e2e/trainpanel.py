"""训练面板真实浏览器：入口、增量轮询、测试积累、错误与四档审计。"""
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tests')); sys.path.insert(0, str(ROOT / 'tests/e2e'))
from browser_runtime import launch_chromium
from create import AUDIT
from omrs.common import save_config
from tools.boxdetect.common import atomic_json

AUDIT_PANEL = AUDIT.replace("document.querySelector('#ib-stage-quick')", "document.querySelector('#tp-app')")


def png():
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (200, 1200), (230, 240, 250)).save(buf, 'PNG')
    return buf.getvalue()


def fixture(root, epoch=1, pid=None):
    metric = {'mean_iou': .85, 'pass_rate': .8, 'passed': 12, 'total': 15, 'extra': 0, 'histogram': [0,0,0,0,0,0,0,3,6,6]}
    summary = {'images':15, 'unchanged':12, 'unchanged_rate':.8, 'question':metric, 'answer':metric}
    atomic_json(root / 'runs/fixture/status.json', {'state':'running', 'epoch':epoch, 'epochs':10,
        'pid':os.getpid() if pid is None else pid, 'dataset':'d1', 'epoch_seconds':8,
        'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    with (root / 'runs/fixture/metrics.jsonl').open('w') as stream:
        for n in range(1, epoch+1):
            stream.write(json.dumps({'epoch':n, 'train/box_loss':1/n, 'train/cls_loss':2/n,
                'val/box_loss':1.2/n, 'val/cls_loss':2.2/n, 'metrics/mAP50(B)':.6+n*.02, 'metrics/mAP50-95(B)':.5+n*.02})+'\n')
    atomic_json(root / 'runs/fixture/eval.json', {'split':'test','conf':.25,'model':summary,'template':summary,
        'overlays':[{'name':'fixture.png','id':'fake'}]})
    path=root / 'runs/fixture/overlays'; path.mkdir(exist_ok=True); (path/'fixture.png').write_bytes(png())
    atomic_json(root / 'datasets/d1/manifest.json', {'version':'d1','counts':{'train':39,'val':8,'test':15},
        'strip_counts':{'train':47,'val':11,'test':20},'samples':[], 'excluded':[{'id':'fake','reason':'模拟排除'}]})
    atomic_json(root / 'models/current/model.json', {'name':'fixture','run':'fixture','sha256':'a'*64,'created_at':'2026-09-29'})


def fake_service():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"name":"fixture","sha256":"fake"}')
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            body=json.dumps({'boxes':[{'label':'question','bbox_2d':[.1,.1,.9,.4],'confidence':.9},
                {'label':'answer','bbox_2d':[.1,.5,.9,.95],'confidence':.85}]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server


def main():
    from playwright.sync_api import sync_playwright
    results=[]
    shots=Path(os.environ.get('OMRS_SHOTS','/tmp/omrs-box-detect-panel-shots')); shots.mkdir(parents=True,exist_ok=True)
    def check(name, ok, detail=''):
        results.append((name,bool(ok),detail)); print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    with tempfile.TemporaryDirectory(prefix='omrs-trainpanel-e2e-') as temp:
        vault=Path(temp)/'vault'; root=Path(temp)/'train'; fixture(root)
        subprocess.run([sys.executable,str(ROOT/'tests/fixtures/make_vault.py'),'--out',str(vault),'--profile','empty'],check=True,stdout=subprocess.DEVNULL)
        detector=fake_service()
        save_config(str(vault),{'train_dir':str(root),'inbox_local_detect_url':f'http://127.0.0.1:{detector.server_port}/detect'})
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        env=os.environ.copy();env.pop('OMRS_SYSTEMD_SERVICE',None)
        proc=subprocess.Popen([sys.executable,str(ROOT/'omrs_engine.py'),'--vault',str(vault),'serve','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        base=f'http://127.0.0.1:{port}'
        def api(path):
            with urllib.request.urlopen(base+path,timeout=10) as response:return json.load(response)
        try:
            for _ in range(100):
                try:api('/api/status');break
                except Exception:time.sleep(.1)
            with sync_playwright() as playwright:
                browser=launch_chromium(playwright)
                ctx=browser.new_context(viewport={'width':1440,'height':900})
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/#/create',wait_until='networkidle')
                page.locator('#create-flow [data-ib-stage="train"]').click()
                link=page.get_by_role('link',name='打开训练面板',exact=True)
                check('录入页保留标注入口并增加训练面板新标签页链接',link.get_attribute('target')=='_blank' and page.locator('#ib-tr-annotate-open').count()==1)
                with ctx.expect_page() as popup:link.click()
                panel=popup.value; panel.on('pageerror',lambda e:errors.append(str(e)))
                panel.wait_for_load_state('networkidle')
                panel.wait_for_selector('#tp-curves svg[data-points="1"]')
                check('五块与当前模型真实读取假实验文件',all(panel.get_by_role('heading',name=n,exact=True).count() for n in ['训练进度','训练曲线','效果评估','数据概况','实验历史']) and 'fixture' in panel.locator('#tp-head').inner_text())
                fixture(root,epoch=2)
                panel.wait_for_selector('#tp-curves svg[data-points="2"]',timeout=10000)
                check('10 秒内进度与两张曲线同步前进',panel.locator('#tp-progress progress').get_attribute('value')=='2' and panel.locator('#tp-curves svg[data-points="2"]').count()==2)
                fixture(root,epoch=2,pid=999999999)
                panel.get_by_text('已中断',exact=True).first.wait_for(timeout=10000)
                check('进程消失显示已中断与续训命令',panel.get_by_role('button',name='复制续训命令',exact=True).count()==1)
                panel.locator('#tp-file').set_input_files({'name':'try.png','mimeType':'image/png','buffer':png()})
                # 初始化标注库后记录整个临时 Vault 的文件内容。
                api('/api/annotate/images')
                before={str(p.relative_to(vault)):p.read_bytes() for p in vault.rglob('*') if p.is_file()}
                panel.get_by_role('button',name='测试',exact=True).click()
                panel.wait_for_selector('.tp-box-answer')
                after={str(p.relative_to(vault)):p.read_bytes() for p in vault.rglob('*') if p.is_file()}
                check('实时测试出两类框、置信度与耗时，积累关闭无文件改动',before==after and panel.locator('.tp-box-question').count()>0 and 'ms' in panel.locator('#tp-try-result').inner_text())
                panel.locator('label.ui-switch',has_text='积累到标注集').click()
                panel.wait_for_function("() => !document.querySelector('#tp-collect').disabled && document.querySelector('#tp-collect').checked")
                panel.get_by_role('button',name='测试',exact=True).click()
                panel.get_by_text('已加入标注集（待校正）',exact=True).wait_for()
                images=api('/api/annotate/images')['images']; boxes=images[0]['boxes']
                check('积累后只有一张 todo 且含模型框',len(images)==1 and images[0]['status']=='todo' and len(boxes)>0)
                panel.get_by_role('button',name='测试',exact=True).click()
                panel.get_by_text('标注集里已有这张',exact=True).wait_for()
                check('重复测试不新增、不覆盖已有框',len(api('/api/annotate/images')['images'])==1 and api('/api/annotate/images')['images'][0]['boxes']==boxes)
                panel.reload(wait_until='networkidle')
                panel.wait_for_function("() => document.querySelector('#tp-collect')?.checked")
                check('刷新后积累开关仍开启',panel.locator('#tp-collect').is_checked())
                detector.shutdown();detector.server_close()
                panel.locator('#tp-file').set_input_files({'name':'try.png','mimeType':'image/png','buffer':png()})
                panel.get_by_role('button',name='测试',exact=True).click()
                panel.get_by_role('alert').filter(has_text='检测服务未启动').wait_for(timeout=10000)
                check('服务停掉提示启动命令且按钮恢复可操作',not panel.get_by_role('button',name='测试',exact=True).is_disabled() and 'serve.py' in panel.locator('#tp-try-result').inner_text())
                panel.close();page.close();ctx.close()
                # 四档审计 × 浅深主题 × 桌面手机，加载档由拦截返回延迟复现。
                for mode in ('normal','empty','error','loading'):
                    selected=root if mode!='empty' else Path(temp)/'empty-train'
                    save_config(str(vault),{'train_dir':str(selected),'train_try_collect':False})
                    if mode=='error':(root/'runs/fixture/eval.json').write_text('{broken')
                    for theme in ('light','dark'):
                        for label,viewport,target in [('desktop',(1440,900),28),('mobile',(390,844),40)]:
                            context=browser.new_context(viewport={'width':viewport[0],'height':viewport[1]})
                            context.add_init_script(f"localStorage.setItem('omrs-theme','{theme}')")
                            audit_page=context.new_page();audit_page.on('pageerror',lambda e:errors.append(str(e)))
                            pending=[]
                            if mode=='loading':audit_page.route('**/api/trainpanel/overview',lambda route:pending.append(route))
                            audit_page.goto(base+'/train',wait_until='domcontentloaded')
                            if mode=='loading':audit_page.wait_for_selector('.ui-skeleton')
                            elif mode=='empty':audit_page.get_by_text('还没有训练记录',exact=True).wait_for()
                            elif mode=='error':audit_page.locator('#tp-evaluation [role=alert]').wait_for()
                            else:audit_page.wait_for_selector('#tp-curves svg')
                            audit=audit_page.evaluate(AUDIT_PANEL,target)
                            ok=bool(audit['sizes']) and min(audit['sizes'])>=12 and len(audit['sizes'])<=6 and not any(audit[k] for k in ('small','inline','handlers','over','overflow'))
                            check(f'四档审计 {mode}/{label}/{theme}',ok,str(audit))
                            audit_page.screenshot(path=str(shots/f'{mode}-{label}-{theme}.png'),full_page=True)
                            if mode=='loading':
                                for route in pending:route.fulfill(status=503,content_type='application/json',body='{"status":"error","msg":"模拟加载结束"}')
                                audit_page.wait_for_function("() => !document.querySelector('#tp-progress .ui-skeleton')")
                            context.close()
                check('页面脚本错误为零',not errors,str(errors))
                if not os.environ.get('OMRS_TEST_CDP_URL'):browser.close()
        except Exception as exc:
            check('浏览器主路径异常',False,repr(exc))
        finally:
            proc.terminate();proc.wait(timeout=10)
            detector.shutdown();detector.server_close()
    failed=[r for r in results if not r[1]]
    for name,ok,detail in failed:print('FAIL',name,detail)
    print(f'{len(results)-len(failed)}/{len(results)} 通过；截图 {shots}')
    return bool(failed)


if __name__=='__main__':sys.exit(main())
