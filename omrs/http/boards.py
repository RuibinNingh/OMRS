"""HTTP boards 领域路由。"""

class BoardsRoutes:

    def _boards_post(self, path):
        body = b'' if hasattr(self, '_prepared_json') else self.rfile.read(self.services.http_io.content_length(self))
        if path == '/api/board/create':
            try:
                data = self.services.http_io.json_body(self, body)
                uids = list(data.get('question_refs') if 'question_refs' in data else data.get('uids') or [])
                if data.get('label') and (not uids):
                    rows = self.services.get_stats(self.vault_path).get('items', [])
                    uids = [row.get('uid') for row in rows if data.get('label') in (row.get('labels') or [])]
                board = self.services.create_board(self.vault_path, data.get('name', ''), uids, data.get('label', ''), str(data.get('folder_id') or ''), **self._board_versions(data, catalog=True))
                self._board_json({'status': 'ok', 'board': board})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/update':
            try:
                data = self.services.http_io.json_body(self, body)
                board_id = str(data.get('id') or '').strip()
                if not board_id:
                    raise ValueError('展示板 id 不能为空')
                changes = {key: data[key] for key in ('name', 'note', 'print', 'items', 'source_labels', 'folder_id') if key in data}
                self._board_json({'status': 'ok', 'board': self.services.update_board(self.vault_path, board_id, **changes, **self._board_versions(data, board=True, catalog='folder_id' in changes or 'name' in changes))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/items/add':
            try:
                data = self.services.http_io.json_body(self, body)
                self._board_json({'status': 'ok', 'board': self.services.board_add_items(self.vault_path, str(data.get('id') or ''), data.get('question_refs') if 'question_refs' in data else data.get('uids') or [], data.get('position'), **self._board_versions(data, board=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/items/remove':
            try:
                data = self.services.http_io.json_body(self, body)
                self._board_json({'status': 'ok', 'board': self.services.board_remove_items(self.vault_path, str(data.get('id') or ''), data.get('question_refs') if 'question_refs' in data else data.get('uids') or [], **self._board_versions(data, board=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/duplicate':
            try:
                data = self.services.http_io.json_body(self, body)
                self._board_json({'status': 'ok', 'board': self.services.duplicate_board(self.vault_path, str(data.get('id') or ''), data.get('name', ''), **self._board_versions(data, board=True, catalog=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/folder/create':
            try:
                data = self.services.http_io.json_body(self, body)
                self._board_json({'status': 'ok', 'folder': self.services.board_create_folder(self.vault_path, data.get('name', ''), **self._board_versions(data, catalog=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/folder/update':
            try:
                data = self.services.http_io.json_body(self, body)
                changes = {key: data[key] for key in ('name', 'order') if key in data}
                self._board_json({'status': 'ok', 'folder': self.services.board_update_folder(self.vault_path, str(data.get('id') or ''), **changes, **self._board_versions(data, catalog=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/folder/delete':
            try:
                data = self.services.http_io.json_body(self, body)
                keep = data.get('keep_boards', True)
                result = self.services.board_delete_folder(self.vault_path, str(data.get('id') or ''), keep is not False, **self._board_versions(data, catalog=True))
                self._board_json({'status': 'ok', **result})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/move':
            try:
                data = self.services.http_io.json_body(self, body)
                self._board_json({'status': 'ok', 'board': self.services.board_move(self.vault_path, str(data.get('id') or ''), data.get('folder_id'), data.get('index'), **self._board_versions(data, board=True, catalog=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/delete':
            try:
                data = self.services.http_io.json_body(self, body)
                ok = self.services.delete_board(self.vault_path, str(data.get('id') or ''), **self._board_versions(data, board=True, catalog=True))
                self._board_json({'status': 'ok' if ok else 'error', 'deleted': ok})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/printed':
            try:
                data = self.services.http_io.json_body(self, body)
                board = self.services.board_record_printed(self.vault_path, str(data.get('id') or ''), str(data.get('mode') or 'all'), data.get('layout') if isinstance(data.get('layout'), dict) else {}, **self._board_versions(data, board=True))
                self._board_json({'status': 'ok', 'board': board})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/board/printed/reset':
            try:
                data = self.services.http_io.json_body(self, body)
                self._board_json({'status': 'ok', 'board': self.services.board_reset_printed(self.vault_path, str(data.get('id') or ''), **self._board_versions(data, board=True))})
            except self.services.board_mod.BoardConflict as exc:
                self._board_json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        else:
            self._json({'status': 'error', 'msg': '接口不存在'}, 404)
