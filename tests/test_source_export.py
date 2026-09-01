import io
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from omrs.source_export import create_source_export


class SourceExportTests(unittest.TestCase):
    def _git(self, root, *args):
        subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE)

    def test_source_export_excludes_personal_and_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init", "-q")
            (root / "omrs").mkdir()
            (root / "omrs" / "server.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "README.md").write_text("OMRS\n", encoding="utf-8")
            (root / "错题").mkdir()
            (root / "错题" / "private.md").write_text("private\n", encoding="utf-8")
            (root / "AI" / "logs").mkdir(parents=True)
            (root / "AI" / "logs" / "private.md").write_text("private\n", encoding="utf-8")
            (root / "OMRS-EXP-demo.html").write_text("private export\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture")

            payload, filename, meta = create_source_export(str(root))

            self.assertTrue(filename.startswith("OMRS-source-sanitized-"))
            self.assertTrue(filename.endswith(".zip"))
            self.assertEqual(meta["files"], 2)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                self.assertIn("OMRS/omrs/server.py", names)
                self.assertIn("OMRS/README.md", names)
                self.assertFalse(any("错题" in name for name in names))
                self.assertFalse(any("AI/logs" in name for name in names))
                self.assertIn("OMRS/SOURCE_EXPORT_MANIFEST.txt", names)
                manifest = archive.read("OMRS/SOURCE_EXPORT_MANIFEST.txt").decode("utf-8")
                self.assertIn("错题/", manifest)
                self.assertIn("OMRS-EXP-*.html", manifest)


if __name__ == "__main__":
    unittest.main()
