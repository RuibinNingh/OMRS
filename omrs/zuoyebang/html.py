"""上游 HTML 白名单与图片本地化；浏览器不接触外网、任意 CSS 或可执行内容。"""
import base64
import html
import http.client
import io
import ipaddress
import re
import socket
import ssl
import urllib.parse
from html.parser import HTMLParser
from .store import ZybError
from .svg import validate as validate_svg

ALLOWED = {'p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'sub', 'sup',
           'img', 'table', 'tbody', 'thead', 'tfoot', 'tr', 'td', 'th', 'ol', 'ul', 'li', 'blockquote', 'nobr', 'bdo'}
DROP = {'script', 'style', 'iframe', 'video', 'audio', 'object', 'embed', 'form', 'input', 'button', 'link', 'meta', 'svg', 'math'}
VISUAL = {'svg', 'math', 'canvas', 'object', 'embed', 'video', 'audio'}
IMAGE_BYTES = 12 * 1024 * 1024
CLASSES = frozenset('''tkspec-embed-text tkspec-dotted-normal tkspec-underline-normal
    tkspec-strike-normal tkspec-underline-wavy tkspec-italic-normal tkspec-text-indent-normal
    tkspec-bold-normal tkspec-script-sub tkspec-script-super tkspec-align-center tkspec-align-left
    tkspec-align-right tkspec-align-justify tkspec-paragraph-bottom-space-normal
    tkspec-table-diagonal-normal tkspec-fill-blank-underline tkspec-fill-blank-brackets
    yikespec-underline yikespec-line-through yikespec-line-wave yikespec-wavy yikespec-italic
    tk-md2html-content p-h1 p-h2 p-h3 math fM fI pA pR pS tB
    mathjye-aligncenter mathjye-alignright mathjye-alignleft mathjye-underline
    mathjye-underpoint mathjye-underwavy mathjye-underpoint2'''.split())


def picture_url(value):
    """复用原App fd53 的pid映射；URL随后仍须通过地址/IP校验。"""
    value = str(value or '').strip()
    if not value:
        return ''
    if value.startswith('//'):
        value = 'https:' + value
    if re.search(r'^(?:https?://|//|data:)|\.(?:jpe?g|png|gif|bmp)$', value, re.I):
        return value
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', value):
        raise ZybError('附图ID格式不合法，原内容已保留', 'image_address')
    prefix = 'https://img.zuoyebang.cc/tk_'
    if value.startswith('zyb_'):
        prefix = 'https://img.zuoyebang.cc/'
    elif value.startswith('qa10_'):
        prefix = 'https://img10.zuoyebang.cc/'
    elif re.match(r'^qa(?:\d+)?_', value):
        prefix = 'https://testimg.zuoyebang.cc/'
    elif match := re.match(r'^zyb(\d*?)_', value):
        prefix = 'https://img' + match[1] + '.zuoyebang.cc/'
    return prefix + value + '.jpg'


def layout_style(source, legacy=False):
    """只保留数值排版声明；旧公式定位由可信class赋予，不接受任意CSS。"""
    allowed = {'width', 'height', 'min-width', 'max-width', 'vertical-align'}
    if legacy:
        allowed |= {'top', 'bottom', 'left', 'right', 'font-size', 'margin-left', 'margin-right',
                    'margin-top', 'margin-bottom', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom'}
    result = []
    for declaration in (source or '').split(';'):
        name, separator, value = declaration.partition(':')
        name, value = name.strip().lower(), value.strip().lower()
        if legacy and name == 'display' and value in ('inline', 'inline-block', 'block', 'table-cell'):
            result.append(name + ':' + value)
            continue
        if legacy and name in ('border-top', 'border-bottom', 'border-left', 'border-right'):
            if re.fullmatch(r'(?:\d+(?:\.\d+)?|\.\d+)(?:px|em) (?:solid|dashed|dotted) (?:#000(?:000)?|black|currentcolor)', value):
                result.append(name + ':' + value)
            continue
        if not separator or name not in allowed:
            continue
        match = re.fullmatch(r'(-?(?:\d+(?:\.\d+)?|\.\d+))(px|em|rem|%)?', value)
        if not match:
            continue
        number, unit = float(match[1]), match[2] or ''
        if (not unit and number != 0) or abs(number) > (1080 if unit == 'px' else 100):
            continue
        if name in {'width', 'height', 'min-width', 'max-width', 'font-size'} and number < 0:
            continue
        result.append(name + ':' + value)
    return ';'.join(result)


def normalize_content(content):
    """原App补裸LaTeX命令；已有定界符时保留原数学表达式。"""
    source = str(content or '')
    if '\\' in source and not any(marker in source for marker in ('$', r'\(', r'\[')):
        source = re.sub(r'\\[a-zA-Z]+(?:\*?\{[^{}]*\})*', lambda m: '$' + m[0] + '$', source)
    return source


def valid_remote(url):
    """接受任意域名；仅允许无凭据、标准端口的 HTTP/HTTPS 地址。"""
    if url.startswith('//'):
        url = 'https:' + url
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme in ('https', 'http') and parsed.hostname and
                 parsed.username is None and parsed.password is None and
                 parsed.port in (None, 80 if parsed.scheme == 'http' else 443))
    except ValueError:
        valid = False
    if not valid:
        raise ZybError('附图地址不合法，请使用不带用户名或密码的标准 HTTP/HTTPS 地址', 'image_address')
    return parsed


