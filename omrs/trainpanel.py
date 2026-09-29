"""训练面板：只读外部实验文件，主程序不加载训练／推理框架。"""
import datetime
import json
import math
import os
from pathlib import Path
import re
import shlex
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request

from .common import CONFIG_DEFAULTS, QUESTIONS_DIR, OMRS_DIR

MAX_JSON_BYTES = 16 * 1024 * 1024


def config(vault):
    """只读配置，空 Vault 也不因查询而创建目录。"""
    path = Path(vault) / QUESTIONS_DIR / OMRS_DIR / 'config.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return {**CONFIG_DEFAULTS, **value} if isinstance(value, dict) else dict(CONFIG_DEFAULTS)
    except (OSError, ValueError):
        return dict(CONFIG_DEFAULTS)


def train_dir(vault):
    value = config(vault).get('train_dir') or '~/omrs-train'
    if not isinstance(value, str):
        raise ValueError('训练目录配置必须是字符串')
    return Path(value).expanduser().resolve()


def safe_path(root, *names):
    root = Path(root).resolve()
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or name in ('.', '..'):
            raise ValueError('路径参数不合法')
    path = root.joinpath(*names).resolve()
    if not path.is_relative_to(root):
        raise ValueError('路径越界')
    return path


def read_json(path):
    if not path.exists():
        return None, None
    try:
        with path.open('rb') as stream:
            data = stream.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise ValueError('文件过大')
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError('必须为 JSON 对象')
        shapes = {
            'manifest.json': {'samples': list, 'excluded': list, 'counts': dict, 'strip_counts': dict},
            'eval.json': {'model': dict, 'template': dict, 'rows': list, 'overlays': list},
        }.get(path.name, {})
        for key, kind in shapes.items():
            if key in value and value[key] is not None and not isinstance(value[key], kind):
                raise ValueError(key + ' 字段类型不合法')
            if value.get(key) is None and key in value and key not in ('model', 'template'):
                raise ValueError(key + ' 字段不能为空')
        if path.name == 'status.json':
            if value.get('state') not in ('running', 'done', 'failed'):
                raise ValueError('训练状态不合法')
            for key in ('epoch', 'epochs', 'pid', 'epoch_seconds'):
                if key in value and (not isinstance(value[key], (int, float)) or not math.isfinite(value[key]) or value[key] < 0):
                    raise ValueError(key + ' 必须是非负有限数值')
        return value, None
    except (OSError, ValueError) as exc:
        return None, '读取失败：' + str(exc)


def timestamp(value):
    try:
        return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0


def status_view(value, current_time=None):
    result = dict(value)
    if result.get('state') == 'running':
        try:
            pid = int(result.get('pid', 0))
            if pid <= 0:
                raise ProcessLookupError()
            os.kill(pid, 0)
            alive = True
        except PermissionError:
            alive = True
        except (OSError, ValueError, TypeError):
            alive = False
        try:
            limit = max(600, 3 * float(result.get('epoch_seconds') or 0))
        except (TypeError, ValueError):
            limit = 600
        now = current_time if current_time is not None else datetime.datetime.now().timestamp()
        if not alive or now - timestamp(result.get('updated_at')) > limit:
            result['state'] = 'interrupted'
    return result


def commands(root, latest=None, dataset=None, vault=None):
    def unused(folder):
        stem = datetime.datetime.now().strftime('%Y%m%d')
        index = 1
        while (root / folder / f'{stem}-{index}').exists():
            index += 1
        return str(root / folder / f'{stem}-{index}')
    py = shlex.quote(str(root / '.venv/bin/python'))
    dataset_path = shlex.quote(str(root / 'datasets' / dataset) if dataset else unused('datasets'))
    next_dataset = shlex.quote(unused('datasets'))
    new_run = shlex.quote(unused('runs'))
    run_path = shlex.quote(str(root / 'runs' / latest)) if latest else new_run
    vault_path = shlex.quote(str(vault or '<Vault目录>'))
    train = f'nice -n 19 {py} tools/boxdetect/train.py --dataset {dataset_path}'
    return {'build': f'{py} tools/boxdetect/build_dataset.py --vault {vault_path} --out {next_dataset}',
            'train': train + ' --run ' + new_run,
            'resume': train + ' --run ' + run_path + ' --resume',
            'evaluate': f'{py} tools/boxdetect/evaluate.py --dataset {dataset_path} --run {run_path}',
            'serve': f'{py} tools/boxdetect/serve.py --model-dir {shlex.quote(str(root / "models/current"))} --port 18765'}


