"""HTTP history 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class HistoryRoutes:

    def _history_commit_payload(self, commit_type, data):
        if not isinstance(data, dict):
            raise ValueError('请求体必须是 JSON 对象')
        if commit_type.startswith('review.'):
            return self._history_review_payload(commit_type, data)
        if commit_type.startswith('session.'):
            session_id = str(data.get('session_id') or '').strip()
            if not session_id:
                raise ValueError('session_id 不能为空')
            if not self._known_history_session(session_id):
                raise ValueError(f'Session 不存在或没有历史反馈：{session_id}')
            return {**data, 'session_id': session_id, 'reason': str(data.get('reason') or '').strip()}
        if commit_type == 'state.restore':
            target_seq = self._history_nonnegative_int(data.get('target_seq'), 'target_seq')
            if target_seq <= 0:
                raise ValueError('target_seq 必须大于 0')
            if self.services.get_commit(self.vault_path, target_seq) is None:
                raise ValueError(f'目标 seq 不存在：{target_seq}')
            return {**data, 'target_seq': target_seq, 'reason': str(data.get('reason') or '').strip()}
        return data

    def _history_review_payload(self, commit_type, data):
        target_commit_id = str(data.get('target_commit_id') or '').strip()
        if not target_commit_id:
            raise ValueError('target_commit_id 不能为空')
        target = self.services.get_commit_by_id(self.vault_path, target_commit_id)
        if not target or target.get('commit_type') != 'review.batch_submit':
            raise ValueError(f'目标反馈提交不存在：{target_commit_id}')
        reviews = target.get('payload', {}).get('feedbacks') or target.get('payload', {}).get('reviews') or []
        index = self._history_nonnegative_int(data.get('target_review_index'), 'target_review_index')
        if index >= len(reviews):
            raise ValueError(f'target_review_index 越界：{index}')
        cleaned = {**data, 'target_commit_id': target_commit_id, 'target_review_index': index, 'reason': str(data.get('reason') or '').strip()}
        if commit_type == 'review.replace':
            replacement = data.get('replacement')
            if not isinstance(replacement, dict):
                raise ValueError('replacement 必须是 JSON 对象')
            score = self._history_score(replacement.get('sub_score'))
            cleaned['replacement'] = {'sub_score': score, 'is_correct': self._history_bool(replacement.get('is_correct'), 'replacement.is_correct'), 'note': str(replacement.get('note') or '')}
        return cleaned

    def _history_nonnegative_int(self, value, field):
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise ValueError(f'{field} 必须是整数')
        if result < 0:
            raise ValueError(f'{field} 不能小于 0')
        return result

    def _history_score(self, value):
        try:
            score = int(round(float(value)))
        except (TypeError, ValueError):
            raise ValueError('replacement.sub_score 必须是 0-10 的数字')
        if score < 0 or score > 10:
            raise ValueError('replacement.sub_score 必须在 0-10 之间')
        return score

    def _history_bool(self, value, field):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {'true', '1', 'yes', 'y', '对', '正确'}:
                return True
            if text in {'false', '0', 'no', 'n', '错', '错误'}:
                return False
        raise ValueError(f'{field} 必须是布尔值')

    def _known_history_session(self, session_id):
        for commit in self.services.read_commits(self.vault_path, ascending=True):
            payload = commit.get('payload') or {}
            ctype = commit.get('commit_type')
            if ctype == 'legacy.bootstrap':
                if any((row.get('Session_ID') == session_id for row in payload.get('session_rows', []))):
                    return True
                if any((row.get('Session_ID') == session_id for row in payload.get('history_rows', []))):
                    return True
            if ctype == 'session.create':
                session = payload.get('session') or payload
                if session.get('session_id') == session_id:
                    return True
            if ctype == 'review.batch_submit':
                if payload.get('session_id') == session_id:
                    return True
                reviews = payload.get('feedbacks') or payload.get('reviews') or []
                if any((review.get('session_id') == session_id for review in reviews)):
                    return True
        return False

    def _history_commit(self, commit_type, message, body):
        try:
            data = self.services.http_io.json_body(self, body)
            data = self._history_commit_payload(commit_type, data)
            commit = self.services.append_commit(self.vault_path, 'api', commit_type, message, data)
            self.services.rebuild_projection(self.vault_path)
            self._json({'status': 'ok', **commit})
        except Exception as exc:
            self._error(exc)

    def _history_post(self, path):
        body = b'' if hasattr(self, '_prepared_json') else self.rfile.read(self.services.http_io.content_length(self))
        if path == '/api/history/review/replace':
            self._history_commit('review.replace', '修改旧反馈', body)
        elif path == '/api/history/review/retract':
            self._history_commit('review.retract', '撤销旧反馈', body)
        elif path == '/api/history/review/restore':
            self._history_commit('review.restore', '恢复旧反馈', body)
        elif path == '/api/history/session/retract':
            self._history_commit('session.retract', '撤销 Session', body)
        elif path == '/api/history/session/restore':
            self._history_commit('session.restore', '恢复 Session', body)
        elif path == '/api/history/state/restore':
            self._history_commit('state.restore', '还原到历史节点', body)
        else:
            self._json({'status': 'error', 'msg': '接口不存在'}, 404)
