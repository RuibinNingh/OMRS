"""MCP 扩展的实际领域契约回归，全部使用临时 Vault。"""
import asyncio
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omrs import content_history, drafts, ledger, projections
from omrs.creation import create_question
from omrs.mcp import queries
from omrs.mcp.common import RequestError
from omrs.question_images import read_draft_image
from test_mcp import png
from test_mcp_protocol import MCPServerProcess, _session, _json_result


class ExtendedQueryTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.text = '完整题面' * 2500
        self.uid = create_question(self.vault, '数学', '函数', 5, question_text=self.text, answer_text='答案')['uid']

    def test_paging_does_not_mix_obisidian_change_and_historical_blob(self):
        first = queries.question_content(self.vault, self.uid)
        self.assertEqual(first['content'], self.text[:4000])
        second = queries.question_content(self.vault, self.uid, offset=4000, expected_hash=first['content_hash'])
        self.assertEqual(second['content'], self.text[4000:8000])
        with self.assertRaisesRegex(ValueError, 'expected_hash'):
            queries.question_content(self.vault, self.uid, offset=4000)
        row = content_history.projection_row(self.vault, uid=self.uid)
        path = Path(content_history.question_file(self.vault, row))
        path.write_text(path.read_text().replace('完整题面', '外部修改'))
        with self.assertRaises(RequestError) as caught:
            queries.question_content(self.vault, self.uid, offset=4000, expected_hash=first['content_hash'])
        self.assertEqual(caught.exception.code, 'content_conflict')
        old = queries.question_content(self.vault, self.uid, version=first['content_hash'])
        self.assertEqual(old['content'], first['content'])
        with self.assertRaises(RequestError):
            queries.question_content(self.vault, self.uid, version='unregistered')

    def test_batch_preserves_duplicates_and_missing_order_without_ledger_changes(self):
        before = ledger.read_commits(self.vault)
        result = queries.questions(self.vault, [self.uid, 'missing', self.uid])['items']
        self.assertEqual([v['uid'] for v in result], [self.uid, 'missing', self.uid])
        self.assertNotIn('sections', result[0])
        self.assertEqual(result[1]['error']['code'], 'not_found')
        self.assertIn('sections', queries.questions(self.vault, [self.uid], True)['items'][0])
        self.assertEqual(ledger.read_commits(self.vault), before)

    def test_history_filter_before_paging_and_correction_uses_stable_id(self):
        qid = content_history.projection_row(self.vault, uid=self.uid)['question_id']
        review = ledger.append_commit(self.vault, 'api', 'review.batch_submit', '练习', {'feedbacks': [
            {'question_id': qid, 'uid_at_that_time': '旧编号', 'subject': '数学', 'is_correct': False, 'sub_score': 3},
            {'uid_at_that_time': '其他', 'subject': '物理', 'is_correct': True, 'sub_score': 10}]})
        for _ in range(5):
            ledger.append_commit(self.vault, 'system', 'system.test', '其他', {})
        ledger.append_commit(self.vault, 'api', 'review.retract', '修正', {'target_commit_id': review['commit_id'], 'target_review_index': 0})
        rows = queries.learning_history(self.vault, uid=self.uid, subject='数学', limit=1)
        self.assertEqual(rows['items'][0]['commit_type'], 'review.retract')
        self.assertTrue(rows['items'][0]['payload']['feedbacks'][0]['retracted'])
        older = queries.learning_history(self.vault, uid=self.uid, subject='数学', before_seq=rows['next_before_seq'], limit=1)
        self.assertEqual(older['items'][0]['seq'], review['seq'])
        self.assertEqual(len(older['items'][0]['payload']['feedbacks']), 1)
        self.assertEqual(queries.learning_history(self.vault, uid='未知')['items'], [])
        self.assertEqual(queries.learning_history(self.vault, since='2100-01-01')['items'], [])
        with self.assertRaises(ValueError):
            queries.learning_history(self.vault, since='invalid')

    def test_draft_image_is_native_original_bound_to_sources_and_sha(self):
        raw = png() + b'ORIGINAL-TAIL'
        image = drafts.add_image(self.vault, 'data:image/png;base64,' + base64.b64encode(raw).decode(), 'conversation', 'run')
        draft = drafts.create_draft(self.vault, {'subject': '数学', 'category': '函数',
            'blocks': [{'section': '题目', 'kind': 'text', 'text': '正文'}], 'source_images': [image['sha256']]},
            {'conversation_id': 'conversation'})
        self.assertEqual(read_draft_image(self.vault, draft['id'], 0), (raw, 'png'))
        with self.assertRaises(ValueError):
            read_draft_image(self.vault, draft['id'], 1)
        path = Path(drafts.image_path(self.vault, image['sha256']))
        path.write_bytes(png(3, 3))
        with self.assertRaisesRegex(ValueError, 'SHA'):
            read_draft_image(self.vault, draft['id'], 0)
        path.unlink()
        outside = Path(self.vault) / 'outside.png'
        outside.write_bytes(raw)
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            read_draft_image(self.vault, draft['id'], 0)


class ExtendedSDKTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServerProcess()
        try:
            cls.server.start()
        except BaseException:
            cls.server.stop()
            raise
    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_real_sdk_full_content_batch_history_and_image(self):
        async def run():
            async with _session(self.server.mcp_port, self.server.keys['all']['secret']) as session:
                batch = _json_result(await session.call_tool('get_questions', {'uids': ['函数1', '缺失']}))
                self.assertEqual(batch['items'][1]['error']['code'], 'not_found')
                content = _json_result(await session.call_tool('get_question_content', {'uid': '函数1'}))
                self.assertIn('f(2)', content['content'])
                history = _json_result(await session.call_tool('get_question_history', {'uid': '函数1'}))
                self.assertEqual(history['total'], 1)
                timeline = _json_result(await session.call_tool('get_learning_history', {'subject': '数学', 'limit': 1}))
                self.assertEqual(len(timeline['items']), 1)
                raw = png() + b'SDK-TAIL'
                result = await session.call_tool('create_draft', {'subject': '数学', 'category': '函数', 'request_id': 'query-images',
                    'blocks': [{'section': '题目', 'kind': 'image', 'image': 0}],
                    'images': [{'file_id': 'original', 'download_url': 'https://example.com/image', 'data_base64': base64.b64encode(raw).decode()}]})
                draft = _json_result(result)
                image = await session.call_tool('get_draft_image', {'draft_id': draft['draft_id'], 'image_index': 0})
                self.assertFalse(image.isError)
                self.assertEqual(base64.b64decode(image.content[0].data), raw)
        asyncio.run(run())


class AnalyticsReportTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name

    def test_subject_category_and_date_filter_before_aggregation(self):
        from omrs.analytics import get_analytics
        from omrs.common import load_csv, save_csv, history_path, HISTORY_HEADERS
        from omrs.feedback import process_feedback
        first = create_question(self.vault, '数学', '同名', 5, question_text='数学题')['uid']
        second = create_question(self.vault, '物理', '同名', 5, question_text='物理题')['uid']
        process_feedback(self.vault, [{'uid': first, 'sub_score': 3, 'is_correct': False, 'source': 'manual'}], '')
        process_feedback(self.vault, [{'uid': second, 'sub_score': 10, 'is_correct': True, 'source': 'manual'}], '')
        rows = load_csv(history_path(self.vault), HISTORY_HEADERS)
        rows[0]['Date'] = '2026-01-01 00:00'
        rows[1]['Date'] = '2026-01-02 00:00'
        save_csv(history_path(self.vault), HISTORY_HEADERS, rows)
        all_data = get_analytics(self.vault)
        self.assertEqual({(r['subject'], r['category']) for r in all_data['categories']}, {('数学', '同名'), ('物理', '同名')})
        chosen = get_analytics(self.vault, category='同名', since='2026-01-02', until='2026-01-02')
        self.assertEqual(chosen['overview']['total_reviews'], 1)
        self.assertEqual(chosen['overview']['accuracy'], 1)
        self.assertEqual(chosen['forecast'], all_data['forecast'])
        self.assertEqual(chosen['overview']['avg_mastery'], all_data['overview']['avg_mastery'])
        self.assertEqual(get_analytics(self.vault, subject='数学')['overview']['total_reviews'], 1)
        self.assertEqual(get_analytics(self.vault, subject='不存在')['overview']['total'], 0)
        self.assertEqual(get_analytics(self.vault, category='不存在')['categories'], [])

    def test_empty_analytics_and_bad_dates(self):
        from omrs.analytics import get_analytics
        self.assertEqual(get_analytics(self.vault)['overview']['total_reviews'], 0)
        with self.assertRaises(ValueError):
            get_analytics(self.vault, since='2026-01-03', until='2026-01-01')

    def test_report_crash_after_file_recovers_same_reservation_and_index(self):
        from omrs import reports
        with patch.object(reports, '_save_index', side_effect=RuntimeError('模拟崩溃')):
            with self.assertRaises(RuntimeError):
                reports.create_mcp_report(self.vault, '报告', '<p>原报告</p>', 'key', 'retry')
        files = list(Path(reports.reports_dir(self.vault)).glob('RPT-MCP-*.html'))
        self.assertEqual(len(files), 1)
        result = reports.create_mcp_report(self.vault, '报告', '<p>原报告</p>', 'key', 'retry')
        self.assertEqual(result['id'] + '.html', files[0].name)
        self.assertTrue(result['reused'])
        self.assertEqual(len(reports.list_reports(self.vault)), 1)
        with self.assertRaises(RequestError):
            reports.create_mcp_report(self.vault, '报告', '<p>改了</p>', 'key', 'retry')
        reports.delete_report(self.vault, result['id'])
        repeated = reports.create_mcp_report(self.vault, '报告', '<p>原报告</p>', 'key', 'retry')
        self.assertEqual(repeated['id'], result['id'])
        self.assertEqual(reports.list_reports(self.vault), [])

    def test_report_size_and_permission_check_before_reuse(self):
        from omrs import reports
        from omrs.mcp.keys import create_key
        self.assertEqual(create_key(self.vault)['scopes'], ['omrs:read', 'draft:create'])
        result = reports.create_mcp_report(self.vault, '报告', 'x', 'key', 'id')
        def reject():
            raise PermissionError('已吊销')
        with self.assertRaises(PermissionError):
            reports.create_mcp_report(self.vault, '报告', 'x', 'key', 'id', reject)
        self.assertEqual(reports.get_report_html(self.vault, result['id']), b'x')
        with self.assertRaises(ValueError):
            reports.create_mcp_report(self.vault, '报告', '中' * 700000, 'key', 'large')


def _sdk_reports_test(self):
    from omrs.mcp.keys import create_key
    key = create_key(self.server.vault, '报告保存', ['omrs:read', 'report:create'])
    async def run():
        async with _session(self.server.mcp_port, key['secret']) as session:
            arguments = {'name': 'SDK 报告', 'html': '<script>window.malicious=true</script><p>保存</p>', 'request_id': 'sdk-report'}
            saved = _json_result(await session.call_tool('create_report', arguments))
            again = _json_result(await session.call_tool('create_report', arguments))
            self.assertEqual(saved['report_id'], again['report_id'])
            self.assertTrue(again['reused'])
            listed = _json_result(await session.call_tool('list_reports', {}))
            self.assertIn(saved['report_id'], [it['id'] for it in listed['items']])
            read = _json_result(await session.call_tool('get_report', {'report_id': saved['report_id'], 'limit': 20}))
            self.assertEqual(read['html'], arguments['html'][:20])
            self.assertEqual(read['next_offset'], 20)
            overview = _json_result(await session.call_tool('get_analytics', {'subject': '未知'}))
            self.assertEqual(overview['overview']['total'], 0)
    asyncio.run(run())

ExtendedSDKTests.test_real_sdk_report_idempotency_and_filtered_analysis = _sdk_reports_test


class DraftPatchTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name

    def make(self, source='agent'):
        data = {'subject': '数学', 'category': '函数', 'blocks': [{'section': '题目', 'kind': 'text', 'text': '原题'}]}
        origin = {'conversation_id': 'other-conversation', 'run_id': 'run', 'tool_call_id': 'call', 'source_channel': source}
        if source == 'mcp':
            origin.update(source_key_id='original-key', source_request_id='original', content_hash='a' * 64)
            d = drafts.create_mcp_draft(self.vault, data, origin, [])
        else:
            d = drafts.create_draft(self.vault, data, origin)
        return d

    def apply(self, d, fields=None, patches=None, request_id='edit', **options):
        from omrs.draft_write import patch_mcp_draft
        return patch_mcp_draft(self.vault, d['id'], d['revision'], fields or {}, patches or [],
                               'mcp-key', request_id, **options)

    def test_all_origins_preserved_and_client_assertion_is_separate(self):
        for source in ('agent', 'legacy', 'mcp'):
            with self.subTest(source=source):
                d = self.make(source)
                result = self.apply(d, {'cause': '没有考虑边界'}, request_id=source, cause_statement='我没考虑边界')
                self.assertTrue(result['wrote'])
                saved = drafts.get_draft(self.vault, d['id'], readonly=True)
                self.assertEqual(saved['source_channel'], source)
                self.assertEqual(saved['conversation_id'], 'other-conversation')
                self.assertEqual(saved['cause_verification'], 'client_asserted')
                self.assertEqual(saved['last_mcp_edit']['key_id'], 'mcp-key')
                self.apply(saved, {'cause': ''}, request_id=f'{source}-clear', cause_statement='撤回这条错因')
                cleared = drafts.get_draft(self.vault, d['id'], readonly=True)
                self.assertEqual((cleared['cause'], cleared['cause_statement'], cleared['cause_verification']),
                                 ('', '撤回这条错因', 'client_asserted'))
                from omrs.draft_write import patch_draft
                with self.assertRaises(drafts.DraftError):
                    patch_draft(self.vault, d['id'], cleared['revision'], {'note': '不能越权'}, [],
                                {'conversation_id': 'mine', 'run_id': 'r', 'tool_call_id': 'c'})

    def test_manual_protection_prevents_entire_patch_and_retry_reuses_receipt(self):
        d = self.make()
        manual = drafts.update_draft(self.vault, d['id'], 1, {'note': '用户备注'}, d['blocks'])
        result = self.apply(manual, {'note': '覆盖', 'category': '新分类'})
        self.assertFalse(result['wrote'])
        self.assertEqual(result['suggestions'][0]['target'], 'field:note')
        saved = drafts.get_draft(self.vault, d['id'], readonly=True)
        self.assertEqual((saved['note'], saved['category'], saved['revision']), ('用户备注', '函数', 2))
        repeated = self.apply(manual, {'note': '覆盖', 'category': '新分类'})
        self.assertTrue(repeated['reused'])
        with self.assertRaises(RequestError):
            self.apply(manual, {'note': '不同'})

    def test_protected_targets_block_even_same_value_or_no_effect(self):
        d = self.make()
        manual = drafts.update_draft(self.vault, d['id'], d['revision'], {'note': '用户备注'},
            [{**d['blocks'][0], 'text': '人工正文'}])
        cases = [({'note': '用户备注', 'category': '新分类'}, []),
                 ({'note': '用户备注'}, []),
                 ({'category': '新分类'}, [{'block_id': manual['blocks'][0]['id'], 'text': '人工正文'}])]
        for index, (fields, patches) in enumerate(cases):
            result = self.apply(manual, fields, patches, request_id=f'protected-{index}')
            self.assertFalse(result['wrote'])
            self.assertTrue(result['suggestions'])
            saved = drafts.get_draft(self.vault, d['id'], readonly=True)
            self.assertEqual((saved['category'], saved['revision']), ('函数', manual['revision']))

    def test_cas_finished_invalid_block_and_receipt_atomicity(self):
        d = self.make()
        with self.assertRaises(drafts.DraftError):
            self.apply(d, {'difficulty': 3})
        with self.assertRaises(drafts.DraftError):
            self.apply(d, {'cause': '猜测'})
        with self.assertRaises(drafts.DraftError):
            self.apply(d, {'cause': ''})
        with self.assertRaises(drafts.DraftError):
            self.apply(d, patches=[{'block_id': d['blocks'][0]['id'], 'box': {}}])
        calls = []
        def interrupted():
            calls.append(1)
            if len(calls) == 3:
                raise PermissionError('处理中失效')
        with self.assertRaises(PermissionError):
            self.apply(d, {'category': '新分类'}, authorize=interrupted)
        self.assertEqual(drafts.get_draft(self.vault, d['id'], readonly=True)['revision'], 1)
        result = self.apply(d, {'category': '新分类'})
        self.assertFalse(result['reused'])
        self.assertTrue(self.apply(d, {'category': '新分类'})['reused'])
        with self.assertRaises(drafts.DraftError) as caught:
            self.apply(d, {'note': '旧版本'}, request_id='old')
        self.assertEqual(caught.exception.code, 'revision_conflict')
        current = drafts.get_draft(self.vault, d['id'], readonly=True)
        drafts.discard_draft(self.vault, d['id'], current['revision'])
        current = drafts.get_draft(self.vault, d['id'], readonly=True)
        with self.assertRaises(drafts.DraftError) as caught:
            self.apply(current, {'note': '已结束'}, request_id='ended')
        self.assertEqual(caught.exception.code, 'state_conflict')


