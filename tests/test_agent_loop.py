"""E1 / E3：通用循环的行为（照搬 Pi runLoop 的 6 条）与服务端权限（确认令牌、过期、预算）。模型用桩客户端。"""
import json
import os
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs.agent.loop import AgentLoop, validate_args  # noqa: E402
from omrs.agent.policy import PendingConfirm, confirm_token  # noqa: E402
from omrs.agent.tools import Registry, ToolDef  # noqa: E402
from omrs.llm.openai_compat import ChatResult, parse_tool_calls  # noqa: E402

LIMITS = {"rounds": 25, "calls": 40, "writes": 20}


def reply(text="", calls=None, finish=None):
    raw = [{"id": f"c{i}", "name": n, "arguments": a if isinstance(a, str) else json.dumps(a)} for i, (n, a) in enumerate(calls or [])]
    return ChatResult(content=text, reasoning="", tool_calls=parse_tool_calls(raw), finish_reason=finish or ("tool_calls" if raw else "stop"),
                      error="", usage={"prompt": 10, "completion": 5, "cached": 0, "reasoning": 0}, ttft_ms=1, duration_ms=2, gen_ms=1)


class Stub:
    def __init__(self, replies, on_call=None):
        self.replies, self.seen, self.on_call = list(replies), [], on_call

    def complete(self, messages, tools=None, **kw):
        self.seen.append([dict(m) for m in messages])
        if self.on_call:
            self.on_call(len(self.seen))
        return self.replies.pop(0) if self.replies else reply("完")

    def cancel(self):
        pass


class Hooks:
    def __init__(self, verdict=None):
        self.ran, self.verdict = [], verdict

    def context_estimate(self, *a):
        return {}

    def before_tool_call(self, call, tool):
        return self.verdict(call, tool) if self.verdict else None

    def execute(self, call, tool):
        self.ran.append(call["name"])
        out = tool.run({}, call["args"])
        return {**out, "commits": [{"commit_id": "CMT-1"}] if tool.level != "read" else []}

    def after_tool_call(self, *a):
        pass


def boom(ctx, args):
    raise RuntimeError("坏了")


REG = Registry([
    ToolDef("echo", "read", "", {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}, lambda c, a: {"result": {"x": a["x"]}, "summary": ""}),
    ToolDef("boom", "read", "", {"type": "object"}, boom),
    ToolDef("write", "rev", "", {"type": "object"}, lambda c, a: {"result": {"ok": True}, "summary": ""}),
])


def run(stub, hooks=None, steer=None, abort=None, limits=LIMITS):
    events, msgs = [], [{"role": "user", "content": "hi"}]
    loop = AgentLoop(stub, REG, hooks or Hooks(), lambda t, d: events.append((t, d)), limits)
    out = loop.run(msgs, "sys", take_steering=steer or (lambda n: []), abort=abort or threading.Event(), on_message=lambda m: None)
    return out, msgs, events


