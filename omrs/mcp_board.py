"""MCP 展示板领域入口：严格局部操作、原子回执与真实纸面影响预览。"""
import copy
import math

from . import boards, locking
from .mcp.common import RequestError, fingerprint, request_identity
from .mcp.keys import active_key

WRITE_TOOLS = ('create_board', 'update_board', 'duplicate_board', 'add_board_items', 'remove_board_items',
               'reorder_board_items', 'update_board_layout', 'update_board_item', 'create_board_folder',
               'update_board_folder', 'move_board')
DELETE_TOOLS = ('delete_board', 'delete_board_folder')
SCOPES = {tool: ('omrs:read', 'board:write') for tool in WRITE_TOOLS}
SCOPES.update({tool: ('omrs:read', 'board:delete') for tool in DELETE_TOOLS})


def authorize(vault, key_id, tool):
    row = active_key(vault, key_id)
    if not row or not set(SCOPES.get(tool, ('omrs:read',))).issubset(row['scopes']):
        raise PermissionError('MCP 密钥已失效或缺少权限')


def _text(value, field, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f'{field} 必须为{maximum}字以内的有效文字')
    return value if empty else value.strip()


def _integer(value, field, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{field} 必须为 {low} 到 {high} 的整数')
    return value


def _patch(value, allowed):
    if not isinstance(value, dict) or not value or set(value) - set(allowed):
        raise ValueError('补丁为空或包含不允许的字段')
    return value


def _folder(data, folder_id):
    _text(folder_id, 'folder_id', 200, True)
    if folder_id and not any(f['id'] == folder_id for f in data['folders']):
        raise RequestError('not_found', '文件夹不存在')


def _uids(vault, value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('uids 必须是最多100项的列表')
    resolver = boards._Resolver(vault)
    result = []
    for uid in value:
        uid = _text(uid, 'uid', 200)
        if uid not in resolver.by_uid:
            raise RequestError('not_found', f'题目不存在：{uid}')
        if uid not in result:
            result.append(uid)
    return result


def _refs(board, refs):
    if not isinstance(refs, list) or len(refs) > 10000:
        raise ValueError('item_refs 必须为题目引用列表')
    result = []
    for ref in refs:
        ref = _text(ref, 'item_ref', 200)
        matches = [i for i in board['items'] if ref in (i['question_id'], i['uid'])]
        if len(matches) != 1:
            raise RequestError('not_found', '板内引用不存在或不唯一')
        if matches[0] in result:
            raise ValueError('item_refs 不能重复引用同一条目')
        result.append(matches[0])
    return result


def dispatch(vault, tool, payload):
    """校验完整请求后才进入现有领域函数；只在领域暂存事务内调用。"""
    p = copy.deepcopy(payload)
    data = boards.load_boards(vault)
    is_folder = tool in ('create_board_folder', 'update_board_folder', 'delete_board_folder')
    existing = tool not in ('create_board', 'create_board_folder') and not is_folder
    directory = tool in ('create_board', 'duplicate_board', 'delete_board', 'move_board') or is_folder
    if tool == 'update_board' and 'name' in p.get('patch', {}):
        directory = True
    if directory:
        _integer(p.get('expected_catalog_revision'), 'expected_catalog_revision', 0, 2**53-1)
    board = None
    if existing:
        _text(p.get('board_id'), 'board_id', 200)
        board = next((b for b in data['boards'] if b['id'] == p['board_id']), None)
        if not board:
            raise RequestError('not_found', '展示板不存在')
        _integer(p.get('expected_revision'), 'expected_revision', 1, 2**53-1)
    boards.check_versions(data, p.get('board_id'), p.get('expected_revision'),
                          p.get('expected_catalog_revision') if directory else None)
    changed = {}
    if tool == 'create_board_folder':
        result = {'folder': boards.create_folder(vault, _text(p['name'], 'name', 60))}
    elif tool in ('update_board_folder', 'delete_board_folder'):
        folder_id = _text(p['folder_id'], 'folder_id', 200)
        _folder(data, folder_id)
        if tool == 'delete_board_folder':
            if type(p['keep_boards']) is not bool:
                raise ValueError('keep_boards 必须是布尔值')
            result = boards.delete_folder(vault, folder_id, p['keep_boards'])
        else:
            patch = _patch(p['patch'], ('name', 'order'))
            if 'name' in patch:
                patch['name'] = _text(patch['name'], 'name', 60)
            if 'order' in patch:
                _integer(patch['order'], 'order', 0, len(data['folders'])-1)
            result = {'folder': boards.update_folder(vault, folder_id, **patch)}
    elif tool == 'create_board':
        _folder(data, p['folder_id'])
        uids = _uids(vault, p['uids'])
        board = boards.create_board(vault, _text(p['name'], 'name', 120), uids, folder_id=p['folder_id'])
        changed = {'added_uids': [i['uid'] for i in board['items']]}
        result = {}
    elif tool == 'duplicate_board':
        board = boards.duplicate_board(vault, board['id'], _text(p['name'], 'name', 120))
        result = {}
    elif tool == 'delete_board':
        result = {'deleted': boards.delete_board(vault, board['id']), 'board_id': board['id']}
        board = None
    elif tool == 'move_board':
        _folder(data, p['folder_id'])
        if p['index'] is not None:
            _integer(p['index'], 'index', 0, len(boards._group(data, p['folder_id'])))
        board = boards.move_board(vault, board['id'], p['folder_id'], p['index'])
        result = {}
    elif tool == 'add_board_items':
        uids = _uids(vault, p['uids'])
        if p['position'] is not None:
            _integer(p['position'], 'position', 0, len(board['items']))
        board = boards.add_items(vault, board['id'], uids, p['position'])
        added = board['added_uids']
        changed = {'added_uids': added, 'skipped_uids': [uid for uid in uids if uid not in added]}
        result = {}
    elif tool in ('remove_board_items', 'reorder_board_items', 'update_board_item'):
        items = board['items']
        if tool == 'update_board_item':
            target = _refs(board, [p['item_ref']])[0]
            patch = _patch(p['patch'], ('gap_lines', 'pin'))
            if 'gap_lines' in patch and patch['gap_lines'] is not None:
                _integer(patch['gap_lines'], 'gap_lines', 0, boards.MAX_GAP_LINES)
            if 'pin' in patch and type(patch['pin']) is not bool:
                raise ValueError('pin 必须是布尔值')
            target.update(patch)
            changed = {'updated_item_ref': target['question_id'] or target['uid'], 'patch': patch}
        else:
            selected = _refs(board, p['item_refs'])
            if tool == 'reorder_board_items':
                if len(selected) != len(items):
                    raise ValueError('排序必须是当前所有引用的完整排列')
                items = selected
            else:
                items = [item for item in items if item not in selected]
                changed = {'removed_item_refs': [i['question_id'] or i['uid'] for i in selected]}
        board = boards.update_board(vault, board['id'], items=items)
        result = {}
    elif tool == 'update_board_layout':
        patch = _patch(p['patch'], boards.DEFAULT_PRINT)
        for key, value in patch.items():
            if key == 'note_ratio':
                if type(value) not in (int, float) or not math.isfinite(value) or not .30 <= value <= .55:
                    raise ValueError('note_ratio 必须为 0.30 到 0.55')
            elif key == 'gap_lines':
                _integer(value, key, 0, 24)
            elif key in ('answers', 'cut_line'):
                if value not in (('none', 'append') if key == 'answers' else boards.CUT_LINES):
                    raise ValueError(f'{key} 无效')
            elif type(value) is not bool:
                raise ValueError(f'{key} 必须是布尔值')
        board = boards.update_board(vault, board['id'], print=patch)
        result = {}
    elif tool == 'update_board':
        patch = _patch(p['patch'], ('name', 'note', 'source_labels'))
        for key in ('name', 'note'):
            if key in patch:
                patch[key] = _text(patch[key], key, 120 if key == 'name' else 20000, key == 'note')
        if 'source_labels' in patch:
            if not isinstance(patch['source_labels'], list) or len(patch['source_labels']) > 100:
                raise ValueError('source_labels 必须为最多100项的列表')
            patch['source_labels'] = [_text(v, 'source_label', 200) for v in patch['source_labels']]
        board = boards.update_board(vault, board['id'], **patch)
        result = {}
    else:
        raise RequestError('unknown_tool', '展示板工具未开放')
    if board:
        result.update(board_id=board['id'], revision=board['revision'], count=len(board['items']))
    result.update(status='applied', changes=changed, catalog_revision=boards.load_boards(vault)['catalog_revision'])
    return result


def preview(vault, tool, payload, auth=lambda: None):
    result, before, after = boards.transaction(vault, lambda: dispatch(vault, tool, payload),
                                               authorize=auth, preview=True, protect_paper=True)
    old = {b['id']: b for b in before['boards']}
    new = {b['id']: b for b in after['boards']}
    impact, snapshot, reasons = [], [], []
    for bid, board in old.items():
        target = new.get(bid)
        if board == target:
            continue
        refs_after = {i['question_id'] or i['uid'] for i in target['items']} if target else set()
        removed = [i['question_id'] or i['uid'] for i in board['items'] if (i['question_id'] or i['uid']) not in refs_after]
        reset = bool(board['printed']['items'] or board['printed']['pages']) and (target is None or board['printed'] != target['printed'])
        emptied = bool(board['items']) and target is not None and not target['items']
        if target is None:
            reasons.append('删除展示板')
        if reset:
            reasons.append('重置已有纸面记录')
        if emptied:
            reasons.append('清空非空展示板')
        entry = {'board_id': bid, 'name': board['name'], 'revision': board['revision'],
                 'deleted': target is None, 'items_before': len(board['items']),
                 'items_after': len(target['items']) if target else 0,
                 'removed_item_refs': removed, 'paper_reset': reset,
                 'paper_pages': board['printed']['pages'], 'paper_count': len(board['printed']['items'])}
        if target and board['print'] != target['print']:
            entry.update(layout_before=board['print'], layout_after=target['print'])
        if tool == 'update_board_item':
            entry['item_patch'] = payload['patch']
            entry['item_ref'] = payload['item_ref']
        impact.append(entry)
        snapshot.append(board)
    if tool == 'delete_board_folder':
        reasons.append('删除文件夹')
    view = {'reasons': list(dict.fromkeys(reasons)), 'boards': impact}
    if tool == 'delete_board_folder':
        view['folder'] = next(f for f in before['folders'] if f['id'] == payload['folder_id'])
        view['keep_boards'] = payload['keep_boards']
    digest = fingerprint({'boards': snapshot, 'impact': view})
    return result, view, digest


def execute(vault, key_id, tool, request_id, payload, web_url):
    from . import mcp_operations as ops
    if tool not in SCOPES:
        raise RequestError('unknown_tool', '展示板工具未开放')
    identity, digest = request_identity(key_id, tool, request_id, payload)
    auth = lambda: authorize(vault, key_id, tool)
    with locking.write_lock():
        auth()
        existing = ops.by_identity(vault, identity)
        if existing:
            if existing['digest'] != digest:
                raise RequestError('request_conflict', '同一 request_id 的内容不同')
            return {**ops.get(vault, existing['operation_id'], key_id, web_url), 'reused': True}
        receipt = boards.load_boards(vault)['mcp_receipts'].get(identity)
        if receipt:
            if receipt['digest'] != digest:
                raise RequestError('request_conflict', '同一 request_id 的内容不同')
            return {**receipt['result'], 'reused': True}
        _, impact, snapshot = preview(vault, tool, payload, auth)
        auth()
        if impact['reasons']:
            return ops.create(vault, key_id, tool, identity, digest, payload, impact, snapshot, web_url)
        return boards.transaction(vault, lambda: dispatch(vault, tool, payload), identity, digest, auth, protect_paper=True)
