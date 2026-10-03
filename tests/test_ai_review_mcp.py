"""MCP 自动写必须先落盘意图；失败和重试只按精确原生回执收束。"""
import asyncio
import tempfile
import unittest
from unittest import mock

from omrs import ai_review, drafts
from omrs.mcp import server as mcp_server
from omrs.mcp.keys import create_key


class AiReviewMcpIntentTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='omrs-ai-review-mcp-')
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.key = create_key(self.vault, '自动草稿测试', ['omrs:read', 'draft:create'])
        self.server = mcp_server.build_server(self.vault)
        token = mcp_server.AccessToken(token=self.key['secret'], client_id=self.key['key_id'], scopes=self.key['scopes'])
        auth = mock.patch.object(mcp_server, 'get_access_token', return_value=token)
        auth.start()
        self.addCleanup(auth.stop)
        self.args = {'subject': '数学', 'category': '自动审核', 'request_id': 'automatic-draft',
                     'blocks': [{'section': '题目', 'kind': 'text', 'text': '原生回执验证'}]}

    def call(self, args=None):
        return asyncio.run(self.server._execute_tool('create_draft', self.args if args is None else args))

    def rows(self):
        records = ai_review.items(self.vault, {'view': 'records'})['items']
        return [ai_review.get(self.vault, row['id']) for row in records if row['kind'] == 'operation']

    def test_failed_intent_registration_blocks_business_tool(self):
        with (mock.patch.object(ai_review, 'create', side_effect=OSError('意图落盘失败')),
              mock.patch.object(drafts, 'create_mcp_draft') as create):
            with self.assertRaises(mcp_server.ToolError) as error:
                self.call()
            create.assert_not_called()
        self.assertIn('无法登记审核意图', str(error.exception))
        self.assertEqual(drafts.counts(self.vault)['review'], 0)

    def test_lost_terminal_state_recovers_committed_draft_without_replay(self):
        original = ai_review.set_state
        def fail_terminal(vault, operation_id, status, *args, **kwargs):
            if status == 'applied':
                raise OSError('统一库终态丢失')
            return original(vault, operation_id, status, *args, **kwargs)
        with mock.patch.object(ai_review, 'set_state', side_effect=fail_terminal):
            result = mcp_server._review_result(self.call())
        row = self.rows()[0]
        self.assertEqual(row['status'], 'running')
        receipt = ai_review._auto_receipt(self.vault, row)
        self.assertEqual(receipt['draft_id'], result['draft_id'])
        with mock.patch.object(drafts, 'create_mcp_draft', side_effect=AssertionError('不能重建已提交草稿')):
            ai_review.initialize(self.vault)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'applied')
        self.assertEqual(drafts.counts(self.vault)['review'], 1)

    def test_native_receipt_failure_rolls_back_tool_transaction_and_records_failure(self):
        with mock.patch.object(ai_review, 'save_auto_receipt', side_effect=OSError('领域回执落盘失败')):
            with self.assertRaises(mcp_server.ToolError):
                self.call()
        row = self.rows()[0]
        self.assertEqual(row['status'], 'failed')
        self.assertIsNone(ai_review._auto_receipt(self.vault, row))
        self.assertEqual(drafts.counts(self.vault)['review'], 0)
        ai_review.initialize(self.vault)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'failed')

    def test_retry_cannot_borrow_receipt_from_original_operation_when_terminal_is_lost(self):
        first_result = mcp_server._review_result(self.call())
        first = self.rows()[0]
        with mock.patch.object(mcp_server, '_review_finish', return_value=None):
            second_result = mcp_server._review_result(self.call())
        self.assertEqual(first_result['draft_id'], second_result['draft_id'])
        self.assertTrue(second_result['reused'])
        second = next(row for row in self.rows() if row['operation_id'] != first['operation_id'])
        self.assertIsNotNone(ai_review._auto_receipt(self.vault, first))
        self.assertIsNone(ai_review._auto_receipt(self.vault, second))
        ai_review.initialize(self.vault)
        self.assertEqual(ai_review.get(self.vault, second['operation_id'])['status'], 'interrupted')
        self.assertEqual(drafts.counts(self.vault)['review'], 1)


if __name__ == '__main__':
    unittest.main()
