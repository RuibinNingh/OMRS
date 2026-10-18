"""真实 Chromium 按手机宽度排版，生成1080像素完整 PNG。"""
import hashlib
import math
import mimetypes
import re
from pathlib import Path
from .store import ZybError

ASSETS = Path(__file__).resolve().parents[2] / 'assets' / 'vendor'
TRUSTED = Path(__file__).with_name('mathjax.js')
LAYOUT_SCRIPT = Path(__file__).with_name('layout.js')
LAYOUT_VERSION = 'mobile-360-v2'
CSS_WIDTH = 360
SCALE = 3
WIDTH = CSS_WIDTH * SCALE
PIXEL_BUDGET = 100_000_000  # 按输出像素计量；超限报错，不整体缩放、截断或分页。


def document(body, role):
    css = Path(__file__).with_name('paper.css').read_text('utf-8')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline' https://omrs-render.invalid; font-src https://omrs-render.invalid; script-src https://omrs-render.invalid">
<link rel="stylesheet" href="https://omrs-render.invalid/vendor/fonts/fonts.css">
<script src="https://omrs-render.invalid/renderer/mathjax.js"></script>
<script src="https://omrs-render.invalid/vendor/mathjax/tex-chtml-full.js"></script>
<script src="https://omrs-render.invalid/renderer/layout.js"></script>
<style>''' + css + '</style></head><body><main id="paper" data-role="' + role + '">' + body + '</main></body></html>'


def render_documents(documents, directory):
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError as exc:
        raise ZybError('请安装 requirements-zuoyebang.txt，并安装 Playwright Chromium', 'render_dependency', 503) from exc
    result = {}
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise ZybError('后端 Chromium 无法启动，请检查渲染依赖', 'render_dependency', 503) from exc
        try:
            context = browser.new_context(viewport={'width': CSS_WIDTH, 'height': 800}, device_scale_factor=SCALE, locale='zh-CN')
            errors = []
            def route(request):
                url = request.request.url
                prefix = 'https://omrs-render.invalid/vendor/'
                if url == 'https://omrs-render.invalid/renderer/mathjax.js':
                    file = TRUSTED
                elif url == 'https://omrs-render.invalid/renderer/layout.js':
                    file = LAYOUT_SCRIPT
                elif url.startswith(prefix + 'fonts/') or url.startswith(prefix + 'mathjax/'):
                    file = (ASSETS / url[len(prefix):]).resolve()
                else:
                    file = None
                if file is None or (file not in (TRUSTED, LAYOUT_SCRIPT) and not file.is_relative_to(ASSETS.resolve())) or not file.is_file():
                    errors.append('resource')
                    request.abort()
                    return
                request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
            context.route('**/*', route)
            for role, body in documents.items():
                if role == 'answer' and not re.sub(r'<[^>]*>', '', body).strip() and '<img' not in body:
                    result[role] = {'empty': True, 'html': ''}
                    continue
                page = context.new_page()
                page.set_default_timeout(45000)
                page.on('pageerror', lambda _error: errors.append('script'))
                page.set_content(document(body, role), wait_until='load')
                page.wait_for_function('() => typeof MathJax?.typesetPromise === "function"')
                dimensions = page.evaluate(r'''async () => {
                  const paper = document.querySelector('#paper');
                  await MathJax.startup.promise;
                  await MathJax.typesetPromise([paper]);
                  await document.fonts.ready;
                  await Promise.all([...paper.querySelectorAll('img')].map(async img => {
                    await img.decode();
                    if (!img.naturalWidth || !img.naturalHeight) throw new Error('图片未加载');
                  }));
                  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                  const fitted = window.omrsFitPaper(paper);
                  await document.fonts.ready;
                  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                  paper.style.minHeight = Math.ceil(paper.getBoundingClientRect().height) + 'px';
                  const edge = paper.getBoundingClientRect();
                  return {width:paper.getBoundingClientRect().width,height:paper.getBoundingClientRect().height,
                    scroll:Math.max(document.body.scrollWidth,paper.scrollWidth),
                    outside:[...paper.querySelectorAll('*')].some(el => {
                      const box=el.getBoundingClientRect();
                      return box.width && (box.left < edge.left - 1 || box.right > edge.right + 1);
                    }),
                    fonts:[...document.fonts].every(font => font.status !== 'error'),
                    math:paper.querySelectorAll('mjx-merror').length,formulas:paper.querySelectorAll('mjx-container').length,
                    images:paper.querySelectorAll('img').length, ...fitted};
                }''')
                height = math.ceil(dimensions['height']) * SCALE
                if errors or not dimensions['fonts'] or dimensions['math']:
                    raise ZybError('字体、公式或附图未完整加载，原内容已保留', 'render_incomplete', 422)
                if dimensions['width'] != CSS_WIDTH or dimensions['scroll'] > CSS_WIDTH + 1 or dimensions['outside']:
                    raise ZybError('正文排版超出手机宽度，不能截断，请检查原内容', 'render_overflow', 422)
                if WIDTH * height > PIXEL_BUDGET:
                    raise ZybError('完整长图超过后端物理像素预算，原内容已保留', 'render_resource', 422)
                path = Path(directory) / (role + '.png')
                page.locator('#paper').screenshot(path=str(path), animations='disabled')
                with Image.open(path) as image:
                    if image.size != (WIDTH, height):
                        raise ZybError('完整长图尺寸校验失败，原内容已保留', 'render_incomplete', 422)
                result[role] = {'width': WIDTH, 'height': height, 'images': dimensions['images'],
                                'formulas': dimensions['formulas'],
                                'fitted_formulas': dimensions['fitted_formulas'], 'fitted_tables': dimensions['fitted_tables'],
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'html': re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', '[已本地化的原始图片]', body)}
                page.close()
            result['browser'] = browser.version
            result['engine'] = 'MathJax 3.2.2'
            result['layout'] = {'version': LAYOUT_VERSION, 'css_width': CSS_WIDTH, 'device_scale_factor': SCALE}
            return result
        except ZybError:
            raise
        except Exception as exc:
            raise ZybError('后端渲染失败，原内容已保留；请检查图片、公式或重试', 'render_failed', 422) from exc
        finally:
            browser.close()
