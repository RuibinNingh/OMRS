"""HTTP drafts 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class DraftsRoutes:

    def _drafts_get(self, path, params):
        try:
            if path == '/api/drafts/list':
                self._json({'status': 'ok', 'drafts': self.services.drafts_mod.list_drafts(self.vault_path, status=params.get('status') or None, conversation_id=params.get('conversation') or None, limit=params.get('limit') or 50)})
            elif path == '/api/drafts/item':
                self._json({'status': 'ok', 'draft': self.services.drafts_mod.get_draft(self.vault_path, params.get('id', ''))})
            elif path == '/api/drafts/image':
                sha = params.get('sha', '')
                if not self.services.re.fullmatch('[0-9a-f]{64}', sha or ''):
                    raise ValueError('sha 参数不合法')
                data_url = self.services.drafts_mod.image_data_url(self.vault_path, sha)
                mime, encoded = data_url.split(';base64,', 1)
                mime = mime[len('data:'):]
                data = self.services.base64.b64decode(encoded)
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'private, max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            elif path == '/api/drafts/counts':
                self._json({'status': 'ok', 'counts': self.services.drafts_mod.counts(self.vault_path)})
            elif path == '/api/drafts/job':
                self._json({'status': 'ok', 'job': self.services.drafts_mod.get_job(self.vault_path, params.get('id', ''))})
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except self.services.drafts_mod.DraftError as exc:
            payload = {'status': 'error', 'msg': str(exc), 'code': exc.code}
            if exc.current_revision is not None:
                payload['current_revision'] = exc.current_revision
            self._json(payload, exc.status)
        except Exception as exc:
            self._error(exc)

    def _drafts_post(self, path):
        try:
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(self.services.http_io.content_length(self))
            data = self.services.http_io.json_body(self, body)
            if not isinstance(data, dict):
                raise self.services.drafts_mod.DraftError('请求必须是 JSON 对象')
            if 'crops' in data:
                data['crops'] = self._image_references(data['crops'], 'draft')
            draft_id, revision = (data.get('id'), data.get('revision'))
            if path == '/api/drafts/update':
                result = {'draft': self.services.drafts_mod.update_draft(self.vault_path, draft_id, revision, data.get('fields'), data.get('blocks'), data.get('source_images'))}
            elif path == '/api/drafts/discard':
                result = {'draft': self.services.drafts_mod.discard_draft(self.vault_path, draft_id, revision)}
            elif path == '/api/drafts/commit':
                result = self.services.drafts_mod.commit_draft(self.vault_path, draft_id, revision, data.get('crops'))
            elif path == '/api/drafts/boxes':
                result = {'draft': self.services.drafts_mod.set_boxes(self.vault_path, draft_id, revision, data.get('blocks'), data.get('training_boxes'))}
            elif path == '/api/drafts/extract':
                result = {'job': self.services.drafts_mod.start_extract(self.vault_path, draft_id, revision, data.get('block_ids'), data.get('crops'))}
            elif path == '/api/drafts/detect':
                result = {'job': self.services.drafts_mod.start_detect(self.vault_path, draft_id, revision, data.get('sha'))}
            elif path == '/api/drafts/image/train':
                result = self.services.drafts_mod.set_image_training(self.vault_path, draft_id, revision, data.get('sha'), data.get('enabled'))
            elif path == '/api/drafts/cleanup':
                if data:
                    raise self.services.drafts_mod.DraftError('cleanup 不接受自定义参数')
                result = self.services.drafts_mod.cleanup(self.vault_path)
            else:
                self._json({'status': 'error', 'msg': 'not found', 'code': 'not_found'}, 404)
                return
            self._json({'status': 'ok', **result})
        except self.services.drafts_mod.DraftError as exc:
            payload = {'status': 'error', 'msg': str(exc), 'code': exc.code}
            if exc.current_revision is not None:
                payload['current_revision'] = exc.current_revision
            self._json(payload, exc.status)
        except (ValueError, TypeError) as exc:
            self._json({'status': 'error', 'msg': str(exc), 'code': 'invalid'}, 400)
