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
from omrs.agent.runtime import model_messages
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

    def complete_stream(self, events):
        deltas = []
        with mock.patch("urllib.request.urlopen", return_value=sse(events)), mock.patch.object(self.client, "_debug") as debug:
            result = self.client.complete([], on_delta=lambda *args: deltas.append(args))
        diagnostic = [call.args[1] for call in debug.call_args_list if call.args[0] == "responses.stream"]
        self.assertEqual(len(diagnostic), 1)
        return result, deltas, diagnostic[0]

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

    def test_summary_opt_in_keeps_non_reasoning_models_compatible(self):
        for model in ("gpt-6.1-sol", "gpt-5", "o3", "provider-reasoning-alias"):
            with self.subTest(model=model):
                client = ResponsesClient("http://example.invalid", "", model, resolve_compat("openai"))
                self.assertEqual(client.build_payload([], None, True, 100)["reasoning"], {"summary": "auto"})
        for model in ("gpt-4.1", "gpt-4o-mini", "chatgpt-4o-latest", "gpt-5-chat-latest"):
            with self.subTest(model=model):
                client = ResponsesClient("http://example.invalid", "", model, resolve_compat("openai"))
                self.assertNotIn("reasoning", client.build_payload([], None, True, 100))
        client = ResponsesClient("http://example.invalid", "", "alias", resolve_compat(
            "openai", {"responses_reasoning_summary": False}))
        self.assertNotIn("reasoning", client.build_payload([], None, True, 100))

    def test_cache_key_is_stable_per_vault_conversation_and_model(self):
        settings = {"faux": False, "debug_log": False, "_base": "http://example.invalid/v1", "_key": "secret",
                    "model": "gpt-6.1-sol", "compat": resolve_compat("openai")}
        with tempfile.TemporaryDirectory() as vault:
            def payload(conv="conv", root=vault, model="gpt-6.1-sol"):
                return make_client(root, {**settings, "model": model}, conversation_id=conv).build_payload([], None, True, 100)
            key = payload()["prompt_cache_key"]
            self.assertEqual(key, payload(root=vault + "/.")["prompt_cache_key"])
            self.assertEqual(key, payload()["prompt_cache_key"])
            self.assertNotIn(key, [payload(conv="other")["prompt_cache_key"], payload(root=vault + "/other")["prompt_cache_key"],
                                   payload(model="gpt-5")["prompt_cache_key"]])
            self.assertLessEqual(len(key), 64)
            self.assertNotIn("secret", key)
            self.assertNotIn(vault, key)
            self.assertNotIn("prompt_cache_key", payload(conv=None))

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

    def test_summary_parts_done_and_empty_final_summary_keep_complete_items_once(self):
        thought = reasoning()
        thought["summary"].append({"type": "summary_text", "text": "核对结果"})
        events = [{"type": "response.reasoning_summary_text.delta", "output_index": 0, "summary_index": 0, "delta": "先查"},
                  {"type": "response.reasoning_summary_text.done", "output_index": 0, "summary_index": 0, "text": "先查询"},
                  {"type": "response.reasoning_summary_part.done", "output_index": 0, "summary_index": 0, "part": thought["summary"][0]},
                  {"type": "response.reasoning_summary_text.delta", "output_index": 0, "summary_index": 1, "delta": "核对"},
                  {"type": "response.output_item.done", "output_index": 0, "item": thought},
                  terminal(response([{**thought, "summary": [], "encrypted_content": None}, message()]))]
        result, deltas, diagnostic = self.complete_stream(events)
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["reasoning"], "先查询\n\n核对结果")
        self.assertEqual("".join(text for kind, text, _ in deltas if kind == "think"), result["reasoning"])
        self.assertEqual(result["response_items"][0], thought)
        self.assertEqual(diagnostic["terminal_reasoning_chars"], 0)
        self.assertEqual(diagnostic["done_reasoning_chars"], 7)
        self.assertEqual(diagnostic["retained_reasoning_chars"], 9)
        self.assertEqual(diagnostic["reasoning_mismatches"], 0)
        self.assertNotIn("先查询", json.dumps(diagnostic, ensure_ascii=False))
        self.assertNotIn("完整的加密推理", json.dumps(diagnostic, ensure_ascii=False))

    def test_done_only_summary_is_visible_without_a_delta_or_item_done(self):
        thought = {**reasoning(), "summary": []}
        for kind in ("response.reasoning_summary_text.done", "response.reasoning_summary_part.done"):
            with self.subTest(kind=kind):
                event = {"type": kind, "output_index": 0, "summary_index": 0, "text": "先查询",
                         "part": {"type": "summary_text", "text": "先查询"}}
                result, deltas, diagnostic = self.complete_stream([event, event, terminal(response([thought, message()]))])
                self.assertEqual(result["reasoning"], "先查询")
                self.assertEqual([text for typ, text, _ in deltas if typ == "think"], ["先查询"])
                self.assertEqual(diagnostic["summary_delta_chars"], 0)
                self.assertEqual(diagnostic["events"][kind], 2)

    def test_completed_reasoning_missing_from_terminal_is_replayed_before_answer(self):
        thought = reasoning()
        result, deltas, _ = self.complete_stream([
            {"type": "response.output_item.done", "output_index": 0, "item": thought},
            terminal(response([message()]))])
        self.assertEqual(result["response_items"], [thought, message()])
        self.assertEqual([text for typ, text, _ in deltas if typ == "think"], ["先查询"])

    def test_summary_index_is_preserved_when_terminal_output_positions_change(self):
        thought = reasoning()
        result, deltas, _ = self.complete_stream([
            {"type": "response.reasoning_summary_text.delta", "output_index": 1, "summary_index": 0, "delta": "先查询"},
            {"type": "response.output_item.done", "output_index": 1, "item": thought},
            terminal(response([{**thought, "summary": []}, message()]))])
        self.assertEqual(result["reasoning"], "先查询")
        self.assertEqual([text for typ, text, _ in deltas if typ == "think"], ["先查询"])

    def test_encrypted_reasoning_without_summary_is_not_fabricated(self):
        result, deltas, diagnostic = self.complete_stream([terminal(response([{**reasoning(), "summary": []}, message()]))])
        self.assertEqual(result["reasoning"], "")
        self.assertFalse(any(kind == "think" for kind, *_ in deltas))
        self.assertEqual(diagnostic["reasoning_tokens"], 10)
        self.assertEqual(diagnostic["retained_reasoning_chars"], 0)

    def test_stream_diagnostic_survives_truncation_and_marks_summary_conflicts(self):
        result, _, diagnostic = self.complete_stream([
            {"type": "response.reasoning_summary_text.delta", "output_index": 0, "delta": "先查询"},
            {"type": "response.reasoning_summary_text.done", "output_index": 0, "text": "不同摘要"}])
        self.assertEqual(result["finish_reason"], "error")
        self.assertFalse(diagnostic["terminal_received"])
        self.assertEqual(diagnostic["reasoning_mismatches"], 1)
        self.assertEqual(diagnostic["retained_reasoning_chars"], 3)

    def test_nonstandard_reasoning_text_field_falls_back_without_duplicate_content(self):
        data = response([{**reasoning(), "summary": [], "text": "先查询"}, message()])
        self.assertEqual(self.complete_json(data)["reasoning"], "先查询")
        data["output"][0]["summary"] = [{"type": "summary_text", "text": "摘要优先"}]
        data["output"][0]["content"] = [{"type": "reasoning_text", "text": "重复推理"}]
        self.assertEqual(self.complete_json(data)["reasoning"], "摘要优先")

    def test_analysis_and_commentary_messages_use_reasoning_channel_like_hermes(self):
        for phase in ("analysis", "commentary"):
            with self.subTest(phase=phase):
                interim = {**message("先查询"), "phase": phase}
                result, deltas, _ = self.complete_stream([
                    {"type": "response.output_item.added", "output_index": 0, "item": interim},
                    {"type": "response.output_text.delta", "output_index": 0, "delta": "先查询"},
                    {"type": "response.output_item.done", "output_index": 0, "item": interim},
                    terminal(response([interim, message("正式回答")]))])
                self.assertEqual((result["reasoning"], result["content"]), ("先查询", "正式回答"))
                self.assertEqual(deltas, [("think", "先查询", None), ("text", "正式回答", None)])

    def test_empty_or_missing_terminal_output_restores_done_tools(self):
        for output in ([], None):
            with self.subTest(output=output):
                calls = [tool_call(call_id="call_a"), tool_call(arguments='{"x":2}', call_id="call_b")]
                data = response()
                if output is None:
                    data.pop("output")
                events = []
                for index, call in enumerate(calls):
                    events.extend([{"type": "response.output_item.added", "output_index": index, "item": {**call, "arguments": ""}},
                                   {"type": "response.function_call_arguments.delta", "output_index": index, "delta": call["arguments"]},
                                   {"type": "response.output_item.done", "output_index": index, "item": call}])
                events.append(terminal(data))
                hooks = Hooks()
                with mock.patch("urllib.request.urlopen", side_effect=[sse(events), sse([terminal(response([message()]))])]):
                    outcome, messages, _ = run(self.client, hooks)
                self.assertEqual(outcome["reason"], "completed")
                self.assertEqual(hooks.ran, ["echo", "echo"])
                self.assertEqual(messages[1]["_response_items"], calls)

    def test_empty_terminal_preserves_done_answer_and_reasoning_without_duplicate_deltas(self):
        items = [reasoning(), message()]
        events = [{"type": "response.reasoning_summary_text.delta", "output_index": 0, "delta": "先查询"},
                  {"type": "response.output_text.delta", "output_index": 1, "delta": "回答"}]
        events += [{"type": "response.output_item.done", "output_index": index, "item": item} for index, item in enumerate(items)]
        events.append(terminal(response()))
        deltas = []
        with mock.patch("urllib.request.urlopen", return_value=sse(events)):
            result = self.client.complete([], on_delta=lambda *args: deltas.append(args))
        self.assertEqual((result["content"], result["reasoning"], result["response_items"]), ("回答", "先查询", items))
        self.assertEqual(deltas, [("think", "先查询", None), ("text", "回答", None)])

    def test_empty_terminal_never_executes_unfinished_or_mixed_tools(self):
        unfinished = tool_call(call_id="partial")
        cases = [[{"type": "response.output_item.added", "output_index": 0, "item": unfinished}],
                 [{"type": "response.output_item.done", "output_index": 0, "item": {**unfinished, "status": "in_progress"}}],
                 [{"type": "response.function_call_arguments.done", "output_index": 0, "arguments": '{"x":1}'}],
                 [{"type": "response.output_item.done", "output_index": 0, "item": tool_call()},
                  {"type": "response.output_item.added", "output_index": 1, "item": unfinished}],
                 [{"type": "response.output_text.delta", "output_index": 0, "delta": "未结束正文"}]]
        for events in cases:
            with self.subTest(events=events), mock.patch("urllib.request.urlopen", return_value=sse(events + [terminal(response())])):
                hooks = Hooks()
                outcome, _, _ = run(self.client, hooks)
            self.assertEqual(outcome["reason"], "error")
            self.assertIn("响应不完整", outcome["error"])
            self.assertEqual(hooks.ran, [])

    def test_terminal_cannot_silently_drop_a_streamed_tool(self):
        events = [{"type": "response.output_item.added", "output_index": 0, "item": tool_call()},
                  terminal(response([message()]))]
        with mock.patch("urllib.request.urlopen", return_value=sse(events)):
            hooks = Hooks()
            outcome, _, _ = run(self.client, hooks)
        self.assertEqual(outcome["reason"], "error")
        self.assertEqual(hooks.ran, [])

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
            loaded = model_messages(AgentStore(vault).messages("conv"))
            rebuilt = self.client.build_payload(loaded, None, True, 100)["input"]
            self.assertEqual(rebuilt[1:3], first)
            self.assertFalse(any("_run" in item or "_response_items" in item for item in rebuilt))
            chat = OpenAICompatClient("http://example.invalid/v1", "", "test", resolve_compat("custom"))
            self.assertNotIn("_response_items", json.dumps(chat.build_payload(loaded, None, False, 100)))

    def test_reloaded_runtime_context_keeps_the_exact_input_prefix(self):
        original = [{"role": "system", "content": "固定规则"}, {"role": "user", "content": "问题"},
                    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_test", "name": "echo", "arguments": '{"x":1}'}],
                     "_response_items": [reasoning(), tool_call()], "_run": "old"},
                    {"role": "tool", "tool_call_id": "call_test", "content": '{"x":1}'}]
        previous = self.client.build_payload(original, None, True, 100)["input"]
        loaded = model_messages(copy.deepcopy(original) + [{"role": "user", "content": "继续"}])
        following = self.client.build_payload(loaded, None, True, 100)["input"]
        self.assertEqual(following[:-1], previous)
        self.assertNotIn("_run", loaded[2])
        self.assertEqual(following[2]["encrypted_content"], "完整的加密推理")

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
