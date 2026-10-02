"""按题目图片下标读取附件原件；不接受客户端文件名或路径。

共享校验仅解码原字节，不重新编码。Pillow 在校验时才导入，普通 Web
启动和仅导入本模块不增加第三方依赖。
"""

from contextlib import contextmanager
import io
import os
import stat
import warnings

from .common import ATTACHMENTS_DIR, QUESTIONS_DIR
from .path_safety import safe_component

MAX_IMAGE_BYTES = 8 * 1024 * 1024
_FORMATS = {"image/png": "png", "image/jpeg": "jpeg", "image/gif": "gif"}
_DIRECTORY_FDS = (os.open in os.supports_dir_fd and os.scandir in os.supports_fd
                  and hasattr(os, "O_NOFOLLOW"))


def validate_original_image(raw):
    """复用 MCP 上传的完整解码保护，返回元数据与原始字节。"""
    from PIL import Image, UnidentifiedImageError
    from . import drafts

    checked = drafts._validate_mcp_bytes(raw)
    mime, width, height = checked["mime"], checked["width"], checked["height"]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(checked["data"])) as original:
                if Image.MIME.get(original.format) != mime or original.size != (width, height):
                    raise ValueError("图片格式或尺寸与实际内容不一致")
                original.verify()
            # 逐帧检查像素流；始终返回 checked 中的原件，不保存解码结果。
            with Image.open(io.BytesIO(checked["data"])) as original:
                pixels = 0
                for frame in range(100):
                    original.seek(frame)
                    pixels += original.width * original.height
                    if pixels > drafts._MCP_MAX_IMAGE_PIXELS:
                        raise ValueError("图片解码像素总量超过 4000 万限制")
                    original.load()
                    try:
                        original.seek(frame + 1)
                    except EOFError:
                        break
                else:
                    raise ValueError("图片帧数超过 100 帧限制")
    except (OSError, SyntaxError, EOFError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("图片内容无法完整解码，请提供有效 PNG / JPEG / GIF") from exc
    return {**checked, "format": _FORMATS[mime]}


def _linked(info):
    # Windows 的目录联接也是重解析点，不能只检查符号链接 mode。
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def _identity(info):
    return info.st_dev, info.st_ino


def _file_flags():
    return (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))


@contextmanager
def _directory(name, parent=None):
    kwargs = {"dir_fd": parent} if parent is not None else {}
    expected = os.stat(name, follow_symlinks=False, **kwargs)
    if _linked(expected) or not stat.S_ISDIR(expected.st_mode):
        raise ValueError("题图附件目录不是安全的普通目录")
    descriptor = os.open(name, _file_flags() | os.O_DIRECTORY, **kwargs)
    try:
        if _identity(os.fstat(descriptor)) != _identity(expected):
            raise ValueError("题图附件目录在读取期间发生变化，请重试")
        yield descriptor
    finally:
        os.close(descriptor)


