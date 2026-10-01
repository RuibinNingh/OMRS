"""OMRS 的受限 MCP 接入。

MCP 适配层只负责协议、密钥和输入适配；题库查询与草稿存储仍由 OMRS
现有领域模块完成。生产环境应使用 ``omrs_engine.py serve --mcp-port``，
让 MCP 与 Web 服务共享主进程写锁，不要为同一 Vault 另起直接写入进程。
"""

from .keys import create_key, list_keys, revoke_key, verify_key

__all__ = ["create_key", "list_keys", "revoke_key", "verify_key"]
