"""按运行撤销（plan G1）：先 dry-run 列出计划与冲突，再执行。逆序撤回这次运行的 agent commit：
标记 / 元数据 / 正文还原到之前的版本，Session 撤回，反馈撤回，新建的题归档，移动移回，停用与恢复互逆。
之后有别的写入碰过同一道题或同一个 Session，或文件被改过而未入账，就整体拒绝并列出冲突，不做部分撤销。
每条逆操作另记一条 commit（payload 带 _revert），原记录保留。
"""
import os

from ..actor import revert_marker
from ..content_history import (atomic_write, projection_row, question_file, read_question_file, record_file_change,
                               refresh_projection)
from ..ledger import append_commit, blob_hash, get_blob, read_commits
from ..question_ops import move_question, resume_question, suspend_question

SKIP_KEYS = {"question.content_snapshot"}


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
    mine = [c for c in commits if (c["payload"].get("_agent") or {}).get("run_id") == run_id]
    reverted = any((c["payload"].get("_revert") or {}).get("run_id") == run_id for c in commits)
    return mine, reverted


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
    if reverted:
        return {"ok": False, "already": True, "items": [], "conflicts": [], "msg": "这次运行已经撤销过"}
    seqs = {c["seq"] for c in mine}
    items, conflicts, seen = [], [], set()
    for c in reversed(mine):
        undo = _undo_text(c)
        if not undo:
            conflicts.append({"commit_id": c["commit_id"], "label": c["commit_type"], "by_commit_id": "",
                              "by_desc": "这类写入不支持撤销"})
            continue
        items.append({"commit_id": c["commit_id"], "seq": c["seq"], "commit_type": c["commit_type"],
                      "desc": c["message"], "undo": undo})
        for o in commits:
            if o["seq"] <= c["seq"] or o["seq"] in seqs or o["commit_type"] in SKIP_KEYS:
                continue
            common = _keys(c) & _keys(o)
            if common and (o["commit_id"], c["commit_id"]) not in seen:
                seen.add((o["commit_id"], c["commit_id"]))
                conflicts.append({"commit_id": c["commit_id"], "label": _label(vault, sorted(common)[0]),
                                  "by_commit_id": o["commit_id"], "by_desc": o["message"], "by_source": o["source"]})
    # 文件被改过但还没入账（例如刚在 Obsidian 里改）：同样拒绝
    latest = {}
    for c in mine:
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
            now = blob_hash(read_question_file(vault, row))
        except OSError:
            continue
        if now != h and not any(x["label"] == row["uid"] for x in conflicts):
            conflicts.append({"commit_id": "", "label": row["uid"], "by_commit_id": "", "by_desc": "文件之后被直接修改过"})
    return {"ok": bool(items) and not conflicts, "already": False, "items": items, "conflicts": conflicts,
            "msg": "" if items else "这次运行没有写入"}


def apply_revert(vault, run_id):
    plan = plan_revert(vault, run_id)
    if not plan["ok"]:
        return plan
    by_id = {c["commit_id"]: c for c in read_commits(vault, ascending=True)}
    done = []
    for item in plan["items"]:
        c = by_id[item["commit_id"]]
        with revert_marker(run_id, c["commit_id"]):
            before_seq = _head(vault)
            _inverse(vault, c, run_id)
            done += [x["commit_id"] for x in read_commits(vault, ascending=True) if x["seq"] > before_seq]
    refresh_projection(vault)
    return {**plan, "reverted": [i["commit_id"] for i in plan["items"]], "new_commits": done}


def _head(vault):
    rows = read_commits(vault, limit=1, ascending=False)
    return rows[0]["seq"] if rows else 0


def _inverse(vault, c, run_id):
    t, p = c["commit_type"], c["payload"]
    reason = f"撤销 AI 运行 {run_id}"
    if t in ("question.metadata_update", "question.content_update"):
        row = projection_row(vault, question_id=p["question_id"])
        before = get_blob(vault, p["before_hash"])
        if row is None or before is None:
            raise RuntimeError(f"{c['commit_id']} 的旧版本正文不可用")
        current = read_question_file(vault, row)
        atomic_write(question_file(vault, row), before)
        record_file_change(vault, row, current, before, f"{reason}：还原 {row['uid']}")
    elif t == "question.create":
        q = p["question"]
        row = projection_row(vault, question_id=q["question_id"])
        if row:
            path = question_file(vault, row)
            if os.path.isfile(path):
                os.remove(path)
            append_commit(vault, "api", "question.archive", f"{reason}：归档 {row['uid']}", {
                "question_id": row["question_id"], "uid_at_that_time": row["uid"], "file_path": row["file_path"],
                "reason": reason, "content_hash": row.get("content_hash") or q.get("content_hash", "")})
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
        for idx, _ in enumerate(p.get("feedbacks") or []):
            append_commit(vault, "api", "review.retract", "撤销旧反馈", {
                "target_commit_id": c["commit_id"], "target_review_index": idx, "reason": reason})