def _sdk_draft_patch_test(self):
    from omrs.mcp.keys import create_key
    key = create_key(self.server.vault, '草稿修订', ['omrs:read', 'draft:update'])
    d = drafts.create_draft(self.server.vault, {'subject': '数学', 'category': '函数',
        'blocks': [{'section': '题目', 'kind': 'text', 'text': '别的来源'}]}, {'conversation_id': 'external-origin'})
    before = ledger.read_commits(self.server.vault)
    async def run():
        async with _session(self.server.mcp_port, key['secret']) as session:
            args = {'draft_id': d['id'], 'expected_revision': 1, 'request_id': 'sdk-update',
                    'block_patches': [{'block_id': d['blocks'][0]['id'], 'text': '修订正文'}]}
            updated = _json_result(await session.call_tool('update_draft', args))
            self.assertTrue(updated['wrote'])
            self.assertTrue(_json_result(await session.call_tool('update_draft', args))['reused'])
            conflict = await session.call_tool('update_draft', {**args, 'request_id': 'new-id'})
            self.assertTrue(conflict.isError)
            self.assertIn('revision_conflict:', conflict.content[0].text)
    asyncio.run(run())
    self.assertEqual(ledger.read_commits(self.server.vault), before)

ExtendedSDKTests.test_real_sdk_cross_source_patch_and_cas = _sdk_draft_patch_test


class BoardVersionTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name

    def test_v3_read_stays_unwritten_until_change_and_revisions_preserved(self):
        import json
        from omrs import boards
        old = {'version': 3, 'folders': [], 'boards': [{'id': 'old', 'name': '旧板', 'items': []}]}
        path = Path(boards.boards_path(self.vault))
        path.write_text(json.dumps(old))
        before = path.read_bytes()
        self.assertEqual(boards.get_board(self.vault, 'old')['revision'], 1)
        self.assertEqual(path.read_bytes(), before)
        changed = boards.update_board(self.vault, 'old', note='新备注', expected_revision=1)
        self.assertEqual(changed['revision'], 2)
        self.assertEqual(json.loads(path.read_text())['version'], 4)
        with self.assertRaises(boards.BoardConflict):
            boards.update_board(self.vault, 'old', name='过期覆盖', expected_revision=1)
        self.assertEqual(boards.get_board(self.vault, 'old')['note'], '新备注')

    def test_catalog_cas_and_transaction_preview_receipt_are_atomic(self):
        from omrs import boards
        folder = boards.create_folder(self.vault, '文件夹', expected_catalog_revision=0)
        with self.assertRaises(boards.BoardConflict):
            boards.create_folder(self.vault, '过期', expected_catalog_revision=0)
        board = boards.create_board(self.vault, '展示板', folder_id=folder['id'], expected_catalog_revision=1)
        path = Path(boards.boards_path(self.vault))
        original = path.read_bytes()
        def change():
            result = boards.update_board(self.vault, board['id'], note='MCP 修改', expected_revision=1)
            return {'board_id': result['id'], 'revision': result['revision']}
        preview, before, after = boards.transaction(self.vault, change, preview=True)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(preview['revision'], 2)
        with patch.object(boards, '_persist', side_effect=OSError('模拟中断')):
            with self.assertRaises(OSError):
                boards.transaction(self.vault, change, identity='request', digest='same')
        self.assertEqual(path.read_bytes(), original)
        result = boards.transaction(self.vault, change, identity='request', digest='same')
        self.assertEqual(result['revision'], 2)
        saved_bytes = path.read_bytes()
        self.assertTrue(boards.transaction(self.vault, change, identity='request', digest='same')['reused'])
        self.assertEqual(path.read_bytes(), saved_bytes)
        with self.assertRaises(RequestError):
            boards.transaction(self.vault, change, identity='request', digest='different')
        boards.create_folder(self.vault, '后续')
        self.assertIn('request', boards.load_boards(self.vault)['mcp_receipts'])
        self.assertEqual(boards.get_board(self.vault, board['id'])['revision'], 2)
