"""调度暂停的持久化、反馈边界、恢复占用与事务回滚；只使用临时 Vault。"""
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from omrs.creation import create_question
from omrs.data_repository import history_rows, mastery_rows
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, read_commits
from omrs.projection_runtime import invalidate
from omrs.projections import rebuild_projection
from omrs.server import OMRSHandler
from omrs.session_operations import create_mcp_session, set_session_paused
from omrs.sessions import active_session_uids, create_session_from_selection, delete_session, get_session, list_sessions


class SessionPauseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.addCleanup(invalidate, self.vault)
        self.questions = [create_question(self.vault, '数学', category, 5, question_text='求 1+1', answer_text='2')
                          for category in ('代数', '几何')]
        self.selected = [{'question_id': q['question_id'], 'source': 'due'} for q in self.questions]
        self.session = create_session_from_selection(self.vault, self.selected)
        self.sid = self.session['session_id']

    def feedback(self, index):
        return process_feedback(self.vault, [{'question_id': self.questions[index]['question_id'],
                                             'is_correct': True, 'sub_score': 5}], self.sid)

    def test_partial_progress_and_learning_survive_pause_replay_and_resume(self):
        self.feedback(0)
        before = get_session(self.vault, self.sid)
        learning, history = mastery_rows(self.vault), history_rows(self.vault)
        paused = set_session_paused(self.vault, self.sid, True)
        self.assertEqual(paused['status'], 'paused')
        self.assertEqual(paused['entries'], before['entries'])
        self.assertEqual(paused['feedback_count'], 1)
        self.assertEqual(paused['pending_count'], 1)
        self.assertEqual(list_sessions(self.vault, 'active'), [])
        self.assertEqual(list_sessions(self.vault, 'paused')[0]['session_id'], self.sid)
        self.assertFalse(active_session_uids(self.vault))
        invalidate(self.vault)
        rebuild_projection(self.vault, force=True)
        self.assertEqual(get_session(self.vault, self.sid)['status'], 'paused')
        self.assertEqual(mastery_rows(self.vault), learning)
        self.assertEqual(history_rows(self.vault), history)
        resumed = set_session_paused(self.vault, self.sid, False)
        self.assertEqual(resumed['status'], 'active')
        self.assertEqual(resumed['entries'], before['entries'])
        self.feedback(1)
        self.assertEqual(get_session(self.vault, self.sid)['status'], 'completed')

    def test_paused_feedback_is_rejected_without_writes(self):
        set_session_paused(self.vault, self.sid, True)
        before = read_commits(self.vault)
        with self.assertRaisesRegex(ValueError, '已暂停'):
            self.feedback(0)
        self.assertEqual(read_commits(self.vault), before)
        self.assertEqual(history_rows(self.vault), [])

    def test_pause_releases_questions_and_resume_conflict_does_not_write(self):
        set_session_paused(self.vault, self.sid, True)
        other = create_session_from_selection(self.vault, self.selected[:1])
        before = read_commits(self.vault)
        with self.assertRaisesRegex(ValueError, other['session_id']):
            set_session_paused(self.vault, self.sid, False)
        self.assertEqual(read_commits(self.vault), before)
        self.assertEqual(get_session(self.vault, self.sid)['status'], 'paused')
        set_session_paused(self.vault, other['session_id'], True)
        self.assertEqual(set_session_paused(self.vault, self.sid, False)['status'], 'active')

    def test_repeated_pause_and_resume_are_idempotent(self):
        for paused in (True, False):
            set_session_paused(self.vault, self.sid, paused)
            count = len(read_commits(self.vault))
            set_session_paused(self.vault, self.sid, paused)
            self.assertEqual(len(read_commits(self.vault)), count)

    def test_completed_retracted_and_invalid_sessions_cannot_change(self):
        self.feedback(0)
        self.feedback(1)
        before = read_commits(self.vault)
        for sid in (self.sid, '', None, [], 'missing'):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                set_session_paused(self.vault, sid, True)
        self.assertEqual(read_commits(self.vault), before)
        delete_session(self.vault, self.sid)
        with self.assertRaisesRegex(ValueError, '不存在或已撤销'):
            set_session_paused(self.vault, self.sid, False)

    def test_projection_failure_rolls_back_fact_and_status(self):
        before = read_commits(self.vault)
        with patch('omrs.session_operations.apply_incremental', side_effect=RuntimeError('模拟投影失败')):
            with self.assertRaisesRegex(RuntimeError, '模拟投影失败'):
                set_session_paused(self.vault, self.sid, True)
        self.assertEqual(read_commits(self.vault), before)
        self.assertEqual(get_session(self.vault, self.sid)['status'], 'active')

    def test_mcp_retry_reflects_paused_status_and_no_actionable_feedback(self):
        delete_session(self.vault, self.sid)
        result = create_mcp_session(self.vault, self.selected, 'key', 'request', lambda: None)
        set_session_paused(self.vault, result['session_id'], True)
        retry = create_mcp_session(self.vault, self.selected, 'key', 'request', lambda: None)
        self.assertEqual(retry['status'], 'paused')
        self.assertTrue(retry['reused'])
        self.assertEqual(retry['actionable_pending_count'], 0)

    def test_http_pause_resume_and_errors(self):
        def request(path, sid):
            handler = object.__new__(OMRSHandler)
            handler.vault_path, handler.path = self.vault, path
            body = json.dumps({'session_id': sid}).encode()
            handler.headers = {'Content-Length': str(len(body))}
            handler.rfile = io.BytesIO(body)
            responses = []
            handler._json = lambda value, status=200: responses.append((value, status))
            handler.do_POST()
            return responses[0]
        for action, expected in (('pause', 'paused'), ('resume', 'active')):
            value, status = request('/api/session/' + action, self.sid)
            self.assertEqual(status, 200)
            self.assertEqual(value['session']['status'], expected)
        self.assertEqual(request('/api/session/pause', 'missing')[1], 400)

    def test_learning_restore_preserves_paused_state(self):
        set_session_paused(self.vault, self.sid, True)
        target = read_commits(self.vault)[-1]['seq']
        set_session_paused(self.vault, self.sid, False)
        append_commit(self.vault, 'test', 'state.restore', '恢复暂停节点', {'target_seq': target})
        rebuild_projection(self.vault)
        self.assertEqual(get_session(self.vault, self.sid)['status'], 'paused')

    def test_resume_and_competing_creation_cannot_both_claim_questions(self):
        set_session_paused(self.vault, self.sid, True)
        barrier = Barrier(2)
        def compete(resume):
            barrier.wait(timeout=5)
            try:
                if resume:
                    set_session_paused(self.vault, self.sid, False)
                else:
                    create_mcp_session(self.vault, self.selected[:1], 'key', 'race', lambda: None)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(compete, (True, False))), 1)
        self.assertEqual(len(list_sessions(self.vault, 'active')), 1)

    def test_shared_query_can_filter_paused_sessions(self):
        from omrs.agent.tools.read import list_sessions_tool
        set_session_paused(self.vault, self.sid, True)
        result = list_sessions_tool({'vault': self.vault}, {'status': 'paused'})['result']
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['sessions'][0]['session_id'], self.sid)
        self.assertEqual(list_sessions_tool({'vault': self.vault}, {'status': 'active'})['result']['total'], 0)


if __name__ == '__main__':
    unittest.main()
