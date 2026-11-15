"""提醒素材、历史快照、动态缺错因及真实AI/MCP边界回归。"""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from omrs import schedule_reminders as reminders, schedule_banner as banner
from omrs.common import save_config
from omrs.exporting import _build_export_data
from omrs.locking import held_by_current_thread
from omrs.problems import ProblemConflict
from omrs.reflection_markdown import render
from tests.test_schedule_banner import SVG


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='omrs-reminders-')
        self.addCleanup(self.folder.cleanup)
        self.vault = self.folder.name

    def create(self, request='one', name='思考三步', svg=SVG):
        return reminders.create(self.vault, name, svg, request)['item']

    def test_read_is_pure_and_catalog_omits_source_bytes(self):
        self.assertEqual(reminders.catalog(self.vault)['items'], [])
        self.assertFalse(Path(self.vault, '错题/.omrs/problems.db').exists())
        made = self.create()
        public = reminders.catalog(self.vault)['items'][0]
        self.assertEqual(public['id'], made['id'])
        self.assertNotIn('src', public)
        self.assertNotIn('svg', public)
        self.assertIn('src', reminders.catalog(self.vault, True)['items'][0])
        self.assertFalse(banner.settings(self.vault)['enabled'])

    def test_create_retry_conflict_and_no_overwrite(self):
        made = self.create()
        self.assertEqual(self.create()['id'], made['id'])
        with self.assertRaises(ProblemConflict):
            self.create(name='别的内容')
        self.assertNotEqual(self.create('two')['id'], made['id'])
        self.assertEqual(len(reminders.catalog(self.vault)['items']), 2)

    def test_security_invalid_names_and_atomic_budget(self):
        for bad in [SVG.replace('<text ', '<text onclick="bad()" '), SVG.replace('font-size="20"', 'font-size="2"')]:
            with self.assertRaises(ValueError):
                self.create(svg=bad)
        for name in ['', '  ', 'a\nb', '字'*81]:
            with self.assertRaises(ValueError):
                self.create(name=name)
        with patch.object(reminders, 'MAX_ITEMS', 0), self.assertRaises(ValueError):
            self.create()
        self.assertEqual(reminders.catalog(self.vault)['items'], [])

    def test_deleted_material_is_not_recreated_by_retry_and_receipt_omits_bytes(self):
        from omrs import problem_store
        made = self.create()
        with problem_store.connect(self.vault) as db:
            saved = json.loads(db.execute('SELECT result FROM receipts').fetchone()[0])
        self.assertNotIn('src', saved['item'])
        reminders.delete(self.vault, made['id'], 1)
        with self.assertRaisesRegex(ValueError, '已删除'):
            self.create()
        self.assertEqual(reminders.catalog(self.vault)['items'], [])

    def test_legacy_template_survives_disable_and_can_be_deleted(self):
        banner.save_settings(self.vault, {'enabled': True, 'svg': SVG, 'expected_revision': 0})
        data = reminders.catalog(self.vault, True)
        identity = data['items'][0]['id']
        banner.save_settings(self.vault, {'enabled': False, 'reminder_id': identity, 'expected_revision': 1})
        self.assertEqual(reminders.catalog(self.vault)['items'][0]['id'], identity)
        banner.save_settings(self.vault, {'enabled': True, 'reminder_id': identity, 'expected_revision': 2})
        self.assertEqual(banner.for_export(self.vault)['svg'], SVG)
        self.assertTrue(reminders.delete(self.vault, identity, 1)['default_cleared'])
        self.assertEqual(reminders.catalog(self.vault)['items'], [])

    def test_default_cas_and_deleted_selection_fail_explicitly(self):
        made = self.create()
        banner.save_settings(self.vault, {'enabled': True, 'reminder_id': made['id'], 'expected_revision': 0})
        with self.assertRaises(ProblemConflict):
            banner.save_settings(self.vault, {'enabled': False, 'expected_revision': 0})
        self.assertEqual(banner.for_export(self.vault, override={'mode':'library','id':made['id']})['svg'], SVG)
        with self.assertRaises(ValueError):
            reminders.delete(self.vault, made['id'], True)
        self.assertTrue(reminders.delete(self.vault, made['id'], 1)['default_cleared'])
        self.assertFalse(banner.settings(self.vault)['enabled'])
        with self.assertRaises(ValueError):
            banner.for_export(self.vault, override={'mode':'library','id':made['id']})

    def test_authorization_rechecked_before_reuse_or_write(self):
        made = self.create()
        def deny():
            raise PermissionError('已撤权')
        with self.assertRaises(PermissionError):
            reminders.create(self.vault, '思考三步', SVG, 'one', authorize=deny)
        self.assertEqual(reminders.catalog(self.vault)['items'][0]['id'], made['id'])

    def test_ai_preview_uses_configured_client_without_write_lock_or_save(self):
        save_config(self.vault, {'agent_enabled':True, 'agent_model':'example', 'agent_base_url':'https://example.test/v1', 'agent_api_key':'synthetic'})
        def answer(*args, **kwargs):
            self.assertFalse(held_by_current_thread())
            self.assertFalse(kwargs['stream'])
            return {'content': '```svg\n'+SVG+'\n```', 'finish_reason':'stop'}
        with patch('omrs.agent.config.make_client', return_value=Mock(complete=answer)):
            self.assertEqual(reminders.generate(self.vault, '提醒我先读题')['snapshot']['svg'], SVG)
        self.assertEqual(reminders.catalog(self.vault)['items'], [])
        with patch('omrs.agent.config.make_client', return_value=Mock(complete=lambda *a,**k:{'content':SVG,'finish_reason':'length'})), self.assertRaises(ValueError):
            reminders.generate(self.vault, '提醒我先读题')

    def test_missing_cause_uses_effective_markdown_and_never_exposes_cause_in_question(self):
        q = {'uid':'合成1', 'question':'求解', 'notes':'## 错因\n\n区间端点漏检'}
        for marked in (True, False):
            data = _build_export_data(self.vault, 'EXP-synthetic', [q], False, mark_missing_cause=marked)
            self.assertFalse(data['questions'][0]['missing_cause'])
            self.assertNotIn('错因', data['questions'][0]['notes'])
            self.assertEqual(data['answers'][0]['notes']['错因'], '区间端点漏检')
        q['notes'] = '## 错因\n' + render([{'id':'REF-synthetic','revision':1,'occurred_at':None,'content_md':'已撤回错因','withdrawn':True}])
        self.assertTrue(_build_export_data(self.vault, 'EXP-synthetic', [q], False, mark_missing_cause=True)['questions'][0]['missing_cause'])
        self.assertFalse(_build_export_data(self.vault, 'EXP-synthetic', [q], False)['questions'][0]['missing_cause'])
        with self.assertRaises(ValueError):
            _build_export_data(self.vault, 'EXP-synthetic', [q], False, mark_missing_cause='true')

    def test_mcp_real_sdk_creation_requires_new_scope_and_does_not_change_default(self):
        from mcp.server.auth.provider import AccessToken
        from omrs.mcp.keys import create_key, revoke_key
        from omrs.mcp.server import build_server
        server = build_server(self.vault)
        key = create_key(self.vault, scopes=['reminder:create'])
        token = AccessToken(token=key['secret'], client_id=key['key_id'], scopes=key['scopes'])
        async def call():
            with patch('omrs.mcp.server.get_access_token', return_value=token):
                result = await server.call_tool('create_schedule_reminder', {'name':'外部AI提醒','svg':SVG,'request_id':'sdk'})
            return result[1] if isinstance(result,tuple) else json.loads(next(x.text for x in result if getattr(x,'text',None)))
        created = asyncio.run(call())
        self.assertIn('item', created)
        self.assertNotIn('src', created['item'])
        self.assertEqual(len(reminders.catalog(self.vault)['items']), 1)
        self.assertFalse(banner.settings(self.vault)['enabled'])
        revoke_key(self.vault, key['key_id'])
        with self.assertRaises(Exception):
            asyncio.run(call())
        self.assertEqual(len(reminders.catalog(self.vault)['items']), 1)
