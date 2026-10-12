"""复用已验收的扫码、账号核对与续登录协议；只操作调用者提供的临时快照。"""
import copy
import hashlib
import json
import os
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from .direct import DirectClient, UpstreamError, sign, NoRedirect
from .qr import qr_data_url
from ..transport import bounded_read, ResponseBudget

SEARCH_FIELDS = {
    'picMD5', 'gradeId', 'firstActTime', 'sessionID', 'guideImage', 'imgCorrection',
    'isMultiAnswer', 'queryht', 'extraMsg', 'referer', 'refererSid', 'preSid', 'sign',
}
ENDPOINTS = {
    'qr_create': 'https://passport.zybang.com/session/submit/qrlogingenid',
    'qr_check': 'https://passport.zybang.com/session/submit/qrlogin',
    'relogin': 'https://passport.zybang.com/session/submit/relogin',
    'userinfo': 'https://napi.zybang.com/napi/user/userinfo',
    'antispam': 'https://pluto.zuoyebang.com/pluto/app/antispam',
}
QR_LIFETIME = 300  # 本地扫码流程期限；未取得官方账号有效期。
QR_POLL_INTERVAL = 2
QR_TERMINAL_STATES = {'authenticated', 'cancelled', 'expired', 'session_changed'}


def account_profile(profile, credential):
    if not isinstance(credential, str) or not 1 <= len(credential) <= 8192 or any(c in credential for c in ';\r\n\t '):
        raise UpstreamError('作业帮未返回有效账号凭据，请重新登录。', kind='protocol')
    result = copy.deepcopy(profile)
    result['fields']['ZYBUSS'] = credential
    for name in ['Cookie', 'X-Wap-Proxy-Cookie']:
        existing_name = next((key for key in result['headers'] if key.lower() == name.lower()), name)
        cookies = [part.strip() for part in result['headers'].get(existing_name, '').split(';')
                   if part.strip() and part.strip().split('=', 1)[0].lower() != 'zybuss']
        cookies.append('ZYBUSS=' + credential)
        result['headers'][existing_name] = '; '.join(cookies)
    result['fields']['sign'] = sign(result['fields'], result['session_token'])
    return result


