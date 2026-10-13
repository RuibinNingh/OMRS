import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from omrs.source_export import create_source_export


class SourceExportTests(unittest.TestCase):
    def test_boxdetect_public_sources_exclude_generated_and_unknown_paths(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            sources = {
                'services/boxdetect/README.md': '# 服务\n',
                'services/boxdetect/pyproject.toml': '[project]\n',
                'services/boxdetect/requirements.txt': 'numpy==2.5.2\n',
                'services/boxdetect/.gitignore': '.state/\n',
                'services/boxdetect/boxdetect_service/server.py': '# 服务源码\n',
                'services/boxdetect/tests/package_smoke.py': '# 安装包检查\n',
                'tools/boxdetect/_service.py': '# 兼容\n',
                'tools/boxdetect/train.py': '# 离线训练\n',
                'tools/boxdetect/requirements-serve.txt': '-r ../../services/boxdetect/requirements.txt\n',
                'tools/boxdetect/crop-prompt-v2.txt': '固定提示词\n',
            }
            private = [
                'services/boxdetect/model.onnx', 'services/boxdetect/model.json',
                'services/boxdetect/.state/secret.py', 'services/boxdetect/private/secret.py',
                'services/boxdetect/boxdetect_service/private/secret.py',
                'services/boxdetect/tests/data/private.py', 'services/boxdetect/token.txt',
                'tools/boxdetect/unregistered.py', 'tools/boxdetect/secret.txt',
                'tools/boxdetect/models/private.py', 'tools/boxdetect/datasets/private.py',
                'tools/boxdetect/managed/state.json', 'tools/other/private.py',
                'services/other/private.py',
            ]
            for name, content in {**sources, **{name: 'secret\n' for name in private}}.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            secret = Path(outside) / 'external.py'
            secret.write_text('secret\n')
            (root / 'services/boxdetect/boxdetect_service/linked.py').symlink_to(secret)
            payload, _, _ = create_source_export(tmp)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {'OMRS/' + name for name in sources} | {'OMRS/SOURCE_EXPORT_MANIFEST.txt'})

    def test_actual_export_has_a_closed_import_graph_for_legacy_and_standalone_service(self):
        source = Path(__file__).resolve().parents[1]
        payload, _, _ = create_source_export(str(source))
        with tempfile.TemporaryDirectory() as temp:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                archive.extractall(temp)
            root = Path(temp) / 'OMRS'
            for name in ['services/boxdetect/pyproject.toml', 'services/boxdetect/requirements.txt',
                         'tools/boxdetect/requirements-serve.txt', 'tools/boxdetect/requirements-train.txt',
                         'tools/boxdetect/crop-prompt-v2.txt']:
                self.assertTrue((root / name).is_file(), name)
            script = """import sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root))
from tools.boxdetect import inference, evaluate, train
from omrs import traincontrol
import boxdetect_service.inference as standalone
assert Path(standalone.__file__).is_relative_to(root)
assert inference.Detector is standalone.Detector
assert train.memory_available is __import__('omrs.system_resources', fromlist=['memory_available']).memory_available
"""
            env = {key: value for key, value in os.environ.items()
                   if key not in ('PYTHONPATH', 'OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL')}
            run = subprocess.run([sys.executable, '-I', '-c', script, str(root)], cwd=temp, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_uncommitted_source_exports_without_git_but_private_data_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "omrs").mkdir()
            (root / "omrs" / "server.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_new.py").write_text("pass\n", encoding="utf-8")
            (root / "README.md").write_text("OMRS\n", encoding="utf-8")
            (root / "requirements-mcp.txt").write_text("mcp==1.28.1\n", encoding="utf-8")
            (root / "错题").mkdir()
            (root / "错题" / "private.md").write_text("private\n", encoding="utf-8")
            (root / "错题" / ".omrs").mkdir()
            (root / "错题" / ".omrs" / "mcp_keys.json").write_text(
                '{"keys":[{"secret_sha256":"secret-test-digest"}]}', encoding="utf-8")
            (root / "Task").mkdir()
            (root / "Task" / "notes.md").write_text("private\n", encoding="utf-8")
            (root / "AI" / "logs").mkdir(parents=True)
            (root / "AI" / "README.md").write_text("docs\n", encoding="utf-8")
            (root / "AI" / "logs" / "private.md").write_text("private\n", encoding="utf-8")
            (root / "omrs" / "config.json").write_text('{"api_key":"secret"}', encoding="utf-8")
            (root / "omrs" / "state.json").write_text('{"private":1}', encoding="utf-8")
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
                    "OMRS/tests/test_new.py", "OMRS/assets/app/package.json",
                    "OMRS/requirements-mcp.txt",
                    "OMRS/SOURCE_EXPORT_MANIFEST.txt",
                })
                self.assertEqual(archive.read("OMRS/requirements-mcp.txt"), b"mcp==1.28.1\n")
                self.assertNotIn(b"secret", b"".join(archive.read(name) for name in names))
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

    def test_same_repository_gateway_sources_and_dependencies_exclude_private_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = {
                'requirements-zuoyebang.txt': 'Pillow>=10.4\n',
                'services/zuoyebang/zyb_gateway/server.py': '# 公开源码\n',
                'services/zuoyebang/pyproject.toml': '[project]\n',
                'services/zuoyebang/requirements.txt': 'segno>=1.6\n',
                'services/zuoyebang/vendor-manifest.json': '{}\n',
                'services/zuoyebang/.gitignore': '.state/\n',
                'services/zuoyebang/deploy/zuoyebang.service.example': '[Unit]\n',
            }
            private = ('services/zuoyebang/.state/account.py',
                       'services/zuoyebang/docs/private/secret.md',
                       'services/zuoyebang/docs/tmp-export/secret.py',
                       'services/zuoyebang/admin-secret.txt',
                       'services/other/private.py')
            for name, content in {**sources, **{name: 'secret\n' for name in private}}.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            payload, _, _ = create_source_export(tmp)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {'OMRS/' + name for name in sources} | {'OMRS/SOURCE_EXPORT_MANIFEST.txt'})
                self.assertNotIn(b'secret', b''.join(archive.read('OMRS/' + name) for name in sources))

    def test_no_source_files_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "没有可导出的源码文件"):
                create_source_export(tmp)


if __name__ == "__main__":
    unittest.main()
