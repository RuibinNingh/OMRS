"""MCP 跨来源草稿补丁；人工保护和状态校验复用内置助手。"""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field
from mcp.types import ToolAnnotations
from ..draft_write import patch_mcp_draft
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'update_draft': ('omrs:read', 'draft:update')}


class BlockPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    block_id: str
    text: str | None = None
    note: str | None = None


def register(server, vault, require, threaded):
    def update_draft(draft_id: Annotated[str, Field(min_length=1, max_length=200)],
                     expected_revision: Annotated[int, Field(ge=1, strict=True)],
                     request_id: Annotated[str, Field(min_length=1, max_length=128)],
                     fields: dict[str, object] = {}, block_patches: Annotated[list[BlockPatch], Field(max_length=40)] = [],
                     cause_statement: str = ''):
        token = require(vault, SCOPES['update_draft'])
        patches = [p.model_dump(exclude_unset=True) for p in block_patches]
        return patch_mcp_draft(vault, draft_id.strip(), expected_revision, fields, patches, token.client_id,
                               request_id, cause_statement, lambda: require(vault, SCOPES['update_draft']))
    server.add_tool(threaded(update_draft), name='update_draft',
                    description=TOOL_DESCRIPTIONS['update_draft'],
                    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
