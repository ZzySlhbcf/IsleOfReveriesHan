"""Regression checks for the release inventory and update guard."""
import json
import io
import os
import sys
import unittest

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mod_src", "tools"))

from resource_manifest import (EXPECTED_CHANGED, IMAGE_LABELS,  # noqa: E402
                               changed_original_images, create_manifest)
from c3bundle import read_directory  # noqa: E402


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

    def test_map_prompt_spacing_and_atlas_preservation(self):
        entries, _, start = read_directory(self.patched)
        spec = next(row for row in entries if row["name"] == "data.json")
        with open(self.patched, "rb") as bundle:
            bundle.seek(start + spec["offset"])
            project = json.loads(bundle.read(spec["size"]))["project"]
        types = {obj[0]: obj for obj in project[3] if isinstance(obj, list) and obj}

        def frame(obj, anim):
            spec = next(a for a in types[obj][7] if a[0] == anim)[7][0]
            name, size, x, y, w, h, rotated = spec[:7]
            entry = next(row for row in entries if row["name"] == name)
            self.assertEqual(size, entry["size"])
            with open(self.patched, "rb") as bundle:
                bundle.seek(start + entry["offset"])
                atlas = Image.open(io.BytesIO(bundle.read(entry["size"]))).convert("RGBA")
            crop = atlas.crop((x, y, x + (h if rotated else w),
                               y + (w if rotated else h)))
            return crop.transpose(Image.Transpose.ROTATE_90) if rotated else crop

        paper = (219, 207, 181, 255)
        for number in range(1, 9):
            world = frame("WorldMapBG", str(number))
            for x in range(80, 88):
                for y in range(136, 144):
                    self.assertEqual(world.getpixel((x, y)), paper)
            detail = frame("Maps_Sprite", f"WorldMap_{number}")
            # Only the footer changes: room markers and map art remain intact.
            self.assertEqual(detail.size, (128, 144))
        upper_city = frame("WarpMenu_HiddenText", "7")
        for x in range(88, 96):
            for y in range(8):
                self.assertEqual(upper_city.getpixel((x, y)), paper)


if __name__ == "__main__":
    unittest.main()
