"""题目 Markdown 中的错因记录；数据库只保留检索身份与操作回执。"""
import copy
import datetime
import hashlib
import json
import re

_SECTION = re.compile(r'^##[ \t]+错因(?:记录)?[ \t]*\r?\n', re.M)
_NEXT = re.compile(r'^#{1,2}[ \t]+', re.M)
_ENTRY = re.compile(r'^###[ \t]+(\d{4}-\d{2}-\d{2}|日期未知)(?:[ \t]+[·|][ \t]+(REF-[\w-]+))?[ \t]*\r?\n', re.M)
_META = re.compile(r'^<!-- omrs-reflection (\{[^\r\n]*\}) -->\r?\n?')


def _headings(pattern, text):
    """代码围栏内的标题是正文，不能把它当作系统分节或日期记录。"""
    blocked, fence, begin, offset = [], None, 0, 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)', line)
        if marker:
            if fence is None:
                fence, begin = marker[1], offset
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                blocked.append((begin, offset + len(line)))
                fence = None
        offset += len(line)
    if fence:
        blocked.append((begin, len(text)))
    return [m for m in pattern.finditer(text) if not any(a <= m.start() < b for a, b in blocked)]


def span(notes):
    matches = _headings(_SECTION, notes)
    if len(matches) > 1:
        raise ValueError('备注有重复错因分节，请先人工整理')
    if not matches:
        return None
    match = matches[0]
    end = next((m for m in _headings(_NEXT, notes) if m.start() >= match.end()), None)
    return match.start(), match.end(), end.start() if end else len(notes)


def notes_of(content):
    from .common import split_sections
    return split_sections(content).get('备注', '')


def without_cause(notes):
    found = span(notes)
    return (notes[:found[0]] + notes[found[2]:]).strip() if found else notes.strip()


def identity(question_id, key):
    return 'REF-' + hashlib.sha256((question_id + ':' + key).encode()).hexdigest()[:32]


def _base(question_id, key, body, date=None):
    return {'id': identity(question_id, key), 'question_id': question_id, 'content_md': body,
            'occurred_at': date, 'created_at': None, 'updated_at': None, 'revision': 1,
            'problem_ids': [], 'recurrence_of': '', 'withdrawn': False,
            'basis': 'user_confirmed', 'source': {'kind': 'markdown'}, 'revisions': []}


def _digest(body, date):
    return hashlib.sha256(json.dumps([body, date], ensure_ascii=False).encode()).hexdigest()


def parse_notes(notes, question_id=''):
    found = span(notes)
    if not found:
        return []
    text = notes[found[1]:found[2]].strip()
    if not text:
        return []
    headings = _headings(_ENTRY, text + '\n')
    values = []
    prefix = text[:headings[0].start()].strip() if headings else text
    if prefix:
        values.append(_base(question_id, 'legacy', prefix))
    for n, heading in enumerate(headings):
        date = None if heading[1] == '日期未知' else datetime.date.fromisoformat(heading[1]).isoformat()
        body = text[heading.end():headings[n + 1].start() if n + 1 < len(headings) else len(text)]
        meta = _META.match(body)
        value = _base(question_id, f'{heading[1]}:{n}', '', date)
        if meta:
            saved = json.loads(meta[1])
            if saved.get('format') != 1 or not heading[2] or saved.get('id') != heading[2]:
                raise ValueError('错因记录元数据损坏，请先核对 Markdown')
            value.update(saved)
            value.pop('format', None)
            body = body[meta.end():]
        elif heading[2]:
            value['id'] = heading[2]
        body = body.strip('\r\n')
        lines = body.splitlines()
        if lines and all(line == '>' or line.startswith('> ') for line in lines):
            body = '\n'.join(line[2:] if line.startswith('> ') else '' for line in lines)
        value.update(content_md=body.strip(), question_id=question_id, occurred_at=date)
        if not value['content_md'] or type(value['revision']) is not int or value['revision'] < 1:
            raise ValueError('错因记录正文或版本无效')
        digest = value.pop('content_digest', None)
        if digest and digest != _digest(value['content_md'], date):
            # 外部 Markdown 编辑也改变 CAS 版本，避免旧表单覆盖外部改动。
            value['revision'] += 1
        values.append(value)
    if len({v['id'] for v in values}) != len(values):
        raise ValueError('错因记录身份重复，请先人工整理')
    return values


def parse(content, question_id):
    return parse_notes(notes_of(content), question_id)


def render(entries):
    blocks = []
    for entry in entries:
        meta = copy.deepcopy(entry)
        body = meta.pop('content_md')
        meta.pop('question_id', None)
        meta.pop('content_hash', None)
        meta.update(format=1, content_digest=_digest(body, entry.get('occurred_at')))
        raw = json.dumps(meta, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        raw = raw.replace('<', '\\u003c').replace('>', '\\u003e').replace('--', '\\u002d\\u002d')
        quoted = '\n'.join('> ' + line if line else '>' for line in body.split('\n'))
        blocks.append(f"### {entry.get('occurred_at') or '日期未知'} · {entry['id']}\n<!-- omrs-reflection {raw} -->\n{quoted}")
    return '\n\n'.join(blocks)


def replace(content, entries):
    from .question_update import _layout
    sections, _ = _layout(content)
    notes = next((s for s in sections if s[0] == '备注'), None)
    if notes is None:
        content = content.rstrip() + '\n\n# 备注\n\n'
        sections, _ = _layout(content)
        notes = next(s for s in sections if s[0] == '备注')
    body = content[notes[1]:notes[2]]
    found = span(body)
    section = '## 错因\n' + render(entries) + '\n\n'
    body = body[:found[0]] + section + body[found[2]:] if found else body.rstrip() + '\n\n' + section
    return content[:notes[1]] + body + content[notes[2]:]


def summary(notes):
    entries = [e for e in parse_notes(notes) if not e['withdrawn']]
    found = span(notes)
    dated = _headings(_ENTRY, notes[found[1]:found[2]]) if found else []
    if len(entries) == 1 and not dated:
        return entries[0]['content_md']
    return '\n\n'.join((e['occurred_at'] or '日期未知') + '\n' + e['content_md'] for e in entries)


def structured(content):
    notes = notes_of(content)
    found = span(notes)
    return bool(found and _headings(_ENTRY, notes[found[1]:found[2]]))
