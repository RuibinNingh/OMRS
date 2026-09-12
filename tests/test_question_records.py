"""GET /api/question 的 records[]：正式练习记录来自 Ledger 投影（history_log.csv），不是 Markdown # 历史。"""
import os
import tempfile
import unittest

from omrs.common import HISTORY_HEADERS, MASTERY_HEADERS, history_path, mastery_path, save_csv
from omrs.ledger import connect
from omrs.stats import get_question_content, get_question_records


def _write_question(vault, rel_path, body):
    path = os.path.join(vault, *rel_path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def _mastery_row(uid, file_path, attempts):
    row = {header: "" for header in MASTERY_HEADERS}
    row.update({"UID": uid, "File_Path": file_path, "Attempts": str(attempts), "Mastery": "0.4", "EF": "2.5"})
    return row


class QuestionRecordsTests(unittest.TestCase):
    def _vault(self, tmp):
        _write_question(
            tmp,
            "错题/数学/三角函数/三角函数7.md",
            "---\n科目: 数学\n难度: 6\n---\n\n# 题目\n求最值\n\n# 答案\n2\n\n# 历史\n2020-01-01 主观:1, 错, 备注:这是早已废弃的旧行\n",
        )
        save_csv(mastery_path(tmp), MASTERY_HEADERS, [_mastery_row("三角函数7", "错题/数学/三角函数/三角函数7.md", 2)])
        with connect(tmp) as db:
            db.execute(
                "INSERT INTO question_projection(question_id, uid, file_path, subject, category, difficulty, current_tag,"
                " metadata_json, metadata_hash, content_hash, archived, suspended, updated_seq)"
                " VALUES ('OP-000001','三角函数7','错题/数学/三角函数/三角函数7.md','数学','三角函数',6,'',"
                "'{}','','',0,0,1)"
            )
            db.commit()
        save_csv(
            history_path(tmp),
            HISTORY_HEADERS,
            [
                # 老行：没有 Question_ID，按 UID 匹配
                {"Log_ID": "legacy-1", "UID": "三角函数7", "Date": "2026-04-02", "Action": "Feedback", "Sub_Score": "3", "Is_Correct": "0", "Session_ID": "S1", "Note": "辅助角公式方向记反", "Question_ID": ""},
                # 改名前的 UID，但 Question_ID 对得上 → 仍算这道题
                {"Log_ID": "C2-001", "UID": "三角函数旧名", "Date": "2026-04-09 20:11", "Action": "Feedback", "Sub_Score": "6", "Is_Correct": "1", "Session_ID": "S2", "Note": "", "Question_ID": "OP-000001"},
                # 别的题
                {"Log_ID": "C3-001", "UID": "导数应用2", "Date": "2026-04-10 09:00", "Action": "Feedback", "Sub_Score": "9", "Is_Correct": "1", "Session_ID": "S2", "Note": "", "Question_ID": "OP-000002"},
            ],
        )

    def test_records_come_from_ledger_projection_not_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._vault(tmp)
            records = get_question_records(tmp, "三角函数7")
            detail = get_question_content(tmp, "三角函数7")

        self.assertEqual([r["log_id"] for r in records], ["legacy-1", "C2-001"])
        self.assertEqual(records[0], {
            "log_id": "legacy-1", "date": "2026-04-02", "time": "", "score": 3, "correct": False,
            "note": "辅助角公式方向记反", "session_id": "S1",
        })
        self.assertEqual(records[1]["date"], "2026-04-09")
        self.assertEqual(records[1]["time"], "20:11")
        self.assertTrue(records[1]["correct"])
        self.assertEqual(detail["records"], records)
        # Markdown 旧行仍原样透传（兼容），但不参与 records
        self.assertIn("早已废弃", detail["history"])
        self.assertFalse(any("废弃" in r["note"] for r in records))

    def test_no_history_gives_empty_list_not_missing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._vault(tmp)
            save_csv(history_path(tmp), HISTORY_HEADERS, [])
            detail = get_question_content(tmp, "三角函数7")
        self.assertEqual(detail["records"], [])
        self.assertEqual(get_question_records(tmp, ""), [])


if __name__ == "__main__":
    unittest.main()
