"""正式调度 MCP 协议、权限、重试与查询闭环；只用临时 Vault。"""
import asyncio
import unittest
import json
import urllib.request

from omrs.creation import create_question
from omrs.feedback import process_feedback
from omrs.ledger import read_commits
from omrs.ledger import blob_hash
from omrs.question_ops import get_question_raw
from omrs.mcp.keys import create_key, revoke_key, _SCOPES
from omrs.sessions import delete_session
from test_mcp_protocol import MCPServerProcess, MCP_AVAILABLE, _session, _json_result


@unittest.skipUnless(MCP_AVAILABLE, '真实 MCP SDK 未安装')
class ReviewSessionProtocolTests(unittest.TestCase):
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

    def questions(self, category, count=2):
        return [create_question(self.server.vault, '数学', category, 5,
                                question_text='协议调度题', answer_text='答案') for _ in range(count)]

    def key(self, scopes=None):
        return create_key(self.server.vault, '调度协议', scopes or ['omrs:read', 'session:create'])

    def approve(self, pending):
        self.assertEqual(pending['status'], 'pending_confirmation')
        self.assertNotIn('session_id', pending)
        request = urllib.request.Request(
            f'http://127.0.0.1:{self.server.web_port}/api/ai-review/decide',
            data=json.dumps({'operation_id': pending['operation_id'], 'expected_revision': pending['revision'],
                             'decision': 'approve'}).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request) as response:
            applied = json.load(response)['item']
        self.assertEqual(applied['status'], 'applied')
        return applied['result']

    def test_recommendation_creation_and_partial_feedback_queries(self):
        self.questions('闭环')
        key = self.key()
        async def run():
            async with _session(self.server.mcp_port, key['secret']) as client:
                async def call(name, args):
                    result = await client.call_tool(name, args)
                    self.assertFalse(result.isError, str(result))
                    return _json_result(result)
                recommendations = await call('get_recommendations', {'category': '闭环', 'count': 2})
                selected = recommendations['selection']
                self.assertEqual(len(selected), 2)
                self.assertTrue(all(item['question_id'] for item in selected))
                pending = await call('create_review_session', {'items': selected, 'request_id': 'sdk-roundtrip'})
                created = self.approve(pending)
                self.assertTrue(created['session_id'].startswith('EXP-'))
                self.assertEqual(created['pending_count'], 2)
                process_feedback(self.server.vault, [{'question_id': selected[0]['question_id'],
                                                      'sub_score': 5, 'is_correct': True}], created['session_id'])
                detail = (await call('get_session', {'session_id': created['session_id'], 'limit': 1}))
                self.assertEqual((detail['feedback_count'], detail['pending_count']), (1, 1))
                self.assertEqual(detail['status'], 'active')
                self.assertEqual(len(detail['entries']), 1)
                self.assertEqual(detail['next_offset'], 1)
                page2 = (await call('get_session', {'session_id': created['session_id'], 'offset': 1, 'limit': 1}))
                self.assertEqual(page2['entries'][0]['question_id'], selected[1]['question_id'])
                listing = (await call('list_sessions', {'status': 'active', 'limit': 100}))
                listed = next(item for item in listing['sessions'] if item['session_id'] == created['session_id'])
                self.assertEqual((listed['feedback_count'], listed['pending_count']), (1, 1))
                process_feedback(self.server.vault, [{'question_id': selected[1]['question_id'],
                                                      'sub_score': 5, 'is_correct': True}], created['session_id'])
                completed = (await call('get_session', {'session_id': created['session_id']}))
                self.assertEqual(completed['status'], 'completed')
                self.assertTrue(completed['completed_at'])
                self.assertTrue(completed['feedback_complete'])
        asyncio.run(run())

    def test_scope_discovery_defaults_and_strict_schema_do_not_write(self):
        question = self.questions('参数', 1)[0]
        payload = {'items': [{'question_id': question['question_id'], 'source': 'due'}], 'request_id': 'schema'}
        async def run():
            for scopes, expected in ((['omrs:read'], 24), (['session:create'], 0), (list(_SCOPES), 44)):
                key = self.key(scopes)
                async with _session(self.server.mcp_port, key['secret']) as client:
                    tools = (await client.list_tools()).tools
                    self.assertEqual(len(tools), expected)
                    if scopes != list(_SCOPES):
                        self.assertNotIn('create_review_session', [item.name for item in tools])
                        self.assertTrue((await client.call_tool('create_review_session', payload)).isError)
            default_key = create_key(self.server.vault, '默认权限')
            self.assertNotIn('session:create', default_key['scopes'])
            key = self.key()
            before = len(read_commits(self.server.vault))
            async with _session(self.server.mcp_port, key['secret']) as client:
                invalid = [
                    {**payload, 'items': []},
                    {**payload, 'items': payload['items'] * 101},
                    {**payload, 'items': [{'question_id': ' ', 'source': 'due'}]},
                    {**payload, 'items': [{'question_id': question['question_id'], 'source': 'instant'}]},
                    {**payload, 'items': [{'question_id': question['question_id'], 'source': 'due', 'extra': True}]},
                    {**payload, 'request_id': ''},
                    {**payload, 'extra': 'no'},
                ]
                for bad in invalid:
                    self.assertTrue((await client.call_tool('create_review_session', bad)).isError, str(bad))
                for bad in ({'limit': True}, {'limit': 1.0}, {'offset': -1}, {'limit': 101}):
                    self.assertTrue((await client.call_tool('list_sessions', bad)).isError)
                schema = next(item.inputSchema for item in (await client.list_tools()).tools
                              if item.name == 'create_review_session')
                self.assertEqual(schema['$defs']['ReviewSessionItem']['additionalProperties'], False)
            self.assertEqual(len(read_commits(self.server.vault)), before)
        asyncio.run(run())

    def test_concurrent_retries_restart_and_retraction_keep_one_session(self):
        question = self.questions('重试', 1)[0]
        key = self.key()
        payload = {'items': [{'question_id': question['question_id'], 'source': 'proficiency'}],
                   'request_id': 'stable-request'}
        before = len([c for c in read_commits(self.server.vault) if c['commit_type'] == 'session.create'])
        async def create():
            async with _session(self.server.mcp_port, key['secret']) as client:
                results = await asyncio.gather(*(client.call_tool('create_review_session', payload) for _ in range(4)))
                self.assertTrue(all(not result.isError for result in results), str(results))
                values = [_json_result(result) for result in results]
                self.assertEqual(len({v['operation_id'] for v in values}), 1)
                self.assertTrue(all(v['status'] == 'pending_confirmation' for v in values))
                self.assertEqual(len([c for c in read_commits(self.server.vault)
                                      if c['commit_type'] == 'session.create']), before)
                return self.approve(values[0])['session_id']
        sid = asyncio.run(create())
        self.assertEqual(len([c for c in read_commits(self.server.vault) if c['commit_type'] == 'session.create']), before + 1)
        self.server.process.terminate()
        self.server.process.wait(timeout=10)
        self.server._log.close()
        self.server.start()
        async def retry(expected_status):
            async with _session(self.server.mcp_port, key['secret']) as client:
                result = await client.call_tool('create_review_session', payload)
                self.assertFalse(result.isError, str(result))
                value = _json_result(result)
                self.assertEqual((value['session_id'], value['reused'], value['status']), (sid, True, expected_status))
                changed = {**payload, 'items': [{'question_id': question['question_id'], 'source': 'due'}]}
                self.assertTrue((await client.call_tool('create_review_session', changed)).isError)
        asyncio.run(retry('active'))
        delete_session(self.server.vault, sid)
        asyncio.run(retry('retracted'))
        self.assertEqual(len([c for c in read_commits(self.server.vault) if c['commit_type'] == 'session.create']), before + 1)
        revoke_key(self.server.vault, key['key_id'])
        async def denied():
            with self.assertRaises(Exception):
                async with _session(self.server.mcp_port, key['secret']):
                    pass
        asyncio.run(denied())

    def test_legacy_web_approval_cannot_approve_unseen_revised_question(self):
        import urllib.error
        question = self.questions('旧审批版本', 1)[0]
        key = self.key(['omrs:read', 'question:propose'])
        original = get_question_raw(self.server.vault, question['uid'])['markdown']
        async def propose():
            async with _session(self.server.mcp_port, key['secret']) as client:
                reply = await client.call_tool('propose_question_update', {
                    'uid': question['uid'], 'question_id': question['question_id'],
                    'expected_content_hash': blob_hash(original), 'patch': {'answer_text': 'MCP 答案'},
                    'request_id': 'legacy-revised', 'reason': '补充解题过程'})
                self.assertFalse(reply.isError, str(reply))
                return _json_result(reply)
        pending = asyncio.run(propose())
        def post(path, body):
            request = urllib.request.Request(f'http://127.0.0.1:{self.server.web_port}'+path,
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                return json.load(response)
        revised = post('/api/ai-review/update', {'operation_id': pending['operation_id'],
            'expected_revision': 1, 'patch': {'answer_text': '人工修订答案'}})['item']
        self.assertEqual(revised['revision'], 2)
        for revision in (None, 1):
            body = {'operation_id': pending['operation_id'], 'decision': 'confirm'}
            if revision is not None:
                body['expected_revision'] = revision
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post('/api/mcp/operations/decide', body)
            self.assertEqual(caught.exception.code, 409)
            self.assertEqual(json.load(caught.exception)['error'], 'revision_conflict')
            self.assertEqual(get_question_raw(self.server.vault, question['uid'])['markdown'], original)
        final = post('/api/mcp/operations/decide', {'operation_id': pending['operation_id'],
            'expected_revision': 2, 'decision': 'confirm'})['operation']
        self.assertEqual(final['status'], 'applied')
        self.assertIn('人工修订答案', get_question_raw(self.server.vault, question['uid'])['markdown'])


if __name__ == '__main__':
    unittest.main()
