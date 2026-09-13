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
PRINTED_HISTORY_FILENAME = "boards_printed_history.jsonl"
BOARDS_VERSION = 3
QUESTION_SECTION = "题目"
UNFILED = ""                  # 未归档：folder_id 为空串，不是一个真实文件夹记录

DEFAULT_PRINT = {
    "note_ratio": 0.50,       # 右侧留白占可分配宽度的比例，默认与题栏等宽
    "gap_lines": 2,           # 题与题之间的留白行数（每行 18px）
    "answers": "none",        # none | append（末页附答案）
    "show_labels": True,
    "show_meta": True,
    "cut_line": "dash",       # none | dash | solid：每题留白末尾的裁切提示线
    "cut_label": False,       # 切割线右端是否标「第 N 题止」
    "locked": False,          # 保护纸面版式；增删引用 / 排序不重置纸面
}
CUT_LINES = ("none", "dash", "solid")
MAX_GAP_LINES = 48            # 每题留白上限（v2 的 extra_gap_lines 上限是 24）
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


def printed_history_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), PRINTED_HISTORY_FILENAME)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _clean_name(name) -> str:
    value = str(name or "").strip()
    if not value:
        raise ValueError("展示板名称不能为空")
    return value[:120]


def _clean_folder_name(name) -> str:
    value = " ".join(str(name or "").split())
    if not value:
        raise ValueError("文件夹名称不能为空")
    return value[:60]


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
    if result["answers"] not in {"none", "append"}:
        result["answers"] = "none"
    result["show_labels"] = bool(result["show_labels"])
    result["show_meta"] = bool(result["show_meta"])
    if result["cut_line"] not in CUT_LINES:
        result["cut_line"] = DEFAULT_PRINT["cut_line"]
    result["cut_label"] = bool(result["cut_label"])
    result["locked"] = bool(result["locked"])
    return result


def _gap_or_none(value):
    """把外部传来的每题留白收敛成 ``0..MAX_GAP_LINES`` 或 ``None``（继承全局）。

    读不懂的值（``"x"``、``NaN``、负数字符串）一律当「没设」而不是 0：
    0 是「这题后面不留白」的真实选择，把坏数据折成 0 会静默改掉纸面。
    """
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(MAX_GAP_LINES, number))


def _normalize_item(item, default_gap=None) -> dict:
    """规范化一个条目；``default_gap`` 是所在板的全局题间留白，只用于 v2 折算。

    ``gap_lines`` 是这道题之后留白的**绝对行数**：``None`` 表示继承全局设置，
    数字表示覆盖。v2 的 ``extra_gap_lines`` 是「在全局之上再加几行」，这里按
    ``全局 + 额外`` 折算成等值的绝对行数，迁移前后纸面像素完全一致。折算后
    ``extra_gap_lines`` 恒为 0，因此重复归一化是空操作（幂等）。
    """
    item = item if isinstance(item, dict) else {}
    extra = _int(item.get("extra_gap_lines", 0) or 0, 0, 0, 24)
    gap = _gap_or_none(item.get("gap_lines"))
    if gap is None and extra:
        gap = min(MAX_GAP_LINES, _int(default_gap, 0, 0, MAX_GAP_LINES) + extra)
    return {
        "question_id": str(item.get("question_id") or "").strip(),
        "uid": str(item.get("uid") or "").strip(),
        "added_at": str(item.get("added_at") or _now()),
        "gap_lines": gap,
        "extra_gap_lines": 0,       # v2 兼容字段：折算后恒为 0，只读不写
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


def _normalize_folder(folder, index: int = 0) -> dict:
    """规范化文件夹记录；名称为空的记录由调用方（load/save）过滤掉。"""
    folder = folder if isinstance(folder, dict) else {}
    created = str(folder.get("created_at") or _now())
    try:
        name = _clean_folder_name(folder.get("name"))
    except ValueError:
        name = ""
    return {
        "id": str(folder.get("id") or "").strip(),
        "name": name,
        "order": _int(folder.get("order", index), index, 0, 9999),
        "created_at": created,
        "updated_at": str(folder.get("updated_at") or created),
    }


def effective_gap_lines(item, print_settings) -> int:
    """一道题实际留几行：``gap_lines`` 为 None 时继承板的全局设置。"""
    value = (item or {}).get("gap_lines")
    if value is None:
        value = (print_settings or {}).get("gap_lines", DEFAULT_PRINT["gap_lines"])
    return _int(value, DEFAULT_PRINT["gap_lines"], 0, MAX_GAP_LINES)


def _normalize_board(board) -> dict:
    board = board if isinstance(board, dict) else {}
    created = str(board.get("created_at") or _now())
    settings = normalize_print(board.get("print"))
    items = []
    seen = set()
    for raw in board.get("items") or []:
        item = _normalize_item(raw, settings["gap_lines"])
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
        "folder_id": str(board.get("folder_id") or "").strip(),
        "order": _int(board.get("order", 0), 0, 0, 9999),
        "created_at": created,
        "updated_at": str(board.get("updated_at") or created),
        "source_labels": list(dict.fromkeys(
            str(x).strip() for x in (board.get("source_labels") or []) if str(x).strip()
        )),
        "print": settings,
        "printed": _normalize_printed(board.get("printed")),
        "items": items,
    }


