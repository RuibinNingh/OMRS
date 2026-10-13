"""三种对话权限、长期送审、独立执行与并发；全部使用临时 Vault。"""
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from omrs import ai_review
from omrs.common import save_config
from omrs.creation import create_question
from omrs.ledger import read_commits
from omrs.question_ops import get_question_raw, save_question_markdown
from omrs.vault_lifecycle import advance_generation
from omrs.agent import runtime
from omrs.agent.tools import build_registry


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='omrs-permission-')
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        save_config(self.vault, {'agent_enabled': True})
        self.q = create_question(self.vault, '数学', '权限', 5, question_text='原题', answer_text='原答案')
        self.rt = runtime.get_runtime(self.vault)
        self.addCleanup(lambda: runtime._RUNTIMES.pop(os.path.abspath(self.vault), None))
        self.conv = self.rt.create_conversation()['id']
        self.run = runtime.Run('run_permission', self.conv, 'faux', self.rt.store)
        self.rt.store.create_run(self.run.id, self.conv, 'faux')
        self.rt.runs[self.run.id] = self.run
        self.registry = build_registry()
        self.hooks = runtime.Hooks(self.rt, self.run, self.registry)
        self.tool = self.registry.get('update_question_section')
        self.call = {'id': 'call_permission', 'name': self.tool.name,
                     'args': {'uid': self.q['uid'], 'section': '答案', 'content': '新答案'}}

    def mode(self, mode):
        return self.rt.set_permission_mode(self.conv, mode, {'kind': 'web', 'access': 'direct', 'client_ip': '127.0.0.1'})

    def proposal(self):
        verdict = self.hooks.before_tool_call(self.call, self.tool)
        row = ai_review.by_identity(self.vault, runtime._review_identity(self.run.id, self.call['id']))
        return verdict, row

    def end_run(self):
        self.rt.store.save_run(self.run.id, status='done', stats=runtime.run_stats(self.run.statistics), ended=True)
        self.run.done = True
        self.rt.runs.pop(self.run.id, None)

    def commits(self):
        return [c for c in read_commits(self.vault) if c['payload'].get('_agent', {}).get('run_id') == self.run.id]

    def waiting(self):
        results = []
        thread = threading.Thread(target=lambda: results.append(self.proposal()), daemon=True)
        thread.start()
        with self.run.cond:
            self.assertTrue(self.run.cond.wait_for(lambda: self.run.pending, timeout=3))
        pc = self.run.pending[self.call['id']]
        self.addCleanup(lambda: pc.close('abort'))
        self.addCleanup(lambda: thread.join(3))
        return thread, results, ai_review.get(self.vault, pc.operation_id)

    def test_default_and_mode_are_durable_and_new_conversation_resets(self):
        self.assertEqual(self.rt.store.conversation(self.conv)['permission_mode'], 'manual')
        self.mode('danger')
        self.assertEqual(runtime.AgentRuntime(self.vault).store.conversation(self.conv)['permission_mode'], 'danger')
        self.assertEqual(self.rt.create_conversation()['permission_mode'], 'manual')
        with self.assertRaises(runtime.AgentError):
            self.mode('invalid')

    def test_hold_continues_then_center_edits_and_applies_without_model(self):
        self.mode('hold')
        verdict, row = self.proposal()
        self.assertEqual(verdict['status'], 'deferred')
        self.assertFalse(verdict['result']['executed'])
        self.assertIsNone(row['expires_at'])
        self.assertEqual(len(self.commits()), 0)
        self.end_run()
        revised = ai_review.update(self.vault, row['operation_id'], 1, {'answer_text': '审核答案'})
        self.assertEqual(revised['revision'], 2)
        self.assertIsNone(revised['expires_at'])
        with self.assertRaises(ai_review.ReviewError):
            ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        final = ai_review.decide(self.vault, row['operation_id'], 2, 'approve', {'kind': 'web'})
        self.assertEqual(final['status'], 'applied')
        self.assertEqual(final['result']['after'], '审核答案')
        self.assertEqual(len(self.commits()), 1)
        saved = self.rt.store.run(self.run.id)
        self.assertEqual(saved['stats']['writes'], 1)
        self.assertEqual(saved['stats']['commits'], final['commits'])
        self.assertEqual(self.rt.store.event_page(self.run.id)['events'][-1]['type'], 'tool.reviewed')

    def test_manual_timeout_transfers_instead_of_expiring(self):
        with patch.object(runtime, 'CONFIRM_TTL_SECONDS', 0.03):
            verdict, row = self.proposal()
        self.assertEqual(verdict['status'], 'deferred')
        self.assertEqual((row['status'], row['permission']['reason']), ('pending_confirmation', 'timeout'))
        self.end_run()
        self.assertEqual(ai_review.decide(self.vault, row['operation_id'], 1, 'approve')['status'], 'applied')

    def test_manual_send_and_change_to_hold_release_wait(self):
        thread, results, row = self.waiting()
        self.mode('hold')
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0][0]['status'], 'deferred')
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['permission']['reason'], 'mode_change')
        self.mode('manual')
        self.assertIsNone(ai_review.get(self.vault, row['operation_id'])['expires_at'])
        self.assertEqual(ai_review.decide(self.vault, row['operation_id'], 1, 'reject')['status'], 'rejected')
        self.assertEqual(len(self.commits()), 0)

    def test_defer_endpoint_is_idempotent_and_releases_wait(self):
        thread, results, row = self.waiting()
        self.rt.defer_review(row['operation_id'], 1)
        self.rt.defer_review(row['operation_id'], 1)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0][0]['status'], 'deferred')
        self.assertEqual(len(self.commits()), 0)

    def test_center_approval_before_timeout_cleanup_keeps_actual_receipt(self):
        timed_out, release = threading.Event(), threading.Event()
        original_wait = runtime.PendingConfirm.wait
        def delayed_cleanup(pc, abort):
            decision = original_wait(pc, abort)
            timed_out.set()
            release.wait(3)
            return decision
        self.addCleanup(release.set)
        with patch.object(runtime, 'CONFIRM_TTL_SECONDS', 0.05), \
                patch.object(runtime.PendingConfirm, 'wait', delayed_cleanup):
            thread, results, row = self.waiting()
            self.assertTrue(timed_out.wait(3))
            self.rt.defer_review(row['operation_id'], row['revision'])
            final = ai_review.decide(self.vault, row['operation_id'], row['revision'], 'approve')
            self.assertEqual(final['status'], 'applied')
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0][0]['status'], 'deferred')
        self.assertFalse(results[0][0]['result']['pending_review'])
        self.assertTrue(results[0][0]['result']['executed'])
        saved = self.rt.store._all('SELECT status,commits_json FROM tool_calls WHERE run_id=? AND call_id=?',
                                   (self.run.id, self.call['id']))[0]
        self.assertEqual(saved['status'], 'done')
        self.assertNotEqual(saved['commits_json'], '[]')
        self.assertEqual(len(self.commits()), 1)

    def test_danger_records_automatic_approval_before_actual_write(self):
        self.mode('danger')
        verdict, row = self.proposal()
        self.assertIsNone(verdict)
        self.assertEqual(row['status'], 'approved')
        self.assertEqual(len(self.commits()), 0)
        decision = ai_review.detail(self.vault, row['operation_id'])['decision']
        self.assertEqual(decision['actor']['kind'], 'permission_mode')
        self.assertEqual(decision['actor']['selected_by']['client_ip'], '127.0.0.1')
        out = self.hooks.execute(self.call, self.tool)
        self.hooks.after_tool_call(self.call, self.tool, out)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'applied')
        self.mode('hold')
        self.assertEqual(ai_review.detail(self.vault, row['operation_id'])['decision'], decision)

    def test_danger_approves_already_deferred_request(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        self.mode('danger')
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'applied')
        self.assertEqual(len(self.commits()), 1)

    def test_center_survives_restart_and_conflicts_with_changed_target(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        runtime._RUNTIMES.pop(os.path.abspath(self.vault))
        runtime.get_runtime(self.vault)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'pending_confirmation')
        old = get_question_raw(self.vault, self.q['uid'])
        save_question_markdown(self.vault, self.q['uid'], old['markdown'].replace('原答案', '外部答案'))
        self.assertEqual(ai_review.decide(self.vault, row['operation_id'], 1, 'approve')['status'], 'conflict')
        self.assertEqual(len(self.commits()), 0)

    def test_ordinary_restart_allows_center_execution_and_rejects_duplicate(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        runtime._RUNTIMES.pop(os.path.abspath(self.vault))
        ai_review.initialize(self.vault)
        self.assertEqual(ai_review.get(self.vault, row['operation_id'])['status'], 'pending_confirmation')
        runtime.get_runtime(self.vault)
        barrier = threading.Barrier(3)
        results = []
        def approve():
            barrier.wait()
            results.append(ai_review.decide(self.vault, row['operation_id'], 1, 'approve'))
        workers = [threading.Thread(target=approve) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual([r['status'] for r in results], ['applied', 'applied'])
        self.assertEqual(len(self.commits()), 1)

    def test_vault_restore_invalidates_center_permit(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        advance_generation(self.vault)
        ai_review.invalidate(self.vault)
        self.assertEqual(ai_review.decide(self.vault, row['operation_id'], 1, 'approve')['status'], 'interrupted')
        self.assertEqual(len(self.commits()), 0)

    def test_center_disabled_assistant_cannot_apply(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        save_config(self.vault, {'agent_enabled': False})
        final = ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertEqual((final['status'], final['error_code']), ('conflict', 'forbidden'))
        self.assertEqual(len(self.commits()), 0)

    def test_abort_cannot_be_turned_into_center_execution_by_late_click(self):
        thread, _, row = self.waiting()
        self.run.abort.set()
        final = ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertEqual(final['status'], 'cancelled')
        thread.join(3)
        self.assertEqual(len(self.commits()), 0)

    def test_abort_before_mode_transfer_cancels_chat_request(self):
        entered, release = threading.Event(), threading.Event()
        original_wait = runtime.PendingConfirm.wait
        def paused_wait(pc, abort):
            entered.set()
            release.wait(3)
            return original_wait(pc, abort)
        self.addCleanup(release.set)
        with patch.object(runtime.PendingConfirm, 'wait', paused_wait):
            thread, _, row = self.waiting()
            self.assertTrue(entered.wait(3))
            self.run.abort.set()
            self.mode('hold')
            final = ai_review.get(self.vault, row['operation_id'])
            self.assertEqual(final['status'], 'cancelled')
            self.assertEqual(final['permission']['channel'], 'chat')
            self.assertEqual(ai_review.decide(self.vault, row['operation_id'], 1, 'approve')['status'], 'cancelled')
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.commits()), 0)

    def test_deleted_conversation_cannot_apply_center_request(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        self.rt.delete_conversation(self.conv)
        final = ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertEqual(final['status'], 'conflict')
        self.assertEqual(len(self.commits()), 0)

    def test_applying_flag_alone_does_not_grant_center_write(self):
        self.mode('hold')
        _, row = self.proposal()
        self.end_run()
        row = ai_review.set_state(self.vault, row['operation_id'], 'applying')
        from omrs.actor import agent_actor
        with agent_actor(self.conv, self.run.id, self.call['id']):
            with self.assertRaises(ai_review.ReviewError):
                ai_review.verify_question_write(self.vault, row)
        self.assertEqual(len(self.commits()), 0)

    def test_center_whole_label_plan_keeps_original_actor_and_can_be_undone(self):
        from omrs.label_plan_prepare import stage
        from omrs.labels import load_labels
        from omrs.agent.revert import apply_revert
        self.mode('hold')
        staged = stage(self.vault, 'agent', self.conv, 'labels', {
            'label_changes': [{'action': 'create', 'key': 'n', 'name': '新标记'}]})
        self.tool = self.registry.get('propose_label_plan')
        self.call = {'id': 'call_labels', 'name': self.tool.name,
                     'args': {'plan_id': staged['plan_id'], 'expected_version': 1}}
        _, row = self.proposal()
        self.end_run()
        final = ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertEqual(final['status'], 'applied')
        self.assertEqual(load_labels(self.vault)['labels'][0]['name'], '新标记')
        self.assertEqual(len(self.commits()), 1)
        self.assertTrue(apply_revert(self.vault, self.run.id)['ok'])
        self.assertFalse(load_labels(self.vault)['labels'])

    def test_center_draft_uses_fixed_revision_and_configuration(self):
        from omrs.agent.tools.drafts import create_draft_tool
        from tests.test_agent_draft_tools import TEXT_ARGS
        save_config(self.vault, {'agent_enabled': True, 'draft_mode': 'confirm', 'draft_crop_mode': 'manual'})
        self.mode('hold')
        draft = create_draft_tool(self.hooks.ctx, TEXT_ARGS)['result']
        self.registry = build_registry({'draft_mode': 'confirm'})
        self.hooks.registry = self.registry
        self.tool = self.registry.get('commit_draft')
        self.call = {'id': 'call_draft', 'name': self.tool.name,
                     'args': {'draft_id': draft['draft_id'], 'revision': draft['revision']}}
        _, row = self.proposal()
        self.end_run()
        final = ai_review.decide(self.vault, row['operation_id'], 1, 'approve')
        self.assertEqual(final['status'], 'applied')
        self.assertEqual(len(self.commits()), 1)

    def test_elapsed_manual_draft_remains_one_pending_item_before_transfer(self):
        from omrs.agent.tools.drafts import create_draft_tool
        from tests.test_agent_draft_tools import TEXT_ARGS
        draft = create_draft_tool(self.hooks.ctx, TEXT_ARGS)['result']
        row = ai_review.create(self.vault, 'agent', 'commit_draft', 'manual-draft',
                               {'draft_id': draft['draft_id'], 'revision': draft['revision']},
                               actor={'conversation_id': self.conv, 'run_id': self.run.id,
                                      'tool_call_id': 'manual-draft'})
        row = ai_review.prepare(self.vault, row['operation_id'], expires_at=time.time()-1,
                                permission={'mode': 'manual', 'channel': 'chat'})
        page = ai_review.items(self.vault)
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['items'][0]['id'], row['operation_id'])
        self.assertEqual(page['items'][0]['status'], 'pending_confirmation')
        self.assertEqual(ai_review.counts(self.vault), {'pending': 1, 'drafts': 0, 'operations': 1})


if __name__ == '__main__':
    unittest.main()
