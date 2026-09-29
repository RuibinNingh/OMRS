"""整图评估：模板只沿用训练集，预测复用 OMRS 切片与合并。"""
import argparse
import io
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image, ImageDraw
from omrs.inbox import iou, merge_strip_boxes, slice_plan
from tools.boxdetect.common import ROLES, atomic_json, sha256


# 仅保留离线历史基线；线上收件箱和草稿不再提供模板框选。
_TEMPLATE_DEFAULTS = {
    'zuoyebang': [
        {'role': 'question', 'x': 0.03, 'y_w': 0.20, 'h_w': 0.75, 'w': 0.94},
        {'role': 'answer', 'x': 0.03, 'y_w': 1.30, 'h_w': None, 'w': 0.94},
    ],
    'plain': [{'role': 'question', 'x': 0.0, 'y_w': 0.0, 'h_w': None, 'w': 1.0}],
}


def template_boxes(item, reference=None):
    """复算已完成实验的模板对照指标，不供在线框选调用。"""
    width, height = float(item['width'] or 1), float(item['height'] or 1)
    boxes = []
    if reference:
        rh = float(reference['height'] or 1)
        for region in reference['regions']:
            if region['role'] == 'ignore':
                continue
            anchored = region['y'] < 0.35
            y = min(0.95, region['y'] * rh / height) if anchored else region['y']
            h = (min(1.0 - y, region['h'] * rh / height) if anchored else
                 (1.0 - y if region['role'] == 'answer' else min(1.0 - y, region['h'])))
            boxes.append({'role': region['role'], 'card': region['card'], 'x': region['x'],
                          'y': y, 'w': region['w'], 'h': h, 'conf': 0.6})
        return [box for box in boxes if box['w'] > 0 and box['h'] > 0]
    for spec in _TEMPLATE_DEFAULTS.get(item['layout'] or '', []):
        y = min(0.95, spec['y_w'] * width / height)
        h = (1.0 - y) if spec['h_w'] is None else min(1.0 - y, spec['h_w'] * width / height)
        if h > 0:
            boxes.append({'role': spec['role'], 'card': 1, 'x': spec['x'], 'y': y,
                          'w': spec['w'], 'h': h, 'conf': 0.4})
    return boxes


def score_image(truth, predictions):
    result = {}
    for role in ROLES:
        expected = [b for b in truth if b['role'] == role]
        candidates = [b for b in predictions if b['role'] == role]
        # 一对一匹配防止一个预测框重复抵多个人工框。
        pairs = sorted([(iou(a, b), i, j) for i, a in enumerate(expected) for j, b in enumerate(candidates)], reverse=True)
        used_a, used_b, scores = set(), set(), [0.] * len(expected)
        for value, i, j in pairs:
            if i not in used_a and j not in used_b:
                used_a.add(i); used_b.add(j); scores[i] = value
        result[role] = {'ious': scores, 'iou': min(scores, default=0.),
                        'extra': max(0, len(candidates) - len(used_b))}
    result['unchanged'] = all(result[r]['iou'] >= .75 and result[r]['extra'] == 0 for r in ROLES)
    return result


def summarize(rows):
    result = {'images': len(rows), 'unchanged': sum(r['unchanged'] for r in rows)}
    result['unchanged_rate'] = result['unchanged'] / len(rows) if rows else 0
    for role in ROLES:
        scores = [v for r in rows for v in r[role]['ious']]
        result[role] = {'mean_iou': sum(scores) / len(scores) if scores else 0,
                        'passed': sum(v >= .75 for v in scores), 'total': len(scores),
                        'pass_rate': sum(v >= .75 for v in scores) / len(scores) if scores else 0,
                        'extra': sum(r[role]['extra'] for r in rows),
                        'histogram': [sum(i/10 <= v < (i+1)/10 or (i == 9 and v == 1) for v in scores) for i in range(10)]}
    return result


def template_predictions(sample, train):
    refs = [s for s in train if s['layout'] == sample['layout']]
    reference = max(refs, key=lambda s: (s['updated_at'], s['id'])) if refs else None
    if reference:
        reference = dict(reference, regions=[dict(b, card=1) for b in reference['boxes']])
    return template_boxes(sample, reference)


def model_predictions(image, detector):
    outputs = []
    for y0, y1 in slice_plan(*image.size):
        # 与 OMRS 线上一致：JPEG 85 条带，保持整图归一化映射。
        buf = io.BytesIO()
        image.crop((0, int(y0*image.height), image.width, int(y1*image.height))).convert('RGB').save(buf, 'JPEG', quality=85)
        with Image.open(io.BytesIO(buf.getvalue())) as strip:
            boxes = detector(strip)
        outputs.append({'y0': y0, 'y1': y1, 'boxes': boxes})
    return merge_strip_boxes(outputs)


