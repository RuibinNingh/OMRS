"""复用用户提供的作业帮签名与解码协议；运行时不依赖手机桥接。"""
import base64
import gzip
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SEARCH_URL = 'https://aisearch.zuoyebang.com/search/submit/whole'


class UpstreamError(RuntimeError):
    def __init__(self, message, code=None, kind='upstream'):
        super().__init__(message)
        self.code = code
        self.kind = kind


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise UpstreamError('作业帮接口地址发生变化，未向其它地址转发凭据。', kind='protocol')


def reject_login_notice(questions):
    """登录拦截可能装在成功信封里，不能将提示作为题目录入。"""
    for question in questions:
        content = (question.get('question') or {}).get('content', '')
        text = html.unescape(re.sub(r'<[^>]*>', '', str(content)))
        if '登录提醒' in text and ('个人中心登录' in text or '重新登录' in text):
            raise UpstreamError('作业帮要求重新登录。请完成账号登录后再搜题。', kind='login_required')


def md5(value):
    return hashlib.md5(value.encode() if isinstance(value, str) else value).hexdigest()


def swap_ends(value, count):
    chars = list(value)
    for index in range(count):
        chars[index], chars[-1-index] = chars[-1-index], chars[index]
    return ''.join(chars)


def decode_key(token, version):
    value = md5('@#AIjd83#@6B') + md5(version) + swap_ends(md5('[' + token + ']@'), 15)
    value = swap_ends(value, 3)
    return swap_ends(value + md5(value), 60)


def sign(fields, token):
    excluded = {'sign', 'image', 'imei', '_imei', 'imsi', '_imsi', 'oaid', '_oaid'}
    params = ''.join(sorted(k + '=' + str(v) for k, v in fields.items() if k.lower() not in excluded))
    encoded = base64.b64encode(params.encode()).decode()
    return md5('8&%d*[' + md5(token) + ']@' + encoded)


def rc4(data, key):
    key = key.encode()
    if not key:
        raise ValueError('缺少答案解码密钥')
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) & 255
        state[i], state[j] = state[j], state[i]
    i = j = 0
    out = bytearray()
    for value in data:
        i = (i + 1) & 255
        j = (j + state[i]) & 255
        state[i], state[j] = state[j], state[i]
        out.append(value ^ state[(state[i] + state[j]) & 255])
    return bytes(out)


def decode_response(body, key):
    if body.get('errNo', 0) != 0:
        code = body.get('errNo')
        if code == 6:
            raise UpstreamError('作业帮签名会话已失效，请更新会话后重试。', code, 'signing_session')
        raise UpstreamError('作业帮直连接口返回错误（代码 %s）。' % code, code)
    data = body.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('answers'), dict):
        raise RuntimeError('作业帮未返回题目数据。')
    answers = data['answers']
    compressed = answers.get('gzip') == 1
    plain = data.get('encode') == 1

    def decode(value, selected_key=key, gz=compressed):
        if not value:
            return ''
        raw = base64.b64decode(value)
        if not plain:
            raw = rc4(raw, selected_key)
        if gz:
            import io
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(24 * 1024 * 1024 + 1)
            if len(raw) > 24 * 1024 * 1024:
                raise UpstreamError('解码正文超过内存预算。', kind='protocol')
        return raw.decode('utf-8')

    pages = answers.get('mainPageInfo') or []
    if plain:
        answers['mainPageInfo'] = [decode(p) for p in pages]
    elif answers.get('encryption') == 1:
        tids = [decode(t, gz=False) for t in answers.get('tids', [])]
        if len(tids) != len(pages):
            raise RuntimeError('作业帮返回的题目密钥数量不一致。')
        answers['tids'] = tids
        answers['mainPageInfo'] = [decode(decode(page, tid, False)) for tid, page in zip(tids, pages)]
    else:
        answers['mainPageInfo'] = [decode(p) for p in pages]
    return {'ok': True, 'data': data}


def multipart(fields, image):
    boundary = '----QuestionDesk' + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n' + str(value) + '\r\n').encode())
    extension, mime = ('png', 'image/png') if image.startswith(b'\x89PNG\r\n\x1a\n') else ('webp', 'image/webp') if image.startswith(b'RIFF') else ('jpg', 'image/jpeg')
    chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="image"; filename="question.' + extension + '"\r\nContent-Type: ' + mime + '\r\n\r\n').encode())
    chunks += [image, ('\r\n--' + boundary + '--\r\n').encode()]
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary


class DirectClient:
    def __init__(self, profile):
        self.path = Path(profile)

    @property
    def ready(self):
        return self.path.exists()

    def load(self):
        profile = json.loads(self.path.read_text('utf-8'))
        if profile.get('url') != 'https://aisearch.zuoyebang.com/search/submit/whole':
            raise ValueError('本地搜题接口地址不合法')
        return profile

    def search(self, image, grade_id=0):
        profile = self.load()
        fields = dict(profile['fields'])
        now = int(time.time() * 1000)
        fields.update(picMD5=md5(image), gradeId=str(grade_id), firstActTime=str(now),
                      sessionID=str(uuid.uuid4()), _t_=str(now // 1000))
        fields['sign'] = sign(fields, profile['session_token'])
        body, content_type = multipart(fields, image)
        headers = dict(profile['headers'])
        headers.update({'Content-Type': content_type, 'Accept': 'application/json', 'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 16)'})
        request = urllib.request.Request(profile['url'], data=body, headers=headers)
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=50) as response:
                raw = response.read(12 * 1024 * 1024 + 1)
                if len(raw) > 12 * 1024 * 1024:
                    raise UpstreamError('作业帮响应超过资源预算。', kind='protocol')
        except (urllib.error.URLError, TimeoutError) as error:
            raise UpstreamError('无法连接作业帮搜题服务，请稍后重试。', kind='network') from error
        try:
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('响应不是对象')
            return decode_response(result, decode_key(profile['session_token'], str(fields['vc'])))
        except UpstreamError:
            raise
        except (ValueError, TypeError, KeyError, RuntimeError, UnicodeError) as error:
            raise UpstreamError('作业帮搜题响应格式已变化，请保留原图并重试。', kind='protocol') from error
