"""P3 草稿训练标注、共享登记与安全清理的领域测试。"""
import datetime
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock
import zipfile

from omrs import drafts, inbox
from omrs.agent.store import AgentStore
from omrs.common import omrs_data_dir
from tests.test_drafts import data_url, make_png

WHOLE = {"x": 0, "y": 0, "w": 1, "h": 1}


class DraftTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.conv = "train-conv"
        self.png = make_png(10, 8)
        self.image = drafts.add_image(self.vault, data_url(self.png), self.conv, "run")

    def create(self, category="函数", section="题目", text=False):
        block = {"section": section, "kind": "text", "text": "题目文字"} if text else {
            "section": section, "kind": "image", "image_sha": self.image["sha256"]}
        blocks = [block] if section == "题目" else [
            {"section": "题目", "kind": "text", "text": "题干"}, block]
        return drafts.create_draft(self.vault, {
            "subject": "数学", "category": category, "source_images": [self.image["sha256"]],
            "blocks": blocks}, {"conversation_id": self.conv})

    def box(self, draft, section="题目"):
        block = next(b for b in draft["blocks"] if b["kind"] == "image")
        return drafts.set_boxes(self.vault, draft["id"], draft["revision"],
                                [{"id": block["id"], "box": WHOLE, "box_origin": "manual"}])

    def train(self, draft):
        return drafts.set_image_training(self.vault, draft["id"], draft["revision"],
                                         self.image["sha256"], True)["draft"]

    def export(self):
        with zipfile.ZipFile(io.BytesIO(inbox.export_dataset(self.vault))) as archive:
            return [json.loads(line) for line in archive.read("labels.jsonl").decode().splitlines()]

    def test_training_box_copy_clear_and_text_retention(self):
        d = self.create()
        self.assertEqual(d["training_tasks"][0]["status"], "pending")
        d = self.box(d)
        task = d["training_tasks"][0]
        self.assertEqual((task["status"], task["boxes"][0]["section"]), ("ready", "题目"))
        d = drafts.set_boxes(self.vault, d["id"], d["revision"],
                             training_boxes=[{"task_id": task["id"], "box": None}])
        self.assertEqual(d["training_tasks"][0]["boxes"], [])
        self.assertEqual(d["blocks"][0]["box"], WHOLE)
        d = drafts.update_draft(self.vault, d["id"], d["revision"], {"note": "保留清空选择"}, d["blocks"])
        self.assertEqual(d["training_tasks"][0]["boxes"], [])
        with self.assertRaises(drafts.DraftError):
            drafts.set_boxes(self.vault, d["id"], d["revision"], training_boxes=[
                {"task_id": task["id"], "box": None},
                {"task_id": task["id"], "section": "题目", "box": WHOLE, "box_origin": "manual"}])
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["revision"], d["revision"])
        d = drafts.set_boxes(self.vault, d["id"], d["revision"],
                             training_boxes=[{"task_id": task["id"], "section": "题目",
                                              "box": WHOLE, "box_origin": "manual"}])
        # 模拟成功提取后的同一块转文字；独立训练标注不能消失。
        db = drafts.connect(self.vault)
        try:
            db.execute("UPDATE blocks SET kind='text',text='提取文字',image_sha=NULL,x=NULL,y=NULL,w=NULL,h=NULL WHERE id=?",
                       (d["blocks"][0]["id"],))
            db.commit()
        finally:
            db.close()
        self.assertTrue(drafts.get_draft(self.vault, d["id"])["training_tasks"][0]["boxes"])

    def test_independent_training_box_survives_body_box_changes(self):
        d = self.box(self.create())
        task = d["training_tasks"][0]
        smaller = {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}
        d = drafts.set_boxes(self.vault, d["id"], d["revision"], training_boxes=[
            {"id": task["boxes"][0]["id"], "task_id": task["id"], "section": "题目",
             "box": smaller, "box_origin": "manual"}])
        d = drafts.set_boxes(self.vault, d["id"], d["revision"], [
            {"id": d["blocks"][0]["id"], "box": {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6},
             "box_origin": "manual"}])
        self.assertEqual(len(d["training_tasks"][0]["boxes"]), 1)
        self.assertEqual(d["training_tasks"][0]["boxes"][0]["box"], smaller)

    def test_repointed_body_block_drops_old_source_annotation(self):
        d = self.box(self.create())
        another = drafts.add_image(self.vault, data_url(make_png(5, 6)), self.conv, "run")
        block = {**d["blocks"][0], "image_sha": another["sha256"]}
        d = drafts.update_draft(self.vault, d["id"], d["revision"], {}, [block],
                                source_images=[self.image["sha256"], another["sha256"]])
        by_sha = {task["image_sha"]: task for task in d["training_tasks"]}
        self.assertEqual(by_sha[self.image["sha256"]]["boxes"], [])
        self.assertEqual(len(by_sha[another["sha256"]]["boxes"]), 1)

    def test_deleted_or_unboxed_image_does_not_leave_training_annotation(self):
        d = self.box(self.create())
        block = d["blocks"][0]
        cleared = drafts.set_boxes(self.vault, d["id"], d["revision"],
                                   [{"id": block["id"], "box": None}])
        self.assertEqual(cleared["training_tasks"][0]["boxes"], [])
        d = self.box(cleared)
        text_block = {"section": "题目", "kind": "text", "text": "改成手写文字"}
        d = drafts.update_draft(self.vault, d["id"], d["revision"], {}, [text_block],
                                source_images=[self.image["sha256"]])
        self.assertEqual(d["training_tasks"][0]["boxes"], [])

    def test_multiple_drafts_accumulate_without_modifying_normal_item(self):
        normal = inbox.upload_images(self.vault, [("user.png", self.png)], source="desktop")["items"][0]
        before = inbox.get_item(self.vault, normal["id"])
        self.assertEqual(before["status"], "pending")
        first = self.train(self.box(self.create("函数")))
        second = self.train(self.box(self.create("几何")))
        one = drafts.commit_draft(self.vault, first["id"], first["revision"])
        two = drafts.commit_draft(self.vault, second["id"], second["revision"])
        self.assertEqual(one["training"]["registered"], [self.image["sha256"]])
        self.assertEqual(two["training"]["registered"], [self.image["sha256"]])
        after = inbox.get_item(self.vault, normal["id"])
        self.assertEqual((after["status"], after["layout"], after["source"], after["regions"]),
                         (before["status"], before["layout"], before["source"], before["regions"]))
        records = self.export()
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]["regions"]), 2)
        self.assertEqual(len(records[0]["chat_annotations"]), 2)
        self.assertEqual(inbox.dataset_stats(self.vault)["images"], 1)

    def test_answer_only_image_is_registered_without_question_frame_on_that_image(self):
        d = self.train(self.box(self.create(section="答案")))
        result = drafts.commit_draft(self.vault, d["id"], d["revision"])
        self.assertEqual(result["training"]["registered"], [self.image["sha256"]])
        self.assertEqual(self.export()[0]["regions"][0]["role"], "answer")

    def test_training_failure_is_retryable_without_second_question(self):
        d = self.train(self.box(self.create()))
        real = inbox.register_chat_training
        with mock.patch.object(inbox, "register_chat_training", side_effect=OSError("模拟登记失败")):
            first = drafts.commit_draft(self.vault, d["id"], d["revision"])
        self.assertEqual(first["draft"]["status"], "done")
        self.assertEqual(first["training"]["failed"], [{"sha": self.image["sha256"], "error": "模拟登记失败"}])
        self.assertEqual(first["draft"]["training_tasks"][0]["status"], "error")
        with mock.patch.object(inbox, "register_chat_training", wraps=real) as registering:
            retry = drafts.commit_draft(self.vault, d["id"], d["revision"])
            self.assertEqual(registering.call_count, 1)
        self.assertTrue(retry["reused"])
        self.assertEqual(retry["training"]["registered"], [self.image["sha256"]])
        self.assertEqual(len([c for c in __import__('omrs.ledger', fromlist=['read_commits']).read_commits(self.vault)
                              if c["commit_type"] == "question.create"]), 1)

    def test_chat_registration_retry_replaces_older_box_set(self):
        d = self.box(self.create())
        original = d["training_tasks"][0]["boxes"][0]
        second = {**original, "id": "extra-box", "section": "答案"}
        sha = self.image["sha256"]
        inbox.register_chat_training(self.vault, sha, self.png, d["id"], [original, second])
        inbox.register_chat_training(self.vault, sha, self.png, d["id"], [original])
        self.assertEqual(len(self.export()[0]["regions"]), 1)

    def test_cleanup_only_expired_discarded_and_preserves_live_chat(self):
        store = AgentStore(self.vault)
        store.create_conversation(self.conv, "保留原对话")
        store.add_message(self.conv, "run", {"role": "user", "content": "图", "_images": ["IMG-1"]})
        d = self.create()
        drafts.discard_draft(self.vault, d["id"], d["revision"])
        db = drafts.connect(self.vault)
        try:
            old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=9)).isoformat(timespec="seconds")
            db.execute("UPDATE drafts SET updated_at=? WHERE id=?", (old, d["id"]))
            db.commit()
        finally:
            db.close()
        result = drafts.cleanup(self.vault)
        self.assertEqual(result["cleaned"]["drafts"], 1)
        self.assertTrue(os.path.isfile(drafts.image_path(self.vault, self.image["sha256"])))
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["source_images"], [])
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["training_tasks"], [])
        self.assertEqual(drafts.cleanup(self.vault)["cleaned"]["drafts"], 0)
        self.assertGreaterEqual(result["retained"]["images"], 1)
        # 删除会话后，下一次清理才可删除不再使用的原图。
        store.delete_conversation(self.conv)
        self.assertEqual(drafts.cleanup(self.vault)["cleaned"]["images"], 1)
        with self.assertRaises(ValueError):
            drafts.image_path(self.vault, self.image["sha256"])

    def test_cleanup_protects_cross_store_training_reference_before_pointer_update(self):
        store = AgentStore(self.vault)
        store.create_conversation(self.conv, "训练引用")
        d = self.box(self.create())
        inbox.register_chat_training(self.vault, self.image["sha256"], self.png, d["id"],
                                     d["training_tasks"][0]["boxes"])
        d = drafts.discard_draft(self.vault, d["id"], d["revision"])
        db = drafts.connect(self.vault)
        try:
            old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=9)).isoformat(timespec="seconds")
            db.execute("UPDATE drafts SET updated_at=? WHERE id=?", (old, d["id"]))
            db.commit()
        finally:
            db.close()
        store.delete_conversation(self.conv)
        result = drafts.cleanup(self.vault)
        self.assertEqual(result["cleaned"]["drafts"], 1)
        self.assertEqual(result["cleaned"]["images"], 0)
        self.assertTrue(os.path.isfile(drafts.image_path(self.vault, self.image["sha256"])))

    def test_cleanup_retries_file_removal_after_database_reference_release(self):
        store = AgentStore(self.vault)
        store.create_conversation(self.conv, "文件删除重试")
        d = self.create()
        d = drafts.discard_draft(self.vault, d["id"], d["revision"])
        db = drafts.connect(self.vault)
        try:
            old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=9)).isoformat(timespec="seconds")
            db.execute("UPDATE drafts SET updated_at=? WHERE id=?", (old, d["id"]))
            db.commit()
        finally:
            db.close()
        store.delete_conversation(self.conv)
        with mock.patch("omrs.draft_training.os.remove", side_effect=OSError("模拟删除失败")):
            with self.assertRaises(OSError):
                drafts.cleanup(self.vault)
        self.assertEqual(drafts.cleanup(self.vault)["cleaned"]["images"], 1)

    def test_unattached_recent_image_is_not_cleanup_candidate(self):
        other = drafts.add_image(self.vault, data_url(make_png(5, 5)), self.conv, "run")
        self.assertEqual(drafts.cleanup(self.vault)["cleaned"]["images"], 0)
        self.assertTrue(os.path.isfile(drafts.image_path(self.vault, other["sha256"])))


if __name__ == "__main__":
    unittest.main()
