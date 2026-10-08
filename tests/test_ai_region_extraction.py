"""区域提取的公式转义、完整判断与正文兼容回归。"""
import json
import tempfile
import unittest
from unittest import mock

from omrs import ai_assist, inbox
from tests.test_inbox import data_url, make_png


class RegionExtractionTests(unittest.TestCase):
    image = "data:image/png;base64,AA=="

    def extract(self, response, role="question", judge=True):
        with mock.patch.object(ai_assist, "_call_model", return_value=response) as call:
            result = ai_assist.extract_region("/unused", self.image, role=role, judge=judge)
        call.assert_called_once()
        return result

    def test_unescaped_math_delimiters_preserve_formulas_and_newlines(self):
        # 实测模型会混用漏转义的定界符与正确转义的公式命令。
        response = r'{"convertible":true,"reason":"纯公式","text":"11. 已知 \(a+b=1\)。\n\[\\frac{1}{a}+\\sqrt{b}\\geqslant 2\]"}'
        result = self.extract(response)
        self.assertTrue(result["convertible"])
        self.assertEqual(result["text"], "已知 $a+b=1$。\n$$\\frac{1}{a}+\\sqrt{b}\\geqslant 2$$")

    def test_already_escaped_math_delimiters_are_not_double_escaped(self):
        text = r"已知 \(x=\sqrt{2}\)，求 \[\frac{1}{x}\]。"
        result = self.extract(json.dumps({"convertible": True, "text": text}))
        self.assertEqual(result["text"], r"已知 $x=\sqrt{2}$，求 $$\frac{1}{x}$$。")

    def test_dollar_math_quotes_and_json_escapes_round_trip(self):
        text = '已知 $\\frac{1}{a}+\\beta=1$，说明为"原文"。\n下一行\t编号。'
        self.assertEqual(self.extract(json.dumps({"convertible": True, "text": text}))["text"], text)

    def test_repair_preserves_existing_even_backslash_runs(self):
        response = r'{"convertible":true,"text":"已知 \(x=1\)，原文 \\\\( 与 \\\\)。"}'
        self.assertEqual(self.extract(response)["text"], r"已知 $x=1$，原文 \\( 与 \\)。")

    def test_fenced_and_prefixed_replies_support_same_delimiter_repair(self):
        response = r'{"convertible":true,"text":"求 \(x^2\)。"}'
        for wrapped in ("```json\n" + response + "\n```", "识别结果：\n" + response):
            with self.subTest(wrapped=wrapped):
                self.assertEqual(self.extract(wrapped)["text"], "求 $x^2$。")

    def test_answer_steps_are_preserved(self):
        response = r'{"convertible":true,"text":"1. 由 \(x=1\) 得结论。\n2. 代入验证。"}'
        self.assertEqual(self.extract(response, role="answer")["text"], "1. 由 $x=1$ 得结论。\n2. 代入验证。")

    def test_other_invalid_json_is_still_rejected(self):
        responses = (
            r'{"convertible":true,"text":"\(x=1\) 和 \sqrt{2}"}',
            r'{"convertible":true,"text":"\(x=1\) 和 \q"}',
            r'{"convertible":true,"text":"\(x=1\)',
            '{"convertible":true,"text":"第一行\n第二行"}',
            r'{"convertible":true "text":"\(x=1\)"}',
        )
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.extract(response)

    def test_repaired_json_still_requires_boolean_and_nonempty_text(self):
        responses = (
            r'{"convertible":"true","text":"\(x=1\)"}',
            r'{"text":"\(x=1\)"}',
            r'{"convertible":true,"reason":"含 \(x\)","text":""}',
        )
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.extract(response)

    def test_negative_judgment_remains_negative(self):
        result = self.extract(r'{"convertible":false,"reason":"\(x\) 依赖图形","text":""}')
        self.assertFalse(result["convertible"])
        self.assertEqual(result["text"], "")

    def test_other_json_consumers_remain_strict(self):
        self.assertEqual(ai_assist._extract_json(r'{"subject":"\(x\)"}'), {})

    def test_unjudged_extraction_remains_plain_text(self):
        text = r"求 $\sqrt{2}$。"
        self.assertEqual(self.extract(text, judge=False)["text"], text)

    def test_inbox_writes_repaired_response_without_moving_box(self):
        with tempfile.TemporaryDirectory() as vault:
            image = data_url(make_png(32, 32))
            item = inbox.upload_images(vault, [("公式.png", make_png(32, 32))])["items"][0]
            box = {"id": "r_math", "card": 1, "role": "question", "x": .1, "y": .2,
                   "w": .5, "h": .4, "origin": "ai", "convert": "auto", "text_status": "none"}
            inbox.update_item(vault, item["id"], {"regions": [box]})
            response = r'{"convertible":true,"reason":"纯公式","text":"求 \(\\sqrt{2}\)。"}'
            with mock.patch.object(ai_assist, "_call_model", return_value=response) as call:
                inbox._run_extract(vault, ai_assist, {"region_id": "r_math", "crop": image})
            call.assert_called_once()
            current = inbox.get_item(vault, item["id"])
            region = current["regions"][0]
            self.assertEqual([region[k] for k in ("x", "y", "w", "h")], [.1, .2, .5, .4])
            self.assertEqual(region["text"], r"求 $\sqrt{2}$。")
            self.assertEqual(region["text_status"], "done")
            self.assertTrue(region["judge"]["ok"])
            self.assertEqual(current["status"], "boxed")


if __name__ == "__main__":
    unittest.main()
