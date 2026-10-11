"""Responses 协议适配：本地保存上下文，复用兼容客户端的 HTTP、超时与中止。

请求使用 input、平铺的 function 工具和 max_output_tokens；返回统一 ChatResult。
原生 output（含加密推理项）随助手消息持久化，下一轮原样回传，不依赖远端对话存储。
"""
import copy
import json

from .openai_compat import OpenAICompatClient
from .usage import normalize_usage


def _input_content(content):
    if not isinstance(content, list):
        return content or ""
    parts = []
    for part in content:
        if part.get("type") == "image_url":
            image = part["image_url"]
            item = {"type": "input_image", "image_url": image["url"]}
            if image.get("detail"):
                item["detail"] = image["detail"]
            parts.append(item)
        elif part.get("type") == "text":
            parts.append({"type": "input_text", "text": part.get("text") or ""})
    return parts


def _events(resp, cancel):
    """按 SSE 帧读取；不完整 JSON 必须报错，不能把残缺工具调用当作成功。"""
    lines = []
    for raw in resp:
        if cancel is not None and cancel.is_set():
            return
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
        elif not line and lines:
            data, lines = "\n".join(lines), []
            if data == "[DONE]":
                return
            yield json.loads(data)
    if lines:
        data = "\n".join(lines)
        if data != "[DONE]":
            yield json.loads(data)


def _call_fields(item):
    call = {"id": item.get("call_id") or "", "name": item.get("name") or "",
            "arguments": item.get("arguments", "")}
    if not all(isinstance(value, str) for value in call.values()):
        raise RuntimeError("Responses 工具调用的 call_id、名称和参数必须是文本")
    return call


def _reasoning_parts(item):
    """优先读取可展示摘要；兼容供应商的正文推理与 text 字段。"""
    summary = [(i, part.get("text") or "") for i, part in enumerate(item.get("summary") or [])]
    if any(text for _, text in summary):
        return "summary", summary
    content = [(i, part.get("text") or "") for i, part in enumerate(item.get("content") or [])]
    return "text", content or [(0, item.get("text") or "")]


def _reasoning_chars(items):
    try:
        return sum(len(text) for item in items if item.get("type") == "reasoning"
                   for _, text in _reasoning_parts(item)[1])
    except (AttributeError, TypeError):
        # 诊断不能遮盖随后解析阶段的协议错误。
        return None


def _completed_reasoning(output, done):
    """流式完成项保留摘要与加密上下文；终态瘦身不能抹掉它们。"""
    output = copy.deepcopy(output)
    for index, item in sorted(done.items()):
        if item.get("type") != "reasoning":
            continue
        target = next((i for i, entry in enumerate(output) if entry.get("type") == "reasoning"
                       and item.get("id") and entry.get("id") == item["id"]), None)
        if target is None and index < len(output) and output[index].get("type") == "reasoning":
            target = index
        if target is None:
            output.insert(min(index, len(output)), copy.deepcopy(item))
        else:
            merged = output[target]
            for key in ("id", "summary", "content", "text", "encrypted_content"):
                if item.get(key):
                    merged[key] = copy.deepcopy(item[key])
    return output


