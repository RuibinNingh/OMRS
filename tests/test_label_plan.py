"""整批定义、题目归类、恢复和撤销的数据正确性门禁。"""
import copy
import os
import tempfile
import unittest
from unittest.mock import patch

from omrs.creation import create_question
from omrs.common import extract_labels, parse_yaml_frontmatter
from omrs.content_history import projection_row, read_question_file
from omrs.label_plan import compile_plan, digest
from omrs.label_plan_journal import execute, receipt, public_result
from omrs.label_plan_revert import revert, revert_preview
from omrs.labels import save_label, load_labels
from omrs.ledger import blob_hash, read_commits
from omrs.question_ops import set_question_labels
from omrs.stats import get_stats


class LabelPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.q = create_question(self.vault, subject='数学', category='代数', difficulty=5, question_text='用配方法解方程', answer_text='答案')

    def change(self, q=None, **values):
        q = q or self.q
        row = projection_row(self.vault, question_id=q['question_id'])
        return {'question_id': q['question_id'], 'expected_content_hash': blob_hash(read_question_file(self.vault, row)), **values}

    def apply(self, payload, op='test_batch'):
        prepared = compile_plan(self.vault, payload)
        return execute(self.vault, prepared, op, digest(prepared['payload']))

    def test_create_assign_atomic_and_undo(self):
        content = read_question_file(self.vault, projection_row(self.vault, question_id=self.q['question_id']))
        result = self.apply({'label_changes': [{'action': 'create', 'key': 'method', 'name': '配方法'}],
                             'question_changes': [self.change(add=['method'])]})
        self.assertEqual(result['counts']['changed'], 1)
        self.assertEqual(get_stats(self.vault)['items'][0]['labels'], ['配方法'])
        self.assertEqual(load_labels(self.vault)['labels'][0]['priority_bonus'], 0)
        self.assertNotIn('_undo', public_result(result))
        preview = revert_preview(self.vault, result['operation_id']); self.assertTrue(preview['ok'])
        self.assertEqual(preview['label_changes'][0]['before']['name'],'配方法')
        self.assertIsNone(preview['label_changes'][0]['after'])
        inverse = revert(self.vault, result['operation_id'], preview['inverse_digest'], 'r1')
        self.assertTrue(inverse['wrote'])
        self.assertEqual(read_question_file(self.vault, projection_row(self.vault, question_id=self.q['question_id'])), content)
        self.assertFalse(os.path.exists(os.path.join(self.vault, '错题', '.omrs', 'labels.json')))
        self.assertTrue(revert(self.vault, result['operation_id'], preview['inverse_digest'], 'r1')['reused'])
        self.assertFalse(revert_preview(self.vault, result['operation_id'])['ok'])

    def test_mixed_rename_merge_delete_and_state_unchanged(self):
        a, b, c = [save_label(self.vault, name=n) for n in ['A', 'B', 'C']]
        set_question_labels(self.vault, self.q['uid'], ['A', 'B', 'C'])
        stats = get_stats(self.vault)['items'][0]
        result = self.apply({'label_changes': [{'action':'update','label_id':b['id'],'name':'目标'},
            {'action':'merge','label_id':a['id'],'into':b['id']}, {'action':'delete','label_id':c['id']}]})
        now = get_stats(self.vault)['items'][0]
        self.assertEqual(now['labels'], ['目标'])
        for key in ('mastery','difficulty','suspended','tag'):
            self.assertEqual(now.get(key), stats.get(key))
        self.assertEqual(result['counts']['changed'], 1)

    def test_cross_subject_default_off(self):
        label = save_label(self.vault, name='A')
        other = create_question(self.vault, subject='物理', category='力学', difficulty=5)
        for q in (self.q,other): set_question_labels(self.vault,q['uid'],['A'])
        prepared = compile_plan(self.vault, {'scope':{'subject':'数学'}, 'label_changes':[{'action':'delete','label_id':label['id']}]})
        self.assertFalse(prepared['payload']['label_changes'][0]['enabled'])
        self.assertEqual(prepared['preview']['label_changes'][0]['affected_count'],2)
        self.assertEqual(prepared['files'],[])
        enabled=copy.deepcopy(prepared['payload']); enabled['label_changes'][0]['enabled']=True
        self.assertEqual(len(compile_plan(self.vault,enabled,trusted=True,allow_cross=True)['files']),2)

    def test_validation_whole_refusal(self):
        label = save_label(self.vault, name='A')
        invalid = [ {'label_changes':[{'action':'merge','label_id':label['id'],'into':label['id']}]},
                   {'label_changes':[{'action':'create','key':'a','name':'A'}]},
                   {'question_changes':[self.change(add=['missing'])]},
                   {'question_changes':[self.change(add=[label['id']],expected_content_hash='0'*64)]} ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):compile_plan(self.vault,payload)
        self.assertEqual(get_stats(self.vault)['items'][0]['labels'],[])

    def test_unscanned_edit_refused_and_preserved(self):
        path=os.path.join(self.vault,self.q['file_path'])
        with open(path,'a') as file:file.write('\n外部修改\n')
        with self.assertRaisesRegex(ValueError,'未扫描'):
            compile_plan(self.vault,{'question_changes':[self.change(uncertain_reason='信息不足')]})
        with open(path) as file:self.assertTrue(file.read().endswith('外部修改\n'))

    def test_replace_fault_rolls_back_all_and_no_receipt(self):
        prepared=compile_plan(self.vault,{'label_changes':[{'action':'create','key':'n','name':'新'}], 'question_changes':[self.change(add=['n'])]})
        real=os.replace
        def fail(source,target):
            if target.endswith('.md') and '.omrs-label-' in source and not failed[0]:
                failed[0]=True;raise OSError('故障注入')
            return real(source,target)
        failed=[False]
        with patch('omrs.label_plan_journal.os.replace',side_effect=fail),self.assertRaises(OSError):
            execute(self.vault,prepared,'fault',digest(prepared['payload']))
        self.assertIsNone(receipt(self.vault,'fault'))
        self.assertEqual(load_labels(self.vault)['labels'],[])
        self.assertEqual(get_stats(self.vault)['items'][0]['labels'],[])

    def test_transaction_fault_restores_files(self):
        prepared=compile_plan(self.vault,{'label_changes':[{'action':'create','key':'n','name':'新'}], 'question_changes':[self.change(add=['n'])]})
        with patch('omrs.label_plan_journal.append_commit_in_db',side_effect=RuntimeError('事务失败')),self.assertRaises(RuntimeError):
            execute(self.vault,prepared,'tx_fault',digest(prepared['payload']))
        self.assertEqual(load_labels(self.vault)['labels'],[])
        self.assertEqual(get_stats(self.vault)['items'][0]['labels'],[])

    def test_committed_projection_failure_receipt_recovery(self):
        prepared=compile_plan(self.vault,{'label_changes':[{'action':'create','key':'n','name':'新'}], 'question_changes':[self.change(add=['n'])]})
        with patch('omrs.label_plan_journal.refresh_projection',side_effect=RuntimeError('提交后中断')),self.assertRaises(RuntimeError):
            execute(self.vault,prepared,'committed',digest(prepared['payload']))
        self.assertIsNotNone(receipt(self.vault,'committed'))
        result=execute(self.vault,prepared,'committed',digest(prepared['payload']))
        self.assertTrue(result['reused']);self.assertEqual(get_stats(self.vault)['items'][0]['labels'],['新'])
        self.assertEqual(len([c for c in read_commits(self.vault) if c['commit_type']=='labels.plan_apply']),1)

    def test_undo_preserves_unrelated_and_blocks_new_reference(self):
        result=self.apply({'label_changes':[{'action':'create','key':'n','name':'新'}], 'question_changes':[self.change(add=['n'])]})
        save_label(self.vault,name='后续')
        set_question_labels(self.vault,self.q['uid'],['新','后续'])
        preview=revert_preview(self.vault,result['operation_id']);self.assertTrue(preview['ok'])
        revert(self.vault,result['operation_id'],preview['inverse_digest'],'r')
        self.assertEqual(get_stats(self.vault)['items'][0]['labels'],['后续'])
        result=self.apply({'label_changes':[{'action':'create','key':'m','name':'另新'}], 'question_changes':[self.change(add=['m'])]},op='second')
        other=create_question(self.vault,subject='数学',category='代数',difficulty=5)
        set_question_labels(self.vault,other['uid'],['另新'])
        self.assertFalse(revert_preview(self.vault,result['operation_id'])['ok'])

    def test_undo_stale_digest_and_changed_definition(self):
        result=self.apply({'label_changes':[{'action':'create','key':'n','name':'新'}]})
        preview=revert_preview(self.vault,result['operation_id'])
        save_label(self.vault,name='后来')
        with self.assertRaises(ValueError):revert(self.vault,result['operation_id'],preview['inverse_digest'],'r')
        save_label(self.vault,value=load_labels(self.vault)['labels'][0]['id'],name='改名')
        self.assertFalse(revert_preview(self.vault,result['operation_id'])['ok'])

    def test_reads_wait_for_complete_batch_not_half_replacement(self):
        import threading
        from omrs.labels import list_label_defs
        ready,release=threading.Event(),threading.Event()
        seen,errors=[],[]
        real=os.replace
        def replace(source,target):
            real(source,target)
            if target.endswith('.md') and '.omrs-label-' in source:
                ready.set();release.wait(3)
        def writer():
            try:self.apply({'label_changes':[{'action':'create','key':'n','name':'完整'}], 'question_changes':[self.change(add=['n'])]})
            except Exception as exc:errors.append(exc)
        def reader():
            try:seen.extend(list_label_defs(self.vault))
            except Exception as exc:errors.append(exc)
        with patch('omrs.label_plan_journal.os.replace',side_effect=replace):
            w=threading.Thread(target=writer);w.start();self.assertTrue(ready.wait(3))
            r=threading.Thread(target=reader);r.start()
            try:
                r.join(.05);self.assertTrue(r.is_alive());self.assertEqual(seen,[])
            finally:release.set();w.join(3);r.join(3)
        self.assertFalse(errors,errors);self.assertEqual(seen[0]['count'],1)

    def test_suspended_cascade_and_affected_limit(self):
        from omrs.question_ops import suspend_question
        label=save_label(self.vault,name='旧')
        set_question_labels(self.vault,self.q['uid'],['旧'])
        suspend_question(self.vault,self.q['uid'])
        payload={'label_changes':[{'action':'delete','label_id':label['id']}]}
        with patch('omrs.label_plan.MAX_QUESTIONS',0),self.assertRaisesRegex(ValueError,'实际受影响'):
            compile_plan(self.vault,payload)
        prepared=compile_plan(self.vault,payload)
        self.assertEqual(prepared['preview']['counts']['changed'],1)
        result=execute(self.vault,prepared,'suspended',digest(prepared['payload']))
        row=projection_row(self.vault,question_id=self.q['question_id']);self.assertTrue(row['suspended'])
        self.assertEqual(extract_labels(parse_yaml_frontmatter(read_question_file(self.vault,row))),[])

    def test_unscanned_new_reference_and_tampered_undo_refused(self):
        label=save_label(self.vault,name='原')
        folder=os.path.dirname(os.path.join(self.vault,self.q['file_path']))
        with open(os.path.join(folder,'代数999.md'),'w') as file:file.write('---\n科目: 数学\n标记: [原]\n---\n新外部题目')
        with self.assertRaisesRegex(ValueError,'未扫描的新'):compile_plan(self.vault,{'label_changes':[{'action':'delete','label_id':label['id']}]})
        os.unlink(os.path.join(folder,'代数999.md'))
        result=self.apply({'label_changes':[{'action':'create','key':'n','name':'新的'}]})
        from omrs.ledger import connect,canonical_json
        saved=receipt(self.vault,result['operation_id']);saved['_undo']['catalog_before']='{}'
        with connect(self.vault) as db:
            db.execute('UPDATE op_results SET result_json=? WHERE op_id=?',(canonical_json(saved),'label-plan:'+result['operation_id']))
        with self.assertRaisesRegex(ValueError,'批次事实'):receipt(self.vault,result['operation_id'])

    def test_undo_unscanned_new_reference_refuses_before_any_write(self):
        result=self.apply({'label_changes':[{'action':'create','key':'n','name':'新定义'}]})
        preview=revert_preview(self.vault,result['operation_id'])
        folder=os.path.dirname(os.path.join(self.vault,self.q['file_path']))
        external=os.path.join(folder,'代数999.md')
        content='---\n科目: 数学\n标记: [新定义]\n---\n外部新题目'
        with open(external,'w') as file:file.write(content)
        before=len(read_commits(self.vault))
        conflict=revert_preview(self.vault,result['operation_id'])
        self.assertFalse(conflict['ok']);self.assertIn('未扫描的新标记引用',conflict['conflicts'][0])
        with self.assertRaisesRegex(ValueError,'未扫描的新标记引用'):
            revert(self.vault,result['operation_id'],preview['inverse_digest'],'unscanned')
        self.assertEqual(len(read_commits(self.vault)),before)
        self.assertEqual(load_labels(self.vault)['labels'][0]['name'],'新定义')
        with open(external) as file:self.assertEqual(file.read(),content)
