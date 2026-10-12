"""独立安装包真实 HTTP 冒烟：不用源码 cwd、不打印任何密码。"""
import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'docs',prefix='installed-smoke-') as tmp:
        process=subprocess.Popen([str(ROOT/'.venv/bin/zuoyebang-gateway'),'serve','--data-dir',str(Path(tmp)/'private'),'--port','0'],cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        assertions=[]
        try:
            while True:
                line=process.stdout.readline()
                if line.startswith('监听：'):port=int(line.strip().rsplit(':',1)[1]);break
                if not line:raise AssertionError('独立安装包未正常启动')
            def get(path):
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                connection.request('GET',path)
                response=connection.getresponse();raw=response.read();result=(response.status,response.getheader('Content-Type'),raw)
                connection.close();return result
            status,_,raw=get('/healthz');assert status==200 and json.loads(raw)=={'service':'zuoyebang-gateway','version':'1.0.0','status':'ok'};assertions.append('installed_health_exact')
            status,_,raw=get('/');assert status==200 and '作业帮'.encode() in raw;assertions.append('installed_panel_html')
            status,mime,raw=get('/assets/panel.js');assert status==200 and 'javascript' in mime and b'addEventListener' in raw;assertions.append('installed_static_assets')
            status,_,raw=get('/api/v1/status');assert status==401 and json.loads(raw)['code']=='key_invalid';assertions.append('installed_api_requires_key')
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise AssertionError('自己的服务未能正常停止')
        assert process.returncode==0
        print(json.dumps({'installed_package_smoke':'ok','assertions':assertions,'own_process_pid':process.pid,'own_process_stopped':True,'returncode':process.returncode,'real_credentials_used':False},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
