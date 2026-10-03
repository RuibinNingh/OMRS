"""外部 MCP 正式复习计划创建适配，不运行内部模型。"""
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from ..session_operations import create_mcp_session


SCOPES = {'create_review_session': ('omrs:read', 'session:create')}


class ReviewSessionItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: Annotated[str, Field(min_length=1, max_length=200, pattern=r'\S')]
    source: Literal['due', 'proficiency']
    # 推荐中的 UID 是展示快照；创建始终按稳定 question_id 绑定当前位置。
    uid: Annotated[str, Field(max_length=200)] = ''


def register(server, vault, require, threaded):
    def create_review_session(
        items: Annotated[list[ReviewSessionItem], Field(min_length=1, max_length=100)],
        request_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r'\S')],
    ):
        token = require(vault, SCOPES['create_review_session'])
        return create_mcp_session(vault, [item.model_dump() for item in items],
                                  token.client_id, request_id,
                                  lambda: require(vault, SCOPES['create_review_session']))

    server.add_tool(threaded(create_review_session), name='create_review_session',
                    description='仅在用户要求创建正式复习计划时调用；按推荐 selection 的稳定题目身份创建 1–100 题的 EXP Session，单题也持久化。request_id 用于技术重试。',
                    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False))
