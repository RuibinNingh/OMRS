"""发布专用升级／代码回退演练：Git 归档旧代码，全部使用临时合成 Vault。

退出 0 表示升级、再升级和保留事实的前向恢复符合断言，不代表旧代码可直接
读写升级后的库。该脚本会主动复现并记录旧代码 UID-only Session 串题风险。
--ref 是此历史回归夹具的旧代码，须具备旧唯一索引与 UID-only Session 语义；
不能用本次任务的文档差异或视觉比较基线替代。
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UID = "数学-代数-001"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _worker(stage, directory):
    # 子进程 PYTHONPATH 只指向选定的新／旧代码；不在进程间复用模块缓存。
    from omrs.ledger import append_commit, blob_hash, connect, read_commits, verify_ledger
    from omrs.projections import rebuild_projection
    from omrs.sessions import create_session_from_selection
    vault = str(directory / "vault")
    facts_path = directory / "facts.json"
    facts = _read(facts_path) if facts_path.exists() else {}

    def check_chain(prefix):
        current = read_commits(vault)
        assert current[:len(prefix)] == prefix, "不可变提交或哈希发生变化"
        assert verify_ledger(vault)["valid"], "Ledger 校验失败"
        return current

    def create(qid):
        content = (f"---\n_omrs_id: {qid}\n难度: 5\ntags:\n  - 状态/待攻克\n"
                   "---\n# 题目\n升级演练合成题\n# 答案\n合成答案\n")
        question = {"question_id": qid, "uid": UID, "file_path": f"错题/数学/代数/{UID}.md",
                    "subject": "数学", "category": "代数", "difficulty": 5,
                    "current_tag": "#状态/待攻克", "metadata": {"tags": ["状态/待攻克"],
                    "_omrs_id": qid, "难度": 5}, "knowledge_tags": [], "labels": [],
                    "content_hash": blob_hash(content)}
        path = Path(vault) / question["file_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        append_commit(vault, "api", "question.create", "创建升级演练题", {"question": question}, blobs=[content])
        return question

    if stage == "baseline":
        create("Q-old")
        rebuild_projection(vault)
        session = create_session_from_selection(vault, [{"uid": UID, "source": "due"}])
        append_commit(vault, "api", "question.archive", "归档旧身份", {"question_id": "Q-old"})
        facts["question"] = create("Q-new")
        rebuild_projection(vault)
        with connect(vault) as db:
            count = db.execute("SELECT COUNT(*) FROM question_projection").fetchone()[0]
        # 旧版整表 UNIQUE + REPLACE 会挤掉归档行；新迁移须从事实链恢复。
        assert count == 1, "升级夹具的 --ref 须保留旧 UNIQUE + REPLACE 语义；不要传入已完成迁移的任务基线"
        facts.update(session_id=session["session_id"], baseline=check_chain([]))
        result = {"stage": stage, "old_projected_questions": count, "commits": len(facts["baseline"])}
    elif stage == "upgrade":
        from omrs.config_repository import initialize
        from omrs.content_history import backfill_missing_content
        from omrs.data_repository import mastery_rows
        from omrs.feedback import process_feedback
        from omrs.indexing import build_index
        from omrs.sessions import get_session
        initialize(vault)
        build_index(vault)
        assert not backfill_missing_content(vault)["conflicts"]
        check_chain(facts["baseline"])
        with connect(vault) as db:
            assert db.execute("SELECT COUNT(*) FROM question_projection").fetchone()[0] == 2
            assert db.execute("SELECT archived FROM question_projection WHERE question_id='Q-old'").fetchone()[0] == 1
            indices = list(db.execute("PRAGMA index_list(question_projection)"))
            assert any(row["name"] == "active_question_uid" and row["partial"] for row in indices)
        session = get_session(vault, facts["session_id"])
        assert session["entries"][0]["question_id"] == "Q-old"
        assert session["entries"][0]["availability"] == "archived"
        rejected = process_feedback(vault, [{"uid": UID, "sub_score": 9, "is_correct": True}], facts["session_id"])
        assert rejected[0]["status"] == "error"
        for _ in range(2):
            assert process_feedback(vault, [{"question_id": "Q-new", "sub_score": 9, "is_correct": True}])[0]["status"] == "ok"
        append_commit(vault, "api", "question.metadata_update", "标记不改学习状态", {
            "question_id": "Q-new", "before": facts["question"],
            "after": {**facts["question"], "labels": ["重点"]}})
        rebuild_projection(vault, force=True)
        assert mastery_rows(vault)[0]["Current_Tag"] == "#状态/已击杀"
        facts["upgraded"] = check_chain(facts["baseline"])
        result = {"stage": stage, "questions_with_archive": 2, "commits": len(facts["upgraded"]),
                  "legacy_session_identity": session["entries"][0]["question_id"]}
    elif stage == "old_replay":
        rebuild_projection(vault)
        with connect(vault) as db:
            tag = db.execute("SELECT current_tag FROM question_projection WHERE question_id='Q-new'").fetchone()[0]
            assert db.execute("SELECT * FROM projection_meta").fetchone() is None
        assert tag == "#状态/待攻克", "夹具未复现旧投影语义"
        assert check_chain(facts["upgraded"]) == facts["upgraded"]
        result = {"stage": stage, "legacy_sql_tag": tag, "checkpoint_invalidated": True}
    elif stage == "reupgrade_after_replay":
        from omrs.config_repository import initialize
        from omrs.data_repository import mastery_rows
        from omrs.projection_runtime import full_project
        from unittest.mock import patch
        initialize(vault)
        with patch("omrs.projection_runtime.full_project", wraps=full_project) as full:
            state = rebuild_projection(vault)
            assert full.call_count == 1
        assert mastery_rows(vault)[0]["Current_Tag"] == state["questions"]["Q-new"]["current_tag"] == "#状态/已击杀"
        assert check_chain(facts["upgraded"]) == facts["upgraded"]
        result = {"stage": stage, "sql_and_state_agree": True, "all_upgrade_facts_preserved": True}
    elif stage == "old_write":
        from omrs.feedback import process_feedback
        # 旧版需要显式导出 CSV；正常新版反馈不自动生成它。
        rebuild_projection(vault)
        accepted = process_feedback(vault, [{"uid": UID, "sub_score": 9, "is_correct": True}], facts["session_id"])
        assert accepted[0]["status"] == "ok" and accepted[0]["question_id"] == "Q-new"
        current = check_chain(facts["upgraded"])
        wrong = next(c for c in current[len(facts["upgraded"]):] if c["commit_type"] == "review.batch_submit")
        assert wrong["payload"]["feedbacks"][0]["question_id"] == "Q-new"
        facts.update(after_legacy_write=current, wrong_commit_id=wrong["commit_id"])
        result = {"stage": stage, "safe_direct_downgrade": False,
                  "old_session_expected_identity": "Q-old", "legacy_write_actual_identity": "Q-new"}
    elif stage == "forward_recovery":
        from omrs.backup_store import create_backup, prepare_import, restore
        from omrs.config_repository import initialize
        from omrs.data_repository import mastery_rows
        from omrs.sessions import get_session
        initialize(vault)
        rebuild_projection(vault)
        check_chain(facts["after_legacy_write"])
        assert get_session(vault, facts["session_id"])["entries"][0]["question_id"] == "Q-old"
        assert mastery_rows(vault)[0]["Attempts"] == "3"
        # 恢复当前代码不会悄悄改写旧程序已追加的错误事实；明确追加撤销节点。
        append_commit(vault, "api", "review.retract", "撤销回退演练中的错误归属反馈", {
            "target_commit_id": facts["wrong_commit_id"], "target_review_index": 0,
            "reason": "旧 Session UID 已复用，确认该条不属于新题"})
        rebuild_projection(vault)
        assert mastery_rows(vault)[0]["Attempts"] == "2"
        current = check_chain(facts["after_legacy_write"])
        snapshot_path, filename, _, _ = create_backup(vault)
        clone = str(directory / "forward-copy")
        try:
            preview = prepare_import(clone, snapshot_path, filename)
            restore(clone, preview["restore_id"], confirm=True)
            assert read_commits(clone)[:len(current)] == current
            assert verify_ledger(clone)["valid"]
            assert mastery_rows(clone)[0]["Attempts"] == "2"
            assert get_session(clone, facts["session_id"])["entries"][0]["question_id"] == "Q-old"
        finally:
            Path(snapshot_path).unlink(missing_ok=True)
        result = {"stage": stage, "all_facts_preserved": True, "immutable_correction_added": True,
                  "current_backup_restore_preserves_facts": True, "commits": len(current)}
    else:
        raise ValueError("未知演练阶段")
    _save(facts_path, facts)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="17d6d84", help="历史回归夹具的旧代码提交，默认 17d6d84；不使用任务差异基线")
    parser.add_argument("--out", help="保存合成 Vault、旧归档及 JSON 证据的仓库外目录")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--directory", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_worker(args.worker, Path(args.directory)), ensure_ascii=False))
        return
    output = Path(args.out or tempfile.mkdtemp(prefix="omrs-upgrade-compat-")).resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("演练目录必须在仓库外，不能包含真实题库")
    if output.exists() and any(output.iterdir()):
        parser.error("演练目录必须为空；不会复用已有 Vault 或归档")
    output.mkdir(parents=True, exist_ok=True)
    baseline = output / "baseline"
    baseline.mkdir()
    reference = subprocess.check_output(["git", "rev-parse", "--verify", args.ref + "^{commit}"], cwd=ROOT, text=True).strip()
    with subprocess.Popen(["git", "archive", reference], cwd=ROOT, stdout=subprocess.PIPE) as archive_process:
        with tarfile.open(fileobj=archive_process.stdout, mode="r|") as archive:
            archive.extractall(baseline, filter="data")
        if archive_process.wait():
            raise RuntimeError("旧代码归档失败")
    stages = [("baseline", baseline), ("upgrade", ROOT), ("old_replay", baseline),
              ("reupgrade_after_replay", ROOT), ("old_write", baseline), ("forward_recovery", ROOT)]
    results = []
    environment = dict(os.environ)
    for key in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"):
        environment.pop(key, None)
    for stage, code in stages:
        environment["PYTHONPATH"] = str(code)
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", stage, "--directory", str(output)]
        completed = subprocess.run(command, cwd=code, env=environment, capture_output=True, text=True, timeout=60)
        (output / (stage + ".log")).write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f"{stage} 演练失败，日志：{output / (stage + '.log')}")
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    report = {"baseline": reference, "safe_direct_downgrade": False, "results": results,
              "limitations": ["合成数据和本机文件系统；不表示已验证真实生产环境、Windows或所有外部集成"]}
    _save(output / "results.json", report)
    print("演练证据：" + str(output / "results.json"))


if __name__ == "__main__":
    main()
