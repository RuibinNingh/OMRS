"""快照导出的真实原图、边界、响应丢失与崩溃恢复回归。"""
import base64
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from omrs import boards, exporting, ledger, mcp_exports as exports
from omrs.creation import create_question
from omrs.mcp.common import RequestError
from test_mcp import png
from test_boards import embedded_data, layout_for


class ExportSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.raw = png()+b'EXACT-TAIL'
        self.uid = create_question(self.vault, '数学', '导出', 5, question_text='题面\n![[original.png]]', answer_text='答案')['uid']
        folder = Path(self.vault) / '错题/附件'
        folder.mkdir(exist_ok=True)
        self.image = folder/'original.png'; self.image.write_bytes(self.raw)
        self.board = boards.create_board(self.vault, '原字节导出', [self.uid])

    def create(self, request='export', mode='all', **kwargs):
        return exports.create(self.vault, self.board['id'], mode, request, 'key1', 'https://web.example', **kwargs)

    def test_native_bytes_in_immutable_self_contained_snapshot_without_paper_or_ledger(self):
        before = ledger.read_commits(self.vault)
        paper = boards.get_board(self.vault, self.board['id'])['printed']
        result = self.create()
        raw, filename = exports.download(self.vault, result['export_id'])
        data = embedded_data(raw)
        img = next(b for b in data['questions'][0]['blocks'] if b['t']=='img')['img']['src']
        self.assertEqual(base64.b64decode(img.split(',',1)[1]), self.raw)
        self.assertNotIn('id="btnDone"', raw.decode())
        self.assertIn('原字节导出', filename)
        self.assertLess(len(json.dumps(result)), 1500)
        self.assertNotIn('html', result)
        self.assertEqual(result['download_url'], 'https://web.example/api/mcp/exports/download?export_id='+result['export_id'])
        boards.update_board(self.vault, self.board['id'], note='之后的修改')
        retry = self.create()
        self.assertTrue(retry['reused'])
        self.assertEqual(exports.download(self.vault, result['export_id'])[0], raw)
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['printed'], paper)
        self.assertEqual(ledger.read_commits(self.vault), before)
        with self.assertRaises(RequestError) as caught:
            self.create(mode='new')
        self.assertEqual(caught.exception.code, 'request_conflict')

    def test_export_does_not_use_arbitrary_path_fallback_or_links(self):
        with patch.object(exporting, '_find_image', side_effect=AssertionError('旧读图不应执行')):
            self.create()
        outside = Path(self.vault)/'private.png'; outside.write_bytes(self.raw)
        self.image.unlink(); self.image.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.create('linked')
        with sqlite3.connect(Path(self.vault)/'错题/.omrs/mcp_exports.db') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM exports').fetchone()[0], 1)

    def test_new_scope_uses_existing_paper_without_recording_it(self):
        layout = layout_for([(i['question_id'], i['uid']) for i in self.board['items']])
        board = boards.record_printed(self.vault, self.board['id'], 'all', layout)
        paper = board['printed']
        uid2 = create_question(self.vault, '数学', '导出', 5, question_text='新增')['uid']
        boards.add_items(self.vault, self.board['id'], [uid2])
        result = self.create(mode='new')
        data = embedded_data(exports.download(self.vault, result['export_id'])[0])
        self.assertEqual([q['uid'] for q in data['questions']], [uid2])
        self.assertEqual(data['meta']['index_start'], 2)
        self.assertEqual(boards.get_board(self.vault, self.board['id'])['printed'], paper)

    def test_expiry_cleans_file_and_blob_but_preserves_request_tombstone(self):
        result = self.create()
        with patch.object(exports.time, 'time', return_value=time.time()+exports.TTL+1):
            with self.assertRaises(RequestError) as caught:
                exports.download(self.vault, result['export_id'])
            self.assertEqual(caught.exception.code, 'export_expired')
            with self.assertRaises(RequestError):
                self.create()
        self.assertFalse(Path(exports._file(self.vault, result['export_id'])).exists())
        with sqlite3.connect(Path(self.vault)/'错题/.omrs/mcp_exports.db') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM contents').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM exports').fetchone()[0], 1)

    def test_crash_after_stable_blob_reservation_recovers_original_board(self):
        with patch.object(exports, '_materialize', side_effect=OSError('模拟文件提交前崩溃')):
            with self.assertRaises(OSError):
                self.create()
        boards.delete_board(self.vault, self.board['id'])
        result = self.create()
        self.assertTrue(result['reused'])
        self.assertEqual(embedded_data(exports.download(self.vault, result['export_id'])[0])['meta']['question_count'], 1)

    def test_size_limit_auth_and_download_identity(self):
        with patch.object(exports, 'MAX_BYTES', 50):
            with self.assertRaises(RequestError) as caught:
                self.create()
        self.assertEqual(caught.exception.code, 'export_too_large')
        def denied():
            raise PermissionError('已吊销')
        with self.assertRaises(PermissionError):
            self.create(authorize=denied)
        for bad in ('../private', '', 'ex_no', 123):
            with self.assertRaises(RequestError):
                exports.download(self.vault, bad)

    def test_expected_revision_and_snapshot_file_tamper(self):
        with self.assertRaises(boards.BoardConflict):
            self.create(expected_revision=999)
        result = self.create(expected_revision=self.board['revision'])
        path = Path(exports._file(self.vault, result['export_id']))
        raw = path.read_bytes(); path.write_bytes(b'x'+raw[1:])
        with self.assertRaises(ValueError):
            exports.download(self.vault, result['export_id'])
