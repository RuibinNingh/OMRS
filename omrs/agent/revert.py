"""按运行撤销（plan G1）：先 dry-run 列出计划与冲突，再执行。逆序撤回这次运行的 agent commit：
标记 / 元数据 / 正文还原到之前的版本，Session 撤回，反馈撤回，新建的题归档，移动移回，停用与恢复互逆。
之后有别的写入碰过同一道题或同一个 Session，或文件被改过而未入账，就整体拒绝并列出冲突，不做部分撤销。
每条逆操作另记一条 commit（payload 带 _revert），原记录保留。
"""
import os
import uuid

from ..actor import revert_marker
from ..content_history import (atomic_write, ensure_content_deletable, projection_row, question_file, read_question_file, record_file_change,
                               refresh_projection)
from ..common import QUESTIONS_DIR, parse_yaml_frontmatter
from ..ledger import append_commit, append_commit_in_db, blob_hash, connect, get_blob, read_commits
from ..path_safety import safe_question_directory
from ..question_ops import move_question, resume_question, suspend_question

SKIP_KEYS = {"question.content_snapshot", "question.content_backfill"}


def _keys(commit):
    p = commit["payload"] or {}
    keys = set()
    for qid in (p.get("question_id"), (p.get("question") or {}).get("question_id")):
        if qid:
            keys.add("q:" + qid)
    for sid in (p.get("session_id"), (p.get("session") or {}).get("session_id")):
        if sid:
            keys.add("s:" + sid)
    for f in p.get("feedbacks") or []:
        if f.get("question_id"):
            keys.add("q:" + f["question_id"])
    return keys


def _run_commits(commits, run_id):
    mine = [c for c in commits if (c["payload"].get("_agent") or {}).get("run_id") == run_id
            and not c["payload"].get("_revert")]
    reverted = {}
    for c in commits:
        marker = c["payload"].get("_revert") or {}
        if marker.get("run_id") == run_id and marker.get("commit_id"):
            reverted.setdefault(marker["commit_id"], []).append(c)
    return mine, reverted


def _completed(c, reverted):
    inverse = reverted.get(c["commit_id"], [])
    if c["commit_type"] == "review.batch_submit":
        indices = {x["payload"].get("target_review_index") for x in inverse
                   if x["commit_type"] == "review.retract" and x["payload"].get("target_commit_id") == c["commit_id"]}
        return bool(inverse) and len(indices) == len(c["payload"].get("feedbacks") or []), indices
    return bool(inverse), set()


def _undo_text(c):
    t, p = c["commit_type"], c["payload"]
    uid = p.get("uid_at_that_time") or (p.get("question") or {}).get("uid") or p.get("from_uid") or ""
    return {
        "question.metadata_update": f"把 {uid} 的标记 / 知识点改回之前的版本",
        "question.content_update": f"把 {uid} 的正文还原为之前的版本",
        "question.create": f"归档 {uid}（正文仍可从 Ledger 取回）",
        "question.move": f"把 {p.get('to_uid', '')} 移回 {p.get('from_uid', '')} 所在分类",
        "question.suspend": f"恢复 {uid}",
        "question.resume": f"重新停用 {uid}",
        "session.create": f"撤回 Session {(p.get('session') or {}).get('session_id', '')}",
        "session.complete": f"把 Session {p.get('session_id', '')} 改回进行中",
        "review.batch_submit": f"撤回这 {len(p.get('feedbacks') or [])} 条反馈",
    }.get(t, "")


def _label(vault, key):
    if key.startswith("s:"):
        return "Session " + key[2:]
    row = projection_row(vault, question_id=key[2:], include_archived=True)
    return row["uid"] if row else key[2:]


