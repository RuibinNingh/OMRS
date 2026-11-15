"""问题中心独立事实、稳定身份与错因事务。"""
import copy
import tempfile
import unittest
from pathlib import Path
from omrs import problems
from omrs.creation import create_question
from omrs.data_repository import mastery_rows


class ProblemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='problem-test-')
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        for n in range(2):
            create_question(self.vault, '数学', '合成材料', 5, question_text=f'合成题{n}')
        self.q = [r['question_id'] for r in mastery_rows(self.vault)]

    def write(self, action, **data):
        data.setdefault('request_id', f'test-{len(self.ids)}')
        self.ids.append(data['request_id'])
        return problems.execute(self.vault, action, data)

    def test_read_does_not_create_store(self):
        self.assertEqual(problems.search(self.vault)['total'], 0)
        self.assertFalse((Path(self.vault)/'错题/.omrs/problems.db').exists())

    def test_many_to_many_and_cas(self):
        self.ids = []
        a = self.write('create_problem', title='符号检查', question_ids=self.q)['problem']
        b = self.write('create_problem', title='端点条件', question_ids=self.q[:1])['problem']
        self.assertEqual(len(problems.get(self.vault, a['id'])['questions']), 2)
        self.assertEqual(problems.search(self.vault, question_id=self.q[0])['total'], 2)
        self.write('update_problem', id=a['id'], expected_revision=1, status='resolved', reason='隔时验证通过')
        with self.assertRaises(problems.ProblemConflict):
            self.write('update_problem', id=a['id'], expected_revision=1, title='不能覆盖')
        self.assertEqual(problems.get(self.vault, b['id'])['revision'], 1)

    def test_reflections_retry_revision_recurrence_and_learning_unchanged(self):
        self.ids = []
        before = copy.deepcopy(mastery_rows(self.vault))
        p = self.write('create_problem', title='变号')['problem']
        payload = dict(question_id=self.q[0], content_md='除负数漏变号', problem_ids=[p['id']], request_id='retry')
        first = self.write('add_reflection_entry', **payload)['entry']
        self.assertEqual(self.write('add_reflection_entry', **payload)['entry']['id'], first['id'])
        self.write('add_reflection_entry', question_id=self.q[0], content_md='端点漏写')
        self.write('add_reflection_entry', question_id=self.q[0], content_md='又漏变号', recurrence_of=first['id'])
        self.write('revise_reflection_entry', id=first['id'], expected_revision=1, content_md='乘负数漏变号', reason='纠正原话')
        entries = problems.reflections(self.vault, self.q[0])['items']
        self.assertEqual(len(entries), 3)
        self.assertEqual(mastery_rows(self.vault), before)
        self.assertEqual(len(problems.get(self.vault, p['id'])['questions']), 1)
        with self.assertRaises(problems.ProblemConflict):
            self.write('add_reflection_entry', **{**payload, 'content_md': '不同请求'})

    def test_missing_question_and_transaction_rollback(self):
        self.ids = []
        with self.assertRaises(ValueError):
            self.write('create_problem', title='不能半写', question_ids=['OP-999999'])
        self.assertEqual(problems.search(self.vault)['total'], 0)

    def test_ai_cannot_claim_user_confirmation(self):
        result = problems.execute(self.vault, 'create_problem', {'title':'假设', 'basis':'user_confirmed', 'request_id':'ai'}, actor={'kind':'mcp'})
        self.assertEqual(result['problem']['basis'], 'ai_hypothesis')

    def test_ai_revision_does_not_inherit_user_confirmation(self):
        self.ids=[]
        p=self.write('create_problem',title='用户观察')['problem']
        changed=problems.execute(self.vault,'update_problem',{'id':p['id'],'expected_revision':1,'description_md':'模型推测','request_id':'ai-edit'},actor={'kind':'agent'})['problem']
        self.assertEqual(changed['basis'],'ai_hypothesis')

    def test_new_reflection_link_advances_problem_revision_and_audit(self):
        self.ids=[]
        p=self.write('create_problem',title='独立问题')['problem']
        self.write('add_reflection_entry',question_id=self.q[0],content_md='新的观察',problem_ids=[p['id']])
        detail=problems.get(self.vault,p['id'])
        self.assertEqual(detail['revision'],2)
        self.assertEqual(detail['events'][0]['action'],'reflection_link')
        self.write('add_reflection_entry',question_id=self.q[0],content_md='再次观察',problem_ids=[p['id']])
        self.assertEqual(problems.get(self.vault,p['id'])['revision'],2)

    def test_user_confirmation_requires_evidence_and_revision_keeps_date(self):
        self.ids=[]
        p=problems.execute(self.vault,'create_problem',{'title':'待验证推测','request_id':'ai-origin'},actor={'kind':'mcp'})['problem']
        with self.assertRaises(ValueError):
            self.write('update_problem',id=p['id'],expected_revision=1,basis='user_confirmed')
        self.write('update_problem',id=p['id'],expected_revision=1,basis='user_confirmed',reason='用户检查原题后确认')
        entry=problems.execute(self.vault,'add_reflection_entry',{'question_id':self.q[0],'content_md':'推测遗漏边界','request_id':'ai-ref'},actor={'kind':'agent'})['entry']
        result=self.write('revise_reflection_entry',id=entry['id'],expected_revision=1,basis='user_confirmed',occurred_at='2026-11-14',reason='核对原题后确认')['entry']
        self.assertEqual(result['basis'],'user_confirmed')
        self.assertEqual(result['occurred_at'],'2026-11-14')


