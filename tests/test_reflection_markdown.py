"""Markdown 唯一正文、旧库归并、编辑并发及真实进程中断恢复。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from omrs import problem_store, problems, reflection_journal, reflection_markdown as md
from omrs.content_history import projection_row, question_file
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.exporting import _parse_notes_subsections
from omrs.ledger import blob_hash, connect, verify_ledger
from omrs.question_update import patch_content


class ReflectionMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='reflection-markdown-')
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.q = create_question(self.vault, '数学', '统一错因', 5, question_text='纯合成题',
                                 cause='旧错因原文\n\n```md\n## 代码里的标题\n```')
        self.row = projection_row(self.vault, uid=self.q['uid'])
        self.qid = self.row['question_id']
        self.file = Path(question_file(self.vault, self.row))
        self.mastery = mastery_rows(self.vault)
        self.n = 0

    def write(self, action='add_reflection_entry', **data):
        self.n += 1
        data.setdefault('request_id', f'markdown-test-{self.n}')
        if action == 'add_reflection_entry':
            data.setdefault('question_id', self.qid)
            data.setdefault('content_md', '新观察')
        return problems.execute(self.vault, action, data)

    def entries(self):
        return problems.reflections(self.vault, self.qid)['items']

    def test_legacy_read_preserves_file_and_unknown_date_without_creating_database(self):
        before = self.file.read_bytes()
        item = self.entries()[0]
        self.assertIsNone(item['occurred_at'])
        self.assertIsNone(item['created_at'])
        self.assertIn('## 代码里的标题', item['content_md'])
        self.assertEqual(before, self.file.read_bytes())
        self.assertFalse(Path(problem_store.path(self.vault)).exists())

    def test_arbitrary_markdown_dates_history_and_other_sections_roundtrip(self):
        before = self.file.read_text()
        body = '# 观察\n\n## 原因\n\n### 2026-11-01\n\n> 引用\n\n```md\n## 关联\n```\n\n<!-- 注释 -->'
        created = self.write(content_md=body, occurred_at='2026-11-15')['entry']
        text = self.file.read_text()
        self.assertIn('### 2026-11-15 · ' + created['id'], text)
        self.assertIn('> # 观察', text)
        parsed = md.parse(text, self.qid)
        self.assertEqual(next(e for e in parsed if e['id'] == created['id'])['content_md'], body)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(md.without_cause(md.notes_of(text)), md.without_cause(md.notes_of(before)))
        self.assertEqual(mastery_rows(self.vault), self.mastery)
        self.assertTrue(verify_ledger(self.vault)['valid'])

    def test_revise_withdraw_and_export_use_markdown_and_keep_old_versions(self):
        first = self.write(content_md='初次观察', occurred_at='2026-11-14')['entry']
        second = self.write('revise_reflection_entry', id=first['id'], expected_revision=1,
                            content_md='修订后的观察', reason='补全依据')['entry']
        self.assertEqual(second['revision'], 2)
        parsed = next(e for e in md.parse(self.file.read_text(), self.qid) if e['id'] == first['id'])
        self.assertEqual(parsed['revisions'][-1]['value']['content_md'], '初次观察')
        exported = _parse_notes_subsections(md.notes_of(self.file.read_text()))['错因']
        self.assertIn('修订后的观察', exported)
        self.assertNotIn('omrs-reflection', exported)
        self.write('revise_reflection_entry', id=first['id'], expected_revision=2, withdrawn=True, reason='记录有误')
        exported = _parse_notes_subsections(md.notes_of(self.file.read_text()))['错因']
        self.assertNotIn('修订后的观察', exported)
        self.assertIn('旧错因原文', exported)

    def test_native_retry_has_one_file_entry_and_one_ledger_change(self):
        one = self.write(request_id='same-request')['entry']
        before = self.file.read_bytes()
        with connect(self.vault) as db:
            count = db.execute('SELECT COUNT(*) FROM commits').fetchone()[0]
        two = self.write(request_id='same-request')['entry']
        self.assertEqual(one['id'], two['id'])
        self.assertEqual(before, self.file.read_bytes())
        with connect(self.vault) as db:
            self.assertEqual(count, db.execute('SELECT COUNT(*) FROM commits').fetchone()[0])
        with problem_store.connect(self.vault) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM objects WHERE kind='entry'").fetchone()[0], 0)

    def test_editing_markdown_is_authoritative_and_stale_form_cannot_overwrite(self):
        entry = self.write(content_md='原观察')['entry']
        loaded = next(e for e in self.entries() if e['id'] == entry['id'])
        self.file.write_text(self.file.read_text().replace('> 原观察', '> 外部更新的观察'))
        self.assertEqual(next(e for e in self.entries() if e['id'] == entry['id'])['content_md'], '外部更新的观察')
        with self.assertRaises(problems.ProblemConflict):
            self.write('revise_reflection_entry', id=entry['id'], expected_revision=loaded['revision'],
                       expected_content_hash=loaded['content_hash'], content_md='过期表单', reason='旧页')
        self.write(content_md='后续观察')
        self.assertIn('外部更新的观察', [e['content_md'] for e in self.entries()])

    def test_removed_markdown_entry_does_not_return_from_database_index(self):
        entry = self.write()['entry']
        remaining = [e for e in md.parse(self.file.read_text(), self.qid) if e['id'] != entry['id']]
        self.file.write_text(md.replace(self.file.read_text(), remaining))
        self.assertNotIn(entry['id'], [e['id'] for e in self.entries()])
        with self.assertRaises(ValueError):
            self.write('revise_reflection_entry', id=entry['id'], expected_revision=1, reason='已移除')

    def test_external_edit_between_reads_keeps_snapshot_hash_and_blocks_stale_revision(self):
        from omrs import question_update
        entry = self.write(content_md='原观察')['entry']
        before = self.file.read_text()
        external = before.replace('> 原观察', '> 外部编辑')
        original_read = question_update._read

        def edit_after_read(*args):
            result = original_read(*args)
            self.file.write_text(external)
            return result

        with patch.object(question_update, '_read', side_effect=edit_after_read):
            loaded = next(e for e in self.entries() if e['id'] == entry['id'])
        self.assertEqual(loaded['content_md'], '原观察')
        self.assertEqual(loaded['content_hash'], blob_hash(before))

        self.file.write_text(before)
        with patch.object(question_update, '_read', side_effect=edit_after_read):
            with self.assertRaises(problems.ProblemConflict):
                self.write('revise_reflection_entry', id=entry['id'], expected_revision=1,
                           content_md='旧网页修订', reason='读取期间被外部修改')
        self.assertEqual(self.file.read_text(), external)

    def test_date_edit_changes_version_and_code_fence_does_not_create_records(self):
        entry = self.write(content_md='日期校对', occurred_at='2026-11-14')['entry']
        content = self.file.read_text().replace('### 2026-11-14 ·', '### 2026-11-15 ·')
        edited = next(e for e in md.parse(content, self.qid) if e['id'] == entry['id'])
        self.assertEqual((edited['occurred_at'], edited['revision']), ('2026-11-15', 2))
        plain = '# 备注\n## 错因记录\n```md\n### 2026-11-15\n```\n普通错因\n'
        self.assertFalse(md.structured(plain))
        self.assertIn('替换旧错因', patch_content(plain, {'cause':'替换旧错因'}))

    def test_manual_date_format_and_legacy_whole_section_update_protection(self):
        content = self.file.read_text().replace('旧错因原文', '### 2026-11-12\n检查负号')
        self.file.write_text(content)
        entry = self.entries()[0]
        self.assertEqual(entry['occurred_at'], '2026-11-12')
        self.assertIn('检查负号', entry['content_md'])
        with self.assertRaisesRegex(ValueError, '不能整段覆盖'):
            patch_content(content, {'cause':'覆盖历史'})
        saved = self.write('revise_reflection_entry', id=entry['id'], expected_revision=1,
                           content_md='核对负号', reason='手写日期记录可修订')['entry']
        self.assertEqual(saved['occurred_at'], '2026-11-12')

    def test_old_database_records_merge_once_with_original_id_and_evidence(self):
        old = {'id':'REF-old-database', 'question_id':self.qid, 'content_md':'旧数据库观察',
               'occurred_at':'2026-10-02', 'created_at':1234, 'updated_at':1234, 'revision':1,
               'problem_ids':[], 'recurrence_of':'', 'withdrawn':False,
               'source':{'kind':'mcp'}, 'basis':'ai_hypothesis'}
        with problem_store.connect(self.vault, True) as db:
            problem_store.save(db, 'entry', old)
            db.execute('INSERT INTO events(object_id,data) VALUES(?,?)',
                       (old['id'], problem_store.dumps({'action':'add_reflection_entry', 'value':old, 'reason':'原证据'})))
        before = self.file.read_bytes()
        self.assertEqual(len(self.entries()), 2)
        self.assertEqual(before, self.file.read_bytes())
        self.assertEqual(problems.migrate_legacy(self.vault), 1)
        self.assertEqual(problems.migrate_legacy(self.vault), 0)
        moved = next(e for e in self.entries() if e['id'] == old['id'])
        for key in ('content_md', 'occurred_at', 'created_at', 'source', 'basis'):
            self.assertEqual(moved[key], old[key])
        self.assertEqual(moved['revisions'][-1]['reason'], '原证据')
        self.assertEqual(mastery_rows(self.vault), self.mastery)

    def test_transaction_error_restores_file_and_problem_links(self):
        before = self.file.read_bytes()
        problem = self.write('create_problem', title='新问题')['problem']
        original = problem_store.save
        def fail(db, kind, value):
            if kind == 'entry_ref':
                raise RuntimeError('模拟事务失败')
            return original(db, kind, value)
        with patch.object(problem_store, 'save', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, '模拟事务失败'):
                self.write(problem_ids=[problem['id']])
        self.assertEqual(before, self.file.read_bytes())
        self.assertEqual(problems.get(self.vault, problem['id'])['questions'], [])
        self.assertEqual(problems.get(self.vault, problem['id'])['revision'], 1)

    def test_real_process_crashes_before_and_after_domain_commit(self):
        for point, committed in [('problem-save', False), ('finish', True), ('ledger-append', True), ('projection', True)]:
            with self.subTest(point=point):
                before = self.file.read_bytes()
                payload = {'question_id':self.qid, 'content_md':'中断窗口 ' + point, 'request_id':'crash-' + point}
                script = '''import json,os,sys
from unittest.mock import patch
from omrs import problems,problem_store,reflection_journal
point=sys.argv[3]
target,name={'problem-save':(problem_store,'save'),'finish':(reflection_journal,'finish'),
 'ledger-append':(reflection_journal,'append_commit_in_db'),'projection':(reflection_journal,'refresh_projection')}[point]
with patch.object(target,name,side_effect=lambda *a,**k:os._exit(73)):
 problems.execute(sys.argv[1],'add_reflection_entry',json.loads(sys.argv[2]))
'''
                proc = subprocess.run([sys.executable, '-c', script, self.vault, json.dumps(payload), point], capture_output=True)
                self.assertEqual(proc.returncode, 73, proc.stderr.decode())
                reflection_journal.recover_pending(self.vault)
                bodies = [e['content_md'] for e in self.entries()]
                self.assertEqual(payload['content_md'] in bodies, committed)
                if not committed:
                    self.assertEqual(before, self.file.read_bytes())
                else:
                    count = len(bodies)
                    problems.execute(self.vault, 'add_reflection_entry', payload)
                    self.assertEqual(len(self.entries()), count)
                self.assertTrue(verify_ledger(self.vault)['valid'])
                self.assertEqual(mastery_rows(self.vault), self.mastery)

    def test_duplicate_or_invalid_date_does_not_silently_discard_records(self):
        content = self.file.read_text()
        for body in ['### 2026-02-30\n无效日期', '## 错因\n重复分节']:
            with self.subTest(body=body), self.assertRaises(ValueError):
                md.parse(content.replace('旧错因原文', body), self.qid)


if __name__ == '__main__':
    unittest.main()
