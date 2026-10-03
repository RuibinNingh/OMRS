"""历史正文补回的原子性、原事实核验和临时 Vault CLI 验证。"""
import copy
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from omrs.content_history import audit_content_coverage, content_versions
from omrs.content_recovery import load_recovery_manifest, recover_content
from omrs.creation import create_question
from omrs.ledger import (blob_hash, connect, content_ref_pairs, get_blob,
                         ledger_path, read_commits, verify_ledger)
from omrs.projections import rebuild_projection
from omrs.question_ops import delete_question, save_question_markdown


class ContentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omrs-content-recovery-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vault = str(self.root / "vault")
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.originals, self.questions = [], []
        for text in ("原始题面甲，不能泄漏到回执", "原始题面乙，不能泄漏到回执"):
            question = create_question(self.vault, "数学", "函数", 5, question_text=text)
            path = Path(self.vault) / question["file_path"]
            original = path.read_text(encoding="utf-8")
            self.questions.append(question)
            self.originals.append(original)
            save_question_markdown(self.vault, question["uid"], original.replace("原始", "当前"))
        with connect(self.vault) as db:
            for content in self.originals:
                db.execute("DELETE FROM blobs WHERE hash=?", (blob_hash(content),))
        gaps = audit_content_coverage(self.vault)["historical_gaps"]
        self.assertEqual(len(gaps), 2)
        entries = []
        for content in self.originals:
            digest = blob_hash(content)
            gap = next(row for row in gaps if row["hash"] == digest)
            filename = digest + ".md"
            (self.sources / filename).write_text(content, encoding="utf-8", newline="")
            entries.append({"question_id": gap["question_id"], "hash": digest,
                            "first_referenced_seq": gap["first_referenced_seq"], "file": filename})
        self.manifest = {"version": 1, "items": entries}
        self.manifest_path = self.sources / "manifest.json"
        self.write_manifest()

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    def run_recovery(self, apply=False):
        items, digest = load_recovery_manifest(self.manifest_path)
        return recover_content(self.vault, items, digest, apply=apply)

    def sql_snapshot(self):
        with contextlib.closing(sqlite3.connect(ledger_path(self.vault))) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall() for name in names}

    def cli(self, vault=None, apply=False):
        env = dict(os.environ)
        for key in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"):
            env.pop(key, None)
        args = [sys.executable, "omrs_engine.py", "--vault", vault or self.vault,
                "content-recover", "--manifest", str(self.manifest_path)]
        if apply:
            args.append("--apply")
        return subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)

    def test_preview_preserves_all_sql_and_current_markdown(self):
        before = self.sql_snapshot()
        files = {q["file_path"]: (Path(self.vault) / q["file_path"]).read_bytes() for q in self.questions}
        result = self.run_recovery()
        self.assertEqual((result["recovered"], result["recoverable"], result["commit"]), (0, 2, None))
        self.assertEqual(self.sql_snapshot(), before)
        self.assertEqual(files, {name: (Path(self.vault) / name).read_bytes() for name in files})
        self.assertNotIn("原始题面", json.dumps(result, ensure_ascii=False))

    def test_apply_preserves_learning_and_original_facts_and_retries_are_empty(self):
        before = self.sql_snapshot()
        files = {q["file_path"]: (Path(self.vault) / q["file_path"]).read_bytes() for q in self.questions}
        result = self.run_recovery(apply=True)
        self.assertEqual(result["recovered"], 2)
        after = self.sql_snapshot()
        self.assertEqual(after["commits"][:-1], before["commits"])
        for name, rows in before.items():
            if name not in {"commits", "blobs", "sqlite_sequence"}:
                self.assertEqual(after[name], rows, name)
        commit = read_commits(self.vault, ascending=False, limit=1)[0]
        self.assertEqual(commit["commit_type"], "question.content_backfill")
        self.assertTrue(commit["payload"]["historical"])
        self.assertNotIn("原始题面", json.dumps(commit, ensure_ascii=False))
        for content in self.originals:
            self.assertEqual(get_blob(self.vault, blob_hash(content)), content)
        rebuild_projection(self.vault)
        after_projection = self.sql_snapshot()
        for name in ("question_projection", "mastery_projection", "session_projection", "history_projection"):
            self.assertEqual(after_projection[name], before[name], name)
        self.assertEqual(files, {name: (Path(self.vault) / name).read_bytes() for name in files})
        self.assertEqual(audit_content_coverage(self.vault)["historical_missing_blobs"], 0)
        self.assertTrue(verify_ledger(self.vault)["valid"])
        self.assertTrue(all(v["available"] for v in content_versions(self.vault, question_id=self.questions[0]["question_id"])["versions"]))
        commits = read_commits(self.vault)
        retry = self.run_recovery(apply=True)
        self.assertEqual((retry["recovered"], retry["already_present"], retry["commit"]), (0, 2, None))
        self.assertEqual(read_commits(self.vault), commits)

    def test_hash_or_identity_mismatch_rejects_entire_batch(self):
        items, digest = load_recovery_manifest(self.manifest_path)
        before = self.sql_snapshot()
        for mode in ("hash", "identity"):
            changed = copy.deepcopy(items)
            changed[1]["content"] += "正文篡改"
            if mode == "identity":
                changed[1]["content"] = changed[1]["content"].replace(changed[1]["question_id"], "OP-999999")
                changed[1]["content_hash"] = blob_hash(changed[1]["content"])
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "哈希或题目身份"):
                recover_content(self.vault, changed, digest, apply=True)
            self.assertEqual(self.sql_snapshot(), before)

    def test_fact_without_matching_reference_is_rejected_even_with_forged_index(self):
        items, digest = load_recovery_manifest(self.manifest_path)
        wrong = items[0]["first_referenced_seq"]
        with connect(self.vault) as db:
            db.execute("UPDATE content_version_refs SET first_seq=? WHERE content_hash=?", (wrong, items[1]["content_hash"]))
        items[1]["first_referenced_seq"] = wrong
        before = self.sql_snapshot()
        with self.assertRaisesRegex(ValueError, "没有引用"):
            recover_content(self.vault, items, digest, apply=True)
        self.assertEqual(self.sql_snapshot(), before)

    def test_corrupt_existing_blob_is_preserved_and_whole_batch_rejected(self):
        h = self.manifest["items"][1]["hash"]
        with connect(self.vault) as db:
            db.execute("INSERT INTO blobs VALUES(?,?,?)", (h, "损坏正文", "2026-01-01"))
        before = self.sql_snapshot()
        with self.assertRaisesRegex(ValueError, "已有正文 blob 损坏"):
            self.run_recovery(apply=True)
        self.assertEqual(self.sql_snapshot(), before)

    def test_corrupt_original_commit_is_not_rewritten(self):
        seq = self.manifest["items"][0]["first_referenced_seq"]
        with connect(self.vault) as db:
            db.execute("UPDATE commits SET commit_hash='损坏' WHERE seq=?", (seq,))
        before = self.sql_snapshot()
        with self.assertRaisesRegex(ValueError, "原始提交哈希损坏"):
            self.run_recovery(apply=True)
        self.assertEqual(self.sql_snapshot(), before)

    def test_missing_reference_or_wrong_first_sequence_is_rejected(self):
        items, digest = load_recovery_manifest(self.manifest_path)
        for seq, message in ((999999, "找不到"), (items[0]["first_referenced_seq"] + 1, "索引")):
            changed = copy.deepcopy(items)
            changed[0]["first_referenced_seq"] = seq
            before = self.sql_snapshot()
            with self.subTest(seq=seq), self.assertRaisesRegex(ValueError, message):
                recover_content(self.vault, changed, digest, apply=True)
            self.assertEqual(self.sql_snapshot(), before)

    def test_partial_blob_failure_rolls_back_every_row_and_fact(self):
        import omrs.ledger as ledger
        original = ledger._store_blobs
        def fail(db, blobs, timestamp):
            original(db, blobs[:1], timestamp)
            raise OSError("磁盘故障注入")
        before = self.sql_snapshot()
        with mock.patch.object(ledger, "_store_blobs", side_effect=fail), self.assertRaisesRegex(OSError, "故障注入"):
            self.run_recovery(apply=True)
        self.assertEqual(self.sql_snapshot(), before)
        self.assertEqual(self.run_recovery(apply=True)["recovered"], 2)

    def test_archived_question_and_reused_uid_keep_original_identity(self):
        old = self.questions[0]
        delete_question(self.vault, old["uid"])
        new = create_question(self.vault, "数学", "函数", 5, question_text="新身份")
        self.assertEqual(new["uid"], old["uid"])
        self.assertNotEqual(new["question_id"], old["question_id"])
        self.assertEqual(self.run_recovery(apply=True)["recovered"], 2)
        old_hash = blob_hash(self.originals[0])
        versions = content_versions(self.vault, question_id=old["question_id"])
        self.assertTrue(versions["archived"])
        self.assertTrue(next(v for v in versions["versions"] if v["hash"] == old_hash)["available"])
        self.assertNotIn(old_hash, [v["hash"] for v in content_versions(self.vault, question_id=new["question_id"])["versions"]])

    def test_cli_preview_and_apply_do_not_initialize_config_or_inbox(self):
        from omrs.cli import main
        import io
        before = self.sql_snapshot()
        for apply in (False, True):
            args = ["omrs_engine.py", "--vault", self.vault, "content-recover", "--manifest", str(self.manifest_path)]
            if apply:
                args.append("--apply")
            output = io.StringIO()
            with mock.patch.object(sys, "argv", args), mock.patch("omrs.config_repository.initialize", side_effect=AssertionError("不应初始化配置")), mock.patch("omrs.inbox_commit.recover_pending", side_effect=AssertionError("不应补收件箱")), contextlib.redirect_stdout(output):
                main()
            result = json.loads(output.getvalue())
            self.assertEqual(result["recovered"], 2 if apply else 0)
            self.assertNotIn("原始题面", output.getvalue())
        self.assertEqual(self.sql_snapshot()["commits"][:-1], before["commits"])

    def test_two_processes_apply_same_manifest_create_only_one_fact(self):
        env = {k:v for k,v in os.environ.items() if k not in {"OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"}}
        args = [sys.executable, "omrs_engine.py", "--vault", self.vault, "content-recover", "--manifest", str(self.manifest_path), "--apply"]
        before = read_commits(self.vault)
        processes = [subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        try:
            outputs = [p.communicate(timeout=20) for p in processes]
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
        self.assertTrue(all(p.returncode == 0 for p in processes), outputs)
        self.assertEqual(sorted(json.loads(out)["recovered"] for out, _ in outputs), [0, 2])
        self.assertEqual(len(read_commits(self.vault)), len(before) + 1)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_manifest_rejects_traversal_symlinks_duplicates_and_invalid_schema(self):
        before = self.sql_snapshot()
        original = copy.deepcopy(self.manifest)
        invalids = [None, {"version": True, "items": []}, {"version": 1, "items": []}]
        duplicate = copy.deepcopy(original)
        duplicate["items"].append(copy.deepcopy(duplicate["items"][0]))
        invalids.append(duplicate)
        for filename in ("../outside.md", str(self.sources / original["items"][0]["file"]), "linked.md"):
            changed = copy.deepcopy(original)
            changed["items"][0]["file"] = filename
            invalids.append(changed)
        (self.sources / "linked.md").symlink_to(self.sources / original["items"][0]["file"])
        for changed in invalids:
            self.manifest = changed
            self.write_manifest()
            with self.subTest(manifest=changed), self.assertRaises(ValueError):
                load_recovery_manifest(self.manifest_path)
        self.assertEqual(self.sql_snapshot(), before)

    def test_manifest_size_and_body_limits_fail_before_write(self):
        for limit in ("MAX_MANIFEST_BYTES", "MAX_CONTENT_BYTES"):
            with self.subTest(limit=limit), mock.patch("omrs.content_recovery." + limit, 10), self.assertRaisesRegex(ValueError, "超过"):
                load_recovery_manifest(self.manifest_path)

    def test_crlf_copy_uses_the_original_text_hash(self):
        filename = self.sources / self.manifest["items"][0]["file"]
        filename.write_bytes(self.originals[0].replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.run_recovery(apply=True)["recovered"], 2)

    def test_empty_vault_is_not_created_by_cli(self):
        vault = str(self.root / "absent")
        result = self.cli(vault=vault, apply=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((Path(vault) / "错题").exists())

    def test_old_schema_is_rejected_without_migration(self):
        with connect(self.vault) as db:
            db.execute("DROP TABLE content_version_refs")
        path = Path(ledger_path(self.vault))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = self.cli(apply=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        self.assertIn("正文补回失败", result.stderr)

    def test_shared_reference_extractor_ignores_non_question_payloads(self):
        self.assertEqual(list(content_ref_pairs("config.tuning_update", {"question_id":"OP-1", "content_hash":"hash"})), [])
        self.assertEqual(set(content_ref_pairs("question.create_external", {"question_id":"OP-1", "content_hash":"hash"})), {("OP-1", "hash")})


if __name__ == "__main__":
    unittest.main()
