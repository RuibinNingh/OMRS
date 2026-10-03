"""运行时：后台运行线程、事件缓冲（轮询 / 长轮询）、确认与中止、全局并发上限。HTTP 接口见 http.py。

一条消息：POST /api/agent/message → 建 run、起后台线程、立即返回 run_id；浏览器 GET /api/agent/events?after=N
取增量事件。写锁只在单次工具执行期间持有；模型思考与网络等待期间不持锁。
"""
import collections
import contextlib
import datetime
import json
import os
import secrets
import threading
import time
import logging
import sqlite3

from .. import drafts, ai_review
from ..common import config_path
from ..actor import agent_actor
from ..ai_assist import collect_taxonomy
from ..labels import list_label_defs
from ..locking import write_lock
from ..vault_lifecycle import generation, lease, task, storage, VaultChanged
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


def _review_identity(run_id, call_id):
    return 'agent:' + ai_review.fingerprint([run_id, call_id])


def _review_deadline(row):
    if row.get('expires_at') is not None and time.time() >= row['expires_at']:
        raise ai_review.ReviewError('expired', '确认已过期，未执行写入', 409)


def _review_snapshot(vault, tool, args):
    """确认绑定受影响题目的身份、正文和学习状态；不以 UID 猜测新目标。"""
    from ..data_repository import resolve_question
    from ..content_history import read_question_file
    from ..ledger import connect, blob_hash
    from ..sessions import get_session, active_session_uids
    if tool == 'commit_draft':
        draft = drafts.get_draft(vault, args['draft_id'])
        return {'draft_id': args['draft_id'], 'revision': draft['revision'], 'status': draft['status'],
                'conversation_id': draft.get('conversation_id', ''),
                'draft_hash': ai_review.fingerprint(draft)}
    uids = ([args['uid']] if args.get('uid') else args.get('uids') or
            [item['uid'] for item in args.get('items', [])])
    selected = []
    with connect(vault) as db:
        for uid in dict.fromkeys(uids):
            row = resolve_question(vault, uid=uid.strip(), db=db)
            if not row:
                raise ValueError('题目不存在或已归档：' + uid)
            target = {key: row[key] for key in ('question_id', 'uid', 'file_path', 'subject', 'category',
                                               'archived', 'suspended')}
            target['content_hash'] = blob_hash(read_question_file(vault, row))
            if tool == 'record_feedback':
                mastery = db.execute('SELECT * FROM mastery_projection WHERE question_id=?',
                                     (row['question_id'],)).fetchone()
                target['mastery'] = dict(mastery) if mastery else None
            selected.append(target)
    snapshot = {'questions': selected}
    if tool == 'set_question_labels':
        snapshot['labels'] = list_label_defs(vault)
    if tool == 'create_review_session':
        snapshot['occupied'] = sorted(set(uids).intersection(active_session_uids(vault)))
    if tool == 'record_feedback':
        sid = (args.get('session_id') or '').strip()
        snapshot['session'] = get_session(vault, sid) if sid else None
        from ..config_repository import read, normalized_tuning
        snapshot['tuning'] = normalized_tuning(read(vault))
    if tool in ('create_category', 'move_question'):
        snapshot['taxonomy'] = collect_taxonomy(vault)
    return snapshot


def _verify_review_snapshot(vault, row):
    if row['tool'] in ('update_question_section', 'set_knowledge_points'):
        from ..question_update import prepare_update
        _, _, snapshot = prepare_update(vault, **row['payload'])
    else:
        snapshot = _review_snapshot(vault, row['tool'], row['payload'])
    if snapshot != row['snapshot']:
        raise ai_review.ReviewError('content_conflict', '确认后目标已变化，请重新申请审核', 409)


