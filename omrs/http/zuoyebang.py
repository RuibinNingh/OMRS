"""作业帮工作区 HTTP 适配；沿用 OMRS 鉴权、来源校验与上传所有者。"""
class ZuoyebangRoutes:
    def _zuoyebang_get(self, path, params):
        from ..zuoyebang import service, service_config, jobs
        try:
            if path == '/api/zuoyebang/status':
                result = service.status(self.vault_path)
            elif path == '/api/zuoyebang/service':
                result = {'service': service_config.public(self.vault_path)}
            elif path == '/api/zuoyebang/job':
                result = {'job': jobs.get_job(self.vault_path, params.get('id', ''))}
            elif path == '/api/zuoyebang/record':
                result = {'record': jobs.get_record(self.vault_path, params.get('id', ''))}
            elif path == '/api/zuoyebang/history':
                result = {'records': jobs.history(self.vault_path)}
            elif path == '/api/zuoyebang/image':
                if params.get('role') == 'source':
                    from ..zuoyebang import source, store
                    from ..vault_lifecycle import lease
                    with lease(self.vault_path):
                        raw, mime = source.read(self.vault_path, store.read(self.vault_path, params.get('id', '')), preview=True)
                else:
                    raw = jobs.image(self.vault_path, params.get('id', ''), params.get('role', ''))
                    mime = 'image/png'
                self.send_response(200)
                self.send_header('Content-Type', mime)
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
        from ..zuoyebang import service, service_config, jobs, store
        from ..zuoyebang.commit import commit
        try:
            data = self.services.http_io.json_body(self)
            if path in ('/api/zuoyebang/profile', '/api/zuoyebang/account'):
                raise store.ZybError('请在独立作业帮服务面板管理账户；OMRS不再导入或扫码新会话', 'gateway_management', 409)
            elif path == '/api/zuoyebang/service':
                result = {'service': service_config.save(self.vault_path, data)}
            elif path == '/api/zuoyebang/service/test':
                if data:
                    raise store.ZybError('连接测试仅使用已保存配置，不接受临时服务参数')
                result = service.status(self.vault_path)
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
