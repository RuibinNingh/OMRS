"""展示板版本化分页读取。"""
from typing import Annotated
from pydantic import Field
from mcp.types import ToolAnnotations
from .. import boards, locking
from .common import RequestError, page
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'list_boards': 'omrs:read', 'get_board': 'omrs:read'}


def register(server, vault, require, threaded):
    def list_boards(offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=100)] = 50):
        require(vault, 'omrs:read')
        data = boards.catalog(vault)
        return {**page(data['boards'], offset, limit), 'folders': data['folders'], 'catalog_revision': data['catalog_revision']}
    def get_board(board_id: Annotated[str, Field(min_length=1, max_length=200)],
                  offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=100)] = 50):
        require(vault, 'omrs:read')
        with locking.write_lock():
            board = boards.get_board(vault, board_id)
            if not board:
                raise RequestError('not_found', '展示板不存在')
            return {**{k: board[k] for k in ('id', 'name', 'note', 'folder_id', 'order', 'revision', 'catalog_revision',
                                            'print', 'printed_summary', 'source_labels', 'created_at', 'updated_at')},
                    **page(board['items'], offset, limit)}
    for fn in (list_boards, get_board):
        server.add_tool(threaded(fn), name=fn.__name__, description=TOOL_DESCRIPTIONS[fn.__name__],
                        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
