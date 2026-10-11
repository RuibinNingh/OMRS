"""渲染题卡的幂等创建；冻结人工内容、预留身份，复用 Ledger 创建回执。"""
import datetime
import json
import os
import uuid
from pathlib import Path
from .. import creation
from ..creation_operation import CreationOperation
from ..ledger import connect, reserve_operation_id
from ..migration import ensure_ledger_bootstrap
from ..taxonomy import category_path
from ..vault_lifecycle import lease
from ..locking import write_lock
from . import store, jobs


def payload_of(record, data):
    form = data.get('form') or {}
    sections = data.get('sections') or {}
    subject, category = str(form.get('subject') or '').strip(), str(form.get('category') or '').strip()
    if not subject or not category:
        raise store.ZybError('请填写科目和分类')
    difficulty = int(form.get('difficulty') or 5)
    if not 1 <= difficulty <= 10:
        raise store.ZybError('难度必须为1到10')
    payload = {'subject': subject, 'category': category, 'difficulty': difficulty,
               'cause': str(form.get('cause') or ''), 'sections': {}}
    for name in ('related_tags', 'labels'):
        values = form.get(name) or []
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise store.ZybError('知识点和标记必须是字符串数组')
        payload[name] = list(dict.fromkeys(values))
    for role in ('question', 'answer'):
        section = sections.get(role) or {}
        mode = section.get('mode')
        empty = record['images'][role].get('empty')
        if mode not in ('image', 'text', 'none') or (mode == 'none') != bool(empty):
            raise store.ZybError('题干与答案的保存方式不合法')
        text = str(section.get('text') or '').strip() if mode == 'text' else ''
        if mode == 'text' and not text:
            raise store.ZybError('文本保存需要完整正文，请补录或保留图片')
        payload['sections'][role] = {'mode': mode, 'text': text,
                                     'sha256': record['images'][role].get('sha256', '')}
    return payload


def digest_of(payload):
    return store.fingerprint(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())


def receipt(vault, record):
    op = record['commit']
    with connect(vault) as db:
        row = db.execute('SELECT result_json FROM op_results WHERE op_id=?', (op['id'],)).fetchone()
        if not row:
            return None
        result = json.loads(row[0])
        commit = db.execute('SELECT commit_type,payload_json FROM commits WHERE commit_id=?', (result.get('commit_id'),)).fetchone()
        payload = json.loads(commit[1]) if commit else {}
        question = payload.get('question') or {}
        origin = payload.get('_inbox') or {}
        identity = op['identity']
        if (not commit or commit[0] != 'question.create' or result.get('digest') != op['digest'] or
                origin.get('zuoyebang_render_id') != record['id'] or origin.get('operation_id') != op['id'] or
                any(question.get(name) != identity[name] or result.get(name) != identity[name] for name in ('question_id', 'uid', 'file_path'))):
            raise store.ZybError('创建回执与来源不一致，数据已保留', 'operation_pending', 409)
        return {**result, 'reused': True}


def pending_question_ids(vault):
    """扫描跳过尚无创建事实的预留文件，防止抢先按外部题目入账。"""
    directory = Path(creation.questions_root(vault)) / '.omrs' / 'zuoyebang'
    if not directory.exists():
        return set()
    with lease(vault):
        pending = set()
        for path in store.root(vault).glob('render-*/record.json'):
            record = store.read(vault, path.parent.name)
            if record.get('commit') and receipt(vault, record) is None:
                pending.add(record['commit']['identity']['question_id'])
        return pending


def commit(vault, identity, data):
    with lease(vault), write_lock():
        record = store.read(vault, identity)
        if record.get('status') != 'ready':
            raise store.ZybError('请先完成后端渲染')
        payload = payload_of(record, data)
        digest = digest_of(payload)
        op = record.get('commit')
        if op and op['digest'] != digest:
            raise store.ZybError('这份渲染已有创建预留，请用首次提交的内容重试；原内容已保留', 'operation_pending', 409)
        if not op:
            ensure_ledger_bootstrap(vault)
            directory, subject, category = category_path(vault, payload['subject'], payload['category'])
            uid = creation._next_uid(creation.questions_root(vault), category)
            op = {'id': 'zyb-' + uuid.uuid4().hex, 'digest': digest, 'payload': payload, 'artifacts': {},
                  'identity': {'uid': uid, 'question_id': reserve_operation_id(vault),
                               'file_path': os.path.relpath(os.path.join(directory, uid + '.md'), vault),
                               'today': datetime.date.today().isoformat()}}
            record['commit'] = op
            store.save(vault, identity, record)
        previous = receipt(vault, record)
        if previous:
            op['result'] = previous
            store.save(vault, identity, record)
            return previous
        def validate(current_vault):
            current = store.read(current_vault, identity).get('commit') or {}
            if current.get('id') != op['id'] or current.get('digest') != digest:
                raise store.ZybError('创建预留已变化', 'operation_pending', 409)
            qroot = os.path.realpath(creation.questions_root(current_vault))
            for relative, checksum in current.get('artifacts', {}).items():
                path = os.path.join(current_vault, relative)
                if os.path.islink(path) or os.path.commonpath((qroot, os.path.realpath(path))) != qroot:
                    raise store.ZybError('预留产物路径不合法', 'operation_pending', 409)
                if os.path.exists(path):
                    with open(path, 'rb') as file:
                        if store.fingerprint(file.read()) != checksum:
                            raise store.ZybError('预留产物已被修改，不能覆盖', 'operation_pending', 409)
        def save_artifacts(current_vault, artifacts):
            current = store.read(current_vault, identity)
            current['commit']['artifacts'] = artifacts
            store.save(current_vault, identity, current)
        operation = CreationOperation(op['identity'], {'zuoyebang_render_id': identity}, op['id'], digest, validate, save_artifacts)
        images = {}
        for role in ('question', 'answer'):
            images[role] = [{'data': jobs.image(vault, identity, role)}] if payload['sections'][role]['mode'] == 'image' else []
        creation.create_question(vault, **{name: payload[name] for name in ('subject', 'category', 'difficulty', 'related_tags', 'labels', 'cause')},
                                 question_text=payload['sections']['question']['text'], answer_text=payload['sections']['answer']['text'],
                                 question_images=images['question'], answer_images=images['answer'],
                                 operation=operation, actor='zuoyebang')
        current = store.read(vault, identity)
        result = receipt(vault, current)
        result['reused'] = False
        current['commit']['result'] = result
        store.save(vault, identity, current)
        return result
