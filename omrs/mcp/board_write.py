"""展示板局部管理工具与本人确认状态查询；没有模型确认入口。"""
from typing import Annotated
from pydantic import Field
from mcp.types import ToolAnnotations
from .. import mcp_board, mcp_operations
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {**mcp_board.SCOPES, 'get_mcp_operation': 'omrs:read'}
Text = Annotated[str, Field(min_length=1, max_length=200)]
RequestID = Annotated[str, Field(min_length=1, max_length=128)]
Revision = Annotated[int, Field(ge=1, strict=True)]
CatalogRevision = Annotated[int, Field(ge=0, strict=True)]
UIDs = Annotated[list[Text], Field(max_length=100)]
Refs = Annotated[list[Text], Field(max_length=10000)]


def register(server, vault, require, threaded, web_url):
    def run(tool, request_id, payload):
        token = require(vault, SCOPES[tool])
        return mcp_board.execute(vault, token.client_id, tool, request_id, payload, web_url)

    def create_board(name: Annotated[str, Field(min_length=1, max_length=120)],
                     expected_catalog_revision: CatalogRevision, request_id: RequestID,
                     uids: UIDs = [], folder_id: str = ''):
        return run('create_board', request_id, dict(name=name, expected_catalog_revision=expected_catalog_revision,
                                                   uids=uids, folder_id=folder_id))

    def update_board(board_id: Text, expected_revision: Revision, request_id: RequestID, patch: dict[str, object],
                     expected_catalog_revision: CatalogRevision | None = None):
        return run('update_board', request_id, dict(board_id=board_id, expected_revision=expected_revision,
                                                   patch=patch, expected_catalog_revision=expected_catalog_revision))

    def duplicate_board(board_id: Text, name: Annotated[str, Field(min_length=1, max_length=120)],
                        expected_revision: Revision, expected_catalog_revision: CatalogRevision, request_id: RequestID):
        return run('duplicate_board', request_id, dict(board_id=board_id, name=name, expected_revision=expected_revision,
                                                      expected_catalog_revision=expected_catalog_revision))

    def delete_board(board_id: Text, expected_revision: Revision, expected_catalog_revision: CatalogRevision,
                     request_id: RequestID):
        return run('delete_board', request_id, dict(board_id=board_id, expected_revision=expected_revision,
                                                   expected_catalog_revision=expected_catalog_revision))

    def add_board_items(board_id: Text, uids: UIDs, expected_revision: Revision, request_id: RequestID,
                        position: Annotated[int, Field(ge=0, strict=True)] | None = None):
        return run('add_board_items', request_id, dict(board_id=board_id, uids=uids, expected_revision=expected_revision,
                                                      position=position))

    def remove_board_items(board_id: Text, item_refs: Refs, expected_revision: Revision, request_id: RequestID):
        return run('remove_board_items', request_id, dict(board_id=board_id, item_refs=item_refs,
                                                         expected_revision=expected_revision))

    def reorder_board_items(board_id: Text, item_refs: Refs, expected_revision: Revision, request_id: RequestID):
        return run('reorder_board_items', request_id, dict(board_id=board_id, item_refs=item_refs,
                                                          expected_revision=expected_revision))

    def update_board_layout(board_id: Text, patch: dict[str, object], expected_revision: Revision, request_id: RequestID):
        return run('update_board_layout', request_id, dict(board_id=board_id, patch=patch, expected_revision=expected_revision))

    def update_board_item(board_id: Text, item_ref: Text, patch: dict[str, object], expected_revision: Revision,
                          request_id: RequestID):
        return run('update_board_item', request_id, dict(board_id=board_id, item_ref=item_ref, patch=patch,
                                                        expected_revision=expected_revision))

    def create_board_folder(name: Annotated[str, Field(min_length=1, max_length=60)],
                            expected_catalog_revision: CatalogRevision, request_id: RequestID):
        return run('create_board_folder', request_id, dict(name=name, expected_catalog_revision=expected_catalog_revision))

    def update_board_folder(folder_id: Text, patch: dict[str, object], expected_catalog_revision: CatalogRevision,
                            request_id: RequestID):
        return run('update_board_folder', request_id, dict(folder_id=folder_id, patch=patch,
                                                          expected_catalog_revision=expected_catalog_revision))

    def delete_board_folder(folder_id: Text, expected_catalog_revision: CatalogRevision, request_id: RequestID,
                            keep_boards: Annotated[bool, Field(strict=True)] = True):
        return run('delete_board_folder', request_id, dict(folder_id=folder_id, keep_boards=keep_boards,
                                                          expected_catalog_revision=expected_catalog_revision))

    def move_board(board_id: Text, folder_id: str, expected_revision: Revision, expected_catalog_revision: CatalogRevision,
                   request_id: RequestID, index: Annotated[int, Field(ge=0, strict=True)] | None = None):
        return run('move_board', request_id, dict(board_id=board_id, folder_id=folder_id, expected_revision=expected_revision,
                                                 expected_catalog_revision=expected_catalog_revision, index=index))

    def get_mcp_operation(operation_id: Text):
        token = require(vault, 'omrs:read')
        result = mcp_operations.get(vault, operation_id, token.client_id, web_url)
        require(vault, 'omrs:read')
        return result

    for fn in (create_board, update_board, duplicate_board, delete_board, add_board_items, remove_board_items,
               reorder_board_items, update_board_layout, update_board_item, create_board_folder,
               update_board_folder, delete_board_folder, move_board, get_mcp_operation):
        server.add_tool(threaded(fn), name=fn.__name__, description=TOOL_DESCRIPTIONS[fn.__name__],
                        annotations=ToolAnnotations(readOnlyHint=fn is get_mcp_operation,
                            destructiveHint=fn.__name__ in mcp_board.DELETE_TOOLS, idempotentHint=True, openWorldHint=False))
