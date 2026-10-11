"""Responses 的请求、流式终态、多轮工具与持久上下文；只用合成响应和临时库。"""
import copy
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

from omrs.agent.config import make_client
from omrs.agent.store import AgentStore
from omrs.llm.compat import resolve_compat
from omrs.llm.openai_compat import OpenAICompatClient
from omrs.llm.responses import ResponsesClient
from tests.test_agent_loop import Hooks, run


def message(text="回答", refusal=False):
    part = {"type": "refusal", "refusal": text} if refusal else {"type": "output_text", "text": text, "annotations": []}
    return {"type": "message", "id": "msg_test", "role": "assistant", "status": "completed", "content": [part]}


def tool_call(name="echo", arguments='{"x":1}', call_id="call_test"):
    return {"type": "function_call", "id": "fc_test", "call_id": call_id, "name": name,
            "arguments": arguments, "status": "completed"}


def reasoning(encrypted="完整的加密推理"):
    return {"type": "reasoning", "id": "rs_test", "summary": [{"type": "summary_text", "text": "先查询"}],
            "encrypted_content": encrypted}


def response(output=None, status="completed", **extra):
    return {"id": "resp_test", "object": "response", "status": status, "output": output or [],
            "usage": {"input_tokens": 120, "output_tokens": 30, "input_tokens_details": {"cached_tokens": 80},
                      "output_tokens_details": {"reasoning_tokens": 10}}, **extra}


