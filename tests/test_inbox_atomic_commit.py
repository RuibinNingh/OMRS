"""逐卡入库通过真实存储验证幂等、故障补齐与标记语义。"""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from omrs import creation, inbox, inbox_commit
from omrs.data_repository import mastery_rows
from omrs.ledger import connect, verify_ledger
from tests.test_inbox import make_png


class InboxAtomicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-inbox-atomic-')
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        item = inbox.upload_images(self.vault,[('card.png',make_png(4,4))])['items'][0]
        self.item = inbox.update_item(self.vault,item['id'],{
            'regions':[{'card':1,'role':'question','x':0,'y':0,'w':1,'h':1,'convert':'text','text':'original','text_status':'done'}],
            'cards':{'1':{'subject':'数学','category':'集合','difficulty':5,'labels':['待检查']}}})
        self.item = inbox.update_item(self.vault,item['id'],{'status':'ready'})
        self.request = dict(expected_revision=self.item['revision'], reset_epoch=self.item['reset_epoch'], require_version=True)

    def commit(self, **kw):
        return inbox.commit_item(self.vault,self.item['id'],**{**self.request,**kw})

    def creates(self):
        with connect(self.vault) as db:
            return db.execute("SELECT COUNT(*) FROM commits WHERE commit_type='question.create'").fetchone()[0]

    def test_parallel_retries_stale_revision_and_lost_response_return_one_identity(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _:self.commit(),range(8)))
        self.assertEqual(len({r['question_id'] for r in results}),1)
        self.assertEqual(self.creates(),1)
        self.assertEqual(sum(not r['reused'] for r in results),1)
        self.assertEqual(self.commit()['question_id'],results[0]['question_id'])
        self.assertTrue(verify_ledger(self.vault)['valid'])

    def test_each_persistence_failure_can_retry_without_second_create(self):
        stages = [(inbox_commit,'_freeze'),(creation,'_atomic_write_text'),
                  (creation,'append_commit_in_db'),(creation,'rebuild_projection'),
                  (inbox_commit,'_finish'),(inbox,'_log')]
        for module,name in stages:
            with self.subTest(stage=name), tempfile.TemporaryDirectory() as vault:
                previous = self.vault
                self.vault = vault
                item = inbox.upload_images(vault,[('card.png',make_png(3,3))])['items'][0]
                item = inbox.update_item(vault,item['id'],{'regions':self.item['regions'],'cards':{'1':{'subject':'数学','category':'集合'}}})
                item = inbox.update_item(vault,item['id'],{'status':'ready'})
                try:
                    with mock.patch.object(module,name,side_effect=OSError('injected '+name)):
                        with self.assertRaises(OSError):
                            inbox.commit_item(vault,item['id'])
                    a = inbox.commit_item(vault,item['id'])
                    b = inbox.commit_item(vault,item['id'])
                    self.assertEqual(a['question_id'],b['question_id'])
                    self.assertEqual(self.creates(),1)
                    self.assertTrue(verify_ledger(vault)['valid'])
                finally:
                    self.vault = previous

    def test_kill_after_ledger_commit_startup_only_repairs_receipt(self):
        code = ('import os,sys\nfrom omrs import inbox,inbox_commit\n'
                'def kill(*args): os._exit(72)\n'
                'inbox_commit._finish=kill\ninbox.commit_item(sys.argv[1],sys.argv[2])\n')
        child = subprocess.run([sys.executable,'-c',code,self.vault,self.item['id']],capture_output=True)
        self.assertEqual(child.returncode,72,child.stderr)
        self.assertEqual(self.creates(),1)
        inbox_commit.recover_pending(self.vault)
        self.assertEqual(inbox.get_item(self.vault,self.item['id'])['status'],'done')
        self.assertTrue(self.commit()['reused'])
        self.assertEqual(self.creates(),1)

    def test_different_content_conflicts_and_pending_operation_blocks_reset(self):
        with mock.patch.object(creation,'_atomic_write_text',side_effect=OSError('file unavailable')):
            with self.assertRaises(OSError):
                self.commit()
        with self.assertRaises(inbox.InboxConflict) as exc:
            inbox.reset_item(self.vault,self.item['id'])
        self.assertEqual(exc.exception.code,'operation_pending')
        with self.assertRaises(inbox.InboxConflict) as exc:
            self.commit(form={'cause':'changed'})
        self.assertEqual(exc.exception.code,'request_conflict')
        self.commit()
        self.assertEqual(self.creates(),1)

    def test_incomplete_image_reservation_keeps_startup_and_original_retry_available(self):
        item = inbox.update_item(self.vault,self.item['id'],{'regions':[
            {'card':1,'role':'question','x':0,'y':0,'w':1,'h':1,'convert':'image'}]})
        inbox.update_item(self.vault,self.item['id'],{'status':'ready'})
        with mock.patch.object(inbox_commit,'_freeze',side_effect=OSError('freeze interrupted')):
            with self.assertRaises(OSError):
                inbox.commit_item(self.vault,item['id'])
        result = inbox_commit.recover_pending(self.vault)
        self.assertEqual(result['awaiting_images'],[{'item_id':item['id'],'card':1}])
        self.assertEqual(self.creates(),0)
        a = inbox.commit_item(self.vault,item['id'])
        self.assertEqual(inbox.commit_item(self.vault,item['id'])['question_id'],a['question_id'])
        self.assertEqual(self.creates(),1)

    def test_omitted_labels_preserved_explicit_empty_clears_and_final_markdown_matches(self):
        item = inbox.update_item(self.vault,self.item['id'],{'cards':{'1':{'difficulty':8}}})
        self.assertEqual(item['cards']['1']['labels'],['待检查'])
        result = inbox.commit_item(self.vault,self.item['id'])
        self.assertIn('待检查', Path(self.vault,result['file_path']).read_text(encoding='utf-8'))
        # 独立新卡测试清空，不对已创建内容做第二次不同请求。
        with tempfile.TemporaryDirectory() as vault:
            item = inbox.upload_images(vault,[('clear.png',make_png(2,2))])['items'][0]
            inbox.update_item(vault,item['id'],{'regions':self.item['regions'],'cards':{'1':{'subject':'数学','category':'集合','labels':['旧标记']}}})
            item = inbox.update_item(vault,item['id'],{'status':'ready','cards':{'1':{'labels':[]}}})
            self.assertEqual(item['cards']['1']['labels'],[])
            result = inbox.commit_item(vault,item['id'])
            self.assertNotIn('旧标记',Path(vault,result['file_path']).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
