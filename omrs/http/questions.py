"""HTTP questions 领域路由。"""

class QuestionsRoutes:

    def _questions_post(self, path):
        body = b'' if hasattr(self, '_prepared_json') else self.rfile.read(self.services.http_io.content_length(self))
        if path == '/api/create':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.create_question(self.vault_path, subject=data['subject'], category=data['category'], difficulty=int(data.get('difficulty', 5)), related_tags=data.get('related_tags', []), labels=data.get('labels', []), question_text=data.get('question_text', ''), answer_text=data.get('answer_text', ''), cause=data.get('cause', ''), question_images=data.get('question_images', []), answer_images=data.get('answer_images', []))
                self._json({'status': 'ok', **result, **({'deprecated_fields': ['note']} if 'note' in data else {})})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/ai-recognize':
            try:
                data = self.services.http_io.json_body(self, body)
                quick_scope = data.get('scope') == 'quick'
                question_image = data.get('question_image') or data.get('image', '')
                answer_image = data.get('answer_image', '')
                if isinstance(question_image, dict):
                    question_image = self.services.uploads.image_data_url(self.vault_path, question_image, purpose='create')
                if isinstance(answer_image, dict):
                    answer_image = self.services.uploads.image_data_url(self.vault_path, answer_image, purpose='create')
                mode = data.get('mode', 'classify')
                result = self.services.recognize_question(self.vault_path, question_image, mode=mode, hint_subject=data.get('subject', ''), hint_category=data.get('category', ''), answer_image=answer_image, allow_labels=not quick_scope)
                if quick_scope:
                    allowed = {'mode', 'subject', 'category', 'difficulty', 'knowledge_tags', 'cause_candidate', 'restrict_tags'} if mode == 'classify' else {'mode', 'question_text'} if mode in ('question_text', 'question') else {'mode', 'answer'}
                    result = {key: value for key, value in result.items() if key in allowed}
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/label/save':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.save_label(self.vault_path, value=data.get('id'), name=data.get('name'), color=data.get('color'), priority_bonus=data.get('priority_bonus'), order=data.get('order'))
                self._json({'status': 'ok', 'label': result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/label/delete':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.delete_label(self.vault_path, data.get('id') or data.get('name'), detach=data.get('detach', True) is not False)
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/label/merge':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.merge_labels(self.vault_path, data.get('from') or data.get('source'), data.get('into') or data.get('target'))
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/labels':
            try:
                data = self.services.http_io.json_body(self, body)
                from ..question_ops import set_question_labels
                result = set_question_labels(self.vault_path, self._question_uid(data), data.get('labels') or [])
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/questions/labels':
            try:
                data = self.services.http_io.json_body(self, body)
                from ..question_ops import set_question_labels
                references = data.get('question_refs')
                if references is not None:
                    if not isinstance(references, list) or not all((isinstance(ref, dict) for ref in references)):
                        raise ValueError('question_refs 必须是题目引用数组')
                    uids = list(dict.fromkeys((self._question_uid(ref) for ref in references)))
                else:
                    uids = list(dict.fromkeys((str(uid).strip() for uid in data.get('uids') or [] if str(uid).strip())))
                add = [str(value).strip() for value in data.get('add') or [] if str(value).strip()]
                remove = {str(value).strip() for value in data.get('remove') or [] if str(value).strip()}
                changed = 0
                failed = []
                for uid in uids:
                    try:
                        question = self.services.get_question_content(self.vault_path, uid)
                        current = list(question.get('labels') or [])
                        next_labels = [value for value in dict.fromkeys(current + add) if value not in remove]
                        result = set_question_labels(self.vault_path, uid, next_labels, scan=False)
                        changed += int(result.get('changed', False))
                    except Exception as exc:
                        failed.append({'uid': uid, 'msg': str(exc)})
                scan = self.services.scan_workspace(self.vault_path) if changed else {'status': 'ok', 'changes': 0, 'conflicts': []}
                self._json({'status': 'ok', 'changed': changed, 'failed': failed, 'scan': scan})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/markdown':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.save_question_markdown(self.vault_path, self._question_uid(data), data.get('markdown', ''), expected_content_hash=str(data.get('expected_content_hash') or ''))
                self._json({'status': 'ok', **result})
            except self.services.ContentConflict as exc:
                self._json({'status': 'error', 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/content/restore':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.restore_content(self.vault_path, self._question_uid(data), data.get('hash', ''), expected_hash=str(data.get('expected_content_hash') or '') or None)
                self._json({'status': 'ok', **result})
            except self.services.ContentConflict as exc:
                self._json({'status': 'error', 'msg': str(exc)}, 409)
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/move':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.move_question(self.vault_path, self._question_uid(data), data.get('subject', ''), data.get('category', ''))
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/suspend':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.suspend_question(self.vault_path, self._question_uid(data), data.get('reason', ''))
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/resume':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.resume_question(self.vault_path, self._question_uid(data), data.get('reason', ''))
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        elif path == '/api/question/delete':
            try:
                data = self.services.http_io.json_body(self, body)
                result = self.services.delete_question(self.vault_path, self._question_uid(data))
                self._json({'status': 'ok', **result})
            except Exception as exc:
                self._error(exc)
        else:
            self._json({'status': 'error', 'msg': '接口不存在'}, 404)