def sse(events):
    return io.BytesIO("".join("event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                              for event in events).encode())


def terminal(data):
    return {"type": "response." + data["status"], "response": data}


class ResponsesTests(unittest.TestCase):
    def setUp(self):
        self.client = ResponsesClient("http://example.invalid/v1", "合成密钥", "test-model", resolve_compat("openai"))

    def complete_json(self, data):
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
            return self.client.complete([{"role": "user", "content": "问"}], stream=False)

    def test_profile_selects_protocol_and_keeps_other_vendors_on_chat(self):
        for name in ("openai", "custom", "deepseek", "dashscope"):
            with self.subTest(name=name):
                client = make_client("unused", {"faux": False, "debug_log": False, "_base": "http://example.invalid/v1",
                                                "_key": "key", "model": "test", "compat": resolve_compat(name)})
                self.assertEqual(type(client), ResponsesClient if name == "openai" else OpenAICompatClient)
                self.assertTrue(client.endpoint.endswith("/responses" if name == "openai" else "/chat/completions"))

    def test_base_and_complete_urls_resolve_without_duplicate_suffix(self):
        for suffix in ("", "/responses", "/responses/", "/chat/completions", "/chat/completions/"):
            with self.subTest(suffix=suffix):
                client = ResponsesClient("http://example.invalid/v1" + suffix, "", "", resolve_compat("openai"))
                self.assertEqual(client.endpoint, "http://example.invalid/v1/responses")

    def test_request_translates_images_tools_and_legacy_history(self):
        messages = [{"role": "system", "content": "规则"}, {"role": "user", "content": [
            {"type": "text", "text": "看图"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA==", "detail": "high"}}]},
            {"role": "assistant", "content": "查一下", "reasoning": "旧思考", "tool_calls": [
                {"id": "old_call", "name": "echo", "arguments": '{"x":1}'}]},
            {"role": "tool", "tool_call_id": "old_call", "name": "echo", "content": '{"x":1}'}]
        tools = [{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}]
        original = copy.deepcopy(messages)
        payload = self.client.build_payload(messages, tools, True, 1234)
        self.assertEqual(messages, original)
        self.assertEqual(payload["max_output_tokens"], 1234)
        self.assertEqual(payload["input"][1]["content"][1], {"type": "input_image", "image_url": "data:image/png;base64,AA==", "detail": "high"})
        self.assertEqual(payload["input"][1]["content"][0], {"type": "input_text", "text": "看图"})
        self.assertEqual(payload["input"][-2]["call_id"], "old_call")
        self.assertEqual(payload["input"][-1], {"type": "function_call_output", "call_id": "old_call", "output": '{"x":1}'})
        self.assertEqual(payload["tools"][0]["strict"], False)
        self.assertEqual(payload["tools"][0]["name"], "echo")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["include"], ["reasoning.encrypted_content"])
        self.assertTrue(all(key not in payload for key in ("messages", "max_tokens", "max_completion_tokens", "stream_options", "previous_response_id")))
        self.assertFalse(any(item.get("type") == "reasoning" for item in payload["input"]))

    def test_nonstream_result_uses_call_id_and_responses_usage(self):
        result = self.complete_json(response([reasoning(), tool_call(), message("已查")]))
        self.assertEqual((result["content"], result["reasoning"], result["finish_reason"]), ("已查", "先查询", "tool_calls"))
        self.assertEqual((result["tool_calls"][0]["id"], result["tool_calls"][0]["args"]), ("call_test", {"x": 1}))
        self.assertEqual((result["usage"]["input_total"], result["usage"]["cache_read"], result["usage"]["reasoning_output"]), (120, 80, 10))

    def test_stream_assembles_arguments_and_preserves_done_reasoning(self):
        call, thought = tool_call(), reasoning()
        events = [{"type": "response.output_item.added", "output_index": 0, "item": reasoning("未完成")},
                  {"type": "response.reasoning_summary_text.delta", "delta": "先查询"},
                  {"type": "response.output_item.done", "output_index": 0, "item": thought},
                  {"type": "response.output_item.added", "output_index": 1, "item": {**call, "arguments": ""}},
                  {"type": "response.function_call_arguments.delta", "output_index": 1, "delta": '{"x":'},
                  {"type": "response.function_call_arguments.delta", "output_index": 1, "delta": '1}'},
                  {"type": "response.function_call_arguments.done", "output_index": 1, "arguments": '{"x":1}'},
                  {"type": "response.output_item.done", "output_index": 1, "item": call},
                  terminal(response([thought, call]))]
        deltas = []
        with mock.patch("urllib.request.urlopen", return_value=sse(events)):
            result = self.client.complete([], on_delta=lambda *args: deltas.append(args))
        self.assertEqual(result["tool_calls"][0]["arguments"], '{"x":1}')
        self.assertEqual(result["response_items"], [thought, call])
        self.assertEqual("".join(text for kind, text, _ in deltas if kind == "args"), '{"x":1}')
        self.assertEqual("".join(text for kind, text, _ in deltas if kind == "think"), "先查询")

    def test_final_text_is_not_duplicated_and_refusals_are_visible(self):
        for refusal in (False, True):
            with self.subTest(refusal=refusal):
                deltas = []
                events = [{"type": "response.refusal.delta" if refusal else "response.output_text.delta", "delta": "回答"},
                          terminal(response([message("回答", refusal)]))]
                with mock.patch("urllib.request.urlopen", return_value=sse(events)):
                    result = self.client.complete([], on_delta=lambda *args: deltas.append(args))
                self.assertEqual(result["content"], "回答")
                self.assertEqual([text for kind, text, _ in deltas if kind == "text"], ["回答"])

    def test_terminal_only_stream_emits_answer(self):
        deltas = []
        with mock.patch("urllib.request.urlopen", return_value=sse([terminal(response([message()]))])):
            result = self.client.complete([], on_delta=lambda *args: deltas.append(args))
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(deltas, [("text", "回答", None)])

    def test_sse_supports_multiline_data(self):
        raw = 'event: response.completed\r\ndata: {"type":"response.completed",\r\ndata: "response":' + json.dumps(response([message()])) + '}\r\n\r\n'
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(raw.encode())):
            result = self.client.complete([])
        self.assertEqual(result["content"], "回答")

    def test_tool_roundtrip_preserves_native_output_across_database_reload(self):
        first = [reasoning(), tool_call()]
        with mock.patch("urllib.request.urlopen", side_effect=[sse([terminal(response(first))]), sse([terminal(response([message()]))])]) as request:
            outcome, messages, _ = run(self.client)
        self.assertEqual(outcome["reason"], "completed")
        followup = json.loads(request.call_args_list[1].args[0].data)
        self.assertEqual(followup["input"][2:4], first)
        self.assertEqual(followup["input"][4]["call_id"], "call_test")
        self.assertEqual(followup["input"][4]["type"], "function_call_output")
        with tempfile.TemporaryDirectory() as vault:
            store = AgentStore(vault)
            store.create_conversation("conv", "合成对话")
            for msg in messages:
                store.add_message("conv", "run", msg)
            loaded = AgentStore(vault).messages("conv")
            rebuilt = self.client.build_payload(loaded, None, True, 100)["input"]
            self.assertEqual(rebuilt[1:3], first)
            self.assertFalse(any("_run" in item or "_response_items" in item for item in rebuilt))
            chat = OpenAICompatClient("http://example.invalid/v1", "", "test", resolve_compat("custom"))
            self.assertNotIn("_response_items", json.dumps(chat.build_payload(loaded, None, False, 100)))

    def test_incomplete_output_never_executes_tools(self):
        hooks = Hooks()
        short = response([tool_call()], "incomplete", incomplete_details={"reason": "max_output_tokens"})
        with mock.patch("urllib.request.urlopen", side_effect=[sse([terminal(short)]), sse([terminal(response([message()]))])]):
            outcome, messages, _ = run(self.client, hooks)
        self.assertEqual(outcome["reason"], "completed")
        self.assertEqual(hooks.ran, [])
        self.assertIn("截断", next(msg["content"] for msg in messages if msg["role"] == "tool"))

    def test_missing_terminal_never_executes_partial_tool(self):
        hooks = Hooks()
        events = [{"type": "response.output_item.added", "output_index": 0, "item": tool_call()}]
        with mock.patch("urllib.request.urlopen", return_value=sse(events)):
            outcome, _, _ = run(self.client, hooks)
        self.assertEqual(outcome["reason"], "error")
        self.assertIn("响应不完整", outcome["error"])
        self.assertEqual(hooks.ran, [])

    def test_failed_filtered_and_malformed_streams_report_errors(self):
        cases = [sse([terminal(response(status="failed", error={"message": "供应商失败"}))]),
                 sse([terminal(response(status="incomplete", incomplete_details={"reason": "content_filter"}))]),
                 sse([{"type": "error", "message": "上游错误"}]), io.BytesIO(b'data: {bad}\n\n'),
                 sse([terminal(response([{"type": "function_call", "name": "echo"}]))])]
        for stream in cases:
            with self.subTest(stream=stream), mock.patch("urllib.request.urlopen", return_value=stream):
                result = self.client.complete([])
            self.assertEqual(result["finish_reason"], "error")
            self.assertTrue(result["error"])

    def test_abort_retains_existing_cancel_contract(self):
        abort = threading.Event()
        events = [{"type": "response.output_text.delta", "delta": "部分"}, terminal(response([message()]))]
        with mock.patch("urllib.request.urlopen", return_value=sse(events)):
            result = self.client.complete([], cancel=abort, on_delta=lambda *_: abort.set())
        self.assertEqual(result["finish_reason"], "aborted")
        self.assertEqual(result["content"], "部分")

    def test_invalid_argument_types_return_error_without_raising(self):
        for bad in ({"x": 1}, {}, [1], 3, None):
            with self.subTest(bad=bad):
                result = self.complete_json(response([tool_call(arguments=bad)]))
                self.assertEqual(result["finish_reason"], "error")
                for event in ({"type": "response.output_item.added", "output_index": 0, "item": tool_call(arguments=bad)},
                              {"type": "response.function_call_arguments.done", "output_index": 0, "arguments": bad}):
                    with mock.patch("urllib.request.urlopen", return_value=sse([event])):
                        result = self.client.complete([])
                    self.assertEqual(result["finish_reason"], "error")
                    self.assertIn("文本", result["error"])

    def test_network_errors_keep_readable_result(self):
        for error in (urllib.error.URLError("测试断连"), TimeoutError("测试超时")):
            with self.subTest(error=error), mock.patch("urllib.request.urlopen", side_effect=error):
                result = self.client.complete([])
            self.assertEqual(result["finish_reason"], "error")
            self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