def plan_revert(vault, run_id):
    commits = read_commits(vault, ascending=True)
    mine, reverted = _run_commits(commits, run_id)
    if mine and all(_completed(c, reverted)[0] for c in mine):
        return {"ok": False, "already": True, "items": [], "conflicts": [], "msg": "这次运行已经撤销过"}
    seqs = {c["seq"] for c in mine}
    items, conflicts, seen = [], [], set()
    for c in reversed(mine):
        complete, done_indices = _completed(c, reverted)
        if complete:
            continue
        undo = _undo_text(c)
        if not undo:
            conflicts.append({"commit_id": c["commit_id"], "label": c["commit_type"], "by_commit_id": "",
                              "by_desc": "这类写入不支持撤销"})
            continue
        item = {"commit_id": c["commit_id"], "seq": c["seq"], "commit_type": c["commit_type"],
                "desc": c["message"], "undo": undo}
        if c["commit_type"] == "review.batch_submit":
            item["pending_review_indices"] = [i for i in range(len(c["payload"].get("feedbacks") or []))
                                              if i not in done_indices]
        items.append(item)
        for o in commits:
            if (o["seq"] <= c["seq"] or o["seq"] in seqs or o["commit_type"] in SKIP_KEYS
                    or (o["payload"].get("_revert") or {}).get("run_id") == run_id):
                continue
            common = _keys(c) & _keys(o)
            if common and (o["commit_id"], c["commit_id"]) not in seen:
                seen.add((o["commit_id"], c["commit_id"]))
                conflicts.append({"commit_id": c["commit_id"], "label": _label(vault, sorted(common)[0]),
                                  "by_commit_id": o["commit_id"], "by_desc": o["message"], "by_source": o["source"]})
    # 文件被改过但还没入账（例如刚在 Obsidian 里改）：同样拒绝
    latest = {}
    related = [c for c in commits if c["seq"] in seqs or (c["payload"].get("_revert") or {}).get("run_id") == run_id]
    for c in related:
        p = c["payload"]
        qid = p.get("question_id") or (p.get("question") or {}).get("question_id")
        h = p.get("after_hash") or (p.get("question") or {}).get("content_hash") or (p.get("after") or {}).get("content_hash")
        if qid and h:
            latest[qid] = h
    for qid, h in latest.items():
        row = projection_row(vault, question_id=qid)
        if not row:
            continue
        try:
            content = read_question_file(vault, row)
            now = blob_hash(content)
            identity = parse_yaml_frontmatter(content).get("_omrs_id")
        except (OSError, ValueError):
            now, identity = "", ""
        if (now != h or now != row.get("content_hash") or identity != qid) and not any(x["label"] == row["uid"] for x in conflicts):
            conflicts.append({"commit_id": "", "label": row["uid"], "by_commit_id": "", "by_desc": "文件之后被直接修改过"})
    for item in items:
        c = next(x for x in mine if x["commit_id"] == item["commit_id"])
        for key in _keys(c):
            if not key.startswith("q:") or key[2:] in latest:
                continue
            row = projection_row(vault, question_id=key[2:])
            if not row:
                continue
            try:
                content = read_question_file(vault, row)
                valid = (blob_hash(content) == row.get("content_hash")
                         and parse_yaml_frontmatter(content).get("_omrs_id") == row["question_id"])
            except (OSError, ValueError):
                valid = False
            if not valid and not any(x["label"] == row["uid"] for x in conflicts):
                conflicts.append({"commit_id": c["commit_id"], "label": row["uid"],
                                  "by_commit_id": "", "by_desc": "文件之后被直接修改过"})
    for item in items:
        c = next(x for x in mine if x["commit_id"] == item["commit_id"])
        p, typ = c["payload"], c["commit_type"]
        if typ in ("question.metadata_update", "question.content_update", "question.create", "question.move"):
            qid = p.get("question_id") or (p.get("question") or {}).get("question_id")
            row = projection_row(vault, question_id=qid)
            if row is not None:
                current = get_blob(vault, row.get("content_hash") or "")
                if (current is None or blob_hash(current) != row.get("content_hash")
                        or parse_yaml_frontmatter(current).get("_omrs_id") != qid):
                    conflicts.append({"commit_id": c["commit_id"], "label": row["uid"],
                                      "by_commit_id": "", "by_desc": "当前正文 blob 不可用或题目身份不匹配"})
        if typ in ("question.metadata_update", "question.content_update"):
            before = get_blob(vault, p.get("before_hash") or "")
            if (before is None or blob_hash(before) != p.get("before_hash")
                    or parse_yaml_frontmatter(before).get("_omrs_id") != p.get("question_id")):
                conflicts.append({"commit_id": c["commit_id"], "label": p.get("uid_at_that_time", ""),
                                  "by_commit_id": "", "by_desc": "旧版本正文不可用或题目身份不匹配"})
        if typ == "question.create":
            q = p["question"]
            row = projection_row(vault, question_id=q["question_id"])
            try:
                content = read_question_file(vault, row) if row else ""
            except (OSError, ValueError):
                content = ""
            if (not content or blob_hash(content) != row.get("content_hash")
                    or parse_yaml_frontmatter(content).get("_omrs_id") != q["question_id"]):
                conflicts.append({"commit_id": c["commit_id"], "label": q.get("uid", ""),
                                  "by_commit_id": "", "by_desc": "待归档文件缺失或题目身份不匹配"})
        if typ in ("question.move", "question.suspend", "question.resume"):
            row = projection_row(vault, question_id=p.get("question_id"))
            if row is None:
                conflicts.append({"commit_id": c["commit_id"], "label": p.get("uid_at_that_time", ""),
                                  "by_commit_id": "", "by_desc": "待撤销题目已不在活动题库"})
            if typ == "question.move" and row is not None:
                parts = p.get("from_path", "").replace("\\", "/").split("/")
                try:
                    if len(parts) != 4 or parts[0] != QUESTIONS_DIR or not parts[3].endswith(".md"):
                        raise ValueError("原路径格式不合法")
                    safe_question_directory(vault, parts[1], parts[2])
                    old_path = os.path.join(vault, *parts)
                    if os.path.exists(old_path) and os.path.realpath(old_path) != os.path.realpath(question_file(vault, row)):
                        with open(old_path, "r", encoding="utf-8") as file:
                            occupant_id = parse_yaml_frontmatter(file.read()).get("_omrs_id")
                        later_moved_ids = {other["payload"].get("question_id") for other in mine
                                           if other["seq"] > c["seq"] and other["commit_type"] == "question.move"
                                           and not _completed(other, reverted)[0]}
                        if occupant_id not in later_moved_ids:
                            raise ValueError("原路径已被其他文件占用")
                except ValueError as exc:
                    conflicts.append({"commit_id": c["commit_id"], "label": row["uid"],
                                      "by_commit_id": "", "by_desc": str(exc)})
    return {"ok": bool(items) and not conflicts, "already": False, "items": items, "conflicts": conflicts,
            "msg": "" if items else "这次运行没有写入"}


