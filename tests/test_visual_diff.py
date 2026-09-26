import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tests.visual.run import diff_images


class DiffImagesTests(unittest.TestCase):
    def test_uses_max_channel_threshold_and_highlights_changed_pixel(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ref = Image.new("RGB", (2, 2), (0, 0, 0))
            cur = ref.copy()
            cur.putpixel((0, 0), (25, 0, 0))
            ref_path, cur_path, diff_path = root / "ref.png", root / "cur.png", root / "diff.png"
            ref.save(ref_path)
            cur.save(cur_path)

            ratio, resized = diff_images(str(ref_path), str(cur_path), str(diff_path))

            self.assertEqual(ratio, 25.0)
            self.assertFalse(resized)
            diff = Image.open(diff_path).convert("RGB")
            self.assertEqual(diff.getpixel((0, 0)), (230, 30, 60))
            self.assertNotEqual(diff.getpixel((1, 1)), (230, 30, 60))


if __name__ == "__main__":
    unittest.main()