def _live_review(vault, row):
    """只找原运行；审核中心不会创建运行或重新唤起模型。"""
    rt = _RUNTIMES.get(os.path.abspath(vault))
    run = rt.runs.get(row['actor'].get('run_id')) if rt else None
    pc = run.pending.get(row['actor'].get('tool_call_id')) if run else None
    if (not run or run.done or run.closing or run.abort.is_set() or not pc or
            pc.operation_id != row['operation_id']):
        return None, None
    return run, pc


def review_decide(vault, row, decision):
    """持久批准成功后才唤醒唯一等待对象；聊天和中心共用同一状态机。"""
    run, pc = _live_review(vault, row)
    if not pc:
        return ai_review.set_state(vault, row['operation_id'], 'interrupted', error_code='interrupted')
    with pc.lock:
        if pc.event.is_set() or time.time() >= pc.expires_at:
            status = 'expired' if time.time() >= pc.expires_at else 'interrupted'
            result = ai_review.set_state(vault, row['operation_id'], status, expected_status='pending_confirmation')
            pc.close('expire' if status == 'expired' else 'abort')
            return result
        if pc.revision != row['revision'] or pc.effective_digest != row['effective_digest']:
            raise ai_review.ReviewError('revision_conflict', '确认票据已变化，请重新查看', 409)
        if decision == 'approve':
            try:
                _verify_review_snapshot(vault, row)
                _review_deadline(row)
            except (ValueError, RuntimeError, OSError) as exc:
                expired = getattr(exc, 'code', '') == 'expired'
                result = ai_review.set_state(vault, row['operation_id'], 'expired' if expired else 'conflict',
                    error_code=getattr(exc, 'code', 'content_conflict'), expected_status='pending_confirmation')
                pc.close('expire' if expired else 'deny')
                return result
        saved = []
        def persist():
            saved.append(ai_review.set_state(vault, row['operation_id'],
                'approved' if decision == 'approve' else 'rejected',
                expected_status='pending_confirmation', expected_revision=pc.revision))
        pc.decide(pc.token, 'allow' if decision == 'approve' else 'deny', persist)
        return saved[0]


def review_update(vault, row, patch, expected_revision):
    run, pc = _live_review(vault, row)
    if not pc:
        ai_review.set_state(vault, row['operation_id'], 'interrupted', error_code='interrupted')
        raise ai_review.ReviewError('state_conflict', '原运行已结束，不能修订提案', 409)
    from ..question_update import prepare_update
    payload = row['payload']
    payload, preview, snapshot = prepare_update(vault, payload['uid'], payload['question_id'],
        payload['expected_content_hash'], {**payload['patch'], **patch})
    preview = {**row['preview'], **preview}
    preview['after'] = preview['changes'][0]['after']
    if snapshot != row['snapshot']:
        raise ai_review.ReviewError('content_conflict', '题目已变化，请重新申请审核', 409)
    with pc.lock:
        if pc.event.is_set() or time.time() >= pc.expires_at:
            raise ai_review.ReviewError('state_conflict', '确认已处理或过期', 409)
        revised = ai_review.revise(vault, row['operation_id'], expected_revision, payload, preview)
        pc.revise(revised['revision'], revised['effective_digest'])
        run.emit('tool.waiting', {'call_id': pc.call_id, 'token': pc.token,
                 'ttl_ms': max(0, int((pc.expires_at-time.time())*1000)), 'expires_at': pc.expires_at,
                 'preview': preview, 'operation_id': row['operation_id'], 'revision': revised['revision']})
        return revised


class AgentError(Exception):
    def __init__(self, status, msg, data=None):
        super().__init__(msg)
        self.status, self.msg, self.data = status, msg, data or {}


def get_runtime(vault):
    key = os.path.abspath(vault)
    with lease(vault), _RT_LOCK:
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
                  "当前只建草稿。告诉用户去审核中心核对并入库，不请求助手直接提交。")
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


