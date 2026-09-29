"""OpenAI 兼容客户端：POST {base}/chat/completions，流式（SSE）与非流式、工具调用、结束原因映射、超时、可中止。

流式时按 index 累积工具调用参数片段，结束后一次性 json.loads（不做残缺 JSON 解析）。
complete() 永不抛出网络/协议错误：finish_reason 为 'error' 时 error 字段是可读原因。
"""
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from .usage import normalize_usage

FINISH_MAP = {"stop": "stop", "tool_calls": "tool_calls", "function_call": "tool_calls", "length": "length",
              "content_filter": "error", "end_turn": "stop"}


IMAGE_TOKEN_ESTIMATE = 1000


def estimate_tokens(text) -> float:
    """粗估 token 数，只用于界面用量计。内容块数组（附图的用户消息）按文字块计，每张图固定 IMAGE_TOKEN_ESTIMATE。"""
    if isinstance(text, list):
        return sum(IMAGE_TOKEN_ESTIMATE if p.get("type") == "image_url" else estimate_tokens(p.get("text"))
                   for p in text if isinstance(p, dict))
    text = text or ""
    cjk = sum(1 for ch in text if "\u3000" <= ch <= "\u9fff" or "\uf900" <= ch <= "\uffef")
    return cjk / 1.35 + (len(text) - cjk) / 3.6


class ChatResult(dict):
    """{content, reasoning, tool_calls:[{id,name,arguments,args,parse_error}], finish_reason,
        error, usage:{prompt,completion,cached,reasoning}, ttft_ms, duration_ms, gen_ms}"""


def parse_tool_calls(calls):
    out = []
    for i, call in enumerate(calls):
        raw = call.get("arguments") or ""
        args, error = None, ""
        try:
            args = json.loads(raw) if raw.strip() else {}
            if not isinstance(args, dict):
                args, error = None, "参数必须是 JSON 对象"
        except json.JSONDecodeError as exc:
            error = f"参数不是合法 JSON：{exc.msg}"
        out.append({"id": call.get("id") or f"call_{i}", "name": call.get("name") or "", "arguments": raw,
                    "args": args, "parse_error": error})
    return out


def _usage(raw):
    return normalize_usage(raw)


