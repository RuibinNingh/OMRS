"""展示板导出只返回受 Web 登录保护的快照下载地址。"""
from typing import Annotated, Literal
from pydantic import Field
from mcp.types import ToolAnnotations
from .. import mcp_exports
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'export_board': 'omrs:read'}


def register(server, vault, require, threaded, web_url):
    def export_board(board_id: Annotated[str, Field(min_length=1, max_length=200)],
                     request_id: Annotated[str, Field(min_length=1, max_length=128)],
                     mode: Literal['all', 'new'] = 'all',
                     expected_revision: Annotated[int, Field(ge=1, strict=True)] | None = None):
        token = require(vault, 'omrs:read')
        return mcp_exports.create(vault, board_id, mode, request_id, token.client_id, web_url,
                                  lambda: require(vault, 'omrs:read'), expected_revision)
    server.add_tool(threaded(export_board), name='export_board',
        description=TOOL_DESCRIPTIONS['export_board'],
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
