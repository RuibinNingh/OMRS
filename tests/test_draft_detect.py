"""P4 草稿自动框选的来源、歧义、训练与并发边界。"""
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from omrs import drafts, inbox
from omrs.common import config_path
from tests.test_drafts import data_url, make_png


QUESTION = {"role": "question", "card": 1, "x": 0.1, "y": 0.1, "w": 0.7, "h": 0.4, "conf": 0.9}
ANSWER = {"role": "answer", "card": 1, "x": 0.1, "y": 0.6, "w": 0.7, "h": 0.3, "conf": 0.8}


class DraftDetectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.conv = "detect-conv"
        self.image = drafts.add_image(self.vault, data_url(make_png(10, 12)), self.conv, "run")

    def configure(self, **values):
        with open(config_path(self.vault), "w", encoding="utf-8") as file:
            json.dump(values, file)

    def create(self, text_only=False):
        block = {"section": "题目", "kind": "text", "text": "已经转成文字"} if text_only else {
            "section": "题目", "kind": "image", "image_sha": self.image["sha256"]}
        return drafts.create_draft(self.vault, {"subject": "数学", "category": "函数",
                     "source_images": [self.image["sha256"]], "blocks": [block]},
                     {"conversation_id": self.conv})

    def wait_job(self, job):
        limit = time.monotonic() + 3
        while time.monotonic() < limit:
            current = drafts.get_job(self.vault, job["id"])
            if current["done"]:
                return current
            time.sleep(0.01)
        self.fail("自动框选作业未结束")

    def test_unique_candidate_applies_to_body_and_training(self):
        d = self.create()
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", return_value=[QUESTION]):
            job = self.wait_job(drafts.start_detect(self.vault, d["id"], d["revision"]))
        current = drafts.get_draft(self.vault, d["id"])
        self.assertEqual((job["status"], job["result"][0]["status"]), ("done", "applied"))
        self.assertEqual(current["blocks"][0]["box_origin"], "ai")
        self.assertEqual(current["blocks"][0]["ai_box"], {key: QUESTION[key] for key in ("x", "y", "w", "h")})
        self.assertEqual(current["training_tasks"][0]["boxes"][0]["box_origin"], "ai")
        self.assertEqual(current["revision"], d["revision"] + 1)

    def test_candidate_coordinates_do_not_depend_on_dictionary_order(self):
        """归一化字典的键顺序改变，正文和训练框仍须使用同一组坐标。"""
        from omrs.draft_write import _box
        expected = {"x": 0.1, "y": 0.15, "w": 0.6, "h": 0.55}
        candidate = {**QUESTION, **expected}
        def reversed_box(value):
            result = _box(value)
            return {key: result[key] for key in ("h", "w", "y", "x")}
        draft = self.create()
        with mock.patch("omrs.draft_detect._box", side_effect=reversed_box), \
                mock.patch("omrs.draft_detect.ai_assist.detect_regions", return_value=[candidate]):
            job = self.wait_job(drafts.start_detect(self.vault, draft["id"], draft["revision"]))
        current = drafts.get_draft(self.vault, draft["id"])
        self.assertEqual(job["status"], "done")
        self.assertEqual(current["blocks"][0]["box"], expected)
        self.assertEqual(current["blocks"][0]["ai_box"], expected)
        self.assertEqual(current["training_tasks"][0]["boxes"][0]["box"], expected)

    def test_local_provider_slices_tall_source_image(self):
        try:
            import PIL  # noqa: F401 - 条带裁图的可选依赖
        except ImportError:
            self.skipTest("当前环境没有 Pillow，收件箱规则会回退整图")
        self.configure(inbox_detect_provider="local_http", inbox_local_detect_url="http://127.0.0.1:1/detect")
        tall = drafts.add_image(self.vault, data_url(make_png(10, 90)), self.conv, "run")
        d = drafts.create_draft(self.vault, {"subject": "数学", "category": "函数",
            "source_images": [tall["sha256"]], "blocks": [
                {"section": "题目", "kind": "image", "image_sha": tall["sha256"]}]},
            {"conversation_id": self.conv})
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions_local", return_value=[QUESTION]) as local:
            job = self.wait_job(drafts.start_detect(self.vault, d["id"], d["revision"]))
        self.assertGreater(local.call_count, 1)
        self.assertEqual(job["status"], "done")
        self.assertTrue(job["result"][0]["candidates"])
        self.assertTrue(all(call.kwargs["layout"] == "other" for call in local.call_args_list))

    def test_legacy_template_config_uses_vlm_without_uploading_draft(self):
        self.configure(inbox_detect_provider="template")
        d = self.create()
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", return_value=[QUESTION]) as model:
            job = self.wait_job(drafts.start_detect(self.vault, d["id"], d["revision"]))
        self.assertEqual(job["result"][0]["status"], "applied")
        model.assert_called_once()
        self.assertEqual(len(inbox.list_items(self.vault)), 0)

    def test_ambiguous_candidates_are_suggestions_only(self):
        d = self.create()
        candidates = [QUESTION, {**QUESTION, "y": 0.55, "h": 0.3}]
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", return_value=candidates):
            job = self.wait_job(drafts.start_detect(self.vault, d["id"], d["revision"]))
        self.assertEqual((job["status"], job["result"][0]["status"], job["result"][0]["reason_code"]),
                         ("done", "suggested", "ambiguous"))
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["blocks"][0]["box"], None)

    def test_shared_and_manual_images_skip_without_calling_provider(self):
        first = self.create()
        second = self.create()
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions") as provider:
            job = self.wait_job(drafts.start_detect(self.vault, first["id"], first["revision"]))
        self.assertEqual(job["result"][0]["reason_code"], "shared_image")
        provider.assert_not_called()
        second = drafts.discard_draft(self.vault, second["id"], second["revision"])
        first = drafts.set_boxes(self.vault, first["id"], first["revision"], [
            {"id": first["blocks"][0]["id"], "box": {"x": 0, "y": 0, "w": 1, "h": 1},
             "box_origin": "manual"}])
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions") as provider:
            job = self.wait_job(drafts.start_detect(self.vault, first["id"], first["revision"]))
        self.assertEqual(job["result"][0]["reason_code"], "manual_box")
        provider.assert_not_called()

    def test_late_edit_conflicts_and_duplicate_start_reuses_job(self):
        d = self.create()
        entered, release = threading.Event(), threading.Event()

        def slow_detect(*_args, **_kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return [QUESTION]

        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", side_effect=slow_detect):
            job = drafts.start_detect(self.vault, d["id"], d["revision"])
            self.assertTrue(entered.wait(2))
            duplicate = drafts.start_detect(self.vault, d["id"], d["revision"])
            self.assertEqual(duplicate["id"], job["id"])
            changed = drafts.update_draft(self.vault, d["id"], d["revision"], {"note": "人工编辑"}, d["blocks"])
            release.set()
            final = self.wait_job(job)
        self.assertEqual((final["status"], final["result"][0]["status"]), ("conflict", "conflict"))
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["revision"], changed["revision"])

    def test_detect_and_extract_on_same_image_are_mutually_exclusive(self):
        d = drafts.create_draft(self.vault, {"subject": "数学", "category": "函数",
            "source_images": [self.image["sha256"]], "blocks": [
                {"section": "题目", "kind": "image", "image_sha": self.image["sha256"]},
                {"section": "答案", "kind": "image", "image_sha": self.image["sha256"]}]},
            {"conversation_id": self.conv})
        d = drafts.set_boxes(self.vault, d["id"], d["revision"], [
            {"id": d["blocks"][0]["id"], "box": {"x": 0, "y": 0, "w": 1, "h": 1},
             "box_origin": "ai"}])
        entered, release = threading.Event(), threading.Event()

        def slow_detect(*_args, **_kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return [ANSWER]

        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", side_effect=slow_detect):
            detecting = drafts.start_detect(self.vault, d["id"], d["revision"])
            self.assertTrue(entered.wait(2))
            with self.assertRaises(drafts.DraftError) as caught:
                drafts.start_extract(self.vault, d["id"], d["revision"], [d["blocks"][0]["id"]])
            self.assertEqual((caught.exception.status, caught.exception.code), (409, "operation_pending"))
            release.set()
            self.wait_job(detecting)

        # 新草稿验证反向：提取运行中，同图检测也不能开始。
        other = drafts.create_draft(self.vault, {"subject": "数学", "category": "几何",
            "source_images": [self.image["sha256"]], "blocks": [
                {"section": "题目", "kind": "image", "image_sha": self.image["sha256"]}]},
            {"conversation_id": self.conv})
        other = drafts.set_boxes(self.vault, other["id"], other["revision"], [
            {"id": other["blocks"][0]["id"], "box": {"x": 0, "y": 0, "w": 1, "h": 1},
             "box_origin": "manual"}])
        entered.clear()
        release.clear()

        def slow_extract(*_args, **_kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return {"text": "转文字"}

        with mock.patch("omrs.draft_jobs.ai_assist.extract_region", side_effect=slow_extract):
            extracting = drafts.start_extract(self.vault, other["id"], other["revision"],
                                               [other["blocks"][0]["id"]])
            self.assertTrue(entered.wait(2))
            with self.assertRaises(drafts.DraftError) as caught:
                drafts.start_detect(self.vault, other["id"], other["revision"])
            self.assertEqual((caught.exception.status, caught.exception.code), (409, "operation_pending"))
            release.set()
            self.wait_job(extracting)

    def test_jobs_order_uses_insert_order_when_created_in_same_second(self):
        d = self.create()
        db = drafts.connect(self.vault)
        try:
            for job_id in ("dj_z_old", "dj_a_new"):
                db.execute("INSERT INTO draft_jobs(id,draft_id,type,status,revision,snapshot_json,processed,total,"
                           "result_json,errors_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (job_id, d["id"], "detect", "error", d["revision"], "[]", 0, 0,
                            "[]", "[]", "2026-09-29T00:00:00+00:00", "2026-09-29T00:00:00+00:00"))
            db.commit()
        finally:
            db.close()
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["jobs"][0]["id"], "dj_a_new")

    def test_force_crop_text_draft_can_commit_before_detect_and_register(self):
        self.configure(draft_force_crop=True, draft_train_default=True)
        d = self.create(text_only=True)
        self.assertTrue(d["training_tasks"][0]["force_crop"])
        self.assertEqual(d["status"], "review")
        committed = drafts.commit_draft(self.vault, d["id"], d["revision"])
        path = os.path.join(self.vault, committed["result"]["file_path"])
        with open(path, "rb") as file:
            before = file.read()
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", return_value=[QUESTION, ANSWER]):
            job = self.wait_job(drafts.start_detect(self.vault, d["id"], committed["draft"]["revision"]))
        current = drafts.get_draft(self.vault, d["id"])
        with open(path, "rb") as file:
            self.assertEqual(file.read(), before)
        self.assertEqual((job["status"], current["status"], current["blocks"][0]["kind"]),
                         ("done", "done", "text"))
        self.assertEqual(current["training_tasks"][0]["status"], "registered")
        self.assertEqual(inbox.dataset_stats(self.vault)["chat"], {"images": 1, "boxes": 2})

    def test_old_text_draft_manual_detect_marks_only_its_task_force_crop(self):
        d = self.create(text_only=True)
        self.assertFalse(d["training_tasks"][0]["force_crop"])
        with mock.patch("omrs.draft_detect.ai_assist.detect_regions", return_value=[QUESTION]):
            job = self.wait_job(drafts.start_detect(self.vault, d["id"], d["revision"], self.image["sha256"]))
        self.assertEqual(job["result"][0]["status"], "applied")
        current = drafts.get_draft(self.vault, d["id"])
        self.assertTrue(current["training_tasks"][0]["force_crop"])
        self.assertEqual(current["blocks"][0]["kind"], "text")


if __name__ == "__main__":
    unittest.main()
