"""运行时：后台运行线程、事件缓冲（轮询 / 长轮询）、确认与中止、全局并发上限。HTTP 接口见 http.py。

一条消息：POST /api/agent/message → 建 run、起后台线程、立即返回 run_id；浏览器 GET /api/agent/events?after=N
取增量事件。写锁只在单次工具执行期间持有；模型思考与网络等待期间不持锁。
"""
import datetime
import json
import os
import secrets
import threading
import time

from .. import drafts
from ..common import config_path
from ..actor import agent_actor
from ..ai_assist import collect_taxonomy
from ..labels import list_label_defs
from ..locking import write_lock
from ..llm.openai_compat import estimate_tokens
from .images import expand_images
from .config import CONFIRM_TTL_SECONDS, MSG_CAP, RESULT_CHAR_CAP, make_client, settings
from .loop import AgentLoop
from .policy import PendingConfirm
from .store import AgentStore, now_iso
from .tools import build_registry

MAX_MESSAGE_IMAGES = 6
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "system.md")
_RUNTIMES = {}
_RT_LOCK = threading.Lock()


class AgentError(Exception):
    def __init__(self, status, msg, data=None):
        super().__init__(msg)
        self.status, self.msg, self.data = status, msg, data or {}


def get_runtime(vault):
    key = os.path.abspath(vault)
    with _RT_LOCK:
        if key not in _RUNTIMES:
            _RUNTIMES[key] = AgentRuntime(key)
        return _RUNTIMES[key]


def _probe_png():
    import base64
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * 8 for _ in range(8))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


PROBE_PNG = _probe_png()


def build_system_prompt(vault, limits, draft_mode="silent"):
    tax = collect_taxonomy(vault)
    lines = [f"- {s}：" + "、".join(tax["categories_by_subject"].get(s, [])) for s in tax["subjects"]]
    labels = [d["name"] for d in list_label_defs(vault)]
    text = "科目与分类：\n" + ("\n".join(lines) or "（题库还是空的）")
    text += "\n标记：" + ("、".join(labels) or "（还没有标记）")
    with open(PROMPT_PATH, "r", encoding="utf-8") as file:
        tpl = file.read()
    draft_rule = ("当前是请求确认后入库：只有本对话的待审核草稿，才可先 get_draft 读取 revision，"
                  "再用 commit_draft 请求用户确认；拒绝、过期或草稿变化后不要沿用旧许可。" if
                  draft_mode == "confirm" else
                  "当前只建草稿。告诉用户去录入页的 AI 草稿区审核并入库，不请求助手直接提交。")
    return (tpl.replace("{today}", datetime.date.today().isoformat()).replace("{taxonomy}", text)
            .replace("{rounds}", str(limits["rounds"])).replace("{calls}", str(limits["calls"]))
            .replace("{writes}", str(limits["writes"])).replace("{draft_mode_rule}", draft_rule))


def model_messages(stored):
    """把存下的消息还原成模型上下文：去掉内部字段；缺结果的工具调用补「已中止」，保证前后一致。"""
    out, answered = [], {m.get("tool_call_id") for m in stored if m.get("role") == "tool"}
    for msg in stored:
        clean = {k: v for k, v in msg.items() if not k.startswith("_")}
        out.append(clean)
        for call in clean.get("tool_calls") or []:
            if call["id"] not in answered:
                out.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                            "content": json.dumps({"ok": False, "error": "运行被中断，这次调用没有执行"}, ensure_ascii=False)})
    return out


def compact_events(events):
    """持久化前把连续的同类增量合并成一条，时间取最后一段。"""
    out = []
    for ev in events:
        last = out[-1] if out else None
        if (last and ev["type"] == "delta" and last["type"] == "delta" and last["data"]["kind"] == ev["data"]["kind"]
                and last["data"]["n"] == ev["data"]["n"] and last["data"].get("index") == ev["data"].get("index")):
            last["data"] = {**last["data"], "text": last["data"]["text"] + ev["data"]["text"]}
            last["t1"] = ev["t"]
            continue
        out.append(dict(ev))
    for i, ev in enumerate(out):
        ev["i"] = i
    return out


