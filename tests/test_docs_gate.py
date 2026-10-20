"""文档门禁覆盖递归分册、服务根与符号引用。"""

import tempfile
import subprocess
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
                      "tools/boxdetect/README.md", "assets/vendor/katex/README.md", "README.md", "AGENTS.md"]
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


def task_log(topic="current", state="已交付"):
    return (f"# 2026-10-20 合成任务\n\n> **任务**\n> - 标识：{topic}\n> - 状态：{state}\n\n"
            + "\n".join(f"## {section}\n\n合成验证记录。\n" for section in check_docs.TASK_SECTIONS))


class TaskLogGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="omrs-docs-git-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.write("AGENTS.md", "| 改动范围 | 必查/必更新文档 |\n|---|---|\n"
                   "| `omrs/sample.py` | `AI/one.md`、`AI/two.md`；接口变化同时更新 `AI/conditional.md` |\n")
        self.write("omrs/sample.py", "# 合成基线\n")
        self.write("AI/one.md", "# 文档一\n")
        self.write("AI/two.md", "# 文档二\n")
        self.write("AI/logs/2026-10-19_legacy.md", "# 2026-10-19 旧任务\n\n已交付的历史事实。\n")
        self.git("init", "-q")
        self.commit()
        root = patch.multiple(check_docs, ROOT=str(self.root), AI_DIR=str(self.root / "AI"), LOG_DIR=str(self.root / "AI/logs"))
        root.start()
        self.addCleanup(root.stop)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True)

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=门禁测试", "-c", "user.email=gate@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "合成基线")

    def test_each_unconditional_document_is_required_and_conditional_docs_are_not_forced(self):
        self.write("omrs/sample.py", "# 已修改\n")
        self.write("AI/one.md", "# 已修改\n")
        self.write("AI/logs/2026-10-20_current.md", task_log())
        problems = check_docs.check_diff("HEAD")
        self.assertEqual(len(problems), 1)
        self.assertIn("AI/two.md", problems[0])
        self.write("AI/two.md", "# 也已修改\n")
        self.assertEqual(check_docs.check_diff("HEAD"), [])

    def test_empty_new_log_does_not_satisfy_persistent_change(self):
        self.write("AI/one.md", "# 已修改\n")
        self.write("AI/logs/2026-10-20_empty.md", "# 2026-10-20 空记录\n")
        problems = check_docs.check_diff("HEAD")
        self.assertTrue(any("非空" in p for p in problems))
        self.assertTrue(any("没有合格" in p for p in problems))

    def test_changing_historical_log_cannot_replace_new_task_log(self):
        self.write("AI/one.md", "# 已修改\n")
        self.write("AI/logs/2026-10-19_legacy.md", "# 2026-10-19 用旧日期伪装新任务\n")
        problems = check_docs.check_diff("HEAD")
        self.assertTrue(any("历史日志只能" in p for p in problems))
        self.assertTrue(any("没有合格" in p for p in problems))

    def test_append_only_erratum_is_accepted_with_its_own_task_record(self):
        old = self.root / "AI/logs/2026-10-19_legacy.md"
        original = old.read_text()
        self.write(str(old.relative_to(self.root)), original + "\n## 勘误（2026-10-20）\n\n纠正原验证计数。\n")
        self.assertTrue(any("没有合格" in p for p in check_docs.check_diff("HEAD")))
        self.write("AI/logs/2026-10-20_current.md", task_log())
        self.assertEqual(check_docs.check_diff("HEAD"), [])
        self.write(str(old.relative_to(self.root)), original.replace("历史事实", "改写历史") + "\n## 勘误（2026-10-20）\n\n附注。\n")
        self.assertTrue(any("历史日志只能" in p for p in check_docs.check_diff("HEAD")))

    def test_ongoing_task_can_continue_across_commits_and_be_delivered(self):
        path = "AI/logs/2026-10-20_current.md"
        self.write(path, task_log(state="进行中"))
        self.commit()
        self.write("AI/one.md", "# 已修改\n")
        self.write(path, task_log() + "\n## 续作结果\n\n完成。\n")
        self.assertEqual(check_docs.check_diff("HEAD"), [])

    def test_delivered_task_cannot_be_reopened_to_bypass_new_task_record(self):
        path = "AI/logs/2026-10-20_current.md"
        self.write(path, task_log())
        self.commit()
        self.write(path, task_log(state="进行中"))
        self.write("AI/one.md", "# 已修改\n")
        self.assertTrue(any("历史日志只能" in p for p in check_docs.check_diff("HEAD")))

    def test_deleted_and_renamed_logs_are_rejected(self):
        old = self.root / "AI/logs/2026-10-19_legacy.md"
        old.rename(old.with_name("2026-10-20_renamed.md"))
        self.assertTrue(any("不得删除、改名" in p for p in check_docs.check_diff("HEAD")))

    def test_document_deletion_does_not_count_as_document_update(self):
        self.write("omrs/sample.py", "# 已修改\n")
        (self.root / "AI/one.md").unlink()
        self.write("AI/two.md", "# 已修改\n")
        self.write("AI/logs/2026-10-20_current.md", task_log())
        self.assertTrue(any("AI/one.md" in p for p in check_docs.check_diff("HEAD")))

    def test_file_names_with_spaces_survive_git_collection(self):
        self.write("docs/with spaces.md", "合成文档\n")
        self.assertIn("docs/with spaces.md", check_docs.changed_files("HEAD"))

    def test_new_log_requires_matching_topic_real_date_and_nonempty_validation(self):
        for path, text, expected in (
            ("AI/logs/2026-10-20_current.md", task_log(topic="different"), "标识"),
            ("AI/logs/2026-99-20_current.md", task_log().replace("2026-10-20", "2026-99-20"), "日期无效"),
            ("AI/logs/2026-10-20_current.md", task_log().replace("## 未执行验证\n\n合成验证记录。", "## 未执行验证\n"), "未执行验证"),
        ):
            with self.subTest(path=path):
                self.assertTrue(any(expected in p for p in check_docs.check_task_log(path, text)))


if __name__ == "__main__":
    unittest.main()
