"""草稿自动框选的 HTTP 竞态、真实进程重启与入库后独立训练回归。"""
from pathlib import Path
import unittest
from unittest import mock

from omrs import drafts
from omrs.common import save_config
from omrs.ledger import read_commits
from tests import test_draft_p3_http as support


DETECTOR = r'''
def detect(*args, **kwargs):
    Path(vault, "extract-entered").touch()
    if mode == "hold":
        deadline = time.monotonic() + 15
        while not Path(vault, "extract-release").exists() and time.monotonic() < deadline:
            time.sleep(.02)
    return [{"role": "question", "card": 1, "x": 0, "y": 0, "w": 1, "h": 1, "conf": .98}]
ai_assist.detect_regions = detect
'''
SERVER = support.SERVER.replace("class Handler(OMRSHandler):", DETECTOR + "\nclass Handler(OMRSHandler):")


class DraftP4HttpTests(support.DraftP3HttpTests):
    def start_server(self, mode="normal"):
        with mock.patch.object(support, "SERVER", SERVER):
            super().start_server(mode)

    def detect(self, current):
        return self.ok("/api/drafts/detect", {
            "id": current["id"], "revision": current["revision"],
        })["job"]

    def sibling(self):
        return drafts.create_draft(self.vault, {
            "subject": "数学", "category": "函数", "source_images": [self.image["sha256"]],
            "blocks": [{"section": "题目", "kind": "text", "text": "同图另一题"}],
        }, {"conversation_id": "http-conv"})

    def test_p4_detect_applies_once_and_manual_edits_preserve_ai_box(self):
        self.start_server()
        finished = self.wait_job(self.detect(self.item()))
        self.assertEqual(finished["status"], "done", finished)
        self.assertEqual(finished["result"][0]["status"], "applied", finished)
        current = self.item()
        block = current["blocks"][0]
        self.assertEqual(block["box_origin"], "ai")
        original = block["ai_box"]
        current = self.ok("/api/drafts/boxes", {
            "id": current["id"], "revision": current["revision"],
            "blocks": [{"id": block["id"], "box": {"x": .1, "y": .1, "w": .6, "h": .6},
                        "box_origin": "ai_edited", "ai_box": original}],
        })["draft"]
        Path(self.vault, "extract-entered").unlink()
        finished = self.wait_job(self.detect(current))
        self.assertEqual(finished["result"][0]["status"], "skipped", finished)
        self.assertFalse(Path(self.vault, "extract-entered").exists())
        block = self.item()["blocks"][0]
        self.assertEqual(block["ai_box"], original)
        self.assertEqual(block["box"]["x"], .1)

    def test_p4_done_sibling_prevents_model_call(self):
        other = self.sibling()
        drafts.commit_draft(self.vault, other["id"], other["revision"])
        self.start_server()
        finished = self.wait_job(self.detect(self.item()))
        self.assertEqual(finished["result"][0]["status"], "skipped", finished)
        self.assertFalse(Path(self.vault, "extract-entered").exists())
        self.assertIsNone(self.item()["blocks"][0]["box"])

    def test_p4_new_shared_reference_during_detection_prevents_writeback(self):
        self.start_server("hold")
        job = self.detect(self.item())
        self.wait_extract_entered()
        try:
            self.sibling()
        finally:
            Path(self.vault, "extract-release").touch()
        finished = self.wait_job(job)
        self.assertEqual(finished["status"], "conflict", finished)
        self.assertEqual(finished["result"][0]["reason_code"], "shared_image", finished)
        self.assertIsNone(self.item()["blocks"][0]["box"])

    def test_p4_edit_during_detection_remains_responsive_and_conflicts(self):
        self.start_server("hold")
        current = self.item()
        job = self.detect(current)
        self.wait_extract_entered()
        try:
            self.ok("/api/drafts/update", {
                "id": current["id"], "revision": current["revision"],
                "fields": {"note": "检测期间人工保存"}, "blocks": current["blocks"],
            })
        finally:
            Path(self.vault, "extract-release").touch()
        self.assertEqual(self.wait_job(job)["status"], "conflict")
        self.assertEqual(self.item()["note"], "检测期间人工保存")
        self.assertIsNone(self.item()["blocks"][0]["box"])

    def test_p4_restart_interrupts_detection_and_retry_succeeds(self):
        self.start_server("hold")
        job = self.detect(self.item())
        self.wait_extract_entered()
        self.start_server()
        self.assertEqual(self.wait_job(job)["status"], "interrupted")
        self.assertIsNone(self.item()["blocks"][0]["box"])
        self.assertEqual(self.wait_job(self.detect(self.item()))["status"], "done")
        self.assertEqual(self.item()["status"], "review")

    def test_p4_force_crop_after_commit_never_changes_markdown_or_duplicates_question(self):
        save_config(self.vault, {"draft_force_crop": True})
        self.draft = self.sibling()
        self.start_server()
        current = self.item()
        self.assertTrue(current["training_tasks"][0]["force_crop"])
        current = self.ok("/api/drafts/image/train", {
            "id": current["id"], "revision": current["revision"],
            "sha": self.image["sha256"], "enabled": True,
        })["draft"]
        result = self.ok("/api/drafts/commit", {"id": current["id"], "revision": current["revision"]})
        self.assertEqual(result["draft"]["status"], "done")
        path = Path(self.vault, result["result"]["file_path"])
        before = path.read_bytes()
        current = self.item()
        task = current["training_tasks"][0]
        saved = self.ok("/api/drafts/boxes", {
            "id": current["id"], "revision": current["revision"],
            "training_boxes": [{"task_id": task["id"], "section": "题目",
                                "box": support.WHOLE, "box_origin": "manual"}],
        })["draft"]
        self.assertEqual(saved["training_tasks"][0]["status"], "registered")
        self.assertEqual(path.read_bytes(), before)
        stats = self.ok("/api/inbox/dataset/stats")
        self.assertEqual(stats["chat"], {"images": 1, "boxes": 1})
        self.ok("/api/drafts/commit", {"id": saved["id"], "revision": saved["revision"]})
        self.assertEqual(len([c for c in read_commits(self.vault) if c["commit_type"] == "question.create"]), 1)
        self.assertEqual(self.ok("/api/inbox/items")["items"], [])


def load_tests(loader, _tests, _pattern):
    # P3 的共用支持被继承，既有用例仍由原模块单独运行。
    return unittest.TestSuite(DraftP4HttpTests(name) for name in loader.getTestCaseNames(DraftP4HttpTests)
                              if name.startswith("test_p4_"))


if __name__ == "__main__":
    unittest.main()