def apply_revert(vault, run_id):
    from ..locking import write_lock
    with write_lock():
        plan = plan_revert(vault, run_id)
        if not plan["ok"]:
            return plan
        by_id = {c["commit_id"]: c for c in read_commits(vault, ascending=True)}
        done = []
        try:
            for item in plan["items"]:
                current_plan = plan_revert(vault, run_id)
                if not current_plan["ok"] or item["commit_id"] not in {i["commit_id"] for i in current_plan["items"]}:
                    raise RuntimeError("撤销中检测到外部修改，已停止后续操作")
                c = by_id[item["commit_id"]]
                with revert_marker(run_id, c["commit_id"]):
                    before_seq = _head(vault)
                    _inverse(vault, c, run_id, pending_review_indices=item.get("pending_review_indices"))
                    done += [x["commit_id"] for x in read_commits(vault, ascending=True) if x["seq"] > before_seq]
                refresh_projection(vault)
        finally:
            refresh_projection(vault)
        mine, _ = _run_commits(read_commits(vault, ascending=True), run_id)
        return {**plan, "reverted": [c["commit_id"] for c in mine], "new_commits": done}


def _head(vault):
    rows = read_commits(vault, limit=1, ascending=False)
    return rows[0]["seq"] if rows else 0


def _inverse(vault, c, run_id, pending_review_indices=None):
    t, p = c["commit_type"], c["payload"]
    reason = f"撤销 AI 运行 {run_id}"
    if t in ("question.metadata_update", "question.content_update"):
        row = projection_row(vault, question_id=p["question_id"])
        before = get_blob(vault, p["before_hash"])
        if row is None or before is None or blob_hash(before) != p["before_hash"] or parse_yaml_frontmatter(before).get("_omrs_id") != row["question_id"]:
            raise RuntimeError(f"{c['commit_id']} 的旧版本正文不可用")
        current = read_question_file(vault, row)
        if blob_hash(current) != row.get("content_hash") or parse_yaml_frontmatter(current).get("_omrs_id") != row["question_id"]:
            raise RuntimeError("文件之后被直接修改过，已停止撤销")
        atomic_write(question_file(vault, row), before)
        try:
            record_file_change(vault, row, current, before, f"{reason}：还原 {row['uid']}")
        except BaseException:
            atomic_write(question_file(vault, row), current)
            raise
    elif t == "question.create":
        q = p["question"]
        row = projection_row(vault, question_id=q["question_id"])
        if row:
            path = question_file(vault, row)
            content = read_question_file(vault, row)
            if blob_hash(content) != row.get("content_hash"):
                raise RuntimeError("文件之后被直接修改过，已停止撤销")
            current_hash = ensure_content_deletable(vault, row, content, record_change=False)
            staged = f"{path}.omrs-revert-{uuid.uuid4().hex}"
            os.replace(path, staged)
            try:
                append_commit(vault, "api", "question.archive", f"{reason}：归档 {row['uid']}", {
                    "question_id": row["question_id"], "uid_at_that_time": row["uid"], "file_path": row["file_path"],
                    "reason": reason, "content_hash": current_hash})
            except BaseException:
                os.replace(staged, path)
                raise
            os.remove(staged)
    elif t == "question.move":
        row = projection_row(vault, question_id=p["question_id"])
        parts = p["from_path"].replace("\\", "/").split("/")
        move_question(vault, row["uid"], parts[1], parts[2])
    elif t == "question.suspend":
        row = projection_row(vault, question_id=p["question_id"])
        resume_question(vault, row["uid"], reason)
    elif t == "question.resume":
        row = projection_row(vault, question_id=p["question_id"])
        suspend_question(vault, row["uid"], reason)
    elif t == "session.create":
        sid = p["session"]["session_id"]
        append_commit(vault, "api", "session.retract", f"撤销 Session {sid}", {"session_id": sid, "reason": reason})
    elif t == "session.complete":
        append_commit(vault, "api", "session.restore", f"恢复 Session {p['session_id']}",
                      {"session_id": p["session_id"], "reason": reason})
    elif t == "review.batch_submit":
        indices = pending_review_indices if pending_review_indices is not None else range(len(p.get("feedbacks") or []))
        with connect(vault) as db:
            db.execute("BEGIN IMMEDIATE")
            for idx in indices:
                append_commit_in_db(db, "api", "review.retract", "撤销旧反馈", {
                    "target_commit_id": c["commit_id"], "target_review_index": idx, "reason": reason})
