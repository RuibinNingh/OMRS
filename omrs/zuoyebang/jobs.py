"""可轮询的搜题、渲染与保真提取作业；网络和浏览器期间不持业务写锁或磁盘租约。"""
import base64
import html as html_lib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from .. import uploads, vault_lifecycle as lifecycle
from ..locking import write_lock
from . import store, session
from .direct import DirectClient, UpstreamError
from .normalize import normalize_questions
from .html import candidate_html
from .render import render_documents
from .validation import validate_image, MAX_BYTES

INSTANCE = uuid.uuid4().hex
_LOCK = threading.Lock()
_ACTIVE = {}


def summary(candidate, index):
    text = html_lib.unescape(re.sub(r'<[^>]*>', '', str(candidate['question'].get('content') or ''))).strip()
    return {'index': index, 'location': candidate.get('location_index'), 'result_index': candidate.get('result_index'),
            'match_type': candidate.get('match_type'), 'title': text[:160] or '图文题目'}


def public_record(record):
    if record['kind'] == 'search':
        return {key: record[key] for key in ('id', 'kind', 'created_at', 'candidates')}
    return {key: value for key, value in record.items() if key not in ('source',)}


def get_record(vault, identity):
    return public_record(store.read(vault, identity))


def get_job(vault, identity):
    row = store.read(vault, identity)
    if row['kind'] != 'job':
        raise store.ZybError('记录不是后台任务')
    if row['status'] == 'running' and (row['instance'] != INSTANCE or row.get('generation') != lifecycle.generation(vault)):
        row.update(status='failed', error='服务已重启或题库已恢复，原内容已保留，请重新提交任务', code='job_interrupted')
    return {key: value for key, value in row.items() if key not in ('instance', 'generation')}


def history(vault):
    with lifecycle.lease(vault):
        rows = []
        for path in store.root(vault).glob('render-*/record.json'):
            if path.parent.is_symlink():
                continue
            row = store.read_json(path)
            rows.append({key: row.get(key) for key in ('id', 'status', 'created_at', 'candidate', 'images', 'error')})
        return sorted(rows, key=lambda row: row['created_at'], reverse=True)[:30]


def image(vault, identity, role):
    if role not in ('question', 'answer'):
        raise store.ZybError('图片角色不合法')
    with lifecycle.lease(vault):
        record = store.read(vault, identity)
        if record.get('status') != 'ready' or record.get('images', {}).get(role, {}).get('empty'):
            raise store.ZybError('完整渲染图片尚未就绪', status=404)
        path = store.location(vault, identity) / (role + '.png')
        if path.is_symlink():
            raise store.ZybError('渲染图片不允许符号链接')
        raw = path.read_bytes()
        if store.fingerprint(raw) != record['images'][role]['sha256']:
            raise store.ZybError('渲染图片已变化，请重新渲染', 'render_changed', 409)
        return raw


def search(vault, payload):
    with lifecycle.lease(vault):
        profile = store.profile_bytes(vault)
    with tempfile.TemporaryDirectory(prefix='omrs-zyb-search-') as temp:
        path = Path(temp) / 'session.json'
        path.write_bytes(profile)
        os.chmod(path, 0o600)
        try:
            candidates = normalize_questions(DirectClient(path).search(payload['image'], payload['grade']))
        except UpstreamError as exc:
            with lifecycle.lease(vault), write_lock():
                if store.fingerprint(store.profile_bytes(vault)) == store.fingerprint(profile):
                    store.observe(vault, 'search', exc.kind, exc.code)
            raise store.ZybError(str(exc), exc.kind, 502) from exc
    record = {'id': 'search-' + uuid.uuid4().hex, 'kind': 'search', 'created_at': time.time(),
              'source': candidates, 'candidates': [summary(candidate, i) for i, candidate in enumerate(candidates)]}
    with lifecycle.lease(vault), write_lock():
        if store.fingerprint(store.profile_bytes(vault)) != store.fingerprint(profile):
            raise store.ZybError('设备会话已更新，请重新搜题', 'session_changed', 409)
        store.observe(vault, 'search')
        store.save(vault, record['id'], record)
    return public_record(record)


def render(vault, payload):
    record = {'id': 'render-' + uuid.uuid4().hex, 'kind': 'render', 'status': 'rendering',
              'created_at': time.time(), 'search_id': payload['search_id'], 'candidate': payload['candidate'],
              'source': payload['source'], 'extraction': {}, 'images': {}}
    store.save(vault, record['id'], record)
    try:
        bodies, count = candidate_html(payload['source'])
        with tempfile.TemporaryDirectory(prefix='omrs-zyb-render-') as temp:
            output = render_documents(bodies, temp)
            with lifecycle.lease(vault), write_lock():
                directory = store.location(vault, record['id'])
                for role in ('question', 'answer'):
                    if not output[role].get('empty'):
                        source = Path(temp) / (role + '.png')
                        target = directory / source.name
                        # 先完整写临时文件并同步，再发布；不跨文件系统 rename。
                        staging = directory / (source.name + '.tmp')
                        with open(staging, 'xb') as file:
                            file.write(source.read_bytes())
                            file.flush()
                            os.fsync(file.fileno())
                        os.chmod(staging, 0o600)
                        os.replace(staging, target)
                    metadata = output[role]
                    if not metadata.get('empty'):
                        metadata['url'] = f'/api/zuoyebang/image?id={record["id"]}&role={role}'
                record.update(status='ready', images={role: output[role] for role in ('question', 'answer')},
                              browser=output['browser'], source_images=count, completed_at=time.time())
                store.save(vault, record['id'], record)
    except Exception as exc:
        record.update(status='failed', error=str(exc) if isinstance(exc, store.ZybError) else '渲染失败，原内容已保留')
        store.save(vault, record['id'], record)
        raise
    return public_record(record)


