"""正式题目的位图编辑，只更新已审批的附件引用。"""
import base64
import binascii
import hashlib
import io
import math
import os
import re
from dataclasses import dataclass

from .errors import RequestError
from .path_safety import safe_component
from .question_images import (MAX_IMAGE_BYTES, publish_attachment, read_attachment_image,
                              validate_original_image)

_SUFFIXES = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif'}
_TARGET = re.compile(r'\.(?:png|jpe?g|gif)\Z', re.I)
_BASE64_LIMIT = (MAX_IMAGE_BYTES + 2) // 3 * 4
_BOX_KEYS = ('x', 'y', 'w', 'h')


@dataclass
class ImageEdit:
    section: str
    target: str
    occurrence: int | None
    action: str
    source_hash: str
    name: str = ''
    image: bytes = b''

    def receipt(self):
        return {'section': self.section, 'target': self.target, 'occurrence': self.occurrence,
                'action': self.action, 'name': self.name or None}


def _box(value):
    if not isinstance(value, dict) or set(value) != set(_BOX_KEYS):
        raise ValueError('裁剪框必须包含 x、y、w、h')
    if any(type(value[k]) not in (int, float) or not 0 <= value[k] <= 1 for k in _BOX_KEYS):
        raise ValueError('裁剪框坐标必须是 0 到 1 的有限数值')
    x, y, w, h = (value[k] for k in _BOX_KEYS)
    if not (w > 0 and h > 0 and x + w <= 1 + 1e-9 and y + h <= 1 + 1e-9):
        raise ValueError('裁剪框超出图片范围')
    return {key: float(value[key]) for key in _BOX_KEYS}


def validate(entries, *, agent=False):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 3:
        raise ValueError('image_edits 须为 1 至 3 项位图修改')
    image_key = 'image_ref' if agent else 'data_base64'
    clean, size = [], 0
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('section') not in ('题目', '答案'):
            raise ValueError('位图修改须指定题目或答案分节')
        target = safe_component(entry.get('target'), '原图文件名')
        if not _TARGET.search(target) or any(ord(ch) < 32 for ch in target):
            raise ValueError('原图须是 PNG、JPEG 或 GIF 附件文件名')
        action = entry.get('action')
        if action not in ('replace', 'crop', 'remove'):
            raise ValueError('位图修改仅支持 replace、crop、remove')
        allowed = {'section', 'target', 'occurrence', 'action'}
        item = {**entry, 'target': target}
        if 'occurrence' in entry and (type(entry['occurrence']) is not int or entry['occurrence'] < 1):
            raise ValueError('occurrence 须为从 1 开始的整数')
        if action == 'replace':
            allowed.add(image_key)
            value = entry.get(image_key)
            if not isinstance(value, str) or not value:
                raise ValueError(f'替换图片须提供 {image_key}')
            if agent:
                if not re.fullmatch(r'IMG-[1-9][0-9]*', value) or len(value) > 24:
                    raise ValueError('image_ref 须为对话中的 IMG-n')
            else:
                size += len(value)
                if size > _BASE64_LIMIT:
                    raise ValueError('一次提案的替换图片总大小不得超过 8 MiB')
        elif action == 'crop':
            allowed.add('box')
            item['box'] = _box(entry.get('box'))
        if entry.keys() - allowed:
            raise ValueError('图片修改包含该操作不支持的字段')
        clean.append(item)
    return clean


def resolve_agent_images(vault, conversation_id, entries):
    from . import drafts
    clean = validate(entries, agent=True)
    for entry in clean:
        if entry['action'] == 'replace':
            if not conversation_id:
                raise ValueError('替换图片须来自当前对话')
            source = drafts.resolve_image(vault, conversation_id, entry.pop('image_ref'))
            entry['data_base64'] = drafts.image_data_url(vault, source['sha256']).split(',', 1)[1]
    return validate(clean)


def _target_name(token):
    if token.startswith('![['):
        value = token[3:-2].partition('|')[0]
    else:
        match = re.fullmatch(r'!\[(?:\\.|[^\]\\])*\]\((.*)\)', token)
        value = match[1] if match else ''
        if re.match(r'^(?:[a-z][a-z0-9+.-]*://|//|data:)', value, re.I):
            return ''
    return value.replace('\\', '/').rsplit('/', 1)[-1].strip()


