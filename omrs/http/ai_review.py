"""受 Web 登录与同源保护的审核接口；MCP 凭据不能借道批准。"""
from .. import ai_review


class AiReviewRoutes:
    def _ai_review_get(self, path, params):
        try:
            if path == '/api/ai-review/items':
                self._json({'status': 'ok', **ai_review.items(self.vault_path, params)})
            elif path == '/api/ai-review/counts':
                self._json({'status': 'ok', 'counts': ai_review.counts(self.vault_path)})
            elif path == '/api/ai-review/detail':
                self._json({'status': 'ok', 'item': ai_review.detail(self.vault_path, params.get('id') or params.get('operation_id', ''))})
        except ai_review.ReviewError as exc:
            self._json({'status': 'error', 'msg': str(exc), 'code': exc.code}, exc.status)
        except self.services.drafts_mod.DraftError as exc:
            self._json({'status': 'error', 'msg': str(exc), 'code': exc.code}, exc.status)
        except (OSError, self.services.sqlite3.Error):
            self._json({'status': 'error', 'msg': '审核数据暂时无法读取，请重试'}, 503)

    def _ai_review_post(self, path):
        try:
            body = b'' if hasattr(self, '_prepared_json') else self.rfile.read(self.services.http_io.content_length(self))
            data = self.services.http_io.json_body(self, body)
            if not isinstance(data, dict) or set(data) - {'id', 'operation_id', 'expected_revision', 'patch', 'decision'}:
                raise ai_review.ReviewError('invalid_request', '审核请求字段不正确')
            operation_id = data.get('id') or data.get('operation_id')
            revision = data.get('expected_revision')
            if type(revision) is not int or revision < 1:
                raise ai_review.ReviewError('invalid_request', '必须提供有效提案版本')
            if path == '/api/ai-review/update':
                item = ai_review.update(self.vault_path, operation_id, revision, data.get('patch'))
            else:
                remote, ip, _ = self._security_context()
                item = ai_review.decide(self.vault_path, operation_id, revision, data.get('decision'),
                                       reviewer={'kind': 'web', 'access': 'session' if remote else 'direct', 'client_ip': ip})
            self._json({'status': 'ok', 'item': ai_review.public(item)})
        except ai_review.ReviewError as exc:
            self._json({'status': 'error', 'msg': str(exc), 'code': exc.code}, exc.status)
        except (ValueError, TypeError) as exc:
            self._json({'status': 'error', 'msg': str(exc), 'code': getattr(exc, 'code', 'invalid_request')}, 400)
        except (OSError, self.services.sqlite3.Error):
            self._json({'status': 'error', 'msg': '审核决定暂时无法保存，请核对当前状态后重试'}, 503)
