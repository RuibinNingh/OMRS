import os
import tempfile
import unittest

from omrs.catalog import build_tree
from omrs.creation import create_question


class CatalogTreeTests(unittest.TestCase):
    def test_tree_groups_questions_and_skips_data_dir(self):
        with tempfile.TemporaryDirectory() as vault:
            create_question(vault, subject="数学", category="隐圆模型", difficulty=5)
            create_question(vault, subject="数学", category="隐圆模型", difficulty=6)
            create_question(vault, subject="物理", category="动能定理", difficulty=8)

            result = build_tree(vault)
            root = result["root"]

            self.assertEqual(root["name"], "错题")
            self.assertEqual(root["question_count"], 3)
            names = [child["name"] for child in root["children"]]
            self.assertIn("数学", names)
            self.assertIn("物理", names)
            # `.omrs/` 是结构化数据目录，不属于用户的题库目录结构
            self.assertNotIn(".omrs", names)

            math = next(child for child in root["children"] if child["name"] == "数学")
            category = next(child for child in math["children"] if child["name"] == "隐圆模型")
            self.assertEqual(category["question_count"], 2)
            uids = sorted(f["uid"] for f in category["files"] if f["kind"] == "question")
            self.assertEqual(uids, ["隐圆模型1", "隐圆模型2"])
            self.assertTrue(all(f["indexed"] for f in category["files"] if f["kind"] == "question"))

    def test_non_question_files_are_classified_not_counted_as_questions(self):
        with tempfile.TemporaryDirectory() as vault:
            create_question(vault, subject="数学", category="隐圆模型", difficulty=5)
            attach_dir = os.path.join(vault, "错题", "数学", "隐圆模型", "附件")
            os.makedirs(attach_dir, exist_ok=True)
            with open(os.path.join(attach_dir, "图1.png"), "wb") as file:
                file.write(b"png")

            root = build_tree(vault)["root"]
            math = next(child for child in root["children"] if child["name"] == "数学")
            category = next(child for child in math["children"] if child["name"] == "隐圆模型")
            attachments = next(child for child in category["children"] if child["name"] == "附件")

            self.assertEqual(attachments["question_count"], 0)
            self.assertEqual(attachments["files"][0]["kind"], "image")
            # 分类目录的索引 md（隐圆模型.md）不匹配题目命名规则，不能算成题目
            self.assertEqual(category["question_count"], 1)
            self.assertTrue(any(f["kind"] == "markdown" for f in category["files"]))

    def test_orphan_question_file_is_reported(self):
        with tempfile.TemporaryDirectory() as vault:
            create_question(vault, subject="数学", category="隐圆模型", difficulty=5)
            stray = os.path.join(vault, "错题", "数学", "隐圆模型", "隐圆模型9.md")
            with open(stray, "w", encoding="utf-8") as file:
                file.write("---\n科目: 数学\n---\n\n# 题目\n\n手动放进来的\n")

            result = build_tree(vault)

            self.assertEqual(result["summary"]["orphans"], 1)
            self.assertEqual(result["summary"]["questions"], 2)
            self.assertEqual(result["indexed_total"], 1)

    def test_missing_questions_root_returns_empty_tree(self):
        with tempfile.TemporaryDirectory() as vault:
            result = build_tree(vault)

            self.assertEqual(result["root"]["question_count"], 0)
            self.assertEqual(result["root"]["children"], [])
            self.assertEqual(result["summary"]["questions"], 0)


if __name__ == "__main__":
    unittest.main()
