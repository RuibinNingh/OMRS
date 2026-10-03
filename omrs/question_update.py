"""正式题目受限补丁：绑定身份和正文版本，保留分节、图片与历史。"""
import json
import os
import re
import stat

from .common import extract_knowledge_tags, extract_labels, parse_yaml_frontmatter
from .content_history import question_file
from .data_repository import resolve_question, storage_write
from .errors import RequestError
from .ledger import blob_hash
from .mcp.common import fingerprint
from .vault_lifecycle import generation, storage

FIELDS = {'question_text': '题目', 'answer_text': '答案', 'cause': '错因', 'note': '补充备注',
          'knowledge_points': '知识点', 'difficulty': '难度', 'labels': '标记'}
_H1 = re.compile(r'^#\s+([^\r\n]+)(?:\r?\n|$)', re.M)
_H2 = re.compile(r'^##(?!#)[ \t]*([^\r\n]+)(?:\r?\n|$)', re.M)
_IMAGES = re.compile(r'!\[\[[^\]\r\n]+\]\]|!\[(?:\\.|[^\]\\\r\n])*\]\((?:\\.|[^()\\\r\n]|\((?:\\.|[^()\\\r\n])*\))*\)')
_BYPASS = re.compile(r'<\s*(?:img|picture|svg|object|embed)\b|!\[|data\s*:', re.I)


def _read(vault, row):
    """拒绝链接和读取期间变化，返回实际 Markdown 与文件身份。"""
    path = question_file(vault, row)
    cursor = os.path.abspath(path)
    while cursor != os.path.abspath(vault):
        if os.path.islink(cursor):
            raise RequestError('content_conflict', '题目路径包含链接，已拒绝编辑')
        parent = os.path.dirname(cursor)
        if parent == cursor:
            raise RequestError('content_conflict', '题目路径身份不明确')
        cursor = parent
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'r', encoding='utf-8', newline='') as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise RequestError('content_conflict', '题目不是普通文件')
        content = file.read()
        after = os.fstat(file.fileno())
    current = os.stat(path, follow_symlinks=False)
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if identity(before) != identity(after) or identity(before) != identity(current):
        raise RequestError('content_conflict', '读取时题目发生变化，请重试')
    if parse_yaml_frontmatter(content).get('_omrs_id') != row['question_id']:
        raise RequestError('identity_conflict', '题目文件身份与题库不一致')
    return content, [before.st_dev, before.st_ino]


def _spans(content, pattern, start=0, end=None):
    end = len(content) if end is None else end
    matches = list(pattern.finditer(content, start, end))
    return [(re.sub(r'[ \t]+#+[ \t]*$', '', m.group(1)).strip(), m.end(), matches[i + 1].start() if i + 1 < len(matches) else end)
            for i, m in enumerate(matches)]


def _layout(content):
    sections = _spans(content, _H1)
    for name in ('题目', '答案', '备注', '历史'):
        if sum(s[0] == name for s in sections) > 1:
            raise RequestError('content_conflict', '题目有重复系统分节，请先人工整理')
    notes = next((s for s in sections if s[0] == '备注'), None)
    subs = _spans(content, _H2, notes[1], notes[2]) if notes else []
    for name in ('错因', '关联', '补充备注'):
        if sum(s[0] == name for s in subs) > 1:
            raise RequestError('content_conflict', '备注有重复系统子节，请先人工整理')
    return sections, subs


def editable_values(content):
    sections, subs = _layout(content)
    values = {}
    for field, name in FIELDS.items():
        spans = subs if field in ('cause', 'note') else sections
        found = next((s for s in spans if s[0] == name), None)
        if field in ('question_text', 'answer_text', 'cause', 'note'):
            values[field] = content[found[1]:found[2]].strip() if found else ''
            if field == 'question_text' and values[field] == '（请在 Obsidian 中编辑此题目内容）':
                values[field] = ''
    meta = parse_yaml_frontmatter(content)
    values.update(knowledge_points=extract_knowledge_tags(meta), labels=extract_labels(meta),
                  difficulty=int(meta.get('难度', 5)))
    return values


def note_of(content):
    """补充备注不包含旧裸文本、错因、关联或陌生子节。"""
    notes = next((s for s in _spans(content, _H1) if s[0] == '备注'), None)
    subs = _spans(content, _H2, notes[1], notes[2]) if notes else []
    note = next((s for s in subs if s[0] == '补充备注'), None)
    return content[note[1]:note[2]].strip() if note else ''


