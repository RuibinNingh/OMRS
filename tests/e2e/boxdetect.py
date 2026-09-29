"""真实 ONNX 服务与隔离 OMRS 浏览器链路；只从外部数据快照取图。"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from browser_runtime import launch_chromium
from omrs.common import save_config


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait_api(base,path):
    for _ in range(150):
        try:
            with urllib.request.urlopen(base+path,timeout=1) as response:return json.load(response)
        except OSError:time.sleep(.1)
    raise RuntimeError('隔离实例未就绪')


def main():
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',required=True)
    parser.add_argument('--train-dir',default=str(Path.home()/'omrs-train'))
    parser.add_argument('--shots',default='/tmp/omrs-box-detect-real-shots')
    args=parser.parse_args()
    dataset=Path(args.dataset);root=Path(args.train_dir);shots=Path(args.shots);shots.mkdir(parents=True,exist_ok=True)
    model=json.loads((root/'models/current/model.json').read_text())
    evaluation=json.loads((root/'runs'/model['run']/'eval.json').read_text())
    manifest=json.loads((dataset/'manifest.json').read_text())
    # 此测试检查接入协议；精度验收仍以完整冻结测试集为准。
    candidates={r['id'] for r in evaluation['rows'] if r['question']['iou']>=.75 and r['answer']['iou']>=.75}
    samples=sorted([s for s in manifest['samples'] if s['split']=='test' and s['id'] in candidates],key=lambda s:s['height'])
    if len(samples)<3:raise RuntimeError('不足三张两框达标的样本，请先检查模型评估')
    samples=[samples[0],samples[len(samples)//2],samples[-1]]
    env=os.environ.copy();env.pop('OMRS_SYSTEMD_SERVICE',None)
    checks=[]
    with tempfile.TemporaryDirectory(prefix='omrs-model-e2e-') as temp:
        vault=Path(temp)/'vault'
        subprocess.run([sys.executable,str(ROOT/'tests/fixtures/make_vault.py'),'--out',str(vault),'--profile','empty'],check=True,stdout=subprocess.DEVNULL)
        detect_port=free_port();port=free_port()
        service_log=(shots/'serve.log').open('w')
        detector=subprocess.Popen([str(root/'.venv/bin/python'),str(ROOT/'tools/boxdetect/serve.py'),'--model-dir',str(root/'models/current'),'--port',str(detect_port)],env=env,stdout=service_log,stderr=service_log)
        proc=None
        try:
            health=wait_api(f'http://127.0.0.1:{detect_port}','/health')
            assert health['sha256']==model['sha256'];checks.append('health SHA-256 与固定模型一致')
            save_config(str(vault),{'train_dir':str(root),'inbox_detect_provider':'local_http',
                'inbox_local_detect_url':f'http://127.0.0.1:{detect_port}/detect','inbox_blind_every':0,
                'inbox_auto_ready_conf':0,'inbox_auto_on_upload':False,'train_try_collect':False})
            proc=subprocess.Popen([sys.executable,str(ROOT/'omrs_engine.py'),'--vault',str(vault),'serve','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            base=f'http://127.0.0.1:{port}';wait_api(base,'/api/status')
            with sync_playwright() as playwright:
                browser=launch_chromium(playwright);ctx=browser.new_context(viewport={'width':1440,'height':1000})
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/#/create',wait_until='networkidle')
                for index,sample in enumerate(samples):
                    page.locator('#create-flow [data-ib-stage="upload"]').click()
                    page.locator('#ib-file').set_input_files({'name':f'测试-{index}.jpg','mimeType':'image/jpeg','buffer':(dataset/sample['file']).read_bytes()})
                    tile=page.locator('.crw-grid-item',has_text=f'测试-{index}.jpg')
                    tile.locator('[data-action="create.gridOpen"]').click()
                    page.get_by_role('button',name='AI 框选此图',exact=True).click()
                    page.wait_for_selector('.crp-box[data-role="question"]',timeout=30000)
                    page.wait_for_selector('.crp-box[data-role="answer"]',timeout=30000)
                    page.screenshot(path=str(shots/f'inbox-{index}.png'))
                    checks.append(f'收件箱真实 AI 框选第 {index+1} 张显示两类框（高 {sample["height"]}）')
                page.goto(base+'/train',wait_until='networkidle')
                page.wait_for_selector('#tp-curves svg')
                page.get_by_role('button',name=model['run'],exact=True).click()
                page.wait_for_selector('#tp-evaluation .tp-compare')
                assert f'{evaluation["model"]["answer"]["pass_rate"]*100:.1f}%' in page.locator('#tp-evaluation').inner_text()
                checks.append('真实实验五块可读，答案达标率与 eval.json 一致')
                for theme in ('light','dark'):
                    page.evaluate("value=>{localStorage.setItem('omrs-theme',value);document.documentElement.dataset.theme=value}",theme)
                    page.screenshot(path=str(shots/f'panel-real-{theme}.png'),full_page=True)
                sample=max([s for s in manifest['samples'] if s['split']=='test'],key=lambda s:s['height'])
                before={str(p.relative_to(vault)):p.read_bytes() for p in vault.rglob('*') if p.is_file()}
                page.locator('#tp-file').set_input_files({'name':'实时长图.jpg','mimeType':'image/jpeg','buffer':(dataset/sample['file']).read_bytes()})
                with page.expect_response('**/api/trainpanel/try') as response:
                    page.get_by_role('button',name='测试',exact=True).click()
                result=response.value.json()
                assert response.value.status==200,result
                page.wait_for_selector('.tp-box')
                after={str(p.relative_to(vault)):p.read_bytes() for p in vault.rglob('*') if p.is_file()}
                assert before==after,'未开启积累却修改了 Vault'
                (shots/'real-try-summary.json').write_text(json.dumps({k:result[k] for k in ['width','height','strips','elapsed_ms']},indent=2))
                page.screenshot(path=str(shots/'panel-real-try.png'))
                checks.append(f'实时测试高 {sample["height"]}，{result["strips"]} 条带，{result["elapsed_ms"]} ms；Vault 未修改')
                detector.terminate();detector.wait(timeout=10)
                page.goto(base+'/#/create',wait_until='networkidle')
                page.locator('#create-flow [data-ib-stage="process"]').click()
                page.get_by_role('button',name='AI 框选此图',exact=True).click()
                page.locator('.ui-toast',has_text='连不上本地检测服务').first.wait_for(timeout=15000)
                page.screenshot(path=str(shots/'inbox-service-offline.png'))
                checks.append('服务停掉后收件箱显示连不上本地检测服务')
                assert not errors,errors
                ctx.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):browser.close()
        finally:
            if proc:proc.terminate();proc.wait(timeout=10)
            if detector.poll() is None:detector.terminate();detector.wait(timeout=10)
            service_log.close()
    for check in checks:print('PASS',check)
    print(f'{len(checks)}/{len(checks)} 通过；截图 {shots}')


if __name__=='__main__':main()
