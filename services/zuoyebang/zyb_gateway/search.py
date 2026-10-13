"""原图片校验与单次搜题；不重编码、重试或持网络业务锁。"""
import base64
import binascii
import io
import json
import hashlib
import warnings
from .errors import ApiError
from .accounts import safe_upstream
from .vendor.direct import UpstreamError


def validate_image(body,config,detail=None):
    encoded=body.get('image_base64')
    grade=body.get('grade')
    if type(grade) is not int or not 0<=grade<=12 or set(body)!={'image_base64','grade'}:
        raise ApiError('image_invalid','年级须为 0 至 12 的整数，字段必须符合 v1 协议')
    if not isinstance(encoded,str) or not encoded or len(encoded)>((config.max_image_bytes+2)//3)*4:
        raise ApiError('image_invalid','原图片超过 8 MiB 或编码不合法')
    try:
        image=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):
        raise ApiError('image_invalid','请发送无 data 前缀的标准 base64')
    if len(image)>config.max_image_bytes or base64.b64encode(image).decode()!=encoded:
        raise ApiError('image_invalid','原图片大小或 base64 不合法')
    try:
        from PIL import Image
    except ImportError:
        raise ApiError('dependency_missing','请在独立虚拟环境安装 Pillow',503)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image)) as opened:
                if opened.format not in ('PNG','JPEG','WEBP') or opened.width*opened.height>config.max_pixels or getattr(opened,'n_frames',1)!=1:
                    raise ValueError('format/budget')
                opened.verify()
            with Image.open(io.BytesIO(image)) as opened:
                opened.load()
                image_meta = {'content_type':Image.MIME[opened.format], 'width':opened.width, 'height':opened.height, 'bytes':len(image), 'sha256':hashlib.sha256(image).hexdigest()}
    except (OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ApiError('image_invalid','只支持完整单帧 PNG/JPEG/WebP，最多 4000 万像素')
    if detail is not None:
        detail.update(image=image, image_meta=image_meta, grade=grade)
    return image,grade


def search(server,body,key_id,detail=None):
    image,grade=validate_image(body,server.config,detail)
    if not server.search_slots.acquire(blocking=False):
        raise ApiError('concurrency_limited','当前搜题并发预算已用完',429)
    try:
        with server.accounts.snapshot() as (client,raw,generation,_flow):
            server.store.search_budget(key_id)
            client.client.timeout=server.config.upstream_timeout
            try:
                result=client.client.search(image,grade_id=grade)
                if not isinstance(result,dict) or result.get('ok') is not True or not isinstance(result.get('data'),dict):
                    raise ApiError('protocol','官方搜题响应不合法',502)
                encoded=json.dumps({'status':'ok','result':result},ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                if len(encoded)>server.config.max_response_bytes:
                    raise ApiError('response_budget','解码后的响应超过资源预算',502)
            except UpstreamError as exc:
                with server.store.lock:
                    if server.accounts.unchanged(raw,generation):server.accounts.observe('search',exc.kind,exc.code)
                raise safe_upstream(exc)
            except (ValueError,TypeError,RecursionError,UnicodeError):
                raise ApiError('protocol','官方搜题响应不合法',502)
            with server.store.lock:
                if not server.accounts.unchanged(raw,generation):
                    raise ApiError('session_changed','设备会话已更换，旧搜题结果未发布',409)
                server.accounts.observe('search')
            return result
    finally:
        server.search_slots.release()