class Run:
    def __init__(self, run_id, conv_id, model, store=None):
        self.id, self.conv_id, self.model, self.store = run_id, conv_id, model, store
        self.events, self.cond = collections.deque(), threading.Condition()
        self.event_count, self.tail_bytes, self.statistics = 0, 0, []
        self.generation = generation(store.vault) if store else None
        self.abort, self.steer, self.pending = threading.Event(), [], {}
        self.status, self.done, self.t0, self.client = "running", False, time.monotonic(), None
        self.closing = False

    def emit(self, type_, data):
        manager = lease(self.store.vault, self.generation) if self.store else contextlib.nullcontext()
        with manager, self.cond:
            event = {"i": self.event_count, "t": int((time.monotonic() - self.t0) * 1000),
                     "type": type_, "data": data}
            if self.store:
                self.store.append_event(self.id, event)
            self.event_count += 1
            size = len(json.dumps(event, ensure_ascii=False, default=str).encode())
            if size <= 1024 * 1024:
                self.events.append(event)
                self.tail_bytes += size
            while len(self.events) > 1000 or self.tail_bytes > 1024 * 1024:
                removed = self.events.popleft()
                self.tail_bytes -= len(json.dumps(removed, ensure_ascii=False, default=str).encode())
            if type_ in ("round.end", "usage.aux", "tool.call", "tool.end"):
                fields = {key: value for key, value in data.items() if key in (
                    "request_id", "n", "usage", "ttft_ms", "gen_ms", "commits", "wrote")}
                self.statistics.append({**event, "data": fields})
            self.cond.notify_all()


