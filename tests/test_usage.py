"""助手主请求与图片辅助请求的 token 口径。"""
import unittest
import io
import json
from unittest import mock

from omrs import ai_assist
from omrs.agent.runtime import run_stats
from omrs.agent.tools.drafts import describe_image_tool
from omrs.llm.usage import normalize_usage


class UsageTests(unittest.TestCase):
    def test_describe_tool_attributes_aux_usage_to_call(self):
        captured = []
        def fake_ask(_vault, _url, _question, usage_callback=None):
            usage_callback({"input_total": 7, "output_total": 3, "scope": "aux"})
            return "答案"
        context = {"vault": "vault", "conversation_id": "conv", "run_id": "run_1", "tool_call_id": "call_2",
                   "emit_usage": captured.append}
        with mock.patch("omrs.agent.tools.drafts.drafts.resolve_image", return_value={"ref": "IMG-1", "sha256": "abc"}), \
             mock.patch("omrs.agent.tools.drafts.drafts.image_data_url", return_value="data:image/png;base64,AA=="), \
             mock.patch("omrs.agent.tools.drafts.ask_image", side_effect=fake_ask):
            result = describe_image_tool(context, {"image": "IMG-1", "question": "是什么"})
        self.assertEqual(result["result"]["answer"], "答案")
        self.assertEqual(captured[0]["request_id"], "run_1:describe:call_2")

    def test_aux_callback_is_optional_and_keeps_text_return(self):
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": "看到了"}}],
                                          "usage": {"prompt_tokens": 8, "completion_tokens": 2,
                                                    "prompt_tokens_details": {"cached_tokens": 0}}}).encode())
        captured = []
        with mock.patch.object(ai_assist, "_ai_config", return_value=("http://example.invalid/v1", "key", "model")), \
             mock.patch.object(ai_assist.urllib.request, "urlopen", return_value=response):
            text = ai_assist._call_model("vault", "看图", "data:image/png;base64,AA==", 100, 5,
                                         usage_callback=captured.append)
        self.assertEqual(text, "看到了")
        self.assertEqual((captured[0]["scope"], captured[0]["input_total"], captured[0]["cache_read"]),
                         ("aux", 8, 0))

    def test_cache_is_input_subset_and_zero_is_known(self):
        first = normalize_usage({"prompt_tokens": 1000, "completion_tokens": 200,
                                 "prompt_tokens_details": {"cached_tokens": 0}, "prompt_cache_hit_tokens": 800})
        second = normalize_usage({"prompt_tokens": 9000, "completion_tokens": 300,
                                  "prompt_cache_hit_tokens": 9000, "completion_tokens_details": {"reasoning_tokens": 100}})
        self.assertEqual((first["cache_read"], second["cache_read"]), (0, 9000))
        self.assertEqual((sum(row["input_total"] + row["output_total"] for row in (first, second)),
                          sum(row["cache_read"] for row in (first, second))), (10500, 9000))
        self.assertIsNone(normalize_usage({"prompt_tokens": 5, "completion_tokens": 0})["cache_read"])
        self.assertEqual(normalize_usage({"prompt_cache_hit_tokens": 3, "prompt_cache_miss_tokens": 7})["input_total"], 10)

    def test_bad_counts_do_not_become_valid_percentages(self):
        for raw in ({"prompt_tokens": -1}, {"prompt_tokens": "10"},
                    {"prompt_tokens": 2, "prompt_cache_hit_tokens": 3},
                    {"completion_tokens": 1, "completion_tokens_details": {"reasoning_tokens": 2}}):
            self.assertTrue(normalize_usage(raw)["invalid"])
        partial = normalize_usage(None, estimated_output=4)
        self.assertIsNone(partial["input_total"])
        self.assertIsNone(partial["cache_read"])
        self.assertEqual(partial["output_total"], 4)
        self.assertFalse(partial["known"])
        self.assertEqual(partial["source"], "estimated")
        self.assertEqual(normalize_usage(None)["source"], "missing")

    def test_run_stats_deduplicates_request_and_counts_aux_once(self):
        row = {"prompt": 1000, "completion": 500, "cached": 0, "reasoning": 50}
        events = [{"i": 1, "type": "round.end", "data": {"n": 1, "request_id": "round:1", "usage": row}},
                  {"i": 2, "type": "round.end", "data": {"n": 1, "request_id": "round:1", "usage": row}},
                  {"i": 3, "type": "usage.aux", "data": {"request_id": "image:1", "usage": {"prompt": 10, "completion": 20}}},
                  {"i": 4, "type": "usage.aux", "data": {"request_id": "image:1", "usage": {"prompt": 10, "completion": 20}}}]
        stats = run_stats(events)
        self.assertEqual(stats["usage"], {"prompt": 1010, "completion": 520, "cached": 0, "reasoning": 50})
        self.assertEqual(stats["rounds"], 1)


if __name__ == "__main__":
    unittest.main()
