"""HTTP training 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class TrainingRoutes:

    def _trainpanel_post(self, path):
        if path == '/api/trainpanel/control':
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 4096:
                    self.close_connection = True
                    raise ValueError('控制请求过大或为空')
                remote, client_ip, _ = self._security_context()
                session = self._active_session
                actor = {'auth_mode': 'pin_session' if session else 'lan_exempt' if remote else 'local', 'session_id': session['id'] if session else '', 'client_ip': client_ip}
                value = self.services.traincontrol.submit(self.vault_path, self.services.http_io.json_body(self), actor=actor)
                self._json({'status': 'ok', 'operation': value}, 202)
            except self.services.traincontrol.Conflict as exc:
                self._json({'status': 'error', 'msg': str(exc)}, 409)
            except (ValueError, OSError, KeyError) as exc:
                self._error(exc)
            return
        if path == '/api/trainpanel/review':
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 16384:
                    self.close_connection = True
                    raise ValueError('复核请求过大或为空')
                data = self.services.http_io.json_body(self)
                if not isinstance(data, dict):
                    raise ValueError('复核请求必须是对象')
                value = self.services.trainaudit_mod.save_review(self.services.trainpanel_mod.train_dir(self.vault_path), data.get('audit', ''), data.get('case', ''), data.get('revision'), data.get('action'), data.get('verdict'), data.get('note', ''), source='user')
                self._json({'status': 'ok', **value})
            except self.services.trainaudit_mod.Conflict as exc:
                self._json({'status': 'error', 'msg': str(exc)}, 409)
            except (ValueError, OSError, self.services.sqlite3.Error) as exc:
                self._error(exc)
            return
        if path != '/api/trainpanel/try':
            self._json({'status': 'error', 'msg': 'not found'}, 404)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            content_type = self.headers.get('Content-Type', '')
            if length <= 0 or length > self.services.trainpanel_mod.MAX_UPLOAD_BYTES + 65536:
                self.close_connection = True
                raise ValueError('请求超过 15 MB 或为空')
            if 'multipart/form-data' not in content_type:
                raise ValueError('请用 multipart/form-data 上传图片')
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(length)
            result = self.services.trainpanel_mod.try_image(self.vault_path, self._multipart_files(body, content_type))
            self._json({'status': 'ok', **result})
        except (ValueError, OSError, self.services.sqlite3.Error) as exc:
            self._error(exc)

    def _trainpanel_get(self, path, params):
        try:
            if path == '/train':
                self._serve('assets/app/trainpanel.html', 'text/html')
            elif path == '/api/trainpanel/manager':
                self._json({'status': 'ok', **self.services.traincontrol.overview(self.vault_path)})
            elif path == '/api/trainpanel/audits':
                self._json({'status': 'ok', **self.services.trainaudit_mod.list_audits(self.vault_path)})
            elif path == '/api/trainpanel/audit':
                self._json({'status': 'ok', **self.services.trainaudit_mod.detail(self.vault_path, params.get('id', ''), params)})
            elif path == '/api/trainpanel/reviews':
                root = self.services.trainpanel_mod.train_dir(self.vault_path)
                self.services.trainaudit_mod.audit(root, params.get('id', ''))
                rows = self.services.trainaudit_mod.reviews(root, params.get('id', ''), params.get('case', ''))
                self._json({'status': 'ok', 'reviews': rows[-100:]})
            elif path == '/api/trainpanel/audit-image':
                image = self.services.trainaudit_mod.image_path(self.vault_path, params.get('id', ''), params.get('resource', ''))
                data = image.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png' if image.suffix.lower() == '.png' else 'image/jpeg')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'private, no-store')
                self.end_headers()
                self.wfile.write(data)
            elif path == '/api/trainpanel/overview':
                self._json({'status': 'ok', **self.services.trainpanel_mod.overview(self.vault_path)})
            elif path == '/api/trainpanel/run':
                self._json({'status': 'ok', **self.services.trainpanel_mod.run_detail(self.vault_path, params.get('name', ''))})
            elif path == '/api/trainpanel/service':
                self._json({'status': 'ok', **self.services.trainpanel_mod.service(self.vault_path)})
            elif path == '/api/trainpanel/overlay':
                image = self.services.trainpanel_mod.overlay_path(self.vault_path, params.get('run', ''), params.get('name', ''))
                data = image.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png' if image.suffix.lower() == '.png' else 'image/jpeg')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'private, no-store')
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except (ValueError, OSError, self.services.sqlite3.Error) as exc:
            self._error(exc)

    def _annotate_get(self, path, params):
        try:
            if path == '/annotate':
                self._serve('assets/app/annotate.html', 'text/html')
            elif path == '/api/annotate/images':
                self._json({'status': 'ok', 'images': self.services.annotate_mod.list_images(self.vault_path), 'stats': self.services.annotate_mod.stats(self.vault_path)})
            elif path == '/api/annotate/stats':
                self._json({'status': 'ok', **self.services.annotate_mod.stats(self.vault_path)})
            elif path == '/api/annotate/raw':
                mime, data = self.services.annotate_mod.raw_file(self.vault_path, params.get('id', ''))
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'private, max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            elif path == '/api/annotate/export':
                with self.services.tempfile.TemporaryFile() as tmp:
                    size = self.services.annotate_mod.export(self.vault_path, fmt=params.get('format', 'omrs_jsonl'), include_todo=params.get('all', '') in {'1', 'true', 'yes'}, fileobj=tmp)
                    tmp.seek(0)
                    stamp = self.services.datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/zip')
                    self.send_header('Content-Disposition', f'attachment; filename="omrs-annotate-{stamp}.zip"')
                    self.send_header('Content-Length', str(size))
                    self.end_headers()
                    self.services.shutil.copyfileobj(tmp, self.wfile, 1024 * 1024)
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except Exception as exc:
            self._error(exc)

    def _annotate_post(self, path):
        try:
            length = int(self.headers.get('Content-Length', 0))
            content_type = self.headers.get('Content-Type', '')
            body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(length)
            if path in ('/api/annotate/upload', '/api/annotate/upload-refs'):
                if hasattr(self, '_prepared_json'):
                    data = self.services.http_io.json_body(self, body)
                    image_files = [(entry.get('filename', entry.get('name', 'image')), entry.get('data', entry)) for entry in data.get('images', [])]
                else:
                    image_files = getattr(self, '_prepared_files', None) or self._multipart_files(body, content_type)
                self._json({'status': 'ok', **self.services.annotate_mod.upload(self.vault_path, image_files)})
                return
            data = self.services.http_io.json_body(self, body)
            if not isinstance(data, dict):
                raise ValueError('请求体必须是 JSON 对象')
            if path == '/api/annotate/save':
                self._json({'status': 'ok', 'image': self.services.annotate_mod.save(self.vault_path, data.get('id', ''), data.get('boxes'), data.get('status'), data.get('expected_revision'))})
            elif path == '/api/annotate/delete':
                self._json({'status': 'ok', **self.services.annotate_mod.delete(self.vault_path, data.get('id', ''), data.get('expected_revision'))})
            else:
                self._json({'status': 'error', 'msg': 'not found'}, 404)
        except self.services.annotate_mod.RevisionConflict as exc:
            self._json({'status': 'error', 'code': 'revision_conflict', 'msg': str(exc), 'current_revision': exc.current_revision}, 409)
        except Exception as exc:
            self._error(exc)