def fetch_image(url):
    """每次跳转校验地址和公网单播 IP；固定已校验 IP，防止 DNS 重绑定。"""
    for _ in range(5):
        parsed = valid_remote(url)
        port = 80 if parsed.scheme == 'http' else 443
        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not address.is_global or address.is_multicast
                                for address in map(ipaddress.ip_address, addresses)):
            raise ZybError('附图服务解析到非公网地址', 'image_address')
        ip = sorted(addresses)[0]
        class PinnedTLS(http.client.HTTPSConnection):
            def connect(self):
                sock = socket.create_connection((ip, port), self.timeout)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        connection = PinnedTLS(parsed.hostname, port, timeout=20, context=ssl.create_default_context()) if port == 443 else http.client.HTTPConnection(ip, port, timeout=20)
        try:
            connection.request('GET', urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, '')),
                               headers={'Host': parsed.hostname, 'User-Agent': 'OMRS/zuoyebang-render', 'Accept': 'image/*'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, response.getheader('Location', ''))
                continue
            if response.status != 200:
                raise ZybError('作业帮附图下载失败，请重试', 'image_download', 502)
            raw = response.read(IMAGE_BYTES + 1)
            if len(raw) > IMAGE_BYTES:
                raise ZybError('附图超过渲染资源预算，已保留原内容', 'render_resource', 422)
            return raw
        except (OSError, http.client.HTTPException) as exc:
            raise ZybError('无法下载作业帮附图，请检查网络后重试', 'image_download', 502) from exc
        finally:
            connection.close()
    raise ZybError('附图跳转次数过多', 'image_download', 502)


def image_url(url, fetcher=fetch_image):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ZybError('后端渲染需要安装 requirements-zuoyebang.txt 中的依赖', 'render_dependency', 503) from exc
    if url.startswith('data:'):
        match = re.fullmatch(r'data:image/(?:png|jpeg|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=\s]+)', url)
        if not match or len(url) > IMAGE_BYTES * 4 / 3 + 100:
            raise ZybError('附图数据格式或大小不合法', 'image_invalid')
        try:
            raw = base64.b64decode(match[1], validate=True)
        except ValueError as exc:
            raise ZybError('附图数据格式不合法', 'image_invalid') from exc
    else:
        valid_remote(url)
        raw = fetcher(url)
    if len(raw) > IMAGE_BYTES:
        raise ZybError('附图超过渲染资源预算，已保留原内容', 'render_resource', 422)
    try:
        try:
            image = Image.open(io.BytesIO(raw))
        except UnidentifiedImageError:
            validate_svg(raw)
            mime = 'image/svg+xml'
        else:
            with image:
                if image.width * image.height > 40_000_000 or image.format not in ('PNG', 'JPEG', 'GIF', 'WEBP'):
                    raise ZybError('附图超过像素预算或格式不受支持', 'image_invalid')
                mime = Image.MIME[image.format]
                if getattr(image, 'is_animated', False):
                    raise ZybError('附图为动画，不能无损生成静态题面', 'image_invalid')
                image.verify()
    except ZybError:
        raise
    except Exception as exc:
        raise ZybError('附图无法解码，原内容已保留', 'image_invalid') from exc
    return 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii'), len(raw)


