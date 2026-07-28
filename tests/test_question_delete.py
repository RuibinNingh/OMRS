import os
import tempfile
import unittest

from omrs.creation import create_question
from omrs.ledger import connect, read_commits
from omrs.question_ops import delete_question, get_question_raw
from omrs.workspace_sync import scan_workspace


class QuestionDeletionTests(unittest.TestCase):
    def test_delete_question_archives_projection_and_clears_fingerprint(self):
        with tempfile.TemporaryDirectory() as vault:
            created = create_question(
                vault,
                subject="数学",
                category="代数",
                difficulty=5,
                question_text="测试题目",
            )
            attachment = os.path.join(vault, "错题", "附件", "shared.png")
            os.makedirs(os.path.dirname(attachment), exist_ok=True)
            with open(attachment, "wb") as file:
                file.write(b"shared attachment")

            result = delete_question(vault, created["uid"])

            self.assertTrue(result["archived"])
            self.assertFalse(os.path.exists(os.path.join(vault, created["file_path"])))
            self.assertTrue(os.path.isfile(attachment))
            with self.assertRaisesRegex(RuntimeError, "UID 不存在"):
                get_question_raw(vault, created["uid"])
            scan_workspace(vault)
            with connect(vault) as db:
                archived = db.execute(
                    "SELECT archived FROM question_projection WHERE question_id = ?",
                    (created["question_id"],),
                ).fetchone()
                fingerprints = db.execute("SELECT COUNT(*) AS n FROM workspace_fingerprint").fetchone()
            self.assertEqual(archived["archived"], 1)
            self.assertEqual(fingerprints["n"], 0)
            archives = [
                commit for commit in read_commits(vault, ascending=True)
                if commit["commit_type"] == "question.archive"
            ]
            self.assertEqual(len(archives), 1)


if __name__ == "__main__":
    unittest.main()
