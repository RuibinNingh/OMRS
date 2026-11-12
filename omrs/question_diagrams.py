"""审核中的SVG新增／替换：预览不写附件，批准后沿用正式改题事务。"""
import base64
import os
import re

from . import question_svg as svg


def validate(entries):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 3:
        raise ValueError('diagrams须为1至3张配图的数组，复杂内容请拆分')
    out, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {'section', 'svg', 'replace'}:
            raise ValueError('SVG配图只允许section、svg和可选replace')
        if entry.get('section') not in ('题目', '答案'):
            raise ValueError('SVG配图须明确属于题目或答案')
        source = entry.get('svg')
        if not isinstance(source, str) or len(source) > svg.MAX_BYTES:
            raise ValueError('svg须为至多256KiB的源码字符串')
        svg.inspect(source.encode('utf-8'))
        replacement = entry.get('replace', '')
        if (not isinstance(replacement, str) or replacement != os.path.basename(replacement)
                or '\\' in replacement or (replacement and not replacement.lower().endswith('.svg'))):
            raise ValueError('replace只能是原章节已有的SVG文件名，不能替换截图或传路径')
        if replacement and replacement in seen:
            raise ValueError('一次提案不能重复替换同一张SVG')
        seen.add(replacement)
        out.append({'section': entry['section'], 'svg': source, 'replace': replacement})
    return out


def apply(content, entries):
    from .common import parse_yaml_frontmatter
    from .question_update import _layout, _IMAGES
    question_id = parse_yaml_frontmatter(content).get('_omrs_id', '')
    for entry in entries:
        name = svg.name_for(question_id, entry['svg'].encode('utf-8'))
        sections, _ = _layout(content)
        slot = next((s for s in sections if s[0] == entry['section']), None)
        if not slot:
            raise ValueError('添加配图的题目章节不存在，请先整理题目格式')
        body = content[slot[1]:slot[2]].strip()
        token = f'![[{name}]]'
        if entry['replace']:
            def filename(token):
                match = re.fullmatch(r'!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', token)
                return match[1].replace('\\', '/').rsplit('/', 1)[-1] if match else ''
            matches = [m for m in _IMAGES.finditer(body) if filename(m[0]) == entry['replace']]
            if len(matches) != 1:
                raise ValueError('要替换的SVG须在指定章节以Obsidian图片引用恰好出现一次')
            match = matches[0]
            body = body[:match.start()] + token + body[match.end():]
        elif token not in body:
            body += ('\n\n' if body else '') + token
        content = content[:slot[1]] + body + '\n\n' + content[slot[2]:]
    return content


def preview(vault, entries):
    from .question_images import read_attachment_image
    result, sources = [], []
    for entry in entries:
        raw = entry['svg'].encode('utf-8')
        info = svg.inspect(raw)
        item = {**info, 'section': entry['section'], 'replace': entry['replace'],
                'src': 'data:' + svg.MIME + ';base64,' + base64.b64encode(raw).decode('ascii')}
        if entry['replace']:
            before, mime = read_attachment_image(vault, entry['replace'])
            if mime != svg.MIME:
                raise ValueError('只允许替换已有SVG附件')
            previous = svg.inspect(before)
            item['before_src'] = 'data:' + mime + ';base64,' + base64.b64encode(before).decode('ascii')
            sources.append({'name': entry['replace'], 'sha256': previous['sha256']})
        result.append(item)
    return result, sources


def save(vault, question_id, entries):
    return [svg.save(vault, question_id, entry['svg'].encode('utf-8'))[0] for entry in entries]