class Cleaner(HTMLParser):
    def __init__(self, localize):
        super().__init__(convert_charrefs=True)
        self.localize = localize
        self.parts, self.stack, self.seen = [], [], set()
        self.dropped = []

    def handle_starttag(self, tag, attributes):
        if self.dropped:
            if tag in DROP and tag not in ('input', 'embed', 'link', 'meta'):
                self.dropped.append(tag)
            return
        if tag in VISUAL:
            raise ZybError('题面含当前无法保真渲染的图形或媒体，原内容已保留', 'render_unsupported', 422)
        if tag in DROP:
            if tag not in ('input', 'embed', 'link', 'meta'):
                self.dropped.append(tag)
            return
        if tag not in ALLOWED:
            return
        attrs = dict(attributes)
        clean = ''
        classes = [name for name in (attrs.get('class') or '').split() if name in CLASSES]
        if tag == 'img':
            src = picture_url(attrs.get('src'))
            if not src:
                raise ZybError('题面存在缺少地址的附图，不能继续渲染', 'image_missing')
            localized = self.localize(src)
            self.seen.add(src)
            clean = ' src="' + html.escape(localized, quote=True) + '" alt="' + html.escape(attrs.get('alt') or '题目附图', quote=True) + '"'
            width = attrs.get('width') or re.search(r'(?:^|;)\s*width\s*:\s*(\d+(?:\.\d+)?)(?:px)?\s*(?:;|$)', attrs.get('style') or '')
            width = width.group(1) if isinstance(width, re.Match) else width
            if width and re.fullmatch(r'\d+(?:\.\d+)?', width) and 1 <= float(width) <= 1080:
                clean += ' width="' + width + '"'
        if tag in ('td', 'th'):
            for name in ('colspan', 'rowspan'):
                if re.fullmatch(r'[1-9]\d?', attrs.get(name) or ''):
                    clean += f' {name}="{attrs[name]}"'
        if tag == 'ol' and attrs.get('type') in ('1', 'a', 'A', 'i', 'I'):
            clean += ' type="' + attrs['type'] + '"'
        if tag in ('ol', 'li'):
            name = 'start' if tag == 'ol' else 'value'
            if re.fullmatch(r'[1-9]\d{0,3}', attrs.get(name) or ''):
                clean += f' {name}="{attrs[name]}"'
        align = re.search(r'(?:^|;)\s*text-align\s*:\s*(left|center|right)\s*(?:;|$)', attrs.get('style') or '')
        if align:
            classes.append('align-' + align.group(1))
        if classes:
            clean += ' class="' + ' '.join(dict.fromkeys(classes)) + '"'
        legacy = any(name in ('math', 'pA', 'pR', 'pS', 'fM', 'fI') for name in classes)
        style = layout_style(attrs.get('style'), legacy)
        if style and tag != 'img':
            clean += ' style="' + style + '"'
        if tag == 'bdo' and attrs.get('dir') in ('ltr', 'rtl'):
            clean += ' dir="' + attrs['dir'] + '"'
        self.parts.append('<' + tag + clean + '>')
        if tag not in ('img', 'br'):
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ('img', 'br'):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.dropped:
            if tag == self.dropped[-1]:
                self.dropped.pop()
            return
        if tag in self.stack:
            while self.stack:
                closed = self.stack.pop()
                self.parts.append('</' + closed + '>')
                if closed == tag:
                    break

    def handle_data(self, data):
        if not self.dropped:
            self.parts.append(html.escape(data))

    def output(self):
        return ''.join(self.parts) + ''.join('</' + tag + '>' for tag in reversed(self.stack))


def sanitize(content, pictures=None, localize=None):
    cleaner = Cleaner(localize or (lambda url: image_url(url)[0]))
    cleaner.feed(normalize_content(content))
    body = cleaner.output()
    for picture in pictures or []:
        value = picture if isinstance(picture, str) else next((picture.get(key) for key in ('url', 'src', 'picUrl', 'pic_url', 'pid') if picture.get(key)), '') if isinstance(picture, dict) else ''
        url = picture_url(value)
        if not url:
            raise ZybError('上游附图字段无法读取，原内容已保留', 'image_missing')
        if url not in cleaner.seen:
            body += '<p><img src="' + html.escape(cleaner.localize(url), quote=True) + '" alt="题目附图"></p>'
            cleaner.seen.add(url)
    return body


def candidate_html(candidate, fetcher=fetch_image):
    cache, budget = {}, 0
    def localize(url):
        nonlocal budget
        if url not in cache:
            value, size = image_url(url, fetcher)
            budget += size
            if budget > 80 * 1024 * 1024:
                raise ZybError('附图总量超过渲染资源预算，原内容已保留', 'render_resource', 422)
            cache[url] = value
        return cache[url]
    question = candidate['question']
    q_html = sanitize(question.get('content'), question.get('picList'), localize)
    answers = candidate.get('answer') or []
    if not all(isinstance(answer, dict) for answer in answers):
        raise ZybError('作业帮答案结构无法读取', 'protocol')
    a_html = '\n'.join('<div class="answer-part">' + sanitize(answer.get('content'), answer.get('picList'), localize) + '</div>' for answer in answers)
    if not re.sub(r'<[^>]*>', '', q_html).strip() and '<img' not in q_html:
        raise ZybError('题干为空，不能生成题目')
    return {'question': q_html, 'answer': a_html}, len(cache)
