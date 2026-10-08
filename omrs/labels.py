"""用户标记定义、题目 YAML 标记级联和查询。

标记定义存于 ``错题/.omrs/labels.json``；题目 Markdown 只保存标记名称，
因此 Obsidian 中仍然可以直接查看和编辑。人工级联与 AI 整理共用可靠批次，
定义与题目文件整体替换，逐题 Ledger 事实保持可重建投影。
"""

from __future__ import annotations
from .vault_lifecycle import storage, open_sqlite
from .data_repository import mastery_rows, storage_read

import datetime
import json
import os
import re
import uuid

from .common import extract_labels, omrs_data_dir, parse_yaml_frontmatter
from .question_ops import set_question_labels
from .workspace_sync import scan_workspace


LABELS_FILENAME = "labels.json"
LABELS_VERSION = 1
DEFAULT_COLOR = "#64748b"
COLORS = {
    "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink",
}


@storage
def labels_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), LABELS_FILENAME)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _clean_name(value) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("标记名称不能为空")
    if len(name) > 80:
        raise ValueError("标记名称不能超过 80 个字符")
    if "\n" in name or "|" in name:
        raise ValueError("标记名称不能包含换行或竖线")
    return name


def _clean_color(value) -> str:
    color = str(value or DEFAULT_COLOR).strip()
    if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", color):
        return DEFAULT_COLOR
    if len(color) == 4:
        color = "#" + "".join(ch * 2 for ch in color[1:])
    return color.lower()


def _clean_bonus(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize_label(raw, index=0) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    name = str(raw.get("name") or "").strip()
    return {
        "id": str(raw.get("id") or f"LB-{uuid.uuid4().hex[:8].upper()}"),
        "name": name[:80],
        "color": _clean_color(raw.get("color")),
        "order": int(raw.get("order", index + 1) or index + 1),
        "priority_bonus": _clean_bonus(raw.get("priority_bonus", 0)),
        "archived": bool(raw.get("archived", False)),
        "created_at": str(raw.get("created_at") or _now()),
    }


@storage_read
def load_labels(vault: str) -> dict:
    path = labels_path(vault)
    if not os.path.isfile(path):
        return {"version": LABELS_VERSION, "labels": []}
    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return {"version": LABELS_VERSION, "labels": []}
    labels = []
    seen_ids, seen_names = set(), set()
    for index, item in enumerate(raw.get("labels") or []):
        label = _normalize_label(item, index)
        if not label["name"] or label["id"] in seen_ids or label["name"] in seen_names:
            continue
        seen_ids.add(label["id"])
        seen_names.add(label["name"])
        labels.append(label)
    labels.sort(key=lambda item: (item["order"], item["created_at"], item["name"]))
    return {"version": LABELS_VERSION, "labels": labels}


@storage
def save_labels(vault: str, data: dict) -> dict:
    path = labels_path(vault)
    labels = []
    seen_names = set()
    for index, item in enumerate(data.get("labels") or []):
        normalized = _normalize_label(item, index)
        if not normalized["name"] or normalized["name"] in seen_names:
            continue
        normalized["order"] = index + 1 if not item.get("order") else normalized["order"]
        seen_names.add(normalized["name"])
        labels.append(normalized)
    payload = {"version": LABELS_VERSION, "labels": labels}
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
    return payload


def _resolve(label_defs, value) -> dict | None:
    needle = str(value or "").strip()
    if not needle:
        return None
    return next((item for item in label_defs
                 if item["id"] == needle or item["name"] == needle), None)


@storage
def _label_counts(vault: str) -> dict:
    counts = {}
    for row in mastery_rows(vault):
        for name in str(row.get("Labels", "") or "").split("|"):
            name = name.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


@storage_read
def list_label_defs(vault: str) -> list[dict]:
    counts = _label_counts(vault)
    return [{**item, "count": counts.get(item["name"], 0)}
            for item in load_labels(vault)["labels"] if not item.get("archived")]


@storage
def save_label(vault: str, value=None, name=None, color=None,
               priority_bonus=None, order=None) -> dict:
    from .label_plan import apply_web, catalog
    from .locking import write_lock
    with write_lock():
        data, _ = catalog(vault)
        old = _resolve(data["labels"], value) if value else None
        change = {"action": "update" if old else "create",
                  **({"label_id": old["id"]} if old else {"key": "web-create"}),
                  "name": _clean_name(name if name is not None else (old["name"] if old else ""))}
        if color is not None:
            change["color"] = _clean_color(color)
        if priority_bonus is not None:
            change["priority_bonus"] = _clean_bonus(priority_bonus)
        if order is not None:
            change["order"] = max(1, int(order))
        prepared, result = apply_web(vault, [change])
        label_id = prepared["payload"]["label_changes"][0]["label_id"]
        label = next(d for d in load_labels(vault)["labels"] if d["id"] == label_id)
        return {**label, "count": _label_counts(vault).get(label["name"], 0),
                "affected": result["counts"]["changed"]}


@storage
def delete_label(vault: str, value, detach=True) -> dict:
    from .label_plan import apply_web, catalog
    from .locking import write_lock
    with write_lock():
        data, _ = catalog(vault)
        label = _resolve(data["labels"], value)
        if not label:
            raise ValueError("标记不存在")
        _, result = apply_web(vault, [{"action": "delete", "label_id": label["id"], "detach": bool(detach)}])
        return {"deleted": True, "name": label["name"], "affected": result["counts"]["changed"]}


@storage
def merge_labels(vault: str, from_value, into_value) -> dict:
    from .label_plan import apply_web, catalog
    from .locking import write_lock
    with write_lock():
        data, _ = catalog(vault)
        source, target = _resolve(data["labels"], from_value), _resolve(data["labels"], into_value)
        if not source or not target:
            raise ValueError("合并标记不存在")
        _, result = apply_web(vault, [{"action": "merge", "label_id": source["id"], "into": target["id"]}])
        return {"merged": True, "from": source["name"], "into": target["name"], "affected": result["counts"]["changed"]}


@storage
def label_priority_map(vault: str) -> dict[str, float]:
    return {item["name"]: _clean_bonus(item.get("priority_bonus"))
            for item in load_labels(vault)["labels"] if not item.get("archived")}


def label_priority_bonus(labels, bonuses=None, cap=1.0) -> float:
    bonuses = bonuses or {}
    try:
        limit = max(0.0, float(cap))
    except (TypeError, ValueError):
        limit = 1.0
    return min(limit, sum(max(0.0, float(bonuses.get(name, 0) or 0))
                           for name in labels or []))
