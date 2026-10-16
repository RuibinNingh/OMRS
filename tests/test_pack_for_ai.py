"""在合成路径上核验 Windows 打包边界，不运行 robocopy。"""

import fnmatch
import re
import unittest
from pathlib import Path, PureWindowsPath


class PackForAITests(unittest.TestCase):
    def test_copy_filters_keep_collaboration_docs_and_skip_private_outputs(self):
        script = (Path(__file__).resolve().parents[1] / "pack_for_ai.bat").read_text(encoding="utf-8-sig")
        command = script[script.index("robocopy "):script.index("if errorlevel 8")]
        dirs = re.findall(r'"([^"]+)"', command.split("/XD", 1)[1].split("/XF", 1)[0])
        files = re.findall(r'"([^"]+)"', command.split("/XF", 1)[1])

        def copied(relative):
            path = PureWindowsPath("C:/synthetic/OMRS") / relative
            for exclusion in dirs:
                pattern = exclusion.replace("%ROOT%", "C:\\synthetic\\OMRS").casefold()
                if "\\" in pattern:
                    if any(fnmatch.fnmatchcase(str(parent).casefold(), pattern) for parent in path.parents):
                        return False
                elif any(fnmatch.fnmatchcase(part.casefold(), pattern) for part in path.parts[:-1]):
                    return False
            return not any(fnmatch.fnmatchcase(path.name.casefold(), pattern.casefold()) for pattern in files)

        excluded = ["错题/private.md", "临时/private.md", "Task/private.md", "tool/private.py",
                    "unused/private.md", "logs/private.md", ".omrs-maintenance/state.json",
                    "assets/.omrs/state.json", "OMRS-EXP-synthetic.html", "SOURCE_EXPORT_MANIFEST.txt",
                    "services/zuoyebang/private/account.json", "services/zuoyebang/.state/token.json",
                    ".venv/omrs-service-e2e/checks.json", "AI/omrs_work/private.md"]
        allowed = ["AGENTS.md", "AI/README.md", "AI/data/storage.md", "AI/training/README.md",
                   "AI/logs/2026-10-16_synthetic.md", "omrs/source_export.py", "assets/app/main.js"]
        for name in excluded:
            self.assertFalse(copied(name), name)
        for name in allowed:
            self.assertTrue(copied(name), name)


if __name__ == "__main__":
    unittest.main()
