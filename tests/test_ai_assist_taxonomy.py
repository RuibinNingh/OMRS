import csv
import json
import tempfile
import unittest
from unittest import mock

from omrs import ai_assist
from omrs.common import MASTERY_HEADERS, mastery_path


def write_mastery(vault, rows):
    path = mastery_path(vault)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=MASTERY_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


class AiAssistTaxonomyTests(unittest.TestCase):
    def test_collect_taxonomy_groups_categories_by_subject(self):
        with tempfile.TemporaryDirectory() as vault:
            write_mastery(
                vault,
                [
                    {"Subject": "数学", "Category": "三角函数", "Knowledge_Tags": "正弦"},
                    {"Subject": "生物", "Category": "遗传", "Knowledge_Tags": "减数分裂"},
                ],
            )

            taxonomy = ai_assist.collect_taxonomy(vault)

        self.assertEqual(taxonomy["categories_by_subject"]["数学"], ["三角函数"])
        self.assertEqual(taxonomy["categories_by_subject"]["生物"], ["遗传"])
        self.assertIn("- 数学: 三角函数", ai_assist._format_category_tree(taxonomy))
        self.assertIn("- 生物: 遗传", ai_assist._format_category_tree(taxonomy))

    def test_classify_rejects_existing_category_from_other_subject(self):
        with tempfile.TemporaryDirectory() as vault:
            write_mastery(
                vault,
                [
                    {"Subject": "数学", "Category": "三角函数", "Knowledge_Tags": "正弦"},
                    {"Subject": "生物", "Category": "遗传", "Knowledge_Tags": "减数分裂"},
                ],
            )
            fake_reply = json.dumps(
                {
                    "subject": "生物",
                    "category": "三角函数",
                    "difficulty": 6,
                    "knowledge_tags": ["三角函数", "减数分裂"],
                },
                ensure_ascii=False,
            )

            with mock.patch.object(ai_assist, "_call_model", return_value=fake_reply):
                result = ai_assist.classify_question(
                    vault, "data:image/png;base64,xxx", restrict_tags=True
                )

        self.assertEqual(result["subject"], "生物")
        self.assertEqual(result["category"], "")
        self.assertEqual(result["knowledge_tags"], ["减数分裂"])

    def test_classify_rejects_existing_category_when_subject_name_is_new(self):
        with tempfile.TemporaryDirectory() as vault:
            write_mastery(
                vault,
                [
                    {"Subject": "数学", "Category": "三角函数", "Knowledge_Tags": "正弦"},
                    {"Subject": "生物", "Category": "遗传", "Knowledge_Tags": "减数分裂"},
                ],
            )
            fake_reply = json.dumps(
                {
                    "subject": "生物学",
                    "category": "三角函数",
                    "difficulty": 6,
                    "knowledge_tags": ["三角函数", "减数分裂"],
                },
                ensure_ascii=False,
            )

            with mock.patch.object(ai_assist, "_call_model", return_value=fake_reply):
                result = ai_assist.classify_question(
                    vault, "data:image/png;base64,xxx", restrict_tags=True
                )

        self.assertEqual(result["subject"], "生物学")
        self.assertEqual(result["category"], "")
        self.assertEqual(result["knowledge_tags"], ["减数分裂"])


if __name__ == "__main__":
    unittest.main()
