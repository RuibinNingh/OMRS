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
