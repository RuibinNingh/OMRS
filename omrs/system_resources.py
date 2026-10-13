"""宿主机与 cgroup 的有效可用内存；读取失败拒绝无保护运行。"""
from pathlib import Path


def memory_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            available = int(line.split()[1]) * 1024
            # cgroup v2 当前进程及祖先的剩余额度，与宿主机取较小值。
            try:
                relative = next(x.split(':',2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
                base = Path('/sys/fs/cgroup')
                current = base / relative.lstrip('/')
                for folder in [current, *current.parents]:
                    if not folder.is_relative_to(base): break
                    if folder == base and not (folder/'memory.max').exists():
                        continue  # cgroup v2 根层不提供 memory.max，无此层限额。
                    limit = (folder/'memory.max').read_text().strip()
                    used = int((folder/'memory.current').read_text())
                    if limit != 'max': available = min(available, max(0,int(limit)-used))
            except (OSError,ValueError,StopIteration):
                raise RuntimeError('无法读取 cgroup 内存边界，拒绝无保护启动')
            return available
    raise RuntimeError('无法读取可用内存，拒绝无保护启动')
