"""合成临时 Ledger 容量门禁；每条路径独立复制基线，统计 P50/P95 和峰值 RSS。"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

for _control_key in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"):
    os.environ.pop(_control_key, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from omrs.common import save_config, parse_yaml_frontmatter
from omrs.ledger import blob_hash
from omrs.workspace_sync import metadata_hash
from omrs.config_repository import initialize
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, append_commit_in_db, connect
from omrs.projections import rebuild_projection, export_legacy_csv

ACTIONS = ("cold", "startup", "full", "tuning", "correction", "correction-heavy",
           "restore", "feedback", "read-models", "csv")
MARKER = ".omrs-data-benchmark.json"


def validate_vault(vault):
    """action 入口只接收本工具生成的 /tmp 合成库，拒绝生产或任意路径。"""
    if not vault:
        raise ValueError("action 模式需要 --vault 合成临时库")
    supplied = Path(vault).absolute()
    root = supplied.resolve()
    if supplied != root or not root.is_relative_to(Path("/tmp")) or not root.name.startswith("omrs-data-capacity-"):
        raise ValueError("容量操作只允许 /tmp/omrs-data-capacity-* 合成库，不接受链接")
    marker = root / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("缺少合成容量库标记，拒绝运行")
    value = json.loads(marker.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("benchmark") != "omrs-data-runtime" or value.get("format_version") != 1
            or value.get("seed") != 20261002 or type(value.get("questions")) is not int
            or value["questions"] < 50 or type(value.get("reviews")) is not int or value["reviews"] < 1):
        raise ValueError("合成容量库标记不合法，拒绝运行")
    for current, directories, files in os.walk(root, followlinks=False):
        if any(Path(current, name).is_symlink() for name in (*directories, *files)):
            raise ValueError("合成容量库不能包含链接，拒绝运行")
    return str(root)


def percentile(values, quantile):
    """最近秩百分位；5 样本的 P95 取最大值。"""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def build(vault, questions, reviews):
    initialize(vault)
    generator = random.Random(20261002)
    with connect(vault) as db:
        db.execute("BEGIN IMMEDIATE")
        for index in range(questions):
            qid, uid = f"Q-{index:05d}", f"代数{index}"
            relative = f"错题/数学/代数/{uid}.md"
            content = f"---\n_omrs_id: {qid}\n科目: 数学\n分类: 代数\n难度: 5\n相关知识点: []\n标记: []\ntags:\n  - 状态/待攻克\n---\n\n# 题目\n计算 {index}+1\n\n# 答案\n{index + 1}\n\n# 历史\n"
            path = Path(vault) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            metadata = parse_yaml_frontmatter(content)
            append_commit_in_db(db, "benchmark", "question.create", "容量夹具", {"question": {
                "question_id": qid, "uid": uid, "file_path": relative,
                "subject": "数学", "category": "代数", "difficulty": 5, "current_tag": "#状态/待攻克",
                "metadata": metadata, "metadata_hash": metadata_hash(metadata), "content_hash": blob_hash(content)}}, blobs=[content])
        for start in range(0, reviews, 100):
            values = []
            for index in range(start, min(start + 100, reviews)):
                q = index % questions
                values.append({"question_id": f"Q-{q:05d}", "uid_at_that_time": f"代数{q}", "source": "due",
                    "subject": "数学", "session_id": "", "is_correct": generator.random() > 0.3,
                    "sub_score": generator.randrange(11), "recorded_at": "2026-10-01T16:15:00+00:00",
                    "review_date": "2026-10-02", "review_timezone": "Asia/Shanghai"})
            append_commit_in_db(db, "benchmark", "review.batch_submit", "容量反馈", {"feedbacks": values})
    rebuild_projection(vault, force=True)
    Path(vault, MARKER).write_text(json.dumps({"benchmark": "omrs-data-runtime", "format_version": 1,
        "seed": 20261002, "questions": questions, "reviews": reviews}), encoding="utf-8")


def measure(vault, action):
    vault = validate_vault(vault)
    start = time.perf_counter()
    result = {}
    if action == "cold":
        rebuild_projection(vault)
    elif action == "startup":
        from omrs.indexing import build_index
        from omrs.content_history import backfill_missing_content
        from omrs.inbox_commit import recover_pending
        initialize(vault)
        recover_pending(vault)
        build_index(vault)
        backfill = backfill_missing_content(vault)
        if backfill["conflicts"]:
            raise AssertionError(backfill)
    elif action == "full":
        rebuild_projection(vault, force=True)
    elif action == "tuning":
        publication = save_config(vault, {"tuning": {"kill_streak": 3}})
        result.update(config_revision=publication["revision"], recalculation=publication["recalculation"])
    elif action == "correction":
        with connect(vault) as db:
            target = db.execute("SELECT commit_id FROM commits WHERE commit_type='review.batch_submit' ORDER BY seq LIMIT 1").fetchone()[0]
        append_commit(vault, "benchmark", "review.replace", "容量修正", {"target_commit_id": target,
            "target_review_index": 0, "replacement": {"sub_score": 2, "is_correct": False}})
        rebuild_projection(vault)
    elif action == "correction-heavy":
        with connect(vault) as db:
            db.execute("BEGIN IMMEDIATE")
            targets = db.execute("SELECT commit_id,payload_json FROM commits WHERE commit_type='review.batch_submit' ORDER BY seq")
            for target in targets:
                for index in range(len(json.loads(target["payload_json"])["feedbacks"])):
                    append_commit_in_db(db, "benchmark", "review.replace", "修正索引容量", {
                        "target_commit_id": target["commit_id"], "target_review_index": index,
                        "replacement": {"note": "容量索引测试"}})
        rebuild_projection(vault)
    elif action == "restore":
        with connect(vault) as db:
            target = db.execute("SELECT MAX(seq) FROM commits WHERE commit_type='review.batch_submit'").fetchone()[0]
        append_commit(vault, "benchmark", "state.restore", "容量还原", {"target_seq": target})
        rebuild_projection(vault)
    elif action == "feedback":
        rebuild_projection(vault)
        import omrs.projection_runtime as runtime
        original = runtime.full_project
        runtime.full_project = lambda *a, **k: (_ for _ in ()).throw(AssertionError("普通反馈触发全量重放"))
        values = []
        try:
            for index in range(50):
                before = time.perf_counter()
                process_feedback(vault, [{"question_id": f"Q-{index:05d}", "is_correct": True, "sub_score": 9}])
                values.append((time.perf_counter() - before) * 1000)
        finally:
            runtime.full_project = original
        result.update(samples=len(values), p50_ms=statistics.median(values), p95_ms=percentile(values, .95))
    elif action == "read-models":
        from omrs.stats import get_stats
        from omrs.analytics import get_analytics
        stats = get_stats(vault)
        analytics = get_analytics(vault)
        with connect(vault) as db:
            expected_q = db.execute("SELECT COUNT(*) FROM question_projection WHERE archived=0 AND suspended=0").fetchone()[0]
            expected_reviews = db.execute("SELECT COUNT(*) FROM history_projection").fetchone()[0]
        if stats["total"] != expected_q or analytics["overview"]["total_reviews"] != expected_reviews:
            raise AssertionError("SQL 聚合读取未覆盖容量夹具")
    elif action == "csv":
        export_legacy_csv(vault)
    with connect(vault) as db:
        result["questions"] = db.execute("SELECT COUNT(*) FROM question_projection").fetchone()[0]
        result["reviews"] = db.execute("SELECT COUNT(*) FROM history_projection").fetchone()[0]
        result["corrections"] = db.execute("SELECT COUNT(*) FROM projection_review_corrections").fetchone()[0]
    if action == "tuning":
        summary = result["recalculation"]
        if (summary["status"] != "complete" or summary["revision"] != result["config_revision"]
                or summary["questions"] != result["questions"] or summary["feedbacks"] != result["reviews"]):
            raise AssertionError("调参发布摘要与同次重算不一致")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if sys.platform.startswith("linux"):
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                peak = int(line.split()[1]) / 1024
    result.update(action=action, seconds=time.perf_counter() - start, rss_mib=peak)
    if result["rss_mib"] > 768:
        raise AssertionError(f"峰值内存超出 768MiB: {result}")
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault")
    parser.add_argument("--action", choices=ACTIONS)
    parser.add_argument("--samples", type=int, default=5, help="每条路径的独立样本数；反馈仍测50次追加")
    parser.add_argument("--questions", type=int, default=10000)
    parser.add_argument("--reviews", type=int, default=100000)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.action:
        try:
            measure(args.vault, args.action)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        return
    if args.vault:
        parser.error("--vault 仅用于 --action 的合成临时库")
    if args.samples < 1:
        parser.error("--samples 至少为1")
    if args.questions < 50 or args.reviews < 1:
        parser.error("容量夹具至少 50 题及 1 条反馈")
    directory = tempfile.mkdtemp(prefix="omrs-data-capacity-", dir="/tmp")
    try:
        before = time.perf_counter()
        build(directory, args.questions, args.reviews)
        cpu = platform.processor()
        if sys.platform.startswith("linux"):
            cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), cpu)
        print(json.dumps({"vault": directory, "build_seconds": time.perf_counter() - before,
            "python": platform.python_version(), "platform": platform.platform(),
            "cpu": cpu, "questions": args.questions, "reviews": args.reviews,
            "samples_per_action": args.samples, "percentile_method": "nearest_rank"}), flush=True)
        for action in ACTIONS:
            results = []
            for sample in range(1, (1 if action == "feedback" else args.samples) + 1):
                with tempfile.TemporaryDirectory(prefix="omrs-data-capacity-sample-", dir="/tmp") as clone:
                    shutil.copytree(directory, clone, dirs_exist_ok=True)
                    completed = subprocess.run([sys.executable, __file__, "--vault", clone, "--action", action],
                        check=True, capture_output=True, text=True, env=dict(os.environ))
                    result = json.loads(completed.stdout.strip().splitlines()[-1])
                    expected_reviews = args.reviews + (50 if action == "feedback" else 0)
                    expected_corrections = args.reviews if action == "correction-heavy" else 1 if action == "correction" else 0
                    if (result["questions"] != args.questions or result["reviews"] != expected_reviews
                            or result["corrections"] != expected_corrections):
                        raise AssertionError("容量样本偏离独立基线：" + json.dumps(result, ensure_ascii=False))
                result.update(kind="sample", sample=sample)
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            if action != "feedback":
                seconds = [row["seconds"] for row in results]
                rss = [row["rss_mib"] for row in results]
                print(json.dumps({"kind": "summary", "action": action, "samples": len(results),
                    "p50_seconds": statistics.median(seconds), "p95_seconds": percentile(seconds, .95),
                    "rss_p50_mib": statistics.median(rss), "rss_p95_mib": percentile(rss, .95),
                    "rss_max_mib": max(rss), "questions": results[0]["questions"],
                    "reviews": results[0]["reviews"], "corrections": results[0]["corrections"]}, ensure_ascii=False), flush=True)
    finally:
        if not args.keep:
            shutil.rmtree(directory)


if __name__ == "__main__":
    main()
