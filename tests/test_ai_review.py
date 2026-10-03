"""统一审批的证据迁移、唯一队列、CAS、原生回执与启动只收束行为。"""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import closing
from unittest import mock

from omrs import ai_review as review, drafts, reports
from omrs.agent.store import AgentStore
from omrs.actor import agent_actor
from omrs.common import omrs_data_dir
from omrs.creation import create_question
from omrs.ledger import append_commit, blob_hash, connect, read_commits
from omrs.mcp.keys import create_key, revoke_key
from omrs.mcp.question_write import propose
from omrs.question_update import apply_update


class AiReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-ai-review-')
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.q = create_question(self.vault, '数学', '函数', 5, question_text='正式题干')
        self.path = Path(self.vault) / self.q['file_path']

    def operation(self, tool='create_category', source='agent', payload=None, pending=True, **kwargs):
        return review.create(self.vault, source, tool, uuid.uuid4().hex, payload or {'subject': '数学', 'category': '分类'},
                             pending=pending, **kwargs)

    def draft(self, request='draft'):
        return drafts.create_mcp_draft(self.vault,
            {'subject': '数学', 'category': '函数', 'blocks': [{'section': '题目', 'kind': 'text', 'text': '待审核'}]},
            {'conversation_id': 'mcp:key', 'source_key_id': 'key', 'source_request_id': request})

    def auto_intent(self, tool='create_draft'):
        return self.operation(tool, 'mcp', pending=False)

    def with_intent(self, row, fn):
        token = review._AUTO_INTENT.set(row)
        try:
            return fn()
        finally:
            review._AUTO_INTENT.reset(token)

    def test_same_draft_and_multiple_commit_proposals_are_one_pending_item(self):
        draft = self.draft()
        first = self.operation('commit_draft', payload={'draft_id': draft['id'], 'revision': draft['revision']})
        second = self.operation('commit_draft', payload={'draft_id': draft['id'], 'revision': draft['revision']})
        counts = review.counts(self.vault)
        self.assertEqual(counts, {'pending': 1, 'drafts': 0, 'operations': 1})
        items = review.items(self.vault)['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], second['operation_id'])
        records = review.items(self.vault, {'view': 'records'})
        self.assertEqual(records['total'], 3)
        self.assertEqual({r['id'] for r in records['items']}, {draft['id'], first['operation_id'], second['operation_id']})

    def test_merged_queue_paginates_without_duplicate_or_missing_items(self):
        drafts_ = [self.draft(f'page-{i}') for i in range(4)]
        operations = [self.operation() for _ in range(7)]
        expected = {d['id'] for d in drafts_} | {o['operation_id'] for o in operations}
        seen, offset = [], 0
        while True:
            result = review.items(self.vault, {'limit': 3, 'offset': offset})
            self.assertEqual(result['total'], len(expected))
            seen.extend(row['id'] for row in result['items'])
            if not result['has_more']:
                break
            offset = result['next_offset']
        self.assertEqual(len(seen), len(expected))
        self.assertEqual(set(seen), expected)
        self.assertEqual(review.items(self.vault, {'source': 'mcp'})['total'], 4)
        self.assertEqual(review.items(self.vault, {'type': 'category'})['total'], 7)
        for options in ({'limit': 101}, {'offset': -1}, {'view': 'unknown'}, {'source': 'invented'}, {'from': 'not-date'}):
            with self.subTest(options=options), self.assertRaises(review.ReviewError):
                review.items(self.vault, options)

    def test_expired_read_changes_no_record_and_pending_counts_hide_it(self):
        row = self.operation(expires_at=time.time()-1)
        path = Path(review.path(self.vault))
        before = path.read_bytes()
        self.assertEqual(review.get(self.vault, row['operation_id'])['status'], 'expired')
        self.assertEqual(review.counts(self.vault)['pending'], 0)
        self.assertEqual(review.items(self.vault, {'view': 'records', 'status': 'expired'})['total'], 1)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(review.ReviewError):
            review.revise(self.vault, row['operation_id'], 1, {}, {})

    def test_cursor_matches_offset_and_rejects_invalid_or_conflicting_position(self):
        for _ in range(5):
            self.operation()
        first = review.items(self.vault, {'limit': 2})
        self.assertEqual(first['next_cursor'], '2')
        cursor = review.items(self.vault, {'limit': 2, 'cursor': first['next_cursor']})
        offset = review.items(self.vault, {'limit': 2, 'offset': 2})
        self.assertEqual(cursor, offset)
        for options in ({'cursor': '-1'}, {'cursor': True}, {'cursor': 'abc'}, {'cursor': '2', 'offset': 3}):
            with self.subTest(options=options), self.assertRaises(review.ReviewError):
                review.items(self.vault, options)

    def test_first_draft_connection_is_counted_as_empty_before_schema_is_ready(self):
        review.initialize(self.vault)
        opened, proceed = threading.Event(), threading.Event()
        initialize = drafts._initialize
        errors = []
        def pause(vault, db):
            opened.set()
            if not proceed.wait(3):
                raise AssertionError('草稿建库测试没有被释放')
            return initialize(vault, db)
        def create():
            try:
                db = drafts.connect(self.vault)
                db.close()
            except BaseException as exc:
                errors.append(exc)
        with mock.patch.object(drafts, '_initialize', side_effect=pause):
            worker = threading.Thread(target=create, daemon=True)
            worker.start()
            try:
                self.assertTrue(opened.wait(2))
                before = Path(review._draft_path(self.vault)).read_bytes()
                self.assertEqual(review.counts(self.vault), {'pending': 0, 'drafts': 0, 'operations': 0})
                self.assertEqual(review.items(self.vault)['items'], [])
                self.assertEqual(Path(review._draft_path(self.vault)).read_bytes(), before)
            finally:
                proceed.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_first_review_connection_is_counted_as_empty_before_schema_is_ready(self):
        opened, proceed = threading.Event(), threading.Event()
        target = review.path(self.vault)
        self.assertFalse(Path(target).exists())
        open_sqlite = review.open_sqlite
        errors, created = [], []
        def pause(vault, path, **kwargs):
            if path == target:
                opened.set()
                if not proceed.wait(3):
                    raise AssertionError('审核建库测试没有被释放')
            return open_sqlite(vault, path, **kwargs)
        def create():
            try:
                created.append(self.operation())
            except BaseException as exc:
                errors.append(exc)
        with mock.patch.object(review, 'open_sqlite', side_effect=pause):
            worker = threading.Thread(target=create, daemon=True)
            worker.start()
            try:
                self.assertTrue(opened.wait(2))
                before = Path(target).read_bytes()
                self.assertEqual(review.counts(self.vault), {'pending': 0, 'drafts': 0, 'operations': 0})
                self.assertEqual(review.items(self.vault)['items'], [])
                self.assertEqual(Path(target).read_bytes(), before)
            finally:
                proceed.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(review.counts(self.vault)['operations'], 1)

    def test_new_draft_table_is_readable_before_incremental_migrations(self):
        ready, proceed = threading.Event(), threading.Event()
        open_sqlite = drafts.open_sqlite
        errors = []
        class PauseAfterSchema:
            def __init__(self, db):
                object.__setattr__(self, 'db', db)
            def __getattr__(self, name):
                return getattr(self.db, name)
            def __setattr__(self, name, value):
                setattr(self.db, name, value)
            def executescript(self, schema):
                result = self.db.executescript(schema)
                ready.set()
                if not proceed.wait(3):
                    raise AssertionError('草稿基础架构测试没有被释放')
                return result
        def open_draft(vault, path, **kwargs):
            return PauseAfterSchema(open_sqlite(vault, path, **kwargs))
        def create():
            try:
                drafts.connect(self.vault).close()
            except BaseException as exc:
                errors.append(exc)
        with mock.patch.object(drafts, 'open_sqlite', side_effect=open_draft):
            worker = threading.Thread(target=create, daemon=True)
            worker.start()
            try:
                self.assertTrue(ready.wait(2))
                before = Path(review._draft_path(self.vault)).read_bytes()
                self.assertEqual(review.counts(self.vault), {'pending': 0, 'drafts': 0, 'operations': 0})
                self.assertEqual(review.items(self.vault)['items'], [])
                self.assertEqual(Path(review._draft_path(self.vault)).read_bytes(), before)
            finally:
                proceed.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_review_count_does_not_hide_corrupt_or_incomplete_existing_schema(self):
        target = Path(review.path(self.vault))
        target.write_bytes(b'not a sqlite database')
        with self.assertRaises(sqlite3.DatabaseError):
            review.counts(self.vault)
        target.unlink()
        with closing(sqlite3.connect(target)) as db:
            db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
            db.commit()
        with self.assertRaises(sqlite3.DatabaseError):
            review.counts(self.vault)
        target.unlink()
        with closing(sqlite3.connect(target)) as db:
            db.execute('CREATE TABLE operations(operation_id TEXT PRIMARY KEY)')
            db.commit()
        with self.assertRaises(sqlite3.DatabaseError):
            review.counts(self.vault)

    def test_startup_initializes_existing_empty_draft_database_before_reads(self):
        target = Path(review._draft_path(self.vault))
        target.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(target).close()
        review.initialize(self.vault)
        with closing(sqlite3.connect(target)) as db:
            columns = {row[1] for row in db.execute('PRAGMA table_info(drafts)')}
        self.assertIn('source_channel', columns)
        before = target.read_bytes()
        self.assertEqual(review.counts(self.vault), {'pending': 0, 'drafts': 0, 'operations': 0})
        self.assertEqual(target.read_bytes(), before)

    def test_cas_revision_does_not_extend_deadline_or_expand_editable_fields(self):
        row = self.operation('update_question_section', payload={'value': '原稿'}, editable_fields=['question_text'])
        updated = review.revise(self.vault, row['operation_id'], 1, {'value': '人工修订'}, {'changes': []})
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['expires_at'], row['expires_at'])
        self.assertEqual(updated['digest'], row['digest'])
        self.assertNotEqual(updated['effective_digest'], row['effective_digest'])
        with self.assertRaises(review.ReviewError):
            review.revise(self.vault, row['operation_id'], 1, {}, {})
        with self.assertRaises(review.ReviewError):
            review.revise(self.vault, row['operation_id'], 2, {}, {}, editable_fields=['answer_text'])
        detail = review.detail(self.vault, row['operation_id'])
        self.assertEqual(detail['original_payload'], {'value': '原稿'})

    def test_legacy_done_without_actual_evidence_is_never_migrated_as_success(self):
        store = AgentStore(self.vault)
        store.create_conversation('legacy', '旧对话')
        store.create_run('run', 'legacy', 'fake')
        store.save_tool_call('run', 'call', 'create_category', 'confirm', {'subject': '数学', 'category': '不存在'},
                             'done', decision='allow')
        review.initialize(self.vault)
        items = review.items(self.vault, {'view': 'records'})['items']
        self.assertEqual(len(items), 1)
        migrated = review.get(self.vault, items[0]['id'])
        self.assertEqual(migrated['status'], 'interrupted')
        self.assertTrue(migrated['history_incomplete'])
        self.assertTrue(migrated['history_readonly'])
        with self.assertRaises(review.ReviewError):
            review.decide(self.vault, migrated['operation_id'], 1, 'approve')
        review.initialize(self.vault)
        self.assertEqual(review.items(self.vault, {'view': 'records'})['total'], 1)

    def test_legacy_tool_end_error_without_result_is_failed(self):
        store = AgentStore(self.vault)
        store.create_conversation('legacy-error', '旧对话')
        store.create_run('error-run', 'legacy-error', 'fake')
        store.save_tool_call('error-run', 'error-call', 'create_category', 'confirm', {}, 'done', decision='allow')
        store.append_event('error-run', {'i': 0, 'type': 'tool.end', 'data': {'call_id': 'error-call',
                           'status': 'error', 'error': '目录写入失败'}})
        review.initialize(self.vault)
        items = review.items(self.vault, {'view': 'records'})['items']
        self.assertEqual(items[0]['status'], 'failed')
        result = review.get(self.vault, items[0]['id'])
        self.assertFalse(result['history_incomplete'])

    def test_failed_automatic_write_is_preserved_and_never_blocks_startup(self):
        row = self.auto_intent()
        review.set_state(self.vault, row['operation_id'], 'failed', error_code='invalid_request')
        review.initialize(self.vault)
        after = review.get(self.vault, row['operation_id'])
        self.assertEqual(after['status'], 'failed')
        self.assertEqual(after['error_code'], 'invalid_request')

    def test_active_tool_error_evidence_is_failed_and_keeps_actual_error(self):
        actor = {'conversation_id': 'legacy', 'run_id': 'failed-run', 'tool_call_id': 'failed-call'}
        row = review.create(self.vault, 'agent', 'create_category',
                            'agent:'+review.fingerprint(['failed-run', 'failed-call']), {}, actor=actor)
        store = AgentStore(self.vault)
        store.create_conversation('legacy', '旧对话')
        store.create_run('failed-run', 'legacy', 'fake')
        store.save_tool_call('failed-run', 'failed-call', 'create_category', 'confirm', {}, 'done', decision='allow')
        store.append_event('failed-run', {'i': 0, 'type': 'tool.end', 'data': {'call_id': 'failed-call',
                           'status': 'error', 'error': '原目录写入失败'}})
        review.initialize(self.vault)
        result = review.get(self.vault, row['operation_id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['result']['error'], '原目录写入失败')
        self.assertEqual(result['error_code'], 'tool_error')

    def test_commits_without_full_batch_result_are_partial_and_incomplete(self):
        store = AgentStore(self.vault)
        store.create_conversation('legacy', '旧对话')
        store.create_run('batch-run', 'legacy', 'fake')
        store.save_tool_call('batch-run', 'batch-call', 'record_feedback', 'confirm',
                             {'items': [{'uid': self.q['uid']}]}, 'done', decision='allow')
        with agent_actor('legacy', 'batch-run', 'batch-call'):
            append_commit(self.vault, 'api', 'system.legacy_test', '旧运行仅一项事实', {'count': 1})
        review.initialize(self.vault)
        rows = review.items(self.vault, {'view': 'records'})['items']
        migrated = review.get(self.vault, rows[0]['id'])
        self.assertEqual(migrated['status'], 'partial')
        self.assertTrue(migrated['history_incomplete'])
        self.assertEqual(len(migrated['commits']), 1)

    def test_native_partial_recovery_also_keeps_history_incomplete(self):
        row = self.operation('record_feedback', pending=False,
                             actor={'conversation_id': 'legacy', 'run_id': 'native-run', 'tool_call_id': 'native-call'})
        with agent_actor('legacy', 'native-run', 'native-call'):
            append_commit(self.vault, 'api', 'system.legacy_test', '原生事实没有批次结果', {'count': 1})
        review.initialize(self.vault)
        recovered = review.get(self.vault, row['operation_id'])
        self.assertEqual(recovered['status'], 'partial')
        self.assertTrue(recovered['history_incomplete'])

    def test_approved_or_applying_without_native_receipt_is_interrupted(self):
        for status in ('approved', 'applying'):
            row = self.operation('delete_board', 'mcp', {'board_id': 'missing'}, actor={'key_id': 'missing'})
            review.set_state(self.vault, row['operation_id'], status)
            with mock.patch('omrs.mcp_operations.review_decide', side_effect=AssertionError('不得重放')):
                review.initialize(self.vault)
            self.assertEqual(review.get(self.vault, row['operation_id'])['status'], 'interrupted')
        pending = self.operation('delete_board', 'mcp', {'board_id': 'missing'}, actor={'key_id': 'missing'})
        review.initialize(self.vault)
        kept = review.get(self.vault, pending['operation_id'])
        self.assertEqual(kept['status'], 'pending_confirmation')
        self.assertEqual(kept['expires_at'], pending['expires_at'])

    def test_native_auto_receipt_failure_rolls_back_creation(self):
        row = self.auto_intent()
        with mock.patch.object(review, 'save_auto_receipt', side_effect=OSError('审核回执无法保存')):
            with self.assertRaises(OSError):
                self.with_intent(row, self.draft)
        self.assertEqual(drafts.counts(self.vault)['review'], 0)
        self.assertIsNone(review._auto_receipt(self.vault, row))

    def test_lost_automatic_terminal_recovers_exact_native_receipt_without_write(self):
        row = self.auto_intent()
        draft = self.with_intent(row, self.draft)
        receipt = review._auto_receipt(self.vault, row)
        self.assertEqual(receipt['draft_id'], draft['id'])
        with mock.patch('omrs.drafts.create_mcp_draft', side_effect=AssertionError('不得重新建题')):
            review.initialize(self.vault)
            review.initialize(self.vault)
        self.assertEqual(review.get(self.vault, row['operation_id'])['status'], 'applied')
        self.assertEqual(drafts.counts(self.vault)['review'], 1)
        other = self.auto_intent()
        review.set_state(self.vault, other['operation_id'], 'failed', error_code='request_conflict')
        self.assertIsNone(review._auto_receipt(self.vault, other))
        review.initialize(self.vault)
        self.assertEqual(review.get(self.vault, other['operation_id'])['status'], 'failed')

    def test_report_native_receipt_is_bound_to_exact_automatic_intent(self):
        row = self.auto_intent('create_report')
        result = self.with_intent(row, lambda: reports.create_mcp_report(self.vault, '报告', '<p>实际报告</p>', 'key', 'report'))
        self.assertEqual(review._auto_receipt(self.vault, row)['report_id'], result['report_id'])
        review.initialize(self.vault)
        self.assertEqual(review.get(self.vault, row['operation_id'])['status'], 'applied')
        other = self.auto_intent('create_report')
        self.assertIsNone(review._auto_receipt(self.vault, other))

    def test_startup_recovers_question_fact_without_reexecuting_tool(self):
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        proposal = propose(self.vault, key['key_id'], 'question', self.q['uid'], self.q['question_id'],
                           blob_hash(self.path.read_text()), {'question_text': '正式新题干'}, reason='修正题干')
        row = review.set_state(self.vault, proposal['operation_id'], 'applying')
        result = apply_update(self.vault, row)
        before = len(read_commits(self.vault))
        with mock.patch('omrs.mcp.question_write.apply_review', side_effect=AssertionError('不得重放题目')):
            review.initialize(self.vault)
        recovered = review.get(self.vault, row['operation_id'])
        self.assertEqual(recovered['status'], 'applied')
        self.assertEqual(recovered['result']['commit_id'], result['commit_id'])
        self.assertEqual(len(read_commits(self.vault)), before)

    def test_center_detail_shows_exact_committed_mcp_receipt_without_mutation(self):
        from omrs import mcp_operations as operations
        from omrs.ledger import ledger_path
        key = create_key(self.vault, scopes=['omrs:read', 'session:create'])
        proposal = operations.create_session(self.vault,
            [{'question_id': self.q['question_id'], 'source': 'due'}], key['key_id'], 'center-receipt', '',
            lambda: operations._session_auth(self.vault, key['key_id']))
        original = operations._save_state
        def fail_terminal(vault, row, status, *args, **kwargs):
            if status == 'applied':
                raise sqlite3.OperationalError('审核终态丢失')
            return original(vault, row, status, *args, **kwargs)
        with mock.patch.object(operations, '_save_state', side_effect=fail_terminal):
            committed = review.decide(self.vault, proposal['operation_id'], 1, 'approve')
        self.assertEqual(committed['status'], 'applied')
        self.assertEqual(review.get(self.vault, proposal['operation_id'])['status'], 'applying')
        revoke_key(self.vault, key['key_id'])
        targets = [Path(review.path(self.vault)), Path(ledger_path(self.vault)), self.path]
        before = {str(path): path.read_bytes() for path in targets}
        facts = read_commits(self.vault)
        with (mock.patch.object(review, 'set_state', side_effect=AssertionError('GET不能保存状态')),
              mock.patch.object(operations, 'review_decide', side_effect=AssertionError('GET不能重新批准'))):
            detail = review.detail(self.vault, proposal['operation_id'])
            records = review.items(self.vault, {'view': 'records', 'status': 'applied'})
            stale = review.items(self.vault, {'view': 'records', 'status': 'applying'})
        self.assertEqual(detail['status'], 'applied')
        self.assertEqual(records['total'], 1)
        self.assertEqual(records['items'][0]['id'], proposal['operation_id'])
        self.assertEqual(records['items'][0]['status'], 'applied')
        self.assertEqual(stale['total'], 0)
        self.assertEqual(detail['result']['session_id'], committed['result']['session_id'])
        self.assertEqual(review.get(self.vault, proposal['operation_id'])['status'], 'applying')
        self.assertEqual({str(path): path.read_bytes() for path in targets}, before)
        self.assertEqual(read_commits(self.vault), facts)

    def test_center_list_and_detail_show_noop_receipt_as_unchanged_without_writes(self):
        from omrs import mcp_operations as operations
        from omrs.ledger import ledger_path
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        proposal = propose(self.vault, key['key_id'], 'unchanged-receipt', self.q['uid'], self.q['question_id'],
                           blob_hash(self.path.read_text()), {'question_text': '正式题干'}, reason='核对原题')
        original = operations._save_state
        def fail_terminal(vault, row, status, *args, **kwargs):
            if status == 'unchanged':
                raise sqlite3.OperationalError('无变化终态丢失')
            return original(vault, row, status, *args, **kwargs)
        facts = read_commits(self.vault)
        with mock.patch.object(operations, '_save_state', side_effect=fail_terminal):
            committed = review.decide(self.vault, proposal['operation_id'], 1, 'approve')
        self.assertEqual(committed['status'], 'unchanged')
        self.assertEqual(review.get(self.vault, proposal['operation_id'])['status'], 'applying')
        targets = [Path(review.path(self.vault)), Path(ledger_path(self.vault)), self.path]
        before = {str(path): path.read_bytes() for path in targets}
        with mock.patch.object(review, 'set_state', side_effect=AssertionError('GET不能写审批')):
            rows = review.items(self.vault, {'view': 'records', 'status': 'unchanged'})
            detail = review.detail(self.vault, proposal['operation_id'])
            self.assertEqual(review.items(self.vault, {'view': 'records', 'status': 'applied'})['total'], 0)
        self.assertEqual(rows['total'], 1)
        self.assertEqual(rows['items'][0]['id'], proposal['operation_id'])
        self.assertEqual(detail['status'], 'unchanged')
        self.assertTrue(detail['result']['no_op'])
        self.assertEqual(review.get(self.vault, proposal['operation_id'])['status'], 'applying')
        self.assertEqual({str(path): path.read_bytes() for path in targets}, before)
        self.assertEqual(read_commits(self.vault), facts)
        with mock.patch.object(operations, '_receipt', return_value={'digest': 'mismatch', 'result': committed['result']}):
            mismatch = review.detail(self.vault, proposal['operation_id'])
            self.assertEqual(review.items(self.vault, {'view': 'records', 'status': 'unchanged'})['total'], 0)
            self.assertEqual(review.items(self.vault, {'view': 'records', 'status': 'conflict'})['total'], 1)
        self.assertEqual(mismatch['status'], 'conflict')
        self.assertEqual(mismatch['error_code'], 'request_conflict')
        self.assertEqual({str(path): path.read_bytes() for path in targets}, before)

    def test_create_refuses_unknown_write_tool_and_authentication_in_actor(self):
        for source, tool in (('agent', 'get_question'), ('mcp', 'unknown_write')):
            with self.assertRaises(review.ReviewError):
                self.operation(tool, source)
        for credential in ('secret', 'token', 'pin', 'cookie', 'authorization'):
            with self.subTest(credential=credential), self.assertRaises(review.ReviewError):
                self.operation(actor={credential: '不得保存'})

    def test_question_reason_remains_bound_to_original_request_after_revision(self):
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        operation = propose(self.vault, key['key_id'], 'reason', self.q['uid'], self.q['question_id'],
                            blob_hash(self.path.read_text()), {'question_text': '新题干'}, reason='  修正漏字  ')
        row = review.get(self.vault, operation['operation_id'])
        updated = review.update(self.vault, row['operation_id'], 1, {'question_text': '人工修订'})
        self.assertEqual(updated['payload']['reason'], '修正漏字')
        self.assertEqual(updated['actor']['reason'], '修正漏字')
        self.assertEqual(updated['preview']['reason'], '修正漏字')
        with self.assertRaises(review.ReviewError):
            review.update(self.vault, row['operation_id'], 2, {'reason': '不得改变原理由'})


if __name__ == '__main__':
    unittest.main()