def done_counts(vault, known_ids):
    counts, additional, errors = {}, 0, {}
    data = Path(vault) / QUESTIONS_DIR / OMRS_DIR
    for source, table in [('annotate', 'images'), ('inbox', 'items')]:
        path = data / source / (source + '.db')
        counts[source] = 0
        if not path.exists():
            continue
        try:
            db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', timeout=2)
            try:
                ids = {source + ':' + str(r[0]) for r in db.execute(f"SELECT id FROM {table} WHERE status='done'")}
                counts[source] = len(ids)
                additional += len(ids - known_ids)
            finally:
                db.close()
        except sqlite3.Error as exc:
            errors[source] = '读取失败：' + str(exc)
    return {'done': counts, 'additional': additional, 'errors': errors}


def overview(vault):
    root = train_dir(vault)
    result = {'model': None, 'dataset': None, 'latest': None, 'runs': [], 'errors': {},
              'collect': config(vault).get('train_try_collect') is True}
    result['model'], error = read_json(safe_path(root, 'models', 'current', 'model.json'))
    if error:
        result['errors']['model'] = error
    datasets = safe_path(root, 'datasets')
    manifests = sorted(datasets.glob('*/manifest.json'), reverse=True) if datasets.exists() else []
    known = set()
    if manifests:
        manifest_path = safe_path(root, 'datasets', manifests[0].parent.name, 'manifest.json')
        manifest, error = read_json(manifest_path)
        if error:
            result['errors']['dataset'] = error
        if manifest:
            result['dataset'] = {k: manifest.get(k) for k in ('version', 'counts', 'strip_counts', 'excluded')}
            known = {s['id'] for s in manifest.get('samples', []) if isinstance(s, dict) and 'id' in s}
            known.update(s['id'] for s in manifest.get('excluded', []) if isinstance(s, dict) and 'id' in s)
    result['live'] = done_counts(vault, known)
    runs = safe_path(root, 'runs')
    for folder in sorted(runs.iterdir(), reverse=True) if runs.exists() else []:
        if not folder.is_dir():
            continue
        try:
            folder = safe_path(root, 'runs', folder.name)
            value, error = read_json(safe_path(folder, 'status.json'))
            evaluation, eval_error = read_json(safe_path(folder, 'eval.json'))
        except ValueError:
            continue
        run = {'name': folder.name, 'status': status_view(value) if value else None,
               'evaluation': {k: evaluation.get(k) for k in ('model', 'template')} if evaluation else None,
               'error': error, 'eval_error': eval_error,
               'current': bool(result['model'] and result['model'].get('run') == folder.name)}
        result['runs'].append(run)
    result['runs'].sort(key=lambda r: (timestamp((r['status'] or {}).get('started_at')), r['name']), reverse=True)
    result['latest'] = result['runs'][0] if result['runs'] else None
    latest = result['latest']
    result['commands'] = commands(root, latest['name'] if latest else None,
                                  (latest['status'] or {}).get('dataset') if latest else (result['dataset'] or {}).get('version'), vault=vault)
    if latest:
        identity, _ = read_json(safe_path(root, 'runs', latest['name'], 'identity.json'))
        if identity:
            suffix = ' '.join('--' + key + ' ' + shlex.quote(str(identity[key]))
                              for key in ('epochs', 'imgsz', 'batch', 'threads', 'weights') if key in identity)
            result['commands']['resume'] += ' ' + suffix
    return result


def run_detail(vault, run):
    root = safe_path(train_dir(vault), 'runs', run)
    if not root.is_dir():
        raise ValueError('实验不存在')
    result = {'name': run, 'metrics': [], 'evaluation': None, 'errors': {}}
    value, error = read_json(safe_path(root, 'status.json'))
    result['status'] = status_view(value) if value else None
    if error:
        result['errors']['status'] = error
    result['evaluation'], error = read_json(safe_path(root, 'eval.json'))
    if error:
        result['errors']['evaluation'] = error
    path = safe_path(root, 'metrics.jsonl')
    if path.exists():
        try:
            with path.open('rb') as stream:
                data = stream.read(MAX_JSON_BYTES + 1)
            if len(data) > MAX_JSON_BYTES:
                raise ValueError('指标文件过大')
            lines = data.splitlines(keepends=True)
            metrics = {}
            for index, line in enumerate(lines):
                # 正在追加的最后半行下次轮询再读。
                if index == len(lines)-1 and not line.endswith(b'\n'):
                    continue
                value = json.loads(line)
                if not isinstance(value, dict) or not isinstance(value.get('epoch'), int):
                    raise ValueError('指标行缺少轮次')
                metrics[value['epoch']] = value
            result['metrics'] = [metrics[k] for k in sorted(metrics)]
        except (OSError, ValueError) as exc:
            result['errors']['metrics'] = '读取失败：' + str(exc)
    return result


