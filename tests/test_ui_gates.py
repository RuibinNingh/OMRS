"""tests/check_ui.py 与 tests/check_contrast.py 的回归：规则能抓到违规，仓库本身通过。"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_contrast  # noqa: E402
import check_ui  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class CheckUiRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(self.root, "AGENTS.md", "| 改动范围 | 文档 |\n| `assets/app/features/instant/` | `AI/frontend/review.md` |\n")
        write(self.root, "assets/core.js", "el.innerHTML='<b onclick=\"x()\" style=\"color:#fff\">'\n")
        write(self.root, "assets/styles.css", ".a{color:#123456;font-size:12px}\n#abc{margin:0}\n")
        write(self.root, "omrs_dashboard.html", "<div></div>\n")

    def tearDown(self):
        self.tmp.cleanup()

    def problems(self):
        return check_ui.check_app(self.root)

    def test_legacy_counts(self):
        counts = check_ui.legacy_counts(os.path.join(self.root, "assets", "core.js"))
        self.assertEqual((counts["handlers"], counts["html_assign"], counts["inline_style"], counts["color_literals"]), (1, 1, 1, 1))
        css = check_ui.legacy_counts(os.path.join(self.root, "assets", "styles.css"))
        self.assertEqual((css["color_literals"], css["font_size_literals"]), (1, 1), "选择器里的 #abc 不算颜色")

    def test_legacy_baseline_is_removed(self):
        self.assertEqual(quiet(check_ui.main, [], root=self.root), 1)
        self.assertEqual(quiet(check_ui.main, ["--update-baseline"], root=self.root), 1)
        write(self.root, "assets/core.js", "\n")
        write(self.root, "assets/styles.css", "\n")
        self.assertEqual(quiet(check_ui.main, [], root=self.root), 1, "旧文件即使无违规也禁止保留")
        os.remove(os.path.join(self.root, "assets", "core.js"))
        os.remove(os.path.join(self.root, "assets", "styles.css"))
        self.assertEqual(quiet(check_ui.main, [], root=self.root), 0)

    def test_new_legacy_file_rejected(self):
        write(self.root, "assets/newpage.js", "\n")
        self.assertEqual(quiet(check_ui.main, [], root=self.root), 1)

    def test_css_rules(self):
        write(self.root, "assets/app/ui/button/button.css",
              ".b{color:#fff;font-size:13px;padding:6px var(--sp-2);border-radius:5px;box-shadow:0 1px 2px black;"
              "z-index:999;transition:opacity 120ms ease}\n@media (max-width:900px){.b{gap:var(--sp-1)}}\n")
        text = "\n".join(self.problems())
        for rule in ("R1", "R2", "R3", "R4 圆角", "R4 阴影", "R4 z-index", "R4 动效", "R5"):
            self.assertIn(rule, text)

    def test_css_tokens_pass(self):
        write(self.root, "assets/app/ui/button/button.css",
              ".b{color:var(--fg-1);font-size:var(--text-sm);padding:0 var(--sp-3);margin:calc(-1 * var(--sp-1)) auto;"
              "border-radius:var(--r-sm);box-shadow:0 0 0 2px var(--focus-ring);z-index:var(--z-modal);"
              "transition:opacity var(--dur-1) var(--ease-out)}\n@media (min-width:1161px){.b{gap:var(--sp-2)}}\n")
        write(self.root, "assets/app/styles/tokens.css", ":root{--x:#fff;--y:rgba(0,0,0,.1)}\n")
        self.assertEqual(self.problems(), [])

    def test_script_rules_and_imports(self):
        write(self.root, "assets/app/core/dom.js", "export function morph(el,h){el.innerHTML=h}\n")
        write(self.root, "assets/app/core/bad.js", "import { x } from '../ui/button/button.js';\n")
        write(self.root, "assets/app/features/instant/view.js",
              "import { y } from '../feedback/state.js';\nexport const v = `<b onclick=\"a()\" style=\"x\">`;\n")
        write(self.root, "assets/app/features/instant/ok.js",
              "import { h } from '../../core/html.js';\nimport { s } from './state.js';\n")
        text = "\n".join(self.problems())
        self.assertNotIn("core/dom.js", text)
        self.assertIn("R7 assets/app/core/bad.js", text)
        self.assertIn("R7 assets/app/features/instant/view.js", text)
        self.assertIn("on*=", text)
        self.assertIn("style=", text)
        self.assertNotIn("ok.js", text)

    def test_feature_must_be_registered(self):
        write(self.root, "assets/app/features/feedback/index.js", "\n")
        write(self.root, "assets/app/features/instant/index.js", "\n")
        text = "\n".join(self.problems())
        self.assertIn("R9 assets/app/features/feedback/", text)
        self.assertNotIn("features/instant/ 没有登记", text)

    def test_line_limit(self):
        write(self.root, "assets/app/core/long.js", "\n" * 401)
        self.assertIn("R8", "\n".join(self.problems()))


class ContrastTest(unittest.TestCase):
    CSS = """:root{--surface-0:#ffffff;--surface-1:#ffffff;--surface-2:#eeeeee;--fg-1:#000;--fg-2:#333;--fg-3:#999999;
      --accent:#000;--accent-hover:#222;--accent-soft:rgba(0,0,0,.05);--on-accent:#fff;--danger:#c00;--success:#060;--warning:#850;--info:#00c;
      --danger-fg:#900;--danger-soft:rgba(200,0,0,0.1);--success-fg:#050;--success-soft:rgba(0,100,0,.1);
      --warning-fg:#640;--warning-soft:rgba(130,80,0,.1);--info-fg:#009;--info-soft:rgba(0,0,200,.1);--focus-ring:var(--info);
      --surface-sunken:var(--surface-0)}
      [data-theme="dark"]{--surface-0:#000;--surface-1:#111;--surface-2:#222;--fg-1:#fff;--fg-2:#ccc;--fg-3:#aaa;
      --accent:#eee;--accent-hover:#ddd;--on-accent:#000;--danger:#f99;--success:#9f9;--warning:#fc6;--info:#9cf;--danger-fg:#fbb;
      --success-fg:#bfb;--warning-fg:#fd9;--info-fg:#bdf}"""

    def test_detects_low_contrast_and_resolves_vars(self):
        rows = check_contrast.evaluate(self.CSS)
        bad = {(t, fg, bg) for t, fg, bg, _, _, ok in rows if not ok}
        self.assertIn(("light", "fg-3", "surface-1"), bad)  # #999 on white ≈ 2.8
        self.assertNotIn(("light", "focus-ring", "surface-1"), bad)  # var(--info) 被解析
        self.assertTrue(all(t == "light" for t, _, _ in bad))

    def test_known_ratio(self):
        self.assertAlmostEqual(check_contrast.ratio((0, 0, 0, 1), (255, 255, 255, 1)), 21.0, places=2)


class RepositoryGatesTest(unittest.TestCase):
    def test_repository_passes_ui_gate(self):
        self.assertEqual(quiet(check_ui.main, [], root=ROOT), 0, "运行 python3 tests/check_ui.py 查看问题")

    def test_repository_tokens_meet_contrast(self):
        rows = check_contrast.evaluate(Path(check_contrast.TOKENS).read_text(encoding="utf-8"))
        self.assertEqual([r for r in rows if not r[5]], [])


if __name__ == "__main__":
    unittest.main()