# ────────────────────────── 文件读写 ──────────────────────────

def _arrange(folders: list, boards: list) -> tuple:
    """规范化整份数据的归属与顺序，load 与 save 共用，因此结果是幂等的。

    - 丢掉无 id / 无名 / 重复 id 的文件夹；文件夹按 order 重排并重新编号 0..n-1。
    - 板的 folder_id 指向不存在的文件夹时静默归入未归档（不报错、不丢板）。
    - 板在所在分组内按 (order, updated_at 倒序) 排序后重新编号。
    """
    clean_folders, seen = [], set()
    for index, folder in enumerate(folders or []):
        item = _normalize_folder(folder, index)
        if not item["id"] or not item["name"] or item["id"] in seen:
            continue
        seen.add(item["id"])
        clean_folders.append(item)
    clean_folders.sort(key=lambda folder: (folder["order"], folder["created_at"]))
    for index, folder in enumerate(clean_folders):
        folder["order"] = index

    clean_boards = [board for board in boards or [] if board["id"]]
    for board in clean_boards:
        if board["folder_id"] not in seen:
            board["folder_id"] = UNFILED
    groups = {}
    for board in clean_boards:
        groups.setdefault(board["folder_id"], []).append(board)
    for group in groups.values():
        group.sort(key=lambda board: (board["order"], _neg_time(board["updated_at"])))
        for index, board in enumerate(group):
            board["order"] = index
    # 输出顺序 = 文件夹顺序 + 组内顺序，未归档恒在最后
    ordered = []
    for folder in clean_folders:
        ordered.extend(groups.get(folder["id"], []))
    ordered.extend(groups.get(UNFILED, []))
    return clean_folders, ordered


def _neg_time(value: str) -> str:
    """把时间串变成「越新越小」的排序键，供正序 sort 表达倒序时间。"""
    return "".join(chr(0x10FFFD - ord(char)) if ord(char) < 0x10FFFD else char for char in str(value or ""))


def load_boards(vault: str) -> dict:
    path = boards_path(vault)
    if not os.path.isfile(path):
        return {"version": BOARDS_VERSION, "folders": [], "boards": []}
    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return {"version": BOARDS_VERSION, "folders": [], "boards": []}
    # v1 没有 folders 键：全部板落到未归档，写回时自然升到 v2
    folders, boards = _arrange(
        raw.get("folders") or [],
        [_normalize_board(board) for board in (raw.get("boards") or [])],
    )
    return {"version": BOARDS_VERSION, "folders": folders, "boards": boards}


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
    folders, boards = _arrange(
        data.get("folders") or [],
        [_normalize_board(board) for board in (data.get("boards") or [])],
    )
    normalized = {"version": BOARDS_VERSION, "folders": folders, "boards": boards}
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
            "folder_id": board["folder_id"],
            "order": board["order"],
            "count": len(details),
            # 选板浮层要在点之前就显示「已有 1/3」，靠这份 uid 集合本地算，避免逐板再请求
            "uids": [detail["uid"] for detail in details if detail["uid"]],
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
    for detail in details:
        detail["effective_gap_lines"] = effective_gap_lines(detail, board["print"])
    return {
        **copy.deepcopy(board),
        "items": details,
        "printed_summary": _printed_summary(board, details),
    }


# ────────────────────────── 增删改 ──────────────────────────

def _new_id() -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return f"BD-{stamp}-{uuid.uuid4().hex[:6]}"


def _new_folder_id() -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return f"BF-{stamp}-{uuid.uuid4().hex[:6]}"


def _folder_or_unfiled(data: dict, folder_id) -> str:
    """把外部传进来的 folder_id 收敛成「存在的文件夹」或未归档。"""
    value = str(folder_id or "").strip()
    return value if any(folder["id"] == value for folder in data["folders"]) else UNFILED


def _group(data: dict, folder_id: str) -> list:
    return [board for board in data["boards"] if board["folder_id"] == folder_id]


# ────────────────────────── 文件夹 ──────────────────────────

def list_folders(vault: str) -> list:
    return [dict(folder) for folder in load_boards(vault)["folders"]]