def extract(vault, payload):
    from ..ai_assist import extract_region, recognize_question
    record = store.read(vault, payload['render_id'])
    if record.get('status') != 'ready':
        raise store.ZybError('请先完成后端渲染')
    for role in ('question', 'answer'):
        if record['images'][role].get('empty'):
            record['extraction'][role] = {'status': 'empty', 'mode': 'none', 'text': '', 'reason': '上游未返回答案'}
            continue
        if record['extraction'].get(role, {}).get('status') == 'done' and not payload.get('force'):
            continue
        try:
            encoded = 'data:image/png;base64,' + base64.b64encode(image(vault, record['id'], role)).decode('ascii')
            result = extract_region(vault, encoded, role=role, judge=True)
            record['extraction'][role] = {'status': 'done', 'mode': 'text' if result['convertible'] else 'image',
                                          'text': result['text'] if result['convertible'] else '', 'reason': result['reason']}
        except Exception as exc:
            record['extraction'][role] = {'status': 'failed', 'mode': 'image', 'text': '',
                                          'reason': str(exc), 'error': '提取失败，完整图片已保留，可重试'}
        store.save(vault, record['id'], record)
    if not record.get('classification'):
        try:
            encoded = 'data:image/png;base64,' + base64.b64encode(image(vault, record['id'], 'question')).decode('ascii')
            record['classification'] = recognize_question(vault, encoded, mode='classify', allow_labels=False)
        except Exception:
            record['classification_error'] = '分类识别失败，请手动填写科目和分类'
        store.save(vault, record['id'], record)
    return public_record(record)


def start_job(vault, kind, data):
    with lifecycle.lease(vault) as generation:
        if kind == 'search':
            session.status(vault)
            store.profile_bytes(vault)
            reference = data.get('image')
            if isinstance(reference, dict):
                uploaded = uploads.resolve(vault, reference, purpose='zuoyebang')
                if uploaded['bytes'] > MAX_BYTES:
                    raise store.ZybError('搜题图片不能超过8MB')
                raw = uploads.read(vault, reference)
            else:
                raw = None
            if raw is None:
                raise store.ZybError('请选择不超过8MB的 JPG、PNG 或 WebP 图片')
            validate_image(raw)
            grade = data.get('grade', 0)
            if type(grade) is not int or not 0 <= grade <= 12:
                raise store.ZybError('年级参数不合法')
            payload = {'image': raw, 'grade': grade}
            key = ('search',)
        elif kind == 'render':
            source = store.read(vault, data.get('search_id'))
            index = data.get('candidate_index')
            if source['kind'] != 'search' or type(index) is not int or not 0 <= index < len(source['source']):
                raise store.ZybError('请选择有效的搜题候选')
            payload = {'search_id': source['id'], 'source': source['source'][index], 'candidate': source['candidates'][index]}
            key = ('render', source['id'], index)
        elif kind == 'extract':
            record = store.read(vault, data.get('render_id'))
            if record.get('status') != 'ready':
                raise store.ZybError('请先完成后端渲染')
            payload = {'render_id': record['id'], 'force': data.get('force') is True}
            key = ('extract', record['id'])
        else:
            raise store.ZybError('后台任务类型不合法')
    vault_key = os.path.realpath(vault)
    with _LOCK:
        active = _ACTIVE.setdefault(vault_key, {})
        if key in active:
            return get_job(vault, active[key])
        if len(active) >= 2:
            raise store.ZybError('已有两个作业帮任务运行，请稍后重试', 'job_busy', 429)
        identity = 'job-' + uuid.uuid4().hex
        active[key] = identity
    job = {'id': identity, 'kind': 'job', 'type': kind, 'status': 'running', 'created_at': time.time(), 'instance': INSTANCE,
           'generation': generation}
    try:
        with lifecycle.lease(vault, generation):
            store.save(vault, identity, job)
    except BaseException:
        with _LOCK:
            active.pop(key, None)
        raise
    def worker():
        try:
            with lifecycle.task(vault, generation):
                result = {'search': search, 'render': render, 'extract': extract}[kind](vault, payload)
                job.update(status='done', result=result, completed_at=time.time())
                store.save(vault, identity, job)
        except Exception as exc:
            job.update(status='failed', error=str(exc) if isinstance(exc, (ValueError, lifecycle.VaultBusy, lifecycle.VaultChanged)) else '作业帮任务失败，请重试',
                       code=getattr(exc, 'code', 'zuoyebang'), completed_at=time.time())
            try:
                with lifecycle.lease(vault, generation):
                    store.save(vault, identity, job)
            except (lifecycle.VaultChanged, lifecycle.VaultBusy):
                pass
        finally:
            with _LOCK:
                active.pop(key, None)
    threading.Thread(target=worker, daemon=True, name='omrs-zuoyebang').start()
    return {key: value for key, value in job.items() if key not in ('instance', 'generation')}
