import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from omrs.source_export import create_source_export


class SourceExportTests(unittest.TestCase):
    def test_uncommitted_source_exports_without_git_but_private_data_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "omrs").mkdir()
            (root / "omrs" / "server.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_new.py").write_text("pass\n", encoding="utf-8")
            (root / "README.md").write_text("OMRS\n", encoding="utf-8")
            (root / "错题").mkdir()
            (root / "错题" / "private.md").write_text("private\n", encoding="utf-8")
            (root / "Task").mkdir()
            (root / "Task" / "notes.md").write_text("private\n", encoding="utf-8")
            (root / "AI" / "logs").mkdir(parents=True)
            (root / "AI" / "README.md").write_text("docs\n", encoding="utf-8")
            (root / "AI" / "logs" / "private.md").write_text("private\n", encoding="utf-8")
            (root / "omrs" / "config.json").write_text('{"api_key":"secret"}', encoding="utf-8")
            (root / "omrs" / "state.json").write_text('{"private":1}', encoding="utf-8")
            (root / "tests" / "ui_baseline.json").write_text('{"files":{}}', encoding="utf-8")
            (root / "assets" / "app").mkdir(parents=True)
            (root / "assets" / "app" / "package.json").write_text('{"type":"module"}', encoding="utf-8")
            (root / "assets" / "app" / "data.json").write_text('{"private":1}', encoding="utf-8")
            (root / "omrs" / "token.txt").write_text("secret\n", encoding="utf-8")
            (root / "omrs" / ".env").write_text("SECRET=value\n", encoding="utf-8")
            (root / "omrs" / "__pycache__").mkdir()
            (root / "omrs" / "__pycache__" / "stale.py").write_text("stale\n", encoding="utf-8")
            (root / "OMRS-EXP-demo.html").write_text("private export\n", encoding="utf-8")

            payload, filename, meta = create_source_export(str(root))

            self.assertTrue(filename.startswith("OMRS-source-sanitized-"))
            self.assertTrue(filename.endswith(".zip"))
            self.assertEqual(meta["files"], 6)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, {
                    "OMRS/README.md", "OMRS/AI/README.md", "OMRS/omrs/server.py",
                    "OMRS/tests/test_new.py", "OMRS/tests/ui_baseline.json", "OMRS/assets/app/package.json",
                    "OMRS/SOURCE_EXPORT_MANIFEST.txt",
                })
                manifest = archive.read("OMRS/SOURCE_EXPORT_MANIFEST.txt").decode("utf-8")
                self.assertIn("不依赖 Git", manifest)
                self.assertIn("tests/test_new.py", manifest)
                self.assertIn("错题/", manifest)

    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            secret = Path(outside) / "secret.py"
            secret.write_text("secret\n", encoding="utf-8")
            (root / "omrs").mkdir()
            (root / "omrs" / "real.py").write_text("real\n", encoding="utf-8")
            (root / "omrs" / "linked.py").symlink_to(secret)
            (root / "assets").symlink_to(Path(outside), target_is_directory=True)

            payload, _, meta = create_source_export(str(root))

            self.assertEqual(meta["files"], 1)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertEqual(set(archive.namelist()), {
                    "OMRS/omrs/real.py", "OMRS/SOURCE_EXPORT_MANIFEST.txt",
                })

    def test_no_source_files_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "没有可导出的源码文件"):
                create_source_export(tmp)


if __name__ == "__main__":
    unittest.main()
