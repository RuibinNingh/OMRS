"""MCP 长任务在恢复后拒绝返回旧结果，不把运行回执写进新世代。"""
import asyncio
import tempfile
import unittest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError
from omrs.mcp.server import RestrictedMCP
from omrs import runtime_records, vault_lifecycle


class MCPLifecycleTests(unittest.TestCase):
    def test_restore_during_tool_returns_stable_error_and_skips_old_receipt(self):
        with tempfile.TemporaryDirectory() as vault:
            server = RestrictedMCP("lifecycle-test", vault=vault)
            async def restore_during_tool(name, arguments):
                with vault_lifecycle.exclusive(vault):
                    vault_lifecycle.advance_generation(vault)
                return "旧结果"
            with patch.object(server, "_execute_tool", side_effect=restore_during_tool), patch.object(runtime_records, "finish", side_effect=vault_lifecycle.VaultChanged("旧任务")) as finish:
                with self.assertRaisesRegex(ToolError, "^vault_changed:"):
                    asyncio.run(server.call_tool("get_status", {}))
                finish.assert_called_once()

    def test_old_receipt_failure_keeps_original_tool_error(self):
        with tempfile.TemporaryDirectory() as vault:
            server = RestrictedMCP("lifecycle-test", vault=vault)
            with patch.object(server, "_execute_tool", side_effect=ToolError("invalid_request: 原始错误")), patch.object(runtime_records, "finish", side_effect=vault_lifecycle.VaultChanged("旧任务")):
                with self.assertRaisesRegex(ToolError, "^invalid_request: 原始错误"):
                    asyncio.run(server.call_tool("get_status", {}))


if __name__ == "__main__":
    unittest.main()