class LoopTest(unittest.TestCase):
    def test_tool_then_answer_completes(self):
        out, msgs, events = run(Stub([reply(calls=[("echo", {"x": 1})]), reply("好")]))
        self.assertEqual(out["reason"], "completed")
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "tool", "assistant"])
        self.assertIn(("tool.end"), [e[0] for e in events])

    def test_errors_go_back_to_model(self):
        hooks = Hooks()
        out, msgs, _ = run(Stub([reply(calls=[("boom", {}), ("nope", {}), ("echo", {"x": "a"}), ("echo", "{bad")]), reply("好")]), hooks)
        self.assertEqual(out["reason"], "completed")
        tool_msgs = [json.loads(m["content"]) for m in msgs if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 4)
        self.assertTrue(all(t["ok"] is False for t in tool_msgs))
        self.assertIn("坏了", tool_msgs[0]["error"])
        self.assertIn("不存在", tool_msgs[1]["error"])
        self.assertIn("integer", tool_msgs[2]["error"])
        self.assertIn("JSON", tool_msgs[3]["error"])

    def test_length_finish_fails_all_calls(self):
        hooks = Hooks()
        out, msgs, _ = run(Stub([reply(calls=[("echo", {"x": 1}), ("write", {})], finish="length"), reply("好")]), hooks)
        self.assertEqual(hooks.ran, [])
        self.assertTrue(all("截断" in json.loads(m["content"])["error"] for m in msgs if m["role"] == "tool"))
        self.assertEqual(out["reason"], "completed")

    def test_abort_between_tools_fills_results(self):
        abort = threading.Event()
        hooks = Hooks()

        def verdict(call, tool):
            abort.set()
            return None
        hooks.verdict = verdict
        out, msgs, _ = run(Stub([reply(calls=[("echo", {"x": 1}), ("echo", {"x": 2})])]), hooks, abort=abort)
        self.assertEqual(out["reason"], "aborted")
        self.assertEqual(hooks.ran, ["echo"])
        calls = [c["id"] for m in msgs for c in m.get("tool_calls", [])]
        answered = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
        self.assertEqual(sorted(calls), sorted(answered))

    def test_steering_is_injected_before_next_request_and_followup_continues(self):
        queue = [["插一句"], [], ["追问"]]
        stub = Stub([reply(calls=[("echo", {"x": 1})]), reply("答"), reply("再答")])
        out, msgs, _ = run(stub, steer=lambda n: queue.pop(0) if queue else [])
        self.assertEqual(out["reason"], "completed")
        self.assertEqual(stub.seen[0][-1]["content"], "插一句")
        self.assertEqual(stub.seen[2][-1]["content"], "追问")

    def test_budgets(self):
        many = [reply(calls=[("echo", {"x": i})]) for i in range(5)]
        out, _, _ = run(Stub(many), limits={"rounds": 25, "calls": 2, "writes": 20})
        self.assertEqual(out["reason"], "budget")
        out, _, _ = run(Stub([reply(calls=[("write", {}), ("write", {})])]), limits={"rounds": 25, "calls": 40, "writes": 1})
        self.assertEqual(out["reason"], "budget")
        out, _, _ = run(Stub(many), limits={"rounds": 2, "calls": 40, "writes": 20})
        self.assertEqual(out["reason"], "max_rounds")

    def test_denied_confirm_is_not_executed(self):
        hooks = Hooks(lambda call, tool: {"status": "denied", "error": "用户未允许，没有执行"})
        out, msgs, _ = run(Stub([reply(calls=[("write", {})]), reply("好")]), hooks)
        self.assertEqual(hooks.ran, [])
        self.assertIn("未允许", json.loads([m for m in msgs if m["role"] == "tool"][0]["content"])["error"])

    def test_schema_subset(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "array", "maxItems": 2, "items": {"type": "string"}}, "b": {"type": "string", "enum": ["x"]}}}
        self.assertEqual(validate_args(schema, {"a": ["1"]}), "")
        self.assertIn("缺少", validate_args(schema, {}))
        self.assertIn("最多", validate_args(schema, {"a": ["1", "2", "3"]}))
        self.assertIn("只能是", validate_args(schema, {"a": [], "b": "y"}))


class PolicyTest(unittest.TestCase):
    def test_token_binds_arguments(self):
        a = confirm_token("run1", "update_question_section", {"uid": "x", "content": "a"})
        self.assertEqual(a, confirm_token("run1", "update_question_section", {"content": "a", "uid": "x"}))
        self.assertNotEqual(a, confirm_token("run1", "update_question_section", {"uid": "x", "content": "b"}))
        self.assertNotEqual(a, confirm_token("run2", "update_question_section", {"uid": "x", "content": "a"}))

    def test_decide_wait_and_expire(self):
        pc = PendingConfirm("r", "c", "t", {"a": 1}, ttl=5)
        with self.assertRaises(ValueError):
            pc.decide("wrong", "allow")
        threading.Timer(0.1, lambda: pc.decide(pc.token, "allow")).start()
        self.assertEqual(pc.wait(threading.Event()), "allow")
        with self.assertRaises(ValueError):
            pc.decide(pc.token, "deny")
        late = PendingConfirm("r", "c", "t", {}, ttl=0.2)
        started = time.monotonic()
        self.assertEqual(late.wait(threading.Event()), "expire")
        self.assertLess(time.monotonic() - started, 2)
        stop = threading.Event()
        stop.set()
        self.assertEqual(PendingConfirm("r", "c", "t", {}, ttl=5).wait(stop), "abort")


if __name__ == "__main__":
    unittest.main()
