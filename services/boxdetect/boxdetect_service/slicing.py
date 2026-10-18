"""整图条带与合并，保持 OMRS 既有几何契约。"""
from .geometry import iou

def _clamp01(value):
    return max(0.0, min(1.0, float(value)))

def slice_plan(width, height, max_ratio=3.0, strip_ratio=2.0, overlap=0.08):
    """返回 [(y0, y1)] 归一化条带。高宽比不超过 max_ratio 时返回整图 [(0,1)]。"""
    if not width or not height or height / width <= max_ratio:
        return [(0.0, 1.0)]
    strip = (width * strip_ratio) / height  # 每条带占整图高度的比例
    step = strip * (1.0 - overlap)
    plan, y = [], 0.0
    while True:
        y1 = min(1.0, y + strip)
        plan.append((round(y, 4), round(y1, 4)))
        if y1 >= 1.0:
            break
        y += step
    # 末尾只剩一小条时并入上一条，避免送一个几乎没内容的碎片
    if len(plan) > 1 and (plan[-1][1] - plan[-1][0]) < 0.5 * strip:
        plan[-2] = (plan[-2][0], 1.0)
        plan.pop()
    return plan


def merge_strip_boxes(strips, min_iou=0.4):
    """strips: [{"y0","y1","boxes":[{role,card,x,y,w,h,conf}]}]，boxes 坐标相对条带。
    映射回整图后，把**不同条带**里同角色、上下相接/重叠且水平重叠的框合并为并集
    （同一条带内的两个框永远不合并，保证一张拍照里的两道题不会被粘成一道）。"""
    mapped = []
    for index, strip in enumerate(strips):
        y0, y1 = float(strip["y0"]), float(strip["y1"])
        span = max(1e-6, y1 - y0)
        for box in strip.get("boxes") or []:
            mapped.append({
                "role": box.get("role", "question"), "card": int(box.get("card", 1) or 1),
                "x": _clamp01(box["x"]), "y": _clamp01(y0 + _clamp01(box["y"]) * span),
                "w": _clamp01(box["w"]), "h": _clamp01(_clamp01(box["h"]) * span),
                "conf": float(box.get("conf", 0.5) or 0.5), "_strips": {index},
            })
    merged = []
    for box in sorted(mapped, key=lambda b: b["y"]):
        target = None
        for cand in merged:
            if cand["role"] != box["role"] or box["_strips"] & cand["_strips"]:
                continue
            h_overlap = min(cand["x"] + cand["w"], box["x"] + box["w"]) - max(cand["x"], box["x"])
            v_gap = box["y"] - (cand["y"] + cand["h"])
            if iou(cand, box) >= min_iou or (h_overlap > 0.5 * min(cand["w"], box["w"]) and v_gap < 0.02):
                target = cand
                break
        if target is None:
            merged.append(dict(box))
            continue
        x1, y1 = min(target["x"], box["x"]), min(target["y"], box["y"])
        x2 = max(target["x"] + target["w"], box["x"] + box["w"])
        y2 = max(target["y"] + target["h"], box["y"] + box["h"])
        target.update({"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "conf": min(target["conf"], box["conf"]),
                       "_strips": target["_strips"] | box["_strips"]})
    for box in merged:
        box.pop("_strips", None)
        box["card"] = box.get("card") or 1
    return merged
