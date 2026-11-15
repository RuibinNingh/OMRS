"""草稿静态配图：原始字节独立于来源位图，审核与入库共用校验。"""
import base64
import hashlib

from . import question_svg

MAX_DIAGRAMS = 3


def prepare(raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    question_svg.inspect(raw)
    return raw, hashlib.sha256(raw).hexdigest()


def view(raw, digest):
    info = question_svg.inspect(raw)
    actual = info['sha256']
    if actual != digest:
        raise ValueError('草稿SVG内容校验失败，请重新提交配图')
    return {**info, 'bytes': len(raw),
            'src': 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode('ascii')}


def bytes_of(block):
    diagram = block.get('svg') or {}
    src = diagram.get('src', '')
    prefix = 'data:image/svg+xml;base64,'
    if not isinstance(src, str) or not src.startswith(prefix) or len(src) > question_svg.MAX_BYTES * 4 // 3 + 100:
        raise ValueError('草稿SVG数据缺失或超限')
    try:
        raw = base64.b64decode(src[len(prefix):], validate=True)
    except ValueError:
        raise ValueError('草稿SVG数据不合法') from None
    raw, digest = prepare(raw)
    if digest != diagram.get('sha256'):
        raise ValueError('草稿SVG内容校验失败')
    return raw
