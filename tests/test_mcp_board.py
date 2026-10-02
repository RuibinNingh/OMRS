"""展示板全量管理、并发、确认和崩溃恢复契约；只用临时 Vault。"""
import asyncio
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from omrs import boards, ledger, mcp_board as core, mcp_operations as ops, runtime_records
from omrs.creation import create_question
from omrs.mcp.common import RequestError
from omrs.mcp.keys import create_key, revoke_key, update_scopes, active_key, _SCOPES
from test_mcp_protocol import MCPServerProcess, _session, _json_result


class BoardManagementTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.uids = [create_question(self.vault, '数学', '函数', 5, question_text=f'题{i}')['uid'] for i in range(2)]
        self.key = create_key(self.vault, '全量', list(_SCOPES))
        self.board = boards.create_board(self.vault, '验收', self.uids)
        self.before_ledger = ledger.read_commits(self.vault)

    def run_tool(self, tool, payload, rid='r1', key=None):
        return core.execute(self.vault, (key or self.key)['key_id'], tool, rid, payload, 'https://omrs.example:8443')

    def board_payload(self, **extras):
        board = boards.get_board(self.vault, self.board['id'])
        return dict(board_id=board['id'], expected_revision=board['revision'], **extras)

    def delete_pending(self, rid='delete', key=None):
        return self.run_tool('delete_board', self.board_payload(expected_catalog_revision=boards.catalog(self.vault)['catalog_revision']), rid, key)

    def paper(self):
        board = boards.get_board(self.vault, self.board['id'])
        data = boards.load_boards(self.vault)
        data['boards'][0]['printed'] = {'at': '2026-10-01', 'pages': 2, 'cursor': {'page': 2, 'y': 100},
            'items': [{'question_id': i['question_id'], 'uid': i['uid'], 'page': 1, 'height': 20, 'hash': 'abc'} for i in board['items']]}
        boards.save_boards(self.vault, data)
        return boards.get_board(self.vault, self.board['id'])['printed']

    def test_strict_batch_sort_patch_and_idempotency_no_learning_change(self):
        board = boards.create_board(self.vault, '空板')
        payload = dict(board_id=board['id'], expected_revision=board['revision'], uids=[*self.uids, self.uids[0]], position=None)
        result = self.run_tool('add_board_items', payload)
        self.assertEqual(result['changes']['added_uids'], self.uids)
        self.assertTrue(self.run_tool('add_board_items', payload)['reused'])
        with self.assertRaises(RequestError) as conflict:
            self.run_tool('add_board_items', {**payload, 'uids': []})
        self.assertEqual(conflict.exception.code, 'request_conflict')
        updated = boards.get_board(self.vault, board['id'])
        invalid = dict(board_id=board['id'], expected_revision=updated['revision'], uids=[self.uids[0], 'missing'], position=None)
        before = Path(boards.boards_path(self.vault)).read_bytes()
        with self.assertRaises(RequestError):
            self.run_tool('add_board_items', invalid, 'invalid')
        self.assertEqual(before, Path(boards.boards_path(self.vault)).read_bytes())
        refs = [i['question_id'] for i in updated['items']]
        for bad in (refs[:1], [refs[0], refs[0]]):
            with self.assertRaises(ValueError):
                self.run_tool('reorder_board_items', dict(board_id=board['id'], expected_revision=updated['revision'], item_refs=bad), 'bad')
        sorted_result = self.run_tool('reorder_board_items', dict(board_id=board['id'], expected_revision=updated['revision'], item_refs=refs[::-1]), 'sort')
        patched = self.run_tool('update_board_item', dict(board_id=board['id'], expected_revision=sorted_result['revision'], item_ref=refs[0], patch={'pin': True, 'gap_lines': 8}), 'patch')
        self.assertEqual(patched['status'], 'applied')
        self.assertEqual(ledger.read_commits(self.vault), self.before_ledger)

    def test_layout_invalid_values_and_stale_version_do_not_write(self):
        for value in ({'gap_lines': 25}, {'note_ratio': .9}, {'locked': 1}, {'arbitrary': 3}, {'answers': 'yes'}):
            with self.assertRaises(ValueError):
                self.run_tool('update_board_layout', self.board_payload(patch=value), 'invalid')
        old = self.board_payload(patch={'gap_lines': 4})
        boards.update_board(self.vault, self.board['id'], note='网页已修改')
        with self.assertRaises(boards.BoardConflict):
            self.run_tool('update_board_layout', old)
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['print']['gap_lines'], 2)

    def test_pending_confirm_repeat_and_owner_boundary(self):
        before = Path(boards.boards_path(self.vault)).read_bytes()
        pending = self.delete_pending()
        self.assertEqual(pending['status'], 'pending_confirmation')
        self.assertTrue(pending['confirmation_url'].startswith('https://omrs.example:8443/#/history?operation='))
        self.assertEqual(Path(boards.boards_path(self.vault)).read_bytes(), before)
        self.assertEqual(self.delete_pending()['operation_id'], pending['operation_id'])
        other = create_key(self.vault, '其他', ['omrs:read'])
        with self.assertRaises(RequestError):
            ops.get(self.vault, pending['operation_id'], other['key_id'])
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['status'], 'applied')
        receipt_bytes = Path(boards.boards_path(self.vault)).read_bytes()
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['status'], 'applied')
        self.assertEqual(Path(boards.boards_path(self.vault)).read_bytes(), receipt_bytes)
        self.assertEqual(ledger.read_commits(self.vault), self.before_ledger)

    def test_reject_expire_revision_revocation_and_permission_changes(self):
        pending = self.delete_pending('reject')
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'reject')['status'], 'rejected')
        expired = self.delete_pending('expire')
        with patch('omrs.mcp_operations.time.time', return_value=time.time()+601):
            self.assertEqual(ops.decide(self.vault, expired['operation_id'], 'confirm')['status'], 'expired')
        changed = self.delete_pending('changed')
        boards.update_board(self.vault, self.board['id'], note='改变')
        self.assertEqual(ops.decide(self.vault, changed['operation_id'], 'confirm')['error_code'], 'revision_conflict')
        missing_permission = self.delete_pending('permission')
        update_scopes(self.vault, self.key['key_id'], ['omrs:read'])
        self.assertEqual(ops.decide(self.vault, missing_permission['operation_id'], 'confirm')['error_code'], 'forbidden')
        update_scopes(self.vault, self.key['key_id'], list(_SCOPES))
        revoked = self.delete_pending('revoked')
        revoke_key(self.vault, self.key['key_id'])
        self.assertEqual(ops.decide(self.vault, revoked['operation_id'], 'confirm')['error_code'], 'forbidden')
        self.assertIsNotNone(boards.get_board(self.vault, self.board['id']))
        with self.assertRaises(ValueError):
            update_scopes(self.vault, self.key['key_id'], list(_SCOPES))

    def test_expired_key_cannot_confirm_or_be_revived(self):
        pending = self.delete_pending()
        keypath = Path(self.vault) / '错题/.omrs/mcp_keys.json'
        data = json.loads(keypath.read_text())
        data['keys'][0]['expires_at'] = '2000-01-01T00:00:00Z'
        keypath.write_text(json.dumps(data))
        self.assertIsNone(active_key(self.vault, self.key['key_id']))
        with self.assertRaises(ValueError):
            update_scopes(self.vault, self.key['key_id'], ['omrs:read'])
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['error_code'], 'forbidden')

    def test_folder_delete_snapshot_catches_child_change_without_catalog_change(self):
        folder = boards.create_folder(self.vault, '目录')
        boards.move_board(self.vault, self.board['id'], folder['id'])
        p = dict(folder_id=folder['id'], keep_boards=True, expected_catalog_revision=boards.catalog(self.vault)['catalog_revision'])
        pending = self.run_tool('delete_board_folder', p)
        boards.update_board(self.vault, self.board['id'], note='目录版本不变但子板变化')
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['error_code'], 'revision_conflict')
        p['expected_catalog_revision'] = boards.catalog(self.vault)['catalog_revision']
        retry = self.run_tool('delete_board_folder', p, 'new')
        self.assertEqual(ops.decide(self.vault, retry['operation_id'], 'confirm')['status'], 'applied')
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['folder_id'], '')

    def test_paper_is_preserved_for_references_unlock_cannot_bypass_reset_confirmation(self):
        paper = self.paper()
        self.run_tool('update_board_layout', self.board_payload(patch={'locked': False}), 'unlock')
        result = self.run_tool('remove_board_items', self.board_payload(item_refs=[self.uids[0]]), 'remove')
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['printed'], paper)
        pending = self.run_tool('update_board_item', self.board_payload(item_ref=self.uids[1], patch={'gap_lines': 8}), 'gap')
        self.assertEqual(pending['status'], 'pending_confirmation')
        self.assertTrue(pending['impact']['boards'][0]['paper_reset'])
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['printed'], paper)
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['status'], 'applied')
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['printed']['items'], [])
        emptied = self.run_tool('remove_board_items', self.board_payload(item_refs=[self.uids[1]]), 'clear')
        self.assertEqual(emptied['status'], 'pending_confirmation')

    def test_duplicate_does_not_copy_paper_and_response_loss_reuses_receipt(self):
        self.paper()
        p = self.board_payload(name='副本', expected_catalog_revision=boards.catalog(self.vault)['catalog_revision'])
        first = self.run_tool('duplicate_board', p)
        retry = self.run_tool('duplicate_board', p)
        self.assertEqual(first['board_id'], retry['board_id'])
        self.assertTrue(retry['reused'])
        self.assertEqual(boards.get_board(self.vault, first['board_id'])['printed']['items'], [])

    def test_crash_after_domain_commit_restores_applying_even_after_revocation(self):
        pending = self.delete_pending()
        original = ops._save_state
        def crash(vault, row, status, *args, **kwargs):
            if status == 'applied':
                raise OSError('模拟响应前进程退出')
            return original(vault, row, status, *args, **kwargs)
        with patch.object(ops, '_save_state', side_effect=crash):
            with self.assertRaises(OSError):
                ops.decide(self.vault, pending['operation_id'], 'confirm')
        revoke_key(self.vault, self.key['key_id'])
        self.assertEqual(ops.get(self.vault, pending['operation_id'])['status'], 'applied')
        self.assertIsNone(boards.get_board(self.vault, self.board['id']))

    def test_crash_before_domain_commit_recovers_once_and_pending_survives(self):
        pending = self.delete_pending()
        self.assertEqual(ops.get(self.vault, pending['operation_id'])['status'], 'pending_confirmation')
        original = boards._persist
        with patch.object(boards, '_persist', side_effect=OSError('模拟磁盘中断')):
            with self.assertRaises(OSError):
                ops.decide(self.vault, pending['operation_id'], 'confirm')
        self.assertIsNotNone(boards.get_board(self.vault, self.board['id']))
        with patch.object(boards, '_persist', wraps=original) as spy:
            self.assertEqual(ops.get(self.vault, pending['operation_id'])['status'], 'applied')
            self.assertEqual(spy.call_count, 1)

    def test_runtime_keeps_summary_only_and_truthful_states(self):
        seq = runtime_records.begin(self.vault, 'delete_board', {'board_id': self.board['id'], 'patch': {'note': '机密'}}, self.key)
        pending = self.delete_pending()
        runtime_records.finish(self.vault, seq, 10, pending)
        self.assertEqual(runtime_records.detail(self.vault, seq)['status'], 'pending_confirmation')
        self.assertNotIn('机密', Path(runtime_records.path(self.vault)).read_bytes().decode('latin1'))
        ops.decide(self.vault, pending['operation_id'], 'reject')
        row = runtime_records.detail(self.vault, seq)
        self.assertEqual(row['status'], 'rejected')
        self.assertIn('未应用', row['summary'])
        self.assertEqual(runtime_records.list_records(self.vault, {'status': 'rejected'})['summary']['total'], 1)


class BoardSDKTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServerProcess().start()
        cls.key = create_key(cls.server.vault, '管理全权', list(_SCOPES))
    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_real_sdk_management_and_web_confirmation_boundary(self):
        import urllib.request
        import urllib.error
        async def run():
            async with _session(self.server.mcp_port, self.key['secret']) as session:
                tools = (await session.list_tools()).tools
                self.assertEqual(len(tools), 38)
                self.assertNotIn('confirm_mcp_operation', [t.name for t in tools])
                listing = _json_result(await session.call_tool('list_boards', {}))
                folder = _json_result(await session.call_tool('create_board_folder', {'name': 'SDK目录', 'expected_catalog_revision': listing['catalog_revision'], 'request_id': 'folder'}))
                result = _json_result(await session.call_tool('create_board', {'name': 'SDK板', 'folder_id': folder['folder']['id'], 'expected_catalog_revision': folder['catalog_revision'], 'request_id': 'board'}))
                self.assertEqual(result['status'], 'applied')
                p = {'board_id': result['board_id'], 'expected_revision': result['revision'], 'uids': ['函数1', '力学1'], 'request_id': 'add'}
                added = _json_result(await session.call_tool('add_board_items', p))
                self.assertEqual(added['changes']['added_uids'], p['uids'])
                pending = _json_result(await session.call_tool('delete_board', {'board_id': result['board_id'], 'expected_revision': added['revision'], 'expected_catalog_revision': added['catalog_revision'], 'request_id': 'delete'}))
                self.assertEqual(pending['status'], 'pending_confirmation')
                self.assertTrue(pending['confirmation_url'].startswith(f'http://127.0.0.1:{self.server.web_port}/'))
                current = _json_result(await session.call_tool('get_mcp_operation', {'operation_id': pending['operation_id']}))
                self.assertEqual(current['status'], 'pending_confirmation')
                self.assertIsNotNone(boards.get_board(self.server.vault, result['board_id']))
                req = urllib.request.Request(f'http://127.0.0.1:{self.server.web_port}/api/mcp/operations/decide',
                    data=json.dumps({'operation_id': pending['operation_id'], 'decision': 'confirm'}).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+self.key['secret']})
                with self.assertRaises(urllib.error.HTTPError) as forbidden:
                    urllib.request.urlopen(req)
                self.assertEqual(forbidden.exception.code, 403)
                del req.headers['Authorization']
                confirmed = json.load(urllib.request.urlopen(req))
                self.assertEqual(confirmed['operation']['status'], 'applied')
                self.assertIsNone(boards.get_board(self.server.vault, result['board_id']))
        asyncio.run(run())

    def test_full_workflow_and_exact_discovery_permissions(self):
        import urllib.request
        import urllib.error
        from omrs.common import mastery_path
        uid = create_question(self.server.vault, '数学', 'SDK推荐', 5, question_text='SDK推荐题')['uid']
        learning_before = ledger.read_commits(self.server.vault)
        mastery_before = Path(mastery_path(self.server.vault)).read_bytes()
        async def run():
            async with _session(self.server.mcp_port, self.key['secret']) as session:
                async def call(tool, args):
                    result = await session.call_tool(tool, args)
                    self.assertFalse(result.isError, str(result))
                    return _json_result(result)
                expected = {'list_taxonomy','search_questions','get_question','get_question_image','get_overview',
                    'get_recommendations','list_sessions','get_session','list_drafts','get_draft','create_draft',
                    'get_questions','get_question_content','get_draft_image','get_question_history','get_learning_history',
                    'get_analytics','list_reports','get_report','create_report','update_draft','list_boards','get_board',
                    'create_board','update_board','duplicate_board','delete_board','add_board_items','remove_board_items',
                    'reorder_board_items','update_board_layout','update_board_item','create_board_folder',
                    'update_board_folder','delete_board_folder','move_board','export_board','get_mcp_operation'}
                self.assertEqual({tool.name for tool in (await session.list_tools()).tools}, expected)
                recommendations = await call('get_recommendations', {'subject': '数学', 'count':20})
                self.assertIn(uid, [item['uid'] for item in recommendations['selection']])
                catalog = await call('list_boards', {})
                folder = await call('create_board_folder', {'name':'全链路', 'expected_catalog_revision':catalog['catalog_revision'],'request_id':'full-folder'})
                made = await call('create_board', {'name':'全链路', 'folder_id':folder['folder_id'], 'expected_catalog_revision':folder['catalog_revision'],'request_id':'full-board'})
                made = await call('add_board_items', {'board_id':made['board_id'],'uids':[uid,'函数1','力学1'], 'expected_revision':made['revision'],'request_id':'full-add'})
                details = await call('get_board', {'board_id':made['board_id']})
                refs = [item['question_id'] for item in details['items']]
                made = await call('reorder_board_items', {'board_id':made['board_id'],'item_refs':refs[::-1],'expected_revision':made['revision'],'request_id':'full-sort'})
                made = await call('update_board_item', {'board_id':made['board_id'],'item_ref':refs[0],'patch':{'gap_lines':7,'pin':True},'expected_revision':made['revision'],'request_id':'full-gap'})
                made = await call('update_board_layout', {'board_id':made['board_id'],'patch':{'answers':'append','note_ratio':.4},'expected_revision':made['revision'],'request_id':'full-layout'})
                report = await call('export_board', {'board_id':made['board_id'], 'expected_revision':made['revision'], 'request_id':'full-export'})
                self.assertEqual(report['status'],'exported')
                self.assertLess(len(json.dumps(report)),1500)
                import urllib.request
                payload = urllib.request.urlopen(report['download_url']).read()
                self.assertIn(b'<!DOCTYPE html>', payload)
                self.assertNotIn(b'id="btnDone"', payload)
                self.assertTrue((await call('export_board', {'board_id':made['board_id'], 'expected_revision':made['revision'], 'request_id':'full-export'}))['reused'])
                # 真正经过 Web 修改，再用 MCP 的旧版本写入，不能丢掉网页内容。
                web_args = {'id': made['board_id'], 'expected_revision': made['revision'], 'note': '网页已修改'}
                web_request = urllib.request.Request(f'http://127.0.0.1:{self.server.web_port}/api/board/update',
                    data=json.dumps(web_args).encode(), headers={'Content-Type': 'application/json'})
                web_saved = json.load(urllib.request.urlopen(web_request))['board']
                stale = await session.call_tool('update_board', {'board_id':made['board_id'], 'expected_revision':made['revision'],
                    'patch':{'note':'过期覆盖'}, 'request_id':'stale-web'})
                self.assertTrue(stale.isError)
                self.assertIn('revision_conflict', stale.content[0].text)
                # 网页改名也必须检查目录版本；目录先变化后，旧目录版本不能写板名。
                changed_folder = await call('update_board_folder', {'folder_id':folder['folder_id'], 'patch':{'name':'全链路目录'},
                    'expected_catalog_revision':made['catalog_revision'], 'request_id':'folder-rename'})
                web_rename = urllib.request.Request(f'http://127.0.0.1:{self.server.web_port}/api/board/update',
                    data=json.dumps({'id':made['board_id'], 'name':'过期改名', 'expected_revision':web_saved['revision'],
                                     'expected_catalog_revision':made['catalog_revision']}).encode(), headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as conflict:
                    urllib.request.urlopen(web_rename)
                self.assertEqual(conflict.exception.code, 409)
                made = await call('update_board', {'board_id':made['board_id'], 'expected_revision':web_saved['revision'],
                    'expected_catalog_revision':changed_folder['catalog_revision'], 'patch':{'name':'全链路完成','note':'网页与MCP版本已核对'}, 'request_id':'full-rename'})
                made = await call('move_board', {'board_id':made['board_id'], 'folder_id':'', 'expected_revision':made['revision'],
                    'expected_catalog_revision':made['catalog_revision'], 'request_id':'full-move'})
                copied = await call('duplicate_board', {'board_id':made['board_id'], 'name':'全链路副本', 'expected_revision':made['revision'],
                    'expected_catalog_revision':made['catalog_revision'], 'request_id':'full-copy'})
                removed = await call('remove_board_items', {'board_id':copied['board_id'], 'item_refs':refs[:1],
                    'expected_revision':copied['revision'], 'request_id':'full-remove'})
                self.assertEqual(removed['changes']['removed_item_refs'], refs[:1])
                pending_folder = await call('delete_board_folder', {'folder_id':folder['folder_id'],
                    'expected_catalog_revision':removed['catalog_revision'], 'request_id':'full-delete-folder'})
                self.assertEqual(pending_folder['status'],'pending_confirmation')
                self.assertEqual(urllib.request.urlopen(report['download_url']).read(),payload)
                self.assertEqual(ledger.read_commits(self.server.vault), learning_before)
                self.assertEqual(Path(mastery_path(self.server.vault)).read_bytes(), mastery_before)
            for scopes, count in ((['omrs:read'],22), (['draft:create'],1), (['board:write'],0), (['omrs:read','draft:update'],23)):
                key = create_key(self.server.vault, '发现', scopes)
                async with _session(self.server.mcp_port, key['secret']) as session:
                    self.assertEqual(len((await session.list_tools()).tools),count)
                    if 'board:write' not in scopes or 'omrs:read' not in scopes:
                        denied = await session.call_tool('create_board', {'name':'越权', 'expected_catalog_revision':0, 'request_id':'denied'})
                        self.assertTrue(denied.isError)
                        self.assertIn('forbidden', denied.content[0].text)
                    # 同一已建立会话实时编辑权限，不能用旧 token/cache 维持增权。
                    update_scopes(self.server.vault, key['key_id'], list(_SCOPES))
                    self.assertEqual(len((await session.list_tools()).tools),38)
                    update_scopes(self.server.vault, key['key_id'], ['omrs:read'])
                    self.assertEqual(len((await session.list_tools()).tools),22)
        asyncio.run(run())
