"""真实进程中断：原生 journal 与世代、身份和读写屏障。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests import test_label_plan as support
from omrs import label_plan_journal as journal
from omrs.labels import load_labels
from omrs.ledger import append_commit
from omrs.vault_lifecycle import advance_generation
from omrs.content_history import projection_row, read_question_file
from omrs.label_plan import compile_plan

SCRIPT = '''
import json, os, sys
from omrs.label_plan import compile_plan,digest
from omrs import label_plan_journal as j
vault,payload,point=sys.argv[1:]
p=compile_plan(vault,json.loads(payload))
if point=='replaced':
 real=j.os.replace
 def replace(source,target):
  real(source,target)
  if target.endswith('.md') and '.omrs-label-' in source:os._exit(77)
 j.os.replace=replace
elif point=='committed':
 j.refresh_projection=lambda *args:os._exit(77)
elif point=='prepared':
 real=j.atomic_json
 def save(path,value):
  real(path,value)
  if value.get('operation_id')=='crash':os._exit(77)
 j.atomic_json=save
j.execute(vault,p,'crash',digest(p['payload']))
'''


class LabelRecoveryTests(unittest.TestCase):
    setUp=support.LabelPlanTests.setUp
    change=support.LabelPlanTests.change

    def crash(self,point='replaced'):
        payload={'label_changes':[{'action':'create','key':'n','name':'新标记'}], 'question_changes':[self.change(add=['n'])]}
        completed=subprocess.run([sys.executable,'-c',SCRIPT,self.vault,json.dumps(payload,ensure_ascii=False),point],capture_output=True,timeout=15)
        self.assertEqual(completed.returncode,77,completed.stderr.decode())
        return Path(self.vault,self.q['file_path'])

    def test_crash_before_replace_leaves_no_business_mutation(self):
        path=Path(self.vault,self.q['file_path']);before=path.read_text()
        self.crash('prepared')
        self.assertEqual(journal.recover_pending(self.vault)['not_written'],1)
        self.assertEqual(path.read_text(),before)
        self.assertIsNone(journal.receipt(self.vault,'crash'))

    def test_crash_during_replace_rolls_back_every_file(self):
        path=Path(self.vault,self.q['file_path']);before=path.read_text()
        self.crash()
        with self.assertRaises(ValueError):load_labels(self.vault)
        self.assertEqual(journal.recover_pending(self.vault)['rolled_back'],1)
        self.assertEqual(path.read_text(),before)
        self.assertEqual(load_labels(self.vault)['labels'],[])
        self.assertIsNone(journal.receipt(self.vault,'crash'))

    def test_committed_crash_receipt_protects_later_edit(self):
        path=self.crash('committed')
        self.assertIsNotNone(journal.receipt(self.vault,'crash'))
        after=path.read_text()+'\n后来编辑\n';path.write_text(after)
        self.assertEqual(journal.recover_pending(self.vault)['committed'],1)
        self.assertEqual(path.read_text(),after)
        self.assertEqual(load_labels(self.vault)['labels'][0]['name'],'新标记')

    def test_recovery_refuses_new_owner_even_same_bytes(self):
        path=self.crash();text=path.read_text();new=path.with_suffix('.replacement');new.write_text(text);os.replace(new,path)
        with self.assertRaisesRegex(ValueError,'外部修改'):journal.recover_pending(self.vault)
        self.assertEqual(path.read_text(),text)
        self.assertTrue(list(Path(journal.directory(self.vault)).glob('*.json')))

    def test_recovery_refuses_later_ledger_fact(self):
        self.crash();append_commit(self.vault,'api','system.test','后来事实',{})
        with self.assertRaisesRegex(ValueError,'其它事实'):journal.recover_pending(self.vault)

    def test_generation_change_never_writes_restored_vault(self):
        path=self.crash();advance_generation(self.vault);path.write_text('恢复后的数据')
        self.assertEqual(journal.recover_pending(self.vault)['obsolete'],1)
        self.assertEqual(path.read_text(),'恢复后的数据')

    def test_readonly_refuses_pending_and_path_tampering(self):
        self.crash()
        with self.assertRaises(ValueError):journal.recover_pending(self.vault,allow_recovery=False)
        file=next(Path(journal.directory(self.vault)).glob('*.json'));intent=json.loads(file.read_text())
        intent['files'][0]['relative']='../outside.json';file.write_text(json.dumps(intent))
        with self.assertRaises(ValueError):journal.recover_pending(self.vault)

    def test_preparation_hash_and_raw_catalog_corruption_refused(self):
        from omrs.labels import labels_path
        Path(labels_path(self.vault)).write_text('{损坏')
        with self.assertRaisesRegex(ValueError,'不可读取'):compile_plan(self.vault,{'question_changes':[self.change(uncertain_reason='不足')]})
