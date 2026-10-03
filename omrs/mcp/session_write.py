"""外部 MCP 正式复习计划创建适配，不运行内部模型。"""
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from ..mcp_operations import create_session


SCOPES = {'create_review_session': ('omrs:read', 'session:create')}


class ReviewSessionItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: Annotated[str, Field(min_length=1, max_length=200, pattern=r'\S')]
    source: Literal['due', 'proficiency']
    # 推荐中的 UID 是展示快照；创建始终按稳定 question_id 绑定当前位置。
    uid: Annotated[str, Field(max_length=200)] = ''


def register(server, vault, require, threaded, web_url=''):
    def create_review_session(
        items: Annotated[list[ReviewSessionItem], Field(min_length=1, max_length=100)],
        request_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r'\S')],
    ):
        token = require(vault, SCOPES['create_review_session'])
        return create_session(vault, [item.model_dump() for item in items],
                              token.client_id, request_id, web_url,
                              lambda: require(vault, SCOPES['create_review_session']))

    server.add_tool(threaded(create_review_session), name='create_review_session',
                    description='仅在用户要求创建正式复习计划时调用；先返回网页审核链接，确认后才按稳定题目身份创建 1–100 题的 EXP Session。待审核结果没有session_id；request_id用于技术重试。',
                    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False))
