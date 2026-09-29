"""通用 Agent 循环（与 OMRS 无关，参照 Pi packages/agent 的 runLoop）。

照搬的行为：
1. 内层循环处理工具调用与运行中插话（steering，在下一次模型请求前注入）；模型给出最终回答后若还有排队的
   插话，作为追问（follow-up）继续下一轮；
2. finish_reason 为 length 时，这一轮的全部工具调用一律判失败、不执行（参数可能残缺）；
3. 工具出错、工具不存在、参数不合 schema：错误作为工具结果交还模型，循环继续；
4. 中止：未完成的工具调用补「已中止」结果，保证会话记录前后一致；中止在工具之间生效，不打断正在执行的工具；
5. 工具串行执行；执行前后有钩子（before 做权限判定，after 做审计与结果截断）；
6. 结束原因明确：completed / aborted / error / budget / max_rounds。
"""
import json
import time

from .policy import Budget


def validate_args(schema: dict, args) -> str:
    """JSON Schema 的小子集：object / 必填 / 基本类型 / enum / maxItems / minimum / maximum。返回错误描述或空串。"""
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}

    def check(sch, value, where):
        t = sch.get("type")
        if t and not isinstance(value, types[t]) or (t in ("integer", "number") and isinstance(value, bool)):
            return f"{where} 应为 {t}"
        if "enum" in sch and value not in sch["enum"]:
            return f"{where} 只能是 " + "、".join(map(str, sch["enum"]))
        if t in ("integer", "number"):
            if "minimum" in sch and value < sch["minimum"]:
                return f"{where} 不能小于 {sch['minimum']}"
            if "maximum" in sch and value > sch["maximum"]:
                return f"{where} 不能大于 {sch['maximum']}"
        if t == "string" and sch.get("minLength") and len(value.strip()) < sch["minLength"]:
            return f"{where} 不能为空"
        if t == "array":
            if "maxItems" in sch and len(value) > sch["maxItems"]:
                return f"{where} 最多 {sch['maxItems']} 项"
            if "minItems" in sch and len(value) < sch["minItems"]:
                return f"{where} 至少 {sch['minItems']} 项"
            for i, item in enumerate(value):
                err = check(sch.get("items") or {}, item, f"{where}[{i}]")
                if err:
                    return err
        if t == "object":
            for key in sch.get("required", []):
                if key not in value:
                    return f"缺少参数 {where + '.' if where != '参数' else ''}{key}"
            props = sch.get("properties") or {}
            for key, item in value.items():
                if key not in props:
                    if sch.get("additionalProperties") is False:
                        return f"未知参数 {key}"
                    continue
                err = check(props[key], item, key)
                if err:
                    return err
        return ""
    return check(schema, args, "参数")


class ToolOutcome:
    def __init__(self, status, content, result=None, summary="", commits=None, error=""):
        self.status, self.content, self.result = status, content, result
        self.summary, self.commits, self.error = summary, commits or [], error


def result_content(result, cap):
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > cap:
        return text[:cap] + f"…（结果超过 {cap} 字符，已截断；请缩小范围或翻页）", len(text)
    return text, len(text)