def validate_patch(patch):
    if not isinstance(patch, dict) or not patch or set(patch) - FIELDS.keys():
        raise ValueError('patch 必须是非空的可编辑字段补丁')
    clean = {}
    for key, value in patch.items():
        if key == 'difficulty':
            if type(value) is not int or not 1 <= value <= 10:
                raise ValueError('难度必须是 1 到 10 的整数')
        elif key in ('knowledge_points', 'labels'):
            if not isinstance(value, list) or len(value) > 64:
                raise ValueError('知识点和标记必须是至多 64 项的字符串数组')
            if any(not isinstance(v, str) or not v.strip() or len(v) > 200 or
                   any(ord(c) < 32 or ord(c) == 127 for c in v) for v in value):
                raise ValueError('知识点和标记不能为空或包含控制字符')
            value = [v.strip() for v in value]
            if key == 'knowledge_points':
                value = [v[2:-2].strip() if v.startswith('[[') and v.endswith(']]') else v for v in value]
                if any(not v or '[[' in v or ']]' in v for v in value):
                    raise ValueError('知识点名称包含不合法的链接边界')
            value = list(dict.fromkeys(value))
        else:
            if not isinstance(value, str) or len(value) > 500000 or '\x00' in value:
                raise ValueError('正文必须是不含空字符、至多 500000 字符的文字')
            forbidden = r'^#{1,2}\s+' if key in ('cause', 'note') else r'^#\s+'
            if re.search(forbidden, value, re.M):
                raise ValueError('补丁不能注入系统分节标题')
            if key in ('cause', 'note') and re.search(r'^##[ \t]*(?:错因|关联|补充备注)', value, re.M):
                raise ValueError('补丁不能注入兼容系统子节标题')
            value = value.strip()
        clean[key] = value
    return clean


def _keep_images(old, new):
    original, proposed = _IMAGES.findall(old), _IMAGES.findall(new)
    # 除两种已识别的字面图片外，不接受 HTML、引用式图片或 data URL 绕过。
    without_tokens = _IMAGES.sub('', new)
    if _BYPASS.search(without_tokens):
        raise ValueError('补丁不能添加 HTML、引用式或内联编码图片')
    if proposed and proposed != original:
        raise ValueError('原图片的字面引用、次数、顺序和所属分节必须保留')
    if not proposed and original:
        new = new + ('\n\n' if new else '') + '\n'.join(original)
    return new


def _replace_text(content, field, value):
    sections, subs = _layout(content)
    name = FIELDS[field]
    found = next((s for s in (subs if field in ('cause', 'note') else sections) if s[0] == name), None)
    old = content[found[1]:found[2]].strip() if found else ''
    new = _keep_images(old, value)
    if new == old:
        return content
    if found:
        return content[:found[1]] + new + '\n\n' + content[found[2]:]
    if field in ('cause', 'note'):
        notes = next((s for s in sections if s[0] == '备注'), None)
        if not notes:
            anchor = next((s for s in _H1.finditer(content) if s.group(1).strip() in ('答案', '历史')), None)
            at = anchor.start() if anchor else len(content)
            content = content[:at].rstrip('\r\n') + '\n\n# 备注\n\n' + content[at:]
            sections, _ = _layout(content)
            notes = next(s for s in sections if s[0] == '备注')
        at = notes[2]
        return content[:at].rstrip('\r\n') + f'\n\n## {name}\n{new}\n\n' + content[at:]
    return content.rstrip('\r\n') + f'\n\n# {name}\n{new}\n'


def _replace_yaml(content, key, value):
    front = re.match(r'\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)', content, re.S)
    if not front:
        raise ValueError('题目缺少可编辑的 YAML 元数据')
    lines = front.group(1).splitlines()
    slots = [i for i, line in enumerate(lines) if re.match(rf'^{re.escape(key)}\s*:', line)]
    if len(slots) > 1:
        raise RequestError('content_conflict', '题目有重复元数据字段，请先人工整理')
    if isinstance(value, list):
        replacement = [f'{key}:'] + ['  - ' + json.dumps(v, ensure_ascii=False) for v in value] if value else [f'{key}: []']
    else:
        replacement = [f'{key}: {value}']
    if slots:
        start, end = slots[0], slots[0] + 1
        while end < len(lines) and (lines[end].startswith((' ', '\t')) or not lines[end].strip()):
            end += 1
        lines[start:end] = replacement
    else:
        lines.extend(replacement)
    return '---\n' + '\n'.join(lines) + '\n---\n' + content[front.end():]


def patch_content(content, patch):
    patch = validate_patch(patch)
    values = editable_values(content)
    for field, value in patch.items():
        if value == values[field]:
            continue
        if field in ('question_text', 'answer_text', 'cause', 'note'):
            content = _replace_text(content, field, value)
        else:
            key = {'knowledge_points': '相关知识点', 'labels': '标记', 'difficulty': '难度'}[field]
            saved = [f'[[{v}]]' for v in value] if field == 'knowledge_points' else value
            content = _replace_yaml(content, key, saved)
    return content