def _open_image(name, parent=None, expected=None):
    kwargs = {"dir_fd": parent} if parent is not None else {}
    expected = expected or os.stat(name, follow_symlinks=False, **kwargs)
    if _linked(expected) or not stat.S_ISREG(expected.st_mode):
        raise ValueError("题目引用的图片不是安全的普通文件")
    descriptor = os.open(name, _file_flags(), **kwargs)
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode) or _identity(actual) != _identity(expected):
            raise ValueError("题目引用的图片在读取期间发生变化，请重试")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_bytes(descriptor):
    before = os.fstat(descriptor)
    if before.st_size > MAX_IMAGE_BYTES:
        raise ValueError("题图超过 MCP 单次图片返回限制（8 MiB）")
    chunks, size = [], 0
    while size <= MAX_IMAGE_BYTES:
        chunk = os.read(descriptor, min(64 * 1024, MAX_IMAGE_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    if size > MAX_IMAGE_BYTES:
        raise ValueError("题图超过 MCP 单次图片返回限制（8 MiB）")
    after = os.fstat(descriptor)
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("题目引用的图片在读取期间发生变化，请重试")
    return b"".join(chunks)


def _read_from_directory_fds(vault, name):
    found = None

    def visit(parent):
        nonlocal found
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.name == name:
                    if found is not None:
                        raise ValueError("题目引用的图片文件名不唯一，无法确定原图")
                    found = _open_image(entry.name, parent)
                elif entry.is_dir(follow_symlinks=False):
                    with _directory(entry.name, parent) as child:
                        visit(child)

    try:
        with _directory(vault) as base:
            with _directory(QUESTIONS_DIR, base) as questions:
                with _directory(ATTACHMENTS_DIR, questions) as attachments:
                    visit(attachments)
                    if found is None:
                        raise ValueError("题目引用的图片不存在")
                    return _read_bytes(found)
    finally:
        if found is not None:
            os.close(found)


def _read_from_paths(vault, name):
    """无目录 FD 的平台：拒绝重解析点，并比对目录与文件身份。"""
    roots = [os.path.join(vault, QUESTIONS_DIR)]
    roots.append(os.path.join(roots[0], ATTACHMENTS_DIR))
    directories, candidate = {}, None

    def check_directory(path):
        info = os.lstat(path)
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("题图附件目录不是安全的普通目录")
        identity = _identity(info)
        if path in directories and directories[path] != identity:
            raise ValueError("题图附件目录在读取期间发生变化，请重试")
        directories[path] = identity

    def visit(path):
        nonlocal candidate
        check_directory(path)
        with os.scandir(path) as entries:
            for entry in entries:
                if os.path.normcase(entry.name) == os.path.normcase(name):
                    if candidate is not None:
                        raise ValueError("题目引用的图片文件名不唯一，无法确定原图")
                    candidate = entry.path, entry.stat(follow_symlinks=False)
                elif entry.is_dir(follow_symlinks=False):
                    visit(entry.path)
        check_directory(path)

    for root in [vault, *roots]:
        check_directory(root)
    visit(roots[-1])
    if candidate is None:
        raise ValueError("题目引用的图片不存在")
    path, expected = candidate
    for directory in list(directories):
        check_directory(directory)
    with_descriptor = _open_image(path, expected=expected)
    try:
        raw = _read_bytes(with_descriptor)
        for directory in list(directories):
            check_directory(directory)
        if _identity(os.lstat(path)) != _identity(expected) or _linked(os.lstat(path)):
            raise ValueError("题目引用的图片在读取期间发生变化，请重试")
        return raw
    finally:
        os.close(with_descriptor)


def read_question_image(vault, uid, image_index):
    """按共享 get_question.images 的当前顺序返回 (原始字节, 格式)。"""
    from .agent.tools import read as read_tools

    if not isinstance(uid, str) or not uid.strip() or len(uid) > 200:
        raise ValueError("uid 必须是 1 到 200 个字符的题目编号")
    if type(image_index) is not int or image_index < 0:
        raise ValueError("image_index 必须是从 0 开始的整数")
    images = read_tools.get_question({"vault": vault}, {"uid": uid.strip()})["result"]["images"]
    if not images:
        raise ValueError("题目没有引用图片")
    if image_index >= len(images):
        raise ValueError("图片下标超出题目图片列表范围")
    try:
        name = safe_component(images[image_index], "题图文件名")
        if any(ord(char) < 32 for char in name):
            raise ValueError("题图文件名包含控制字符")
    except (TypeError, ValueError):
        raise ValueError("题目引用的图片文件名不安全") from None
    try:
        base = os.path.realpath(vault)
        raw = (_read_from_directory_fds(base, name) if _DIRECTORY_FDS
               else _read_from_paths(base, name))
    except FileNotFoundError:
        raise ValueError("题目引用的图片不存在") from None
    except OSError:
        raise ValueError("题目引用的图片无法安全读取") from None
    checked = validate_original_image(raw)
    return checked["data"], checked["format"]


def read_draft_image(vault, draft_id, image_index):
    """只读草稿来源列表中的原件，验证 SHA 和目录/文件身份。"""
    import hashlib
    import re
    from . import drafts
    from .common import QUESTIONS_DIR

    if not isinstance(draft_id, str) or not draft_id.strip() or len(draft_id) > 200:
        raise ValueError('draft_id 不能为空或超长')
    if type(image_index) is not int or image_index < 0:
        raise ValueError('image_index 必须是从 0 开始的整数')
    draft = drafts.get_draft(vault, draft_id.strip(), readonly=True)
    sources = draft.get('source_images') or []
    if image_index >= len(sources):
        raise ValueError('图片下标超出草稿来源图片列表范围')
    source = sources[image_index]
    sha = source.get('sha256', '')
    formats = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif'}
    if not re.fullmatch('[0-9a-f]{64}', sha) or source.get('mime') not in formats:
        raise ValueError('草稿原图身份不合法')
    name = sha + '.' + formats[source['mime']]
    parts = [QUESTIONS_DIR, '.omrs', 'drafts', 'images']
    try:
        if _DIRECTORY_FDS:
            from contextlib import ExitStack
            with ExitStack() as stack:
                parent = stack.enter_context(_directory(os.path.realpath(vault)))
                for part in parts:
                    parent = stack.enter_context(_directory(part, parent))
                descriptor = _open_image(name, parent)
                try:
                    raw = _read_bytes(descriptor)
                finally:
                    os.close(descriptor)
        else:
            path = os.path.realpath(vault)
            directories = []
            for part in parts:
                path = os.path.join(path, part)
                info = os.lstat(path)
                if _linked(info) or not stat.S_ISDIR(info.st_mode):
                    raise ValueError('草稿图片目录不安全')
                directories.append((path, _identity(info)))
            descriptor = _open_image(os.path.join(path, name))
            try:
                raw = _read_bytes(descriptor)
                for directory, identity in directories:
                    if _identity(os.lstat(directory)) != identity or _linked(os.lstat(directory)):
                        raise ValueError('草稿图片目录在读取期间变化')
            finally:
                os.close(descriptor)
    except OSError:
        raise ValueError('草稿原图无法安全读取') from None
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('草稿原图内容与登记 SHA 不一致')
    checked = validate_original_image(raw)
    return checked['data'], checked['format']
