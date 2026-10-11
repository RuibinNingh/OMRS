"""真实 Chromium 生成1080像素完整 PNG；每次调用在工作线程拥有独立浏览器。"""
import hashlib
import math
import mimetypes
import re
from pathlib import Path
from .store import ZybError

ASSETS = Path(__file__).resolve().parents[2] / 'assets' / 'vendor'
WIDTH = 1080
PIXEL_BUDGET = 100_000_000  # 物理内存预算，超限报错，绝不缩放、截断或分页。


def document(body, role):
    css = Path(__file__).with_name('paper.css').read_text('utf-8')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline' https://omrs-render.invalid; font-src https://omrs-render.invalid; script-src https://omrs-render.invalid">
<link rel="stylesheet" href="https://omrs-render.invalid/vendor/fonts/fonts.css">
<link rel="stylesheet" href="https://omrs-render.invalid/vendor/katex/katex.min.css">
<script src="https://omrs-render.invalid/vendor/katex/katex.min.js"></script>
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
            context = browser.new_context(viewport={'width': WIDTH, 'height': 800}, device_scale_factor=1, locale='zh-CN')
            errors = []
            def route(request):
                url = request.request.url
                prefix = 'https://omrs-render.invalid/vendor/'
                file = (ASSETS / url[len(prefix):]).resolve() if url.startswith(prefix) else None
                if file is None or not file.is_relative_to(ASSETS.resolve()) or not file.is_file():
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
                page.wait_for_function('() => typeof katex === "object"')
                dimensions = page.evaluate(r'''async () => {
                  const paper = document.querySelector('#paper');
                  const walker = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
                  const nodes = [];
                  while (walker.nextNode()) nodes.push(walker.currentNode);
                  const pattern = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|(?<!\\)\$(?!\$)[^$]+?(?<!\\)\$|\\\([\s\S]+?\\\))/g;
                  for (const node of nodes) {
                    const source = node.textContent, fragment = document.createDocumentFragment();
                    let offset = 0, found = false;
                    for (const match of source.matchAll(pattern)) {
                      found = true;
                      fragment.append(document.createTextNode(source.slice(offset, match.index)));
                      const marker = match[0], display = marker.startsWith('$$') || marker.startsWith('\\[');
                      const paired = marker.startsWith('\\') || marker.startsWith('$$');
                      const span = document.createElement('span');
                      katex.render(marker.slice(paired ? 2 : 1, paired ? -2 : -1), span,
                        {displayMode:display,throwOnError:true,trust:false,strict:'ignore',output:'html'});
                      fragment.append(span);
                      offset = match.index + marker.length;
                    }
                    if (found) { fragment.append(document.createTextNode(source.slice(offset))); node.replaceWith(fragment); }
                  }
                  await document.fonts.ready;
                  await Promise.all([...paper.querySelectorAll('img')].map(async img => {
                    await img.decode();
                    if (!img.naturalWidth || !img.naturalHeight) throw new Error('图片未加载');
                  }));
                  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                  paper.style.minHeight = Math.ceil(paper.getBoundingClientRect().height) + 'px';
                  return {width:paper.getBoundingClientRect().width,height:paper.getBoundingClientRect().height,
                    scroll:Math.max(document.body.scrollWidth,paper.scrollWidth),
                    fonts:[...document.fonts].every(font => font.status !== 'error'),
                    math:paper.querySelectorAll('.katex-error').length,images:paper.querySelectorAll('img').length};
                }''')
                height = math.ceil(dimensions['height'])
                if errors or not dimensions['fonts'] or dimensions['math']:
                    raise ZybError('字体、公式或附图未完整加载，原内容已保留', 'render_incomplete', 422)
                if dimensions['width'] != WIDTH or dimensions['scroll'] > WIDTH + 1:
                    raise ZybError('正文排版超出1080像素，不能截断，请检查原内容', 'render_overflow', 422)
                if WIDTH * height > PIXEL_BUDGET:
                    raise ZybError('完整长图超过后端物理像素预算，原内容已保留', 'render_resource', 422)
                path = Path(directory) / (role + '.png')
                page.locator('#paper').screenshot(path=str(path), animations='disabled')
                with Image.open(path) as image:
                    if image.size != (WIDTH, height):
                        raise ZybError('完整长图尺寸校验失败，原内容已保留', 'render_incomplete', 422)
                result[role] = {'width': WIDTH, 'height': height, 'images': dimensions['images'],
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'html': re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', '[已本地化的原始图片]', body)}
                page.close()
            result['browser'] = browser.version
            return result
        except ZybError:
            raise
        except Exception as exc:
            raise ZybError('后端渲染失败，原内容已保留；请检查图片或重试', 'render_failed', 422) from exc
        finally:
            browser.close()
