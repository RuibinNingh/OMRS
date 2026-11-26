"""把自包含 A4 文档在独立 Chromium 进程内定稿为 PDF。"""
import json
import os
import signal
import subprocess
import sys
from contextlib import contextmanager
from threading import BoundedSemaphore

from .render_process import stop_renderer


RENDER_TIMEOUT = 45
_SLOT = BoundedSemaphore(1)
_HEAD = (
    '<head><meta name="omrs-render" content="pdf">'
    '<meta http-equiv="Content-Security-Policy" content="'
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; base-uri 'none'; form-action 'none'\">"
)


class PdfExportError(RuntimeError):
    def __init__(self, message, status, code):
        super().__init__(message)
        self.status = status
        self.code = code


@contextmanager
def render_slot():
    if not _SLOT.acquire(blocking=False):
        raise PdfExportError('正在生成另一份 PDF，请稍后重试', 503, 'pdf_busy')
    try:
        yield
    finally:
        _SLOT.release()


def render(html):
    """调用方持有渲染名额，HTML 已从 Vault 读入快照。"""
    try:
        process = subprocess.Popen(
            [sys.executable, '-m', 'omrs.export_pdf'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=os.name != 'nt',
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
    except OSError as exc:
        raise PdfExportError('无法启动 PDF 渲染进程，请稍后重试或选择 A4 HTML', 503, 'pdf_unavailable') from exc
    with process:
        try:
            payload, errors = process.communicate(html, timeout=RENDER_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            stop_renderer(process)
            process.communicate()
            raise PdfExportError('PDF 生成超时，请减少本次选题或选择 A4 HTML', 504, 'pdf_timeout') from exc
    if process.returncode:
        try:
            error = json.loads(errors.splitlines()[-1])
            failure = PdfExportError(error['message'], error['status'], error['code'])
        except (IndexError, ValueError, TypeError, KeyError):
            failure = PdfExportError('PDF 渲染失败，请重试或选择 A4 HTML', 500, 'pdf_render')
        raise failure
    if not payload.startswith(b'%PDF-') or not payload.rstrip().endswith(b'%%EOF'):
        raise PdfExportError('未生成完整的 PDF，请重试', 500, 'pdf_render')
    return payload


def _render(html):
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as exc:
        raise PdfExportError('服务端缺少 Playwright，请安装 Chromium 渲染依赖或选择 A4 HTML',
                             503, 'pdf_unavailable') from exc

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            raise PdfExportError('服务端 Chromium 无法启动，请检查渲染依赖或选择 A4 HTML',
                                 503, 'pdf_unavailable') from exc
        try:
            context = browser.new_context(
                viewport={'width': 1024, 'height': 1123}, device_scale_factor=1,
                locale='zh-CN', service_workers='block',
            )
            render_errors = []

            def block_request(route):
                render_errors.append('network')
                route.abort()

            context.route('**/*', block_request)
            page = context.new_page()
            page.set_default_timeout(0)  # 总期限由父进程执行，包含浏览器退出。
            page.on('pageerror', lambda _error: render_errors.append('script'))
            page.emulate_media(media='print')
            page.set_content(html.decode('utf-8').replace('<head>', _HEAD, 1), wait_until='load')
            page.locator('html[data-omrs-layout-ready]').wait_for(state='attached')
            result = page.evaluate('() => window.__OMRS_RESULT')
            if result['errors']:
                raise PdfExportError('PDF 排版失败：' + result['errors'][0], 422, 'pdf_layout')
            if not result['pages'] or render_errors:
                raise PdfExportError('PDF 排版未完整生成，请重试或选择 A4 HTML', 500, 'pdf_render')
            payload = page.pdf(format='A4', prefer_css_page_size=True, scale=1, print_background=True)
            if render_errors:
                raise PdfExportError('PDF 导出时渲染失败，请重试或选择 A4 HTML', 500, 'pdf_render')
            return payload
        finally:
            browser.close()


def _main():
    # POSIX 先允许 Chromium 在进程组被强制回收前正常退出。
    def terminate(_signum, _frame):
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, terminate)
    try:
        sys.stdout.buffer.write(_render(sys.stdin.buffer.read()))
    except PdfExportError as exc:
        print(json.dumps({'message': str(exc), 'status': exc.status, 'code': exc.code}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
