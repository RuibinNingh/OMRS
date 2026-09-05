"""展示板持久化、题目引用解析与「纸面记录」（增量打印）。

展示板是呈现层数据，不进入 Ledger。文件只保存题目的稳定 ``question_id`` 与
当前 ``uid`` 快照；读取时优先按 question_id 命中，题目改名或迁移分类后仍能对上。

纸面记录（``printed``）描述「现在纸上已经有什么」：已打印题目在第几页、
占多高、最后一题之后的续排位置（cursor）。有了它就可以只打印新增题目——
新题接在上一张纸的空白处继续排版，已打印区域留白，把原纸放回打印机即可。
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import uuid

from .common import MASTERY_HEADERS, load_csv, mastery_path, omrs_data_dir, split_sections
from .ledger import connect


BOARDS_FILENAME = "boards.json"
BOARDS_VERSION = 1
QUESTION_SECTION = "题目"

DEFAULT_PRINT = {
    "note_ratio": 0.42,       # 右侧留白占内容区宽度的比例
    "gap_lines": 2,           # 题与题之间的留白行数（每行 18px）
    "binding_mm": 22,         # 左侧装订边
    "answers": "none",        # none | append（末页附答案）
    "show_labels": True,
    "show_meta": True,
}
PRINT_MODES = ("all", "new")
EMPTY_PRINTED = {
    "at": "",
    "pages": 0,
    "cursor": {"page": 0, "y": 0.0},
    "print": {},
    "items": [],
    "answer_pages": [],
}


def boards_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), BOARDS_FILENAME)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _clean_name(name) -> str:
    value = str(name or "").strip()
    if not value:
        raise ValueError("展示板名称不能为空")
    return value[:120]


def _int(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _float(value, default, low, high):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_print(value) -> dict:
    """规范化版面设置；未知键忽略，缺失键回退默认值。"""
    result = dict(DEFAULT_PRINT)
    if isinstance(value, dict):
        result.update({key: value[key] for key in DEFAULT_PRINT if key in value})
    result["note_ratio"] = round(_float(result["note_ratio"], DEFAULT_PRINT["note_ratio"], 0.30, 0.55), 2)
    result["gap_lines"] = _int(result["gap_lines"], DEFAULT_PRINT["gap_lines"], 0, 24)
    result["binding_mm"] = _int(result["binding_mm"], DEFAULT_PRINT["binding_mm"], 10, 40)
    if result["answers"] not in {"none", "append"}:
        result["answers"] = "none"
    result["show_labels"] = bool(result["show_labels"])
    result["show_meta"] = bool(result["show_meta"])
    return result


def _normalize_item(item) -> dict:
    item = item if isinstance(item, dict) else {}
    return {
        "question_id": str(item.get("question_id") or "").strip(),
        "uid": str(item.get("uid") or "").strip(),
        "added_at": str(item.get("added_at") or _now()),
        "extra_gap_lines": _int(item.get("extra_gap_lines", 0) or 0, 0, 0, 24),
        "pin": bool(item.get("pin", False)),
    }


def _normalize_segments(raw) -> list:
    segments = []
    for seg in raw or []:
        if not isinstance(seg, dict):
            continue
        page = _int(seg.get("page"), 0, 0, 100000)
        if page <= 0:
            continue
        segments.append({
            "page": page,
            "top": round(_float(seg.get("top"), 0.0, 0.0, 100000.0), 2),
            "height": round(_float(seg.get("height"), 0.0, 0.0, 100000.0), 2),
        })
    return segments


def _normalize_printed(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    pages = _int(raw.get("pages"), 0, 0, 100000)
    if pages <= 0:
        return copy.deepcopy(EMPTY_PRINTED)
    cursor = raw.get("cursor") if isinstance(raw.get("cursor"), dict) else {}
    items = []
    seen = set()
    for item in raw.get("items") or []:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or "").strip()
        if not question_id or question_id in seen:
            continue
        seen.add(question_id)
        items.append({
            "question_id": question_id,
            "uid": str(item.get("uid") or "").strip(),
            "hash": str(item.get("hash") or ""),
            "segments": _normalize_segments(item.get("segments")),
        })
    return {
        "at": str(raw.get("at") or ""),
        "pages": pages,
        "cursor": {
            "page": _int(cursor.get("page"), pages, 1, max(1, pages)),
            "y": round(_float(cursor.get("y"), 0.0, 0.0, 100000.0), 2),
        },
        "print": normalize_print(raw.get("print")),
        "items": items,
        "answer_pages": sorted({p for p in (_int(x, 0, 0, 100000) for x in raw.get("answer_pages") or []) if p > 0}),
    }


def _normalize_board(board) -> dict:
    board = board if isinstance(board, dict) else {}
    created = str(board.get("created_at") or _now())
    items = []
    seen = set()
    for raw in board.get("items") or []:
        item = _normalize_item(raw)
        if not item["uid"] and not item["question_id"]:
            continue
        key = item["question_id"] or f"uid:{item['uid']}"
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return {
        "id": str(board.get("id") or "").strip(),
        "name": str(board.get("name") or "未命名展示板").strip()[:120],
        "note": str(board.get("note") or ""),
        "created_at": created,
        "updated_at": str(board.get("updated_at") or created),
        "source_labels": list(dict.fromkeys(
            str(x).strip() for x in (board.get("source_labels") or []) if str(x).strip()
        )),
        "print": normalize_print(board.get("print")),
        "printed": _normalize_printed(board.get("printed")),
        "items": items,
    }


# ────────────────────────── 文件读写 ──────────────────────────

def load_boards(vault: str) -> dict:
    path = boards_path(vault)
    if not os.path.isfile(path):
        return {"version": BOARDS_VERSION, "boards": []}
    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return {"version": BOARDS_VERSION, "boards": []}
    boards = [_normalize_board(board) for board in (raw.get("boards") or [])]
    return {"version": BOARDS_VERSION, "boards": [board for board in boards if board["id"]]}


def _rotate(path: str, keep: int = 3) -> None:
    if not os.path.isfile(path):
        return
    for index in range(keep, 1, -1):
        old = f"{path}.bak.{index - 1}"
        new = f"{path}.bak.{index}"
        if os.path.exists(old):
            os.replace(old, new)
    with open(path, "rb") as source, open(f"{path}.bak.1", "wb") as target:
        target.write(source.read())


def save_boards(vault: str, data: dict) -> dict:
    path = boards_path(vault)
    normalized = {
        "version": BOARDS_VERSION,
        "boards": [_normalize_board(board) for board in (data.get("boards") or [])],
    }
    _rotate(path)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
    return normalized


def _find(data: dict, board_id: str) -> dict:
    board = next((board for board in data["boards"] if board["id"] == str(board_id or "").strip()), None)
    if not board:
        raise ValueError(f"展示板不存在: {board_id}")
    return board


# ────────────────────────── 题目引用解析 ──────────────────────────

def print_hash_for_content(content: str) -> str:
    """题目正文（纸上印的那部分）的指纹，用于提示「纸面是旧版」。"""
    sections = split_sections(content or "")
    text = (sections.get(QUESTION_SECTION) or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class _Resolver:
    """一次性读取投影与 CSV，避免逐题反复打开文件。"""

    def __init__(self, vault: str):
        self.vault = vault
        self.by_id, self.by_uid = {}, {}
        try:
            with connect(vault) as db:
                for row in db.execute("SELECT * FROM question_projection WHERE archived = 0"):
                    record = dict(row)
                    self.by_id[record["question_id"]] = record
                    self.by_uid[record["uid"]] = record
        except Exception:
            pass
        self.rows_by_uid = {}
        self.rows_by_id = {}
        for row in load_csv(mastery_path(vault), MASTERY_HEADERS):
            uid = row.get("UID", "")
            if not uid:
                continue
            self.rows_by_uid[uid] = row
            if row.get("question_id"):
                self.rows_by_id[row["question_id"]] = row
            if uid not in self.by_uid:
                # 投影尚未建立（极旧数据或测试夹具）时，用 CSV 兜底
                self.by_uid[uid] = {
                    "question_id": row.get("question_id", ""),
                    "uid": uid,
                    "subject": row.get("Subject", ""),
                    "category": row.get("Category", ""),
                    "difficulty": row.get("Difficulty", 5),
                    "suspended": str(row.get("Suspended", "")).lower() in {"1", "true", "yes"},
                    "file_path": row.get("File_Path", ""),
                }
        self._hash_cache = {}

    def record(self, item: dict):
        record = self.by_id.get(item.get("question_id")) if item.get("question_id") else None
        return record or self.by_uid.get(item.get("uid"))

    def print_hash(self, record: dict) -> str:
        file_path = str((record or {}).get("file_path") or "")
        if not file_path:
            return ""
        if file_path in self._hash_cache:
            return self._hash_cache[file_path]
        path = os.path.join(self.vault, file_path.replace("\\", os.sep).replace("/", os.sep))
        try:
            with open(path, "r", encoding="utf-8") as file:
                value = print_hash_for_content(file.read())
        except OSError:
            value = ""
        self._hash_cache[file_path] = value
        return value

    def detail(self, item: dict, printed_index: dict) -> dict:
        record = self.record(item)
        printed = printed_index.get(item.get("question_id"))
        if not record:
            return {
                **item,
                "missing": True,
                "suspended": False,
                "subject": "",
                "category": "",
                "difficulty": "",
                "mastery": 0.0,
                "due_date": "",
                "labels": [],
                "printed": bool(printed),
                "printed_page": printed.get("page") if printed else None,
                "changed": False,
            }
        row = self.rows_by_uid.get(record.get("uid")) or self.rows_by_id.get(record.get("question_id")) or {}
        labels = [x.strip() for x in str(row.get("Labels", "") or "").split("|") if x.strip()]
        question_id = record.get("question_id") or item.get("question_id", "")
        printed = printed_index.get(question_id)
        changed = bool(printed and printed.get("hash") and self.print_hash(record) != printed["hash"])
        try:
            mastery = float(row.get("Mastery", 0) or 0)
        except (TypeError, ValueError):
            mastery = 0.0
        return {
            **item,
            "question_id": question_id,
            "uid": record.get("uid") or item.get("uid", ""),
            "file_path": record.get("file_path", ""),
            "missing": False,
            "suspended": bool(record.get("suspended")) or str(row.get("Suspended", "")).lower() in {"1", "true", "yes"},
            "subject": record.get("subject") or row.get("Subject", ""),
            "category": record.get("category") or row.get("Category", ""),
            "difficulty": record.get("difficulty", row.get("Difficulty", "")),
            "mastery": mastery,
            "due_date": row.get("Due_Date", ""),
            "labels": labels,
            "printed": bool(printed),
            "printed_page": printed.get("page") if printed else None,
            "changed": changed,
        }


def _printed_index(printed: dict) -> dict:
    index = {}
    for item in (printed or {}).get("items") or []:
        segments = item.get("segments") or []
        index[item["question_id"]] = {
            "page": segments[0]["page"] if segments else None,
            "hash": item.get("hash", ""),
        }
    return index


def _printed_summary(board: dict, details: list) -> dict:
    printed = board.get("printed") or copy.deepcopy(EMPTY_PRINTED)
    index = _printed_index(printed)
    active = [d for d in details if not d["missing"] and not d["suspended"]]
    return {
        "at": printed.get("at", ""),
        "pages": printed.get("pages", 0),
        "count": len(printed.get("items") or []),
        "new_count": sum(1 for d in active if d["question_id"] not in index),
        "changed_count": sum(1 for d in details if d.get("changed")),
        "cursor": dict(printed.get("cursor") or {}),
        "answer_pages": list(printed.get("answer_pages") or []),
        "print": dict(printed.get("print") or {}),
    }


def list_boards(vault: str) -> list:
    data = load_boards(vault)
    resolver = _Resolver(vault)
    result = []
    for board in data["boards"]:
        index = _printed_index(board["printed"])
        details = [resolver.detail(item, index) for item in board["items"]]
        result.append({
            "id": board["id"],
            "name": board["name"],
            "note": board["note"],
            "count": len(details),
            "updated_at": board["updated_at"],
            "created_at": board["created_at"],
            "print": board["print"],
            "missing": sum(1 for item in details if item["missing"]),
            "suspended": sum(1 for item in details if item["suspended"]),
            "printed_summary": _printed_summary(board, details),
        })
    return result


def get_board(vault: str, board_id: str):
    data = load_boards(vault)
    board = next((board for board in data["boards"] if board["id"] == str(board_id or "").strip()), None)
    if not board:
        return None
    resolver = _Resolver(vault)
    index = _printed_index(board["printed"])
    details = [resolver.detail(item, index) for item in board["items"]]
    return {
        **copy.deepcopy(board),
        "items": details,
        "printed_summary": _printed_summary(board, details),
    }


# ────────────────────────── 增删改 ──────────────────────────

def _new_id() -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return f"BD-{stamp}-{uuid.uuid4().hex[:6]}"


def create_board(vault: str, name: str, uids=None, label: str = "") -> dict:
    data = load_boards(vault)
    resolver = _Resolver(vault)
    now = _now()
    items, seen = [], set()
    for uid in uids or []:
        record = resolver.by_uid.get(str(uid or "").strip())
        if not record:
            continue
        key = record.get("question_id") or f"uid:{record['uid']}"
        if key in seen:
            continue
        seen.add(key)
        items.append({"question_id": record.get("question_id", ""), "uid": record["uid"], "added_at": now})
    board = _normalize_board({
        "id": _new_id(),
        "name": _clean_name(name),
        "created_at": now,
        "updated_at": now,
        "source_labels": [label] if label else [],
        "print": DEFAULT_PRINT,
        "items": items,
    })
    data["boards"].append(board)
    save_boards(vault, data)
    return get_board(vault, board["id"])


def update_board(vault: str, board_id: str, **changes) -> dict:
    data = load_boards(vault)
    board = _find(data, board_id)
    if changes.get("name") is not None:
        board["name"] = _clean_name(changes["name"])
    if changes.get("note") is not None:
        board["note"] = str(changes["note"])
    if changes.get("source_labels") is not None:
        raw = changes["source_labels"]
        if isinstance(raw, str):
            raw = [raw]
        board["source_labels"] = list(dict.fromkeys(
            str(value).strip() for value in (raw or []) if str(value).strip()
        ))
    if isinstance(changes.get("print"), dict):
        board["print"] = normalize_print({**board.get("print", {}), **changes["print"]})
    if changes.get("items") is not None:
        # 整体覆盖：保留每题原有 added_at，避免前端只传 uid 时把加入时间冲掉
        previous = {item["question_id"] or f"uid:{item['uid']}": item for item in board["items"]}
        items = []
        for raw in changes["items"] or []:
            item = _normalize_item(raw)
            key = item["question_id"] or f"uid:{item['uid']}"
            old = previous.get(key)
            if old and not (raw or {}).get("added_at"):
                item["added_at"] = old["added_at"]
            items.append(item)
        board["items"] = items
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def add_items(vault: str, board_id: str, uids, position=None) -> dict:
    data = load_boards(vault)
    board = _find(data, board_id)
    resolver = _Resolver(vault)
    existing_ids = {item.get("question_id") for item in board["items"] if item.get("question_id")}
    existing_uids = {item.get("uid") for item in board["items"] if item.get("uid")}
    added = []
    for raw_uid in uids or []:
        uid = str(raw_uid or "").strip()
        record = resolver.by_uid.get(uid)
        if not record:
            continue
        question_id = record.get("question_id") or ""
        if uid in existing_uids or (question_id and question_id in existing_ids):
            continue
        if question_id:
            existing_ids.add(question_id)
        existing_uids.add(uid)
        added.append({"question_id": question_id, "uid": uid, "added_at": _now()})
    at = len(board["items"]) if position in (None, "") else _int(position, len(board["items"]), 0, len(board["items"]))
    board["items"][at:at] = added
    board["updated_at"] = _now()
    save_boards(vault, data)
    result = get_board(vault, board_id)
    result["added"] = len(added)
    return result


def remove_items(vault: str, board_id: str, uids) -> dict:
    data = load_boards(vault)
    board = _find(data, board_id)
    remove = {str(uid or "").strip() for uid in uids or []}
    board["items"] = [
        item for item in board["items"]
        if item.get("uid") not in remove and item.get("question_id") not in remove
    ]
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def duplicate_board(vault: str, board_id: str, name: str) -> dict:
    """复制板：复制题目引用与版面设置；纸面记录不复制（新板对应新纸）。"""
    data = load_boards(vault)
    source = _find(data, board_id)
    now = _now()
    clone = _normalize_board({
        "id": _new_id(),
        "name": _clean_name(name),
        "note": source.get("note", ""),
        "created_at": now,
        "updated_at": now,
        "source_labels": source.get("source_labels", []),
        "print": source.get("print", DEFAULT_PRINT),
        "items": copy.deepcopy(source.get("items", [])),
    })
    data["boards"].append(clone)
    save_boards(vault, data)
    return get_board(vault, clone["id"])


def delete_board(vault: str, board_id: str) -> bool:
    data = load_boards(vault)
    before = len(data["boards"])
    data["boards"] = [board for board in data["boards"] if board["id"] != board_id]
    if len(data["boards"]) == before:
        return False
    save_boards(vault, data)
    return True


# ────────────────────────── 导出与纸面记录 ──────────────────────────

def board_items_for_export(vault: str, board_id: str, mode: str = "all"):
    """返回 (board, 可导出的 items)。

    停用与缺失题始终跳过（与 A4 导出一致）。``mode="new"`` 时只返回
    尚未进入纸面记录的题目，供增量打印使用。
    """
    board = get_board(vault, board_id)
    if not board:
        raise ValueError(f"展示板不存在: {board_id}")
    mode = mode if mode in PRINT_MODES else "all"
    printed_ids = {item["question_id"] for item in board["printed"].get("items") or []}
    items = []
    for item in board["items"]:
        if item["missing"] or item["suspended"]:
            continue
        if mode == "new" and item["question_id"] in printed_ids:
            continue
        items.append(item)
    return board, items


def record_printed(vault: str, board_id: str, mode: str, layout: dict) -> dict:
    """把浏览器测得的版面写入纸面记录。

    ``layout`` = {pages, cursor:{page,y}, items:[{question_id, uid, segments:[{page,top,height}]}],
                  answer_pages:[...]}
    mode="all" 整体替换；mode="new" 在原记录上追加新题并推进 cursor / pages。
    """
    data = load_boards(vault)
    board = _find(data, board_id)
    mode = mode if mode in PRINT_MODES else "all"
    layout = layout if isinstance(layout, dict) else {}
    pages = _int(layout.get("pages"), 0, 0, 100000)
    if pages <= 0:
        raise ValueError("版面数据没有页数，无法记录")
    resolver = _Resolver(vault)
    new_items = []
    for raw in layout.get("items") or []:
        if not isinstance(raw, dict):
            continue
        question_id = str(raw.get("question_id") or "").strip()
        if not question_id:
            continue
        record = resolver.by_id.get(question_id) or resolver.by_uid.get(str(raw.get("uid") or ""))
        new_items.append({
            "question_id": question_id,
            "uid": str(raw.get("uid") or (record or {}).get("uid") or ""),
            "hash": resolver.print_hash(record) if record else "",
            "segments": _normalize_segments(raw.get("segments")),
        })
    cursor = layout.get("cursor") if isinstance(layout.get("cursor"), dict) else {}
    answer_pages = sorted({p for p in (_int(x, 0, 0, 100000) for x in layout.get("answer_pages") or []) if p > 0})
    previous = board.get("printed") or copy.deepcopy(EMPTY_PRINTED)
    if mode == "new" and previous.get("pages", 0) > 0:
        known = {item["question_id"] for item in previous["items"]}
        printed = {
            "at": _now(),
            "pages": max(pages, previous["pages"]),
            "cursor": cursor,
            "print": previous.get("print") or board["print"],
            "items": list(previous["items"]) + [item for item in new_items if item["question_id"] not in known],
            "answer_pages": sorted(set(previous.get("answer_pages") or []) | set(answer_pages)),
        }
    else:
        printed = {
            "at": _now(),
            "pages": pages,
            "cursor": cursor,
            "print": board["print"],
            "items": new_items,
            "answer_pages": answer_pages,
        }
    board["printed"] = _normalize_printed(printed)
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def reset_printed(vault: str, board_id: str) -> dict:
    data = load_boards(vault)
    board = _find(data, board_id)
    board["printed"] = copy.deepcopy(EMPTY_PRINTED)
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)
