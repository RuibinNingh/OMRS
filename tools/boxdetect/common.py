"""数据构建的纯函数；不加载任何训练框架。"""
import hashlib
import json
import random
from pathlib import Path

ROLES = ('question', 'answer')


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def dhash(image):
    pixels = list(image.convert('L').resize((9, 8)).getdata())
    return sum((pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
               for y in range(8) for x in range(8))


def group_samples(samples, threshold=4):
    """传递闭包保证所有近似图与同 SHA 图不跨集，组标识与输入顺序无关。"""
    samples = sorted(samples, key=lambda s: s['id'])
    parents = list(range(len(samples)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for i, a in enumerate(samples):
        for j, b in enumerate(samples[:i]):
            if a['sha256'] == b['sha256'] or (int(a['dhash'], 16) ^ int(b['dhash'], 16)).bit_count() <= threshold:
                parents[root(i)] = root(j)
    grouped = {}
    for i, sample in enumerate(samples):
        grouped.setdefault(root(i), []).append(sample['id'])
    return sorted(grouped.values())


def split_groups(groups, seed=20260929, frozen=None, min_test=1):
    """冻结后新图绝不进测试集；与测试图近似的新图隔离，不泄漏到训练。"""
    groups = sorted([sorted(g) for g in groups])
    ids = {i for g in groups for i in g}
    if frozen is not None and not set(frozen) <= ids:
        raise ValueError('冻结测试集有图片缺失或失效，请恢复数据后重建')
    shuffled = list(groups)
    random.Random(seed).shuffle(shuffled)
    split = {'train': [], 'val': [], 'test': [], 'quarantine': []}
    if frozen is None:
        target = max(min_test, round(len(ids) * .15))
        while shuffled and len(split['test']) < target:
            split['test'].extend(shuffled.pop())
    else:
        frozen = set(frozen)
        remaining = []
        for group in shuffled:
            if frozen.intersection(group):
                split['test'].extend(i for i in group if i in frozen)
                split['quarantine'].extend(i for i in group if i not in frozen)
            else:
                remaining.append(group)
        shuffled = remaining
    target = max(1, round((len(ids) - len(split['test']) - len(split['quarantine'])) * 15 / 85))
    while shuffled and len(split['val']) < target:
        split['val'].extend(shuffled.pop())
    split['train'] = [i for group in shuffled for i in group]
    return {k: sorted(v) for k, v in split.items()}


def clip_box(box, y0, y1):
    top, bottom = max(box['y'], y0), min(box['y'] + box['h'], y1)
    height = bottom - top
    if height <= 0 or height < .03 * (y1 - y0) or height < .15 * box['h']:
        return None
    return dict(box, y=(top-y0)/(y1-y0), h=height/(y1-y0))


def yolo_line(box):
    return f"{ROLES.index(box['role'])} {box['x'] + box['w']/2:.8f} {box['y'] + box['h']/2:.8f} {box['w']:.8f} {box['h']:.8f}\n"
