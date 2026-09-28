"""脚本化假模型：只在进程环境变量 OMRS_AGENT_FAUX_SCRIPT 指向脚本文件时可用（配置接口无法开启）。

脚本 JSON：{"scenarios":[{"match":"正则","rounds":[轮, ...]}], "default":{"rounds":[...]}}
每一轮：{"think":"…","text":"…","tool_calls":[{"name":"…","arguments":{…}}],"finish_reason":"length",
        "error":"…","ttft_ms":600,"tps":55}
按这次运行第一次请求时最近一条用户消息选场景，之后每次请求依次取下一轮。字符串里可用模板：
{{last_user}}；{{r:工具名.路径}}（最近一次该工具结果里的值，路径用 . 分隔）；
整串恰好是 {{raw:工具名.路径}} 时代入原始 JSON 值，{{pluck:工具名.路径.字段}} 代入列表里该字段组成的列表；{{refs:工具名.路径.字段}} 把列表里的字段拼成 `a`、`b`。
"""
import json
import os
import re
import time

from .openai_compat import ChatResult, estimate_tokens, parse_tool_calls

ENV = "OMRS_AGENT_FAUX_SCRIPT"


def faux_script_path():
    path = os.environ.get(ENV, "").strip()
    return path if path and os.path.isfile(path) else ""


def _tool_results(messages):
    names = {}
    for msg in messages:
        for call in msg.get("tool_calls") or []:
            names[call["id"]] = call["name"]
    results = {}
    for msg in messages:
        if msg.get("role") == "tool":
            try:
                results[names.get(msg.get("tool_call_id"), "")] = json.loads(msg.get("content") or "null")
            except json.JSONDecodeError:
                pass
    return results


def _text_of(content):
    """用户消息的文字：内容块数组（附图）时拼接其中的文字块。"""
    if isinstance(content, list):
        return "\n".join(p.get("text") or "" for p in content if isinstance(p, dict) and p.get("type") == "text")
    return content or ""


def _dig(value, path):
    for part in [p for p in path.split(".") if p]:
        if isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


class FauxClient:
    def __init__(self, script_path, model="faux"):
        with open(script_path, "r", encoding="utf-8") as file:
            self.script = json.load(file)
        self.model = model
        self.rounds = None
        self.index = 0

    def cancel(self):
        pass

    def _pick(self, messages):
        last = next((_text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
        for sc in self.script.get("scenarios", []):
            if re.search(sc.get("match", "$^"), last):
                return sc["rounds"]
        return (self.script.get("default") or {}).get("rounds") or [{"text": "（假模型没有匹配的脚本）"}]

    def _fill(self, value, ctx):
        if isinstance(value, dict):
            return {k: self._fill(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._fill(v, ctx) for v in value]
        if not isinstance(value, str):
            return value
        m = re.fullmatch(r"\{\{raw:([\w]+)\.?([\w.]*)\}\}", value)
        if m:
            return _dig(ctx["results"].get(m.group(1)), m.group(2))
        m = re.fullmatch(r"\{\{pluck:([\w]+)\.([\w.]+)\.(\w+)\}\}", value)
        if m:
            items = _dig(ctx["results"].get(m.group(1)), m.group(2)) or []
            return [_dig(i, m.group(3)) for i in items if isinstance(i, dict)]

        def sub(match):
            kind, body = match.group(1), match.group(2)
            if kind == "last_user":
                return ctx["last_user"]
            tool, _, path = body.partition(".")
            if kind == "refs":
                path, _, field = path.rpartition(".")
                items = _dig(ctx["results"].get(tool), path) or []
                return "、".join(f"`{_dig(i, field)}`" for i in items if isinstance(i, dict))
            got = _dig(ctx["results"].get(tool), path)
            return "" if got is None else (got if isinstance(got, str) else json.dumps(got, ensure_ascii=False))
        return re.sub(r"\{\{(last_user|r|refs)(?::([\w.]+))?\}\}", sub, value)

    def complete(self, messages, tools=None, *, stream=True, max_tokens=4096, on_delta=None, cancel=None):
        started = time.monotonic()
        if self.rounds is None:
            self.rounds = self._pick(messages)
        spec = self.rounds[min(self.index, len(self.rounds) - 1)] if self.index < len(self.rounds) else {"text": "（脚本已结束）"}
        self.index += 1
        ctx = {"results": _tool_results(messages),
               "last_user": next((_text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")}
        tps = float(spec.get("tps", 60))

        def pause(ms):
            end = time.monotonic() + ms / 1000
            while time.monotonic() < end:
                if cancel is not None and cancel.is_set():
                    return False
                time.sleep(min(0.02, max(0.0, end - time.monotonic())))
            return True

        def emit(kind, text, extra=None):
            for i in range(0, len(text), 3):
                piece = text[i:i + 3]
                if not pause(estimate_tokens(piece) / tps * 1000):
                    return False
                on_delta and on_delta(kind, piece, extra)
            return True

        ok = pause(spec.get("ttft_ms", 400))
        first = time.monotonic()
        think = self._fill(spec.get("think", ""), ctx)
        text = self._fill(spec.get("text", ""), ctx)
        calls = []
        for i, call in enumerate(spec.get("tool_calls") or []):
            args = call.get("raw_arguments")
            if args is None:
                args = json.dumps(self._fill(call.get("arguments", {}), ctx), ensure_ascii=False)
            calls.append({"id": f"call_{os.urandom(3).hex()}", "name": call["name"], "arguments": args})
        ok = ok and emit("think", think) and emit("text", text)
        for i, call in enumerate(calls):
            ok = ok and emit("args", call["arguments"], {"index": i, "name": call["name"]})
        now = time.monotonic()
        aborted = not ok or (cancel is not None and cancel.is_set())
        prompt = int(sum(estimate_tokens(json.dumps(m, ensure_ascii=False)) for m in messages)) + 2400
        finish = "aborted" if aborted else ("error" if spec.get("error") else spec.get("finish_reason") or (
            "tool_calls" if calls else "stop"))
        return ChatResult(content=text, reasoning=think, tool_calls=parse_tool_calls(calls), finish_reason=finish,
                          error=spec.get("error", ""),
                          usage={"prompt": prompt, "completion": int(estimate_tokens(think + text) + sum(
                              estimate_tokens(c["arguments"]) for c in calls)), "cached": int(prompt * 0.6) // 64 * 64,
                                 "reasoning": int(estimate_tokens(think))},
                          ttft_ms=int((first - started) * 1000), duration_ms=int((now - started) * 1000),
                          gen_ms=int((now - first) * 1000))
