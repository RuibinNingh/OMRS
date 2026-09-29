"""正文入账、回填、删除与按运行撤销的临时 Vault 回归。"""
import os
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock

from omrs.actor import agent_actor
from omrs.agent import revert
from omrs.content_history import (audit_content_coverage, backfill_missing_content,
                                  content_versions, ensure_content_snapshot, restore_content)
from omrs.creation import create_question
from omrs.ledger import append_commit, blob_hash, connect, get_blob, ledger_path, read_commits
from omrs.question_ops import delete_question, move_question, save_question_markdown, set_question_labels
from omrs.workspace_sync import scan_workspace


class ContentIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omrs-content-")
        self.vault = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, text="题面"):
        return create_question(self.vault, "数学", "函数", 5, question_text=text)

    def path(self, q):
        return os.path.join(self.vault, q["file_path"])

    def test_legacy_page_survives_history_but_normal_edit_removes_active_field(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            original = file.read()
        legacy = original.replace("难度: 5\n", "难度: 5\n页码: p.23\n", 1)
        with open(self.path(q), "w", encoding="utf-8") as file:
            file.write(legacy)
        scan_workspace(self.vault)
        self.assertEqual(get_blob(self.vault, blob_hash(legacy)), legacy)
        saved = save_question_markdown(self.vault, q["uid"], legacy.replace("题面", "人工修改的题面"))
        with open(self.path(q), encoding="utf-8") as file:
            current = file.read()
        self.assertNotIn("页码:", current)
        self.assertIn("人工修改的题面", current)
        self.assertEqual(saved["content_hash"], blob_hash(current))
        self.assertEqual(get_blob(self.vault, blob_hash(legacy)), legacy)

    def test_create_move_and_external_changes_store_new_hashes(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            initial = file.read()
        self.assertEqual(get_blob(self.vault, blob_hash(initial)), initial)

        moved = move_question(self.vault, q["uid"], "数学", "代数")
        with open(self.path(moved), encoding="utf-8") as file:
            moved_content = file.read()
        self.assertEqual(get_blob(self.vault, blob_hash(moved_content)), moved_content)

        external = moved_content.replace("难度: 5", "难度: 6").replace("题面", "修改后的题面")
        self.assertNotEqual(external, moved_content)
        with open(self.path(moved), "w", encoding="utf-8") as file:
            file.write(external)
        scan_workspace(self.vault)
        self.assertEqual(get_blob(self.vault, blob_hash(external)), external)
        versions = content_versions(self.vault, uid=moved["uid"])["versions"]
        self.assertTrue(all(v["available"] for v in versions))

        renamed_path = self.path(moved).replace(moved["uid"] + ".md", "代数99.md")
        moved_again = external.replace("修改后的题面", "外部移动后的题面").replace("难度: 6", "难度: 7")
        os.replace(self.path(moved), renamed_path)
        with open(renamed_path, "w", encoding="utf-8") as file:
            file.write(moved_again)
        scan_workspace(self.vault)
        self.assertEqual(get_blob(self.vault, blob_hash(moved_again)), moved_again)
        self.assertTrue(any(c["commit_type"] == "question.move_external" for c in read_commits(self.vault)))

        new_external = moved_again.replace(f"_omrs_id: {q['question_id']}\n", "", 1)
        external_path = os.path.join(os.path.dirname(renamed_path), "代数98.md")
        with open(external_path, "w", encoding="utf-8") as file:
            file.write(new_external)
        scan_workspace(self.vault)
        with open(external_path, encoding="utf-8") as file:
            injected = file.read()
        self.assertEqual(get_blob(self.vault, blob_hash(injected)), injected)

        supplied_id = moved_again.replace(q["question_id"], "OP-777777", 1).replace("外部移动后的题面", "显式身份的新题")
        supplied_path = os.path.join(os.path.dirname(renamed_path), "代数97.md")
        with open(supplied_path, "w", encoding="utf-8") as file:
            file.write(supplied_id)
        scan_workspace(self.vault)
        self.assertEqual(get_blob(self.vault, blob_hash(supplied_id)), supplied_id)
        self.assertTrue(any(c["commit_type"] == "question.create_external" and
                            c["payload"].get("question", {}).get("question_id") == "OP-777777"
                            for c in read_commits(self.vault)))

    def test_create_failure_keeps_only_body_copy_for_later_scan(self):
        with mock.patch("omrs.creation.append_commit", side_effect=RuntimeError("Ledger 提交失败")):
            with self.assertRaisesRegex(RuntimeError, "Ledger 提交失败"):
                self.create("唯一题面")
        files = [os.path.join(root, name) for root, _, names in os.walk(os.path.join(self.vault, "错题"))
                 for name in names if name == "函数1.md"]
        self.assertEqual(len(files), 1)
        with open(files[0], encoding="utf-8") as file:
            content = file.read()
        self.assertIn("唯一题面", content)
        self.assertIsNone(get_blob(self.vault, blob_hash(content)))
        scan_workspace(self.vault)
        self.assertEqual(get_blob(self.vault, blob_hash(content)), content)

    def test_incremental_backfill_is_idempotent_and_audit_is_read_only(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        h = blob_hash(content)
        ensure_content_snapshot(self.vault)
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (h,))
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        audit = audit_content_coverage(self.vault)
        self.assertEqual(len(audit["current_missing_blobs"]), 1)
        self.assertTrue(audit["current_missing_blobs"][0]["recoverable_from_current_file"])
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)
        self.assertEqual(backfill_missing_content(self.vault)["count"], 1)
        self.assertEqual(get_blob(self.vault, h), content)
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        self.assertEqual(backfill_missing_content(self.vault)["count"], 0)
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)

    def test_backfill_skips_file_with_different_hash(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        h = blob_hash(content)
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (h,))
        with open(self.path(q), "w", encoding="utf-8") as file:
            file.write(content + "\n人工未入账修改")
        result = backfill_missing_content(self.vault)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(get_blob(self.vault, h))
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        self.assertEqual(scan_workspace(self.vault)["status"], "conflict")
        with self.assertRaisesRegex(RuntimeError, "blob 缺失且文件已改"):
            save_question_markdown(self.vault, q["uid"], content + "\n再次修改")
        with self.assertRaisesRegex(RuntimeError, "blob 缺失且文件已改"):
            set_question_labels(self.vault, q["uid"], ["待核对"])
        with self.assertRaisesRegex(RuntimeError, "blob 缺失且文件已改"):
            delete_question(self.vault, q["uid"])
        self.assertTrue(os.path.isfile(self.path(q)))
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)

    def test_corrupt_projection_blob_blocks_scan_edit_labels_and_delete(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        with connect(self.vault) as db:
            db.execute("UPDATE blobs SET content=? WHERE hash=?", ("损坏", blob_hash(content)))
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        self.assertEqual(scan_workspace(self.vault)["status"], "conflict")
        with self.assertRaisesRegex(RuntimeError, "blob 校验失败"):
            save_question_markdown(self.vault, q["uid"], content + "\n新题面")
        with self.assertRaisesRegex(RuntimeError, "blob 校验失败"):
            set_question_labels(self.vault, q["uid"], ["待核对"])
        with self.assertRaisesRegex(RuntimeError, "blob 校验失败"):
            delete_question(self.vault, q["uid"])
        with self.assertRaisesRegex(RuntimeError, "blob 校验失败"):
            move_question(self.vault, q["uid"], "数学", "代数")
        self.assertTrue(os.path.isfile(self.path(q)))
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)

    def test_labels_save_missing_current_blob_before_file_change(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            before = file.read()
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash=?", (blob_hash(before),))
        set_question_labels(self.vault, q["uid"], ["待核对"])
        with open(self.path(q), encoding="utf-8") as file:
            after = file.read()
        self.assertEqual(get_blob(self.vault, blob_hash(before)), before)
        self.assertEqual(get_blob(self.vault, blob_hash(after)), after)

    def test_backfill_skips_file_with_different_identity(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        h = blob_hash(content)
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (h,))
        with open(self.path(q), "w", encoding="utf-8") as file:
            file.write(content.replace(q["question_id"], "OP-OTHER", 1))
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        result = backfill_missing_content(self.vault)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(get_blob(self.vault, h))
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)

    def test_backfill_skips_unsafe_projection_path_without_commit(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        h = blob_hash(content)
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (h,))
            db.execute("UPDATE question_projection SET file_path = ? WHERE question_id = ?",
                       ("../outside.md", q["question_id"]))
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        result = backfill_missing_content(self.vault)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(get_blob(self.vault, h))
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)

    def test_content_audit_cli_is_read_only_and_has_no_body(self):
        from omrs.cli import main
        q = self.create("正文机密标记XYZ")
        with open(ledger_path(self.vault), "rb") as file:
            before = file.read()
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["omrs_engine.py", "--vault", self.vault, "content-audit", "--json"]):
            with contextlib.redirect_stdout(output):
                main()
        report = json.loads(output.getvalue())
        self.assertEqual(report["active_questions"], 1)
        self.assertEqual(report["current_missing_blobs"], [])
        self.assertNotIn("正文机密标记XYZ", output.getvalue())
        with open(ledger_path(self.vault), "rb") as file:
            self.assertEqual(file.read(), before)

    def test_server_backfills_and_recovers_before_scanner_and_listener(self):
        from omrs.cli import main
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        h = blob_hash(content)
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (h,))
        events = []

        def recover(_vault):
            self.assertEqual(get_blob(self.vault, h), content)
            events.append("recover")
            return {"state": "none"}

        def scanner(_vault):
            self.assertEqual(events, ["recover"])
            events.append("scanner")

        class FakeServer:
            def __init__(self, *_args):
                self.assertion = events == ["recover", "scanner"]
                events.append("listener")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def serve_forever(self):
                if not self.assertion:
                    raise AssertionError("监听早于回填、恢复或扫描")

        with mock.patch.object(sys, "argv", ["omrs_engine.py", "--vault", self.vault, "serve", "--port", "0"]), \
             mock.patch("omrs.cli.build_index", return_value=[]), \
             mock.patch("omrs.cli.ensure_image_dependencies_interactive"), \
             mock.patch("omrs.cli.load_config", return_value={}), \
             mock.patch("omrs.traincontrol.recover_pending", side_effect=recover), \
             mock.patch("omrs.agent.runtime.get_runtime"), \
             mock.patch("omrs.cli.start_workspace_scanner", side_effect=scanner), \
             mock.patch("omrs.cli.OMRSTCPServer", FakeServer), \
             contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(events, ["recover", "scanner", "listener"])

    def test_audit_reports_historical_gap_separately(self):
        q = self.create("旧版")
        with open(self.path(q), encoding="utf-8") as file:
            original = file.read()
        save_question_markdown(self.vault, q["uid"], original.replace("旧版", "新版"))
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (blob_hash(original),))
        report = audit_content_coverage(self.vault)
        self.assertEqual(report["current_missing_blobs"], [])
        self.assertEqual(report["historical_missing_blobs"], 1)
        self.assertEqual(report["historical_gaps"][0]["hash"], blob_hash(original))

    def test_restore_rejects_other_question_and_forged_history(self):
        first, second = self.create("甲"), self.create("乙")
        with open(self.path(first), encoding="utf-8") as file:
            original = file.read()
        with open(self.path(second), encoding="utf-8") as file:
            other = file.read()
        other_hash = blob_hash(other)
        with self.assertRaisesRegex(RuntimeError, "不属于该题"):
            restore_content(self.vault, first["uid"], other_hash)
        append_commit(self.vault, "migration", "question.content_snapshot", "伪造的历史索引",
                      {"items": [{"question_id": first["question_id"], "content_hash": other_hash}]})
        with self.assertRaisesRegex(RuntimeError, "身份不匹配"):
            restore_content(self.vault, first["uid"], other_hash)
        with open(self.path(first), encoding="utf-8") as file:
            self.assertEqual(file.read(), original)

    def test_delete_keeps_file_when_blob_check_fails(self):
        q = self.create()
        with mock.patch("omrs.content_history.get_blob", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "拒绝删除"):
                delete_question(self.vault, q["uid"])
        self.assertTrue(os.path.isfile(self.path(q)))

    def test_delete_rejects_corrupted_existing_blob(self):
        q = self.create()
        with open(self.path(q), encoding="utf-8") as file:
            content = file.read()
        h = blob_hash(content)
        with connect(self.vault) as db:
            db.execute("UPDATE blobs SET content = ? WHERE hash = ?", ("损坏的 blob", h))
        head = read_commits(self.vault, limit=1, ascending=False)[0]["seq"]
        with self.assertRaisesRegex(RuntimeError, "blob 校验失败"):
            delete_question(self.vault, q["uid"])
        self.assertTrue(os.path.isfile(self.path(q)))
        self.assertEqual(read_commits(self.vault, limit=1, ascending=False)[0]["seq"], head)

    def test_delete_and_move_restore_files_when_commit_fails(self):
        q = self.create()
        with mock.patch("omrs.question_ops.append_commit", side_effect=RuntimeError("Ledger 提交失败")):
            with self.assertRaisesRegex(RuntimeError, "Ledger 提交失败"):
                delete_question(self.vault, q["uid"])
        self.assertTrue(os.path.isfile(self.path(q)))
        with mock.patch("omrs.question_ops.append_commit", side_effect=RuntimeError("Ledger 提交失败")):
            with self.assertRaisesRegex(RuntimeError, "Ledger 提交失败"):
                move_question(self.vault, q["uid"], "数学", "代数")
        self.assertTrue(os.path.isfile(self.path(q)))

    def test_agent_create_revert_keeps_first_body_in_ledger(self):
        with agent_actor("conv", "run-create", "call"):
            q = self.create("首版正文")
            with open(self.path(q), encoding="utf-8") as file:
                content = file.read()
            save_question_markdown(self.vault, q["uid"], content + "\nAI 补充")
        plan = revert.plan_revert(self.vault, "run-create")
        self.assertTrue(plan["ok"], plan)
        self.assertEqual(len(plan["items"]), 2)
        revert.apply_revert(self.vault, "run-create")
        self.assertFalse(os.path.exists(self.path(q)))
        self.assertEqual(get_blob(self.vault, blob_hash(content)), content)

    def test_revert_preflights_corrupt_current_blob_before_archiving_any_question(self):
        with agent_actor("conv", "run-corrupt", "call"):
            first = self.create("甲")
            second = self.create("乙")
        with open(self.path(first), encoding="utf-8") as file:
            first_hash = blob_hash(file.read())
        with connect(self.vault) as db:
            db.execute("UPDATE blobs SET content=? WHERE hash=?", ("损坏", first_hash))

        plan = revert.plan_revert(self.vault, "run-corrupt")
        self.assertFalse(plan["ok"])
        self.assertTrue(any("当前正文 blob 不可用" in row["by_desc"] for row in plan["conflicts"]))
        self.assertFalse(revert.apply_revert(self.vault, "run-corrupt")["ok"])
        self.assertTrue(os.path.isfile(self.path(first)))
        self.assertTrue(os.path.isfile(self.path(second)))
        self.assertFalse(any((c["payload"].get("_revert") or {}).get("run_id") == "run-corrupt"
                             for c in read_commits(self.vault)))

    def test_revert_preflights_missing_old_blob_and_resumes_partial_run(self):
        first, second = self.create("甲"), self.create("乙")
        originals = {}
        with agent_actor("conv", "run-integrity", "call"):
            for q in (first, second):
                with open(self.path(q), encoding="utf-8") as file:
                    before = file.read()
                originals[q["uid"]] = before
                save_question_markdown(self.vault, q["uid"], before + "\nAI 修改")
        mine = [c for c in read_commits(self.vault) if (c["payload"].get("_agent") or {}).get("run_id") == "run-integrity"]
        old_hash = mine[0]["payload"]["before_hash"]
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash = ?", (old_hash,))
        plan = revert.plan_revert(self.vault, "run-integrity")
        self.assertFalse(plan["ok"])
        self.assertTrue(any("旧版本正文不可用" in x["by_desc"] for x in plan["conflicts"]))
        self.assertFalse(any((c["payload"].get("_revert") or {}).get("run_id") == "run-integrity"
                             for c in read_commits(self.vault)))
        with connect(self.vault) as db:
            db.execute("INSERT INTO blobs(hash,content,created_at) VALUES (?,?,?)",
                       (old_hash, originals[first["uid"]], "2026-01-01T00:00:00+00:00"))

        original_inverse = revert._inverse
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("模拟第二步中断")
            return original_inverse(*args, **kwargs)

        with mock.patch.object(revert, "_inverse", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "模拟第二步中断"):
                revert.apply_revert(self.vault, "run-integrity")
        pending = revert.plan_revert(self.vault, "run-integrity")
        self.assertTrue(pending["ok"], pending)
        self.assertEqual(len(pending["items"]), 1)
        revert.apply_revert(self.vault, "run-integrity")
        self.assertTrue(revert.plan_revert(self.vault, "run-integrity")["already"])
        for q in (first, second):
            with open(self.path(q), encoding="utf-8") as file:
                self.assertEqual(file.read(), originals[q["uid"]])


if __name__ == "__main__":
    unittest.main()
