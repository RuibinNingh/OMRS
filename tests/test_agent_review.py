"""助手原运行与审核中心共用审批：版本、竞争、截止和落盘故障；只用临时 Vault。"""
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from omrs import ai_review
from omrs.agent import runtime
from omrs.agent.policy import PendingConfirm
from omrs.agent.tools import build_registry
from omrs.creation import create_question
from omrs.ledger import read_commits
from omrs.question_ops import get_question_raw, save_question_markdown


class AgentReviewTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='omrs-agent-review-')
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.question = create_question(self.vault, '数学', '审核', 5, question_text='原题', answer_text='原答案')
        self.rt = runtime.get_runtime(self.vault)
        self.addCleanup(lambda: runtime._RUNTIMES.pop(os.path.abspath(self.vault), None))
        self.conv = self.rt.create_conversation()['id']
        self.run = runtime.Run('run_review', self.conv, 'faux', self.rt.store)
        self.rt.store.create_run(self.run.id, self.conv, 'faux')
        self.rt.runs[self.run.id] = self.run
        self.registry = build_registry()
        self.hooks = runtime.Hooks(self.rt, self.run, self.registry)
        self.results, self.errors = [], []

    def start(self, tool='update_question_section', args=None, execute=True):
        args = args or {'uid': self.question['uid'], 'section': '答案', 'content': '模型答案'}
        self.call = {'id': 'call_review', 'name': tool, 'args': args}
        self.tool = self.registry.get(tool)
        def worker():
            try:
                verdict = self.hooks.before_tool_call(self.call, self.tool)
                if verdict is None and execute:
                    out = self.hooks.execute(self.call, self.tool)
                    self.hooks.after_tool_call(self.call, self.tool, out)
                    self.results.append(out)
                else:
                    self.results.append(verdict)
            except Exception as exc:
                self.errors.append(exc)
        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        with self.run.cond:
            self.assertTrue(self.run.cond.wait_for(lambda: bool(self.run.pending) or bool(self.errors) or
                                                   bool(self.results), timeout=3))
        self.assertFalse(self.errors, self.errors)
        self.assertTrue(self.run.pending, self.results)
        self.pc = self.run.pending[self.call['id']]
        return ai_review.get(self.vault, self.pc.operation_id)

    def stop(self):
        self.run.abort.set()
        for pc in list(self.run.pending.values()):
            pc.close('abort')
        if hasattr(self, 'thread'):
            self.thread.join(3)

    def finish(self):
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.assertFalse(self.errors, self.errors)

    def test_center_edit_invalidates_old_chat_ticket_and_executes_effective_patch(self):
        row = self.start()
        old_token, deadline = self.pc.token, self.pc.expires_at
        revised = ai_review.update(self.vault, row['operation_id'], 1, {'answer_text': '人工答案'})
        self.assertEqual(revised['digest'], row['digest'])
        self.assertNotEqual(revised['effective_digest'], row['effective_digest'])
        self.assertEqual((revised['revision'], self.pc.revision), (2, 2))
        self.assertEqual((revised['expires_at'], self.pc.expires_at), (row['expires_at'], deadline))
        with self.assertRaises(runtime.AgentError):
            self.rt.confirm(self.run.id, self.call['id'], old_token, 'allow')
        approved = ai_review.decide(self.vault, row['operation_id'], 2, 'approve')
        self.assertEqual(approved['status'], 'approved')
        self.finish()
        final = ai_review.get(self.vault, row['operation_id'])
        self.assertEqual(final['status'], 'applied')
        self.assertEqual(self.results[0]['result']['after'], '人工答案')
        changes = [c for c in read_commits(self.vault) if c['payload'].get('_agent', {}).get('run_id') == self.run.id]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['payload']['_agent']['tool_call_id'], self.call['id'])

    def test_center_and_chat_race_publish_one_business_commit(self):
        row = self.start()
        barrier = threading.Barrier(3)
        decisions = []
        def decide(chat):
            barrier.wait()
            try:
                decisions.append(self.rt.confirm(self.run.id, self.call['id'], self.pc.token, 'allow') if chat else
                    ai_review.decide(self.vault, row['operation_id'], 1, 'approve'))
            except runtime.AgentError as exc:
                decisions.append(exc)
        workers = [threading.Thread(target=decide, args=(chat,)) for chat in (False, True)]
        for thread in workers:
            thread.start()
        barrier.wait()
        for thread in workers:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.finish()
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'applied')
        self.assertEqual(sum(c['payload'].get('_agent', {}).get('run_id') == self.run.id
                             for c in read_commits(self.vault)), 1)

    def test_failed_decision_storage_does_not_wake_original_run(self):
        row = self.start()
        original = ai_review.set_state
        def broken(vault, operation_id, status, *args, **kwargs):
            if status == 'approved':
                raise OSError('模拟批准落盘失败')
            return original(vault, operation_id, status, *args, **kwargs)
        with patch.object(ai_review, 'set_state', side_effect=broken):
            with self.assertRaises(OSError):
                ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertFalse(self.pc.event.is_set())
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'pending_confirmation')
        ai_review.decide(self.vault, row['operation_id'], 1, 'reject')
        self.finish()
        self.assertEqual(self.results[0]['decision'], 'deny')

    def test_changed_target_conflicts_and_original_run_receives_denial(self):
        row = self.start()
        old = get_question_raw(self.vault, self.question['uid'])
        save_question_markdown(self.vault, self.question['uid'], old['markdown'].replace('原答案', '网页答案'))
        result = ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertEqual(result['status'], 'conflict')
        self.finish()
        self.assertEqual(self.results[0]['decision'], 'deny')

    def test_restart_never_resumes_old_model_wait(self):
        row = self.start(execute=False)
        runtime.AgentRuntime(self.vault)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'interrupted')
        self.assertEqual(ai_review.decide(self.vault, row['operation_id'], 1, 'approve')['status'], 'interrupted')
        self.assertFalse(self.pc.event.is_set())

    def test_learning_tools_now_require_confirmation(self):
        levels = self.registry.levels()
        self.assertEqual(levels['create_review_session'], 'confirm')
        self.assertEqual(levels['set_question_labels'], 'confirm')
        row = self.start('create_review_session', {'items': [{'uid': self.question['uid'], 'source': 'due'}]})
        self.assertFalse(any(c['commit_type'] == 'session.create' for c in read_commits(self.vault)))
        self.rt.confirm(self.run.id, self.call['id'], self.pc.token, 'allow')
        self.finish()
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'applied')

    def test_approved_proposal_expiring_before_execution_never_writes(self):
        row = self.start(execute=False)
        ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.finish()
        with patch('omrs.agent.runtime.time.time', return_value=row['expires_at']+1):
            with self.assertRaises(ai_review.ReviewError):
                self.hooks.execute(self.call, self.tool)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'expired')
        self.assertFalse(any(c['payload'].get('_agent', {}).get('run_id') == self.run.id
                             for c in read_commits(self.vault)))


class PendingReviewPolicyTests(unittest.TestCase):
    def test_revision_rotates_ticket_without_extending_deadline(self):
        pending = PendingConfirm('r', 'c', 't', {}, 5, operation_id='op_'+'a'*32, effective_digest='a')
        original, expires = pending.token, pending.expires_at
        pending.revise(2, 'b')
        self.assertNotEqual(pending.token, original)
        self.assertEqual(pending.expires_at, expires)
        with self.assertRaises(ValueError):
            pending.decide(original, 'allow')
        pending.expires_at = time.time()-1
        with self.assertRaises(ValueError):
            pending.revise(3, 'c')


if __name__ == '__main__':
    unittest.main()
