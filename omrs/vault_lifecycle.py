"""Vault 磁盘生命周期：跨线程/进程租约、恢复世代与有界连接。

锁顺序：租约 → 领域写锁 → 模块锁 → SQLite/文件。网络与长轮询不持租约。
维护文件在 Vault 根目录，不能随错题目录交换；正常访问共享，捕获/交换独占。
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import json
import os
import sqlite3
import sys
import threading
import time
import uuid

_STATES = {}
_STATES_LOCK = threading.Lock()
_LOCAL = threading.local()
_EXPECTED = contextvars.ContextVar("vault_task_generation", default={})


class VaultBusy(RuntimeError):
    code = "vault_busy"
    status = 503


class VaultChanged(RuntimeError):
    code = "vault_changed"
    status = 409


def maintenance_dir(vault):
    path = os.path.join(os.path.realpath(vault), ".omrs-maintenance")
    os.makedirs(path, mode=0o700, exist_ok=True)
    if os.path.islink(path):
        raise ValueError("Vault 维护目录不能是符号链接")
    return path


def fsync_dir(path):
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    tmp = path + "." + uuid.uuid4().hex + ".tmp"
    try:
        with open(tmp, "x", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        fsync_dir(os.path.dirname(path))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def generation(vault):
    path = os.path.join(maintenance_dir(vault), "generation.json")
    try:
        with open(path, encoding="utf-8") as file:
            value = json.load(file)
        result = value["generation"]
        if type(result) is not int or result < 0:
            raise ValueError("Vault 世代文件不合法")
        return result
    except FileNotFoundError:
        return 0


def advance_generation(vault):
    value = generation(vault) + 1
    atomic_json(os.path.join(maintenance_dir(vault), "generation.json"), {"generation": value})
    return value


class _State:
    def __init__(self):
        self.cond = threading.Condition(threading.RLock())
        self.readers = {}
        self.writer = None
        self.waiting = 0


def _state(key):
    with _STATES_LOCK:
        return _STATES.setdefault(key, _State())


def _os_lock(file, exclusive, deadline):
    if os.name != "nt":
        import fcntl
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        while True:
            try:
                fcntl.flock(file.fileno(), mode | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise VaultBusy("Vault 正在维护，获取磁盘租约超时")
                time.sleep(0.02)
    else:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                        ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                        ("hEvent", wintypes.HANDLE)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        overlap = Overlapped()
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(file.fileno()))
        flags = 1 | (2 if exclusive else 0)
        while not kernel.LockFileEx(handle, flags, 0, 1, 0, ctypes.byref(overlap)):
            if ctypes.get_last_error() not in (33, 158):
                raise ctypes.WinError(ctypes.get_last_error())
            if time.monotonic() >= deadline:
                raise VaultBusy("Vault 正在维护，获取磁盘租约超时")
            time.sleep(0.02)


def _verify(key, expected):
    current = generation(key)
    required = expected if expected is not None else _EXPECTED.get().get(key)
    if required is not None and required != current:
        raise VaultChanged("题库已恢复，旧任务结果未写入，请刷新后重试")
    return current


@contextlib.contextmanager
def _access(vault, exclusive_mode=False, expected_generation=None, timeout=60):
    key, tid = os.path.realpath(vault), threading.get_ident()
    held = getattr(_LOCAL, "held", None)
    if held is None:
        held = _LOCAL.held = {}
    entry = held.get(key)
    if entry is not None:
        if exclusive_mode and not entry["exclusive"]:
            raise VaultBusy("维护必须在释放普通租约后开始，禁止共享锁升级")
        _verify(key, expected_generation)
        entry["refs"] += 1
    else:
        state, deadline = _state(key), time.monotonic() + timeout
        with state.cond:
            if exclusive_mode:
                state.waiting += 1
            try:
                while state.writer is not None or (bool(state.readers) if exclusive_mode else state.waiting > 0):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise VaultBusy("Vault 正在维护，获取磁盘租约超时")
                    state.cond.wait(remaining)
                if exclusive_mode:
                    state.writer = tid
                else:
                    state.readers[tid] = 1
            finally:
                if exclusive_mode:
                    state.waiting -= 1
                state.cond.notify_all()
        file = None
        try:
            file = open(os.path.join(maintenance_dir(key), "storage.lock"), "a+b")
            _os_lock(file, exclusive_mode, deadline)
            entry = {"file": file, "exclusive": exclusive_mode, "refs": 1, "state": state}
            held[key] = entry
        except BaseException:
            if file:
                file.close()
            with state.cond:
                if exclusive_mode:
                    state.writer = None
                else:
                    state.readers.pop(tid, None)
                state.cond.notify_all()
            raise
    try:
        yield _verify(key, expected_generation)
    finally:
        entry["refs"] -= 1
        if entry["refs"] == 0:
            held.pop(key, None)
            entry["file"].close()
            state = entry["state"]
            with state.cond:
                if entry["exclusive"]:
                    state.writer = None
                else:
                    state.readers.pop(tid, None)
                state.cond.notify_all()


@contextlib.contextmanager
def lease(vault, expected_generation=None, timeout=60):
    with _access(vault, expected_generation=expected_generation, timeout=timeout) as value:
        yield value


@contextlib.contextmanager
def exclusive(vault, timeout=60):
    with _access(vault, exclusive_mode=True, timeout=timeout) as value:
        yield value


@contextlib.contextmanager
def task(vault, expected_generation=None):
    key = os.path.realpath(vault)
    with lease(key, expected_generation) as value:
        token = _EXPECTED.set({**_EXPECTED.get(), key: value})
    try:
        yield value
    finally:
        _EXPECTED.reset(token)


@contextlib.contextmanager
def maintenance_task(vault):
    key = os.path.realpath(vault)
    entry = getattr(_LOCAL, "held", {}).get(key)
    if not entry or not entry["exclusive"]:
        raise VaultBusy("只有独占维护可以更新任务世代")
    token = _EXPECTED.set({**_EXPECTED.get(), key: generation(key)})
    try:
        yield
    finally:
        _EXPECTED.reset(token)


def storage(fn):
    """仅包磁盘函数；后台计算使用 task 传递世代而不持磁盘锁。"""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        first = args[0] if args else kwargs.get("vault")
        vault = first if isinstance(first, (str, os.PathLike)) else getattr(first, "vault", None)
        if vault is None and len(args) > 1:
            vault = args[1]
        if vault is None:
            raise TypeError("存储函数缺少 Vault")
        with lease(vault):
            return fn(*args, **kwargs)
    return wrapped


class _Connection(sqlite3.Connection):
    def close(self):
        try:
            super().close()
        finally:
            manager = getattr(self, "_lease", None)
            self._lease = None
            if manager:
                manager.__exit__(None, None, None)

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def open_sqlite(vault, path, **kwargs):
    manager = lease(vault)
    manager.__enter__()
    try:
        db = sqlite3.connect(path, factory=_Connection, **kwargs)
        db._lease = manager
        return db
    except BaseException:
        manager.__exit__(None, None, None)
        raise


@contextlib.contextmanager
def transaction(db):
    """已打开连接的短事务；外层存储操作仍负责关闭连接和租约。"""
    sqlite3.Connection.__enter__(db)
    try:
        yield db
    except BaseException:
        sqlite3.Connection.__exit__(db, *sys.exc_info())
        raise
    else:
        sqlite3.Connection.__exit__(db, None, None, None)
