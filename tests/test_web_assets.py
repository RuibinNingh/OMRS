"""资源内容版本和合并产物的失效、依赖、路径与样式层级回归。"""
import os
import pathlib
import tempfile
import unittest

from omrs.web_assets import AssetStore, accepts_gzip


class WebAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.store = AssetStore(self.root)
        self.write("assets/app/main.js", "import { x } from './child.js';\nexport { y } from './nested/next.js';")
        self.write("assets/app/child.js", "import './main.js';\nexport const x = 1;")
        self.write("assets/app/nested/next.js", "export const y = 1;")

    def write(self, name, content):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def test_content_version_stable_across_stores_and_mtime_changes(self):
        version = self.store.refresh()
        self.assertEqual(version, AssetStore(self.root).refresh())
        path = self.root / "assets/app/child.js"
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
        self.assertEqual(version, self.store.refresh())
        path.write_text(path.read_text().replace("x = 1", "x = 2"))
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertNotEqual(version, self.store.refresh())
        self.assertIsNone(self.store.resolve(f"/assets/_v/{version}/app/child.js"))

    def test_changed_file_not_cached_under_old_version(self):
        self.store.refresh()
        url = self.store.url("assets/app/child.js")
        self.assertTrue(self.store.resolve(url)[2])
        self.write("assets/app/child.js", "export const x = 2;")
        self.assertIsNone(self.store.resolve(url))
        self.assertFalse(self.store.resolve("/assets/app/child.js")[2])

    def test_preload_handles_reexports_cycles_and_relative_urls(self):
        self.store.refresh()
        self.assertEqual(self.store.module_graph("assets/app/main.js"), (
            "assets/app/child.js", "assets/app/nested/next.js"))
        page = b'<head><link href="assets/app/theme.css?v=old"><script type="module" src="assets/app/main.js?v=old"></script></head>'
        text = self.store.document(page).decode()
        self.assertNotIn("?v=old", text)
        self.assertIn(self.store.url("assets/app/main.js"), text)
        self.assertEqual(text.count('rel="modulepreload"'), 2)

    def test_css_layers_order_relative_font_and_dependency_invalidation(self):
        self.write("assets/app/styles/index.css", '@layer vendor, ui;\n@import url("../../vendor/font.css") layer(vendor);\n@import url("ui.css") layer(ui);')
        self.write("assets/vendor/font.css", '@font-face { src:url("fonts/a.woff2"); }')
        self.write("assets/vendor/fonts/a.woff2", "font")
        self.write("assets/app/styles/ui.css", '@import url("button.css");\n.x { background:url(data:image/png;base64,abc); }')
        self.write("assets/app/styles/button.css", ".button { display:flex; }")
        self.store.refresh()
        css = self.store.stylesheet("assets/app/styles/index.css").decode()
        self.assertNotIn("@import", css)
        self.assertIn('@layer vendor {\n@font-face', css)
        self.assertIn('@layer ui {\n.button', css)
        self.assertIn(self.store.url("assets/vendor/fonts/a.woff2"), css)
        self.assertIn("url(data:image/png;base64,abc)", css)
        self.assertLess(css.index("@font-face"), css.index(".button"))
        old_version = self.store.version
        self.write("assets/app/styles/button.css", ".button { display:grid; }")
        self.store.refresh()
        self.assertNotEqual(old_version, self.store.version)
        self.assertIn(b"display:grid", self.store.stylesheet("assets/app/styles/index.css"))

    def test_traversal_and_symlinks_are_not_served(self):
        outside = self.write("secret.txt", "secret")
        (self.root / "assets/leak.txt").symlink_to(outside)
        self.store.refresh()
        for path in ("/assets/../secret.txt", "/assets/%2e%2e/secret.txt", "/assets/leak.txt", self.store.url("assets/leak.txt")):
            self.assertIsNone(self.store.resolve(path), path)

    def test_css_dependency_change_cannot_generate_under_old_version(self):
        self.write("assets/app/styles/index.css", '@import url("child.css") layer(ui);')
        self.write("assets/app/styles/child.css", '.button { display:flex; }')
        self.store.refresh()
        self.write("assets/app/styles/child.css", '.button { display:grid; }')
        with self.assertRaises(FileNotFoundError):
            self.store.stylesheet("assets/app/styles/index.css")

    def test_gzip_quality(self):
        for value in ("gzip", "br, GZIP;q=0.5", "*;q=0.1"):
            self.assertTrue(accepts_gzip(value), value)
        for value in (None, "identity", "gzip;q=0, *;q=1", "gzip;q=2", "gzip;q=nan", "gzip;q=invalid"):
            self.assertFalse(accepts_gzip(value), value)


if __name__ == "__main__":
    unittest.main()
