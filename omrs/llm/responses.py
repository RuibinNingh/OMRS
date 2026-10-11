"""Responses 协议适配：本地保存上下文，复用兼容客户端的 HTTP、超时与中止。

请求使用 input、平铺的 function 工具和 max_output_tokens；返回统一 ChatResult。
原生 output（含加密推理项）随助手消息持久化，下一轮原样回传，不依赖远端对话存储。
"""
import copy
import json

from .openai_compat import OpenAICompatClient


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


class ResponsesClient(OpenAICompatClient):
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
        if output is None:
            output = [item for _, item in sorted(state.get("items", {}).items())]
        state["response_items"] = copy.deepcopy(output)
        content, reasoning, calls = [], [], {}
        for index, item in enumerate(output):
            kind = item.get("type")
            if kind == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        content.append(part.get("text") or "")
                    elif part.get("type") == "refusal":
                        content.append(part.get("refusal") or "")
            elif kind == "reasoning":
                reasoning.extend(part.get("text") or "" for part in item.get("summary") or [])
                reasoning.extend(part.get("text") or "" for part in item.get("content") or [])
            elif kind == "function_call":
                call = _call_fields(item)
                if not call["id"] or not call["name"]:
                    raise RuntimeError("Responses 工具调用缺少 call_id 或名称")
                calls[index] = call
        # 终态是权威内容；供应商只发终态时仍补发文本，已收到增量的不重复显示。
        for key, parts, kind in (("content", content, "text"), ("reasoning", reasoning, "think")):
            if parts and not state[key] and on_delta:
                on_delta(kind, "".join(parts), None)
            state[key] = parts
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

    def _read_stream(self, resp, state, on_delta, cancel):
        state["items"] = {}
        for event in _events(resp, cancel):
            kind = event.get("type")
            if kind == "error":
                error = event.get("error") or event
                raise RuntimeError(error.get("message") or "Responses 流式请求失败")
            if kind in ("response.completed", "response.incomplete", "response.failed"):
                self._read_response(event.get("response") or {}, state, on_delta)
                return
            if kind in ("response.output_item.added", "response.output_item.done"):
                index, item = event["output_index"], event["item"]
                state["items"][index] = copy.deepcopy(item)
                if item.get("type") == "function_call":
                    self._mark(state)
                    state["calls"][index] = call = _call_fields(item)
                    if kind == "response.output_item.added" and on_delta:
                        on_delta("args", call["arguments"], {"index": index, "name": call["name"]})
            elif kind in ("response.output_text.delta", "response.refusal.delta",
                          "response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
                text = event.get("delta") or ""
                if text:
                    self._mark(state)
                    thinking = kind in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta")
                    state["reasoning" if thinking else "content"].append(text)
                    if on_delta:
                        on_delta("think" if thinking else "text", text, None)
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
