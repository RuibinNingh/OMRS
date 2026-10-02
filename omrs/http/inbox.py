"""HTTP inbox 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class InboxRoutes:

    def _inbox_get(self, path, params):
        try:
            if path == '/m':
                self._serve('assets/inbox_mobile.html', 'text/html')
            elif path == '/api/inbox/items':
                self._json({'status': 'ok', 'items': self.services.inbox_mod.list_items(self.vault_path, status=params.get('status') or None)})
            elif path == '/api/inbox/item':
                self._json({'status': 'ok', 'item': self.services.inbox_mod.get_item(self.vault_path, params.get('id', ''))})
            elif path == '/api/inbox/raw':
                mime, data = self.services.inbox_mod.raw_file(self.vault_path, params.get('id', ''))
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'private, max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            elif path == '/api/inbox/job':
                self._json({'status': 'ok', 'job': self.services.inbox_mod.get_job(self.vault_path, params.get('id', ''))})
            elif path == '/api/inbox/slice-plan':
                plan = self.services.inbox_mod.slice_plan(int(params.get('width', 0) or 0), int(params.get('height', 0) or 0))
                self._json({'status': 'ok', 'strips': [{'y0': a, 'y1': b} for a, b in plan]})
            elif path == '/api/inbox/dataset/stats':
                self._json({'status': 'ok', **self.services.inbox_mod.dataset_stats(self.vault_path)})
            elif path == '/api/inbox/dataset/export':
                data = self.services.inbox_mod.export_dataset(self.vault_path, fmt=params.get('format', 'omrs_jsonl'), include_raw=params.get('raw', '1') != '0')
                stamp = self.services.datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="omrs-dataset-{stamp}.zip"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except Exception as exc:
            self._error(exc)

    def _inbox_post(self, path):
        try:
            length = int(self.headers.get('Content-Length', 0))
            content_type = self.headers.get('Content-Type', '')
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(length)
            if path in ('/api/inbox/upload', '/api/inbox/upload-refs'):
                if 'multipart/form-data' in content_type:
                    files = getattr(self, '_prepared_files', None) or self._multipart_files(body, content_type)
                    source = 'phone' if 'Mobile' in (self.headers.get('User-Agent') or '') else 'desktop'
                    result = self.services.inbox_mod.upload_images(self.vault_path, files, source=source)
                else:
                    data = self.services.http_io.json_body(self, body)
                    files = []
                    for entry in data.get('images', []):
                        value = entry.get('data', entry) if isinstance(entry, dict) else entry
                        if isinstance(value, dict) and value.get('upload_ref'):
                            self.services.uploads.resolve(self.vault_path, value, purpose='inbox')
                            raw = value
                        else:
                            mime, raw = self.services.inbox_mod._data_url_bytes(value)
                        files.append((entry.get('filename', entry.get('name', 'image')) if isinstance(entry, dict) else 'image', raw))
                    result = self.services.inbox_mod.upload_images(self.vault_path, files, source=data.get('source', 'desktop'))
                self._json({'status': 'ok', **result})
                return
            data = self.services.http_io.json_body(self, body)
            if path == '/api/inbox/item/update':
                cards = data.get('cards') if isinstance(data.get('cards'), dict) else {}
                deprecated = [f'cards.{key}.page' for key, form in cards.items() if isinstance(form, dict) and 'page' in form]
                self._json({'status': 'ok', 'item': self.services.inbox_mod.update_item(self.vault_path, data.get('id', ''), data, require_epoch=True, require_version=True), **({'deprecated_fields': deprecated} if deprecated else {})})
            elif path == '/api/inbox/item/reset':
                self._json({'status': 'ok', 'item': self.services.inbox_mod.reset_item(self.vault_path, data.get('id', ''), data.get('expected_revision'), data.get('reset_epoch'), require_version=True)})
            elif path == '/api/inbox/discard':
                entries = data.get('items') or ([data] if data.get('id') else [{'id': item_id} for item_id in data.get('ids') or []])
                self._json({'status': 'ok', 'results': self.services.inbox_mod.discard_items(self.vault_path, entries, require_version=True)})
            elif path == '/api/inbox/jobs':
                self._json({'status': 'ok', 'job': self.services.inbox_mod.start_job(self.vault_path, data.get('type', ''), data)})
            elif path == '/api/inbox/commit':
                deprecated = ['form.page'] if 'page' in (data.get('form') or {}) else []
                self._json({'status': 'ok', **self.services.inbox_mod.commit_item(self.vault_path, data.get('id', ''), card=data.get('card', 1), form=data.get('form') or {}, crops=data.get('crops') or {}, expected_revision=data.get('expected_revision'), reset_epoch=data.get('reset_epoch'), require_version=True), **({'deprecated_fields': deprecated} if deprecated else {})})
            elif path == '/api/inbox/crops':
                saved = [self.services.inbox_mod.save_crop(self.vault_path, rid, url) for rid, url in (data.get('crops') or {}).items()]
                self._json({'status': 'ok', 'saved': len(saved)})
            elif path == '/api/inbox/cleanup':
                days = data.get('discarded_days')
                self._json({'status': 'ok', **self.services.inbox_mod.cleanup(self.vault_path, discarded_days=int(days) if days not in (None, '') else None, crops=bool(data.get('crops')))})
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except self.services.inbox_mod.InboxConflict as exc:
            self._json({'status': 'error', 'msg': str(exc), 'code': exc.code, 'current_revision': exc.current_revision}, 409)
        except Exception as exc:
            self._error(exc)
