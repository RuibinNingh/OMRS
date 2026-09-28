"""当前写入者上下文（contextvars）：用户（默认）或某次 AI 运行。

AI 工具在 ``agent_actor(...)`` 里调用领域函数；其间 ``append_commit`` 把来源 ``api`` 改记为 ``agent``，
payload 加 ``_agent: {conversation_id, run_id, tool_call_id}``（参与哈希，投影忽略），并把产生的 commit
记进上下文，供工具结果与按运行撤销使用。见 AI/ledger.md「写入来源」、AI/agent.md。
"""
import contextlib
import contextvars


class AgentActor:
    def __init__(self, conversation_id: str, run_id: str, tool_call_id: str):
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.tool_call_id = tool_call_id
        self.commits = []

    def stamp(self) -> dict:
        return {"conversation_id": self.conversation_id, "run_id": self.run_id,
                "tool_call_id": self.tool_call_id}


_ACTOR = contextvars.ContextVar("omrs_actor", default=None)


def current_agent():
    return _ACTOR.get()


def note_commit(info: dict) -> None:
    actor = _ACTOR.get()
    if actor is not None:
        actor.commits.append(info)


@contextlib.contextmanager
def agent_actor(conversation_id: str, run_id: str, tool_call_id: str):
    actor = AgentActor(conversation_id, run_id, tool_call_id)
    token = _ACTOR.set(actor)
    try:
        yield actor
    finally:
        _ACTOR.reset(token)


_REVERT = contextvars.ContextVar("omrs_revert", default=None)


def current_revert():
    return _REVERT.get()


@contextlib.contextmanager
def revert_marker(run_id: str, commit_id: str):
    """按运行撤销时的逆操作：append_commit 给 payload 加 _revert: {run_id, commit_id}。"""
    token = _REVERT.set({"run_id": run_id, "commit_id": commit_id})
    try:
        yield
    finally:
        _REVERT.reset(token)
