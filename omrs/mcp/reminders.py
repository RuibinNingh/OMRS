"""外部AI只能新增提醒素材；默认选择和删除留给网页用户。"""
from typing import Annotated
import hashlib
from pydantic import Field
from mcp.types import ToolAnnotations
from .. import schedule_reminders
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'list_schedule_reminders': 'omrs:read', 'create_schedule_reminder': 'reminder:create'}
PREPARE_TOOLS = {'create_schedule_reminder'}


def register(server, vault, require, threaded):
    def list_schedule_reminders():
        require(vault, 'omrs:read')
        return schedule_reminders.catalog(vault)

    def create_schedule_reminder(name: Annotated[str, Field(min_length=1, max_length=80)],
                                 svg: Annotated[str, Field(min_length=1, max_length=262144)],
                                 request_id: Annotated[str, Field(min_length=1, max_length=200)]):
        token = require(vault, 'reminder:create')
        receipt = 'mcp:' + token.client_id + ':' + hashlib.sha256(request_id.encode()).hexdigest()
        result = schedule_reminders.create(vault, name, svg, receipt, source='MCP 创建',
            authorize=lambda: require(vault, 'reminder:create'))
        require(vault, 'reminder:create')
        return {**result, 'item': {k: v for k, v in result['item'].items() if k != 'src'},
                'web_hint': '已加入提醒素材库；请在复习调度中预览并选择使用，不会自动启用。'}

    for fn in (list_schedule_reminders, create_schedule_reminder):
        server.add_tool(threaded(fn), name=fn.__name__, description=TOOL_DESCRIPTIONS[fn.__name__],
            annotations=ToolAnnotations(readOnlyHint=fn is list_schedule_reminders,
                destructiveHint=False, idempotentHint=True, openWorldHint=False))