class ProblemManagementTests(unittest.TestCase):
    """批量回收站与状态操作的事务、身份和恢复边界。"""
    def setUp(self):
        ProblemTests.setUp(self)
        self.ids = []

    write = ProblemTests.write

    def manage(self, operation, values, **extra):
        return self.write('manage_problems', operation=operation,
            items=[{'id': p['id'], 'expected_revision': p['revision']} for p in values], **extra)

    def test_trash_restore_keeps_materials_reflections_and_learning(self):
        baseline = copy.deepcopy(mastery_rows(self.vault))
        p = self.write('create_problem', title='保留材料', question_ids=self.q)['problem']
        e = self.write('add_reflection_entry', question_id=self.q[0], content_md='保留观察', problem_ids=[p['id']])['entry']
        deleted = self.manage('trash', [p])['problems'][0]
        self.assertEqual(problems.search(self.vault)['total'], 0)
        self.assertEqual(problems.search(self.vault, deleted='only')['items'][0]['id'], p['id'])
        self.assertEqual(problems.search(self.vault)['counts']['trash'], 1)
        detail = problems.get(self.vault, p['id'])
        self.assertEqual(len(detail['questions']), 2)
        self.assertEqual(detail['entries'][0]['id'], e['id'])
        self.assertEqual(detail['events'][0]['action'], 'trash_problem')
        restored = self.manage('restore', [deleted])['problems'][0]
        self.assertIsNone(restored['deleted_at'])
        self.assertEqual(problems.search(self.vault)['total'], 1)
        self.assertEqual(problems.get(self.vault, p['id'])['events'][0]['action'], 'restore_problem')
        self.assertEqual(mastery_rows(self.vault), baseline)

    def test_batch_cas_rolls_back_every_problem_and_receipt(self):
        a = self.write('create_problem', title='甲')['problem']
        b = self.write('create_problem', title='乙')['problem']
        self.write('update_problem', id=b['id'], expected_revision=1, title='乙已变化')
        with self.assertRaises(problems.ProblemConflict):
            self.manage('trash', [a, b], request_id='batch-conflict')
        self.assertEqual(problems.search(self.vault)['total'], 2)
        self.assertEqual(problems.get(self.vault, a['id'])['revision'], 1)
        b = problems.get(self.vault, b['id'])
        result = self.manage('trash', [a, b], request_id='batch-conflict')
        self.assertEqual(len(result['problems']), 2)

    def test_receipt_retry_does_not_trash_twice(self):
        p = self.write('create_problem', title='重试')['problem']
        first = self.manage('trash', [p], request_id='same-trash')
        second = self.manage('trash', [p], request_id='same-trash')
        self.assertTrue(second['reused'])
        self.assertEqual(first['problems'], second['problems'])
        self.assertEqual(problems.get(self.vault, p['id'])['revision'], 2)
        with self.assertRaises(problems.ProblemConflict):
            self.manage('restore', first['problems'], request_id='same-trash')

    def test_deleted_problem_blocks_existing_writes_and_new_reflection_links(self):
        p = self.write('create_problem', title='已删除')['problem']
        p = self.manage('trash', [p])['problems'][0]
        for action, extra in [('update_problem', {'title': '不能覆盖'}), ('link_problem_questions', {'question_ids': self.q})]:
            with self.assertRaises(problems.ProblemConflict):
                self.write(action, id=p['id'], expected_revision=p['revision'], **extra)
        with self.assertRaises(problems.ProblemConflict):
            self.write('add_reflection_entry', question_id=self.q[0], content_md='不能关联', problem_ids=[p['id']])
        self.assertEqual(problems.reflections(self.vault, self.q[0])['total'], 0)

    def test_management_not_exposed_to_ai_or_review(self):
        from omrs import problem_review
        for kind in ('agent', 'mcp'):
            with self.assertRaisesRegex(ValueError, '仅支持用户'):
                problems.execute(self.vault, 'manage_problems', {'request_id': kind}, actor={'kind': kind})
        with self.assertRaises(ValueError):
            problem_review.snapshot(self.vault, 'manage_problems', {})
        self.assertNotIn('manage_problems', problems.ACTIONS)

    def test_existing_reflection_revision_and_recurrence_survive_trash(self):
        p = self.write('create_problem', title='独立记录', question_ids=self.q[:1])['problem']
        e = self.write('add_reflection_entry', question_id=self.q[0], content_md='保留原记录', problem_ids=[p['id']])['entry']
        deleted = self.manage('trash', [p])['problems'][0]
        changed = self.write('revise_reflection_entry', id=e['id'], expected_revision=e['revision'],
            content_md='修订原记录', problem_ids=[p['id']], reason='更正原文')['entry']
        self.assertEqual(changed['content_md'], '修订原记录')
        repeated = self.write('add_reflection_entry', question_id=self.q[0], content_md='再次观察',
            recurrence_of=e['id'], problem_ids=[p['id']])['entry']
        self.assertEqual(repeated['problem_ids'], [p['id']])
        self.assertEqual(problems.get(self.vault, p['id'])['revision'], deleted['revision'])

    def test_status_needs_reason_and_invalid_batch_is_atomic(self):
        p = self.write('create_problem', title='批量状态')['problem']
        for operation, extra in [('status', {'status': 'resolved'}), ('restore', {}), ('trash', {'items': []})]:
            if 'items' in extra:
                with self.assertRaises(ValueError):
                    self.write('manage_problems', operation=operation, **extra)
            else:
                with self.assertRaises(ValueError):
                    self.manage(operation, [p], **extra)
        with self.assertRaises(ValueError):
            self.manage('trash', [p, p])
        with self.assertRaises(ValueError):
            self.manage('status', [p], status={}, reason='无效状态')
        with self.assertRaises(ValueError):
            self.manage('trash', [p] * 101)
        self.assertEqual(problems.get(self.vault, p['id'])['revision'], 1)
        changed = self.manage('status', [p], status='verifying', reason='隔时验证')['problems'][0]
        self.assertEqual(changed['status'], 'verifying')
        self.assertEqual(problems.get(self.vault, p['id'])['events'][0]['reason'], '隔时验证')

    def test_search_counts_pagination_sort_and_legacy_objects(self):
        values = [self.write('create_problem', title=title, status=status)['problem'] for title, status in
                  [('共同 B', 'working'), ('共同 A', 'resolved'), ('其他', 'analyzing')]]
        self.manage('trash', values[2:])
        first = problems.search(self.vault, query='共同', sort='title', limit=1)
        second = problems.search(self.vault, query='共同', sort='title', limit=1, cursor=first['next_cursor'])
        self.assertEqual(first['items'][0]['title'], '共同 A')
        self.assertEqual(second['items'][0]['title'], '共同 B')
        self.assertEqual(first['counts'], dict(analyzing=0, working=1, verifying=0, resolved=1, parked=0, all=2, trash=0))
        self.assertEqual(problems.search(self.vault, status='working')['total'], 1)
        self.assertEqual(problems.search(self.vault, sort='updated_asc')['items'][0]['id'], values[0]['id'])
        for args in ({'sort': 'unknown'}, {'deleted': 'true'}):
            with self.assertRaises(ValueError):
                problems.search(self.vault, **args)