class ResponsesClient(OpenAICompatClient):
    def __init__(self, base_url, api_key, model, compat, timeout=120, debug_path=None, *, prompt_cache_key=None):
        super().__init__(base_url, api_key, model, compat, timeout, debug_path)
        self.prompt_cache_key = prompt_cache_key

    @property
    def endpoint(self):
        base = self.base_url
        if base.endswith("/responses"):
            return base
        # 已保存的完整 Chat Completions 地址切换协议时也能正常使用。
        if base.endswith("/chat/completions"):
            base = base[:-len("/chat/completions")]
        return base + "/responses"

    def build_payload(self, messages, tools, stream, max_tokens):
        items = []
        for msg in messages:
            role = msg.get("role")
            if role == "assistant":
                if msg.get("_response_items"):
                    items.extend(copy.deepcopy(msg["_response_items"]))
                    continue
                # 兼容先前以 Chat Completions 保存的会话；不伪造推理项。
                if msg.get("content"):
                    items.append({"role": "assistant", "content": msg["content"]})
                for call in msg.get("tool_calls") or []:
                    items.append({"type": "function_call", "call_id": call["id"], "name": call["name"],
                                  "arguments": call.get("arguments") or "{}"})
            elif role == "tool":
                items.append({"type": "function_call_output", "call_id": msg["tool_call_id"],
                              "output": msg.get("content") or ""})
            else:
                items.append({"role": self.compat["system_role"] if role == "system" else role or "user",
                              "content": _input_content(msg.get("content"))})
        payload = {"model": self.model, "input": items, "stream": bool(stream), "store": False,
                   "include": ["reasoning.encrypted_content"]}
        # 不改推理强度；旧非推理模型不接受 reasoning 参数，模型别名可用兼容开关关闭。
        non_reasoning = str(self.model).lower().startswith(("gpt-3.5", "gpt-4", "chatgpt-4o", "gpt-5-chat"))
        if self.compat.get("responses_reasoning_summary", True) and not non_reasoning:
            payload["reasoning"] = {"summary": "auto"}
        if self.prompt_cache_key:
            payload["prompt_cache_key"] = self.prompt_cache_key
        if max_tokens:
            payload["max_output_tokens"] = int(max_tokens)
        if tools:
            # 显式保留非 strict 的可选参数契约，避免 Responses 自动收紧 schema。
            payload["tools"] = [{**tool["function"], "type": "function", "strict": self.compat["strict_tools"]}
                                for tool in tools]
        return payload

    def _read_response(self, data, state, on_delta=None):
        self._mark(state)
        state["usage"] = data.get("usage")
        output = data.get("output")
        if output is None or output == []:
            # 部分网关终态只有状态/用量；只能恢复 output_item.done，不能执行 added 或参数拼片。
            done = state.get("done_items", {})
            pending = (set(state.get("items", {})) | set(state["calls"]) | state.get("delta_items", set())) - set(done)
            if data.get("status") == "completed" and (pending or (
                    (state["content"] or state["reasoning"]) and not done)):
                raise RuntimeError("Responses 终态缺少完整输出项，响应不完整")
            output = [item for _, item in sorted(done.items())]
        if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
            raise RuntimeError("Responses output 必须是输出项数组")
        output = _completed_reasoning(output, state.get("done_items", {}))
        state["response_items"] = copy.deepcopy(output)
        content, calls = [], {}
        for index, item in enumerate(output):
            kind = item.get("type")
            source_index = next((i for i, done in state.get("done_items", {}).items()
                                 if item.get("id") and done.get("id") == item["id"]), index)
            if kind == "message":
                for part_index, part in enumerate(item.get("content") or []):
                    if part.get("type") == "output_text":
                        text = part.get("text") or ""
                        if item.get("phase") in ("analysis", "commentary"):
                            self._read_reasoning_part(source_index, part_index, "message", text, state, on_delta)
                        else:
                            content.append(text)
                    elif part.get("type") == "refusal":
                        content.append(part.get("refusal") or "")
            elif kind == "reasoning":
                self._read_reasoning_item(item, source_index, state, on_delta)
            elif kind == "function_call":
                if data.get("status") == "completed" and item.get("status") not in (None, "completed"):
                    raise RuntimeError("Responses 工具调用未完整结束，响应不完整")
                call = _call_fields(item)
                if not call["id"] or not call["name"]:
                    raise RuntimeError("Responses 工具调用缺少 call_id 或名称")
                calls[index] = call
        # 正文仍以终态为准；推理摘要由逐项完成事件补齐，空终态不覆盖已有摘要。
        if content and not state["content"] and on_delta:
            on_delta("text", "".join(content), None)
        state["content"] = content
        if data.get("status") == "completed":
            seen = {call["id"] for call in state["calls"].values() if call["id"]}
            if seen - {call["id"] for call in calls.values()} or (state["calls"] and not calls):
                raise RuntimeError("Responses 终态遗漏工具调用，响应不完整")
        state["calls"] = calls
        status = data.get("status")
        if status == "completed":
            state["finish"] = "tool_calls" if calls else "stop"
        elif status == "incomplete" and (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
            state["finish"] = "length"
        else:
            error = data.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            reason = (data.get("incomplete_details") or {}).get("reason")
            raise RuntimeError(message or f"Responses 未正常完成：{reason or status or '缺少状态'}")

    def _read_whole(self, resp, state):
        self._read_response(json.loads(resp.read().decode("utf-8", "replace")), state)

    def _read_reasoning_part(self, index, part_index, channel, text, state, on_delta, *, delta=False):
        if not text:
            return
        if not isinstance(text, str):
            raise RuntimeError("Responses 推理摘要必须是文本")
        key = (index, channel, part_index)
        parts = state.setdefault("reasoning_parts", {})
        chunks = parts.setdefault(key, [])
        if not delta:
            prior = "".join(chunks)
            if not text.startswith(prior):
                # 展示过的文本不能靠追加改写；保留增量并在诊断中标记供应商差异。
                state["reasoning_mismatches"] = state.get("reasoning_mismatches", 0) + 1
                return
            text = text[len(prior):]
        if not text:
            return
        self._mark(state)
        separator = "\n\n" if not chunks and state["reasoning"] else ""
        chunks.append(text)
        state["reasoning"].append(separator + text)
        if on_delta:
            on_delta("think", separator + text, None)

    def _read_reasoning_item(self, item, index, state, on_delta):
        channel, parts = _reasoning_parts(item)
        for part_index, text in parts:
            self._read_reasoning_part(index, part_index, channel, text, state, on_delta)

    def _read_stream(self, resp, state, on_delta, cancel):
        state["items"] = {}
        state["done_items"] = {}
        state["delta_items"] = set()
        diagnostics = {"events": {}, "summary_delta_chars": 0, "terminal_received": False}
        state["stream_diagnostics"] = diagnostics
        try:
            self._consume_stream(resp, state, on_delta, cancel)
        finally:
            # 每个请求只追加一条计数日志，不记录摘要正文、工具参数或加密内容。
            self._debug("responses.stream", {**diagnostics,
                "done_reasoning_chars": _reasoning_chars(state["done_items"].values()),
                "retained_reasoning_chars": sum(map(len, state["reasoning"])),
                "reasoning_mismatches": state.get("reasoning_mismatches", 0),
                "cancelled": bool(cancel is not None and cancel.is_set())})

    def _consume_stream(self, resp, state, on_delta, cancel):
        diagnostics = state["stream_diagnostics"]
        for event in _events(resp, cancel):
            kind = event.get("type")
            # 类型白名单防止非标准帧把单条诊断扩成无界数据。
            label = kind if kind in _STREAM_TYPES else "other"
            diagnostics["events"][label] = diagnostics["events"].get(label, 0) + 1
            if kind == "error":
                error = event.get("error") or event
                raise RuntimeError(error.get("message") or "Responses 流式请求失败")
            if kind in ("response.completed", "response.incomplete", "response.failed"):
                data = event.get("response") or {}
                usage = normalize_usage(data.get("usage"))
                diagnostics.update({"terminal_received": True, "terminal_type": kind,
                    "response_id": str(data.get("id") or "")[:128],
                    "terminal_reasoning_chars": _reasoning_chars(data.get("output") or []),
                    "output_tokens": usage["output_total"], "reasoning_tokens": usage["reasoning_output"]})
                self._read_response(data, state, on_delta)
                return
            if kind in ("response.output_item.added", "response.output_item.done"):
                index, item = event["output_index"], event["item"]
                state["items"][index] = copy.deepcopy(item)
                if kind == "response.output_item.added":
                    state["active_output_index"] = index
                    state["active_message_phase"] = item.get("phase") if item.get("type") == "message" else None
                if kind == "response.output_item.done":
                    state["done_items"][index] = copy.deepcopy(item)
                    if item.get("type") == "reasoning":
                        self._read_reasoning_item(item, index, state, on_delta)
                    elif item.get("type") == "message" and item.get("phase") in ("analysis", "commentary"):
                        for part_index, part in enumerate(item.get("content") or []):
                            if part.get("type") == "output_text":
                                self._read_reasoning_part(index, part_index, "message", part.get("text"), state, on_delta)
                if item.get("type") == "function_call":
                    self._mark(state)
                    state["calls"][index] = call = _call_fields(item)
                    if kind == "response.output_item.added" and on_delta:
                        on_delta("args", call["arguments"], {"index": index, "name": call["name"]})
            elif kind in ("response.output_text.delta", "response.refusal.delta",
                          "response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
                text = event.get("delta") or ""
                if text:
                    if "output_index" in event:
                        state["delta_items"].add(event["output_index"])
                    self._mark(state)
                    index = event.get("output_index", state.get("active_output_index", 0))
                    phase = (state["items"].get(index) or {}).get("phase", state.get("active_message_phase"))
                    thinking = kind in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta") or (
                        kind == "response.output_text.delta" and phase in ("analysis", "commentary"))
                    if thinking:
                        channel = "summary" if "summary" in kind else "message" if "output_text" in kind else "text"
                        part_index = event.get("summary_index" if channel == "summary" else "content_index", 0)
                        self._read_reasoning_part(index, part_index, channel,
                                                  text, state, on_delta, delta=True)
                        if channel == "summary":
                            diagnostics["summary_delta_chars"] += len(text)
                    else:
                        state["content"].append(text)
                        if on_delta:
                            on_delta("text", text, None)
            elif kind in ("response.reasoning_summary_text.done", "response.reasoning_summary_part.done"):
                text = event.get("text") if kind.endswith("text.done") else (event.get("part") or {}).get("text")
                self._read_reasoning_part(event.get("output_index", state.get("active_output_index", 0)), event.get("summary_index", 0),
                                          "summary", text, state, on_delta)
            elif kind in ("response.function_call_arguments.delta", "response.function_call_arguments.done"):
                index = event["output_index"]
                call = state["calls"].setdefault(index, {"id": "", "name": "", "arguments": ""})
                text = event.get("delta" if kind.endswith(".delta") else "arguments", "")
                if not isinstance(text, str):
                    raise RuntimeError("Responses 工具参数必须是文本")
                if kind.endswith(".delta"):
                    self._mark(state)
                    call["arguments"] += text
                    if on_delta:
                        on_delta("args", text, {"index": index, "name": call["name"]})
                else:
                    call["arguments"] = text
                if index in state["items"]:
                    state["items"][index]["arguments"] = call["arguments"]
        if cancel is None or not cancel.is_set():
            raise RuntimeError("Responses 流在终态事件前结束，响应不完整")


_STREAM_TYPES = frozenset({"error", "response.created", "response.in_progress", "response.completed",
    "response.incomplete", "response.failed", "response.output_item.added", "response.output_item.done",
    "response.output_text.delta", "response.refusal.delta", "response.reasoning_text.delta",
    "response.reasoning_summary_text.delta", "response.reasoning_summary_text.done",
    "response.reasoning_summary_part.added", "response.reasoning_summary_part.done",
    "response.function_call_arguments.delta", "response.function_call_arguments.done"})
