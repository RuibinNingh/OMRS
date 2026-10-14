"""公式定界符转换、MCP 草稿持久化及导出完整块回归。"""
import json
from pathlib import Path
import tempfile
import unittest

from omrs import drafts, exporting
from omrs.draft_write import patch_mcp_draft
from omrs.math_text import normalize_math_delimiters


CASES = json.loads((Path(__file__).parent / 'fixtures/math_delimiters.json').read_text())


class MathDelimiterTests(unittest.TestCase):
    def test_shared_cases_and_repeated_conversion(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                actual = normalize_math_delimiters(case['source'])
                self.assertEqual(actual, case['expected'])
                self.assertEqual(normalize_math_delimiters(actual), actual)

    def test_mcp_draft_create_patch_retry_and_cause_evidence(self):
        with tempfile.TemporaryDirectory() as vault:
            original = r'我把 \(v_0\) 的方向弄反了'
            data = {'subject': '物理', 'category': '公式兼容', 'cause': original, 'cause_statement': original,
                    'blocks': [{'section': '题目', 'kind': 'text', 'text': r'求 \(t\)'},
                               {'section': '答案', 'kind': 'text', 'text': CASES[0]['source']}]}
            origin = {'source_key_id': 'test-key', 'source_request_id': 'math-create',
                      'conversation_id': 'mcp:math-create'}
            created = drafts.create_mcp_draft(vault, data, origin)
            self.assertEqual(created['blocks'][0]['text'], '求 $t$')
            self.assertEqual(created['blocks'][1]['text'], CASES[0]['expected'])
            self.assertEqual(created['cause'], '我把 $v_0$ 的方向弄反了')
            self.assertEqual(created['cause_statement'], original)
            self.assertEqual(drafts.create_mcp_draft(vault, data, origin)['id'], created['id'])
            block_id = created['blocks'][1]['id']
            patches = [{'block_id': block_id, 'text': r'\[\Delta t=\frac{v_0}{g}\]', 'note': r'检查 \(g\)'}]
            result = patch_mcp_draft(vault, created['id'], created['revision'], {}, patches,
                                     'test-key', 'math-update', '', lambda: None)
            current = drafts.get_draft(vault, created['id'])
            self.assertTrue(result['wrote'])
            self.assertEqual(current['blocks'][1]['text'], r'$$\Delta t=\frac{v_0}{g}$$')
            self.assertEqual(current['blocks'][1]['note'], '检查 $g$')
            retry = patch_mcp_draft(vault, created['id'], created['revision'], {}, patches,
                                    'test-key', 'math-update', '', lambda: None)
            self.assertTrue(retry['reused'])
            self.assertEqual(drafts.get_draft(vault, created['id'])['revision'], current['revision'])

    def test_legacy_export_preserves_multiline_formulas_and_table_cells(self):
        blocks = exporting._text_to_blocks('/unused', '前文\n\\[\n\\frac{v_0}{g}\n\\]\n后文')
        self.assertEqual(blocks, [{'t': 'txt', 'text': '前文'},
                                 {'t': 'txt', 'text': '$$\n\\frac{v_0}{g}\n$$'},
                                 {'t': 'txt', 'text': '后文'}])
        table = exporting._text_to_blocks('/unused', '| 值 |\n| --- |\n| \\(t\\) |')
        self.assertEqual(table[0]['rows'], [['$t$']])
        self.assertEqual(exporting._parse_notes_subsections('## 错因\n\\(v_0\\)'), {'错因': '$v_0$'})


if __name__ == '__main__':
    unittest.main()
