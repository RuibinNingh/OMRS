"""展示板持久化与题目引用解析。

展示板是呈现层数据，不进入 Ledger。文件只保存题目的稳定
``question_id`` 与当前 ``uid`` 快照；读取时优先使用 question_id，以便题目
改名或迁移分类后仍能命中。
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import uuid

from .common import MASTERY_HEADERS, load_csv, mastery_path, omrs_data_dir
from .ledger import connect


BOARDS_FILENAME = "boards.json"
BOARDS_VERSION = 1
DEFAULT_PRINT = {
    "note_ratio": 0.42,
    "gap_lines": 6,
    "binding_mm": 22,
    "binding_marks": "none",
    "answers": "none",
    "show_labels": True,
    "show_meta": True,
}


def boards_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), BOARDS_FILENAME)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _clean_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        raise ValueError("展示板名称不能为空")
    return value[:120]


def _normalize_print(value: dict | None) -> dict:
    result = dict(DEFAULT_PRINT)
    if isinstance(value, dict):
        result.update({key: value[key] for key in DEFAULT_PRINT if key in value})
    try:
        result["note_ratio"] = max(0.30, min(0.55, float(result["note_ratio"])))
    except (TypeError, ValueError):
        result["note_ratio"] = DEFAULT_PRINT["note_ratio"]
    try:
        result["gap_lines"] = max(0, min(24, int(result["gap_lines"])))
    except (TypeError, ValueError):
        result["gap_lines"] = DEFAULT_PRINT["gap_lines"]
    try:
        result["binding_mm"] = max(10, min(40, int(result["binding_mm"])))
    except (TypeError, ValueError):
        result["binding_mm"] = DEFAULT_PRINT["binding_mm"]
    if result["binding_marks"] not in {"none", "3hole", "26hole"}:
        result["binding_marks"] = "none"
    if result["answers"] not in {"none", "append"}:
        result["answers"] = "none"
    result["show_labels"] = bool(result["show_labels"])
    result["show_meta"] = bool(result["show_meta"])
    return result


def _normalize_item(item: dict) -> dict:
    item = item if isinstance(item, dict) else {}
    try:
        extra_gap_lines = max(0, min(24, int(item.get("extra_gap_lines", 0) or 0)))
    except (TypeError, ValueError):
        extra_gap_lines = 0
    return {
        "question_id": str(item.get("question_id") or "").strip(),
        "uid": str(item.get("uid") or "").strip(),
        "added_at": str(item.get("added_at") or _now()),
        "extra_gap_lines": extra_gap_lines,
        "pin": bool(item.get("pin", False)),
    }


def _normalize_board(board: dict) -> dict:
    board = board if isinstance(board, dict) else {}
    created = str(board.get("created_at") or _now())
    items = []
    seen = set()
    for raw in board.get("items") or []:
        item = _normalize_item(raw)
        key = item["question_id"] or f"uid:{item['uid']}"
        if not item["uid"] and not item["question_id"]:
            continue
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    try:
        last_printed_page = max(0, int(board.get("last_printed_page", 0) or 0))
    except (TypeError, ValueError):
        last_printed_page = 0
    return {
        "id": str(board.get("id") or "").strip(),
        "name": str(board.get("name") or "未命名展示板").strip()[:120],
        "note": str(board.get("note") or ""),
        "created_at": created,
        "updated_at": str(board.get("updated_at") or created),
        "source_labels": list(dict.fromkeys(str(x).strip() for x in (board.get("source_labels") or []) if str(x).strip())),
        "print": _normalize_print(board.get("print")),
        "last_printed_page": last_printed_page,
        "items": items,
    }


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
    return {"version": BOARDS_VERSION, "boards": boards}


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
    if os.path.isfile(path):
        _rotate(path)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
    return normalized


def _projection_maps(vault: str) -> tuple[dict, dict]:
    by_id, by_uid = {}, {}
    with connect(vault) as db:
        for row in db.execute("SELECT * FROM question_projection"):
            record = dict(row)
            if record.get("archived"):
                continue
            by_id[record["question_id"]] = record
            by_uid[record["uid"]] = record
    # Tests and very old vaults may have CSV before the projection is built.
    for row in load_csv(mastery_path(vault), MASTERY_HEADERS):
        uid = row.get("UID", "")
        if uid and uid not in by_uid:
            by_uid[uid] = {
                "question_id": row.get("question_id", ""),
                "uid": uid,
                "subject": row.get("Subject", ""),
                "category": row.get("Category", ""),
                "difficulty": row.get("Difficulty", 5),
                "suspended": str(row.get("Suspended", "")).lower() in {"1", "true", "yes"},
                "archived": 0,
                "file_path": row.get("File_Path", ""),
            }
    return by_id, by_uid


def _item_detail(vault: str, item: dict, by_id: dict, by_uid: dict) -> dict:
    record = by_id.get(item.get("question_id")) if item.get("question_id") else None
    record = record or by_uid.get(item.get("uid"))
    if not record:
        return {
            **item,
            "missing": True,
            "suspended": False,
            "subject": "",
            "category": "",
            "difficulty": "",
            "mastery": 0,
            "due_date": "",
            "labels": [],
        }
    row = next(
        (r for r in load_csv(mastery_path(vault), MASTERY_HEADERS)
         if r.get("UID") == record.get("uid")
         or (record.get("question_id") and r.get("question_id") == record.get("question_id"))),
        {},
    )
    labels = [x for x in str(row.get("Labels", "") or "").split("|") if x]
    return {
        **item,
        "question_id": record.get("question_id") or item.get("question_id", ""),
        "uid": record.get("uid") or item.get("uid", ""),
        "file_path": record.get("file_path", ""),
        "missing": False,
        "suspended": bool(record.get("suspended")) or str(row.get("Suspended", "")).lower() in {"1", "true", "yes"},
        "subject": record.get("subject", row.get("Subject", "")),
        "category": record.get("category", row.get("Category", "")),
        "difficulty": record.get("difficulty", row.get("Difficulty", "")),
        "mastery": float(row.get("Mastery", 0) or 0),
        "due_date": row.get("Due_Date", ""),
        "labels": labels,
    }


def list_boards(vault: str) -> list[dict]:
    data = load_boards(vault)
    by_id, by_uid = _projection_maps(vault)
    result = []
    for board in data["boards"]:
        details = [_item_detail(vault, item, by_id, by_uid) for item in board["items"]]
        result.append({
            "id": board["id"],
            "name": board["name"],
            "note": board["note"],
            "count": len(details),
            "updated_at": board["updated_at"],
            "created_at": board["created_at"],
            "print": board["print"],
            "last_printed_page": board["last_printed_page"],
            "missing": sum(1 for item in details if item["missing"]),
            "suspended": sum(1 for item in details if item["suspended"]),
        })
    return result


def get_board(vault: str, board_id: str) -> dict | None:
    data = load_boards(vault)
    board = next((board for board in data["boards"] if board["id"] == str(board_id or "").strip()), None)
    if not board:
        return None
    by_id, by_uid = _projection_maps(vault)
    return {
        **copy.deepcopy(board),
        "items": [_item_detail(vault, item, by_id, by_uid) for item in board["items"]],
    }


def _new_id() -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return f"BD-{stamp}-{uuid.uuid4().hex[:6]}"


def create_board(vault: str, name: str, uids=None, label: str = "") -> dict:
    data = load_boards(vault)
    by_id, by_uid = _projection_maps(vault)
    now = _now()
    items = []
    for uid in uids or []:
        record = by_uid.get(str(uid).strip())
        if not record:
            continue
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
    board = next((board for board in data["boards"] if board["id"] == board_id), None)
    if not board:
        raise ValueError(f"展示板不存在: {board_id}")
    if "name" in changes and changes["name"] is not None:
        board["name"] = _clean_name(changes["name"])
    if "note" in changes and changes["note"] is not None:
        board["note"] = str(changes["note"])
    if "source_labels" in changes and changes["source_labels"] is not None:
        raw = changes["source_labels"]
        if isinstance(raw, str):
            raw = [raw]
        board["source_labels"] = list(dict.fromkeys(
            str(value).strip() for value in (raw or []) if str(value).strip()
        ))
    if "print" in changes and isinstance(changes["print"], dict):
        board["print"] = _normalize_print({**board.get("print", {}), **changes["print"]})
    if "last_printed_page" in changes and changes["last_printed_page"] is not None:
        board["last_printed_page"] = max(0, int(changes["last_printed_page"]))
    if "items" in changes and changes["items"] is not None:
        board["items"] = [
            _normalize_item(item)
            for item in (changes["items"] or [])
        ]
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def add_items(vault: str, board_id: str, uids, position=None) -> dict:
    data = load_boards(vault)
    board = next((board for board in data["boards"] if board["id"] == board_id), None)
    if not board:
        raise ValueError(f"展示板不存在: {board_id}")
    _, by_uid = _projection_maps(vault)
    existing_ids = {item.get("question_id") for item in board["items"] if item.get("question_id")}
    existing_uids = {item.get("uid") for item in board["items"] if item.get("uid")}
    added = []
    for raw_uid in uids or []:
        uid = str(raw_uid or "").strip()
        record = by_uid.get(uid)
        if not record:
            continue
        question_id = record.get("question_id") or ""
        if uid in existing_uids or (question_id and question_id in existing_ids):
            continue
        entry = {"question_id": record.get("question_id", ""), "uid": uid, "added_at": _now()}
        if question_id:
            existing_ids.add(question_id)
        existing_uids.add(uid)
        added.append(entry)
    at = len(board["items"]) if position in (None, "") else max(0, min(len(board["items"]), int(position)))
    board["items"][at:at] = added
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def remove_items(vault: str, board_id: str, uids) -> dict:
    data = load_boards(vault)
    board = next((board for board in data["boards"] if board["id"] == board_id), None)
    if not board:
        raise ValueError(f"展示板不存在: {board_id}")
    remove = {str(uid or "").strip() for uid in uids or []}
    board["items"] = [
        item for item in board["items"]
        if item.get("uid") not in remove and item.get("question_id") not in remove
    ]
    board["updated_at"] = _now()
    save_boards(vault, data)
    return get_board(vault, board_id)


def duplicate_board(vault: str, board_id: str, name: str) -> dict:
    source = get_board(vault, board_id)
    if not source:
        raise ValueError(f"展示板不存在: {board_id}")
    data = load_boards(vault)
    now = _now()
    clone = _normalize_board({
        "id": _new_id(),
        "name": _clean_name(name),
        "note": source.get("note", ""),
        "created_at": now,
        "updated_at": now,
        "source_labels": source.get("source_labels", []),
        "print": source.get("print", DEFAULT_PRINT),
        "last_printed_page": 0,
        "items": [item for item in source.get("items", []) if not item.get("missing")],
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


def board_items_for_export(vault: str, board_id: str) -> tuple[dict, list[dict]]:
    board = get_board(vault, board_id)
    if not board:
        raise ValueError(f"展示板不存在: {board_id}")
    questions = []
    for item in board["items"]:
        if item["missing"] or item["suspended"]:
            continue
        questions.append(item)
    return board, questions