class OpenAICompatClient:
    def __init__(self, base_url, api_key, model, compat, timeout=120, debug_path=None):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = model
        self.compat = compat
        self.timeout = timeout
        self.debug_path = debug_path
        self._resp = None
        self._lock = threading.Lock()

    @property
    def endpoint(self):
        return self.base_url if self.base_url.endswith("/chat/completions") else self.base_url + "/chat/completions"

    def cancel(self):
        """从别的线程中止正在进行的请求：关闭响应，阻塞中的读取随即返回。"""
        with self._lock:
            resp = self._resp
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def build_payload(self, messages, tools, stream, max_tokens):
        c = self.compat
        out = []
        for msg in messages:
            role = msg.get("role")
            if role == "system":
                out.append({"role": c["system_role"], "content": msg.get("content") or ""})
            elif role == "assistant":
                item = {"role": "assistant", "content": msg.get("content") or None}
                if msg.get("tool_calls"):
                    item["tool_calls"] = [{"id": t["id"], "type": "function",
                                           "function": {"name": t["name"], "arguments": t.get("arguments") or "{}"}}
                                          for t in msg["tool_calls"]]
                    if c["send_reasoning_back"] and msg.get("reasoning"):
                        item["reasoning_content"] = msg["reasoning"]
                if item["content"] is None and not item.get("tool_calls"):
                    item["content"] = ""
                out.append(item)
            elif role == "tool":
                item = {"role": "tool", "tool_call_id": msg["tool_call_id"], "content": msg.get("content") or ""}
                if c["tool_result_name"]:
                    item["name"] = msg.get("name") or ""
                out.append(item)
            else:
                out.append({"role": "user", "content": msg.get("content") or ""})
        payload = {"model": self.model, "messages": out, "stream": bool(stream)}
        if tools:
            payload["tools"] = []
            for tool in tools:
                fn = dict(tool["function"])
                if c["strict_tools"]:
                    fn["strict"] = True
                payload["tools"].append({"type": "function", "function": fn})
        if max_tokens:
            payload[c["max_tokens_field"]] = int(max_tokens)
        if stream and c["stream_usage"]:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _debug(self, kind, data):
        if not self.debug_path:
            return
        try:
            os.makedirs(os.path.dirname(self.debug_path), exist_ok=True)
            with open(self.debug_path, "a", encoding="utf-8") as file:
                file.write(json.dumps({"t": time.time(), "kind": kind, "data": data}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def complete(self, messages, tools=None, *, stream=True, max_tokens=4096, on_delta=None, cancel=None):
        started = time.monotonic()
        state = {"content": [], "reasoning": [], "calls": {}, "finish": None, "usage": None, "first": None}
        payload = self.build_payload(messages, tools, stream, max_tokens)
        self._debug("request", {"endpoint": self.endpoint, "payload": payload})
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         method="POST", headers={"Content-Type": "application/json",
                                                                 "Authorization": f"Bearer {self.api_key}",
                                                                 "Accept": "text/event-stream" if stream else "application/json"})
        error = ""
        try:
            resp = urllib.request.urlopen(request, timeout=self.timeout)
            with self._lock:
                self._resp = resp
            try:
                if stream:
                    self._read_stream(resp, state, on_delta, cancel)
                else:
                    self._read_whole(resp, state)
            finally:
                with self._lock:
                    self._resp = None
                resp.close()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:600]
            except Exception:
                pass
            error = f"模型服务返回 HTTP {exc.code}：{detail or exc.reason}"
        except urllib.error.URLError as exc:
            error = f"无法连接模型服务：{getattr(exc, 'reason', exc)}"
        except (TimeoutError, socket.timeout):
            error = f"模型服务超时（>{self.timeout}s）"
        except Exception as exc:  # noqa: BLE001 - 关闭响应中止时读取会抛出各种异常
            if not (cancel is not None and cancel.is_set()):
                error = f"调用模型出错：{exc}"
        aborted = cancel is not None and cancel.is_set()
        finish = "aborted" if aborted else ("error" if error else FINISH_MAP.get(state["finish"] or "", None))
        calls = parse_tool_calls([state["calls"][k] for k in sorted(state["calls"])])
        if finish is None:
            finish = "tool_calls" if calls else "stop"
        content, reasoning = "".join(state["content"]), "".join(state["reasoning"])
        usage = _usage(state["usage"]) if state["usage"] is not None else normalize_usage(
            None, estimated_output=int(estimate_tokens(content + reasoning + "".join(c["arguments"] for c in calls))))
        now = time.monotonic()
        first = state["first"]
        result = ChatResult(content=content, reasoning=reasoning, tool_calls=calls, finish_reason=finish, error=error,
                            usage=usage, ttft_ms=int(((first or now) - started) * 1000),
                            duration_ms=int((now - started) * 1000), gen_ms=int((now - (first or now)) * 1000))
        self._debug("response", {k: v for k, v in result.items()})
        return result

    def _mark(self, state):
        if state["first"] is None:
            state["first"] = time.monotonic()

    def _read_stream(self, resp, state, on_delta, cancel):
        fields = self.compat["reasoning_fields"]
        for raw in resp:
            if cancel is not None and cancel.is_set():
                return
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if obj.get("error"):
                raise RuntimeError(str(obj["error"].get("message") if isinstance(obj["error"], dict) else obj["error"]))
            if obj.get("usage"):
                state["usage"] = obj["usage"]
            for choice in obj.get("choices") or []:
                delta = choice.get("delta") or {}
                for field in fields:
                    if delta.get(field):
                        self._mark(state)
                        state["reasoning"].append(delta[field])
                        on_delta and on_delta("think", delta[field], None)
                        break
                if delta.get("content"):
                    self._mark(state)
                    state["content"].append(delta["content"])
                    on_delta and on_delta("text", delta["content"], None)
                for tc in delta.get("tool_calls") or []:
                    self._mark(state)
                    idx = tc.get("index", len(state["calls"]))
                    call = state["calls"].setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    call["id"] = call["id"] or tc.get("id") or ""
                    fn = tc.get("function") or {}
                    if fn.get("name") and not call["name"]:
                        call["name"] = fn["name"]
                    if fn.get("arguments"):
                        call["arguments"] += fn["arguments"]
                    on_delta and on_delta("args", fn.get("arguments") or "", {"index": idx, "name": call["name"]})
                if choice.get("finish_reason"):
                    state["finish"] = choice["finish_reason"]

    def _read_whole(self, resp, state):
        data = json.loads(resp.read().decode("utf-8", "replace"))
        self._mark(state)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        state["content"].append(content)
        for field in self.compat["reasoning_fields"]:
            if msg.get(field):
                state["reasoning"].append(msg[field])
                break
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            state["calls"][i] = {"id": tc.get("id") or "", "name": fn.get("name") or "", "arguments": fn.get("arguments") or ""}
        state["finish"] = choice.get("finish_reason")
        state["usage"] = data.get("usage")
