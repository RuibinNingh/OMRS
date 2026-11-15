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
