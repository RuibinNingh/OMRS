import datetime
import hashlib
import json
import os
import re
import threading

from .common import (
    FILE_PATTERN,
    extract_category,
    extract_knowledge_tags,
    extract_labels,
    extract_tag,
    parse_yaml_frontmatter,
    questions_root,
)
from .ledger import append_commit, canonical_json, connect, reserve_operation_id
from .vault_lifecycle import storage


_SCAN_LOCK = threading.Lock()
_SCHEDULER_LOCK = threading.RLock()


def metadata_hash(meta: dict) -> str:
    structured = {
        "_omrs_id": meta.get("_omrs_id", ""),
        "科目": meta.get("科目", ""),
        "分类": extract_category(meta),
        "难度": str(meta.get("难度", "")),
        "页码": str(meta.get("页码", "")),
        "相关知识点": extract_knowledge_tags(meta),
        "标记": extract_labels(meta),
        "tags": meta.get("tags", []),
    }
    return hashlib.sha256(canonical_json(structured).encode("utf-8")).hexdigest()


def content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


@storage
def scan_question_files(vault: str) -> list:
    qroot = questions_root(vault)
    if not os.path.isdir(qroot):
        os.makedirs(qroot, exist_ok=True)
        return []
    results = []
    for root, dirs, files in os.walk(qroot):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for fname in files:
            if not FILE_PATTERN.match(fname):
                continue
            fullpath = os.path.join(root, fname)
            with open(fullpath, "r", encoding="utf-8") as file:
                content = file.read()
            relpath = os.path.relpath(fullpath, vault)
            subject, category = _infer_subject_category(vault, fullpath)
            results.append({
                "uid": os.path.splitext(fname)[0],
                "file_path": relpath,
                "full_path": fullpath,
                "subject": subject,
                "category": category,
                "content": content,
                "meta": parse_yaml_frontmatter(content),
            })
    return results


@storage
def scan_workspace(vault: str):
    from .locking import write_lock

    # 锁顺序：写锁在外，_SCAN_LOCK 在内（_SCAN_LOCK 只防扫描重入，不排队重复扫描）
    with write_lock():
        if not _SCAN_LOCK.acquire(blocking=False):
            return {"status": "busy", "changes": 0, "conflicts": []}
        try:
            return _scan_workspace_locked(vault)
        except Exception as exc:
            _write_scan_status(vault, 0, [str(exc)], str(exc))
            raise
        finally:
            _SCAN_LOCK.release()


