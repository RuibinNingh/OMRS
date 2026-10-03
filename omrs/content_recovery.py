"""从已核验的本机副本补回历史正文；默认预览，不还原当前 Markdown。"""
import json
import os
import re
import sqlite3
from pathlib import Path

from .common import OMRS_DIR, parse_yaml_frontmatter, questions_root
from .data_repository import storage_write
from .ledger import (append_commit_in_db, blob_hash, compute_commit_hash,
                     content_ref_pairs)
from .vault_lifecycle import open_sqlite

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_CONTENT_BYTES = 16 * 1024 * 1024
MAX_ITEMS = 100


def load_recovery_manifest(filename):
    """清单和正文在进入写锁前读取；相对路径仅指向清单目录内的普通文件。"""
    path = Path(filename).absolute()
    with path.open("rb") as file:
        data = file.read(MAX_MANIFEST_BYTES + 1)
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("正文补回清单超过 2 MiB")
    manifest = json.loads(data.decode("utf-8"))
    if (not isinstance(manifest, dict) or type(manifest.get("version")) is not int
            or manifest["version"] != 1 or not isinstance(manifest.get("items"), list)
            or not 1 <= len(manifest["items"]) <= MAX_ITEMS):
        raise ValueError("正文补回清单必须为 version:1，包含 1–100 个 items")
    items, hashes, total = [], set(), 0
    base = path.parent.resolve()
    for raw in manifest["items"]:
        if not isinstance(raw, dict):
            raise ValueError("正文补回条目必须为对象")
        qid, digest, seq = raw.get("question_id"), raw.get("hash"), raw.get("first_referenced_seq")
        if (not isinstance(qid, str) or not re.fullmatch(r"OP-[0-9]+", qid)
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or type(seq) is not int or seq < 1 or digest in hashes):
            raise ValueError("正文补回条目的身份、哈希、原始序号非法或重复")
        filename = raw.get("file")
        if not isinstance(filename, str) or not filename or Path(filename).is_absolute():
            raise ValueError("正文文件必须使用相对于清单目录的路径")
        content_path = base / filename
        if (not content_path.resolve().is_relative_to(base)
                or any(part.is_symlink() for part in (content_path, *content_path.parents)
                       if part.is_relative_to(base)) or not content_path.is_file()):
            raise ValueError("正文文件必须是清单目录内的普通文件，不接受符号链接")
        with content_path.open("rb") as file:
            body = file.read(MAX_CONTENT_BYTES + 1)
        total += len(body)
        if total > MAX_CONTENT_BYTES:
            raise ValueError("本批正文超过 16 MiB，请分批补回")
        # 与历史 Markdown 文本读取一致，只转换通用换行，不改写其他正文。
        content = body.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if blob_hash(content) != digest or parse_yaml_frontmatter(content).get("_omrs_id") != qid:
            raise ValueError("候选正文哈希或题目身份不匹配，已拒绝整批补回")
        items.append({"question_id": qid, "content_hash": digest,
                      "first_referenced_seq": seq, "content": content})
        hashes.add(digest)
    return items, blob_hash(data.decode("utf-8"))


@storage_write
def recover_content(vault, items, manifest_hash, apply=False):
    """原事实、候选正文和已有 blob 全部一致才提交；故障与重试不产生半批数据。"""
    from .backup_store import recover_restore
    recover_restore(vault, allow_recovery=False)
    if type(apply) is not bool or not re.fullmatch(r"[0-9a-f]{64}", manifest_hash):
        raise ValueError("补回参数不合法")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError("正文补回必须包含 1–100 个条目")
    path = Path(os.path.join(questions_root(vault), OMRS_DIR, "ledger.db")).absolute()
    if not path.is_file():
        raise FileNotFoundError("ledger.db 不存在，正文补回不会建库或迁移旧库")
    with open_sqlite(vault, path.as_uri() + ("?mode=rw" if apply else "?mode=ro"), uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        # 不使用会初始化 Schema 的 connect；只接受具有正文引用索引的现有库。
        db.execute("SELECT question_id,content_hash,first_seq FROM content_version_refs LIMIT 0")
        missing, existing, seen = [], [], set()
        for item in items:
            qid, digest, seq, content = (item.get(k) for k in
                                       ("question_id", "content_hash", "first_referenced_seq", "content"))
            if (not isinstance(qid, str) or not isinstance(content, str)
                    or type(seq) is not int or seq < 1 or not isinstance(digest, str)
                    or digest in seen or blob_hash(content) != digest
                    or parse_yaml_frontmatter(content).get("_omrs_id") != qid):
                raise ValueError("候选正文哈希或题目身份不匹配，已拒绝整批补回")
            seen.add(digest)
            fact = db.execute("SELECT * FROM commits WHERE seq=?", (seq,)).fetchone()
            if fact is None:
                raise ValueError("找不到清单指定的原始提交")
            payload = json.loads(fact["payload_json"])
            if compute_commit_hash(fact["prev_hash"], fact["created_at"], fact["source"],
                                   fact["commit_type"], payload) != fact["commit_hash"]:
                raise ValueError("原始提交哈希损坏，已拒绝补回")
            if (qid, digest) not in content_ref_pairs(fact["commit_type"], payload):
                raise ValueError("原始提交没有引用此题的正文哈希，已拒绝补回")
            indexed = db.execute("SELECT first_seq FROM content_version_refs WHERE question_id=? AND content_hash=?",
                                 (qid, digest)).fetchone()
            if indexed is None or indexed["first_seq"] != seq:
                raise ValueError("正文引用索引与原始提交不一致，须先核查索引")
            saved = db.execute("SELECT content FROM blobs WHERE hash=?", (digest,)).fetchone()
            if saved is not None:
                if saved["content"] != content:
                    raise ValueError("已有正文 blob 损坏，补回不会覆盖它")
                existing.append(digest)
            else:
                missing.append(item)
        commit = None
        if apply and missing:
            commit = append_commit_in_db(db, "migration", "question.content_backfill",
                f"从核验副本补回 {len(missing)} 个历史正文版本", {
                    "historical": True, "manifest_hash": manifest_hash,
                    "items": [{k: v for k, v in item.items() if k != "content"} for item in missing],
                }, blobs=[item["content"] for item in missing])
    return {"status": "ok", "applied": apply, "recovered": len(missing) if apply else 0,
            "recoverable": len(missing), "already_present": len(existing),
            "manifest_hash": manifest_hash, "commit": commit}
