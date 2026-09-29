"""旧 Vault 升级时的页码、备注及备份恢复边界。"""

import csv
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from omrs.common import HISTORY_HEADERS, parse_yaml_frontmatter
from omrs.indexing import build_index
from omrs.ledger import read_commits, verify_ledger
from omrs.migration import ensure_ledger_bootstrap, normalize_markdown_template
from omrs.optimization import create_backup_export, prepare_backup_import, restore_backup
from omrs.projections import rebuild_projection


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MigrationCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omrs-migration-compat-")
        self.vault = Path(self.tmp.name) / "source"
        self.vault.mkdir()
        question_dir = self.vault / "错题" / "数学" / "函数"
        question_dir.mkdir(parents=True)
        self.with_page = question_dir / "函数1.md"
        self.without_page = question_dir / "函数2.md"
        self.with_page.write_text(self.question_text("页码: p.23\n", "甲"), encoding="utf-8")
        self.without_page.write_text(self.question_text("", "乙"), encoding="utf-8")
        data_dir = self.vault / "错题" / ".omrs"
        data_dir.mkdir()
        with (data_dir / "history_log.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HISTORY_HEADERS)
            writer.writeheader()
            writer.writerow({"Log_ID": "OLD-1", "UID": "函数1", "Date": "2025-01-01",
                             "Action": "review", "Sub_Score": "8", "Is_Correct": "1",
                             "Note": "反馈 note 不等于页码"})
        self.draft_db = data_dir / "drafts" / "drafts.db"
        self.draft_db.parent.mkdir()
        with sqlite3.connect(self.draft_db) as db:
            db.execute("CREATE TABLE legacy_note (body TEXT)")
            db.execute("INSERT INTO legacy_note VALUES (?)", ("草稿 note 不等于页码",))
        self.agent_db = data_dir / "agent.db"
        with sqlite3.connect(self.agent_db) as db:
            db.execute("CREATE TABLE conversation (body TEXT)")
            db.execute("INSERT INTO conversation VALUES (?)", ("聊天数据",))
        self.inbox_db = data_dir / "inbox" / "inbox.db"
        self.annotate_db = data_dir / "annotate" / "annotate.db"
        for path in (self.inbox_db, self.annotate_db):
            path.parent.mkdir()
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE legacy_note (body TEXT)")
                db.execute("INSERT INTO legacy_note VALUES (?)", ("不同存储的备注",))
        self.config = data_dir / "config.json"
        self.config.write_text('{"agent_enabled": true}\n', encoding="utf-8")
        self.anchor = self.vault / "错题/数学/函数.md"
        self.anchor.write_text("# 函数分类锚点\n", encoding="utf-8")
        self.image = self.vault / "错题/附件/图甲.png"
        self.image.parent.mkdir()
        self.image.write_bytes(b"legacy-image-bytes")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def question_text(page, suffix):
        return ("---\n科目: 数学\n分类: \"[[函数]]\"\n难度: 5\n"
                + page + "相关知识点: []\ntags:\n  - 状态/待攻克\n---\n\n"
                + f"# 题目\n\n题目{suffix} ![[图{suffix}.png]]\n\n"
                  f"# 答案\n\n答案{suffix}\n\n# 备注\n\n## 错因\n\n错因{suffix}\n\n"
                  f"## 关联\n\n图片说明{suffix}\n")

    def test_normalization_keeps_old_page_only_when_present_and_preserves_notes(self):
        for page in ("", "页码: p.23\n"):
            original = self.question_text(page, "甲")
            normalized, changed = normalize_markdown_template(
                original, "Q-1", "数学", "函数", 5, page="p.23" if page else "")
            self.assertTrue(changed)
            self.assertEqual("页码" in parse_yaml_frontmatter(normalized), bool(page))
            self.assertIn("错因甲", normalized)
            self.assertIn("图片说明甲", normalized)
            self.assertIn("![[图甲.png]]", normalized)

    def test_bootstrap_is_repeatable_and_keeps_old_page_and_other_notes(self):
        first = ensure_ledger_bootstrap(str(self.vault))
        self.assertEqual(first["status"], "created")
        rebuild_projection(str(self.vault))
        self.assertTrue(verify_ledger(str(self.vault))["valid"])
        before = {path: digest(path) for path in (self.with_page, self.without_page, self.draft_db,
                                                  self.agent_db, self.inbox_db, self.annotate_db,
                                                  self.config, self.anchor, self.image)}
        commits = read_commits(str(self.vault))
        self.assertEqual(len(commits), 2)
        snapshot = {question["uid"]: question["metadata"] for question in
                    commits[1]["payload"]["questions"]}
        self.assertEqual(snapshot["函数1"]["页码"], "p.23")
        self.assertNotIn("页码", snapshot["函数2"])
        self.assertEqual(ensure_ledger_bootstrap(str(self.vault))["status"], "exists")
        self.assertEqual(len(read_commits(str(self.vault))), len(commits))
        self.assertEqual(before, {path: digest(path) for path in before})
        self.assertEqual(parse_yaml_frontmatter(self.with_page.read_text(encoding="utf-8"))["页码"], "p.23")
        self.assertNotIn("页码:", self.without_page.read_text(encoding="utf-8"))
        self.assertIn("反馈 note 不等于页码", (self.vault / "错题/.omrs/history_log.csv").read_text(encoding="utf-8"))
        with sqlite3.connect(self.draft_db) as db:
            self.assertEqual(db.execute("SELECT body FROM legacy_note").fetchone()[0], "草稿 note 不等于页码")

    def test_tracked_scan_entry_is_repeatable(self):
        self.assertEqual(len(build_index(str(self.vault))), 2)
        before = [(item["commit_id"], item["commit_type"]) for item in read_commits(str(self.vault))]
        texts = {path: digest(path) for path in (self.with_page, self.without_page)}
        self.assertEqual(len(build_index(str(self.vault))), 2)
        self.assertEqual([(item["commit_id"], item["commit_type"])
                          for item in read_commits(str(self.vault))], before)
        self.assertEqual({path: digest(path) for path in texts}, texts)

    def test_quiescent_backup_restores_independent_stores_and_legacy_evidence(self):
        ensure_ledger_bootstrap(str(self.vault))
        rebuild_projection(str(self.vault))
        original = {path.relative_to(self.vault / "错题"): digest(path) for path in
                    (self.with_page, self.without_page, self.draft_db, self.agent_db,
                     self.inbox_db, self.annotate_db, self.config, self.anchor, self.image)}
        payload, _, _ = create_backup_export(str(self.vault))
        restored = Path(self.tmp.name) / "restored"
        restored.mkdir()
        prepared = prepare_backup_import(str(restored), payload)
        result = restore_backup(str(restored), prepared["restore_id"], confirm=True)
        self.assertEqual(result["question_count"], 2)
        self.assertTrue(verify_ledger(str(restored))["valid"])
        for relative, expected in original.items():
            self.assertEqual(digest(restored / "错题" / relative), expected)


if __name__ == "__main__":
    unittest.main()
