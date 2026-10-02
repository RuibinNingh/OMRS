"""HTTP auth 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class AuthRoutes:

    def _auth_status(self):
        remote, _, scheme = self._security_context()
        session = self.services.security.session_for(self.vault_path, self._cookie_token()) if remote else None
        lan_exempt = remote and self._direct_lan_exempt()
        self._json({'status': 'ok', 'instance_id': self.services.OMRS_INSTANCE_ID, 'remote': remote, 'authenticated': bool(session) or not remote or lan_exempt, 'lan_pin_exempt': lan_exempt, 'pin_configured': self.services.security.auth_summary(self.vault_path)['pin_configured'], 'warning_required': bool(remote and session and (scheme == 'http') and (not session['warning_ack']))})

    def _auth_login(self):
        remote, client_ip, scheme = self._security_context()
        try:
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(self.services.http_io.content_length(self))
            data = self.services.http_io.json_body(self, body)
            if not isinstance(data, dict):
                raise ValueError('登录请求必须是 JSON 对象')
            token, _ = self.services.security.login(self.vault_path, str(data.get('pin', '')), client_ip)
            self.send_response(200)
            attrs = f'{self.services.security.COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={self.services.security.ABSOLUTE_SECONDS}'
            if scheme == 'https':
                attrs += '; Secure'
            self.send_header('Set-Cookie', attrs)
            payload = b'{"status":"ok"}'
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (ValueError, TypeError, self.services.json.JSONDecodeError) as exc:
            self._error(exc)

    def _auth_post(self, path):
        try:
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(self.services.http_io.content_length(self))
            data = self.services.http_io.json_body(self, body)
            if not isinstance(data, dict):
                raise ValueError('请求体必须是 JSON 对象')
            remote, client_ip, _ = self._security_context()
            session = self._active_session
            if path == '/api/auth/pin':
                if remote and self.services.security.auth_summary(self.vault_path)['pin_configured'] and (not self.services.security.verify_pin_limited(self.vault_path, str(data.get('current_pin', '')), client_ip)):
                    raise ValueError('当前 PIN 错误')
                if data.get('pin'):
                    result = self.services.security.set_pin(self.vault_path, str(data['pin']), data.get('idle_minutes', 30))
                else:
                    result = self.services.security.set_idle_minutes(self.vault_path, data.get('idle_minutes', 30))
                self._json({'status': 'ok', **result})
            elif path == '/api/auth/disable':
                if remote or self.services.load_config(self.vault_path).get('allow_external'):
                    raise ValueError('关闭局域网访问后才能停用 PIN')
                self.services.security.disable_pin(self.vault_path)
                self._json({'status': 'ok'})
            elif path == '/api/auth/activity':
                if session:
                    self.services.security.activity(session)
                self._json({'status': 'ok'})
            elif path == '/api/auth/warning-ack':
                if session:
                    session['warning_ack'] = True
                self._json({'status': 'ok'})
            elif path == '/api/auth/logout':
                self.services.security.logout(self._cookie_token())
                self.send_response(200)
                self.send_header('Set-Cookie', f'{self.services.security.COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except (ValueError, TypeError, self.services.json.JSONDecodeError) as exc:
            self._error(exc)
