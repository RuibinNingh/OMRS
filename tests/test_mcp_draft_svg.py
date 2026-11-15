"""MCP新题配图：原始字节、独立草稿块、审核入库及真实SDK边界。"""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from omrs import drafts, creation
from omrs.draft_svg import bytes_of
from omrs.ledger import read_commits
from tests.test_mcp_draft_atomic import FaultConnection
from tests.test_mcp_protocol import MCPServerProcess, MCP_AVAILABLE, _session, _json_result, _png
from tests.test_question_svg import diagram


def data(raw=None):
    return {'subject': '物理', 'category': '配图草稿', 'blocks': [
        {'section': '题目', 'kind': 'text', 'text': '分析下面的受力图。'},
        {'section': '题目', 'kind': 'svg', 'svg_data': raw if raw is not None else diagram()},
        {'section': '题目', 'kind': 'text', 'text': '求合力。'},
        {'section': '答案', 'kind': 'svg', 'svg': diagram('答案图').decode()},
    ]}


def origin(request='svg-1'):
    return {'conversation_id': 'mcp:svg:' + request, 'source_key_id': 'svg-key', 'source_request_id': request}


def update_blocks(draft):
    return [{k: b.get(k) for k in ('id', 'section', 'kind', 'text', 'note', 'image_sha', 'box', 'box_origin', 'ai_box')}
            for b in draft['blocks']]


class DraftSvgTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='omrs-draft-svg-')
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name

    def test_preserves_bytes_order_and_single_commit_without_source_or_training(self):
        raw = diagram('原始字节') + b'\n'
        draft = drafts.create_mcp_draft(self.vault, data(raw), origin())
        self.assertEqual(draft['status'], 'review')
        self.assertEqual(draft['source_images'], [])
        self.assertEqual(draft['training_tasks'], [])
        self.assertEqual(bytes_of(draft['blocks'][1]), raw)
        self.assertFalse((Path(self.vault)/'错题'/'附件').exists())
        self.assertFalse(any(c['commit_type'] == 'question.create' for c in read_commits(self.vault)))
        result = drafts.commit_draft(self.vault, draft['id'], draft['revision'])
        content = (Path(self.vault)/result['result']['file_path']).read_text()
        name = result['result']['question_id'] + '-svg-' + hashlib.sha256(raw).hexdigest() + '.svg'
        self.assertLess(content.index('分析下面'), content.index(name))
        self.assertLess(content.index(name), content.index('求合力'))
        self.assertEqual((Path(self.vault)/'错题'/'附件'/name).read_bytes(), raw)
        self.assertTrue(drafts.commit_draft(self.vault, draft['id'], 1)['reused'])
        self.assertEqual(sum(c['commit_type'] == 'question.create' for c in read_commits(self.vault)), 1)

    def test_manual_save_move_delete_and_source_readonly(self):
        draft = drafts.create_mcp_draft(self.vault, data(), origin())
        blocks = update_blocks(draft)
        svg = blocks.pop(1)
        svg.update(section='答案', note='人工核对过的说明')
        blocks.append(svg)
        saved = drafts.update_draft(self.vault, draft['id'], 1, {'subject': '物理'}, blocks)
        self.assertEqual(saved['blocks'][-1]['note'], svg['note'])
        self.assertEqual(bytes_of(saved['blocks'][-1]), diagram())
        for change in ({'kind': 'text', 'text': '改写'}, {'box': {'x': 0, 'y': 0, 'w': 1, 'h': 1}},
                       {'svg': '<svg/>'}, {'id': None}):
            mutated = update_blocks(saved)
            mutated[-1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                drafts.update_draft(self.vault, draft['id'], saved['revision'], {}, mutated)
        saved = drafts.update_draft(self.vault, draft['id'], saved['revision'], {}, update_blocks(saved)[:-1])
        self.assertEqual(sum(b['kind'] == 'svg' for b in saved['blocks']), 1)

    def test_svg_cannot_crop_extract_or_train(self):
        draft = drafts.create_mcp_draft(self.vault, data(), origin())
        key = draft['blocks'][1]['id']
        with self.assertRaises(ValueError):
            drafts.set_boxes(self.vault, draft['id'], 1, [{'id': key, 'box': {'x': 0, 'y': 0, 'w': 1, 'h': 1}}])
        with self.assertRaises(ValueError):
            drafts.start_extract(self.vault, draft['id'], 1, [key])
        with self.assertRaises(ValueError):
            drafts.commit_draft(self.vault, draft['id'], 1, {key: 'data:image/png;base64,eA=='})
        self.assertEqual(drafts.get_draft(self.vault, draft['id'])['training_tasks'], [])

    def test_atomic_failure_preserves_shared_original_and_no_svg_relations(self):
        raw = _png()
        shared = drafts.create_mcp_draft(self.vault, {'subject': '数学', 'category': '来源', 'blocks': [
            {'section': '题目', 'kind': 'image', 'image': 0}]}, origin('shared'), [raw])
        real = drafts.connect
        for fault in ('INSERT INTO blocks', 'commit'):
            def faulty(vault):
                return FaultConnection(real(vault), sql=None if fault == 'commit' else fault, commit=fault == 'commit')
            with self.subTest(fault=fault), mock.patch.object(drafts, 'connect', side_effect=faulty):
                with self.assertRaises(Exception):
                    drafts.create_mcp_draft(self.vault, data(), origin(fault), [raw])
            with real(self.vault) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM blocks WHERE kind='svg'").fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM mcp_requests').fetchone()[0], 1)
            self.assertTrue(Path(drafts.image_path(self.vault, shared['source_images'][0]['sha256'])).exists())

    def test_same_request_reuses_concurrently_and_changed_svg_conflicts(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: drafts.create_mcp_draft(self.vault, data(), origin()), range(3)))
        self.assertEqual(len({r['id'] for r in results}), 1)
        with self.assertRaises(drafts.DraftError):
            drafts.create_mcp_draft(self.vault, data(diagram('改图')), origin())

    def test_legacy_blocks_migrate_and_corruption_stops_commit(self):
        old = drafts.create_mcp_draft(self.vault, {'subject': '数学', 'category': '旧草稿', 'blocks': [
            {'section': '题目', 'kind': 'text', 'text': '保持旧数据'}]}, origin('old'))
        with drafts.connect(self.vault) as db:
            db.execute('ALTER TABLE blocks DROP COLUMN svg_data')
            db.execute('ALTER TABLE blocks DROP COLUMN svg_hash')
        self.assertEqual(drafts.get_draft(self.vault, old['id'])['blocks'][0]['text'], '保持旧数据')
        draft = drafts.create_mcp_draft(self.vault, data(), origin())
        with drafts.connect(self.vault) as db:
            db.execute('UPDATE blocks SET svg_data=? WHERE id=?', (diagram('篡改'), draft['blocks'][1]['id']))
        with self.assertRaisesRegex(ValueError, '校验失败'):
            drafts.commit_draft(self.vault, draft['id'], 1)
        self.assertFalse((Path(self.vault)/'错题'/'附件').exists())

    def test_interrupted_commit_can_edit_and_retry_without_stale_svg(self):
        draft = drafts.create_mcp_draft(self.vault, data(), origin())
        with mock.patch.object(creation, 'append_commit', side_effect=RuntimeError('测试Ledger中断')):
            with self.assertRaises(RuntimeError):
                drafts.commit_draft(self.vault, draft['id'], 1)
        self.assertTrue(list((Path(self.vault)/'错题'/'附件').glob('*.svg')))
        saved = drafts.update_draft(self.vault, draft['id'], 1, {'note': '重试前修改'}, update_blocks(draft))
        self.assertFalse(list((Path(self.vault)/'错题'/'附件').glob('*.svg')))
        result = drafts.commit_draft(self.vault, draft['id'], saved['revision'])
        self.assertEqual(result['draft']['status'], 'done')


