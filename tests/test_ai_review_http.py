"""真实隔离 Web 服务验证审核的身份边界、CAS 与只读查询。"""
import json
from pathlib import Path
import sqlite3
import time
import unittest
import urllib.error
import urllib.request
import uuid

from omrs import ai_review, content_history, ledger
from omrs.creation import create_question
from omrs.mcp.keys import create_key
from omrs.mcp.question_write import propose
from tests.test_mcp_protocol import MCPServerProcess


class AiReviewHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServerProcess()
        try:
            cls.server.start()
            deadline = time.monotonic()+10
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{cls.server.web_port}/api/auth/session', timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline or cls.server.process.poll() is not None:
                        raise
                    time.sleep(.05)
        except BaseException:
            cls.server.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.vault = self.server.vault
        self.base = f'http://127.0.0.1:{self.server.web_port}'
        self.question = create_question(self.vault, '数学', 'HTTP审核'+uuid.uuid4().hex[:6], 5,
                                        question_text='审核前题干', answer_text='审核前答案')
        self.key = create_key(self.vault, 'HTTP审核来源', ['omrs:read', 'question:propose'])
        row = content_history.projection_row(self.vault, uid=self.question['uid'])
        self.before = content_history.read_question_file(self.vault, row)
        self.operation = propose(self.vault, self.key['key_id'], 'http-proposal', self.question['uid'],
            self.question['question_id'], ledger.blob_hash(self.before), {'answer_text': '模型答案'}, reason='修正遗漏')

    def request(self, path, body=None, headers=None):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        request = urllib.request.Request(self.base+path, data=data,
            headers={'Content-Type': 'application/json', 'Origin': self.base, **(headers or {})})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def content(self):
        row = content_history.projection_row(self.vault, uid=self.question['uid'])
        return content_history.read_question_file(self.vault, row)

    def test_queries_and_pagination_never_apply_pending_or_approved_operations(self):
        operation_id = self.operation['operation_id']
        ai_review.set_state(self.vault, operation_id, 'approved')
        count = len(ledger.read_commits(self.vault))
        for path in ('/api/ai-review/items?view=records&limit=1&cursor=0',
                     '/api/ai-review/detail?id='+operation_id, '/api/ai-review/counts'):
            status, result = self.request(path)
            self.assertEqual(status, 200, result)
            self.assertEqual(result['status'], 'ok')
        self.assertEqual(ai_review.get(self.vault, operation_id)['status'], 'approved')
        self.assertEqual(self.content(), self.before)
        self.assertEqual(len(ledger.read_commits(self.vault)), count)

    def test_bearer_and_mcp_header_cannot_reach_any_web_review_route(self):
        operation_id = self.operation['operation_id']
        for credentials in ({'Authorization': 'Bearer '+self.key['secret']},
                            {'X-OMRS-MCP-Key': self.key['secret']}):
            headers = {**credentials, 'Cookie': 'omrs_session=pretend-local-session'}
            for path, body in (
                ('/api/ai-review/items', None), ('/api/ai-review/counts', None),
                ('/api/ai-review/detail?id='+operation_id, None),
                ('/api/ai-review/update', {'id': operation_id, 'expected_revision': 1, 'patch': {'answer_text': '越权'}}),
                ('/api/ai-review/decide', {'id': operation_id, 'expected_revision': 1, 'decision': 'approve'})):
                with self.subTest(headers=list(credentials), path=path):
                    status, result = self.request(path, body, headers)
                    self.assertEqual(status, 403, result)
                    self.assertEqual(result['code'], 'mcp_boundary')
        self.assertEqual(ai_review.get(self.vault, operation_id)['status'], 'pending_confirmation')
        self.assertEqual(self.content(), self.before)

    def test_empty_native_draft_database_during_first_connection_does_not_return_503(self):
        target = Path(ai_review._draft_path(self.vault))
        self.assertFalse(target.exists())
        target.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(target).close()
        before = target.read_bytes()
        for path in ('/api/ai-review/counts', '/api/ai-review/items'):
            status, result = self.request(path)
            self.assertEqual(status, 200, result)
            self.assertEqual(result['status'], 'ok')
        self.assertEqual(target.read_bytes(), before)

    def test_http_revision_types_stale_approval_and_server_owned_actor(self):
        operation_id = self.operation['operation_id']
        for revision in (True, '1', 0, None):
            status, result = self.request('/api/ai-review/decide',
                {'id': operation_id, 'expected_revision': revision, 'decision': 'approve'})
            self.assertEqual(status, 400, result)
            self.assertEqual(result['code'], 'invalid_request')
        status, revised = self.request('/api/ai-review/update',
            {'id': operation_id, 'expected_revision': 1, 'patch': {'answer_text': '人工答案'}})
        self.assertEqual(status, 200, revised)
        self.assertEqual(revised['item']['revision'], 2)
        self.assertEqual(revised['item']['actor']['key_id'], self.key['key_id'])
        self.assertEqual(revised['item']['payload']['reason'], '修正遗漏')
        status, result = self.request('/api/ai-review/decide',
            {'id': operation_id, 'expected_revision': 1, 'decision': 'approve'})
        self.assertEqual(status, 409, result)
        self.assertEqual(result['code'], 'revision_conflict')
        self.assertEqual(self.content(), self.before)
        status, approved = self.request('/api/ai-review/decide',
            {'id': operation_id, 'expected_revision': 2, 'decision': 'approve'})
        self.assertEqual(status, 200, approved)
        self.assertEqual(approved['item']['status'], 'applied')
        self.assertIn('人工答案', self.content())
        detail = self.request('/api/ai-review/detail?id='+operation_id)[1]['item']
        self.assertEqual(detail['decision']['actor'], {'kind': 'web', 'access': 'direct', 'client_ip': '127.0.0.1'})

    def test_request_body_cannot_inject_source_decider_identity_or_reason(self):
        operation_id = self.operation['operation_id']
        for injected in ({'actor': {'key_id': 'other'}}, {'source': 'agent'}, {'reviewer': {'kind': 'admin'}}):
            status, result = self.request('/api/ai-review/decide',
                {'id': operation_id, 'expected_revision': 1, 'decision': 'approve', **injected})
            self.assertEqual(status, 400, result)
            self.assertEqual(result['code'], 'invalid_request')
        status, result = self.request('/api/ai-review/update',
            {'id': operation_id, 'expected_revision': 1, 'patch': {'reason': '不能篡改原理由'}})
        self.assertEqual(status, 403, result)
        self.assertEqual(result['code'], 'forbidden')
        self.assertEqual(ai_review.get(self.vault, operation_id)['revision'], 1)
        self.assertEqual(self.content(), self.before)


if __name__ == '__main__':
    unittest.main()
