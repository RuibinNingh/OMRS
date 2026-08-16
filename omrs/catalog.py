"""目录树：把 `错题/` 工作区扫成一棵可折叠的文件夹树，供前端「目录」页展示。

只读模块。不写 Ledger、不写投影、不改任何文件；`GET /api/tree` 每次直接走一遍磁盘。
题目的熟练度等结构化状态仍以投影为准，这里只负责「工作区里有哪些文件夹和文件」。
"""

import os

from .common import (
    FILE_PATTERN,
    MASTERY_HEADERS,
    OMRS_DIR,
    QUESTIONS_DIR,
    load_csv,
    mastery_path,
    questions_root,
)

# 目录树递归上限，防御性设置：正常题库不会有这么深的层级，
# 遇到异常符号链接或极端结构时避免无限递归撑爆响应。
MAX_DEPTH = 12

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


def _file_kind(name: str) -> str:
    """按文件名判断展示用的类别。question 只表示「符合题目命名规则的 md」。"""
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    if ext == ".md":
        return "question" if FILE_PATTERN.match(name) else "markdown"
    if ext in IMAGE_EXTS:
        return "image"
    return "other"


def _safe_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _walk(dir_path: str, vault: str, uid_map: dict, depth: int) -> dict:
    """递归构造一个文件夹节点。返回值里的 path 一律是相对 vault 的 POSIX 风格路径。"""
    rel = os.path.relpath(dir_path, vault).replace("\\", "/")
    node = {
        "name": os.path.basename(dir_path) or rel,
        "path": rel,
        "type": "dir",
        "children": [],
        "files": [],
        "question_count": 0,
        "file_count": 0,
        "size": 0,
        "truncated": False,
    }

    if depth >= MAX_DEPTH:
        node["truncated"] = True
        return node

    try:
        entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
    except OSError:
        return node

    for entry in entries:
        name = entry.name
        if name.startswith("."):
            # `.omrs/` 是结构化数据目录，不属于用户的题库目录结构。
            continue
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            continue

        if is_dir:
            child = _walk(entry.path, vault, uid_map, depth + 1)
            node["children"].append(child)
            node["question_count"] += child["question_count"]
            node["file_count"] += child["file_count"]
            node["size"] += child["size"]
            if child["truncated"]:
                node["truncated"] = True
            continue

        kind = _file_kind(name)
        size = _safe_size(entry.path)
        uid = os.path.splitext(name)[0] if kind == "question" else ""
        file_node = {
            "name": name,
            "path": os.path.relpath(entry.path, vault).replace("\\", "/"),
            "type": "file",
            "kind": kind,
            "size": size,
        }
        if uid:
            file_node["uid"] = uid
            # 在题库投影里的题目才可以直接打开详情；孤立 md 只列出来。
            file_node["indexed"] = uid in uid_map
            meta = uid_map.get(uid)
            if meta:
                file_node["subject"] = meta.get("Subject", "")
                file_node["category"] = meta.get("Category", "")
                file_node["tag"] = meta.get("Current_Tag", "")
            node["question_count"] += 1
        node["files"].append(file_node)
        node["file_count"] += 1
        node["size"] += size

    return node


def build_tree(vault: str) -> dict:
    """返回 `错题/` 的目录树，以及一份简单的汇总。

    未建立题库目录时返回一棵空树而不是报错，让前端可以正常提示「还没有题目」。
    """
    qroot = questions_root(vault)
    uid_map = {}
    for row in load_csv(mastery_path(vault), MASTERY_HEADERS):
        uid = (row.get("UID") or "").strip()
        if uid:
            uid_map[uid] = row

    if not os.path.isdir(qroot):
        empty = {
            "name": QUESTIONS_DIR,
            "path": QUESTIONS_DIR,
            "type": "dir",
            "children": [],
            "files": [],
            "question_count": 0,
            "file_count": 0,
            "size": 0,
            "truncated": False,
        }
        return {"root": empty, "summary": _summary(empty, 0), "indexed_total": len(uid_map)}

    tree = _walk(qroot, vault, uid_map, 0)
    orphan = _count_orphans(tree)
    return {
        "root": tree,
        "summary": _summary(tree, orphan),
        "indexed_total": len(uid_map),
        "data_dir": f"{QUESTIONS_DIR}/{OMRS_DIR}",
    }


def _count_orphans(node: dict) -> int:
    """统计磁盘上有、但题库投影里没有的题目文件（通常是刚放进来还没扫描）。"""
    count = sum(
        1
        for f in node.get("files", [])
        if f.get("kind") == "question" and not f.get("indexed", False)
    )
    for child in node.get("children", []):
        count += _count_orphans(child)
    return count


def _summary(node: dict, orphan: int) -> dict:
    def count_dirs(n):
        return len(n.get("children", [])) + sum(count_dirs(c) for c in n.get("children", []))

    return {
        "dirs": count_dirs(node),
        "files": node.get("file_count", 0),
        "questions": node.get("question_count", 0),
        "size": node.get("size", 0),
        "orphans": orphan,
        "truncated": node.get("truncated", False),
    }
