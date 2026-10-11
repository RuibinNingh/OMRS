"""原App正文格式、附图映射及真实Chromium兼容；不连接账号或外网。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from omrs.zuoyebang.html import candidate_html, sanitize, picture_url, valid_remote, fetch_image
from omrs.zuoyebang.render import render_documents
from omrs.zuoyebang.store import ZybError
from tests.zuoyebang_fixtures import png


class BodyCompatibility(unittest.TestCase):
    def test_pid_families_and_inline_dedup_keep_original_bytes(self):
        expected = {
            'plain': 'https://img.zuoyebang.cc/tk_plain.jpg',
            'zyb_a': 'https://img.zuoyebang.cc/zyb_a.jpg',
            'qa10_a': 'https://img10.zuoyebang.cc/qa10_a.jpg',
            'qa_a': 'https://testimg.zuoyebang.cc/qa_a.jpg',
            'qa12_a': 'https://testimg.zuoyebang.cc/qa12_a.jpg',
            'zyb12_a': 'https://img12.zuoyebang.cc/zyb12_a.jpg',
        }
        calls = []
        raw = png()
        def download(url):
            calls.append(url)
            return raw
        for pid, url in expected.items():
            with self.subTest(pid=pid):
                self.assertEqual(picture_url(pid), url)
                self.assertEqual(valid_remote(url).hostname, url.split('/')[2])
        candidate = {'question': {'content': '<p>题目<img src="' + expected['zyb_a'] + '"></p>',
                                 'picList': [{'pid': 'zyb_a'}, {'pid': 'qa10_a'}]},
                     'answer': [{'content': '对应答案', 'picList': [{'pid': 'zyb_a'}]}]}
        body, count = candidate_html(candidate, download)
        self.assertEqual(calls, [expected['zyb_a'], expected['qa10_a']])
        self.assertEqual(count, 2)
        self.assertEqual(body['question'].count('<img'), 2)
        self.assertEqual(body['answer'].count('<img'), 1)
        import base64
        self.assertIn(base64.b64encode(raw).decode(), body['question'])

    def test_new_domain_still_rejects_spoofed_hosts_redirects_and_private_ips(self):
        for value in ('https://img.zuoyebang.cc.evil.example/a.jpg', 'https://u:p@img.zuoyebang.cc/a',
                      'https://img.zuoyebang.cc:444/a', 'https://evil.example/a.jpg', '../private', 'file:///etc/passwd'):
            with self.subTest(value=value), self.assertRaises(ZybError):
                valid_remote(picture_url(value))
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 443))]):
            with self.assertRaises(ZybError): fetch_image('https://img.zuoyebang.cc/a.jpg')
        connection = Mock()
        connection.getresponse.return_value.status = 302
        connection.getresponse.return_value.getheader.return_value = 'https://evil.example/a.jpg'
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('8.8.8.8', 80))]), \
                patch('http.client.HTTPConnection', return_value=connection):
            with self.assertRaises(ZybError): fetch_image('http://img.zuoyebang.cc/a.jpg')
        self.assertEqual(connection.request.call_count, 1)
        self.assertNotIn('Cookie', connection.request.call_args.kwargs['headers'])

    def test_styles_preserve_semantics_without_executable_attributes(self):
        body = sanitize('<script>evil()</script><span class="tkspec-script-sub evil" onclick="evil()" style="background:url(https://evil.example);display:none">2</span>'
                        '<span class="tkspec-fill-blank-underline">  </span>'
                        '<span class="pR" style="width:2em;height:1em;top:-.5em;position:fixed;opacity:0">x</span>'
                        '<table class="tB"><tr><td colspan="2" class="tkspec-align-center">内容</td></tr></table>')
        for forbidden in ('evil', 'onclick', 'background', 'display:none', 'position', 'opacity'):
            self.assertNotIn(forbidden, body)
        self.assertIn('tkspec-script-sub', body)
        self.assertIn('tkspec-fill-blank-underline', body)
        self.assertIn('style="width:2em;height:1em', body)
        self.assertIn('colspan="2"', body)

    def test_native_fixture_formulas_and_blank_classes_render(self):
        candidates = json.loads((Path(__file__).parent / 'fixtures/zuoyebang-body.json').read_text())
        with tempfile.TemporaryDirectory() as work:
            for index, candidate in enumerate(candidates):
                directory = Path(work) / str(index); directory.mkdir()
                bodies, _ = candidate_html(candidate)
                result = render_documents(bodies, directory)
                self.assertEqual(result['engine'], 'MathJax 3.2.2')
                self.assertGreaterEqual(result['question']['formulas'], 4)
                self.assertEqual(result['question']['width'], 1080)
                self.assertIn(('B', 'C', 'B')[index], result['answer']['html'])
                if index == 2: self.assertIn('tkspec-fill-blank-brackets', result['question']['html'])

    def test_delimiters_bare_commands_and_chemistry(self):
        content = r'<p><span>$x+y$</span> \(\frac{1}{2}\) $$z^2$$ \[\sqrt{4}\] $\ce{H2O}$</p>'
        with tempfile.TemporaryDirectory() as work:
            result = render_documents({'question': sanitize(content)}, work)
            self.assertEqual(result['question']['formulas'], 5)
            result = render_documents({'question': sanitize(r'计算 \frac{1}{2}')}, work)
            self.assertEqual(result['question']['formulas'], 1)

    def test_sanitized_legacy_formula_keeps_same_pixels_as_trusted_source(self):
        content = '<p>H<span class="tkspec-script-sub">2</span>O，x<span class="tkspec-script-super">2</span>，<span class="tkspec-fill-blank-underline">    </span></p>'
        content += '<p><span class="math"><nobr><span class="pR" style="width:2em"><span class="fI">x</span><span class="fM">＋1</span></span></nobr></span></p>'
        content += '<p><span class="math"><nobr><span class="pR" style="display:inline-block;width:2em;height:2em;vertical-align:-.5em"><span class="pA fM" style="top:0;left:.5em">1</span><span class="pA fM" style="top:1em;left:0;width:2em;border-top:1px solid #000">x＋1</span></span></nobr></span></p>'
        content += '<table class="tB"><tr><td colspan="2">表头</td></tr><tr><td>甲</td><td>乙</td></tr></table>'
        with tempfile.TemporaryDirectory() as work:
            result = render_documents({'question': content, 'answer': sanitize(content)}, work)
            self.assertEqual(result['question']['sha256'], result['answer']['sha256'])

    def test_invalid_tex_cannot_succeed_or_load_arbitrary_scripts(self):
        with tempfile.TemporaryDirectory() as work:
            for body in (r'$\notAnAvailableCommand{x}$', r'$\require{https://evil.example/code}$', r'$\href{javascript:evil()}{x}$'):
                with self.subTest(body=body), self.assertRaises(ZybError):
                    render_documents({'question': sanitize(body)}, work)


if __name__ == '__main__': unittest.main()
