"""展示板局部管理工具与本人确认状态查询；没有模型确认入口。"""
from typing import Annotated
from pydantic import Field
from mcp.types import ToolAnnotations
from .. import mcp_board, mcp_operations

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

    descriptions = {
        'create_board': '新建展示板，可加入最多100道题；必须携带目录版本和请求编号。',
        'update_board': '局部修改板名、备注或 source_labels；改名另需目录版本。',
        'duplicate_board': '复制板内引用和版式，纸面记录不复制。',
        'delete_board': '申请删除展示板，返回网页确认链接，未确认前不修改。',
        'add_board_items': '批量加题，完整校验后写入；已在板中的题跳过，返回实际变更。',
        'remove_board_items': '仅移除板内引用，清空非空板需网页确认；题目本身保留。',
        'reorder_board_items': '提交所有板内稳定 question_id 或当前 UID 的完整排列。',
        'update_board_layout': '局部修改 print 版式，非法值拒绝；实际重置纸面记录需网页确认。',
        'update_board_item': '仅修改单题 gap_lines（0..48/null继承）及 pin；重置纸面记录需网页确认。',
        'create_board_folder': '新建展示板文件夹。',
        'update_board_folder': '局部修改文件夹 name 或 order。',
        'delete_board_folder': '申请删除文件夹，默认保留板移到未归档；必须网页确认。',
        'move_board': '将板移入文件夹（空串为未归档）或调整组内位置；检查板和目录版本。',
        'get_mcp_operation': '读取本密钥发起的确认操作，查询待确认、应用、拒绝、到期和冲突；不能确认。',
    }
    for fn in (create_board, update_board, duplicate_board, delete_board, add_board_items, remove_board_items,
               reorder_board_items, update_board_layout, update_board_item, create_board_folder,
               update_board_folder, delete_board_folder, move_board, get_mcp_operation):
        server.add_tool(threaded(fn), name=fn.__name__, description=descriptions[fn.__name__],
                        annotations=ToolAnnotations(readOnlyHint=fn is get_mcp_operation,
                            destructiveHint=fn.__name__ in mcp_board.DELETE_TOOLS, idempotentHint=True, openWorldHint=False))