def evaluate(dataset, model=None, baseline=False, split='test', out=None, conf=.25):
    dataset = Path(dataset)
    manifest = json.loads((dataset / 'manifest.json').read_text())
    train = [s for s in manifest['samples'] if s['split'] == 'train']
    samples = [s for s in manifest['samples'] if s['split'] == split]
    template_rows, rows, images = [], [], []
    detector = None
    if model:
        from tools.boxdetect.inference import Detector
        detector = Detector(model, conf=conf)
    for sample in samples:
        template_rows.append(dict(id=sample['id'], **score_image(sample['boxes'], template_predictions(sample, train))))
        if detector:
            started = time.monotonic()
            with Image.open(dataset / sample['file']) as image:
                prediction = model_predictions(image, detector)
            row = dict(id=sample['id'], elapsed_ms=round((time.monotonic()-started)*1000),
                       **score_image(sample['boxes'], prediction))
            rows.append(row); images.append((sample, prediction, row))
    result = {'dataset': manifest['version'], 'manifest_sha256': sha256(dataset / 'manifest.json'),
              'split': split, 'conf': conf, 'template': summarize(template_rows), 'template_rows': template_rows,
              'model': summarize(rows) if detector else None, 'rows': rows, 'overlays': []}
    if out:
        out = Path(out)
        if detector:
            result['model_sha256'] = sha256(model)
            (out.parent / 'overlays').mkdir(exist_ok=True, parents=True)
            for sample, prediction, row in sorted(images, key=lambda x: min(x[2][r]['iou'] for r in ROLES))[:12]:
                with Image.open(dataset / sample['file']) as original:
                    image = original.convert('RGB'); image.thumbnail((1600, 1600))
                draw = ImageDraw.Draw(image)
                for boxes, color in [(sample['boxes'], '#18a558'), (prediction, '#e23b32')]:
                    for b in boxes:
                        xy = [b['x']*image.width, b['y']*image.height, (b['x']+b['w'])*image.width, (b['y']+b['h'])*image.height]
                        draw.rectangle(xy, outline=color, width=3)
                        draw.text((xy[0]+4, xy[1]+3), b['role'], fill=color)
                name = sample['id'].replace(':', '-') + '.jpg'
                image.save(out.parent / 'overlays' / name, quality=85)
                result['overlays'].append({'name': name, 'id': sample['id']})
        atomic_json(out, result)
    return result


def select_confidence(dataset, model, out):
    """候选阈值在查看测试集模型结果前固定，只用验证集整图打分。"""
    trials = []
    for conf in (.1, .25, .4, .55):
        result = evaluate(dataset, model=model, split='val', conf=conf)
        metrics = result['model']
        score = (sum(metrics[r]['pass_rate'] for r in ROLES), metrics['unchanged_rate'],
                 -sum(metrics[r]['extra'] for r in ROLES), conf)
        trials.append({'conf': conf, 'score': score, 'model': metrics})
    best = max(trials, key=lambda t: tuple(t['score']))
    result = {'split': 'val', 'selected': best['conf'], 'trials': trials,
              'model_sha256': sha256(model)}
    atomic_json(out, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--baseline', choices=['template'])
    parser.add_argument('--model')
    parser.add_argument('--run', help='完成实验的导出、验证选阈值、测试评估（不发布）')
    parser.add_argument('--split', choices=['val', 'test'], default='test')
    parser.add_argument('--out')
    parser.add_argument('--conf', type=float, default=.25)
    parser.add_argument('--select-conf', action='store_true')
    args = parser.parse_args()
    if args.run:
        from tools.boxdetect.publish import export
        run = Path(args.run).resolve()
        model = export(run)
        selection = select_confidence(args.dataset, model, run / 'thresholds.json')
        result = evaluate(args.dataset, model=model, split='test', out=run / 'eval.json', conf=selection['selected'])
        print(json.dumps({'model': result['model'], 'template': result['template']}, ensure_ascii=False, indent=2))
        return
    if args.select_conf:
        if not args.model or args.split != 'val':
            parser.error('--select-conf 必须指定 --model 与 --split val')
        print(json.dumps(select_confidence(args.dataset, args.model, args.out or str(Path(args.model).parent / 'thresholds.json')), ensure_ascii=False, indent=2))
        return
    if not args.baseline and not args.model:
        parser.error('必须指定 --baseline template 或 --model')
    out = args.out or str((Path(args.model).parent / ('eval.json' if args.split == 'test' else 'val-eval.json')) if args.model else Path(args.dataset) / ('template-' + args.split + '.json'))
    result = evaluate(args.dataset, args.model, bool(args.baseline), args.split, out, args.conf)
    print(json.dumps({k:result[k] for k in ('dataset', 'split', 'template', 'model')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