class AgentLoop:
    def __init__(self, client, registry, hooks, emit, limits, result_cap=6000, max_output_tokens=10240):
        self.client, self.registry, self.hooks, self.emit = client, registry, hooks, emit
        self.budget = Budget(limits)
        self.result_cap = result_cap
        self.max_output_tokens = max_output_tokens

    def run(self, messages, system, *, take_steering, abort, on_message):
        """messages：会话消息（不含 system，本函数就地追加）。返回 {reason, error}。"""
        tools = self.registry.schemas()
        while True:
            if abort.is_set():
                return {"reason": "aborted", "error": ""}
            for text in take_steering(self.budget.rounds + 1):
                msg = {"role": "user", "content": text}
                messages.append(msg)
                on_message(msg)
            if self.budget.rounds >= self.budget.limits["rounds"]:
                return {"reason": "max_rounds", "error": f"模型请求轮数达到上限 {self.budget.limits['rounds']}"}
            self.budget.rounds += 1
            n = self.budget.rounds
            self.emit("round.start", {"n": n, "context": self.hooks.context_estimate(system, tools, messages)})

            def on_delta(kind, text, extra, _n=n):
                data = {"n": _n, "kind": kind, "text": text}
                if extra:
                    data.update(extra)
                self.emit("delta", data)

            res = self.client.complete([{"role": "system", "content": system}] + messages, tools,
                                       max_tokens=self.max_output_tokens, on_delta=on_delta, cancel=abort)
            self.emit("round.end", {"n": n, "finish": res["finish_reason"], "usage": res["usage"],
                                    "ttft_ms": res["ttft_ms"], "duration_ms": res["duration_ms"], "gen_ms": res["gen_ms"],
                                    "error": res.get("error", "")})
            if res["finish_reason"] == "error":
                return {"reason": "error", "error": res.get("error") or "模型返回错误"}
            assistant = {"role": "assistant", "content": res["content"] or ""}
            if res["reasoning"]:
                assistant["reasoning"] = res["reasoning"]
            calls = res["tool_calls"]
            if calls:
                assistant["tool_calls"] = [{"id": c["id"], "name": c["name"], "arguments": c["arguments"]} for c in calls]
            if res["content"] or calls or res["reasoning"]:
                messages.append(assistant)
                on_message(assistant)
            if res["finish_reason"] == "aborted" or abort.is_set():
                self._fill_aborted(messages, on_message, calls, 0)
                return {"reason": "aborted", "error": ""}
            if not calls:
                follow = take_steering(None)
                if follow:
                    for text in follow:
                        msg = {"role": "user", "content": text}
                        messages.append(msg)
                        on_message(msg)
                    continue
                return {"reason": "completed", "error": ""}
            for call in calls:
                tool = self.registry.get(call["name"])
                self.emit("tool.call", {"n": n, "call_id": call["id"], "name": call["name"], "args": call["args"],
                                        "arguments": call["arguments"], "level": tool.level if tool else "read",
                                        "known": bool(tool)})
            budget_hit = ""
            for i, call in enumerate(calls):
                if abort.is_set():
                    self._fill_aborted(messages, on_message, calls, i)
                    return {"reason": "aborted", "error": ""}
                if res["finish_reason"] == "length":
                    outcome = self._fail(call, "模型输出达到长度上限被截断，参数可能不完整，这次调用没有执行")
                elif budget_hit:
                    outcome = self._fail(call, budget_hit, status="aborted")
                else:
                    outcome = self._execute(call)
                    if outcome.status == "budget":
                        budget_hit = outcome.error
                        outcome.status = "error"
                msg = {"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": outcome.content}
                messages.append(msg)
                on_message(msg)
            if budget_hit:
                return {"reason": "budget", "error": budget_hit}

    def _fail(self, call, text, status="error"):
        self.emit("tool.end", {"call_id": call["id"], "status": status, "error": text, "summary": ""})
        return ToolOutcome(status, json.dumps({"ok": False, "error": text}, ensure_ascii=False), error=text)

    def _fill_aborted(self, messages, on_message, calls, start):
        for call in calls[start:]:
            self.emit("tool.end", {"call_id": call["id"], "status": "aborted", "error": "已中止", "summary": ""})
            msg = {"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                   "content": json.dumps({"ok": False, "error": "运行已中止，这次调用没有执行"}, ensure_ascii=False)}
            messages.append(msg)
            on_message(msg)

    def _execute(self, call):
        tool = self.registry.get(call["name"])
        if tool is None:
            return self._fail(call, f"工具 {call['name']} 不存在")
        if call["parse_error"]:
            return self._fail(call, call["parse_error"])
        err = validate_args(tool.schema, call["args"])
        if err:
            return self._fail(call, err)
        if self.budget.calls >= self.budget.limits["calls"]:
            text = f"工具调用次数达到本次运行上限 {self.budget.limits['calls']}，运行结束"
            self.emit("tool.end", {"call_id": call["id"], "status": "error", "error": text, "summary": ""})
            return ToolOutcome("budget", json.dumps({"ok": False, "error": text}, ensure_ascii=False), error=text)
        self.budget.calls += 1
        if tool.level != "read" and self.budget.writes >= self.budget.limits["writes"]:
            text = f"写入次数达到本次运行上限 {self.budget.limits['writes']}，运行结束"
            self.emit("tool.end", {"call_id": call["id"], "status": "error", "error": text, "summary": ""})
            return ToolOutcome("budget", json.dumps({"ok": False, "error": text}, ensure_ascii=False), error=text)
        verdict = self.hooks.before_tool_call(call, tool)
        if verdict is not None:
            self.emit("tool.end", {"call_id": call["id"], "status": verdict["status"], "error": verdict["error"],
                                   "summary": "", "decision": verdict.get("decision")})
            return ToolOutcome(verdict["status"], json.dumps({"ok": False, "error": verdict["error"]}, ensure_ascii=False),
                               error=verdict["error"])
        started = time.monotonic()
        self.emit("tool.running", {"call_id": call["id"]})
        try:
            out = self.hooks.execute(call, tool)
        except Exception as exc:  # noqa: BLE001 - 工具出错交还模型
            text = f"工具出错：{exc}"
            self.emit("tool.end", {"call_id": call["id"], "status": "error", "error": text, "summary": "",
                                   "dur_ms": int((time.monotonic() - started) * 1000)})
            return ToolOutcome("error", json.dumps({"ok": False, "error": text}, ensure_ascii=False), error=text)
        wrote = bool(out["commits"] or out.get("wrote"))  # 不写 Ledger 的写入工具（建草稿）自己声明算一次写入
        if wrote:
            self.budget.writes += 1
        content, chars = result_content(out["result"], self.result_cap)
        self.hooks.after_tool_call(call, tool, out)
        self.emit("tool.end", {"call_id": call["id"], "status": "done", "summary": out.get("summary", ""),
                               "result": out["result"] if chars <= 20000 else None, "result_chars": chars,
                               "commits": out["commits"], "wrote": wrote, "extra": out.get("extra"),
                               "dur_ms": int((time.monotonic() - started) * 1000), "budget": self.budget.snapshot()})
        return ToolOutcome("done", content, out["result"], out.get("summary", ""), out["commits"])
