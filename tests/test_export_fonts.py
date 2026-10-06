"""固定打印字体的字符覆盖、离线资源及缓存更新。"""
import base64
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from omrs import export_fonts


class PrintFontTests(unittest.TestCase):
    def test_both_families_cover_export_text_with_local_woff2(self):
        css = export_fonts.inline_print_fonts({"question": "龘中文Aa7"})
        faces = export_fonts._FACE_RE.findall(css)
        for family in ("OMRS Print Serif", "OMRS Print Sans"):
            ranges = []
            for face in faces:
                if family in face:
                    ranges.extend(export_fonts._ranges(re.search(r"unicode-range:\s*([^;]+)", face)[1]))
            for char in "龘中文Aa7":
                self.assertTrue(any(lo <= ord(char) <= hi for lo, hi in ranges), (family, char))
        for uri in re.findall(r"url\(([^)]+)\)", css):
            self.assertTrue(uri.startswith("data:font/woff2;base64,"))
            self.assertTrue(base64.b64decode(uri.split(",", 1)[1]).startswith(b"wOF2"))
        self.assertIn("SIL OPEN FONT LICENSE", css)
        self.assertNotIn("local(", css)
        self.assertNotIn("JetBrains", css)
        self.assertLess(len(faces), 100)

    def test_image_payload_does_not_select_extra_subsets(self):
        plain = export_fonts.inline_print_fonts({"question": "中文"})
        image = export_fonts.inline_print_fonts({"question": "中文", "img": "data:image/png;base64,龘"})
        self.assertEqual(plain, image)

    def test_changed_font_invalidates_cached_data_uri(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.woff2"
            path.write_bytes(b"wOF2first")
            first = export_fonts._font_uri(str(path), export_fonts._signature(path))
            path.write_bytes(b"wOF2second-version")
            second = export_fonts._font_uri(str(path), export_fonts._signature(path))
            self.assertNotEqual(first, second)

    def test_invalid_font_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(export_fonts, "FONT_ROOT", Path(folder)):
            for sheet, family, _, license_name in export_fonts._FAMILIES:
                (Path(folder) / sheet).write_text(
                    "@font-face{font-family:'" + family + "';src:url('../outside.woff2');unicode-range:U+0-FFFF;}",
                    encoding="utf-8",
                )
                (Path(folder) / license_name).write_text("license", encoding="utf-8")
            with self.assertRaises(ValueError):
                export_fonts.inline_print_fonts({"question": "中文"})


if __name__ == "__main__":
    unittest.main()
