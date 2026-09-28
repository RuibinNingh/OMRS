"""/api/agent/* 接口。沿用现有认证（未登录请求在 server.py 的 _authorize 就被拒）；写锁规则见 AI/api.md。"""
import json

from ..locking import WriteLockTimeout
from .runtime import AgentError, get_runtime


def _body(handler):
    raw = handler.rfile.read(int(handler.headers.get("Content-Length", 0)) or 0)
    data = json.loads(raw or b"{}")
    if not isinstance(data, dict):
        raise AgentError(400, "请求体必须是 JSON 对象")
    return data


def _reply(handler, fn):
    try:
        handler._json({"status": "ok", **fn()})
    except AgentError as exc:
        handler._json({"status": "error", "msg": exc.msg, **exc.data}, exc.status)
    except WriteLockTimeout:
        handler._json({"status": "error", "msg": "写入繁忙，请稍后重试"}, 503)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        handler._json({"status": "error", "msg": str(exc)}, 400)


def handle_agent_get(handler, path, params):
    rt = get_runtime(handler.vault_path)
    routes = {
        "/api/agent/status": lambda: rt.status(),
        "/api/agent/conversations": lambda: {"conversations": rt.list_conversations()},
        "/api/agent/conversation": lambda: rt.conversation(params.get("id", "")),
        "/api/agent/events": lambda: rt.events(params.get("run", ""), int(params.get("after", 0) or 0),
                                               float(params.get("wait", 0) or 0)),
    }
    fn = routes.get(path)
    if fn is None:
        handler._json({"status": "error", "msg": "not found"}, 404)
        return
    _reply(handler, fn)


def handle_agent_post(handler, path):
    rt = get_runtime(handler.vault_path)
    _reply(handler, lambda: agent_post_routes(rt, path, _body(handler)))


def agent_post_routes(rt, path, data):
    if path == "/api/agent/conversation/create":
        return {"conversation": rt.create_conversation(data.get("title", ""))}
    if path == "/api/agent/conversation/delete":
        return rt.delete_conversation(data.get("id", ""))
    if path == "/api/agent/message":
        return rt.post_message(data.get("conversation_id", ""), data.get("text", ""), data.get("images"))
    if path == "/api/agent/confirm":
        return rt.confirm(data.get("run_id", ""), data.get("call_id", ""), data.get("token", ""), data.get("decision", ""))
    if path == "/api/agent/abort":
        return rt.abort(data.get("run_id", ""))
    if path == "/api/agent/test":
        return rt.test_connection()
    if path == "/api/agent/run/revert":
        return rt.revert(data.get("run_id", ""), dry_run=data.get("dry_run", True) is not False)
    raise AgentError(404, "not found")
