"""服务端 PDF 的并发、子进程期限和失败契约。"""
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from omrs import export_pdf
from omrs.export_pdf import PdfExportError


class PdfExportTests(unittest.TestCase):
    def test_busy_does_not_queue_and_error_releases_slot(self):
        with self.assertRaisesRegex(ValueError, '合成错误'), export_pdf.render_slot():
            with self.assertRaises(PdfExportError) as busy, export_pdf.render_slot():
                self.fail('忙碌时不可取得第二个名额')
            self.assertEqual((busy.exception.status, busy.exception.code), (503, 'pdf_busy'))
            raise ValueError('合成错误')
        with export_pdf.render_slot():
            pass

    def test_timeout_reaps_worker_and_releases_slot(self):
        child = MagicMock()
        child.communicate.side_effect = [subprocess.TimeoutExpired('worker', 45), (b'', b'')]
        with patch.object(export_pdf.subprocess, 'Popen', return_value=child) as launch, \
                patch.object(export_pdf, 'stop_renderer') as stop:
            with self.assertRaises(PdfExportError) as timed_out, export_pdf.render_slot():
                export_pdf.render(b'html')
        self.assertEqual((timed_out.exception.status, timed_out.exception.code), (504, 'pdf_timeout'))
        self.assertIn('omrs.export_pdf', launch.call_args.args[0])
        child.communicate.assert_any_call(b'html', timeout=45)
        stop.assert_called_once_with(child)
        with export_pdf.render_slot():
            pass

    def test_child_error_contract_and_incomplete_pdf(self):
        child = MagicMock()
        child.returncode = 1
        child.communicate.return_value = (b'', json.dumps({
            'message': '服务端 Chromium 无法启动', 'status': 503, 'code': 'pdf_unavailable',
        }).encode())
        with patch.object(export_pdf.subprocess, 'Popen', return_value=child), export_pdf.render_slot():
            with self.assertRaisesRegex(PdfExportError, 'Chromium 无法启动') as unavailable:
                export_pdf.render(b'html')
            self.assertEqual((unavailable.exception.status, unavailable.exception.code), (503, 'pdf_unavailable'))
            child.returncode = 0
            child.communicate.return_value = (b'%PDF-1.4\n', b'')
            with self.assertRaisesRegex(PdfExportError, '未生成完整'):
                export_pdf.render(b'html')
