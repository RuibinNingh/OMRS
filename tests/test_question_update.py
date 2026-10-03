"""临时题库验证安全正式题目补丁、审批回执及真实进程中断恢复。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

from omrs import ai_review, question_update as update
from omrs.actor import agent_actor
from omrs.common import extract_knowledge_tags, extract_labels, parse_yaml_frontmatter
from omrs.content_history import projection_row, read_question_file
from omrs.creation import create_question
from omrs.errors import RequestError
from omrs.ledger import append_commit, blob_hash, connect, read_commits, verify_ledger
from omrs.mcp.keys import create_key, revoke_key
from omrs.mcp.question_write import prepare_review, propose
from omrs.question_ops import move_question, save_question_markdown
from omrs.vault_lifecycle import advance_generation, maintenance_dir
from omrs.workspace_sync import scan_workspace


class QuestionUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-question-update-')
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.q = create_question(self.vault, '数学', '函数', 5, question_text='旧题干', answer_text='旧答案')
        self.path = Path(self.vault) / self.q['file_path']
        self.key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        self.run = SimpleNamespace(id='run', conv_id='cv', done=False, closing=False, abort=threading.Event())
        from omrs.agent.runtime import _RUNTIMES
        runtime_patch = mock.patch.dict(_RUNTIMES, {self.vault: SimpleNamespace(runs={'run': self.run})})
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)

    def content(self):
        return self.path.read_text(encoding='utf-8')

    def approved(self, row):
        ai_review.set_state(self.vault, row['operation_id'], 'approved')
        return ai_review.set_state(self.vault, row['operation_id'], 'applying')

    def row(self, patch, source='mcp', approve=True):
        payload, preview, snapshot = update.prepare_update(self.vault, self.q['uid'], self.q['question_id'],
                                                           blob_hash(self.content()), patch)
        row = ai_review.create(self.vault, source, 'propose_question_update' if source == 'mcp' else 'update_question_section',
                                uuid.uuid4().hex, payload, preview=preview, snapshot=snapshot,
                                pending=True, editable_fields=list(patch),
                                actor={'key_id': self.key['key_id']} if source == 'mcp' else
                                {'conversation_id': 'cv', 'run_id': 'run', 'tool_call_id': 'call'})
        return self.approved(row) if approve else row

    def crash(self, row, point='append_commit_in_db'):
        file = Path(self.temp.name) / 'operation.json'
        file.write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
        script = ('import json,os,sys\nfrom omrs import question_update as u\n'
                  'from omrs import question_update_journal as j\n'
                  'from unittest.mock import patch\n'
                  'row=json.load(open(sys.argv[2],encoding="utf-8"))\n'
                  'with patch.object(j,sys.argv[3],side_effect=lambda *a,**k: os._exit(73)):\n'
                  ' u.apply_update(sys.argv[1],row)\n')
        process = subprocess.run([sys.executable, '-c', script, self.vault, str(file), point], capture_output=True)
        self.assertEqual(process.returncode, 73, process.stderr.decode())

    def test_patch_preserves_system_sections_and_all_literal_images(self):
        content = self.content().replace('旧题干', '旧题干\n![[图.png|300]]\n![[图.png|300]]\n![答案图](附件/图(a).png)')
        content = content.replace('## 错因\n', '裸备注\n\n## 错因\n旧错因\n')
        content = content.replace('## 关联\n', '## 关联\n保留关联\n\n## 陌生小节\n不可丢失\n')
        self.path.write_text(content, encoding='utf-8')
        scan_workspace(self.vault)
        old = self.content()
        row = self.row({'question_text': '新题干', 'cause': '新错因', 'note': '补充文字'})
        result = update.apply_update(self.vault, row)
        current = self.content()
        self.assertIn('![[图.png|300]]\n![[图.png|300]]\n![答案图](附件/图(a).png)', current)
        for preserved in ('裸备注', '## 关联\n保留关联', '## 陌生小节\n不可丢失', '# 历史'):
            self.assertIn(preserved, current)
        self.assertIn('## 补充备注\n补充文字', current)
        self.assertEqual(update.note_of(current), '补充文字')
        self.assertEqual(result['before_hash'], blob_hash(old))
        self.assertTrue(verify_ledger(self.vault)['valid'])

    def test_image_changes_order_duplicates_and_bypasses_are_rejected(self):
        base = self.content().replace('旧题干', '旧题干\n![[一.png]]\n![[一.png]]\n![b](b.png)')
        scan_workspace(self.vault)
        proposals = ['新\n![[一.png]]\n![b](b.png)', '新\n![b](b.png)\n![[一.png]]\n![[一.png]]',
                     '新\n![[evil.png]]', '![a](https://example.com/evil.png)', '<img src="x">',
                     '![a][external]\n[external]: https://example.com/a.png', 'data:image/png;base64,AAAA',
                     '<picture><source srcset="x"></picture>']
        for proposal in proposals:
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                update.patch_content(base, {'question_text': proposal})
        image = '![b](b.png)'
        nested = self.content().replace('旧题干', '![a](file(a).png)')
        with self.assertRaises(ValueError):
            update.patch_content(nested, {'question_text': '![a](file(a).gif)'})
        with self.assertRaises(ValueError):
            update.patch_content(base, {'answer_text': image})

    def test_headers_and_unsafe_metadata_fail_before_any_write(self):
        for patch in ({'question_text': '正文\n# 历史\n覆盖'}, {'answer_text': '#\u00a0题目\n覆盖'},
                      {'cause': '## 关联\n覆盖'}, {'note': '# 历史\n覆盖'}, {'difficulty': True},
                      {'difficulty': 11}, {'difficulty': 1.5}, {'knowledge_points': ['a\r\nb']},
                      {'labels': ['a\x7fb']}, {'knowledge_points': ['\x1binject']},
                      {'tags': ['状态/已击杀']}, {'subject': '别科'}, {'question_id': 'OP-777777'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.row(patch)
        self.assertIn('旧题干', self.content())

    def test_duplicate_old_system_sections_refuse_edit(self):
        for appended in ('\n# 题目\n另一个题目', '\n# 备注\n其它备注'):
            with self.subTest(appended=appended), self.assertRaises(RequestError):
                update.patch_content(self.content() + appended, {'question_text': '新题干'})
        duplicate = self.content().replace('## 关联', '## 错因\n重复\n\n## 关联')
        with self.assertRaises(RequestError):
            update.patch_content(duplicate, {'note': '不能修改'})

    def test_json_yaml_scalar_roundtrip_preserves_literal_values(self):
        points = ['双引号"', "单引号'", '反斜杠\\路径', '冒号: 注释#原文', '带,逗号']
        row = self.row({'knowledge_points': points, 'difficulty': 10})
        update.apply_update(self.vault, row)
        meta = parse_yaml_frontmatter(self.content())
        self.assertEqual(extract_knowledge_tags(meta), points)
        self.assertEqual(meta['_omrs_id'], self.q['question_id'])
        self.assertEqual(meta['tags'], ['状态/待攻克'])
        self.assertEqual(int(meta['难度']), 10)
        projected = projection_row(self.vault, uid=self.q['uid'])
        self.assertEqual(projected['difficulty'], 10)

    def test_existing_labels_only_and_yamls_are_safe(self):
        from omrs.labels import save_label
        label = '计算"\\细节'
        save_label(self.vault, name=label)
        row = self.row({'labels': [label]})
        update.apply_update(self.vault, row)
        self.assertEqual(extract_labels(parse_yaml_frontmatter(self.content())), [label])
        with self.assertRaises(ValueError):
            self.row({'labels': ['从未创建']})

    def test_noop_has_receipt_but_no_new_fact(self):
        row = self.row({'question_text': '旧题干'})
        before = len(read_commits(self.vault))
        result = update.apply_update(self.vault, row)
        self.assertTrue(result['no_op'])
        self.assertEqual(result['commits'], [])
        self.assertEqual(before, len(read_commits(self.vault)))
        self.assertTrue(update.apply_update(self.vault, row)['reused'])

    def test_retry_returns_committed_result_even_after_later_manual_changes(self):
        row = self.row({'question_text': 'AI 新题干'})
        result = update.apply_update(self.vault, row)
        save_question_markdown(self.vault, self.q['uid'], self.content().replace('AI 新题干', '人工又改了'))
        before = len(read_commits(self.vault))
        retry = update.apply_update(self.vault, row)
        self.assertEqual(retry['commit_id'], result['commit_id'])
        self.assertTrue(retry['reused'])
        self.assertIn('人工又改了', self.content())
        self.assertEqual(before, len(read_commits(self.vault)))

    def test_changed_identity_hash_or_generation_refuses_old_approval(self):
        row = self.row({'question_text': '过期修改'})
        self.path.write_text(self.content().replace('旧题干', '外部修改'), encoding='utf-8')
        with self.assertRaises(RequestError):
            update.apply_update(self.vault, row)
        self.path.write_text(self.content().replace('外部修改', '旧题干'), encoding='utf-8')
        advance_generation(self.vault)
        with self.assertRaises(ai_review.ReviewError):
            update.apply_update(self.vault, row)
        self.assertIn('旧题干', self.content())

    def test_uid_reuse_cannot_retarget_original_identity(self):
        row = self.row({'question_text': '过期修改'})
        move_question(self.vault, self.q['uid'], '数学', '代数')
        fresh = create_question(self.vault, '数学', '函数', 5, question_text='新题')
        self.assertEqual(fresh['uid'], self.q['uid'])
        with self.assertRaises(RuntimeError):
            update.apply_update(self.vault, row)
        self.assertIn('新题', self.content())

    def test_original_request_digest_is_not_changed_by_human_revision(self):
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        base = blob_hash(self.content())
        original = propose(self.vault, key['key_id'], 'req', self.q['uid'], self.q['question_id'], base,
                           {'question_text': '模型版本'}, reason='修正题干')
        raw = ai_review.get(self.vault, original['operation_id'])
        payload, preview, snapshot = prepare_review(self.vault, raw, {'question_text': '人工修订'})
        self.assertEqual(snapshot, raw['snapshot'])
        revised = ai_review.revise(self.vault, raw['operation_id'], raw['revision'], payload, preview)
        self.assertEqual(revised['digest'], raw['digest'])
        self.assertNotEqual(revised['effective_digest'], raw['effective_digest'])
        self.assertEqual(revised['expires_at'], raw['expires_at'])
        with self.assertRaises(RequestError):
            prepare_review(self.vault, revised, {'answer_text': '非法扩大'})
        retried = propose(self.vault, key['key_id'], 'req', self.q['uid'], self.q['question_id'], base,
                          {'question_text': '模型版本'}, reason='修正题干')
        self.assertTrue(retried['reused'])
        self.assertEqual(retried['payload']['patch']['question_text'], '人工修订')
        result = update.apply_update(self.vault, self.approved(revised))
        self.assertEqual(result['fields']['question_text'], '人工修订')

    def test_agent_append_and_late_approval_record_original_actor(self):
        spec = update.prepare_agent(self.vault, 'update_question_section',
                                    {'uid': self.q['uid'], 'section': '答案', 'content': '追加', 'mode': 'append'})
        self.assertEqual(spec['editable_fields'], ['answer_text'])
        row = ai_review.create(self.vault, 'agent', 'update_question_section', 'agent-test', **spec,
                               actor={'conversation_id': 'cv', 'run_id': 'run', 'tool_call_id': 'call'}, pending=True)
        with agent_actor('cv', 'run', 'call'):
            result = update.apply_agent(self.vault, self.approved(row))
        self.assertIn('旧答案\n\n追加', self.content())
        self.assertTrue(result['wrote'])
        fact = read_commits(self.vault)[-1]
        self.assertEqual(fact['source'], 'agent')
        self.assertEqual(fact['payload']['_agent']['run_id'], 'run')
        self.assertEqual(fact['payload']['_ai_review']['operation_id'], row['operation_id'])

    def test_normal_failure_rolls_file_back_and_keeps_no_false_agent_commit(self):
        row = self.row({'question_text': '不能部分写入'}, source='agent')
        before = self.content()
        with agent_actor('cv', 'run', 'call') as actor:
            with mock.patch('omrs.question_update_journal.append_commit_in_db', side_effect=OSError('故障')):
                with self.assertRaises(OSError):
                    update.apply_update(self.vault, row)
            self.assertEqual(actor.commits, [])
        self.assertEqual(self.content(), before)
        self.assertIsNone(update.recover_receipt(self.vault, row))

    def test_pending_proposal_cannot_bypass_review_via_low_level_apply(self):
        row = self.row({'question_text': '未经批准'}, approve=False)
        before = self.content()
        with self.assertRaises(ai_review.ReviewError) as error:
            update.apply_update(self.vault, row)
        self.assertEqual(error.exception.code, 'state_conflict')
        self.assertEqual(self.content(), before)
        self.assertIsNone(update.recover_receipt(self.vault, row))

    def test_revoke_after_staging_blocks_file_replace_and_cleans_intent(self):
        from omrs import question_update_journal as journal
        row = self.row({'question_text': '撤权后不可写'})
        stage = journal._stage
        def revoke(*args):
            staged = stage(*args)
            revoke_key(self.vault, self.key['key_id'])
            return staged
        before = self.content()
        with mock.patch.object(journal, '_stage', side_effect=revoke):
            with self.assertRaises(ai_review.ReviewError) as error:
                update.apply_update(self.vault, row)
        self.assertEqual(error.exception.code, 'forbidden')
        self.assertEqual(self.content(), before)
        self.assertIsNone(update.recover_receipt(self.vault, row))
        self.assertEqual(list((Path(maintenance_dir(self.vault)) / 'question-updates').glob('*.json')), [])
        self.assertEqual(list(self.path.parent.glob('*.omrs-update-*')), [])

    def test_expiry_after_staging_blocks_file_replace(self):
        from omrs import question_update_journal as journal
        row = self.row({'question_text': '到期后不可写'})
        stage = journal._stage
        clock = [time.time()]
        def expire(*args):
            staged = stage(*args)
            clock[0] = row['expires_at'] + 1
            return staged
        before = self.content()
        with mock.patch.object(journal, '_stage', side_effect=expire), mock.patch('omrs.ai_review.time.time', side_effect=lambda: clock[0]):
            with self.assertRaises(ai_review.ReviewError) as error:
                update.apply_update(self.vault, row)
        self.assertEqual(error.exception.code, 'expired')
        self.assertEqual(self.content(), before)
        self.assertIsNone(update.recover_receipt(self.vault, row))

    def test_new_revision_after_staging_invalidates_held_authorization(self):
        from omrs import question_update_journal as journal
        row = self.row({'question_text': '旧版本不可写'})
        stage = journal._stage
        def revise(*args):
            staged = stage(*args)
            with ai_review._connect(self.vault, True) as db:
                db.execute('UPDATE operations SET revision=revision+1 WHERE operation_id=?', (row['operation_id'],))
                db.commit()
            return staged
        before = self.content()
        with mock.patch.object(journal, '_stage', side_effect=revise):
            with self.assertRaises(ai_review.ReviewError) as error:
                update.apply_update(self.vault, row)
        self.assertEqual(error.exception.code, 'revision_conflict')
        self.assertEqual(self.content(), before)

    def test_agent_abort_after_staging_blocks_file_replace(self):
        from omrs import question_update_journal as journal
        row = self.row({'question_text': '中止后不可写'}, source='agent')
        stage = journal._stage
        def abort(*args):
            staged = stage(*args)
            self.run.abort.set()
            return staged
        before = self.content()
        with agent_actor('cv', 'run', 'call'), mock.patch.object(journal, '_stage', side_effect=abort):
            with self.assertRaises(ai_review.ReviewError) as error:
                update.apply_update(self.vault, row)
        self.assertEqual(error.exception.code, 'interrupted')
        self.assertEqual(self.content(), before)
        self.assertIsNone(update.recover_receipt(self.vault, row))

    def test_process_crash_before_fact_rolls_back_only_owned_file(self):
        row = self.row({'question_text': '中断题干'})
        before = self.content()
        self.crash(row)
        self.assertIn('中断题干', self.content())
        recovered = update.recover_pending(self.vault)
        self.assertEqual(recovered['rolled_back'], 1)
        self.assertEqual(before, self.content())
        self.assertIsNone(update.recover_receipt(self.vault, row))

    def test_process_crash_after_fact_recovers_receipt_without_rewriting(self):
        row = self.row({'question_text': '已提交'})
        self.crash(row, 'refresh_projection')
        committed = update.recover_receipt(self.vault, row)
        self.assertIsNotNone(committed)
        self.path.write_text(self.content().replace('已提交', '之后人工编辑'), encoding='utf-8')
        self.assertEqual(update.recover_pending(self.vault)['committed'], 1)
        self.assertIn('之后人工编辑', self.content())

    def test_interrupted_write_does_not_overwrite_new_owner_or_later_fact(self):
        row = self.row({'question_text': '中断题干'})
        self.crash(row)
        saved = self.content()
        replacement = self.path.with_suffix('.replacement')
        replacement.write_text(saved, encoding='utf-8')
        os.replace(replacement, self.path)
        with self.assertRaisesRegex(RequestError, '不再属于'):
            update.recover_pending(self.vault)
        self.assertEqual(saved, self.content())

    def test_later_fact_prevents_blind_rollback(self):
        row = self.row({'question_text': '中断题干'})
        self.crash(row)
        append_commit(self.vault, 'api', 'system.test', '新事实', {'test': True})
        with self.assertRaisesRegex(RequestError, '其它事实'):
            update.recover_pending(self.vault)
        self.assertIn('中断题干', self.content())

    def test_old_generation_journal_never_touches_restored_library(self):
        row = self.row({'question_text': '旧世代中断'})
        self.crash(row)
        advance_generation(self.vault)
        self.path.write_text(self.content().replace('旧世代中断', '恢复后的正文'), encoding='utf-8')
        self.assertEqual(update.recover_pending(self.vault)['obsolete'], 1)
        self.assertIn('恢复后的正文', self.content())
        self.assertTrue(list((Path(maintenance_dir(self.vault)) / 'question-updates').glob('*.obsolete')))

    def test_readonly_audit_refuses_pending_intent_and_symlink_paths(self):
        row = self.row({'question_text': '中断题干'})
        self.crash(row)
        with self.assertRaises(RequestError):
            update.recover_pending(self.vault, allow_recovery=False)
        update.recover_pending(self.vault)
        linked = self.path.with_suffix('.linked')
        self.path.rename(linked)
        self.path.symlink_to(linked)
        with self.assertRaises(RequestError):
            self.row({'question_text': '拒绝链接'})

    def test_shared_reads_expose_identity_difficulty_and_bounded_note(self):
        from omrs.agent.tools.read import get_question
        from omrs.mcp.queries import question_content
        row = self.row({'note': '补充说明' * 3000, 'difficulty': 7})
        update.apply_update(self.vault, row)
        result = get_question({'vault': self.vault}, {'uid': self.q['uid']})['result']
        self.assertEqual(result['question_id'], self.q['question_id'])
        self.assertEqual(result['difficulty'], 7)
        self.assertIn('补充说明', result['note'])
        content = question_content(self.vault, self.q['uid'], limit=100)
        self.assertEqual(content['question_id'], self.q['question_id'])
        self.assertEqual(content['difficulty'], 7)
        self.assertEqual(len(content['note']), 100)
        self.assertTrue(content['note_truncated'])
        self.assertEqual(content['note_total_chars'], 12000)


if __name__ == '__main__':
    unittest.main()
