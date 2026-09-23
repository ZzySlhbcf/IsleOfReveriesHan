"""Regression checks for the release inventory and update guard."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mod_src", "tools"))

from resource_manifest import (EXPECTED_CHANGED, IMAGE_LABELS,  # noqa: E402
                               changed_original_images, create_manifest)


class ManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vanilla = os.environ.get("CN_VANILLA_BUNDLE")
        cls.patched = os.path.join(ROOT, "www", "assets.dat")
        if not cls.vanilla or not os.path.isfile(cls.vanilla):
            raise unittest.SkipTest("Set CN_VANILLA_BUNDLE to the English game bundle")
        cls.inventory = create_manifest(cls.vanilla, cls.patched)

    def test_exactly_the_reviewed_changes(self):
        self.assertEqual({row["path"] for row in self.inventory["modified"]},
                         EXPECTED_CHANGED)
        self.assertEqual(len(self.inventory["added"]), 24)
        self.assertEqual(self.inventory["removed"], [])
        self.assertEqual({row["path"] for row in self.inventory["modified"]
                          if row["path"].startswith("images/")}, set(IMAGE_LABELS))

    def test_update_guard_accepts_matching_original(self):
        self.assertEqual(changed_original_images(self.inventory, self.vanilla), [])

    def test_update_guard_detects_changed_atlas_and_bad_inventory(self):
        modified = json.loads(json.dumps(self.inventory, ensure_ascii=False))
        atlas = next(row for row in modified["modified"]
                     if row["path"] in IMAGE_LABELS)
        atlas["original"]["sha256"] = "0" * 64
        self.assertEqual(changed_original_images(modified, self.vanilla),
                         [atlas["path"]])
        modified["modified"].remove(atlas)
        with self.assertRaises(ValueError):
            changed_original_images(modified, self.vanilla)


if __name__ == "__main__":
    unittest.main()
