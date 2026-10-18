"""仅复制独立项目，构建并在外部最小环境安装，执行真实模型及 HTTP 冒烟。"""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import venv


def run(command, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('独立包命令失败：' + result.stderr[-2000:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--wheelhouse', help='离线依赖 wheel 目录；提供时不联网')
    parser.add_argument('--out', help='可选 JSON 验收结果文件')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'PYTHONHOME', 'OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL')}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='boxdetect-package-') as temp:
        root = Path(temp)
        project = root / 'source'
        shutil.copytree(source, project, ignore=shutil.ignore_patterns('__pycache__', '.venv', 'build', 'dist', '*.egg-info', '.state', 'private'))
        model = root / 'model'
        model.mkdir()
        for name in ['model.onnx', 'model.json']:
            shutil.copyfile(Path(args.model_dir) / name, model / name)
        meta = json.loads((model / 'model.json').read_text())
        wheels = root / 'wheels'
        run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--disable-pip-version-check',
             '--wheel-dir', str(wheels), str(project)], root, env)
        runtime = root / 'runtime'
        venv.EnvBuilder(with_pip=True).create(runtime)
        python = runtime / 'bin' / 'python'
        install = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
        if args.wheelhouse:
            install += ['--no-index', '--find-links', str(Path(args.wheelhouse).resolve())]
        run(install + ['-r', str(project / 'requirements.txt')], root, env)
        run([str(python), '-m', 'pip', 'install', '--no-deps', '--disable-pip-version-check',
             str(next(wheels.glob('*.whl')))], root, env)
        shutil.rmtree(project)
        outside = root / 'outside'
        outside.mkdir()
        audit = """import io, base64, json, sys, importlib.util, importlib.metadata
from PIL import Image
from boxdetect_service.inference import Detector
image = Image.new('RGB', (48, 96), 'white')
Detector(sys.argv[1], conf=float(sys.argv[2]))(image)
for prefix in ['omrs', 'tools', 'torch', 'ultralytics']:
    assert importlib.util.find_spec(prefix) is None, prefix
    assert not any(n == prefix or n.startswith(prefix + '.') for n in sys.modules), prefix
buf = io.BytesIO(); image.save(buf, 'PNG')
long_buf = io.BytesIO(); Image.new('RGB', (320, 1600), 'white').save(long_buf, 'PNG')
print(json.dumps({'image':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode(),
                 'long_image':'data:image/png;base64,'+base64.b64encode(long_buf.getvalue()).decode(),
                 'versions':{n:importlib.metadata.version(n) for n in ['onnxruntime','numpy','Pillow']}}))
"""
        audit_result = json.loads(run([str(python), '-I', '-c', audit, str(model / 'model.onnx'), str(meta['conf'])], outside, env))
        assert audit_result['versions'] == {'onnxruntime': '1.30.0', 'numpy': '2.5.2', 'Pillow': '12.3.0'}
        run([str(python), '-I', '-m', 'boxdetect_service', 'probe', '--model-dir', str(model)], outside, env)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        with (root / 'server.log').open('w') as log:
            proc = subprocess.Popen([str(python), '-I', '-m', 'boxdetect_service', 'serve', '--model-dir', str(model), '--port', str(port), '--data-dir', str(root/'state'), '--legacy-loopback'],
                                    cwd=outside, env=env, stdout=log, stderr=log)
            try:
                base = f'http://127.0.0.1:{port}'
                for _ in range(100):
                    try:
                        with opener.open(base + '/health', timeout=1) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        if proc.poll() is not None:
                            raise RuntimeError('安装后的检测服务提前退出')
                        time.sleep(.1)
                else:
                    raise RuntimeError('安装后的检测服务未就绪')
                assert health == {key: meta[key] for key in ['name', 'sha256', 'classes', 'imgsz', 'conf']} | {'file': 'model.onnx'}
                request = urllib.request.Request(base + '/detect',
                                                 data=json.dumps({'image': audit_result['image']}).encode(),
                                                 headers={'Content-Type': 'application/json'})
                with opener.open(request, timeout=10) as response:
                    predictions = json.load(response)
                assert set(predictions) == {'boxes'}
                for box in predictions['boxes']:
                    assert set(box) == {'label', 'bbox_2d', 'confidence'}
                    assert box['label'] in ['question', 'answer'] and len(box['bbox_2d']) == 4
                    assert all(0 <= value <= 1 for value in box['bbox_2d'])
                def api(path,body=None,headers=None):
                    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                                               headers={'Content-Type':'application/json','Origin':base,**(headers or {})})
                    with opener.open(req,timeout=30) as response:
                        return json.load(response),dict(response.headers)
                login,heads=api('/api/admin/login',{'password':(root/'state/admin-secret.txt').read_text().strip()})
                admin={'Cookie':heads['Set-Cookie'].split(';')[0],'X-CSRF-Token':login['csrf_token']}
                created,_=api('/api/admin/keys',{'name':'独立安装包验收'},admin)
                whole,_=api('/api/v1/detect',{'image':audit_result['long_image'],'request_id':'e'*32},
                            {'Authorization':'Bearer '+created['key']})
                assert whole['strips']>1 and whole['model']['sha256']==meta['sha256']
                history,_=api('/api/admin/history',headers=admin)
                assert len([r for r in history['items'] if r['request_id']=='e'*32])==1
                for path in ('/','/assets/panel.js','/assets/panel.css'):
                    with opener.open(base+path,timeout=5) as response:assert len(response.read())>100
            finally:
                proc.terminate()
                proc.wait(timeout=5)
        report = {'checks': 11, 'health': health, 'versions': audit_result['versions'],
                  'forbidden_modules': [], 'http_boxes': len(predictions['boxes']),'whole_image_strips':whole['strips'],'panel_assets':3}
        if args.out:
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
