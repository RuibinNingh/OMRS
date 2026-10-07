"""MCP 正式题目提案；所有写入等待网页审核，模型没有批准入口。"""
from typing import Annotated
from pydantic import Field
from mcp.types import ToolAnnotations

from .. import ai_review
from ..data_repository import storage_write
from ..errors import RequestError
from ..question_update import prepare_update, apply_update, validate_patch
from .common import request_identity
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'propose_question_update': ('omrs:read', 'question:propose')}


@storage_write
def propose(vault, key_id, request_id, uid, question_id, expected_content_hash, patch, web_url='', authorize=None, *, reason):
    clean = validate_patch(patch)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000 or '\x00' in reason:
        raise ValueError('修改理由必须是不含空字符、1 到 2000 字符的文字')
    reason = reason.strip()
    requested = {'uid': uid.strip(), 'question_id': question_id, 'expected_content_hash': expected_content_hash, 'patch': clean, 'reason': reason}
    identity, digest = request_identity(key_id, 'propose_question_update', request_id, requested)
    if authorize:
        authorize()
    previous = ai_review.by_identity(vault, identity)
    if previous:
        if previous['digest'] != digest:
            raise RequestError('request_conflict', '相同 request_id 的题目修改内容不同')
        return {**ai_review.public(previous, web_url), 'reused': True}
    payload, preview, snapshot = prepare_update(vault, **requested)
    if authorize:
        authorize()
    row = ai_review.create(vault, 'mcp', 'propose_question_update', identity, payload,
                           actor={'key_id': key_id, 'request_id': request_id.strip(), 'reason': reason},
                           preview=preview, snapshot=snapshot, pending=True, digest=digest,
                           editable_fields=list(clean))
    if authorize:
        authorize()
    return {**ai_review.public(row, web_url), 'reused': False}


def prepare_review(vault, row, patch):
    if not isinstance(patch, dict) or not set(patch).issubset(row['editable_fields']):
        raise RequestError('forbidden', '不能扩大原提案的编辑字段')
    payload = row['payload']
    return prepare_update(vault, payload['uid'], payload['question_id'], payload['expected_content_hash'],
                          {**payload['patch'], **patch}, reason=payload.get('reason', ''))


def apply_review(vault, row):
    return apply_update(vault, row)


def register(server, vault, require, threaded, web_url):
    def propose_question_update(uid: Annotated[str, Field(min_length=1, max_length=200)],
                                question_id: Annotated[str, Field(min_length=1, max_length=200)],
                                expected_content_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')],
                                patch: dict[str, object],
                                request_id: Annotated[str, Field(min_length=1, max_length=128)],
                                reason: Annotated[str, Field(min_length=1, max_length=2000)]):
        token = require(vault, SCOPES['propose_question_update'])
        return propose(vault, token.client_id, request_id, uid, question_id, expected_content_hash, patch,
                       web_url, lambda: require(vault, SCOPES['propose_question_update']), reason=reason)
    server.add_tool(threaded(propose_question_update), name='propose_question_update',
                    description=TOOL_DESCRIPTIONS['propose_question_update'],
                    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
