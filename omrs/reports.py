"""AI 分析报告托管。

报告（纯 HTML）存放在 `错题/report/`，元数据索引在 `错题/report/index.json`。
报告由后端同源提供（GET /api/report/view?id=...），因此报告内可用
`<img src="/api/image?name=...">` 直接引用题目图片（见 api.md / data.md）。

对应 API：
  GET  /api/reports          → list_reports()
  POST /api/report/create    → create_report(name, html)
  GET  /api/report/view?id=  → get_report_html(id)
  POST /api/report/delete    → delete_report(id)
"""

import datetime
import json
import os
import re

from .common import questions_root

REPORT_DIR = "report"
_INDEX = "index.json"
_ID_RE = re.compile(r"^RPT-[0-9A-Za-z]+$")


def reports_dir(vault: str) -> str:
    path = os.path.join(questions_root(vault), REPORT_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _index_path(vault: str) -> str:
    return os.path.join(reports_dir(vault), _INDEX)


def _load_index(vault: str) -> list:
    path = _index_path(vault)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_index(vault: str, items: list) -> None:
    tmp = _index_path(vault) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, _index_path(vault))


def list_reports(vault: str) -> list:
    """按创建时间倒序返回元数据列表（过滤掉文件已丢失的条目）。"""
    items = _load_index(vault)
    rdir = reports_dir(vault)
    alive = [it for it in items if os.path.isfile(os.path.join(rdir, it.get("filename", "")))]
    alive.sort(key=lambda it: it.get("created_at", ""), reverse=True)
    return alive


def _valid_id(report_id: str) -> bool:
    return bool(report_id) and bool(_ID_RE.match(report_id))


def create_report(vault: str, name: str, html: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("报告名称不能为空")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("报告内容（HTML）不能为空")

    now = datetime.datetime.now()
    report_id = f"RPT-{now.strftime('%Y%m%d%H%M%S')}"
    # 同秒冲突加后缀
    existing_ids = {it.get("id") for it in _load_index(vault)}
    if report_id in existing_ids:
        suffix = 1
        while f"{report_id}-{suffix}" in existing_ids:
            suffix += 1
        report_id = f"{report_id}-{suffix}"

    filename = f"{report_id}.html"
    payload = html.encode("utf-8")
    path = os.path.join(reports_dir(vault), filename)
    with open(path, "w", encoding="utf-8") as file:
        file.write(html)
        file.flush()
        os.fsync(file.fileno())

    meta = {
        "id": report_id,
        "name": name,
        "filename": filename,
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "size": len(payload),
    }
    items = _load_index(vault)
    items.append(meta)
    _save_index(vault, items)
    return meta


def get_report_html(vault: str, report_id: str) -> bytes:
    items = _load_index(vault)
    meta = next((it for it in items if it.get("id") == report_id), None)
    if not meta:
        raise ValueError("报告不存在")
    path = os.path.join(reports_dir(vault), meta.get("filename", ""))
    if not os.path.isfile(path):
        raise ValueError("报告文件已丢失")
    with open(path, "rb") as file:
        return file.read()


def delete_report(vault: str, report_id: str) -> bool:
    items = _load_index(vault)
    meta = next((it for it in items if it.get("id") == report_id), None)
    if not meta:
        return False
    path = os.path.join(reports_dir(vault), meta.get("filename", ""))
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
    _save_index(vault, [it for it in items if it.get("id") != report_id])
    return True
