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

ALLOWED = {'p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'sub', 'sup',
           'img', 'table', 'tbody', 'thead', 'tfoot', 'tr', 'td', 'th', 'ol', 'ul', 'li', 'blockquote'}
DROP = {'script', 'style', 'iframe', 'video', 'audio', 'object', 'embed', 'form', 'input', 'button', 'link', 'meta', 'svg', 'math'}
VISUAL = {'svg', 'math', 'canvas', 'object', 'embed', 'video', 'audio'}
HOSTS = ('zuoyebang.com', 'zybang.com', 'qbimg.com', 'bdimg.com', 'baidu.com')
IMAGE_BYTES = 12 * 1024 * 1024


def valid_remote(url):
    if url.startswith('//'):
        url = 'https:' + url
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    if (parsed.scheme not in ('https', 'http') or parsed.username or parsed.password or
            parsed.port not in (None, 80 if parsed.scheme == 'http' else 443) or
            not any(host == domain or host.endswith('.' + domain) for domain in HOSTS)):
        raise ZybError('附图地址不属于允许的作业帮图片服务', 'image_address')
    return parsed


def fetch_image(url):
    """每次跳转校验域名和实际连接 IP；固定已校验 IP，防止 DNS 重绑定。"""
    for _ in range(5):
        parsed = valid_remote(url)
        port = 80 if parsed.scheme == 'http' else 443
        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
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
        from PIL import Image
    except ImportError as exc:
        raise ZybError('后端渲染需要安装 requirements-zuoyebang.txt 中的依赖', 'render_dependency', 503) from exc
    if url.startswith('data:'):
        match = re.fullmatch(r'data:image/(?:png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\s]+)', url)
        if not match or len(url) > IMAGE_BYTES * 4 / 3 + 100:
            raise ZybError('附图数据格式或大小不合法', 'image_invalid')
        try:
            raw = base64.b64decode(match[1], validate=True)
        except ValueError as exc:
            raise ZybError('附图数据格式不合法', 'image_invalid') from exc
    else:
        valid_remote(url)
        raw = fetcher(url)
    try:
        with Image.open(io.BytesIO(raw)) as image:
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
        if tag == 'img':
            src = attrs.get('src') or ''
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
        align = re.search(r'(?:^|;)\s*text-align\s*:\s*(left|center|right)\s*(?:;|$)', attrs.get('style') or '')
        if align:
            clean += ' class="align-' + align.group(1) + '"'
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
    cleaner.feed(str(content or ''))
    body = cleaner.output()
    for picture in pictures or []:
        url = picture if isinstance(picture, str) else next((picture.get(key) for key in ('url', 'src', 'picUrl', 'pic_url') if picture.get(key)), '') if isinstance(picture, dict) else ''
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