def create_folder(vault: str, name: str) -> dict:
    data = load_boards(vault)
    now = _now()
    folder = _normalize_folder({
        "id": _new_folder_id(),
        "name": _clean_folder_name(name),
        "order": len(data["folders"]),
        "created_at": now,
        "updated_at": now,
    }, len(data["folders"]))
    data["folders"].append(folder)
    save_boards(vault, data)
    return next(item for item in load_boards(vault)["folders"] if item["id"] == folder["id"])


def update_folder(vault: str, folder_id: str, **changes) -> dict:
    data = load_boards(vault)
    folder = next((item for item in data["folders"] if item["id"] == str(folder_id or "").strip()), None)
    if not folder:
        raise ValueError(f"文件夹不存在: {folder_id}")
    if changes.get("name") is not None:
        folder["name"] = _clean_folder_name(changes["name"])
    if changes.get("order") is not None:
        target = _int(changes["order"], folder["order"], 0, max(0, len(data["folders"]) - 1))
        others = [item for item in data["folders"] if item["id"] != folder["id"]]
        others.insert(target, folder)
        for index, item in enumerate(others):
            item["order"] = index
        data["folders"] = others
    folder["updated_at"] = _now()
    save_boards(vault, data)
    return next(item for item in load_boards(vault)["folders"] if item["id"] == folder["id"])


def delete_folder(vault: str, folder_id: str, keep_boards: bool = True) -> dict:
    """删除文件夹。keep_boards 时把组内板移到未归档，否则连板一起删。"""
    data = load_boards(vault)
    target = str(folder_id or "").strip()
    if not any(folder["id"] == target for folder in data["folders"]):
        raise ValueError(f"文件夹不存在: {folder_id}")
    affected = _group(data, target)
    if keep_boards:
        tail = len(_group(data, UNFILED))
        for offset, board in enumerate(affected):
            board["folder_id"] = UNFILED
            board["order"] = tail + offset
    else:
        keep = {board["id"] for board in affected}
        data["boards"] = [board for board in data["boards"] if board["id"] not in keep]
    data["folders"] = [folder for folder in data["folders"] if folder["id"] != target]
    save_boards(vault, data)
    return {"deleted": True, "boards_kept": len(affected) if keep_boards else 0,
            "boards_deleted": 0 if keep_boards else len(affected)}


def move_board(vault: str, board_id: str, folder_id=None, index=None) -> dict:
    """把板移到某个文件夹，并可指定它在该组内的位置。"""
    data = load_boards(vault)
    board = _find(data, board_id)
    target = board["folder_id"] if folder_id is None else _folder_or_unfiled(data, folder_id)
    siblings = [item for item in _group(data, target) if item["id"] != board["id"]]
    at = len(siblings) if index in (None, "") else _int(index, len(siblings), 0, len(siblings))
    board["folder_id"] = target
    siblings.insert(at, board)
    for position, item in enumerate(siblings):
        item["order"] = position
    save_boards(vault, data)
    return get_board(vault, board_id)


