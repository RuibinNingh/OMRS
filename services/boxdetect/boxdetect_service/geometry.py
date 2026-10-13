"""检测框的纯几何计算，不引用题库业务模块。"""


def iou(a, b):
    if not a or not b:
        return 0.0
    x1, y1 = max(a['x'], b['x']), max(a['y'], b['y'])
    x2 = min(a['x'] + a['w'], b['x'] + b['w'])
    y2 = min(a['y'] + a['h'], b['y'] + b['h'])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a['w'] * a['h'] + b['w'] * b['h'] - inter
    return inter / union if union > 0 else 0.0