def overlay_path(vault, run, name):
    folder = safe_path(train_dir(vault), 'runs', run)
    path = safe_path(folder, 'overlays', name)
    evaluation, error = read_json(safe_path(folder, 'eval.json'))
    registered = (evaluation or {}).get('overlays', [])
    if error or not any(isinstance(x, dict) and x.get('name') == name for x in registered):
        raise ValueError('叠加图未登记')
    if path.suffix.lower() not in ('.jpg', '.jpeg', '.png') or not path.is_file():
        raise ValueError('叠加图不存在或类型不符')
    return path


def service(vault):
    url = config(vault).get('inbox_local_detect_url', '')
    if not url:
        return {'state': 'unconfigured', 'message': '尚未配置本地检测服务地址'}
    try:
        if not isinstance(url, str):
            raise ValueError('检测服务地址必须是字符串')
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise ValueError('地址不合法')
        health = urllib.parse.urlunsplit((parts.scheme, parts.netloc, '/health', '', ''))
        with urllib.request.urlopen(health, timeout=2) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError('健康检查响应过大')
        model = json.loads(payload)
        if not isinstance(model, dict):
            raise ValueError('健康检查格式不合法')
        return {'state': 'online', 'model': model}
    except (OSError, ValueError):
        return {'state': 'offline', 'message': '检测服务未启动', 'command': commands(train_dir(vault))['serve']}


# 同时只解码一张测试原图，避免多个标签页叠加长图内存。
_TRY_SLOT = threading.BoundedSemaphore(1)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


def try_image(vault, files):
    """实时测试只在内存中切片；积累成功后仍是 todo，不直接成为训练标签。"""
    import base64
    import io
    import time
    from PIL import Image
    from . import ai_assist, annotate, inbox, locking

    if len(files) != 1:
        raise ValueError('每次请选择一张 PNG、JPEG 或 GIF')
    name, data = files[0]
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('图片不能为空且不能超过 15 MB')
    url = config(vault).get('inbox_local_detect_url', '')
    if not isinstance(url, str):
        raise ValueError('检测服务地址必须是字符串')
    if not url:
        raise ValueError('尚未配置本地检测服务地址，请到录入题目 → AI 训练填写')
    if not _TRY_SLOT.acquire(blocking=False):
        raise ValueError('已有图片正在测试，请稍后重试')
    started = time.monotonic()
    try:
        outputs = []
        try:
            image = Image.open(io.BytesIO(data))
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError('图片无法解码') from exc
        with image:
            if image.format not in ('PNG', 'JPEG', 'GIF'):
                raise ValueError('只支持 PNG、JPEG 或 GIF')
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError('图片像素超过 4000 万，请拆分后测试')
            try:
                image.load()
            except OSError as exc:
                raise ValueError('图片损坏或截断') from exc
            for y0, y1 in inbox.slice_plan(width, height):
                buf = io.BytesIO()
                strip = image.crop((0, int(y0*height), width, int(y1*height))).convert('RGB')
                strip.save(buf, 'JPEG', quality=85)
                encoded = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
                try:
                    boxes = ai_assist.detect_regions_local(url, encoded, 'zuoyebang', width, strip.height)
                except (OSError, ValueError) as exc:
                    if '连不上' in str(exc) or isinstance(exc, OSError):
                        raise ValueError('检测服务未启动；' + commands(train_dir(vault))['serve']) from exc
                    raise
                finally:
                    strip.close()
                outputs.append({'y0': y0, 'y1': y1, 'boxes': boxes})
        result = {'boxes': inbox.merge_strip_boxes(outputs), 'width': width, 'height': height,
                  'strips': len(outputs), 'elapsed_ms': round((time.monotonic()-started)*1000)}
        if config(vault).get('train_try_collect') is True:
            try:
                with locking.write_lock():
                    # 等待写锁期间用户可能已关闭积累，再确认一次服务端开关。
                    if config(vault).get('train_try_collect') is True:
                        uploaded = annotate.upload(vault, [(name, data)])
                        if uploaded['duplicates']:
                            result['collected'] = {'id': uploaded['duplicates'][0]['id'], 'duplicate': True}
                        else:
                            image_id = uploaded['images'][0]['id']
                            annotate.save(vault, image_id, result['boxes'], status=None)
                            result['collected'] = {'id': image_id, 'duplicate': False, 'status': 'todo'}
            except Exception as exc:
                result['collect_error'] = '积累失败：' + str(exc)
        return result
    finally:
        _TRY_SLOT.release()
