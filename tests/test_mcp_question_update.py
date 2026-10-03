"""官方 SDK 与真实隔离 MCP 服务验证改题提案、权限及人工有效补丁。"""
import asyncio
import unittest

from omrs import ai_review, content_history, ledger
from omrs.mcp.keys import create_key, revoke_key
from tests.test_mcp_protocol import MCPServerProcess, _session, _json_result


class MCPQuestionUpdateSDKTests(unittest.TestCase):
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

    def test_permission_is_hidden_by_default_and_requires_both_scopes(self):
        async def run():
            keys = [self.server.keys['all'], create_key(self.server.vault, scopes=['question:propose']),
                    create_key(self.server.vault, scopes=['omrs:read', 'question:propose'])]
            for key, visible in zip(keys, (False, False, True)):
                async with _session(self.server.mcp_port, key['secret']) as session:
                    tools = {tool.name for tool in (await session.list_tools()).tools}
                    self.assertEqual('propose_question_update' in tools, visible)
                    if not visible:
                        result = await session.call_tool('propose_question_update', {})
                        self.assertTrue(result.isError)
        asyncio.run(run())

    def test_sdk_proposal_is_readonly_until_revised_web_approval_and_retry_reuses(self):
        key = create_key(self.server.vault, scopes=['omrs:read', 'question:propose'])
        async def run():
            async with _session(self.server.mcp_port, key['secret']) as session:
                read = _json_result(await session.call_tool('get_question', {'uid': '函数1'}))
                self.assertIn('question_id', read)
                self.assertIn('difficulty', read)
                self.assertIn('note', read)
                row = content_history.projection_row(self.server.vault, uid='函数1')
                before = content_history.read_question_file(self.server.vault, row)
                count = len(ledger.read_commits(self.server.vault))
                args = {'uid': '函数1', 'question_id': read['question_id'], 'expected_content_hash': read['content_hash'],
                        'patch': {'answer_text': '模型建议答案'}, 'request_id': 'sdk-edit-retry', 'reason': '修正答案'}
                first = await session.call_tool('propose_question_update', args)
                self.assertFalse(first.isError)
                operation = _json_result(first)
                self.assertEqual(operation['status'], 'pending_confirmation')
                self.assertIn('/#/ai-review?operation=', operation['confirmation_url'])
                self.assertEqual(content_history.read_question_file(self.server.vault, row), before)
                self.assertEqual(len(ledger.read_commits(self.server.vault)), count)
                revised = ai_review.update(self.server.vault, operation['operation_id'], 1, {'answer_text': '人工修订答案'})
                self.assertEqual(revised['revision'], 2)
                retry = _json_result(await session.call_tool('propose_question_update', args))
                self.assertTrue(retry['reused'])
                self.assertEqual(retry['payload']['patch']['answer_text'], '人工修订答案')
                with self.assertRaises(ai_review.ReviewError):
                    ai_review.decide(self.server.vault, operation['operation_id'], 1, 'approve')
                approved = ai_review.decide(self.server.vault, operation['operation_id'], 2, 'approve')
                self.assertEqual(approved['status'], 'applied')
                self.assertIn('人工修订答案', content_history.read_question_file(self.server.vault, row))
                self.assertNotIn('模型建议答案', content_history.read_question_file(self.server.vault, row))
                count = len(ledger.read_commits(self.server.vault))
                again = _json_result(await session.call_tool('propose_question_update', args))
                self.assertEqual(again['operation_id'], operation['operation_id'])
                self.assertEqual(again['status'], 'applied')
                self.assertEqual(len(ledger.read_commits(self.server.vault)), count)
                self.assertTrue(ledger.verify_ledger(self.server.vault)['valid'])
        asyncio.run(run())

    def test_revoke_before_approval_and_unsafe_patch_leave_official_question_unchanged(self):
        key = create_key(self.server.vault, scopes=['omrs:read', 'question:propose'])
        async def run():
            async with _session(self.server.mcp_port, key['secret']) as session:
                read = _json_result(await session.call_tool('get_question', {'uid': '力学1'}))
                args = {'uid': '力学1', 'question_id': read['question_id'], 'expected_content_hash': read['content_hash'],
                        'patch': {'question_text': '被吊销的建议'}, 'request_id': 'sdk-edit-revoked', 'reason': '修正题干'}
                for reason in (None, '', '   ', 'x' * 2001):
                    invalid = {**args, 'reason': reason}
                    if reason is None:
                        invalid.pop('reason')
                    self.assertTrue((await session.call_tool('propose_question_update', invalid)).isError)
                for patch in ({'difficulty': True}, {'difficulty': 1.5}, {'cause': '## 关联\n覆盖'},
                              {'question_text': '![外链](https://example.com/image.png)'},
                              {'knowledge_points': ['a\nb']}, {'tags': ['状态/已击杀']}):
                    result = await session.call_tool('propose_question_update', {**args, 'patch': patch})
                    self.assertTrue(result.isError, patch)
                result = _json_result(await session.call_tool('propose_question_update', args))
                row = content_history.projection_row(self.server.vault, uid='力学1')
                before = content_history.read_question_file(self.server.vault, row)
                revoke_key(self.server.vault, key['key_id'])
                decided = ai_review.decide(self.server.vault, result['operation_id'], 1, 'approve')
                self.assertEqual(decided['status'], 'conflict')
                self.assertEqual(decided['error_code'], 'forbidden')
                self.assertEqual(content_history.read_question_file(self.server.vault, row), before)
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
