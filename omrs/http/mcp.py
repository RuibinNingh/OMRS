"""HTTP mcp 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class McpRoutes:

    def _mcp_get(self, path, params):
        try:
            if path == '/api/mcp/keys':
                from ..mcp.keys import list_keys
                self._json({'status': 'ok', 'keys': list_keys(self.vault_path)})
            elif path == '/api/mcp/operations/detail':
                from ..mcp_operations import get
                self._json({'status': 'ok', 'operation': get(self.vault_path, params.get('operation_id', ''))})
            elif path == '/api/mcp/exports/download':
                from ..mcp_exports import download
                payload, filename = download(self.vault_path, params.get('export_id', ''))
                self._download(payload, filename, 'text/html; charset=utf-8')
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except self.services.RequestError as exc:
            self._json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 404 if exc.code == 'not_found' else 410 if exc.code == 'export_expired' else 409)
        except (ValueError, TypeError) as exc:
            self._error(exc)
        except (OSError, self.services.sqlite3.Error):
            self._json({'status': 'error', 'msg': 'MCP 管理数据暂时无法读取'}, 503)

    def _mcp_post(self, path):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 <= length <= 16 * 1024:
                raise ValueError('Key 管理请求超过大小限制')
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(length)
            data = self.services.http_io.json_body(self, body)
            if not isinstance(data, dict):
                raise ValueError('请求必须是 JSON 对象')
            from ..mcp.keys import create_key, revoke_key, update_scopes
            if path == '/api/mcp/keys':
                if set(data) - {'name', 'scopes', 'expires_at'}:
                    raise ValueError('Key 管理请求包含不允许的字段')
                self._json({'status': 'ok', 'key': create_key(self.vault_path, data.get('name', ''), data.get('scopes'), data.get('expires_at'))})
            elif path == '/api/mcp/keys/revoke':
                if set(data) != {'key_id'}:
                    raise ValueError('吊销请求只能包含 key_id')
                self._json({'status': 'ok', 'key': revoke_key(self.vault_path, data.get('key_id', ''))})
            elif path == '/api/mcp/keys/update':
                if set(data) != {'key_id', 'scopes'}:
                    raise ValueError('权限编辑只接受 key_id 和 scopes')
                self._json({'status': 'ok', 'key': update_scopes(self.vault_path, data['key_id'], data['scopes'])})
            elif path == '/api/mcp/operations/decide':
                if set(data) != {'operation_id', 'decision'}:
                    raise ValueError('确认请求只接受 operation_id 和 decision')
                from ..mcp_operations import decide
                self._json({'status': 'ok', 'operation': decide(self.vault_path, data['operation_id'], data['decision'])})
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except self.services.RequestError as exc:
            self._json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 404 if exc.code == 'not_found' else 409)
        except (ValueError, TypeError, self.services.json.JSONDecodeError) as exc:
            self._error(exc)
        except (OSError, self.services.sqlite3.Error):
            self._json({'status': 'error', 'msg': 'MCP 管理数据暂时无法保存，请重试'}, 503)

    def _runtime_records_get(self, params, detail=False):
        from .. import runtime_records
        try:
            if detail:
                seq = int(params.get('seq', '0'))
                if seq <= 0:
                    raise ValueError('记录编号不正确')
                row = runtime_records.detail(self.vault_path, seq)
                self._json({'status': 'ok', 'detail': row} if row else {'status': 'error', 'msg': '运行记录不存在'}, 200 if row else 404)
            else:
                self._json({'status': 'ok', **runtime_records.list_records(self.vault_path, params)})
        except (ValueError, TypeError) as exc:
            self._error(exc)
        except (OSError, self.services.sqlite3.Error):
            self._json({'status': 'error', 'msg': '运行记录暂时无法读取，请检查存储后重试。'}, 503)
