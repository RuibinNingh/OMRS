"""MCP 正式调度、旧审批与只读恢复边界；所有业务在临时 Vault。"""
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from unittest.mock import patch

from omrs import ai_review, mcp_operations as ops
from omrs.creation import create_question
from omrs.ledger import read_commits
from omrs.mcp.keys import create_key, revoke_key
from omrs.question_ops import get_question_raw, save_question_markdown


class McpReviewApprovalTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='omrs-mcp-review-')
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.question = create_question(self.vault, '数学', '确认', 5, question_text='原题')
        self.key = create_key(self.vault, '调度审批', ['omrs:read', 'session:create'])

    def propose(self, request='request'):
        return ops.create_session(self.vault,
            [{'question_id': self.question['question_id'], 'source': 'due'}],
            self.key['key_id'], request, 'https://omrs.example',
            lambda: ops._session_auth(self.vault, self.key['key_id']))

    def test_create_requires_review_and_rejection_never_creates_session(self):
        pending = self.propose()
        self.assertEqual(pending['status'], 'pending_confirmation')
        self.assertNotIn('session_id', pending)
        self.assertFalse(any(c['commit_type'] == 'session.create' for c in read_commits(self.vault)))
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'reject')['status'], 'rejected')
        self.assertEqual(self.propose()['status'], 'rejected')
        self.assertFalse(any(c['commit_type'] == 'session.create' for c in read_commits(self.vault)))

    def test_revocation_and_changed_content_stop_unexecuted_approval(self):
        pending = self.propose('changed')
        old = get_question_raw(self.vault, self.question['uid'])
        save_question_markdown(self.vault, self.question['uid'], old['markdown'].replace('原题', '网页更新'))
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['error_code'], 'revision_conflict')
        pending = self.propose('revoked')
        revoke_key(self.vault, self.key['key_id'])
        self.assertEqual(ops.decide(self.vault, pending['operation_id'], 'confirm')['error_code'], 'forbidden')
        self.assertFalse(any(c['commit_type'] == 'session.create' for c in read_commits(self.vault)))

    def test_deadline_crossed_during_approval_preview_stops_actual_session_write(self):
        pending = self.propose()
        row = ai_review.get(self.vault, pending['operation_id'])
        current = [time.time()]
        original = ops.session_preview
        def slow_preview(*args, **kwargs):
            result = original(*args, **kwargs)
            current[0] = row['expires_at']+1
            return result
        with patch('omrs.mcp_operations.time.time', side_effect=lambda: current[0]), \
                patch.object(ops, 'session_preview', side_effect=slow_preview):
            result = ops.decide(self.vault, pending['operation_id'], 'confirm')
        self.assertEqual(result['status'], 'expired')
        self.assertFalse(any(c['commit_type'] == 'session.create' for c in read_commits(self.vault)))

    def test_get_uses_native_receipt_without_writing_state_or_replaying(self):
        pending = self.propose()
        original = ops._save_state
        def fail_completion(vault, row, status, *args, **kwargs):
            if status == 'applied':
                raise sqlite3.OperationalError('模拟辅助数据库不可写')
            return original(vault, row, status, *args, **kwargs)
        with patch.object(ops, '_save_state', side_effect=fail_completion):
            applied = ops.decide(self.vault, pending['operation_id'], 'confirm')
        self.assertEqual(applied['status'], 'applied')
        self.assertEqual(ai_review.get(self.vault, pending['operation_id'])['status'], 'applying')
        before = read_commits(self.vault)
        with patch.object(ai_review, 'set_state', side_effect=AssertionError('GET 不能写状态')):
            current = ops.get(self.vault, pending['operation_id'])
        self.assertEqual(current['status'], 'applied')
        self.assertEqual(read_commits(self.vault), before)
        ops.refresh(self.vault)
        self.assertEqual(ai_review.get(self.vault, pending['operation_id'])['status'], 'applied')

    def legacy(self):
        operation_id = 'op_'+'b'*32
        with closing(ops._connect(self.vault, True)) as db:
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (operation_id, 'legacy-request', self.key['key_id'], 'delete_board', 'legacy-digest',
                 json.dumps({'board_id': 'legacy-board'}), '{}', 'legacy-snapshot',
                 'pending_confirmation', time.time(), time.time()+600, '{}', ''))
            db.commit()
        return operation_id

    def test_legacy_get_is_readonly_and_upgrade_never_revives_approval(self):
        operation_id = self.legacy()
        with patch.object(ai_review, 'create', side_effect=AssertionError('GET 不能迁移旧审批')):
            old = ops.get(self.vault, operation_id)
        self.assertEqual(old['status'], 'interrupted')
        self.assertTrue(old['history_readonly'])
        ops.refresh(self.vault)
        imported = ai_review.get(self.vault, operation_id)
        self.assertTrue(imported['history_readonly'])
        self.assertEqual(imported['status'], 'interrupted')
        self.assertEqual(ops.decide(self.vault, operation_id, 'confirm')['status'], 'interrupted')

    def test_vault_invalidation_closes_old_and_new_pending(self):
        legacy_id = self.legacy()
        pending = self.propose()
        ops.invalidate(self.vault)
        with closing(ops._connect(self.vault)) as db:
            old = db.execute('SELECT status,error_code FROM operations WHERE operation_id=?', (legacy_id,)).fetchone()
        self.assertEqual(tuple(old), ('conflict', 'vault_changed'))
        self.assertEqual(ai_review.get(self.vault, pending['operation_id'])['status'], 'interrupted')
        self.assertFalse(any(c['commit_type'] == 'session.create' for c in read_commits(self.vault)))


if __name__ == '__main__':
    unittest.main()