@storage
def prepare_update(vault, uid, question_id, expected_content_hash, patch, reason=''):
    if not isinstance(uid, str) or not uid.strip() or not isinstance(question_id, str) or not question_id:
        raise ValueError('必须提供题目 UID 与稳定 question_id')
    if not isinstance(expected_content_hash, str) or not re.fullmatch('[0-9a-f]{64}', expected_content_hash):
        raise ValueError('必须提供完整的 expected_content_hash')
    patch = validate_patch(patch)
    if not isinstance(reason, str) or len(reason) > 2000 or '\x00' in reason:
        raise ValueError('修改理由必须是不含空字符、至多 2000 字符的文字')
    reason = reason.strip()
    row = resolve_question(vault, uid=uid.strip(), question_id=question_id)
    if not row:
        raise RequestError('not_found', '题目不存在或已归档')
    content, _ = _read(vault, row)
    if blob_hash(content) != expected_content_hash:
        raise RequestError('content_conflict', '题目正文已变化，请重新读题后提交')
    if 'labels' in patch:
        from .labels import list_label_defs
        known = {d['name'] for d in list_label_defs(vault) if not d.get('archived')}
        if set(patch['labels']) - known:
            raise ValueError('只能设置当前已存在的标记')
    final = patch_content(content, patch)
    before, after = editable_values(content), editable_values(final)
    changes = [{'field': k, 'label': FIELDS[k], 'before': before[k], 'after': after[k],
                'kind': 'list' if isinstance(after[k], list) else 'number' if k == 'difficulty' else 'text'} for k in patch]
    payload = {'uid': row['uid'], 'question_id': question_id, 'expected_content_hash': expected_content_hash, 'patch': patch, 'reason': reason}
    preview = {'title': f"修改题目 {row['uid']}", 'summary': '、'.join(FIELDS[k] for k in patch), 'changes': changes, 'reason': reason}
    snapshot = {'question_id': question_id, 'uid': row['uid'], 'file_path': row['file_path'],
                'content_hash': expected_content_hash, 'generation': generation(vault)}
    return payload, preview, snapshot


@storage_write
def apply_update(vault, review):
    from .question_update_journal import apply, receipt, recover_pending
    from .actor import current_agent
    actor = current_agent()
    count = len(actor.commits) if actor else 0
    try:
        return apply(vault, review)
    except Exception:
        # 普通异常立即按同一崩溃协议收束；进程中断留给启动恢复。
        recover_pending(vault)
        committed = receipt(vault, review)
        if committed:
            return {**committed, 'reused': True}
        if actor:
            del actor.commits[count:]
        raise


def recover_pending(vault, allow_recovery=True):
    from .question_update_journal import recover_pending as recover
    return recover(vault, allow_recovery=allow_recovery)


def recover_receipt(vault, row):
    from .question_update_journal import receipt
    return receipt(vault, row)


@storage
def prepare_agent(vault, tool, args):
    row = resolve_question(vault, uid=args.get('uid', '').strip())
    if not row:
        raise RequestError('not_found', '题目不存在')
    content, _ = _read(vault, row)
    if tool == 'update_question_section':
        field = {'题目': 'question_text', '答案': 'answer_text', '错因': 'cause'}.get(args.get('section'))
        if not field or args.get('mode', 'replace') not in ('replace', 'append'):
            raise ValueError('不支持的题目分节或编辑方式')
        text = args.get('content', '')
        validate_patch({field: text})
        old = editable_values(content)[field]
        if args.get('mode') == 'append' and old:
            text = old + '\n\n' + text.strip()
        patch = {field: text}
    elif tool == 'set_knowledge_points':
        patch = {'knowledge_points': args.get('points')}
    else:
        raise ValueError('工具没有正式题目补丁契约')
    payload, preview, snapshot = prepare_update(vault, row['uid'], row['question_id'], blob_hash(content), patch)
    before, after = editable_values(content), editable_values(patch_content(content, payload['patch']))
    preview.update(uid=row['uid'], content_hash=blob_hash(content))
    if tool == 'update_question_section':
        from .common import extract_images
        preview.update(section=args['section'], mode=args.get('mode') or 'replace', before=before[field], after=after[field],
                       question=before['question_text'], answer=before['answer_text'], images_kept=extract_images(before[field]))
    else:
        preview.update(before=before['knowledge_points'], after=after['knowledge_points'])
    return {'payload': payload, 'preview': preview, 'snapshot': snapshot, 'editable_fields': list(patch)}


def apply_agent(vault, row, ctx=None):
    result = apply_update(vault, row)
    preview = row.get('preview') or {}
    if row['tool'] == 'update_question_section':
        field = next(iter(row['payload']['patch']))
        result = {**result, 'section': preview.get('section'), 'before': preview.get('before', ''),
                  'after': result['fields'][field]}
    elif row['tool'] == 'set_knowledge_points':
        after = result['fields']['knowledge_points']
        result = {**result, 'before': preview.get('before', []), 'after': after, 'points': after}
    return {'result': result, 'summary': '没有实际变化' if result.get('no_op') else '已写入',
            'commits': result.get('commits', []), 'wrote': not result.get('no_op')}
