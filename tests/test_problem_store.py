"""真实附件、数据库损坏、稳定身份与全库恢复。"""
import base64
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from omrs import problems, problem_assets, problem_store, schedule_banner, backup_store, ai_review, problem_review
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.question_ops import move_question, delete_question
from omrs.mcp.keys import create_key
from omrs.sessions import create_session_from_selection
from omrs.vault_lifecycle import generation
from tests.test_schedule_banner import SVG


class ProblemStoreTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='problem-storage-');self.addCleanup(self.t.cleanup)
        self.v=self.t.name
        self.q=create_question(self.v,'数学','身份',5,question_text='纯合成题')
        self.qid=mastery_rows(self.v)[0]['question_id']
        self.p=problems.execute(self.v,'create_problem',{'title':'原稳定题目','question_ids':[self.qid],'request_id':'p'})['problem']

    def test_identity_survives_move_archive_and_uid_reuse(self):
        olduid=self.q['uid']
        move_question(self.v,olduid,'物理','移动材料')
        linked=problems.get(self.v,self.p['id'])['questions'][0]
        self.assertEqual(linked['question_id'],self.qid)
        delete_question(self.v,linked['uid'])
        create_question(self.v,'数学','身份',5,question_text='另一道合成题')
        linked=problems.get(self.v,self.p['id'])['questions'][0]
        self.assertEqual(linked['question_id'],self.qid)
        self.assertFalse(linked['available'])

    def test_assets_backup_restore_and_pending_generation(self):
        image=io.BytesIO();Image.new('RGB',(20,20),'white').save(image,format='PNG')
        raw=image.getvalue()
        asset=problems.execute(self.v,'add_problem_asset',{'data_base64':base64.b64encode(raw).decode(),'request_id':'asset'})['asset']
        self.assertEqual(problem_assets.read(self.v,asset['name'])[0],raw)
        schedule_banner.save_settings(self.v,{'svg':SVG,'enabled':True,'expected_revision':0})
        sid=create_session_from_selection(self.v,[{'question_id':self.qid}])['session_id']
        reflection=problems.execute(self.v,'add_reflection_entry',{'question_id':self.qid,'content_md':'原始记录','request_id':'r'})['entry']
        key=create_key(self.v,scopes=['omrs:read','problem:read','problem:write'])
        op=problem_review.propose(self.v,key['key_id'],'create_problem',{'title':'备份中的待审','request_id':'pending'},'http://127.0.0.1:9999')
        archive,*_=backup_store.create_backup(self.v);self.addCleanup(lambda:os.path.exists(archive) and os.unlink(archive))
        problems.execute(self.v,'update_problem',{'id':self.p['id'],'title':'备份后修改','expected_revision':1,'request_id':'changed'})
        before=generation(self.v)
        restore_id=backup_store.prepare_import(self.v,archive)['restore_id']
        backup_store.restore(self.v,restore_id,True)
        self.assertGreater(generation(self.v),before)
        self.assertEqual(problems.get(self.v,self.p['id'])['title'],'原稳定题目')
        self.assertEqual(problems.reflections(self.v,self.qid)['items'][0]['id'],reflection['id'])
        self.assertEqual(problem_assets.read(self.v,asset['name'])[0],raw)
        self.assertIsNotNone(schedule_banner.for_export(self.v,sid))
        self.assertNotEqual(ai_review.decide(self.v,op['operation_id'],1,'approve')['status'],'applied')
        backup_store.restore(self.v,restore_id,True)
        self.assertEqual(problems.search(self.v)['total'],1)

    def test_reads_do_not_change_database_and_corruption_is_not_empty(self):
        target=Path(problem_store.path(self.v));before=hashlib.sha256(target.read_bytes()).hexdigest()
        problems.search(self.v);problems.get(self.v,self.p['id']);problems.reflections(self.v,self.qid)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),before)
        target.write_bytes(b'not a database')
        with self.assertRaises(Exception):problems.search(self.v)

    def test_dangerous_svg_and_path_traversal_refused(self):
        with self.assertRaises(ValueError):problem_assets.read(self.v,'../../other')
        for raw in [SVG.replace('<text ','<text onclick="x" ').encode(),SVG.replace('<text ','<foreignObject/><text ').encode()]:
            with self.assertRaises(ValueError):problems.execute(self.v,'add_problem_asset',{'data_base64':base64.b64encode(raw).decode(),'request_id':hashlib.sha256(raw).hexdigest()})
