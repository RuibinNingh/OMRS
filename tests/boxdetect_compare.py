"""迁移前源码、新服务与兼容入口的真实推理对照；不调用生产检测端口。"""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True, help='迁移前 Git 源码的临时归档')
    parser.add_argument('--python', required=True, help='仅有推理依赖的隔离解释器')
    parser.add_argument('--model-dir', required=True, help='只读模型快照')
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    before = Path(args.before).resolve()
    model = Path(args.model_dir).resolve()
    dataset = Path(args.dataset).resolve()
    manifest = json.loads((dataset / 'manifest.json').read_text())
    samples = sorted((s for s in manifest['samples'] if s['split'] == 'test'), key=lambda s: s['height'])
    images = []
    for label, sample in [('short', samples[0]), ('long', samples[-1])]:
        with Image.open(dataset / sample['file']) as image:
            buf = io.BytesIO()
            image.convert('RGB').save(buf, 'PNG')
        images.append((label, buf.getvalue()))
    buf = io.BytesIO()
    Image.new('RGB', (640, 640), 'white').save(buf, 'PNG')
    images.append(('blank', buf.getvalue()))
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'PYTHONHOME', 'OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL')}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results = {}
    with tempfile.TemporaryDirectory(prefix='boxdetect-compare-') as temp:
        for label, cwd, entry in [
            ('before', before, [str(before / 'tools/boxdetect/serve.py')]),
            ('service', ROOT / 'services/boxdetect', ['-m', 'boxdetect_service', 'serve']),
            ('legacy', ROOT, [str(ROOT / 'tools/boxdetect/serve.py')]),
        ]:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            with (Path(temp) / (label + '.log')).open('w') as log:
                compatibility=[] if label=='before' else ['--data-dir',str(Path(temp)/('state-'+label)),'--legacy-loopback']
                proc = subprocess.Popen([args.python, *entry, '--model-dir', str(model), '--port', str(port),*compatibility],
                                        cwd=cwd, env=env, stdout=log, stderr=log)
                try:
                    base = f'http://127.0.0.1:{port}'
                    for _ in range(100):
                        try:
                            with opener.open(base + '/health', timeout=1) as response:
                                health = json.load(response)
                            break
                        except OSError:
                            if proc.poll() is not None:
                                raise RuntimeError(label + ' 提前退出')
                            time.sleep(.1)
                    else:
                        raise RuntimeError(label + ' 未就绪')
                    predictions = {}
                    for name, image in images:
                        body = json.dumps({'image': 'data:image/png;base64,' + base64.b64encode(image).decode()}).encode()
                        request = urllib.request.Request(base + '/detect', data=body, headers={'Content-Type': 'application/json'})
                        with opener.open(request, timeout=20) as response:
                            predictions[name] = json.load(response)
                    results[label] = {'health': health, 'predictions': predictions}
                finally:
                    proc.terminate()
                    proc.wait(timeout=5)
    assert results['before'] == results['service'] == results['legacy'], '新旧模型身份或完整预测不一致'
    report = {'entries': list(results), 'cases': [name for name, _ in images], 'exact_match': True,
              'health': results['service']['health'],
              'box_counts': {name: len(value['boxes']) for name, value in results['service']['predictions'].items()}}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