class Run:
    def __init__(self, run_id, conv_id, model):
        self.id, self.conv_id, self.model = run_id, conv_id, model
        self.events, self.cond = [], threading.Condition()
        self.abort, self.steer, self.pending = threading.Event(), [], {}
        self.status, self.done, self.t0, self.client = "running", False, time.monotonic(), None
        self.closing = False  # 收尾中：不再接插话，新消息开新运行

    def emit(self, type_, data):
        with self.cond:
            self.events.append({"i": len(self.events), "t": int((time.monotonic() - self.t0) * 1000),
                                "type": type_, "data": data})
            self.cond.notify_all()


class Hooks:
    def __init__(self, rt, run, registry):
        self.rt, self.run, self.registry = rt, run, registry
        self.ctx = {"vault": rt.vault, "run_id": run.id, "conversation_id": run.conv_id}
        self._draft_config_marks = {}

    def _draft_config_mark(self):
        try:
            info = os.stat(config_path(self.rt.vault))
            return (info.st_dev, info.st_ino, info.st_mtime_ns)
        except FileNotFoundError:
            return None

    def context_estimate(self, system, tools, messages):
        chat = sum(estimate_tokens(m.get("content") or "") + estimate_tokens(
            "".join(c.get("arguments") or "" for c in m.get("tool_calls") or [])) for m in messages if m["role"] != "tool")
        res = sum(estimate_tokens(m.get("content") or "") for m in messages if m["role"] == "tool")
        return {"sys": int(estimate_tokens(system)), "tools": int(estimate_tokens(json.dumps(tools, ensure_ascii=False))),
                "chat": int(chat), "res": int(res), "msgs": len(messages)}

    def before_tool_call(self, call, tool):
        if tool.level != "confirm":
            return None
        try:
            mark = self._draft_config_mark() if tool.name == "commit_draft" else None
            preview = tool.preview(self.ctx, call["args"]) if tool.preview else {}
            if tool.name == "commit_draft":
                if mark != self._draft_config_mark():
                    raise ValueError("助手配置在预览时已变化，请重新申请确认")
                self._draft_config_marks[call["id"]] = mark
        except Exception as exc:  # noqa: BLE001 - 参数本身不成立（题目不存在等）：不打扰用户，直接交还模型
            return {"status": "error", "error": f"工具出错：{exc}"}
        pc = PendingConfirm(self.run.id, call["id"], call["name"], call["args"], CONFIRM_TTL_SECONDS)
        self.run.pending[call["id"]] = pc
        self.run.status = "waiting"
        self.run.emit("tool.waiting", {"call_id": call["id"], "token": pc.token, "ttl_ms": CONFIRM_TTL_SECONDS * 1000,
                                       "expires_at": pc.expires_at, "preview": preview})
        how = pc.wait(self.run.abort)
        self.run.pending.pop(call["id"], None)
        self.run.status = "running"
        self.run.emit("tool.decision", {"call_id": call["id"], "how": how})
        self.rt.store.save_tool_call(self.run.id, call["id"], call["name"], tool.level, call["args"],
                                     "done" if how == "allow" else "denied", decision=how)
        if how == "allow":
            return None
        errors = {"deny": "用户未允许，没有执行", "expire": "确认已过期，没有执行", "abort": "运行已中止，没有执行"}
        return {"status": "aborted" if how == "abort" else "denied", "error": errors[how], "decision": how}

    def execute(self, call, tool):
        ctx = {**self.ctx, "tool_call_id": call["id"]}
        if tool.name == "commit_draft" and self._draft_config_marks.get(call["id"]) != self._draft_config_mark():
            raise ValueError("助手配置已变化，请重新读取草稿并重新申请确认")
        if tool.level == "read":
            out = tool.run(ctx, call["args"])
            return {**out, "commits": []}
        with write_lock():
            with agent_actor(self.run.conv_id, self.run.id, call["id"]) as actor:
                out = tool.run(ctx, call["args"])
        return {**out, "commits": list(actor.commits)}

    def after_tool_call(self, call, tool, out):
        self.rt.store.save_tool_call(self.run.id, call["id"], call["name"], tool.level, call["args"], "done",
                                     result=out["result"], commits=out["commits"])