class Hooks:
    def __init__(self, rt, run, registry):
        self.rt, self.run, self.registry = rt, run, registry
        self.ctx = {"vault": rt.vault, "run_id": run.id, "conversation_id": run.conv_id}
        self._draft_config_marks = {}
        self._review_ids = {}

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
        if tool.level == 'read':
            return None
        with lease(self.rt.vault), write_lock():
            row = ai_review.create(self.rt.vault, 'agent', tool.name, _review_identity(self.run.id, call['id']),
                call['args'], actor={'conversation_id': self.run.conv_id, 'run_id': self.run.id,
                                      'tool_call_id': call['id']})
            self._review_ids[call['id']] = row['operation_id']
            if row['status'] != 'running':
                return {'status': 'denied', 'error': '这次调用已处理或已过期，不能再次执行'}
            if tool.level != 'confirm':
                return None
            try:
                mark = self._draft_config_mark() if tool.name == 'commit_draft' else None
                if tool.name in ('update_question_section', 'set_knowledge_points'):
                    from ..question_update import prepare_agent
                    prepared = prepare_agent(self.rt.vault, tool.name, call['args'])
                    payload, preview, snapshot = (prepared[key] for key in ('payload', 'preview', 'snapshot'))
                    editable_fields = prepared['editable_fields']
                else:
                    payload = call['args']
                    preview = tool.preview(self.ctx, payload) if tool.preview else {}
                    snapshot = _review_snapshot(self.rt.vault, tool.name, payload)
                    editable_fields = []
                if tool.name == 'commit_draft':
                    if mark != self._draft_config_mark():
                        raise ValueError('助手配置在预览时已变化，请重新申请确认')
                    self._draft_config_marks[call['id']] = mark
                row = ai_review.prepare(self.rt.vault, row['operation_id'], payload, preview, snapshot,
                                        editable_fields=editable_fields)
            except Exception as exc:  # noqa: BLE001 - 无效提案记录失败，不进入用户等待
                ai_review.set_state(self.rt.vault, row['operation_id'], 'failed',
                                    error_code=getattr(exc, 'code', 'invalid_request'))
                return {'status': 'error', 'error': f'工具出错：{exc}'}
            pc = PendingConfirm(self.run.id, call["id"], call["name"], call["args"], CONFIRM_TTL_SECONDS,
                operation_id=row['operation_id'], revision=row['revision'], effective_digest=row['effective_digest'])
            pc.expires_at = row['expires_at']
            self.run.pending[call["id"]] = pc
        self.run.status = "waiting"
        self.run.emit("tool.waiting", {"call_id": call["id"], "token": pc.token, "ttl_ms": CONFIRM_TTL_SECONDS * 1000,
                                       "expires_at": pc.expires_at, "preview": preview,
                                       "operation_id": row['operation_id'], 'revision': row['revision']})
        how = pc.wait(self.run.abort)
        self.run.pending.pop(call["id"], None)
        self.run.status = "running"
        with lease(self.rt.vault), write_lock():
            row = ai_review.get(self.rt.vault, pc.operation_id)
            if how != 'allow' and row['status'] == 'pending_confirmation':
                ai_review.set_state(self.rt.vault, pc.operation_id,
                    {'deny': 'rejected', 'expire': 'expired', 'abort': 'cancelled'}[how],
                    error_code='interrupted' if how == 'abort' else '')
        self.run.emit("tool.decision", {"call_id": call["id"], "how": how})
        self.rt.store.save_tool_call(self.run.id, call["id"], call["name"], tool.level, call["args"],
                                     "done" if how == "allow" else "denied", decision=how)
        if how == "allow":
            return None
        errors = {"deny": "用户未允许，没有执行", "expire": "确认已过期，没有执行", "abort": "运行已中止，没有执行"}
        return {"status": "aborted" if how == "abort" else "denied", "error": errors[how], "decision": how}

    def execute(self, call, tool):
        ctx = {**self.ctx, "tool_call_id": call["id"], "emit_usage": lambda data: self.run.emit("usage.aux", data)}
        if tool.level == "read":
            out = tool.run(ctx, call["args"])
            return {**out, "commits": []}
        with lease(self.rt.vault), write_lock():
            if self.run.abort.is_set():
                operation_id = self._review_ids.get(call['id'])
                if operation_id:
                    ai_review.set_state(self.rt.vault, operation_id, 'cancelled', error_code='interrupted')
                raise ValueError('运行已中止，未执行写入')
            if tool.level == 'confirm':
                row = ai_review.get(self.rt.vault, self._review_ids[call['id']])
                if row['status'] != 'approved':
                    raise ValueError('这次调用没有有效批准')
                try:
                    if tool.name == 'commit_draft' and self._draft_config_marks.get(call['id']) != self._draft_config_mark():
                        raise ValueError('助手配置已变化，请重新读取草稿并重新申请确认')
                    _verify_review_snapshot(self.rt.vault, row)
                    _review_deadline(row)
                except Exception as exc:
                    ai_review.set_state(self.rt.vault, row['operation_id'],
                                        'expired' if getattr(exc, 'code', '') == 'expired' else 'conflict',
                                        error_code=getattr(exc, 'code', 'content_conflict'))
                    raise
                row = ai_review.set_state(self.rt.vault, row['operation_id'], 'applying', expected_status='approved')
            else:
                row = ai_review.create(self.rt.vault, 'agent', tool.name, _review_identity(self.run.id, call['id']),
                    call['args'], actor={'conversation_id': self.run.conv_id, 'run_id': self.run.id,
                                         'tool_call_id': call['id']})
                self._review_ids[call['id']] = row['operation_id']
                if row['status'] != 'running':
                    raise ValueError('这次调用已经处理，不能再次执行')
            with agent_actor(self.run.conv_id, self.run.id, call["id"]) as actor:
                try:
                    if tool.level == 'confirm':
                        _review_deadline(row)
                    if tool.name in ('update_question_section', 'set_knowledge_points'):
                        from ..question_update import apply_agent
                        out = apply_agent(self.rt.vault, row, ctx)
                    else:
                        out = tool.run(ctx, row['payload'])
                except Exception as exc:
                    ai_review.set_state(self.rt.vault, row['operation_id'],
                        'partial' if actor.commits else 'expired' if getattr(exc, 'code', '') == 'expired' else 'failed',
                        commits=list(actor.commits),
                        error_code=getattr(exc, 'code', 'internal_error'))
                    raise
        out['result'] = {**out['result'], 'operation_id': row['operation_id']}
        return {**out, "commits": list(out.get('commits') or actor.commits)}

    def after_tool_call(self, call, tool, out):
        self.rt.store.save_tool_call(self.run.id, call["id"], call["name"], tool.level, call["args"], "done",
                                     result=out["result"], commits=out["commits"])
        if tool.level != 'read':
            result = out['result']
            status = 'partial' if result.get('failed') else 'applied' if out['commits'] or out.get('wrote') else 'unchanged'
            try:
                ai_review.set_state(self.rt.vault, self._review_ids[call['id']], status,
                                    result=result, commits=out['commits'])
            except (OSError, sqlite3.Error):
                logging.getLogger(__name__).error('审核操作终态写入失败，保留原生结果待核对')


