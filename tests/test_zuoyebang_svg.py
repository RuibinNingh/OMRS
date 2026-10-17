"""静态 SVG 附图兼容与安全边界；不连接外网。"""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from omrs.zuoyebang.html import candidate_html, image_url, sanitize
from omrs.zuoyebang.render import render_documents
from omrs.zuoyebang.store import ZybError
from tests.zuoyebang_fixtures import svg


def document(body='', dimensions='width="60" height="14"', attributes=''):
    return ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            + dimensions + ' ' + attributes + '>' + body + '</svg>').encode()


class StaticSVG(unittest.TestCase):
    def localize(self, raw):
        return image_url('https://images.example/formula.jpg', lambda _url: raw)

    def reject(self, raw, code='image_invalid'):
        with self.assertRaises(ZybError) as caught:
            self.localize(raw)
        self.assertEqual(caught.exception.code, code)
        self.assertIn('保留', str(caught.exception))

    def test_remote_and_inline_svg_preserve_original_bytes(self):
        raw = b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>' + svg()
        expected = 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode()
        self.assertEqual(self.localize(raw), (expected, len(raw)))
        self.assertEqual(image_url(expected), (expected, len(raw)))

    def test_candidate_caches_same_svg_across_question_answer_and_piclist(self):
        url = 'https://images.example/formula.svg'
        candidate = {'question': {'content': '<img src="' + url + '">', 'picList': [{'url': url}]},
                     'answer': [{'content': '<img src="' + url + '">'}]}
        calls = []
        def fetch(address):
            calls.append(address)
            return svg()
        bodies, count = candidate_html(candidate, fetch)
        self.assertEqual(calls, [url])
        self.assertEqual(count, 1)
        for body in bodies.values():
            self.assertEqual(body.count('<img'), 1)
            self.assertIn(base64.b64encode(svg()).decode(), body)

    def test_dimensions_allow_viewbox_and_absolute_units(self):
        for dimensions in ('viewBox="-2 0 60 14"', 'width="45pt" height="14px"',
                           'width="1in" height="1cm"', 'width="1e2" height="14" viewBox="0,0,60,14"'):
            with self.subTest(dimensions=dimensions):
                self.localize(document('<path d="M0 0L1 1"/>', dimensions))

    def test_invalid_missing_and_oversized_dimensions_fail(self):
        for dimensions in ('', 'width="60"', 'width="0" height="14"', 'width="-1" height="14"',
                           'width="100%" height="14"', 'width="NaN" height="14"',
                           'width="1e999" height="14"', 'width="10000" height="10000"',
                           'viewBox="0 0 60 0"', 'viewBox="0 0 60 NaN"', 'viewBox="0 0 60"',
                           'width="60" height="14" viewBox="0 0 -1 1"'):
            with self.subTest(dimensions=dimensions):
                self.reject(document(dimensions=dimensions))

    def test_scripts_events_animation_foreign_content_and_unknown_namespaces_fail(self):
        for body in ('<script>alert(1)</script>', '<foreignObject><p>正文</p></foreignObject>',
                     '<image href="https://images.example/another.svg"/>', '<animate/>',
                     '<animateTransform/>', '<set/>', '<style>@import "https://images.example/a.css";</style>',
                     '<a href="https://images.example/">文字</a>', '<path xmlns="urn:other"/>', '<filter/>'):
            with self.subTest(body=body):
                self.reject(document(body))
        for attributes in ('onload="alert(1)"', 'xml:base="https://images.example/"',
                           'xmlns:other="urn:other" other:href="#glyph"'):
            with self.subTest(attributes=attributes):
                self.reject(document(attributes=attributes))

    def test_external_and_obfuscated_references_fail(self):
        for address in ('https://images.example/a.svg#x', '//images.example/a.svg#x',
                        'file:///etc/passwd', 'data:image/svg+xml;base64,AAAA', 'javascript:alert(1)',
                        '&#104;ttps://images.example/a.svg', '#missing'):
            with self.subTest(address=address):
                self.reject(document('<use xlink:href="' + address + '"/>'))
        for value in ('url(https://images.example/a.svg#x)', 'url(file:///etc/passwd)',
                      r'u\72l(https://images.example/a)', 'u/**/rl(https://images.example/a)',
                      'url(&quot;https://images.example/a&quot;)'):
            with self.subTest(value=value):
                self.reject(document('<path fill="' + value + '"/>'))

    def test_static_styles_gradients_and_local_references_are_preserved(self):
        raw = document('<defs><linearGradient id="ink"><stop offset="0" stop-color="black"/>'
                       '<stop offset="1" style="stop-color:white"/></linearGradient></defs>'
                       '<rect width="30" height="10" style="fill:url(#ink);stroke:none"/>')
        self.assertEqual(base64.b64decode(self.localize(raw)[0].split(',')[1]), raw)
        for style in ('fill:url(https://images.example/a)', 'fill:red;filter:url(#ink)',
                      'fill:red;@import:url(https://images.example/a)', r'f\69ll:red'):
            with self.subTest(style=style):
                self.reject(document('<path style="' + style + '"/>'))

    def test_doctype_entities_and_processing_instructions_fail_including_utf16(self):
        sources = ['<!DOCTYPE svg [<!ENTITY word "replacement">]>' + document('<text>&word;</text>').decode(),
                   '<!DOCTYPE svg SYSTEM "file:///etc/passwd">' + document().decode(),
                   '<?xml-stylesheet href="https://images.example/a.css"?>' + document().decode()]
        for source in sources:
            for encoding in ('utf-8', 'utf-16'):
                with self.subTest(encoding=encoding, source=source):
                    self.reject(source.encode(encoding))

    def test_duplicate_ids_and_recursive_references_fail(self):
        for body in ('<path id="a"/><path id="a"/>', '<g id="a"><use href="#a"/></g>',
                     '<defs><g id="a"><use href="#b"/></g><g id="b"><use href="#a"/></g></defs><use href="#a"/>',
                     '<defs><linearGradient id="a" href="#b"/><linearGradient id="b" href="#a"/></defs>'):
            with self.subTest(body=body):
                self.reject(document(body))

    def test_structure_and_reference_expansion_have_separate_budgets(self):
        with patch('omrs.zuoyebang.svg.MAX_NODES', 4):
            self.reject(document('<path/>' * 4), 'render_resource')
        with patch('omrs.zuoyebang.svg.MAX_DEPTH', 4):
            self.reject(document('<g>' * 4 + '</g>' * 4), 'render_resource')
        body = '<defs><path id="a0" d="M0 0L1 1"/>'
        for index in range(1, 17):
            body += f'<g id="a{index}">' + f'<use href="#a{index - 1}"/>' * 2 + '</g>'
        body += '</defs><use href="#a16"/>'
        self.reject(document(body), 'render_resource')

    def test_malformed_xml_and_non_image_responses_fail(self):
        for raw in (b'not an image', b'<html>download failed</html>', b'<svg', b'\x00\xff',
                    document('<path>'), b'<svg xmlns="urn:other" width="60" height="14"/>'):
            with self.subTest(raw=raw):
                self.reject(raw)
        with patch('omrs.zuoyebang.html.IMAGE_BYTES', len(svg()) - 1):
            self.reject(svg(), 'render_resource')

    def test_inline_svg_html_still_requires_an_image_context(self):
        with self.assertRaises(ZybError) as caught:
            sanitize(svg().decode())
        self.assertEqual(caught.exception.code, 'render_unsupported')

    def test_real_chromium_paints_svg_in_question_and_answer(self):
        from PIL import Image
        url = 'https://images.example/formula.svg'
        candidate = {'question': {'content': '<p>公式附图：<img src="' + url + '"></p>'},
                     'answer': [{'content': '<p>对应答案：<img src="' + url + '"></p>'}]}
        bodies, count = candidate_html(candidate, lambda _url: svg())
        with tempfile.TemporaryDirectory() as directory:
            result = render_documents(bodies, directory)
            self.assertEqual(count, 1)
            for role in ('question', 'answer'):
                self.assertEqual(result[role]['width'], 1080)
                self.assertEqual(result[role]['images'], 1)
                self.assertNotIn('base64,', result[role]['html'])
                with Image.open(Path(directory) / (role + '.png')) as image:
                    red = sum(1 for r, g, b in image.convert('RGB').getdata() if r > 120 and g < 80 and b < 80)
                self.assertGreater(red, 100)


if __name__ == '__main__':
    unittest.main()
