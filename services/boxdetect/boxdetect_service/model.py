"""模型身份与预检校验；只读取显式指定的模型目录。"""
import hashlib
import json
from pathlib import Path

ROLES = ('question', 'answer')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def model_info(folder):
    folder = Path(folder)
    meta = json.loads((folder / 'model.json').read_text())
    model = folder / 'model.onnx'
    if not model.is_file() or model.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('模型缺失或超过64MiB')
    if meta.get('classes') != list(ROLES) or meta.get('imgsz') not in (640, 960):
        raise ValueError('模型类别或输入尺寸不支持')
    if not isinstance(meta.get('conf'), (int, float)) or not 0 < meta['conf'] <= 1:
        raise ValueError('模型阈值不合法')
    if sha256(model) != meta.get('sha256'):
        raise ValueError('模型哈希不匹配')
    return meta
