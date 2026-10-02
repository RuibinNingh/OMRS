"""HTTP learning 领域路由。"""

class LearningRoutes:

    def _learning_post(self, path):
        body = b'' if hasattr(self, '_prepared_json') else self.rfile.read(self.services.http_io.content_length(self))
        if path == '/api/schedule':
            try:
                data = self.services.http_io.json_body(self, body)
                session = self.services.create_session(self.vault_path, int(data.get('count', 10)), data.get('subject') or None)
                self._json({'status': 'ok', 'session_id': session['session_id'], 'created_at': session['created_at'], 'subject_filter': session['subject_filter'], 'count': session['count'], 'session_status': session['status'], 'completed_at': session['completed_at'], 'items': session['items'], 'entries': session.get('entries',[]), 'uids': session.get('uids',[]), 'feedback_uids': session.get('feedback_uids',[])})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/session/bind':
            try:
                from ..sessions import bind_session_entry
                data = self.services.http_io.json_body(self, body)
                result = bind_session_entry(self.vault_path, data.get('session_id', ''), data.get('entry_id', ''), data.get('question_id', ''))
                self._json({'status': 'ok', 'session': result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/session/delete':
            try:
                data = self.services.http_io.json_body(self, body)
                ok = self.services.delete_session(self.vault_path, data.get('session_id', ''))
                self._json({'status': 'ok' if ok else 'error', 'deleted': ok})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/feedback':
            try:
                data = self.services.http_io.json_body(self, body)
                results = self.services.process_feedback(self.vault_path, data.get('feedbacks', []), data.get('session_id', ''), attempt_id=data.get('attempt_id', ''))
                self._json({'status': 'ok', 'results': results})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/confirm-schedule':
            try:
                data = self.services.http_io.json_body(self, body)
                selected = data.get('selected', [])
                if not isinstance(selected, list) or len(selected) < 1:
                    self._json({'status': 'error', 'msg': '至少选择 1 道题'}, 400)
                    return
                if 'persist' in data and (not isinstance(data['persist'], bool)):
                    raise ValueError('persist 必须为布尔值')
                if len(selected) == 1 and (not data.get('persist', False)):
                    from ..scheduling import get_items_by_uids
                    import datetime as dt_mod
                    uid = self._question_uid(selected[0]) if isinstance(selected[0], dict) else selected[0]
                    items = get_items_by_uids(self.vault_path, [uid])
                    session_id = f"TMP-{dt_mod.datetime.now().strftime('%Y%m%d%H%M%S')}"
                    self._json({'status': 'ok', 'session_id': session_id, 'session_type': 'tmp', 'count': 1, 'items': items})
                else:
                    session = self.services.create_session_from_selection(self.vault_path, selected, data.get('subject') or None)
                    self._json({'status': 'ok', 'session_type': 'exp', **session})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/export':
            try:
                data = self.services.http_io.json_body(self, body)
                uids = data.get('uids', [])
                references = data.get('question_refs')
                session_id = data.get('session_id', '')
                export_format = (data.get('format') or 'a4').strip().lower()
                include_answers = bool(data.get('include_answers', False))
                question_gap_lines = data.get('question_gap_lines', 0)
                a4_two_columns = data.get('a4_two_columns', True)
                if export_format == 'board':
                    board_id = str(data.get('board_id') or data.get('id') or '').strip()
                    if not board_id:
                        self._json({'status': 'error', 'msg': 'board_id 不能为空'}, 400)
                        return
                    mode = 'new' if str(data.get('mode') or '').lower() == 'new' else 'all'
                    payload = self.services.export_board_html(self.vault_path, board_id, mode=mode, include_answers=data.get('include_answers'), overrides=data.get('overrides') if isinstance(data.get('overrides'), dict) else None)
                    board = self.services.get_board(self.vault_path, board_id) or {}
                    self._download(payload, self.services.board_export_filename(board, mode), 'text/html; charset=utf-8')
                    return
                if not uids and not references and (not session_id):
                    self._json({'status': 'error', 'msg': '需要 session_id 或 uids'}, 400)
                    return
                payload, sid, filename, content_type = self.services.export_schedule_artifact(self.vault_path, uids or None, session_id, export_format, include_answers=include_answers, question_gap_lines=question_gap_lines, a4_two_columns=a4_two_columns, question_refs=references)
                self._download(payload, filename, content_type)
            except Exception as exc:
                self._error(exc)
        else:
            self._json({'status': 'error', 'msg': '接口不存在'}, 404)
