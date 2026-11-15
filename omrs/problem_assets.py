"""问题私有附件：内容寻址、静态SVG页面profile，不改变题目图规范。"""
import base64
import hashlib
import os
import re
from xml.etree import ElementTree as ET
from .question_images import _directory, _open_image, _read_bytes, validate_original_image
from .zuoyebang import svg

MAX_BYTES = 8*1024*1024
NAME = re.compile(r'PA-[0-9a-f]{64}\.(?:svg|png|jpg|gif|webp)\Z')


def inspect(raw, banner=False):
    if not raw or len(raw) > (256*1024 if banner else MAX_BYTES):
        raise ValueError('附件为空或超过大小限制')
    if raw.lstrip().startswith(b'<'):
        if len(raw)>256*1024:
            raise ValueError('SVG超过256KiB')
        svg.validate(raw)
        root = ET.fromstring(raw)
        if len(list(root.iter())) > 1000:
            raise ValueError('SVG节点过多')
        if banner:
            from .question_svg import inspect as print_inspect
            info = print_inspect(raw,print_mm=197.3)
            if info['print_height_mm'] > 28:
                raise ValueError('首页提醒高度超过28mm，请精简SVG')
        return 'svg', 'image/svg+xml'
    if banner:
        raise ValueError('调度提醒只接受静态SVG')
    mime = validate_original_image(raw)["mime"]
    suffix = {'image/png':'png','image/jpeg':'jpg','image/gif':'gif','image/webp':'webp'}.get(mime)
    if not suffix:
        raise ValueError('不支持的图片格式')
    return suffix,mime


def save(vault, data):
    encoded = data.get('data_base64','')
    if not isinstance(encoded,str) or len(encoded) > (MAX_BYTES+2)//3*4:
        raise ValueError('附件超过8MiB')
    raw = base64.b64decode(encoded,validate=True)
    ext,mime = inspect(raw)
    name = 'PA-'+hashlib.sha256(raw).hexdigest()+'.'+ext
    # 目录描述符逐层拒绝链接；在同目录用排他创建发布不可变对象。
    with _directory(os.path.abspath(vault)) as base, _directory('错题',base) as questions, _directory('.omrs',questions) as internal:
        try:
            os.mkdir('problem-assets',mode=0o700,dir_fd=internal)
        except FileExistsError:
            pass
        with _directory('problem-assets',internal) as assets:
            temporary = '.upload-'+os.urandom(16).hex()
            fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=assets)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary,name,src_dir_fd=assets,dst_dir_fd=assets,follow_symlinks=False)
                except FileExistsError:
                    fd = _open_image(name,assets)
                    try:
                        if _read_bytes(fd,MAX_BYTES)!=raw:
                            raise ValueError('附件内容校验失败')
                    finally:
                        os.close(fd)
                os.fsync(assets)
            finally:
                os.unlink(temporary,dir_fd=assets)
    return {'id':name,'name':name,'mime':mime,'bytes':len(raw),'markdown':'![]('+name+')'}


def read(vault, name):
    if not isinstance(name,str) or not NAME.fullmatch(name):
        raise ValueError('附件身份无效')
    with _directory(os.path.abspath(vault)) as base, _directory('错题',base) as questions, _directory('.omrs',questions) as internal, _directory('problem-assets',internal) as assets:
        fd = _open_image(name,assets)
        try:
            raw = _read_bytes(fd,MAX_BYTES)
        finally:
            os.close(fd)
    if name.split('.')[0][3:]!=hashlib.sha256(raw).hexdigest():
        raise ValueError('附件摘要不一致')
    return raw,inspect(raw)[1]
