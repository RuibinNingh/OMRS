"""作业帮工作区 HTTP 适配；沿用 OMRS 鉴权、来源校验与上传所有者。"""
class ZuoyebangRoutes:
    def _zuoyebang_get(self, path, params):
        from ..zuoyebang import session, jobs
        try:
            if path == '/api/zuoyebang/status':
                result = session.status(self.vault_path)
            elif path == '/api/zuoyebang/job':
                result = {'job': jobs.get_job(self.vault_path, params.get('id', ''))}
            elif path == '/api/zuoyebang/record':
                result = {'record': jobs.get_record(self.vault_path, params.get('id', ''))}
            elif path == '/api/zuoyebang/history':
                result = {'records': jobs.history(self.vault_path)}
            elif path == '/api/zuoyebang/image':
                raw = jobs.image(self.vault_path, params.get('id', ''), params.get('role', ''))
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'private, no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(raw)
                return
            else:
                self._json({'status': 'error', 'msg': '接口不存在'}, 404)
                return
            self._json({'status': 'ok', **result})
        except Exception as exc:
            self._error(exc)

    def _zuoyebang_post(self, path):
        from ..zuoyebang import session, jobs
        from ..zuoyebang.commit import commit
        try:
            data = self.services.http_io.json_body(self)
            if path == '/api/zuoyebang/profile':
                result = session.import_profile(self.vault_path, data.get('profile'))
            elif path == '/api/zuoyebang/account':
                result = {'account': session.account_operation(self.vault_path, data.get('operation'), data.get('flow_id', ''))}
            elif path == '/api/zuoyebang/jobs':
                result = {'job': jobs.start_job(self.vault_path, data.get('type'), data)}
            elif path == '/api/zuoyebang/commit':
                result = commit(self.vault_path, data.get('render_id', ''), data)
            else:
                self._json({'status': 'error', 'msg': '接口不存在'}, 404)
                return
            self._json({'status': 'ok', **result})
        except Exception as exc:
            self._error(exc)
