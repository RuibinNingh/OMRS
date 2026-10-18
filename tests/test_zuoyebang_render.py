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

    def test_arbitrary_image_domains_keep_question_answer_and_original_bytes(self):
        question_url = 'https://img.cdnjtzy.com/synthetic-question.jpg'
        answer_url = 'https://new-images.example/synthetic-answer.png'
        raw = png()
        calls = []
        def download(url):
            calls.append(url)
            return raw
        candidate = {'question': {'content': '<img src="' + question_url + '">',
                                 'picList': [{'url': question_url}]},
                     'answer': [{'content': '<img src="//new-images.example/synthetic-answer.png">'}]}
        body, count = candidate_html(candidate, download)
        self.assertEqual(calls, [question_url, answer_url])
        self.assertEqual(count, 2)
        import base64
        for role in ('question', 'answer'):
            self.assertEqual(body[role].count('<img'), 1)
            self.assertIn(base64.b64encode(raw).decode(), body[role])
        self.assertEqual(valid_remote('http://another-cdn.example:80/a').hostname, 'another-cdn.example')

    def test_image_addresses_reject_credentials_nonstandard_ports_and_invalid_urls(self):
        for value in ('https://u:p@images.example/a', 'https://@images.example/a',
                      'https://images.example:444/a', 'https://images.example:bad/a',
                      'https://images.example:65536/a', 'https:///a.jpg', 'https://[invalid]/a',
                      '../private.jpg', 'file:///etc/passwd', 'ftp://images.example/a.jpg'):
            with self.subTest(value=value), self.assertRaises(ZybError):
                valid_remote(value)

    def test_arbitrary_domains_still_reject_nonpublic_multicast_and_mixed_dns(self):
        for ips in ([], ['127.0.0.1'], ['10.0.0.1'], ['169.254.169.254'], ['::1'], ['fd00::1'],
                    ['fe80::1'], ['224.0.0.1'], ['ff02::1'], ['8.8.8.8', '192.168.1.1']):
            addresses = [(None, None, None, None, (ip, 80)) for ip in ips]
            with self.subTest(ips=ips), patch('socket.getaddrinfo', return_value=addresses), \
                    patch('http.client.HTTPConnection') as connect:
                with self.assertRaises(ZybError) as caught:
                    fetch_image('http://new-images.example/a.jpg')
                self.assertEqual(caught.exception.code, 'image_address')
                connect.assert_not_called()

    def test_public_cross_domain_redirects_pin_each_connection_and_send_no_credentials(self):
        original, redirected = Mock(), Mock()
        original.getresponse.return_value.status = 302
        original.getresponse.return_value.getheader.return_value = 'http://another-cdn.example/a.jpg'
        redirected.getresponse.return_value.status = 200
        redirected.getresponse.return_value.read.return_value = png()
        addresses = [[(None, None, None, None, ('8.8.8.8', 80))],
                     [(None, None, None, None, ('1.1.1.1', 80))]]
        with patch('socket.getaddrinfo', side_effect=addresses) as lookup, \
                patch('http.client.HTTPConnection', side_effect=[original, redirected]) as connect:
            self.assertEqual(fetch_image('http://img.cdnjtzy.com/a.jpg'), png())
        self.assertEqual([call.args[:2] for call in lookup.call_args_list],
                         [('img.cdnjtzy.com', 80), ('another-cdn.example', 80)])
        self.assertEqual([call.args for call in connect.call_args_list], [('8.8.8.8', 80), ('1.1.1.1', 80)])
        for connection, host in ((original, 'img.cdnjtzy.com'), (redirected, 'another-cdn.example')):
            headers = connection.request.call_args.kwargs['headers']
            self.assertEqual(headers['Host'], host)
            self.assertNotIn('Cookie', headers)
            self.assertNotIn('Authorization', headers)
            connection.close.assert_called_once()

    def test_public_image_redirect_cannot_reach_private_targets_or_other_protocols(self):
        for target in ('http://127.0.0.1/a.jpg', 'http://private-images.example/a.jpg', 'file:///etc/passwd'):
            connection = Mock()
            connection.getresponse.return_value.status = 302
            connection.getresponse.return_value.getheader.return_value = target
            addresses = [[(None, None, None, None, ('8.8.8.8', 80))],
                         [(None, None, None, None, ('127.0.0.1', 80))]]
            with self.subTest(target=target), patch('socket.getaddrinfo', side_effect=addresses), \
                    patch('http.client.HTTPConnection', return_value=connection) as connect:
                with self.assertRaises(ZybError) as caught:
                    fetch_image('http://new-images.example/a.jpg')
                self.assertEqual(caught.exception.code, 'image_address')
            self.assertEqual(connect.call_count, 1)
            self.assertEqual(connection.request.call_count, 1)
            connection.close.assert_called_once()

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

    def test_mobile_text_stays_readable_and_budget_counts_threefold_height(self):
        from PIL import Image
        content = '<p>手机排版正文</p>'
        with tempfile.TemporaryDirectory() as work:
            result = render_documents({'question': content}, work)
            with Image.open(Path(work) / 'question.png') as image:
                ink = image.convert('L').point(lambda value: 255 if value < 128 else 0).getbbox()
                self.assertEqual(image.size, (1080, result['question']['height']))
                # 15 CSS px以3倍输出，中文笔画仍须保留足够的物理像素。
                self.assertGreater(ink[3] - ink[1], 36)
            self.assertEqual(result['layout']['css_width'], 360)
            self.assertEqual(result['layout']['device_scale_factor'], 3)
            self.assertEqual(result['question']['height'] % 3, 0)
            pixels = 1080 * result['question']['height']
            with patch('omrs.zuoyebang.render.PIXEL_BUDGET', pixels // 2), self.assertRaises(ZybError) as caught:
                render_documents({'question': content}, work)
            self.assertEqual(caught.exception.code, 'render_resource')

    def test_long_equations_legacy_formula_and_wide_table_fit_locally(self):
        content = r'<p>长公式前的正文。</p><p>$$a_1+a_2+a_3+a_4+a_5+a_6+a_7+a_8+a_9+a_{10}=100$$</p>'
        content += '<p><span class="math"><nobr><span class="pR" style="display:inline-block;width:900px">' + 'x＋1＋' * 25 + '</span></nobr></span></p>'
        content += r'<table style="width:900px"><tr><td colspan="2">表格标题</td></tr><tr><td>甲</td><td>$x^2+y^2=z^2$</td></tr></table><p>表格后的完整正文。</p>'
        with tempfile.TemporaryDirectory() as work:
            result = render_documents({'question': sanitize(content)}, work)['question']
            self.assertEqual(result['width'], 1080)
            self.assertEqual(result['formulas'], 2)
            self.assertEqual(result['fitted_formulas'], 2)
            self.assertEqual(result['fitted_tables'], 1)
            self.assertIn('表格后的完整正文', result['html'])

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
