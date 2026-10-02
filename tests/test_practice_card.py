"""P5：聊天练习卡身份、恢复和反馈原子幂等契约。"""
import os
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from omrs.agent.practice import create_practice_card, get_practice, save_progress, start_practice
from omrs.agent.store import AgentStore
from omrs.creation import create_question
from omrs.feedback import process_feedback
from omrs.ledger import connect, read_commits, verify_ledger
from omrs.question_ops import delete_question, move_question, suspend_question


class PracticeCardTests(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-practice-")
        os.makedirs(os.path.join(self.vault, "错题"))
        self.ids = [create_question(self.vault, "数学", "函数", 5, question_text=f"第 {i} 题", answer_text="答案")["uid"] for i in range(3)]
        self.store = AgentStore(self.vault)
        self.store.create_conversation("conv", "练习")
        self.store.create_run("run", "conv", "faux")
        self.ctx = {"vault": self.vault, "conversation_id": "conv", "run_id": "run", "tool_call_id": "call"}

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def card(self):
        args = {"title": "函数巩固", "items": [{"uid": uid, "source": "due"} for uid in self.ids]}
        return create_practice_card(self.ctx, args)["result"]

    def attempts(self, qid):
        with connect(self.vault) as db:
            return db.execute("SELECT attempts FROM mastery_projection WHERE question_id=?", (qid,)).fetchone()[0]

    def test_creation_start_refresh_and_lost_response_are_idempotent(self):
        card = self.card()
        self.assertEqual(self.card()["card_id"], card["card_id"])
        opened = start_practice(self.vault, card["card_id"])
        self.assertEqual([i["uid"] for i in opened["items"]], self.ids)
        self.assertEqual(start_practice(self.vault, card["card_id"])["attempt_id"], opened["attempt_id"])
        qid = card["items"][0]["question_id"]
        self.assertEqual(self.attempts(qid), 0)
        entry = {"question_id": qid, "uid": self.ids[0], "is_correct": True, "sub_score": 8, "entry_id": qid}
        first = process_feedback(self.vault, [entry], opened["session_id"], attempt_id=opened["attempt_id"])
        second = process_feedback(self.vault, [entry], opened["session_id"], attempt_id=opened["attempt_id"])
        self.assertEqual([x["status"] for x in first], ["ok"])
        self.assertEqual([x["status"] for x in second], ["ok"])
        self.assertEqual(self.attempts(qid), 1, [c["payload"] for c in read_commits(self.vault) if c["commit_type"] == "review.batch_submit"])
        with self.assertRaises(ValueError):
            process_feedback(self.vault, [entry], opened["session_id"])
        self.assertEqual(len([c for c in read_commits(self.vault) if c["commit_type"] == "review.batch_submit"]), 1)
        self.assertEqual(get_practice(self.vault, card["card_id"])["submitted"], [qid])
        again = start_practice(self.vault, card["card_id"], restart=True, request_id="retry-1")
        self.assertEqual(start_practice(self.vault, card["card_id"], restart=True, request_id="retry-1")["attempt_id"], again["attempt_id"])
        self.assertNotEqual(again["attempt_id"], opened["attempt_id"])
        self.assertEqual(get_practice(self.vault, card["card_id"])["attempt_id"], again["attempt_id"])
        self.assertEqual(start_practice(self.vault, card["card_id"])["attempt_id"], again["attempt_id"])
        save_progress(self.vault, again["attempt_id"], {"seq": 2, "index": 1, "results": {qid: {"correct": True}}})
        save_progress(self.vault, again["attempt_id"], {"seq": 1, "index": 0, "results": {}})
        self.assertEqual(get_practice(self.vault, card["card_id"])["progress"]["index"], 1)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_partial_error_retry_and_deleted_chat(self):
        card = self.card()
        opened = start_practice(self.vault, card["card_id"])
        entries = [{"question_id": i["question_id"], "uid": i["uid_at_creation"], "entry_id": i["question_id"], "is_correct": True, "sub_score": 8} for i in card["items"]]
        entries[1]["sub_score"] = 99
        result = process_feedback(self.vault, entries, opened["session_id"], attempt_id=opened["attempt_id"])
        self.assertEqual([x["status"] for x in result], ["ok", "error", "ok"])
        entries[1]["sub_score"] = 4
        result = process_feedback(self.vault, entries, opened["session_id"], attempt_id=opened["attempt_id"])
        self.assertEqual([x["status"] for x in result], ["ok", "ok", "ok"])
        self.assertEqual([self.attempts(i["question_id"]) for i in card["items"]], [1, 1, 1])
        self.store.delete_conversation("conv")
        with self.assertRaises(ValueError):
            start_practice(self.vault, card["card_id"], restart=True)
        self.assertEqual(get_practice(self.vault, card["card_id"], attempt_id=opened["attempt_id"])["attempt_id"], opened["attempt_id"])

    def test_parallel_same_entry_has_one_ledger_effect(self):
        card = self.card()
        opened = start_practice(self.vault, card["card_id"])
        qid = card["items"][0]["question_id"]
        entry = {"question_id": qid, "entry_id": qid, "uid": self.ids[0], "is_correct": True, "sub_score": 8}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(process_feedback, self.vault, [entry], opened["session_id"], opened["attempt_id"]) for _ in range(2)]
            self.assertEqual([f.result()[0]["status"] for f in futures], ["ok", "ok"])
        self.assertEqual(self.attempts(qid), 1, [c["payload"] for c in read_commits(self.vault) if c["commit_type"] == "review.batch_submit"])
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_reject_forged_attempt_and_card_move_suspend(self):
        card = self.card()
        qid = card["items"][0]["question_id"]
        with self.assertRaises(ValueError):
            process_feedback(self.vault, [{"question_id": qid, "entry_id": qid, "uid": self.ids[0], "is_correct": True, "sub_score": 8}], "IMM-forged", attempt_id="forged")
        move_question(self.vault, self.ids[0], "数学", "数列")
        suspend_question(self.vault, self.ids[1], "暂缓")
        opened = start_practice(self.vault, card["card_id"])
        self.assertNotEqual(opened["items"][0]["uid"], self.ids[0])
        save_progress(self.vault, opened["attempt_id"], {"seq": 1, "results": {qid: {"correct": True}}})
        self.assertTrue(get_practice(self.vault, card["card_id"])["progress"]["results"][qid]["correct"])
        self.assertEqual([x["question_id"] for x in opened["unavailable"]], [card["items"][1]["question_id"]])
        forged_uid = {"question_id": qid, "entry_id": qid, "uid": self.ids[2], "source": "proficiency", "is_correct": True, "sub_score": 8}
        from omrs.data_repository import IdentityConflict
        with self.assertRaises(IdentityConflict):
            process_feedback(self.vault, [forged_uid], opened["session_id"], attempt_id=opened["attempt_id"])
        valid = {**forged_uid, "uid": opened["items"][0]["uid"]}
        result = process_feedback(self.vault, [valid], opened["session_id"], attempt_id=opened["attempt_id"])
        self.assertEqual(result[0]["question_id"], qid)
        self.assertEqual(result[0]["source"], "due", "排期来源以卡片服务端快照为准")
        self.assertEqual(self.attempts(card["items"][2]["question_id"]), 0, "伪造 UID 不能把反馈记到另一题")
        delete_question(self.vault, self.ids[2])
        self.assertEqual(len(get_practice(self.vault, card["card_id"])["unavailable"]), 2)
        deleted = {"question_id": card["items"][2]["question_id"], "entry_id": card["items"][2]["question_id"],
                   "uid": self.ids[0], "is_correct": True, "sub_score": 8}
        deleted.pop("uid", None)
        result = process_feedback(self.vault, [deleted], opened["session_id"], attempt_id=opened["attempt_id"])
        self.assertEqual(result[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
