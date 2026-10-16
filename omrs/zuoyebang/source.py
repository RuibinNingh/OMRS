"""原图私有保存、完整性读取与人工选择范围的保真裁图。"""
import io
import os
from . import store
from .validation import validate_image
from .geometry import crop_bounds


def metadata(raw):
    from PIL import Image
    mime = validate_image(raw)
    with Image.open(io.BytesIO(raw)) as image:
        return {'width': image.width, 'height': image.height, 'mime': mime, 'sha256': store.fingerprint(raw), 'bytes': len(raw),
                'orientation': image.getexif().get(274, 1)}


def write_asset(vault, identity, filename, raw):
    directory = store.location(vault, identity)
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory / filename
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())


def read(vault, record, *, preview=False):
    info = record.get('image')
    if record.get('kind') != 'search' or not isinstance(info, dict):
        raise store.ZybError('这份旧记录没有保存搜题原图，请重新上传', 'source_missing', 404)
    display = info.get('preview') if preview else None
    path = store.location(vault, record['id']) / ('source-preview.png' if display else 'source.bin')
    if path.is_symlink():
        raise store.ZybError('原图不允许符号链接')
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise store.ZybError('搜题原图不存在，请重新上传', 'source_missing', 404) from None
    expected = display or info
    if store.fingerprint(raw) != expected['sha256']:
        raise store.ZybError('搜题原图已变化，请重新上传', 'source_changed', 409)
    return raw, expected['mime']


def crop(raw, bounds):
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        rectangle = crop_bounds(bounds, image.width, image.height)
        image.load()
        with image.crop(rectangle).convert('RGBA' if 'A' in image.getbands() else 'RGB') as cropped:
            output = io.BytesIO()
            # 不带入 EXIF 方向；坐标与裁切始终以原始像素为准。
            cropped.info.clear()
            cropped.save(output, format='PNG')
            result = output.getvalue()
            return result, {'width': cropped.width, 'height': cropped.height, 'sha256': store.fingerprint(result),
                            'bytes': len(result), 'images': 1, 'html': '', 'empty': False}