def _scan_workspace_locked(vault: str):
    files = scan_question_files(vault)
    try:
        from .inbox_commit import pending_question_ids
        pending_ids = set(pending_question_ids(vault))
    except ImportError:
        pending_ids = set()
    files = [item for item in files if item["meta"].get("_omrs_id") not in pending_ids]
    conflicts = _detect_conflicts(files)
    changes = []
    if conflicts:
        _write_scan_status(vault, 0, conflicts, "")
        return {"status": "conflict", "changes": 0, "conflicts": conflicts}

    with connect(vault) as db:
        fingerprints = {
            row["question_id"]: dict(row)
            for row in db.execute("SELECT * FROM workspace_fingerprint").fetchall()
            if row["question_id"]
        }
        projection = {
            row["question_id"]: dict(row)
            for row in db.execute("SELECT * FROM question_projection").fetchall()
        }

    # 先核对全部已知文件，再追加任何扫描提交；否则一个冲突题可能在扫描中
    # 被更新为新哈希，使当前缺失的旧正文只能作为历史缺口被发现。
    from .content_history import ContentConflict, check_content_reconcile
    blocked_ids = set()
    for item in files:
        question_id = item["meta"].get("_omrs_id")
        row = projection.get(question_id)
        if not row:
            continue
        try:
            check_content_reconcile(vault, row, item["content"])
        except ContentConflict as exc:
            blocked_ids.add(question_id)
            conflicts.append(f"{item['uid']}：{exc}")

    seen_ids = set(pending_ids)
    known_ids = set(projection) | {item["meta"].get("_omrs_id") for item in files if item["meta"].get("_omrs_id")}
    for item in files:
        meta = item["meta"]
        question_id = meta.get("_omrs_id")
        if question_id in blocked_ids:
            seen_ids.add(question_id)
            continue
        is_new = not question_id
        if not question_id:
            question_id = reserve_operation_id(vault)
            while question_id in known_ids:
                question_id = reserve_operation_id(vault)
            known_ids.add(question_id)
            item["content"] = _inject_omrs_id(item["content"], question_id)
            _atomic_write_text(item["full_path"], item["content"])
            item["meta"] = parse_yaml_frontmatter(item["content"])
            meta = item["meta"]
        if is_new or (question_id not in fingerprints and question_id not in projection):
            append_commit(vault, "self_check", "question.create_external", "检测到外部新增题目", {
                "question": _question_payload(item, question_id),
            }, blobs=[item["content"]])
            changes.append({"type": "question.create_external", "uid": item["uid"]})
        seen_ids.add(question_id)

        mh = metadata_hash(meta)
        ch = content_hash(item["content"])
        old = fingerprints.get(question_id)
        current = projection.get(question_id)
        if not old:
            continue
        if old["file_path"] != item["file_path"] or old["uid"] != item["uid"]:
            append_commit(vault, "self_check", "question.move_external", "检测到人工改名或移动", {
                "question_id": question_id,
                "from_uid": old["uid"],
                "from_category": (current or {}).get("category", ""),
                "to_uid": item["uid"],
                "from_path": old["file_path"],
                "to_path": item["file_path"],
                "to_category": extract_category(meta) or item["category"],
            })
            changes.append({"type": "question.move_external", "uid": item["uid"]})
        if old["metadata_hash"] != mh:
            append_commit(vault, "self_check", "question.metadata_update_external", "检测到人工修改结构化字段", {
                "question_id": question_id,
                "uid_at_that_time": item["uid"],
                "before": _projection_to_question(current or {}),
                "after": _question_payload(item, question_id),
            }, blobs=[item["content"]])
            changes.append({"type": "question.metadata_update_external", "uid": item["uid"]})
        elif old["content_hash"] != ch:
            # 只改了正文（例如在 Obsidian 里编辑）：记一笔 question.content_update，正文进 blobs
            append_commit(vault, "self_check", "question.content_update", "检测到人工修改正文", {
                "question_id": question_id,
                "uid_at_that_time": item["uid"],
                "before_hash": old["content_hash"],
                "after_hash": ch,
            }, blobs=[item["content"]])
            changes.append({"type": "content_only", "uid": item["uid"]})

    for question_id, old in fingerprints.items():
        if question_id in seen_ids:
            continue
        append_commit(vault, "self_check", "question.archive_external", "检测到 Markdown 文件消失", {
            "question_id": question_id,
            "uid_at_that_time": old["uid"],
            "file_path": old["file_path"],
        })
        changes.append({"type": "question.archive_external", "uid": old["uid"]})

    from .projections import rebuild_projection

    state = rebuild_projection(vault)
    update_fingerprints(vault, [
        _question_to_fingerprint_payload(q) for q in state["questions"].values()
        if not q.get("archived")
    ])
    _write_scan_status(vault, len([c for c in changes if c["type"] != "content_only"]), conflicts, "")
    return {"status": "conflict" if conflicts else "ok", "changes": len(changes), "conflicts": conflicts}


