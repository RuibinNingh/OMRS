"""进程级写锁：所有持久化写入经这把可重入锁串行。

锁顺序（写死）：写锁在外，模块锁（security._LOCK、inbox._LOCK、optimization._LOCK、
workspace_sync._SCAN_LOCK、agent.store 的连接锁）在内。持有任何模块锁时不得再取写锁。
取锁超时抛 WriteLockTimeout，HTTP 层返回 503「写入繁忙，请稍后重试」。
POST 默认在锁内处理；豁免清单与理由见 AI/api.md「并发与写锁」。
"""
import contextlib
import threading
import time


class WriteLockTimeout(RuntimeError):
    pass


_LOCK = threading.RLock()
_OWNER = threading.local()
DEFAULT_TIMEOUT = 60.0

# 经逐条读代码确认不写持久状态（或只写自带锁的独立存储）的 POST
POST_LOCK_EXEMPT = {
    "/api/auth/login": "只写内存会话（security._LOCK）",
    "/api/ai-recognize": "只调用外部模型，不写 Vault",
    "/api/restart": "本身不写；重启线程在 shutdown 前取写锁，等进行中的写入完成",
    "/api/agent/message": "只写 agent.db（自带连接锁）；工具写入在运行线程里逐次取写锁",
    "/api/agent/confirm": "只改内存中的确认状态",
    "/api/agent/abort": "只改内存中的运行状态",
    "/api/agent/test": "只向模型发一次测试请求，不写任何状态",
    "/api/agent/conversation/create": "只写 agent.db",
    "/api/agent/conversation/delete": "只写 agent.db",
}
POST_LOCK_EXEMPT_PREFIXES = ("/api/auth/",)


def post_exempt(path: str) -> bool:
    return path in POST_LOCK_EXEMPT or path.startswith(POST_LOCK_EXEMPT_PREFIXES)


def held_by_current_thread() -> bool:
    return getattr(_OWNER, "depth", 0) > 0


@contextlib.contextmanager
def write_lock(timeout: float = None):
    wait = DEFAULT_TIMEOUT if timeout is None else timeout
    started = time.monotonic()
    if not _LOCK.acquire(timeout=wait):
        raise WriteLockTimeout(f"写入繁忙（等待写锁 {time.monotonic() - started:.1f} 秒）")
    _OWNER.depth = getattr(_OWNER, "depth", 0) + 1
    try:
        yield
    finally:
        _OWNER.depth -= 1
        _LOCK.release()


def acquire_for_shutdown(timeout: float = 30.0) -> bool:
    """重启前调用：等进行中的写入完成（最多 timeout 秒）。取到后不释放，进程随后退出。"""
    return _LOCK.acquire(timeout=timeout)
