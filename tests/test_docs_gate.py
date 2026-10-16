"""文档门禁覆盖递归分册、服务根与符号引用。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import check_docs


class DocsGateTests(unittest.TestCase):
    def test_recursive_public_targets_exclude_private_and_avoid_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            public = ["AI/README.md", "AI/data/storage.md", "AI/training/records/sample.md",
                      "AI/plans/README.md", "AI/plans/sample/plan.md", "AI/plans/sample/progress.md",
                      "services/zuoyebang/docs/nested/api.md", "services/boxdetect/README.md",
                      "tools/boxdetect/README.md", "assets/vendor/katex/README.md", "README.md"]
            private = ["AI/.secret.md", "AI/logs/private.md", "AI/omrs_work/private.md", "AI/plans/archive/old.md",
                       "services/zuoyebang/private/secret.md", "services/zuoyebang/.state/secret.md",
                       "tools/boxdetect/tmp-sample/secret.md", "assets/vendor/node_modules/private.md"]
            for name in public + private:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# 合成文档\n", encoding="utf-8")
            (root / "AI/linked.md").symlink_to(root / "AI/logs/private.md")
            (root / "AI/linked-dir").symlink_to(root / "AI/logs", target_is_directory=True)
            with patch.multiple(check_docs, ROOT=temp, AI_DIR=str(root / "AI"),
                                PLANS_DIR=str(root / "AI/plans")):
                targets = check_docs.doc_targets()
                names = [Path(path).relative_to(root).as_posix() for path in targets]
            self.assertEqual(set(names), set(public))
            self.assertEqual(len(names), len(set(names)))

    def test_symbol_suffix_still_checks_file_but_not_symbol(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "omrs").mkdir()
            (root / "omrs/exists.py").write_text("pass\n", encoding="utf-8")
            doc = root / "README.md"
            doc.write_text("`omrs/exists.py::not_a_symbol()`\n`omrs/missing.py::read()`\n"
                           "`services/missing/main.py::Service.run`\n", encoding="utf-8")
            with patch.object(check_docs, "ROOT", temp):
                problems, _ = check_docs.check_file(str(doc))
            self.assertEqual(len(problems), 2)
            self.assertIn("omrs/missing.py", problems[0])
            self.assertIn("services/missing/main.py", problems[1])

    def test_service_docs_accept_service_root_and_repository_root_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = root / "services/zuoyebang"
            (service / "assets").mkdir(parents=True)
            (service / "assets/panel.js").write_text("export {};\n", encoding="utf-8")
            (root / "omrs").mkdir()
            (root / "omrs/server.py").write_text("pass\n", encoding="utf-8")
            doc = service / "README.md"
            doc.write_text("`assets/panel.js::mount()`\n`omrs/server.py`\n"
                           "`tests/missing.py::test_missing`\n", encoding="utf-8")
            with patch.object(check_docs, "ROOT", temp):
                problems, _ = check_docs.check_file(str(doc))
            self.assertEqual(len(problems), 1)
            self.assertIn("tests/missing.py", problems[0])


if __name__ == "__main__":
    unittest.main()