@storage
def update_fingerprints(vault: str, questions: list):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with connect(vault) as db:
        db.execute("DELETE FROM workspace_fingerprint")
        for question in questions:
            if not question.get("file_path"):
                continue
            db.execute(
                """
                INSERT OR REPLACE INTO workspace_fingerprint
                (file_path, question_id, uid, metadata_hash, content_hash, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    question.get("file_path", ""),
                    question.get("question_id", ""),
                    question.get("uid", ""),
                    question.get("metadata_hash", ""),
                    question.get("content_hash", ""),
                    now,
                ),
            )
        db.commit()


def get_scan_status(vault: str):
    with connect(vault) as db:
        row = db.execute("SELECT * FROM workspace_scan_status WHERE id = 1").fetchone()
    if not row:
        return {"last_scan_at": "", "change_count": 0, "conflict_count": 0, "conflicts": []}
    return {
        "last_scan_at": row["last_scan_at"] or "",
        "change_count": row["change_count"],
        "conflict_count": row["conflict_count"],
        "conflicts": json.loads(row["conflicts_json"] or "[]"),
        "last_error": row["last_error"] or "",
    }


def start_workspace_scanner(vault: str, interval_seconds=600):
    from .vault_lifecycle import generation, task, VaultChanged
    with _SCHEDULER_LOCK:
        existing = getattr(start_workspace_scanner, "_thread", None)
        if existing and existing.is_alive():
            return
        stop = threading.Event()
        epoch = generation(vault)

        def _loop():
            try:
                with task(vault, epoch):
                    while not stop.is_set():
                        try:
                            scan_workspace(vault)
                        except VaultChanged:
                            return
                        except Exception:
                            pass
                        if stop.wait(interval_seconds):
                            return
            except VaultChanged:
                return

        thread = threading.Thread(target=_loop, name="omrs-workspace-scan", daemon=True)
        start_workspace_scanner._stop = stop
        start_workspace_scanner._thread = thread
        thread.start()


def stop_workspace_scanner():
    # 恢复屏障内不能 join：旧线程可能正等待租约。独立 stop 和世代令其自行退出。
    with _SCHEDULER_LOCK:
        stop = getattr(start_workspace_scanner, "_stop", None)
        if stop:
            stop.set()
        start_workspace_scanner._thread = None


def _write_scan_status(vault, change_count, conflicts, error):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with connect(vault) as db:
        db.execute(
            """
            INSERT OR REPLACE INTO workspace_scan_status
            (id, last_scan_at, change_count, conflict_count, conflicts_json, last_error)
            VALUES (1, ?, ?, ?, ?, ?)
            """,
            (now, int(change_count), len(conflicts), json.dumps(conflicts, ensure_ascii=False), error or ""),
        )
        db.commit()


def _detect_conflicts(files):
    conflicts = []
    by_uid = {}
    by_id = {}
    for item in files:
        by_uid.setdefault(item["uid"], []).append(item["file_path"])
        qid = item["meta"].get("_omrs_id")
        if qid:
            by_id.setdefault(qid, []).append(item["file_path"])
    for uid, paths in by_uid.items():
        if len(paths) > 1:
            conflicts.append(f"重复 UID {uid}: " + " | ".join(paths))
    for qid, paths in by_id.items():
        if len(paths) > 1:
            conflicts.append(f"重复 _omrs_id {qid}: " + " | ".join(paths))
    return conflicts


def _infer_subject_category(vault, fullpath):
    rel = os.path.relpath(fullpath, questions_root(vault))
    parts = rel.split(os.sep)
    subject = parts[0] if len(parts) >= 2 else ""
    category = parts[1] if len(parts) >= 3 else ""
    return subject, category


def _inject_omrs_id(content, question_id):
    match = re.match(r"^(---\s*\n)(.*?)(\n---)", content, re.DOTALL)
    if match:
        body = match.group(2)
        if "_omrs_id:" in body:
            body = re.sub(r"^_omrs_id:.*$", f"_omrs_id: {question_id}", body, flags=re.MULTILINE)
        else:
            body = f"_omrs_id: {question_id}\n{body}"
        return f"{match.group(1)}{body}{match.group(3)}{content[match.end(3):]}"
    return f"---\n_omrs_id: {question_id}\n相关知识点: []\ntags:\n  - 状态/待攻克\n---\n\n{content}"


def _question_payload(item, question_id):
    meta = item["meta"]
    return {
        "question_id": question_id,
        "uid": item["uid"],
        "file_path": item["file_path"],
        "subject": meta.get("科目", item["subject"]),
        "category": extract_category(meta) or item["category"],
        "difficulty": meta.get("难度", "5"),
        "current_tag": extract_tag(meta),
        "knowledge_tags": extract_knowledge_tags(meta),
        "labels": extract_labels(meta),
        "metadata": meta,
        "metadata_hash": metadata_hash(meta),
        "content_hash": content_hash(item["content"]),
        "archived": False,
    }


def _projection_to_question(row):
    if not row:
        return {}
    return {
        "question_id": row.get("question_id", ""),
        "uid": row.get("uid", ""),
        "file_path": row.get("file_path", ""),
        "subject": row.get("subject", ""),
        "category": row.get("category", ""),
        "difficulty": row.get("difficulty", 5),
        "current_tag": row.get("current_tag", ""),
        "labels": [value.strip() for value in str(row.get("labels", "") or "").split("|") if value.strip()],
    }


def _question_to_fingerprint_payload(question):
    return {
        "question_id": question.get("question_id", ""),
        "uid": question.get("uid", ""),
        "file_path": question.get("file_path", ""),
        "metadata_hash": question.get("metadata_hash", ""),
        "content_hash": question.get("content_hash", ""),
    }


def _atomic_write_text(path, content):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