def _matches(content, entries):
    from .question_update import _IMAGES, _layout
    sections, _ = _layout(content)
    used = set()
    for entry in entries:
        section, target = entry['section'], entry['target']
        slot = next((span for span in sections if span[0] == section), None)
        matches = [m for m in _IMAGES.finditer(content, slot[1], slot[2])
                   if _target_name(m[0]) == target] if slot else []
        occurrence = entry.get('occurrence')
        if not matches or (occurrence and occurrence > len(matches)):
            raise ValueError('指定分节中没有该图片引用')
        if occurrence is None and len(matches) != 1:
            raise ValueError('图片在该分节出现多次，请指定从 1 开始的 occurrence')
        match = matches[(occurrence or 1) - 1]
        if match.start() in used:
            raise ValueError('一次提案不能重复修改同一处图片')
        used.add(match.start())
        yield match


def _read(vault, target):
    raw, mime = read_attachment_image(vault, target, maximum=MAX_IMAGE_BYTES)
    if mime not in _SUFFIXES:
        raise ValueError('原附件不是 PNG、JPEG 或 GIF 位图')
    return raw


def _replacement(encoded):
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('替换图片 Base64 不合法') from exc


def _crop(raw, box):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        if getattr(source, 'is_animated', False):
            raise ValueError('动图可替换或移除，裁剪请使用静态图片')
        image = ImageOps.exif_transpose(source)
        width, height = image.size
        x, y, w, h = (box[key] for key in _BOX_KEYS)
        pixels = (math.floor(x * width), math.floor(y * height),
                  min(width, math.ceil((x + w) * width)), min(height, math.ceil((y + h) * height)))
        if pixels == (0, 0, width, height):
            return raw
        result = io.BytesIO()
        image.crop(pixels).convert('RGBA').save(result, format='PNG')
        return result.getvalue()


def _preview(raw):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((640, 640))
        rgba = image.convert('RGBA')
        display = Image.new('RGB', rgba.size, 'white')
        display.paste(rgba, mask=rgba.getchannel('A'))
        buffer = io.BytesIO()
        display.save(buffer, format='JPEG', quality=82)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def prepare(vault, question_id, content, entries, *, show_preview):
    if not re.fullmatch(r'OP-[0-9]+', question_id):
        raise ValueError('位图修改须绑定稳定题目身份')
    matches = list(_matches(content, entries))
    material, previews, uploaded_bytes = [], [], 0
    for entry, match in zip(entries, matches):
        action, target = entry['action'], entry['target']
        before = _read(vault, target)
        validate_original_image(before)
        edit = ImageEdit(entry['section'], target, entry.get('occurrence'), action,
                         hashlib.sha256(before).hexdigest())
        after = None
        if action == 'replace':
            after = _replacement(entry['data_base64'])
            uploaded_bytes += len(after)
            if uploaded_bytes > MAX_IMAGE_BYTES:
                raise ValueError('一次提案的替换图片总大小不得超过 8 MiB')
        elif action == 'crop':
            after = _crop(before, entry['box'])
        if after is not None:
            if after == before:
                edit.name = target
            else:
                info = validate_original_image(after)
                edit.image = after
                edit.name = f"{question_id}-img-{hashlib.sha256(after).hexdigest()}.{_SUFFIXES[info['mime']]}"
        material.append(edit)
        if show_preview:
            previews.append({**edit.receipt(), 'before_src': _preview(before),
                             'after_src': _preview(after) if after is not None else None})
    for edit, match in sorted(zip(material, matches), key=lambda pair: pair[1].start(), reverse=True):
        if edit.name == edit.target:
            continue
        width = re.search(r'\|\d+\]\]$', match[0]) if match[0].startswith('![[') else None
        suffix = width[0][:-2] if width else ''
        replacement = f'![[{edit.name}{suffix}]]' if edit.name else ''
        content = content[:match.start()] + replacement + content[match.end():]
    sources = [{**edit.receipt(), 'source_hash': edit.source_hash} for edit in material]
    return content, material, previews, sources


def verify_sources(vault, edits):
    for edit in edits:
        try:
            current = hashlib.sha256(_read(vault, edit.target)).hexdigest()
        except (OSError, ValueError) as exc:
            raise RequestError('content_conflict', '原图片已变更，请重新发起提案') from exc
        if current != edit.source_hash:
            raise RequestError('content_conflict', '原图片已变更，请重新发起提案')


def save(vault, edits):
    for edit in edits:
        if edit.image:
            publish_attachment(vault, edit.name, edit.image, MAX_IMAGE_BYTES)


def public_payload(payload):
    patch = payload.get('patch') or {}
    if not isinstance(patch, dict) or not patch.get('image_edits'):
        return payload
    edits = [{key: value for key, value in edit.items() if key != 'data_base64'}
             for edit in patch['image_edits']]
    return {**payload, 'patch': {**patch, 'image_edits': edits}}
