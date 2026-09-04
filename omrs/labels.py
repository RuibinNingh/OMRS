"""用户标记定义、题目 YAML 标记级联和查询。

标记定义存于 ``错题/.omrs/labels.json``；题目 Markdown 只保存标记名称，
因此 Obsidian 中仍然可以直接查看和编辑。题目归属的写入统一经过
``scan_workspace``，由既有 metadata_update_external 机制生成 Ledger 记录。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import uuid

from .common import extract_labels, load_csv, mastery_path, omrs_data_dir, MASTERY_HEADERS, parse_yaml_frontmatter
from .question_ops import set_question_labels
from .workspace_sync import scan_workspace


LABELS_FILENAME = "labels.json"
LABELS_VERSION = 1
DEFAULT_COLOR = "#64748b"
COLORS = {
    "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink",
}


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


def _label_counts(vault: str) -> dict:
    counts = {}
    for row in load_csv(mastery_path(vault), MASTERY_HEADERS):
        for name in str(row.get("Labels", "") or "").split("|"):
            name = name.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def list_label_defs(vault: str) -> list[dict]:
    counts = _label_counts(vault)
    return [{**item, "count": counts.get(item["name"], 0)}
            for item in load_labels(vault)["labels"] if not item.get("archived")]


def save_label(vault: str, value=None, name=None, color=None,
               priority_bonus=None, order=None) -> dict:
    data = load_labels(vault)
    old = _resolve(data["labels"], value) if value else None
    clean = _clean_name(name if name is not None else (old["name"] if old else ""))
    duplicate = next((item for item in data["labels"]
                      if item["name"] == clean and item is not old), None)
    if duplicate:
        raise ValueError(f"标记已存在: {clean}")
    if old:
        old_name = old["name"]
        old["name"] = clean
        if color is not None:
            old["color"] = _clean_color(color)
        if priority_bonus is not None:
            old["priority_bonus"] = _clean_bonus(priority_bonus)
        if order is not None:
            old["order"] = max(1, int(order))
        old["archived"] = False
        affected = _rename_references(vault, old_name, clean) if old_name != clean else 0
        save_labels(vault, data)
        return {**old, "count": _label_counts(vault).get(clean, 0), "affected": affected}
    label = {
        "id": f"LB-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
        "name": clean,
        "color": _clean_color(color),
        "order": max([item["order"] for item in data["labels"]] or [0]) + 1
            if order is None else max(1, int(order)),
        "priority_bonus": _clean_bonus(priority_bonus),
        "archived": False,
        "created_at": _now(),
    }
    data["labels"].append(label)
    save_labels(vault, data)
    return {**label, "count": 0, "affected": 0}


def _rename_references(vault: str, old_name: str, new_name: str) -> int:
    """批量改名，返回实际含旧名称的题目数。"""
    if old_name == new_name:
        return 0
    from .ledger import connect
    with connect(vault) as db:
        rows = [dict(row) for row in db.execute(
            "SELECT uid FROM question_projection WHERE archived = 0"
        ).fetchall()]
    changed = 0
    for row in rows:
        try:
            with connect(vault) as db:
                record = db.execute(
                    "SELECT file_path FROM question_projection WHERE uid = ? AND archived = 0",
                    (row["uid"],),
                ).fetchone()
            if not record:
                continue
            path = os.path.join(vault, str(record["file_path"]).replace("\\", os.sep))
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
            labels = extract_labels(parse_yaml_frontmatter(content))
            if old_name not in labels:
                continue
            labels = [new_name if item == old_name else item for item in labels]
            if set(labels) != set(extract_labels(parse_yaml_frontmatter(content))):
                set_question_labels(vault, row["uid"], labels, scan=False)
                changed += 1
        except (OSError, RuntimeError):
            continue
    if changed:
        scan_workspace(vault)
    return changed


def delete_label(vault: str, value, detach=True) -> dict:
    data = load_labels(vault)
    label = _resolve(data["labels"], value)
    if not label:
        raise ValueError("标记不存在")
    affected = 0
    if detach:
        affected = _remove_reference(vault, label["name"])
    data["labels"] = [item for item in data["labels"] if item["id"] != label["id"]]
    save_labels(vault, data)
    return {"deleted": True, "name": label["name"], "affected": affected}


def _remove_reference(vault: str, name: str) -> int:
    from .ledger import connect
    with connect(vault) as db:
        rows = [dict(row) for row in db.execute(
            "SELECT uid, file_path FROM question_projection WHERE archived = 0"
        ).fetchall()]
    changed = 0
    for row in rows:
        try:
            path = os.path.join(vault, str(row["file_path"]).replace("\\", os.sep))
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
            from .common import parse_yaml_frontmatter
            labels = extract_labels(parse_yaml_frontmatter(content))
            if name not in labels:
                continue
            set_question_labels(vault, row["uid"], [item for item in labels if item != name], scan=False)
            changed += 1
        except (OSError, RuntimeError):
            continue
    if changed:
        scan_workspace(vault)
    return changed


def merge_labels(vault: str, from_value, into_value) -> dict:
    data = load_labels(vault)
    source = _resolve(data["labels"], from_value)
    target = _resolve(data["labels"], into_value)
    if not source or not target:
        raise ValueError("合并标记不存在")
    if source["id"] == target["id"]:
        raise ValueError("不能把标记合并到自身")
    # Capture references before changing any Markdown so the merge preserves
    # other labels on each affected question.
    from .ledger import connect
    with connect(vault) as db:
        rows = [dict(row) for row in db.execute(
            "SELECT uid, file_path FROM question_projection WHERE archived = 0"
        ).fetchall()]
    affected_rows = []
    for row in rows:
        try:
            path = os.path.join(vault, str(row["file_path"]).replace("\\", os.sep))
            with open(path, "r", encoding="utf-8") as file:
                labels = extract_labels(parse_yaml_frontmatter(file.read()))
            if source["name"] in labels:
                affected_rows.append((row, labels))
        except OSError:
            continue
    source_uids = {row["uid"] for row, _ in affected_rows}
    for row, labels in affected_rows:
        merged = [target["name"] if name == source["name"] else name for name in labels]
        merged = list(dict.fromkeys(merged))
        set_question_labels(vault, row["uid"], merged, scan=False)
    if source_uids:
        scan_workspace(vault)
    data["labels"] = [item for item in data["labels"] if item["id"] != source["id"]]
    save_labels(vault, data)
    return {"merged": True, "from": source["name"], "into": target["name"], "affected": len(source_uids)}


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