def run_stats(events):
    s = {"rounds": 0, "calls": 0, "writes": 0, "commits": [], "usage": {"prompt": 0, "completion": 0, "cached": 0, "reasoning": 0},
         "ttft_ms": [], "gen_ms": 0}
    for ev in events:
        d = ev["data"]
        if ev["type"] == "round.end":
            s["rounds"] += 1
            for k in s["usage"]:
                s["usage"][k] += int((d.get("usage") or {}).get(k) or 0)
            s["ttft_ms"].append(d.get("ttft_ms", 0))
            s["gen_ms"] += d.get("gen_ms", 0)
        elif ev["type"] == "tool.call":
            s["calls"] += 1
        elif ev["type"] == "tool.end" and (d.get("commits") or d.get("wrote")):
            s["writes"] += 1
            s["commits"] += d.get("commits") or []
    return s


class AgentRuntime:
    def __init__(self, vault):
        self.vault = vault
        self.store = AgentStore(vault)
        self.store.interrupt_leftovers()
        self.runs, self.lock = {}, threading.Lock()

    # ── 状态与对话 ──
    def active_runs(self):
        return [r for r in self.runs.values() if not r.done and not r.closing]

    def status(self):
        s = settings(self.vault)
        live = self.active_runs()
        return {"enabled": s["enabled"], "configured": s["configured"], "missing": s["missing"], "faux": s["faux"],
                "model": s["model"], "compat": s["compat"]["name"], "base_host": s["base_host"],
                "context_window": s["compat"]["context_window"], "limits": s["limits"], "msg_cap": MSG_CAP,
                "confirm_ttl_ms": CONFIRM_TTL_SECONDS * 1000, "tools": build_registry(s).levels(),
                "active": [{"run_id": r.id, "conversation_id": r.conv_id, "status": r.status} for r in live]}

    def create_conversation(self, title=""):
        conv_id = "c_" + secrets.token_hex(4)
        return self.store.create_conversation(conv_id, (title or "新对话").strip()[:40])

    def delete_conversation(self, conv_id):
        if any(r.conv_id == conv_id for r in self.active_runs()):
            raise AgentError(409, "这个对话正在运行，先停止再删除")
        if not self.store.conversation(conv_id):
            raise AgentError(404, "对话不存在")
        self.store.delete_conversation(conv_id)
        return {"deleted": True}

    def list_conversations(self):
        live = {r.conv_id: r for r in self.active_runs()}
        out = []
        for c in self.store.conversations():
            runs = self.store.runs(c["id"])
            msgs = self.store.messages(c["id"])
            last = next((m for m in reversed(msgs) if m["role"] in ("assistant", "user") and m.get("content")), None)
            writes = sum(r["stats"].get("writes", 0) for r in runs if not r["reverted"])
            r = live.get(c["id"])
            out.append({"id": c["id"], "title": c["title"], "created_at": c["created_at"], "updated_at": c["updated_at"],
                        "msgs": c["msgs"], "runs": len(runs), "writes": writes, "snippet": (last or {}).get("content", "")[:120],
                        "reverted": any(x["reverted"] for x in runs), "live": r.status if r else ""})
        return out

    def conversation(self, conv_id):
        conv = self.store.conversation(conv_id)
        if not conv:
            raise AgentError(404, "对话不存在")
        msgs = self.store.messages(conv_id)
        items = []
        for run in self.store.runs(conv_id):
            starter = next((m for m in msgs if m["_run"] == run["id"] and m["role"] == "user"), None)
            if starter:
                items.append({"type": "user", "text": starter.get("content", ""), "at": starter["_at"],
                              "images": self._image_refs(conv_id, starter.get("_images"))})
            live = self.runs.get(run["id"])
            if live and not live.done:
                with live.cond:
                    events = list(live.events)
                run = {**run, "status": live.status}
            else:
                events = run["events"]
            items.append({"type": "run", "run": {k: v for k, v in run.items() if k != "events"}, "events": events,
                          "live": bool(live and not live.done)})
        return {"conversation": conv, "items": items, "msgs": len(msgs)}

    def _image_refs(self, conv_id, refs):
        out = []
        for ref in refs or []:
            try:
                row = drafts.resolve_image(self.vault, conv_id, ref)
            except ValueError:
                out.append({"ref": ref, "missing": True})
                continue
            out.append({"ref": row["ref"], "sha": row["sha256"], "width": row["width"], "height": row["height"]})
        return out

    # ── 发消息、插话、事件 ──
    def post_message(self, conv_id, text, images=None):
        text = (text or "").strip()
        images = images or []
        if not isinstance(images, list):
            raise AgentError(400, "images 必须是图片 data URL 数组")
        if len(images) > MAX_MESSAGE_IMAGES:
            raise AgentError(400, f"一条消息最多 {MAX_MESSAGE_IMAGES} 张图片")
        if not text and not images:
            raise AgentError(400, "消息不能为空")
        s = settings(self.vault)
        if not s["enabled"]:
            raise AgentError(403, "AI 助手未启用：请在「设置 → AI 助手」里打开")
        if not s["configured"]:
            raise AgentError(400, "AI 助手尚未配置：" + "、".join(s["missing"]))
        conv = self.store.conversation(conv_id)
        if not conv:
            raise AgentError(404, "对话不存在")
        with self.lock:
            here = next((r for r in self.active_runs() if r.conv_id == conv_id), None)
            if here:
                if images:
                    raise AgentError(409, "运行中不能插入图片，等这次回答结束再发")
                sid = "st_" + secrets.token_hex(3)
                with here.cond:
                    here.steer.append({"id": sid, "text": text})
                here.emit("steer.queued", {"id": sid, "text": text, "at": now_iso()})
                return {"run_id": here.id, "steered": True, "steer_id": sid}
            if len(self.active_runs()) >= s["limits"]["concurrent"]:
                raise AgentError(409, "另一个对话正在运行，等它结束再发")
            if self.store.message_count(conv_id) >= MSG_CAP:
                raise AgentError(409, f"这个对话已有 {MSG_CAP} 条消息，到上限了，请新开对话")
            run_id = "run_" + secrets.token_hex(4)
            refs = []
            for index, data_url in enumerate(images):  # 任何一张不合格：整条消息拒收，不建运行
                try:
                    refs.append(drafts.add_image(self.vault, data_url, conv_id, run_id)["ref"])
                except ValueError as exc:
                    raise AgentError(400, f"第 {index + 1} 张图片：{exc}")
            run = Run(run_id, conv_id, s["model"])
            self.runs[run.id] = run
            self.store.create_run(run.id, conv_id, s["model"])
            message = {"role": "user", "content": text}
            if refs:
                message["_images"] = list(dict.fromkeys(refs))
            self.store.add_message(conv_id, run.id, message)
            label = text or "[图片] " + "、".join(message.get("_images", []))
            title = label.replace("\n", " ")[:15] + ("…" if len(label) > 15 else "") if conv["title"] == "新对话" else None
            self.store.touch(conv_id, title)
        threading.Thread(target=self._execute, args=(run, s), name=f"omrs-agent-{run.id}", daemon=True).start()
        return {"run_id": run.id, "steered": False}

    def _execute(self, run, s):
        out = {"reason": "error", "error": ""}
        try:
            registry = build_registry(s)
            client = run.client = make_client(self.vault, s)
            system = build_system_prompt(self.vault, s["limits"], s["draft_mode"])
            run.emit("run.start", {"run_id": run.id, "model": s["model"], "limits": s["limits"], "started_at": now_iso(),
                                   "context_window": s["compat"]["context_window"], "vision": s["vision"]})
            messages = model_messages(expand_images(self.vault, run.conv_id, self.store.messages(run.conv_id),
                                                    s["vision"], run.emit, run.abort))

            def take_steering(n):
                with run.cond:
                    items, run.steer = run.steer, []
                for item in items:
                    run.emit("steer.delivered", {"id": item["id"], "round": n})
                return [item["text"] for item in items]

            loop = AgentLoop(client, registry, Hooks(self, run, registry), run.emit, s["limits"], RESULT_CHAR_CAP,
                             max_output_tokens=s["max_output_tokens"])
            out = loop.run(messages, system, take_steering=take_steering, abort=run.abort,
                           on_message=lambda m: self.store.add_message(run.conv_id, run.id, m))
        except Exception as exc:  # noqa: BLE001
            out = {"reason": "error", "error": f"运行出错：{exc}"}
        with self.lock:  # 与 post_message 互斥：此后到达的消息开新运行，不会落进已结束的运行
            run.closing = True
            with run.cond:
                late, run.steer = run.steer, []
        for item in late:  # 运行收尾时才到的插话：留在对话里，作为下一次运行的上下文
            self.store.add_message(run.conv_id, run.id, {"role": "user", "content": item["text"]})
            run.emit("steer.late", {"id": item["id"]})
        stats = run_stats(run.events)
        run.emit("run.end", {"reason": out["reason"], "error": out.get("error", ""), "stats": stats})
        self.store.save_run(run.id, status="done", reason=out["reason"], error=out.get("error", ""), stats=stats,
                            events=compact_events(run.events), ended=True)
        self.store.touch(run.conv_id)
        with run.cond:
            run.done, run.status = True, "done"
            run.cond.notify_all()

    def events(self, run_id, after=0, wait=0.0):
        run = self.runs.get(run_id)
        if run is None:
            stored = self.store.run(run_id)
            if not stored:
                raise AgentError(404, "运行不存在")
            evs = stored["events"]
            return {"events": evs[after:], "next": len(evs), "done": True, "status": "done", "compacted": True}
        deadline = time.monotonic() + max(0.0, min(25.0, wait))
        with run.cond:
            while len(run.events) <= after and not run.done and time.monotonic() < deadline:
                run.cond.wait(timeout=max(0.01, deadline - time.monotonic()))
            evs = run.events[after:]
            return {"events": evs, "next": after + len(evs), "done": run.done and after + len(evs) >= len(run.events),
                    "status": run.status}

    def confirm(self, run_id, call_id, token, decision):
        run = self.runs.get(run_id)
        pc = run.pending.get(call_id) if run else None
        if pc is None:
            raise AgentError(409, "没有等待确认的这次调用（可能已处理、已过期或运行已结束）")
        try:
            pc.decide(token, decision)
        except ValueError as exc:
            raise AgentError(400, str(exc))
        return {"call_id": call_id, "decision": decision}

    def abort(self, run_id):
        run = self.runs.get(run_id)
        if run is None or run.done:
            raise AgentError(409, "运行已经结束")
        run.abort.set()
        if run.client is not None:
            run.client.cancel()
        run.emit("run.aborting", {})
        return {"aborting": True}

    def test_connection(self):
        """用已保存的配置发一次带工具的非流式请求：确认地址、密钥、模型可用，且模型会调用工具。"""
        s = settings(self.vault)
        if not s["configured"]:
            raise AgentError(400, "还没配置好：" + "、".join(s["missing"]))
        client = make_client(self.vault, s)
        probe = [{"type": "function", "function": {"name": "ping", "description": "连通性测试：收到请求时调用一次",
                                                   "parameters": {"type": "object", "properties": {}}}}]
        res = client.complete([{"role": "system", "content": "这是连通性测试。请调用 ping 工具，不要输出别的内容。"},
                               {"role": "user", "content": "测试"}], probe, stream=False, max_tokens=64)
        if res["finish_reason"] == "error":
            raise AgentError(502, res.get("error") or "模型返回错误")
        out = {"model": s["model"], "ms": res["duration_ms"], "finish": res["finish_reason"],
               "tools": any(c["name"] == "ping" for c in res["tool_calls"]) or s["faux"]}
        if s["vision"]:  # 主 AI 支持图片：再发一张 8×8 白图，确认上游接受 image_url
            img = client.complete([{"role": "user", "content": [
                {"type": "text", "text": "这是连通性测试，图里是什么颜色？只回答颜色。"},
                {"type": "image_url", "image_url": {"url": PROBE_PNG}}]}], None, stream=False, max_tokens=32)
            out["vision_ok"] = img["finish_reason"] != "error"
            if not out["vision_ok"]:
                out["vision_error"] = img.get("error") or "模型返回错误"
        return out

    def revert(self, run_id, dry_run=True):
        from .revert import apply_revert, plan_revert
        if any(r.id == run_id for r in self.active_runs()):
            raise AgentError(409, "这次运行还没结束，结束后才能撤销")
        if not self.store.run(run_id):
            raise AgentError(404, "运行不存在")
        if dry_run:
            return plan_revert(self.vault, run_id)
        with write_lock():
            result = apply_revert(self.vault, run_id)
        if not result["ok"]:
            raise AgentError(409, result.get("msg") or "有冲突，这次运行不能整体撤销", result)
        info = {"at": now_iso(), "commits": result["new_commits"], "reverted": result["reverted"]}
        self.store.set_reverted(run_id, info)
        return {**result, "info": info}
