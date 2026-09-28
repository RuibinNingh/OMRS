"""服务端权限：级别、确认令牌、预算。规则写死在这里，不写在提示词里。

- read：自动执行；rev（可撤销）：自动执行，计入写入预算；confirm：发确认事件，只认界面按钮发来的
  POST /api/agent/confirm；不注册的能力（删除、设置、PIN、备份恢复、重启、源码导出……）根本没有工具。
- 确认令牌 = sha256(run_id + 工具名 + 规范化参数)，参数一变就是新请求；令牌 10 分钟过期。
"""
import hashlib
import json
import threading
import time

LEVELS = ("read", "rev", "confirm")


def canonical_args(args) -> str:
    return json.dumps(args or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def confirm_token(run_id: str, name: str, args) -> str:
    return hashlib.sha256(f"{run_id}\n{name}\n{canonical_args(args)}".encode("utf-8")).hexdigest()


class PendingConfirm:
    def __init__(self, run_id, call_id, name, args, ttl):
        self.run_id, self.call_id, self.name, self.args = run_id, call_id, name, args
        self.token = confirm_token(run_id, name, args)
        self.expires_at = time.time() + ttl
        self.decision = None
        self.decided_at = None
        self.event = threading.Event()

    def decide(self, token: str, decision: str) -> None:
        if decision not in ("allow", "deny"):
            raise ValueError("decision 只能是 allow 或 deny")
        if token != self.token:
            raise ValueError("确认码与这次调用的参数不匹配")
        if self.event.is_set():
            raise ValueError("这次调用已经处理过")
        if time.time() > self.expires_at:
            raise ValueError("确认已过期")
        self.decision, self.decided_at = decision, time.time()
        self.event.set()

    def wait(self, abort: threading.Event) -> str:
        """阻塞到用户点击、过期或运行中止。返回 allow / deny / expire / abort。"""
        while True:
            left = self.expires_at - time.time()
            if left <= 0:
                self.decision = self.decision or "expire"
                self.event.set()
                return self.decision
            if self.event.wait(min(0.25, left)):
                return self.decision
            if abort.is_set():
                self.decision = "abort"
                self.event.set()
                return "abort"


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.rounds = self.calls = self.writes = 0

    def snapshot(self):
        return {"rounds": self.rounds, "calls": self.calls, "writes": self.writes,
                "max_rounds": self.limits["rounds"], "max_calls": self.limits["calls"], "max_writes": self.limits["writes"]}