def create_board(vault: str, name: str, uids=None, label: str = "", folder_id: str = "") -> dict:
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
    folder = _folder_or_unfiled(data, folder_id)
    board = _normalize_board({
        "id": _new_id(),
        "name": _clean_name(name),
        "folder_id": folder,
        "order": len(_group(data, folder)),
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
    if changes.get("folder_id") is not None:
        board["folder_id"] = _folder_or_unfiled(data, changes["folder_id"])
    if changes.get("source_labels") is not None:
        raw = changes["source_labels"]
        if isinstance(raw, str):
            raw = [raw]
        board["source_labels"] = list(dict.fromkeys(
            str(value).strip() for value in (raw or []) if str(value).strip()
        ))
    old_print = normalize_print(board.get("print"))
    old_items = list(board.get("items") or [])
    if isinstance(changes.get("print"), dict):
        board["print"] = normalize_print({**board.get("print", {}), **changes["print"]})
    if changes.get("items") is not None:
        # 整体覆盖：保留每题原有 added_at，避免前端只传 uid 时把加入时间冲掉
        # print 分支在上面已经生效，这里取到的是本次请求之后的全局留白：
        # 同一帧提交 items + print 时，v2 折算用的是新设置，不会用旧值折算出错值。
        previous = {item["question_id"] or f"uid:{item['uid']}": item for item in board["items"]}
        previous_by_uid = {item["uid"]: item for item in board["items"]}
        resolver = _Resolver(vault)
        items = []
        for raw in changes["items"] or []:
            item = _normalize_item(raw, board["print"]["gap_lines"])
            record = resolver.record(item)
            if record:
                item["question_id"] = record.get("question_id") or item["question_id"]
                item["uid"] = record.get("uid") or item["uid"]
            key = item["question_id"] or f"uid:{item['uid']}"
            old = previous.get(key) or previous_by_uid.get(item["uid"])
            if old and not (raw or {}).get("added_at"):
                item["added_at"] = old["added_at"]
            items.append(item)
        board["items"] = items
    # 引用集合/顺序不是纸面：只比较仍在板内的已印题的有效留白。
    # 已移出的题保留旧占位；新题（含重新加入的旧 ID）都不重排既有纸面。
    printed_ids = {item["question_id"] for item in board["printed"]["items"]}
    previous_items = {item["question_id"]: item for item in old_items if item["question_id"]}
    printed_gap_changed = any(
        item["question_id"] in printed_ids and item["question_id"] in previous_items
        and effective_gap_lines(previous_items[item["question_id"]], old_print)
        != effective_gap_lines(item, board["print"])
        for item in board["items"]
    )
    layout_changed = (
        (isinstance(changes.get("print"), dict) and any(
            old_print.get(key) != board["print"].get(key)
            for key in ("note_ratio", "show_labels", "show_meta", "cut_line")
        ))
        or (board["print"]["cut_line"] != "none" and old_print["cut_label"] != board["print"]["cut_label"])
        or printed_gap_changed
    )
    if layout_changed and (old_print.get("locked") or board["print"].get("locked")):
        _append_printed_history(vault, board, "reset")
        board["printed"] = copy.deepcopy(EMPTY_PRINTED)
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
    # 引用追加不改变已经印在纸上的位置；新增题按原 cursor 续排。
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
    # 移出引用不能擦掉纸上的旧占位；同一稳定 ID 再加入仍算已打印。
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
        "folder_id": source.get("folder_id", UNFILED),
        "order": source.get("order", 0) + 1,
        "created_at": now,
        "updated_at": now,
        "source_labels": source.get("source_labels", []),
        "print": source.get("print", DEFAULT_PRINT),
        "items": copy.deepcopy(source.get("items", [])),
    })
    data["boards"].append(clone)
    # 组内位置显式排在源板之后：同秒操作的 updated_at 会撞在一起，不能靠时间兜底
    siblings = [board for board in _group(data, clone["folder_id"]) if board["id"] != clone["id"]]
    at = next((index for index, board in enumerate(siblings) if board["id"] == source["id"]), len(siblings) - 1) + 1
    siblings.insert(at, clone)
    for index, board in enumerate(siblings):
        board["order"] = index
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


# ────────────────────────── 纸面记录历史（追加式） ──────────────────────────

def _append_printed_history(vault: str, board: dict, event: str, mode: str = "") -> bool:
    """把即将被替换的纸面记录的摘要追加进 jsonl，一行一条，只增不改。

    展示板是呈现层数据，不进 Ledger（见 ``AI/ledger.md``）；这份 jsonl 是审计辅助，
    只含题数、页数、cursor 与设置，没有逐题 items/segments/hash，不能直接恢复纸面。
    空纸面（pages<=0）没有可留存的历史，跳过。
    写失败只记运行日志，绝不打断打印记录本身。
    """
    snapshot = (board or {}).get("printed") or {}
    if _int(snapshot.get("pages"), 0, 0, 100000) <= 0:
        return False
    line = {
        "at": _now(),                                     # 事件时间（这份快照被替换的时刻）
        "board_id": board.get("id", ""),
        "board_name": board.get("name", ""),
        "event": event if event in {"record", "reset"} else "record",
        "mode": mode if mode in PRINT_MODES else "",
        "pages": snapshot.get("pages", 0),
        "count": len(snapshot.get("items") or []),
        "cursor": dict(snapshot.get("cursor") or {}),
        "print": dict(snapshot.get("print") or {}),
    }
    try:
        path = printed_history_path(vault)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(line, ensure_ascii=False) + "\n")
        return True
    except OSError as exc:
        try:
            from .log_utils import write_log
            write_log(vault, "board_printed_history_failed", {"board_id": line["board_id"], "error": str(exc)})
        except Exception:
            pass
        return False


def read_printed_history(vault: str, board_id: str = "", limit: int = 20) -> list:
    """按时间倒序读回纸面历史；``board_id`` 为空时不过滤。坏行跳过，不报错。"""
    path = printed_history_path(vault)
    if not os.path.isfile(path):
        return []
    target = str(board_id or "").strip()
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as file:
            for raw in file:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                if target and row.get("board_id") != target:
                    continue
                rows.append(row)
    except OSError:
        return []
    rows.reverse()
    return rows[:max(0, _int(limit, 20, 0, 1000))]


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
    _append_printed_history(vault, board, "record", mode)   # 先留存旧纸面，再覆盖
    board["printed"] = _normalize_printed(printed)
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def reset_printed(vault: str, board_id: str) -> dict:
    data = load_boards(vault)
    board = _find(data, board_id)
    _append_printed_history(vault, board, "reset")
    board["printed"] = copy.deepcopy(EMPTY_PRINTED)
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)
