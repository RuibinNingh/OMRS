"""统计、题目、反馈、计划、展示板及维护 HTTP 适配。"""

class CoreRoutes:

    def _core_get(self, path, params):
        query_pairs = self.services.urllib.parse.parse_qsl(self.services.urllib.parse.urlparse(self.path).query, keep_blank_values=True)
        if path == '/api/stats':
            self._json(self.services.get_stats(self.vault_path))
        elif path == '/api/taxonomy':
            self._json({'status': 'ok', 'taxonomy': self.services.collect_taxonomy(self.vault_path)})
        elif path == '/api/labels':
            self._json({'status': 'ok', 'labels': self.services.list_label_defs(self.vault_path)})
        elif path == '/api/boards':
            self._json({'status': 'ok', **self.services.board_mod.catalog(self.vault_path)})
        elif path == '/api/board':
            board = self.services.get_board(self.vault_path, params.get('id', ''))
            if board is None:
                self._json({'status': 'error', 'msg': '展示板不存在'}, 404)
            else:
                self._json({'status': 'ok', 'board': board})
        elif path == '/api/status':
            try:
                stats = self.services.get_stats(self.vault_path)
                self._json({'status': 'ok', 'version': self.services.__version__, 'started_at': self.started_at.isoformat(), 'uptime_seconds': int(self.services.time.monotonic() - self.started_monotonic), 'question_count': int(stats.get('total', 0)), 'listen_external': bool(self.listen_external), 'vault_path': self.services.os.path.abspath(self.vault_path), 'workspace_scan': self.services.get_scan_status(self.vault_path)})
            except Exception as exc:
                self._json({'status': 'error', 'version': self.services.__version__, 'msg': str(exc)}, 500)
        elif path == '/api/analytics':
            try:
                self._json(self.services.get_analytics(self.vault_path))
            except Exception as exc:
                self._error(exc)
        elif path == '/api/source/export':
            try:
                payload, filename, _meta = self.services.create_source_export(self.vault_path)
                filename_encoded = self.services.urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f"""attachment; filename="{filename}"; filename*=UTF-8''{filename_encoded}""")
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/export-review':
            artifact = None
            try:
                include_images = params.get('include_images', '').strip().lower() in {'1', 'true', 'yes'}
                payload, filename, content_type = self.services.build_review_export(
                    self.vault_path, include_images=include_images, file_artifact=True)
                if isinstance(payload, (str, self.services.os.PathLike)):
                    artifact = payload
                    self._download_file(artifact, filename, content_type)
                else:
                    self._download(payload, filename, content_type)
            except Exception as exc:
                self._error(exc)
            finally:
                if artifact is not None:
                    try:
                        self.services.os.unlink(artifact)
                    except FileNotFoundError:
                        pass
        elif path == '/api/sessions':
            self._json({'sessions': self.services.list_sessions(self.vault_path, params.get('status'))})
        elif path == '/api/session':
            session_id = params.get('id', '')
            session = self.services.get_session(self.vault_path, session_id)
            if session is None:
                self._json({'status': 'error', 'msg': f'session {session_id} 不存在'}, 404)
            else:
                self._json(session)
        elif path == '/api/question':
            self._json(self.services.get_question_content(self.vault_path, params.get('uid', ''), question_id=params.get('question_id', '')))
        elif path == '/api/question/raw':
            try:
                self._json({'status': 'ok', **self.services.get_question_raw(self.vault_path, self._question_uid(params))})
            except Exception as exc:
                self._json({'status': 'error', 'msg': str(exc)}, getattr(exc, 'status', 404))
        elif path == '/api/history':
            try:
                before = params.get('before_seq') or None
                limit = int(params.get('limit', 100))
                limit = max(1, min(500, limit))
                summary_only = params.get('view') == 'summary'
                from ..runtime_records import filters
                options = filters(params)
                commits = self.services.ledger_history(self.vault_path, before, limit + 1 if summary_only else limit, summary_only=summary_only, **{key: options[key] for key in ('q', 'since', 'until')})
                has_more = summary_only and len(commits) > limit
                if has_more:
                    commits = commits[1:]
                self._json({'status': 'ok', 'commits': commits, 'has_more': has_more, 'next_before_seq': min((row['seq'] for row in commits), default=None) if has_more else None, 'retraction_state': self.services.ledger_retraction_state(self.vault_path), **({} if summary_only else {'history': __import__('omrs.data_repository', fromlist=['history_rows']).history_rows(self.vault_path, limit=100)})})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/history/detail':
            try:
                detail = self.services.ledger_history_detail(self.vault_path, int(params.get('seq', '0')))
                if detail is None:
                    self._json({'status': 'error', 'msg': '历史节点不存在'}, 404)
                else:
                    from ..runtime_records import calls_for_draft
                    try:
                        detail['runtime_calls'] = calls_for_draft(self.vault_path, detail.get('payload', {}).get('_draft', {}).get('draft_id'))
                    except (OSError, self.services.sqlite3.Error, ValueError):
                        detail['runtime_calls'] = []
                        detail['runtime_calls_error'] = '来源调用暂时无法读取，请稍后刷新。'
                    self._json({'status': 'ok', 'detail': detail})
            except (ValueError, TypeError) as exc:
                self._error(exc)
        elif path == '/api/runtime/records':
            self._runtime_records_get(params)
        elif path == '/api/runtime/records/detail':
            self._runtime_records_get(params, detail=True)
        elif path == '/api/question/content/history':
            try:
                self._json({'status': 'ok', **self.services.content_versions(self.vault_path, uid=params.get('uid') or None, question_id=params.get('question_id') or None)})
            except Exception as exc:
                self._json({'status': 'error', 'msg': str(exc)}, getattr(exc, 'status', 404))
        elif path == '/api/question/content/version':
            content = self.services.get_blob(self.vault_path, params.get('hash', ''))
            if content is None:
                self._json({'status': 'error', 'msg': '这个版本的正文不在 Ledger 里'}, 404)
            else:
                self._json({'status': 'ok', 'hash': params.get('hash', ''), 'markdown': content})
        elif path == '/api/ledger/verify':
            self._json(self.services.verify_ledger(self.vault_path))
        elif path == '/api/optimize/summary':
            try:
                self._json(self.services.storage_summary(self.vault_path))
            except Exception as exc:
                self._error(exc)
        elif path == '/api/optimize/job':
            job = self.services.get_job(params.get('id', ''))
            if not job:
                self._json({'status': 'error', 'msg': 'job 不存在'}, 404)
            else:
                self._json({'status': 'ok', 'job': job})
        elif path == '/api/scan':
            self._json({'status': 'error', 'msg': '请使用 POST /api/scan'}, 405)
        elif path == '/api/tree':
            try:
                self._json({'status': 'ok', **self.services.build_tree(self.vault_path)})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/config':
            from ..config_repository import public_config
            config = public_config(self.vault_path)
            config.update(self.services.security.auth_summary(self.vault_path))
            config['entry_background'] = self.services.entry_background.public_state(self.vault_path)
            self._json(config)
        elif path == '/api/reports':
            try:
                self._json({'status': 'ok', 'reports': self.services.list_reports(self.vault_path)})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/report/view':
            try:
                html = self.services.get_report_html(self.vault_path, params.get('id', ''))
                if self._active_session:
                    html = self.services.signed_report_images(html, self._sign_report_image)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Security-Policy', 'sandbox allow-scripts allow-downloads allow-popups')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except Exception as exc:
                self._json({'status': 'error', 'msg': str(exc)}, getattr(exc, 'status', 404))
        elif path == '/api/recommend':
            try:
                due_count = int(params.get('due_count', 10))
                prof_count = int(params.get('prof_count', 10))
                subject = params.get('subject') or None
                category = params.get('category') or None
                knowledge_tag = params.get('knowledge_tag') or None
                requested_labels = [value for key, value in query_pairs if key == 'label' and value]
                label = requested_labels if requested_labels else params.get('label') or None
                rec = self.services.generate_recommendations(self.vault_path, due_count=due_count, prof_count=prof_count, subject=subject, category=category, knowledge_tag=knowledge_tag, label=label, exclude_uids=self.services.active_session_uids(self.vault_path))
                self._json({'status': 'ok', **rec})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/image':
            name = params.get('name', '')
            if not name:
                self._json({'error': 'missing name'}, 400)
                return
            try:
                from ..question_images import read_attachment_image
                data, content_type = read_attachment_image(self.vault_path, name)
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                remote, _, _ = self._security_context()
                self.send_header('Cache-Control', 'no-store' if remote else 'max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            except (OSError, ValueError, TypeError):
                self._json({'status': 'error', 'msg': '附件不存在或无法安全读取'}, 404)
        elif path in ('/', '/index.html'):
            self._serve('omrs_dashboard.html', 'text/html')
        elif path.startswith('/assets/'):
            self._serve_asset(path)
        else:
            self.send_error(404)

    def _do_post_routes(self, path):
        from .registry import target
        route = target('POST', path)
        if route and route != '_do_post_routes':
            return getattr(self, route)(path)
        if path == '/api/backup/import':
            self._handle_backup_import()
            return
        if path == '/api/entry-background':
            self._entry_background_post()
            return
        if path.startswith('/api/inbox/'):
            self._inbox_post(path)
            return
        if path.startswith('/api/trainpanel/'):
            self._trainpanel_post(path)
            return
        if path.startswith('/api/drafts/'):
            self._drafts_post(path)
            return
        if path.startswith('/api/annotate/'):
            self._annotate_post(path)
            return
        body = b'' if hasattr(self, '_prepared_json') or hasattr(self, '_prepared_files') else self.rfile.read(self.services.http_io.content_length(self))
        if path == '/api/scan':
            try:
                index, scan = self.services.build_index(self.vault_path, return_scan=True)
                self._json({'status': 'ok', 'count': len(index), 'scan': scan})
            except RuntimeError as exc:
                self._error(exc)
        elif path == '/api/config':
            try:
                data = self.services.http_io.json_body(self, body)
                if not isinstance(data, dict):
                    raise ValueError('配置必须是 JSON 对象')
                if 'http_legacy_upload_mib' in data and (type(data['http_legacy_upload_mib']) is not int or not 2 <= data['http_legacy_upload_mib'] <= 8192):
                    raise ValueError('http_legacy_upload_mib 必须是 2 到 8192 的整数')
                if 'ai_thinking' in data and (not isinstance(data['ai_thinking'], bool)):
                    raise ValueError('ai_thinking 必须是布尔值')
                if 'inbox_detect_provider' in data and data['inbox_detect_provider'] not in self.services.inbox_mod.PROVIDERS:
                    raise ValueError('未知框选提供方')
                if 'lan_pin_exempt_cidrs' in data:
                    data['lan_pin_exempt_cidrs'] = self.services.security.normalize_lan_cidrs(data['lan_pin_exempt_cidrs'])
                effective = {**self.services.load_config(self.vault_path), **data}
                if effective.get('allow_external') and (not self.services.security.auth_summary(self.vault_path)['pin_configured']) and (not self.services.security.normalize_lan_cidrs(effective.get('lan_pin_exempt_cidrs', []))):
                    raise ValueError('启用外部访问前请设置 PIN 或配置局域网免 PIN 网段')
                if data.pop('clear_ai_api_key', False):
                    data['ai_api_key'] = ''
                elif data.get('ai_api_key') == '':
                    data.pop('ai_api_key')
                if data.pop('clear_agent_api_key', False):
                    data['agent_api_key'] = ''
                elif data.get('agent_api_key') == '':
                    data.pop('agent_api_key')
                from ..agent.config import validate_agent_config
                validate_agent_config(data)
                self.services.validate_draft_config(data)
                data.pop('pin_hash', None)
                data.pop('salt', None)
                result = self.services.save_config(self.vault_path, data)
                self._json({'status': 'ok', **(result or {})})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/workspace/scan':
            try:
                self._json({'status': 'ok', **self.services.scan_workspace(self.vault_path)})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/optimize/scan':
            try:
                self._json(self.services.scan_compression(self.vault_path))
            except Exception as exc:
                self._error(exc)
        elif path == '/api/optimize/compress':
            try:
                data = self.services.http_io.json_body(self, body)
                self._json(self.services.start_compression(self.vault_path, data.get('scan_id', ''), data.get('backup_token', ''), confirm=bool(data.get('confirm'))))
            except Exception as exc:
                self._error(exc)
        elif path == '/api/backup/export':
            try:
                payload, filename, token = self.services.create_backup_export(self.vault_path)
                try:
                    if isinstance(payload, (str, self.services.os.PathLike)):
                        self._download_file(payload, filename, 'application/zip', {'X-OMRS-Backup-Token': token})
                    else:
                        self._download(payload, filename, 'application/zip', {'X-OMRS-Backup-Token': token})
                finally:
                    if isinstance(payload, (str, self.services.os.PathLike)):
                        self.services.os.unlink(payload)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/backup/restore':
            try:
                data = self.services.http_io.json_body(self, body)
                self._json(self.services.restore_backup(self.vault_path, data.get('restore_id', ''), confirm=data.get('confirm') is True))
            except Exception as exc:
                self._error(exc)
        elif path == '/api/report/create':
            try:
                data = self.services.http_io.json_body(self, body)
                meta = self.services.create_report(self.vault_path, data.get('name', ''), data.get('html', ''))
                self._json({'status': 'ok', **meta})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/report/delete':
            try:
                data = self.services.http_io.json_body(self, body)
                ok = self.services.delete_report(self.vault_path, data.get('id', ''))
                self._json({'status': 'ok' if ok else 'error', 'deleted': ok})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/restart':
            self._json({'status': 'ok', 'msg': '正在重启...'})
            import subprocess
            import threading
            import time

            def _restart():
                service_name = self.services.os.environ.get('OMRS_SYSTEMD_SERVICE', '').strip()
                if service_name:
                    try:
                        result = subprocess.run(['systemctl', 'restart', '--no-block', service_name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                        if result.returncode == 0:
                            return
                    except OSError:
                        pass
                self.services.locking.acquire_for_shutdown(30.0)
                self.server.shutdown()
                time.sleep(1.5)
                cmd = getattr(self.services.OMRSHandler, '_restart_cmd', None)
                if cmd:
                    subprocess.Popen(cmd)
            threading.Thread(target=_restart, daemon=False).start()
        else:
            self._json({'status': 'error', 'msg': '接口不存在'}, 404)
