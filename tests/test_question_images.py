"""题图原件：共享图片列表、安全目录读取、原字节及解码资源边界。"""

import importlib.util
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from omrs import question_images
from omrs.agent.tools import read as read_tools
from omrs.creation import create_question
from omrs.ledger import read_commits
from tests.test_mcp_protocol import _gif, _jpeg, _png

HAS_PIL = importlib.util.find_spec("PIL") is not None


def animated_gif(frames):
    from PIL import Image
    images = [Image.new("RGB", (2, 2), (index, 255 - index, 0)) for index in range(frames)]
    stream = io.BytesIO()
    images[0].save(stream, format="GIF", save_all=True, append_images=images[1:],
                   duration=10, loop=0, disposal=2, optimize=False)
    return stream.getvalue()


class QuestionImagesImportTests(unittest.TestCase):
    def test_import_does_not_require_mcp_or_pillow(self):
        script = """
import builtins
original = builtins.__import__
def limited(name, *args, **kwargs):
    if name.split('.')[0] in {'mcp', 'PIL'}:
        raise ModuleNotFoundError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = limited
import omrs.question_images
import omrs.cli
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(HAS_PIL, "可选图片校验依赖 Pillow 未安装")
class QuestionImageTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="omrs-question-images-")
        self.addCleanup(work.cleanup)
        self.vault = Path(work.name) / "vault"
        self.attachments = self.vault / "错题" / "附件"
        self.attachments.mkdir(parents=True)
        self.outside = Path(work.name) / "outside"
        self.outside.mkdir()
        self.outside_image = self.outside / "private.png"
        self.outside_image.write_bytes(_png(3, 3))

    def question(self, question="![[figure.png]]", answer=""):
        return create_question(str(self.vault), "物理", "读图", 5,
                               question_text=question, answer_text=answer)["uid"]

    def write(self, name="figure.png", raw=None):
        path = self.attachments / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_png() if raw is None else raw)
        return path

    def read(self, uid, index=0):
        return question_images.read_question_image(str(self.vault), uid, index)

    def both_readers(self):
        return (True, False) if question_images._DIRECTORY_FDS else (False,)

    def test_supported_formats_and_tail_bytes_are_unchanged(self):
        uid = self.question()
        for raw, fmt in ((_png(), "png"), (_jpeg(), "jpeg"), (_gif(), "gif"),
                         (_png() + b"PNG-ORIGINAL-TAIL", "png"),
                         (_jpeg() + b"JPEG-ORIGINAL-TAIL", "jpeg"),
                         (animated_gif(3), "gif")):
            with self.subTest(fmt=fmt, size=len(raw)):
                self.write(raw=raw)
                for reader in self.both_readers():
                    with patch.object(question_images, "_DIRECTORY_FDS", reader):
                        self.assertEqual(self.read(uid), (raw, fmt))

    def test_images_order_and_deduplication_match_untruncated_shared_read(self):
        uid = self.question("![先出现的 Markdown](markdown.png)\n![[wiki.png]]\n"
                            + "长题干" * 600 + "\n![[late.png]]\n![[wiki.png]]",
                            "![[answer.png]]\n![重复](markdown.png)")
        images = {"markdown.png": _png(3, 2), "wiki.png": _png(4, 2),
                  "late.png": _png(5, 2), "answer.png": _png(6, 2)}
        for name, raw in images.items():
            self.write(name, raw)
        before = read_tools.get_question({"vault": str(self.vault)}, {"uid": uid})["result"]
        self.assertIn("已截断", before["sections"]["题目"])
        self.assertEqual(set(before["images"]), set(images))
        for index, name in enumerate(before["images"]):
            self.assertEqual(self.read(" " + uid + " ", index), (images[name], "png"))
        self.assertEqual(read_tools.get_question({"vault": str(self.vault)}, {"uid": uid})["result"], before)

    def test_unique_nested_attachment_is_read_without_business_writes(self):
        uid = self.question()
        original = _png()
        self.write("nested/deeper/figure.png", original)
        commits = read_commits(str(self.vault))
        for reader in self.both_readers():
            with patch.object(question_images, "_DIRECTORY_FDS", reader):
                self.assertEqual(self.read(uid), (original, "png"))
        self.assertEqual(read_commits(str(self.vault)), commits)

    def test_absent_question_no_images_out_of_range_and_invalid_inputs(self):
        uid = self.question()
        self.write()
        empty = self.question("纯文字")
        for args, message in (((empty, 0), "没有引用图片"), ((uid, 1), "超出"),
                              (("不存在1", 0), "题目不存在"), ((uid, -1), "整数"),
                              ((uid, True), "整数"), ((uid, "0"), "整数"),
                              ((uid, .5), "整数"), ((uid, 1.0), "整数"),
                              (("", 0), "题目编号"), ((" " * 3, 0), "题目编号"),
                              (("x" * 201, 0), "题目编号")):
            with self.subTest(args=args):
                with self.assertRaisesRegex(ValueError, message):
                    self.read(*args)

    def test_missing_image_has_no_path_and_no_vault_root_fallback(self):
        uid = self.question("![[private.png]]")
        (self.vault / "private.png").write_bytes(_png())
        for reader in self.both_readers():
            with patch.object(question_images, "_DIRECTORY_FDS", reader):
                with self.assertRaisesRegex(ValueError, "^题目引用的图片不存在$") as error:
                    self.read(uid)
                self.assertNotIn(str(self.vault), str(error.exception))

    def test_paths_cannot_escape_and_encoded_names_are_not_decoded(self):
        for reference in ("../../private.png", str(self.outside_image),
                          r"C:\outside\private.png", "..%2fprivate.png",
                          "%2e%2e%2fprivate.png", "https://example.test/private.png"):
            uid = self.question(f"![[{reference}]]")
            for reader in self.both_readers():
                with self.subTest(reference=reference, reader=reader), \
                        patch.object(question_images, "_DIRECTORY_FDS", reader):
                    with self.assertRaisesRegex(ValueError, "图片不存在"):
                        self.read(uid)
        encoded = self.question("![[space%20name.png]]")
        self.write("space name.png")
        with self.assertRaisesRegex(ValueError, "图片不存在"):
            self.read(encoded)

    def test_unsafe_selected_filename_is_rejected_before_filesystem_access(self):
        for name in ("../figure.png", str(self.outside_image), r"C:\private.png",
                     "C:private.png", ".", "..", "null\0.png", "line\n.png"):
            with self.subTest(name=name), \
                    patch.object(read_tools, "get_question", return_value={"result": {"images": [name]}}), \
                    patch.object(question_images, "_read_from_directory_fds") as opened:
                with self.assertRaisesRegex(ValueError, "文件名不安全"):
                    self.read("示例1")
                opened.assert_not_called()

    def test_duplicate_name_rejects_instead_of_choosing_first(self):
        uid = self.question()
        self.write()
        self.write("nested/figure.png", _png(5, 5))
        for reader in self.both_readers():
            with patch.object(question_images, "_DIRECTORY_FDS", reader):
                with self.assertRaisesRegex(ValueError, "文件名不唯一"):
                    self.read(uid)

    def test_file_directory_and_root_symlinks_are_rejected(self):
        uid = self.question("![[private.png]]")
        for reader in self.both_readers():
            with patch.object(question_images, "_DIRECTORY_FDS", reader):
                link = self.attachments / "private.png"
                link.symlink_to(self.outside_image)
                with self.assertRaisesRegex(ValueError, "普通文件"):
                    self.read(uid)
                link.unlink()
                link = self.attachments / "linked"
                link.symlink_to(self.outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "图片不存在"):
                    self.read(uid)
                link.unlink()
                self.attachments.rmdir()
                self.attachments.symlink_to(self.outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "普通目录"):
                    self.read(uid)
                self.attachments.unlink()
                self.attachments.mkdir()

    def test_non_regular_file_is_rejected_before_read(self):
        uid = self.question()
        target = self.attachments / "figure.png"
        for reader in self.both_readers():
            with patch.object(question_images, "_DIRECTORY_FDS", reader), \
                    patch.object(question_images, "_read_bytes") as read:
                target.mkdir()
                with self.assertRaisesRegex(ValueError, "普通文件"):
                    self.read(uid)
                target.rmdir()
                if hasattr(os, "mkfifo"):
                    os.mkfifo(target)
                    with self.assertRaisesRegex(ValueError, "普通文件"):
                        self.read(uid)
                    target.unlink()
                read.assert_not_called()

    def test_file_swap_between_stat_and_open_cannot_return_external_bytes(self):
        uid = self.question()
        real_open = os.open
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        for reader in self.both_readers():
            target = self.write()

            def replace(name, *args, **kwargs):
                if os.fspath(name).endswith("figure.png"):
                    target.unlink()
                    target.symlink_to(self.outside_image)
                return real_open(name, *args, **kwargs)

            with self.subTest(reader=reader), patch.object(question_images, "_DIRECTORY_FDS", reader), \
                    patch.object(question_images.os, "open", side_effect=replace), \
                    patch.object(question_images, "_read_bytes") as read:
                # 路径兼容分支模拟缺少 O_NOFOLLOW 的平台，仍须以文件身份拒绝。
                if not reader:
                    with patch.object(question_images, "_file_flags", return_value=flags):
                        with self.assertRaisesRegex(ValueError, "发生变化"):
                            self.read(uid)
                else:
                    with self.assertRaisesRegex(ValueError, "无法安全读取"):
                        self.read(uid)
                read.assert_not_called()
            target.unlink()

    def test_eight_mib_is_inclusive_and_larger_file_rejected_before_read(self):
        uid = self.question()
        raw = _png()
        raw += b"\0" * (question_images.MAX_IMAGE_BYTES - len(raw))
        self.write(raw=raw)
        self.assertEqual(self.read(uid), (raw, "png"))
        self.write(raw=raw + b"x")
        with patch.object(question_images.os, "read") as read:
            with self.assertRaisesRegex(ValueError, "8 MiB"):
                self.read(uid)
            read.assert_not_called()

    def test_growth_after_size_check_still_reads_at_most_limit_plus_one(self):
        target = self.write(raw=b"x" * (question_images.MAX_IMAGE_BYTES + 100))
        before = target.stat()
        small_stat = SimpleNamespace(st_size=0, st_mtime_ns=before.st_mtime_ns,
                                     st_ctime_ns=before.st_ctime_ns)
        real_read = os.read
        with target.open("rb") as stream, \
                patch.object(question_images.os, "fstat", return_value=small_stat), \
                patch.object(question_images.os, "read", wraps=real_read) as read:
            with self.assertRaisesRegex(ValueError, "8 MiB"):
                question_images._read_bytes(stream.fileno())
            self.assertEqual(sum(call.args[1] for call in read.call_args_list),
                             question_images.MAX_IMAGE_BYTES + 1)

    def test_changed_file_while_reading_is_rejected(self):
        uid = self.question()
        target = self.write()
        original_read = os.read
        changed = False

        def change(descriptor, size):
            nonlocal changed
            chunk = original_read(descriptor, size)
            if not changed:
                changed = True
                with target.open("ab") as stream:
                    stream.write(b"changed")
            return chunk

        with patch.object(question_images.os, "read", side_effect=change):
            with self.assertRaisesRegex(ValueError, "读取期间发生变化"):
                self.read(uid)

    def test_corrupt_empty_and_unsupported_images_are_rejected(self):
        uid = self.question()
        bad_png = b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 2, 2)
        from PIL import Image
        bmp = io.BytesIO()
        Image.new("RGB", (2, 2)).save(bmp, format="BMP")
        for raw in (b"", bad_png, _png()[:-15], _jpeg()[:100], _gif()[:12], bmp.getvalue()):
            with self.subTest(size=len(raw)):
                self.write(raw=raw)
                with self.assertRaises(ValueError):
                    self.read(uid)

    def test_pixel_and_frame_limits_are_enforced_without_transforming_images(self):
        from PIL import Image
        huge = bytearray(_png())
        huge[16:20] = (40_000_001).to_bytes(4, "big")
        huge[20:24] = (1).to_bytes(4, "big")
        with patch.object(Image, "open") as decode:
            with self.assertRaisesRegex(ValueError, "像素超过"):
                question_images.validate_original_image(bytes(huge))
            decode.assert_not_called()
        with patch("omrs.drafts._MCP_MAX_IMAGE_PIXELS", 8):
            with self.assertRaisesRegex(ValueError, "像素总量"):
                question_images.validate_original_image(animated_gif(3))
        raw = animated_gif(100)
        self.assertEqual(question_images.validate_original_image(raw)["data"], raw)
        with self.assertRaisesRegex(ValueError, "100 帧"):
            question_images.validate_original_image(animated_gif(101))


if __name__ == "__main__":
    unittest.main()
