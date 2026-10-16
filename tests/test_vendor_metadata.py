"""校验本地 vendor 来源清单与许可证副本，运行时不联网。"""

import hashlib
import json
import unittest
from pathlib import Path


class VendorMetadataTests(unittest.TestCase):
    def test_katex_manifest_covers_distribution_and_license(self):
        root = Path(__file__).resolve().parents[1] / 'assets/vendor/katex'
        manifest = json.loads((root / 'manifest.json').read_text())
        expected = {p.relative_to(root).as_posix() for p in root.rglob('*')
                    if p.is_file() and p.name not in ('README.md', 'manifest.json')}
        self.assertEqual(set(manifest['sha256']), expected)
        self.assertEqual(manifest['version'], '0.16.10')
        self.assertEqual(manifest['license'], 'MIT')
        self.assertIn('Permission is hereby granted', (root / 'LICENSE').read_text())
        for name, digest in manifest['sha256'].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)

    def test_entry_manifest_hashes_assets_and_limits_component_license(self):
        root = Path(__file__).resolve().parents[1] / 'assets/vendor'
        manifest = json.loads((root / 'entry-scene.manifest.json').read_text())
        for name, digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)
        component = manifest['third_party_components'][0]
        self.assertEqual(component['version'], '0.184.0')
        self.assertIn('revision:`184`', (root / 'entry-scene.js').read_text())
        self.assertIn('Permission is hereby granted', (root / component['license_file']).read_text())
        self.assertEqual(manifest['reference_scene_authorization'], 'unconfirmed')


if __name__ == '__main__':
    unittest.main()