@unittest.skipUnless(MCP_AVAILABLE, '真实SDK需要可选MCP依赖')
class DraftSvgProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServerProcess()
        try:
            cls.server.start()
        except BaseException:
            cls.server.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_source_file_bitmap_sdk_image_and_approved_question(self):
        async def run():
            attachments = []
            for name, raw, mime in [('diagram.svg', diagram('文件图'), 'image/svg+xml'), ('original.png', _png(), 'image/png')]:
                attachments.append({'download_url': 'https://files.example.org/' + name, 'file_id': name,
                                    'file_name': name, 'mime_type': mime, 'data_base64': base64.b64encode(raw).decode()})
            payload = {'subject': '物理', 'category': '混排SVG', 'request_id': 'sdk-svg-mixed', 'images': attachments,
                       'blocks': [{'section': '题目', 'kind': 'text', 'text': '题干'},
                                  {'section': '题目', 'kind': 'image', 'image': 1},
                                  {'section': '题目', 'kind': 'image', 'image': 0},
                                  {'section': '答案', 'kind': 'svg', 'svg': diagram('源码图').decode()}]}
            async with _session(self.server.mcp_port, self.server.keys['all']['secret']) as session:
                created = _json_result(await session.call_tool('create_draft', payload))
                self.assertIn('draft_id', created, created)
                self.assertEqual([b['kind'] for b in created['blocks']], ['text', 'image', 'svg', 'svg'])
                self.assertEqual(len(created['source_images']), 1)
                self.assertNotIn('src', created['blocks'][2]['svg'])
                self.assertNotIn('svg_data', json.dumps(created))
                self.assertTrue(_json_result(await session.call_tool('create_draft', payload))['reused'])
                result = await session.call_tool('get_draft_image', {'draft_id': created['draft_id'], 'block_id': created['blocks'][2]['id']})
                self.assertFalse(result.isError, str(result))
                self.assertEqual(len(result.content), 1)
                self.assertEqual(result.content[0].mimeType, 'image/png')
                self.assertTrue(base64.b64decode(result.content[0].data).startswith(b'\x89PNG'))
                original = await session.call_tool('get_draft_image', {'draft_id': created['draft_id'], 'image_index': 0})
                self.assertEqual(base64.b64decode(original.content[0].data), _png())
                for args in ({}, {'block_id': created['blocks'][0]['id']}, {'block_id': 'other'},
                             {'block_id': created['blocks'][2]['id'], 'image_index': 0}, {'image_index': True}):
                    with self.subTest(args=args):
                        self.assertTrue((await session.call_tool('get_draft_image', {'draft_id': created['draft_id'], **args})).isError)
                result = drafts.commit_draft(self.server.vault, created['draft_id'], 1)
                image = await session.call_tool('get_question_image', {'uid': result['result']['uid'], 'image_index': 1})
                self.assertFalse(image.isError, str(image))
                self.assertEqual(image.content[0].mimeType, 'image/png')
        asyncio.run(run())

    def test_invalid_sources_files_and_conflicts_do_not_create_partial_drafts(self):
        async def run():
            async with _session(self.server.mcp_port, self.server.keys['all']['secret']) as session:
                base = {'subject': '物理', 'category': 'SVG边界'}
                bad = [diagram(size=4).decode(), diagram(extra='<script/>').decode(), '<svg/>',
                       diagram(extra='<image href="https://example.org/x"/>').decode(), 'x' * (256 * 1024 + 1)]
                cases = [{'blocks': [{'section': '题目', 'kind': 'svg', 'svg': source}]} for source in bad]
                cases += [{'blocks': [{'section': '题目', 'kind': 'svg', 'svg': diagram().decode()}] * 4},
                          {'blocks': [{'section': '题目', 'kind': 'svg', 'svg': diagram().decode(), 'text': '混用'}]},
                          {'blocks': [{'section': '题目', 'kind': 'text', 'text': '未引用文件'}],
                           'images': [{'file_id': 'svg', 'download_url': 'https://files.example.org/x.svg',
                                       'data_base64': base64.b64encode(diagram()).decode()}]}]
                before = len(drafts.list_drafts(self.server.vault))
                for n, case in enumerate(cases):
                    with self.subTest(n=n):
                        self.assertTrue((await session.call_tool('create_draft', {**base, 'request_id': f'svg-bad-{n}', **case})).isError)
                self.assertEqual(len(drafts.list_drafts(self.server.vault)), before)
                request = {**base, 'request_id': 'svg-conflict', 'blocks': [
                    {'section': '题目', 'kind': 'svg', 'svg': diagram().decode()}]}
                first = _json_result(await session.call_tool('create_draft', request))
                self.assertIn('draft_id', first)
                request['blocks'][0]['svg'] = diagram('改图').decode()
                self.assertTrue((await session.call_tool('create_draft', request)).isError)
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
