"""ai-draft P1-2：对话附图。消息存储格式、两种看图方式（直接看图 / 转述）、转述缓存与失败、插话与数量限制。

模型与转述都用替身，不联网。
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs import drafts  # noqa: E402
from omrs.agent import images as agent_images  # noqa: E402
from omrs.agent import runtime as agent_runtime  # noqa: E402
from omrs.agent.runtime import AgentError, AgentRuntime, model_messages  # noqa: E402
from omrs.common import load_config, save_config  # noqa: E402
from omrs.llm.openai_compat import ChatResult, estimate_tokens  # noqa: E402
from tests.test_drafts import data_url, make_png  # noqa: E402

TRANSCRIPT = {"summary": "作业帮截图", "layout": "zuoyebang",
              "blocks": [{"role": "question", "text": "求 $x^2=4$ 的解", "convertible": True, "reason": ""},
                         {"role": "answer", "text": "见图", "convertible": False, "reason": "底部有函数图像"}]}


def png(n):
    return data_url(make_png(4 + n, 4, (n * 20 % 256, 0, 0)))


class StubClient:
    def __init__(self):
        self.seen = []
        self.done = threading.Event()

    def complete(self, messages, tools=None, **kw):
        self.seen.append(messages)
        self.done.set()
        return ChatResult(content="好的", reasoning="", tool_calls=[], finish_reason="stop", error="",
                          usage={"prompt": 1, "completion": 1, "cached": 0, "reasoning": 0},
                          ttft_ms=1, duration_ms=1, gen_ms=1)

    def cancel(self):
        pass


class ExpandTest(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-img-")
        os.makedirs(os.path.join(self.vault, "错题"))
        self.events = []

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def emit(self, kind, data):
        self.events.append((kind, data))

    def msg(self, text, *urls):
        refs = [drafts.add_image(self.vault, u, "conv", "run")["ref"] for u in urls]
        return {"role": "user", "content": text, "_images": refs}

    def test_no_images_returns_same_list(self):
        stored = [{"role": "user", "content": "你好"}]
        self.assertIs(agent_images.expand_images(self.vault, "conv", stored, True, self.emit), stored)

    def test_vision_expands_only_latest_four(self):
        stored = [self.msg("第一条", png(1), png(2), png(3)), {"role": "assistant", "content": "嗯"},
                  self.msg("第二条", png(4), png(5))]
        out = model_messages(agent_images.expand_images(self.vault, "conv", stored, True, self.emit))
        urls = [p for m in out if isinstance(m["content"], list) for p in m["content"] if p["type"] == "image_url"]
        self.assertEqual(len(urls), 4)
        first = " ".join(p.get("text", "") for p in out[0]["content"])
        self.assertIn("[IMG-1 已省略，需要时调 describe_image]", first)
        self.assertIn("[IMG-2]", first)
        self.assertNotIn("_images", out[2])
        self.assertEqual(stored[0]["content"], "第一条")  # 存储副本不被改动
        self.assertEqual(self.events, [])

    def test_transcribe_mode_caches_by_sha_and_model(self):
        stored = [self.msg("看这题", png(1))]
        with mock.patch.object(agent_images, "transcribe_image", return_value=TRANSCRIPT) as fake:
            out = agent_images.expand_images(self.vault, "conv", stored, False, self.emit)
            again = agent_images.expand_images(self.vault, "conv", stored, False, self.emit)
        self.assertEqual(fake.call_count, 1)
        self.assertIsInstance(out[0]["content"], str)
        self.assertIn("[IMG-1 转述]", out[0]["content"])
        self.assertIn("需留图：底部有函数图像", out[0]["content"])
        self.assertEqual(out[0]["content"], again[0]["content"])
        self.assertEqual([k for k, _ in self.events], ["image.transcribe", "image.transcribed"])

    def test_transcribe_usage_has_run_identity_and_cache_is_not_model_cache(self):
        stored = [self.msg("看这题", png(1))]
        def fake_transcribe(_vault, _url, usage_callback=None):
            usage_callback({"input_total": 12, "output_total": 3, "cache_read": 0, "scope": "aux"})
            return TRANSCRIPT
        with mock.patch.object(agent_images, "transcribe_image", side_effect=fake_transcribe) as fake:
            agent_images.expand_images(self.vault, "conv", stored, False, self.emit, run_id="run_test")
            agent_images.expand_images(self.vault, "conv", stored, False, self.emit, run_id="run_test")
        self.assertEqual(fake.call_count, 1)
        usages = [data for kind, data in self.events if kind == "usage.aux"]
        self.assertEqual(len(usages), 1)
        self.assertTrue(usages[0]["request_id"].startswith("run_test:transcribe:IMG-1:"))
        self.assertEqual(usages[0]["usage"]["cache_read"], 0)

    def test_transcribe_failure_is_text_not_crash(self):
        stored = [self.msg("", png(1))]
        with mock.patch.object(agent_images, "transcribe_image", side_effect=ValueError("尚未配置 AI")):
            out = agent_images.expand_images(self.vault, "conv", stored, False, self.emit)
        self.assertIn("[IMG-1 转述失败：尚未配置 AI。可调 describe_image 再试]", out[0]["content"])
        self.assertTrue(out[0]["content"].startswith("（只发了图片）"))
        self.assertFalse(self.events[-1][1]["ok"])

    def test_transcript_truncated(self):
        long = {"summary": "长", "blocks": [{"role": "question", "text": "字" * 5000, "convertible": True}]}
        text = agent_images.render_transcript("IMG-1", long)
        self.assertLess(len(text), agent_images.TRANSCRIPT_CAP + 60)
        self.assertIn("已截断", text)

    def test_token_estimate_handles_parts(self):
        parts = [{"type": "text", "text": "abc"}, {"type": "image_url", "image_url": {"url": "x"}}]
        self.assertGreater(estimate_tokens(parts), 1000)


class PostMessageTest(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-img-")
        os.makedirs(os.path.join(self.vault, "错题"))
        cfg = load_config(self.vault)
        cfg.update({"agent_enabled": True, "agent_base_url": "http://127.0.0.1:9", "agent_api_key": "k",
                    "agent_model": "m", "agent_vision": True})
        save_config(self.vault, cfg)
        self.client = StubClient()
        patcher = mock.patch.object(agent_runtime, "make_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rt = AgentRuntime(self.vault)
        self.conv = self.rt.create_conversation("")["id"]

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def wait(self, run_id):
        import time
        deadline = time.monotonic() + 5
        while self.rt.store.run(run_id)["status"] != "done" and time.monotonic() < deadline:
            self.rt.events(run_id, 0, 0.1)
            time.sleep(0.01)
        self.assertEqual(self.rt.store.run(run_id)["status"], "done")

    def test_text_only_message_format_unchanged(self):
        out = self.rt.post_message(self.conv, "你好")
        self.wait(out["run_id"])
        stored = [m for m in self.rt.store.messages(self.conv) if m["role"] == "user"]
        self.assertEqual({k: v for k, v in stored[0].items() if not k.startswith("_") or k == "_images"},
                         {"role": "user", "content": "你好"})

    def test_images_are_stored_as_refs_and_sent_as_image_url(self):
        out = self.rt.post_message(self.conv, "", [png(1), png(2), png(1)])
        self.wait(out["run_id"])
        user = [m for m in self.rt.store.messages(self.conv) if m["role"] == "user"][0]
        self.assertEqual(user["_images"], ["IMG-1", "IMG-2"])
        self.assertEqual(user["content"], "")
        sent = self.client.seen[0][-1]["content"]
        self.assertEqual(sum(1 for p in sent if p["type"] == "image_url"), 2)
        item = self.rt.conversation(self.conv)["items"][0]
        self.assertEqual([i["ref"] for i in item["images"]], ["IMG-1", "IMG-2"])
        self.assertTrue(self.rt.store.conversation(self.conv)["title"].startswith("[图片] IMG-1"))

    def test_too_many_or_bad_images_rejected_without_run(self):
        with self.assertRaises(AgentError) as ctx:
            self.rt.post_message(self.conv, "x", [png(i) for i in range(7)])
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(AgentError) as ctx:
            self.rt.post_message(self.conv, "x", [png(1), "data:image/png;base64,AAAA"])
        self.assertIn("第 2 张图片", ctx.exception.msg)
        self.assertEqual(self.rt.store.message_count(self.conv), 0)
        self.assertEqual(self.rt.store.runs(self.conv), [])

    def test_steer_with_image_is_409(self):
        gate = threading.Event()
        orig = self.client.complete

        def slow(messages, tools=None, **kw):
            gate.wait(5)
            return orig(messages, tools, **kw)
        self.client.complete = slow
        out = self.rt.post_message(self.conv, "第一条")
        try:
            with self.assertRaises(AgentError) as ctx:
                self.rt.post_message(self.conv, "插话", [png(1)])
            self.assertEqual(ctx.exception.status, 409)
        finally:
            gate.set()
            self.wait(out["run_id"])


class FauxDraftTest(unittest.TestCase):
    """假模型端到端：贴图 → 看到 IMG-1 → create_draft 建出待框选草稿，commit 数不变。"""

    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-img-")
        os.makedirs(os.path.join(self.vault, "错题"))
        cfg = load_config(self.vault)
        cfg.update({"agent_enabled": True, "agent_vision": True})
        save_config(self.vault, cfg)
        env = mock.patch.dict(os.environ, {"OMRS_AGENT_FAUX_SCRIPT": os.path.join(ROOT, "tests", "fixtures", "agent_faux.json")})
        env.start()
        self.addCleanup(env.stop)
        self.rt = AgentRuntime(self.vault)

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def test_image_to_draft(self):
        from omrs.ledger import read_commits
        conv = self.rt.create_conversation("")["id"]
        before = len(read_commits(self.vault))
        run_id = self.rt.post_message(conv, "录一下这张截图", [png(1)])["run_id"]
        import time
        deadline = time.monotonic() + 30
        while self.rt.store.run(run_id)["status"] != "done" and time.monotonic() < deadline:
            time.sleep(0.02)
        events = self.rt.store.event_page(run_id, limit=500)["events"]
        end = next(e for e in events if e["type"] == "tool.end")
        self.assertEqual(end["data"]["status"], "done", end)
        self.assertTrue(end["data"]["wrote"])
        draft = drafts.get_draft(self.vault, end["data"]["result"]["draft_id"])
        self.assertEqual(draft["status"], "cropping")
        self.assertEqual(draft["conversation_id"], conv)
        self.assertEqual(len(read_commits(self.vault)), before)
        self.assertEqual(events[-1]["data"]["stats"]["writes"], 1)


if __name__ == "__main__":
    unittest.main()
