"""将作业帮旋转后坐标还原到上传原图；坐标异常不丢弃可读候选。"""
import math
from .normalize import as_json


def response_data(value):
    value = as_json(value)
    for _ in range(4):
        if not isinstance(value, dict) or isinstance(value.get('answers'), dict):
            return value if isinstance(value, dict) else {}
        key = next((key for key in ('body', 'data', 'result') if key in value), None)
        if key is None:
            break
        value = as_json(value[key])
    return value if isinstance(value, dict) else {}


def location_index(value, fallback=0):
    if type(value) is int and 0 <= value < 10000:
        return value
    if isinstance(value, str) and value.isdecimal() and 0 <= int(value) < 10000:
        return int(value)
    return fallback


def regions(value, candidates, width, height):
    data = response_data(value)
    answers = data.get('answers') or {}
    locs = answers.get('locs', []) if isinstance(answers, dict) else []
    angles = answers.get('angles', []) if isinstance(answers, dict) else []
    locs = locs[:200] if isinstance(locs, list) else []
    angles = angles if isinstance(angles, list) else []
    rotation = data.get('rotateAngle', answers.get('rotateAngle', 0) if isinstance(answers, dict) else 0)
    try:
        rotation = float(rotation)
        if not math.isfinite(rotation) or rotation % 90:
            raise ValueError()
        rotation = int(rotation) % 360
    except (TypeError, ValueError, OverflowError):
        rotation = None
    indices = set(range(len(locs)))
    for candidate in candidates:
        candidate['location_index'] = location_index(candidate.get('location_index'))
        indices.add(candidate['location_index'])
    result = []
    for index in sorted(indices):
        row = {'index': index, 'candidate_indices': [i for i, c in enumerate(candidates) if c['location_index'] == index]}
        if index < len(locs) and rotation is not None:
            try:
                values = [float(n) for n in locs[index].split('@')]
                if len(values) != 8 or not all(math.isfinite(n) for n in values):
                    raise ValueError()
                working_w, working_h = (height, width) if rotation in (90, 270) else (width, height)
                points = []
                for x, y in zip(values[::2], values[1::2]):
                    if not (0 <= x <= working_w and 0 <= y <= working_h):
                        raise ValueError()
                    x, y = {0: (x, y), 90: (y, height - x), 180: (width - x, height - y), 270: (width - y, x)}[rotation]
                    points.append([round(x, 3), round(y, 3)])
                left, top = min(p[0] for p in points), min(p[1] for p in points)
                right, bottom = max(p[0] for p in points), max(p[1] for p in points)
                if right <= left or bottom <= top:
                    raise ValueError()
                row.update(polygon=points, bounds={'x': left, 'y': top, 'width': right - left, 'height': bottom - top})
            except (ValueError, TypeError, AttributeError, OverflowError):
                row.pop('polygon', None)
                row.pop('bounds', None)
            if index < len(angles):
                try:
                    angle = float(angles[index])
                    if math.isfinite(angle):
                        row['angle'] = angle % 360
                except (ValueError, TypeError, OverflowError):
                    pass  # 可选角度异常不丢弃有效的题框。
        result.append(row)
    return result, rotation


def crop_bounds(value, width, height):
    if not isinstance(value, dict) or set(value) != {'x', 'y', 'width', 'height'}:
        raise ValueError('请选择有效的题目范围')
    if any(type(value[k]) not in (int, float) or not math.isfinite(value[k]) for k in value):
        raise ValueError('题目范围必须是有限数值')
    x, y, w, h = (value[k] for k in ('x', 'y', 'width', 'height'))
    if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width + .01 or y + h > height + .01:
        raise ValueError('题目范围超出原图')
    return (math.floor(x), math.floor(y), min(width, math.ceil(x + w)), min(height, math.ceil(y + h)))
