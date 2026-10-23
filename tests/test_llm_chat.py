"""兼容模型流的终态校验与真实阻塞读取中止；不连接供应商。"""
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from omrs.llm.compat import resolve_compat
from omrs.llm.openai_compat import OpenAICompatClient
from omrs.llm.responses import ResponsesClient
from tests.test_agent_loop import Hooks, run


def frame(delta=None, finish=None):
    return {"choices": [{"delta": delta or {}, "finish_reason": finish}]}


def sse(*events, done=False):
    text = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
    return io.BytesIO((text + ("data: [DONE]\n\n" if done else "")).encode())


class ChatStreamTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenAICompatClient("http://example.invalid", "", "synthetic", resolve_compat("custom"))

    def test_eof_before_terminal_is_error_even_for_parseable_tool_arguments(self):
        calls = {"tool_calls": [{"index": 0, "id": "partial", "function": {"name": "write", "arguments": "{}"}}]}
        for delta in ({}, {"content": "未完成的答案"}, calls):
            with self.subTest(delta=delta), patch("urllib.request.urlopen", return_value=sse(frame(delta))):
                hooks = Hooks()
                outcome, _, _ = run(self.client, hooks=hooks)
                self.assertEqual(outcome["reason"], "error")
                self.assertIn("结束标识", outcome["error"])
                self.assertEqual(hooks.ran, [])

    def test_empty_stream_is_not_success(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO()):
            self.assertEqual(self.client.complete([])["finish_reason"], "error")

    def test_explicit_terminal_or_done_can_complete(self):
        for response in (sse(frame({"content": "完整回答"}, "stop")),
                         sse(frame({"content": "完整回答"}), done=True)):
            with self.subTest(response=response), patch("urllib.request.urlopen", return_value=response):
                result = self.client.complete([])
                self.assertEqual((result["finish_reason"], result["content"]), ("stop", "完整回答"))

    def test_malformed_frame_and_unknown_finish_never_become_success(self):
        for response in (io.BytesIO(b'data: {invalid}\n\ndata: [DONE]\n\n'),
                         sse(frame({"content": "文本"}, "unknown"), done=True)):
            with self.subTest(response=response), patch("urllib.request.urlopen", return_value=response):
                self.assertEqual(self.client.complete([])["finish_reason"], "error")

    def test_length_finish_keeps_existing_no_tool_execution_contract(self):
        calls = {"tool_calls": [{"index": 0, "id": "partial", "function": {"name": "write", "arguments": "{}"}}]}
        with patch("urllib.request.urlopen", side_effect=[sse(frame(calls, "length")), sse(frame({"content": "结束"}, "stop"))]):
            hooks = Hooks()
            outcome, _, _ = run(self.client, hooks=hooks)
        self.assertEqual(outcome["reason"], "completed")
        self.assertEqual(hooks.ran, [])


class StreamCancellationTests(unittest.TestCase):
    def test_cancel_wakes_both_protocols_without_waiting_for_more_server_data(self):
        for client_type in (OpenAICompatClient, ResponsesClient):
            with self.subTest(protocol=client_type.__name__):
                self.check_cancel(client_type)

    def check_cancel(self, client_type):
        release, received, cancelled, abort = (threading.Event() for _ in range(4))
        event = frame({"content": "合成首帧"}) if client_type is OpenAICompatClient else {
            "type": "response.output_text.delta", "output_index": 0, "delta": "合成首帧"}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
                release.wait(5)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        client = client_type(f"http://127.0.0.1:{server.server_port}", "", "synthetic", resolve_compat("custom"), timeout=4)
        result = []
        worker = threading.Thread(target=lambda: result.append(client.complete([], cancel=abort, on_delta=lambda *_: received.set())), daemon=True)
        worker.start()
        def cancel():
            abort.set()
            client.cancel()
            cancelled.set()
        stopper = threading.Thread(target=cancel, daemon=True)
        try:
            self.assertTrue(received.wait(2), "未收到本机合成首帧")
            stopper.start()
            self.assertTrue(cancelled.wait(1), "中止接口阻塞在响应关闭")
            worker.join(1)
            self.assertFalse(worker.is_alive(), "中止后仍在等服务端数据")
            self.assertFalse(release.is_set())
            self.assertEqual(result[0]["finish_reason"], "aborted")
        finally:
            abort.set()
            release.set()
            worker.join(5)
            if stopper.ident:
                stopper.join(5)
            server.shutdown()
            server.server_close()
            serving.join(2)
