"""静态配图安全、纸面尺寸、不可覆盖版本及审核回执。"""
import base64
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

from omrs import question_svg as svg, ai_review, question_update
from omrs.creation import create_question
from omrs.ledger import blob_hash, verify_ledger
from omrs.mcp.keys import create_key, revoke_key
from omrs.mcp.question_write import propose
from omrs.question_images import read_attachment_image
from omrs import uploads


def diagram(label='力 F', size=14, height=200, extra=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 340 {height}" width="340" height="{height}">'
            '<title>受力示意图</title><rect width="340" height="'+str(height)+'" fill="white"/>'
            '<rect x="120" y="90" width="80" height="50" fill="#ddd" stroke="black" stroke-width="1.2"/>'
            '<path d="M160 90V35M155 42L160 35L165 42" fill="none" stroke="black" stroke-width="1.2"/>'
            f'<text x="175" y="60" font-size="{size}">{label}</text>{extra}</svg>').encode()


class SvgTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-svg-')
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name

    @unittest.skipUnless(os.name == 'posix', '进程组超时回收只在POSIX实测')
    def test_png_timeout_reaps_renderer_children_and_releases_slot(self):
        marker = Path(self.vault)/'child.pid'
        code = '''
import os, signal, subprocess, sys, time
def stop(*_args):
    raise SystemExit(1)
signal.signal(signal.SIGTERM, stop)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
try:
    with open(sys.argv[1], 'w') as stream:
        stream.write(str(child.pid))
    time.sleep(60)
finally:
    child.terminate()
    child.wait()
'''
        real_popen = subprocess.Popen

        def hanging_renderer(_command, **options):
            process = real_popen([sys.executable, '-c', code, str(marker)], **options)
            communicate = process.communicate
            process.communicate = lambda *args, timeout=None: communicate(
                *args, timeout=.5 if timeout == 30 else timeout)
            return process

        with mock.patch.object(svg.subprocess, 'Popen', side_effect=hanging_renderer):
            with self.assertRaisesRegex(ValueError, '转PNG超时'):
                svg.to_png(diagram('超时测试'))
        self.assertTrue(marker.exists(), '模拟渲染器应已启动子进程')
        with self.assertRaises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)
        acquired = 0
        try:
            for _ in range(2):
                self.assertTrue(svg._PNG_SLOTS.acquire(blocking=False))
                acquired += 1
        finally:
            for _ in range(acquired):
                svg._PNG_SLOTS.release()

    def test_print_profile_and_density_warnings(self):
        info = svg.inspect(diagram())
        self.assertGreater(info['min_font_pt'], 8.5)
        self.assertLess(info['print_height_mm'], 70)
        self.assertEqual(info['warnings'], [])
        labels = ''.join(f'<text x="10" y="{15+i*20}" font-size="14">标注{i}</text>' for i in range(13))
        self.assertTrue(svg.inspect(diagram(height=300, extra=labels))['warnings'])

    def test_invalid_and_unreadable_svg_is_rejected(self):
        bad = [diagram(size=8), diagram(height=350), diagram().replace(b'1.2', b'.2'),
               diagram().replace(b'<text ', b'<text transform="scale(.5)" '),
               diagram().replace(b'<text ', b'<text textLength="2" '),
               diagram().replace(b'<title>', b'<script>alert(1)</script><title>'),
               diagram(extra='<image href="https://example.com/a.png"/>'),
               diagram(extra='<foreignObject/>'), diagram(extra='<animate/>'),
               diagram(extra='<use href="#x"/>'), diagram(extra='<g onclick="alert(1)"/>'),
               diagram(extra='<g style="clip-path:url(#ink)"/><linearGradient id="ink"/>'),
               diagram().replace(b'fill="white"', b'fill="none"', 1),
               diagram().replace(b'viewBox=', b'transform="scale(.5)" viewBox='),
               diagram().replace(b'<text ', b'<text font-stretch="condensed" '),
               diagram().replace(b'<text ', b'<text letter-spacing="-2" '),
               b'<!DOCTYPE svg [<!ENTITY x "bad">]>'+diagram(), b'bad', b'x'*(svg.MAX_BYTES+1)]
        for raw in bad:
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError):
                svg.inspect(raw)

    def test_inherited_transforms_and_tspan_tail_cannot_hide_small_type(self):
        raw = diagram().replace(b'<text x="175" y="60" font-size="14">',
                                b'<g transform="scale(2)"><text x="50" y="30" font-size="7">')
        raw = raw.replace(b'</text>', b'</text></g>')
        self.assertAlmostEqual(svg.inspect(raw)['min_font_pt'], svg.inspect(diagram())['min_font_pt'])
        tiny_tail = diagram().replace(b'font-size="14"', b'font-size="4"').replace(
            '力 F'.encode(), '<tspan font-size="14">大字</tspan>小字'.encode())
        with self.assertRaisesRegex(ValueError, '至少8.5pt'):
            svg.inspect(tiny_tail)

    def test_save_without_directory_fds_and_unsafe_directories(self):
        folder = Path(self.vault)/'错题'
        folder.mkdir()
        with mock.patch('omrs.question_images._DIRECTORY_FDS', False):
            name, _ = svg.save(self.vault, 'OP-123456', diagram())
            self.assertEqual(svg.save(self.vault, 'OP-123456', diagram())[0], name)
            self.assertEqual(read_attachment_image(self.vault, name)[0], diagram())
            target = folder/'附件'/name
            target.write_bytes(diagram(label='外部修改'))
            with self.assertRaisesRegex(ValueError, '不能覆盖'):
                svg.save(self.vault, 'OP-123456', diagram())
        target.unlink()
        (folder/'附件').rmdir()
        outside = Path(self.vault)/'outside'
        outside.mkdir()
        (folder/'附件').symlink_to(outside, target_is_directory=True)
        for use_fds in (True, False):
            with mock.patch('omrs.question_images._DIRECTORY_FDS', use_fds), self.assertRaises(ValueError):
                svg.save(self.vault, 'OP-123456', diagram())
        self.assertEqual(list(outside.iterdir()), [])

    def proposal(self, replacement=''):
        q = create_question(self.vault, '物理', '力学', 5, question_text='分析受力', answer_text='平衡')
        path = Path(self.vault)/q['file_path']
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        patch = {'diagrams': [{'section': '答案', 'svg': diagram().decode(), 'replace': replacement}]}
        result = propose(self.vault, key['key_id'], uuid.uuid4().hex, q['uid'], q['question_id'],
                         blob_hash(path.read_text()), patch, reason='补充受力图')
        return q, path, key, ai_review.get(self.vault, result['operation_id'])

    def test_rejection_revocation_and_changed_body_do_not_create_attachments(self):
        for action in ('reject', 'revoke', 'change'):
            q, path, key, row = self.proposal()
            before = path.read_bytes()
            if action == 'revoke':
                revoke_key(self.vault, key['key_id'])
            if action == 'change':
                before += '\n外部编辑\n'.encode()
                path.write_bytes(before)
            decided = ai_review.decide(self.vault, row['operation_id'], 1, 'reject' if action == 'reject' else 'approve')
            self.assertIn(decided['status'], ('rejected', 'conflict'))
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((Path(self.vault)/'错题'/'附件').exists())

    def test_agent_diagram_only_append_preserves_text_and_images(self):
        q = create_question(self.vault, '物理', '力学', 5, question_text='原题面', answer_text='原答案')
        prepared = question_update.prepare_agent(self.vault, 'update_question_section', {
            'uid': q['uid'], 'section': '答案', 'mode': 'append', 'content': '',
            'diagrams': [{'section': '答案', 'svg': diagram().decode()}]})
        self.assertEqual(prepared['payload']['patch']['answer_text'].strip(), '原答案')
        final = question_update.patch_content((Path(self.vault)/q['file_path']).read_text(), prepared['payload']['patch'])
        self.assertIn('原题面', final)
        self.assertIn('原答案', final)
        self.assertEqual(len(prepared['preview']['diagrams']), 1)
        self.assertFalse((Path(self.vault)/'错题'/'附件').exists())

    def test_changed_replacement_source_conflicts_before_saving(self):
        q = create_question(self.vault, '物理', '力学', 5, question_text='分析受力\n![[manual.svg]]')
        folder = Path(self.vault)/'错题'/'附件'
        folder.mkdir()
        (folder/'manual.svg').write_bytes(diagram())
        path = Path(self.vault)/q['file_path']
        before = path.read_bytes()
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        result = propose(self.vault, key['key_id'], 'replace', q['uid'], q['question_id'], blob_hash(path.read_text()),
                         {'diagrams': [{'section': '题目', 'svg': diagram('新图').decode(), 'replace': 'manual.svg'}]}, reason='替换')
        (folder/'manual.svg').write_bytes(diagram('外部变图'))
        decided = ai_review.decide(self.vault, result['operation_id'], 1, 'approve')
        self.assertEqual(decided['status'], 'conflict')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(folder.iterdir())), 1)

    def test_process_crash_keeps_attachment_and_rolls_back_body_then_retries(self):
        q, path, _key, row = self.proposal()
        before = path.read_bytes()
        ai_review.set_state(self.vault, row['operation_id'], 'approved')
        row = ai_review.set_state(self.vault, row['operation_id'], 'applying')
        operation = Path(self.vault)/'operation.json'
        operation.write_text(json.dumps(row))
        script = ('import json,os,sys\nfrom unittest.mock import patch\n'
                  'from omrs import question_update as u,question_update_journal as j\n'
                  'with patch.object(j,"append_commit_in_db",side_effect=lambda *a,**k: os._exit(73)):\n'
                  ' u.apply_update(sys.argv[1],json.load(open(sys.argv[2])))\n')
        result = subprocess.run([sys.executable, '-c', script, self.vault, str(operation)], capture_output=True)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertNotEqual(path.read_bytes(), before)
        self.assertEqual(question_update.recover_pending(self.vault)['rolled_back'], 1)
        self.assertEqual(path.read_bytes(), before)
        applied = question_update.apply_update(self.vault, row)
        self.assertEqual(read_attachment_image(self.vault, applied['fields']['diagrams'][0])[0], diagram())
        self.assertTrue(verify_ledger(self.vault)['valid'])

    def test_vector_export_and_backup_restore_preserve_original_bytes(self):
        from omrs import boards, exporting, mcp_exports, backup_store, optimization
        raw = diagram()
        q = create_question(self.vault, '物理', '力学', 5, question_text='分析受力',
                            question_images=['data:'+svg.MIME+';base64,'+base64.b64encode(raw).decode()])
        board = boards.create_board(self.vault, '配图打印', [q['uid']])
        export = mcp_exports.create(self.vault, board['id'], 'all', 'svg-export', 'key', 'http://localhost:9999')
        html = mcp_exports.download(self.vault, export['export_id'])[0]
        self.assertIn(base64.b64encode(raw), html)
        with mock.patch.object(mcp_exports, 'MAX_BYTES', 500):
            with self.assertRaisesRegex(ValueError, '64 MiB'):
                mcp_exports.create(self.vault, board['id'], 'all', 'too-big', 'key', 'http://localhost:9999')
        image = Path(self.vault)/'错题'/'附件'/q['images'][0]
        self.assertIn(str(image), optimization._image_files(self.vault))
        archive, _, _, _ = backup_store.create_backup(self.vault)
        self.addCleanup(lambda: os.path.exists(archive) and os.unlink(archive))
        with tempfile.TemporaryDirectory(prefix='omrs-svg-restored-') as restored:
            prepared = backup_store.prepare_import(restored, archive)
            self.assertEqual(prepared['preview']['image_files'], 1)
            backup_store.restore(restored, prepared['restore_id'], True)
            self.assertEqual(read_attachment_image(restored, q['images'][0])[0], raw)
        image.write_bytes(diagram('同名篡改'))
        with self.assertRaisesRegex(ValueError, '同名修改'):
            exporting.export_board_html(self.vault, board['id'])

    def test_create_upload_and_hash_checked_attachment(self):
        raw = diagram()
        uploaded = uploads.start(self.vault, 'figure.svg', svg.MIME, len(raw), 'create')
        uploads.chunk(self.vault, uploaded['upload_id'], 0, raw)
        completed = uploads.complete(self.vault, uploaded['upload_id'])
        self.assertEqual(completed['mime'], svg.MIME)
        self.assertEqual(completed['svg']['title'], '受力示意图')
        q = create_question(self.vault, '物理', '力学', 5, question_text='分析受力',
                            question_images=[{'upload_ref': completed['upload_ref']}])
        name = q['images'][0]
        self.assertTrue(svg.MANAGED.fullmatch(name))
        self.assertEqual(read_attachment_image(self.vault, name), (raw, svg.MIME))
        path = Path(self.vault)/'错题'/'附件'/name
        path.write_bytes(diagram(label='另一幅图'))
        with self.assertRaisesRegex(ValueError, '同名修改'):
            read_attachment_image(self.vault, name)

    def test_approval_add_replace_and_retries_preserve_previous_file(self):
        q = create_question(self.vault, '物理', '力学', 5, question_text='分析受力', answer_text='平衡')
        path = Path(self.vault)/q['file_path']
        key = create_key(self.vault, scopes=['omrs:read', 'question:propose'])
        old_files = []
        first_hash = ''
        for label in ('力 F', '力 G'):
            patch = {'diagrams': [{'section': '答案', 'svg': diagram(label).decode(),
                                   **({'replace': old_files[-1]} if old_files else {})}]}
            result = propose(self.vault, key['key_id'], uuid.uuid4().hex, q['uid'], q['question_id'],
                             blob_hash(path.read_text()), patch, reason='补充受力图')
            row = ai_review.get(self.vault, result['operation_id'])
            self.assertEqual(len(row['preview']['diagrams']), 1)
            if not old_files:
                self.assertFalse((Path(self.vault)/'错题'/'附件').exists())
            ai_review.set_state(self.vault, row['operation_id'], 'approved')
            row = ai_review.set_state(self.vault, row['operation_id'], 'applying')
            applied = question_update.apply_update(self.vault, row)
            if not first_hash:
                first_hash = applied['after_hash']
            self.assertTrue(question_update.apply_update(self.vault, row)['reused'])
            old_files.append(applied['fields']['diagrams'][0])
        self.assertNotEqual(*old_files)
        for name in old_files:
            self.assertTrue((Path(self.vault)/'错题'/'附件'/name).is_file())
        self.assertNotIn(old_files[0], path.read_text())
        self.assertIn(old_files[1], path.read_text().split('# 答案')[1])
        from omrs.content_history import restore_content
        restore_content(self.vault, q['uid'], first_hash, expected_hash=blob_hash(path.read_text()))
        self.assertIn(old_files[0], path.read_text())
        self.assertNotIn(old_files[1], path.read_text())
        self.assertEqual(read_attachment_image(self.vault, old_files[0])[0], diagram('力 F'))
        self.assertTrue(verify_ledger(self.vault)['valid'])


if __name__ == '__main__':
    unittest.main()
