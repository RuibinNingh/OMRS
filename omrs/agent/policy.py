"""服务端权限：级别、确认令牌、预算。规则写死在这里，不写在提示词里。

- read 自动执行；rev 自动执行并记录业务动作；confirm 由聊天或审核中心的人类决定共用同一持久权威。
  不注册的能力（删除、设置、PIN、备份恢复、重启、源码导出……）根本没有工具。
- 确认令牌绑定原运行、工具、operation_id、revision 和有效内容摘要；10 分钟到期，不因修订延长。
"""
import hashlib
import json
import threading
import time

LEVELS = ("read", "prepare", "rev", "confirm")


def canonical_args(args) -> str:
    return json.dumps(args or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def confirm_token(run_id: str, name: str, args, operation_id="", revision=1, effective_digest="") -> str:
    binding = (f"{operation_id}\n{revision}\n{effective_digest}" if operation_id else canonical_args(args))
    return hashlib.sha256(f"{run_id}\n{name}\n{binding}".encode("utf-8")).hexdigest()


class PendingConfirm:
    def __init__(self, run_id, call_id, name, args, ttl, *, operation_id="", revision=1, effective_digest=""):
        self.run_id, self.call_id, self.name, self.args = run_id, call_id, name, args
        self.operation_id, self.revision, self.effective_digest = operation_id, revision, effective_digest
        self.token = confirm_token(run_id, name, args, operation_id, revision, effective_digest)
        self.expires_at = time.time() + ttl
        self.decision = None
        self.decided_at = None
        self.event = threading.Event()
        self.lock = threading.RLock()

    def decide(self, token: str, decision: str, persist=None) -> None:
        with self.lock:
            if decision not in ("allow", "deny"):
                raise ValueError("decision 只能是 allow 或 deny")
            if token != self.token:
                raise ValueError("确认码与这次调用的参数不匹配")
            if self.event.is_set():
                raise ValueError("这次调用已经处理过")
            if time.time() >= self.expires_at:
                raise ValueError("确认已过期")
            if persist:
                persist()
            self.decision, self.decided_at = decision, time.time()
            self.event.set()

    def revise(self, revision, effective_digest):
        """换确认票据但保留原截止时间；不得使旧聊天卡批准人工修订版本。"""
        with self.lock:
            if self.event.is_set() or time.time() >= self.expires_at:
                raise ValueError("确认已处理或过期")
            self.revision, self.effective_digest = revision, effective_digest
            self.token = confirm_token(self.run_id, self.name, self.args,
                                       self.operation_id, revision, effective_digest)

    def close(self, reason):
        with self.lock:
            if not self.event.is_set():
                self.decision, self.decided_at = reason, time.time()
                self.event.set()
            return self.decision or "abort"

    def wait(self, abort: threading.Event) -> str:
        """阻塞到用户点击、过期或运行中止。返回 allow / deny / expire / abort。"""
        while True:
            left = self.expires_at - time.time()
            if left <= 0:
                return self.close("expire")
            if self.event.wait(min(0.25, left)):
                return self.decision or "abort"
            if abort.is_set():
                return self.close("abort")


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.rounds = self.calls = self.writes = 0

    def snapshot(self):
        return {"rounds": self.rounds, "calls": self.calls, "writes": self.writes,
                "max_rounds": self.limits["rounds"], "max_calls": self.limits["calls"], "max_writes": self.limits["writes"]}
