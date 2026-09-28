"""只读人工标注，构建按组划分、冻结测试集的条带数据集。"""
import argparse
import collections
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from omrs.inbox import slice_plan
from tools.boxdetect.common import ROLES, atomic_json, clip_box, dhash, group_samples, sha256, split_groups, yolo_line

EXT = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif'}


def source_rows(vault):
    vault = Path(vault).resolve()
    data = vault / '.omrs' if vault.name == '错题' else vault / '错题' / '.omrs'
    for source, table, folder in [('annotate', 'images', 'images'), ('inbox', 'items', 'raw')]:
        path = data / source / (source + '.db')
        if not path.exists():
            continue
        db = sqlite3.connect(path.as_uri() + '?mode=ro')
        db.row_factory = sqlite3.Row
        try:
            for row in db.execute(f"SELECT * FROM {table} WHERE status='done' ORDER BY id"):
                row = dict(row)
                boxes = json.loads(row['boxes']) if source == 'annotate' else [dict(b) for b in db.execute(
                    'SELECT * FROM regions WHERE item_id=? ORDER BY ord', (row['id'],))]
                yield dict(id=source + ':' + row['id'], source=source, sha256=row['sha256'],
                           path=data / source / folder / (row['sha256'] + '.' + EXT.get(row['mime'], 'png')),
                           width=row['width'], height=row['height'], boxes=boxes,
                           layout=row.get('layout', 'zuoyebang'), updated_at=row['updated_at'])
        finally:
            db.close()


def inspect_sources(vault):
    samples, excluded = [], []
    for sample in source_rows(vault):
        reason = None
        boxes = sample['boxes']
        if not set(ROLES) <= {b['role'] for b in boxes}:
            reason = '缺少题目或答案框'
        elif any(b.get('origin') == 'ai' for b in boxes):
            reason = '含未编辑 AI 框'
        else:
            try:
                if sha256(sample['path']) != sample['sha256']:
                    raise ValueError('原图 SHA-256 与库记录不符')
                with Image.open(sample['path']) as image:
                    image.load()
                    if image.size != (sample['width'], sample['height']):
                        raise ValueError('尺寸与库记录不符')
                    sample['dhash'] = f'{dhash(image):016x}'
                for box in boxes:
                    if box['role'] not in ROLES:
                        continue
                    if not all(math.isfinite(float(box[k])) for k in ('x', 'y', 'w', 'h')) or not (
                        0 <= box['x'] < 1 and 0 <= box['y'] < 1 and box['w'] > 0 and box['h'] > 0
                        and box['x'] + box['w'] <= 1.000001 and box['y'] + box['h'] <= 1.000001):
                        raise ValueError('框坐标越界或非法')
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                reason = '原图或标注无效：' + str(exc)
        if reason:
            excluded.append({'id': sample['id'], 'reason': reason})
        else:
            sample['boxes'] = [{k: b[k] for k in ('role', 'x', 'y', 'w', 'h')} for b in boxes if b['role'] in ROLES]
            samples.append(sample)
    return samples, excluded


def build(vault, out, frozen_manifest=None, threshold=4, seed=20260929):
    out = Path(out).resolve()
    source = Path(vault).resolve()
    data = source if source.name == '错题' else source / '错题'
    if out.is_relative_to(data):
        raise ValueError('产物目录不得位于真实数据内')
    if out.exists():
        raise ValueError('输出目录已存在，请使用新数据版本')
    # 同一训练根目录默认沿用最早版本，防止无意重新抽测试集。
    if frozen_manifest is None:
        previous = sorted(out.parent.glob('*/manifest.json'))
        frozen_manifest = previous[0] if previous else None
    frozen = None
    old = None
    if frozen_manifest:
        old = json.loads(Path(frozen_manifest).read_text())
        frozen = old['splits']['test']
    samples, excluded = inspect_sources(vault)
    if old:
        current = {s['id']: s for s in samples}
        for s in old['samples']:
            if s['id'] in frozen and (s['id'] not in current or any(
                    current[s['id']][k] != s[k] for k in ('sha256', 'boxes'))):
                raise ValueError('冻结测试图或标签发生变化，禁止静默替换')
    groups = group_samples(samples, threshold)
    splits = split_groups(groups, seed, frozen, min_test=15)
    if not splits['train'] or not splits['val'] or len(splits['test']) < 15:
        raise ValueError('分组后必须有训练／验证数据以及至少 15 张测试图')
    out.mkdir(parents=True)
    counts = collections.Counter()
    for split in ('train', 'val', 'test'):
        (out / 'images' / split).mkdir(parents=True)
        (out / 'labels' / split).mkdir(parents=True)
    (out / 'originals').mkdir()
    for sample in samples:
        source_path = sample.pop('path')
        key = sample['id'].replace(':', '-')
        original = Path('originals') / (key + source_path.suffix)
        shutil.copyfile(source_path, out / original)
        sample['file'] = original.as_posix()
        sample['split'] = next(k for k, ids in splits.items() if sample['id'] in ids)
        sample['group'] = next(i for i, group in enumerate(groups) if sample['id'] in group)
        sample['strips'] = []
        if sample['split'] == 'quarantine':
            continue
        with Image.open(out / original) as image:
            for index, (y0, y1) in enumerate(slice_plan(*image.size)):
                name = key + f'-{index:02}'
                image.crop((0, int(y0*image.height), image.width, int(y1*image.height))).convert('RGB').save(
                    out / 'images' / sample['split'] / (name + '.jpg'), quality=85)
                boxes = [c for b in sample['boxes'] if (c := clip_box(b, y0, y1))]
                (out / 'labels' / sample['split'] / (name + '.txt')).write_text(''.join(map(yolo_line, boxes)))
                sample['strips'].append({'name': name, 'y0': y0, 'y1': y1})
                counts[sample['split']] += 1
    manifest = {'version': out.name, 'seed': seed, 'dhash_threshold': threshold, 'classes': list(ROLES),
                'frozen_from': old['version'] if old else None, 'groups': groups, 'splits': splits,
                'counts': {k: len(v) for k, v in splits.items()}, 'strip_counts': dict(counts),
                'excluded': excluded, 'samples': samples}
    atomic_json(out / 'manifest.json', manifest)
    (out / 'manifest.sha256').write_text(sha256(out / 'manifest.json') + '\n')
    (out / 'test_ids.txt').write_text('\n'.join(splits['test']) + '\n')
    (out / 'data.yaml').write_text('path: ' + json.dumps(str(out)) + '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: question\n  1: answer\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', default='错题')
    parser.add_argument('--out', required=True)
    parser.add_argument('--frozen-manifest')
    parser.add_argument('--threshold', type=int, default=4)
    parser.add_argument('--seed', type=int, default=20260929)
    args = parser.parse_args()
    result = build(args.vault, args.out, args.frozen_manifest, args.threshold, args.seed)
    print(json.dumps({k: result[k] for k in ('version', 'counts', 'strip_counts', 'excluded')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