def run_stats(events):
    s = {"rounds": 0, "calls": 0, "writes": 0, "commits": [], "usage": {"prompt": 0, "completion": 0, "cached": 0, "reasoning": 0},
         "ttft_ms": [], "gen_ms": 0}
    requests = {}
    rounds = {}
    for ev in events:
        d = ev["data"]
        if ev["type"] == "round.end":
            key = d.get("request_id") or f"round:{d.get('n')}"
            requests[key] = d.get("usage") or {}
            rounds[key] = d
        elif ev["type"] == "usage.aux":
            requests[d.get("request_id") or f"aux:{ev.get('i')}"] = d.get("usage") or {}
        elif ev["type"] == "tool.call":
            s["calls"] += 1
        elif ev["type"] == "tool.end" and (d.get("commits") or d.get("wrote")):
            s["writes"] += 1
            s["commits"] += d.get("commits") or []
    s["rounds"] = len(rounds)
    s["ttft_ms"] = [d.get("ttft_ms", 0) for d in rounds.values()]
    s["gen_ms"] = sum(d.get("gen_ms", 0) for d in rounds.values())
    for usage in requests.values():
        for k in s["usage"]:
            value = usage.get(k)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                s["usage"][k] += value
    return s


class AgentRuntime:
    def __init__(self, vault):
        self.vault = vault
        self.store = AgentStore(vault)
        self.store.interrupt_leftovers()
        ai_review.invalidate(vault, reason='interrupted', source='agent')
        self.runs, self.lock = {}, threading.RLock()

    # ── 状态与对话 ──
    def active_runs(self):
        with self.lock:
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

    def list_conversations(self, limit=30, cursor=None):
        live = {run.conv_id: run for run in self.active_runs()}
        page = self.store.conversation_page(limit, cursor)
        for row in page["conversations"]:
            row["live"] = live[row["id"]].status if row["id"] in live else ""
            row["reverted"] = bool(row["reverted"])
            row["snippet"] = row["snippet"] or ""
        return page

    def conversation(self, conv_id, limit=20, cursor=None):
        conv = self.store.conversation(conv_id)
        if not conv:
            raise AgentError(404, "对话不存在")
        page = self.store.run_page(conv_id, limit, cursor)
        items = []
        for run in page["runs"]:
            starter = self.store.starter_message(run["id"])
            if starter:
                items.append({"type": "user", "item_key": "user:" + str(starter["_id"]),
                              "text": starter.get("content", ""), "at": starter["_at"],
                              "images": self._image_refs(conv_id, starter.get("_images"))})
            live = self.runs.get(run["id"])
            if live:
                run = {**run, "status": live.status}
            events = self.store.event_page(run["id"])
            items.append({"type": "run", "item_key": "run:" + run["id"],
                          "run": {key:value for key,value in run.items() if key != "events"},
                          "events": events["events"], "events_next": events["next"],
                          "events_has_more": events["has_more"], "live": bool(live and not live.done)})
        return {"conversation": conv, "items": items, "msgs": self.store.message_count(conv_id),
                "has_more": page["has_more"], "next_cursor": page["next_cursor"]}

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
    @storage
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
            run = Run(run_id, conv_id, s["model"], self.store)
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
        try:
            with task(self.vault, run.generation):
                self._execute_current(run, s)
        except VaultChanged:
            # 恢复前的网络结果不落入新世代；原库运行随备份保留。
            run.abort.set()
            with run.cond:
                run.done, run.status = True, "done"
                run.cond.notify_all()
            with self.lock:
                self.runs.pop(run.id, None)

    def _execute_current(self, run, s):
        out = {"reason": "error", "error": ""}
        try:
            registry = build_registry(s)
            client = run.client = make_client(self.vault, s)
            system = build_system_prompt(self.vault, s["limits"], s["draft_mode"])
            run.emit("run.start", {"run_id": run.id, "model": s["model"], "limits": s["limits"], "started_at": now_iso(),
                                   "context_window": s["compat"]["context_window"], "vision": s["vision"]})
            messages = model_messages(expand_images(self.vault, run.conv_id, self.store.messages(run.conv_id),
                                                    s["vision"], run.emit, run.abort, run.id))

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
        stats = run_stats(run.statistics)
        run.emit("run.end", {"reason": out["reason"], "error": out.get("error", ""), "stats": stats})
        self.store.save_run(run.id, status="done", reason=out["reason"], error=out.get("error", ""), stats=stats,
                            ended=True)
        self.store.touch(run.conv_id)
        with run.cond:
            run.done, run.status = True, "done"
            run.cond.notify_all()
        with self.lock:
            self.runs.pop(run.id, None)
        run.events.clear()
        run.tail_bytes = 0
        run.statistics.clear()

    def events(self, run_id, after=0, wait=0.0, limit=200):
        after, limit = int(after), max(1, min(500, int(limit)))
        if after < 0:
            raise AgentError(400, "事件游标不能为负数")
        run = self.runs.get(run_id)
        if run is not None:
            deadline = time.monotonic() + max(0.0,min(25.0,wait))
            with run.cond:
                while run.event_count <= after and not run.done and time.monotonic() < deadline:
                    run.cond.wait(timeout=max(0.01,deadline-time.monotonic()))
        stored = self.store.run(run_id)
        if stored is None:
            raise AgentError(404, "运行不存在")
        page = self.store.event_page(run_id,after,limit)
        done = stored["status"] == "done"
        return {**page,"done":done and not page["has_more"],"status":run.status if run else stored["status"],"compacted":False}

    def confirm(self, run_id, call_id, token, decision, reviewer=None):
        run = self.runs.get(run_id)
        pc = run.pending.get(call_id) if run else None
        if pc is None:
            raise AgentError(409, "没有等待确认的这次调用（可能已处理、已过期或运行已结束）")
        try:
            with lease(self.vault), write_lock(), pc.lock:
                if decision not in ('allow', 'deny'):
                    raise ValueError('decision 只能是 allow 或 deny')
                if token != pc.token:
                    raise ValueError('确认码与这次调用的参数不匹配')
                if pc.event.is_set() or time.time() >= pc.expires_at:
                    raise ValueError('确认已处理或过期')
                result = ai_review.decide(self.vault, pc.operation_id, pc.revision,
                    'approve' if decision == 'allow' else 'reject', reviewer=reviewer or {'kind': 'web', 'access': 'chat'})
        except ValueError as exc:
            raise AgentError(getattr(exc, 'status', 400), str(exc))
        return {'call_id': call_id, 'decision': decision, 'operation_id': pc.operation_id,
                'revision': pc.revision, 'status': result['status']}

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
        with lease(self.vault), write_lock():
            result = apply_revert(self.vault, run_id)
        if not result["ok"]:
            raise AgentError(409, result.get("msg") or "有冲突，这次运行不能整体撤销", result)
        info = {"at": now_iso(), "commits": result["new_commits"], "reverted": result["reverted"]}
        self.store.set_reverted(run_id, info)
        return {**result, "info": info}
