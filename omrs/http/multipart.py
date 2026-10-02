"""从已限时接收的磁盘正文分离 multipart 文件；文件只产生暂存引用。"""
import email.message
import mmap
import os
import tempfile

from ..http_io import BodyError
from ..uploads import stage_file


def files(stream, content_type, vault, purpose):
    header = email.message.Message()
    header["Content-Type"] = content_type
    boundary = header.get_param("boundary")
    if not isinstance(boundary, str) or not boundary or len(boundary) > 200:
        raise BodyError("multipart boundary 不合法")
    try:
        delimiter = b"--" + boundary.encode("ascii")
    except UnicodeError as exc:
        raise BodyError("multipart boundary 必须为 ASCII") from exc
    stream.seek(0, os.SEEK_END)
    if not stream.tell():
        raise BodyError("multipart 正文为空")
    result = []
    with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        if mapped[:len(delimiter)] != delimiter:
            raise BodyError("multipart 请求缺少起始边界")
        position = len(delimiter)
        while mapped[position:position + 2] != b"--":
            if mapped[position:position + 2] != b"\r\n":
                raise BodyError("multipart 边界格式错误")
            start = position + 2
            header_end = mapped.find(b"\r\n\r\n", start, start + 16384)
            if header_end < 0:
                raise BodyError("multipart 文件头缺失或超过 16 KiB")
            next_boundary = mapped.find(b"\r\n" + delimiter, header_end + 4)
            if next_boundary < 0:
                raise BodyError("multipart 请求提前结束")
            item = email.message.Message()
            try:
                for line in mapped[start:header_end].decode("utf-8").split("\r\n"):
                    name, value = line.split(":", 1)
                    item[name] = value.strip()
            except (UnicodeError, ValueError) as exc:
                raise BodyError("multipart 文件头格式错误") from exc
            filename = item.get_filename()
            if filename is not None:
                filename = os.path.basename(filename) or "image"
                with tempfile.NamedTemporaryFile("w+b") as output:
                    offset = header_end + 4
                    while offset < next_boundary:
                        block = mapped[offset:min(offset + 65536, next_boundary)]
                        output.write(block)
                        offset += len(block)
                    output.flush()
                    complete = stage_file(vault, output.name, filename,
                                          item.get_content_type(), purpose)
                result.append((filename, {"upload_ref": complete["upload_ref"]}))
            position = next_boundary + 2 + len(delimiter)
        if not result:
            raise BodyError("未找到上传文件")
    stream.seek(0)
    return result
