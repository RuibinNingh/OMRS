"""仅绑定回环地址的 ONNX local_http 检测服务。"""
import argparse
import base64
import binascii
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.boxdetect.common import ROLES, sha256
from tools.boxdetect.inference import Detector

MAX_BODY = 22 * 1024 * 1024


def make_server(model_dir, port):
    model_dir = Path(model_dir)
    metadata = json.loads((model_dir / 'model.json').read_text())
    model = model_dir / 'model.onnx'
    digest = sha256(model)
    if metadata.get('sha256') != digest or metadata.get('classes') != list(ROLES):
        raise ValueError('模型校验值或类别与元数据不一致')
    detector = Detector(model, conf=float(metadata['conf']))
    if detector.size != metadata.get('imgsz'):
        raise ValueError('输入尺寸与元数据不一致')

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def respond(self, value, code=200):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                self.respond({'file':'model.onnx', 'sha256':digest, 'classes':list(ROLES),
                              'name':metadata['name'], 'imgsz':detector.size, 'conf':detector.conf})
            else:
                self.respond({'error':'接口不存在'}, 404)

        def do_POST(self):
            from PIL import Image
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= MAX_BODY:
                    raise ValueError('请求为空或过大')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict) or not isinstance(payload.get('image'), str):
                    raise ValueError('需要 image dataURL')
                head, encoded = payload['image'].split(',', 1)
                if head not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/gif;base64'):
                    raise ValueError('只接受 PNG/JPEG/GIF dataURL')
                data = base64.b64decode(encoded, validate=True)
                if len(data) > 15 * 1024 * 1024:
                    raise ValueError('图片超过 15 MB')
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 40_000_000:
                        raise ValueError('图片像素超过上限')
                    image.load()
                    predictions = detector(image)
                self.respond({'boxes':[{'label':b['role'], 'bbox_2d':[b['x'], b['y'], min(1., b['x']+b['w']), min(1., b['y']+b['h'])],
                                        'confidence':b['conf']} for b in predictions]})
            except (ValueError, OSError, binascii.Error, Image.DecompressionBombError) as exc:
                self.close_connection = True
                self.respond({'error':str(exc)}, 400)

        def log_message(self, format, *args):
            print(format % args, flush=True)

    return HTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', default=str(Path.home() / 'omrs-train/models/current'))
    parser.add_argument('--port', type=int, default=18765)
    args = parser.parse_args()
    server = make_server(args.model_dir, args.port)
    print(json.dumps({'host':'127.0.0.1', 'port':server.server_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
