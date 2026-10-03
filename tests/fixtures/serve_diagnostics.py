"""隔离浏览器实例的服务入口：仅在测试日志记录审核计数的 SQLite 异常。"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from omrs import ai_review
from omrs.cli import main

_counts = ai_review.counts


def diagnostic_counts(*args, **kwargs):
    try:
        return _counts(*args, **kwargs)
    except sqlite3.Error as exc:
        # 不记录请求、提案或凭据；HTTP 仍由原处理器返回固定隐私提示。
        print(f'审核计数 SQLite 诊断：{type(exc).__name__}: {str(exc)[:400]}', file=sys.stderr, flush=True)
        raise


if __name__ == '__main__':
    ai_review.counts = diagnostic_counts
    main()
