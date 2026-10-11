"""搜题原图验证；只检查格式、尺寸和完整性，不重新编码原始字节。"""
import io
from .store import ZybError

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MIMES = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}


def validate_image(source, total_bytes=None):
    if isinstance(source, bytes):
        total_bytes = len(source)
        source = io.BytesIO(source)
    if type(total_bytes) is not int or not 0 < total_bytes <= MAX_BYTES:
        raise ZybError('请选择不超过8MB的 JPG、PNG 或 WebP 图片')
    try:
        from PIL import Image
    except ImportError as exc:
        raise ZybError('搜题图片验证需要 Pillow，请安装作业帮可选依赖', 'dependency_missing', 503) from exc
    try:
        source.seek(0)
        with Image.open(source) as picture:
            mime = MIMES.get(picture.format)
            if not mime or picture.width * picture.height > MAX_PIXELS:
                raise ZybError('搜题图片格式不受支持或超过4000万像素')
            picture.verify()
        source.seek(0)
        with Image.open(source) as picture:
            picture.load()
        return mime
    except ZybError:
        raise
    except Exception as exc:
        raise ZybError('搜题图片损坏或无法完整解码，请重新上传') from exc