class AccountClient:
    def __init__(self, profile):
        self.client = DirectClient(profile)
        self.flow_path = self.client.path.parent / 'qr-login.json'
        self.lock = threading.RLock()
        self.timeout = 30

    def status(self):
        if not self.client.ready:
            return {'local_session_ready': False, 'has_account_credential': False, 'server_verified': False}
        profile = self.client.load()
        return {'local_session_ready': True, 'has_account_credential': bool(profile['fields'].get('ZYBUSS')),
                'server_verified': False, 'synced_at': profile.get('created_at'),
                'antispam_refreshed_at': profile.get('antispam_refreshed_at'), 'version': profile['fields'].get('vcname')}

    def fingerprint(self):
        return hashlib.sha256(self.client.path.read_bytes()).hexdigest()

    def request(self, operation, profile, params=None, authenticated=True, bootstrap=False):
        fields = {key: value for key, value in profile['fields'].items() if key not in SEARCH_FIELDS}
        fields.update(params or {})
        fields['_t_'] = str(int(time.time()))
        headers = dict(profile['headers'])
        if not authenticated:
            fields.pop('ZYBUSS', None)
            for name in list(headers):
                if 'cookie' in name.lower():
                    headers[name] = '; '.join(part.strip() for part in headers[name].split(';')
                                            if part.strip() and part.strip().split('=', 1)[0].lower() != 'zybuss')
        if bootstrap:
            fields.pop('token', None)
            headers = {}
        fields['sign'] = 'init_error' if bootstrap else sign(fields, profile['session_token'])
        headers.update({'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json',
                        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 16)'})
        request = urllib.request.Request(ENDPOINTS[operation], data=urllib.parse.urlencode(fields).encode(), headers=headers)
        deadline = time.monotonic() + self.timeout
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = bounded_read(response, 2 * 1024 * 1024, deadline)
        except ResponseBudget as error:
            raise UpstreamError('作业帮账号响应超过资源预算。', kind='protocol') from error
        except (urllib.error.URLError, OSError) as error:
            raise UpstreamError('电脑无法连接作业帮账号服务。', kind='network') from error
        if len(raw) > 2 * 1024 * 1024:
            raise UpstreamError('作业帮账号响应过大。')
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise UpstreamError('作业帮账号响应格式已变化。', kind='protocol') from error
        if not isinstance(result, dict) or 'errNo' not in result:
            raise UpstreamError('作业帮账号响应格式已变化。', kind='protocol')
        return result

    @staticmethod
    def success(result):
        if result['errNo'] == 6:
            raise UpstreamError('签名会话已失效，请更新本地会话后重试。', 6, kind='signing_session')
        if result['errNo'] != 0:
            raise UpstreamError('作业帮账号接口返回错误（代码 %s）。' % result['errNo'], result['errNo'])
        if not isinstance(result.get('data'), dict):
            raise UpstreamError('作业帮账号响应格式已变化。', kind='protocol')
        return result['data']

    def verify(self, profile=None):
        profile = profile or self.client.load()
        result = self.request('userinfo', profile, {'vipDialogReq': '', 'abKv': ''})
        data = self.success(result)
        user = data.get('user') or {}
        if not isinstance(user, dict) or str(user.get('uid', '0')) in ('', '0', 'None'):
            raise UpstreamError('作业帮账号未登录，请完成登录后再搜题。', kind='login_required')
        return {'server_verified': True, 'has_account_credential': True, 'checked_at': time.time()}

    def commit(self, profile, expected):
        if self.fingerprint() != expected:
            raise UpstreamError('本地会话在操作期间发生变化，请重新开始。', kind='session_changed')
        temporary = self.client.path.with_name('.session-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary, self.client.path)
        finally:
            temporary.unlink(missing_ok=True)

    def relogin(self):
        with self.lock:
            expected = self.fingerprint()
            profile = self.client.load()
            data = self.success(self.request('relogin', profile))
            candidate = account_profile(profile, data.get('zybuss'))
            summary = self.verify(candidate)
            changed = candidate['fields']['ZYBUSS'] != profile['fields'].get('ZYBUSS')
            if changed:
                self.commit(candidate, expected)
            return dict(summary, credential_changed=changed)

    def start_qr(self):
        with self.lock:
            expected = self.fingerprint()
            data = self.success(self.request('qr_create', self.client.load(), {'appId': 'homework'}, authenticated=False))
            identifier = data.get('uuid')
            if not isinstance(identifier, str) or not 1 <= len(identifier) <= 256:
                raise UpstreamError('作业帮未返回登录二维码。', kind='protocol')
            flow = {'id': uuid.uuid4().hex, 'uuid': identifier, 'created_at': time.time(),
                    'profile_fingerprint': expected, 'last_poll_at': 0, 'state': 'pending'}
            flow['expires_at'] = flow['created_at'] + QR_LIFETIME
            payload = 'app://homework/qr_code?uuid=' + urllib.parse.quote(identifier, safe='')
            rendered = qr_data_url(payload)
            self.save_flow(flow)
            return dict(self.flow_summary(flow), qr_url=payload, qr_image=rendered,
                        message='请用已登录的作业帮 App 扫码，并在官方确认页面完成授权。')

    def save_flow(self, flow):
        temporary = self.flow_path.with_name('.qr-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(flow), encoding='utf-8')
            os.replace(temporary, self.flow_path)
        finally:
            temporary.unlink(missing_ok=True)

    def read_flow(self, flow_id):
        if not isinstance(flow_id, str) or len(flow_id) != 32 or any(c not in string.hexdigits for c in flow_id):
            raise ValueError('扫码流程编号不合法')
        try:
            flow = json.loads(self.flow_path.read_text('utf-8'))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise UpstreamError('本地二维码流程已损坏，请重新创建。', kind='qr_missing') from error
        if not isinstance(flow, dict) or not isinstance(flow.get('id'), str):
            raise UpstreamError('本地二维码流程已损坏，请重新创建。', kind='qr_missing')
        return flow

    @staticmethod
    def flow_summary(flow):
        result = {'flow_id': flow['id'], 'state': flow.get('state', 'pending'),
                  'expires_at': flow.get('expires_at', flow['created_at'] + QR_LIFETIME),
                  'poll_interval': QR_POLL_INTERVAL}
        # 终态仅返回白名单摘要，不返回挑战值与账号令牌。
        result.update({key: flow[key] for key in ('message', 'server_verified', 'has_account_credential', 'checked_at')
                       if key in flow})
        return result

    def finish_flow(self, flow, state, message, summary=None):
        flow = {key: value for key, value in flow.items() if key not in ('uuid', 'profile_fingerprint')}
        flow.update(state=state, message=message)
        flow.update(summary or {})
        self.save_flow(flow)
        return self.flow_summary(flow)

    @staticmethod
    def absent_flow(flow_id, exists):
        return {'flow_id': flow_id, 'state': 'replaced' if exists else 'missing',
                'message': '登录二维码已更换，请使用当前二维码。' if exists else '请重新创建登录二维码。'}

    def interrupted_flow(self, flow):
        """网络等待后复核流程，防止迟到授权覆盖取消或替换。"""
        current = self.read_flow(flow['id'])
        if current is None or current['id'] != flow['id']:
            return self.absent_flow(flow['id'], current is not None)
        if current.get('state') in QR_TERMINAL_STATES:
            return self.flow_summary(current)
        if time.time() >= current.get('expires_at', current['created_at'] + QR_LIFETIME):
            return self.finish_flow(current, 'expired', '登录二维码已过期，请重新创建。')
        return None

    def cancel_qr(self, flow_id):
        with self.lock:
            flow = self.read_flow(flow_id)
            if flow is None or flow_id != flow['id']:
                return self.absent_flow(flow_id, flow is not None)
            if flow.get('state') in QR_TERMINAL_STATES:
                return self.flow_summary(flow)
            if time.time() >= flow.get('expires_at', flow['created_at'] + QR_LIFETIME):
                return self.finish_flow(flow, 'expired', '登录二维码已过期，请重新创建。')
            return self.finish_flow(flow, 'cancelled', '扫码登录已取消，当前账号未更改。')

    def poll_qr(self, flow_id):
        with self.lock:
            flow = self.read_flow(flow_id)
            if flow is None or flow_id != flow['id']:
                return self.absent_flow(flow_id, flow is not None)
            if flow.get('state') in QR_TERMINAL_STATES:
                return self.flow_summary(flow)
            now = time.time()
            if now >= flow.get('expires_at', flow['created_at'] + QR_LIFETIME):
                return self.finish_flow(flow, 'expired', '登录二维码已过期，请重新创建。')
            if flow['profile_fingerprint'] != self.fingerprint():
                return self.finish_flow(flow, 'session_changed', '会话已经更新，请重新创建登录二维码。')
            if now - flow['last_poll_at'] < QR_POLL_INTERVAL:
                return dict(self.flow_summary(flow), retry_after=QR_POLL_INTERVAL)
            flow['last_poll_at'] = now
            self.save_flow(flow)
            profile = self.client.load()
            result = self.request('qr_check', profile, {'appId': 'homework', 'uuid': flow['uuid']}, authenticated=False)
            interrupted = self.interrupted_flow(flow)
            if interrupted:
                return interrupted
            if result['errNo'] == 860019:
                return dict(self.flow_summary(flow), message='等待作业帮 App 确认登录。', retry_after=QR_POLL_INTERVAL)
            if result['errNo'] == 860018:
                return self.finish_flow(flow, 'expired', '作业帮二维码已失效，请重新创建。')
            data = self.success(result)
            candidate = account_profile(profile, data.get('zybuss'))
            summary = self.verify(candidate)
            interrupted = self.interrupted_flow(flow)
            if interrupted:
                return interrupted
            self.commit(candidate, flow['profile_fingerprint'])
            return self.finish_flow(flow, 'authenticated', '账号登录成功，可以上传图片搜题。', summary)
