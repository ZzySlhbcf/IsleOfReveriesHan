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
                               changed_original_images, create_manifest,
                               atlas_frame_pixels, unchanged_atlas_frames)
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

    def test_repacked_atlases_are_checked_by_animation_frames(self):
        """Atlas repacking is safe only if all rendered frames are unchanged."""
        import copy
        from unittest.mock import patch

        previous = os.environ.get("CN_PREVIOUS_VANILLA_BUNDLE")
        if not previous or not os.path.isfile(previous):
            self.skipTest("Set CN_PREVIOUS_VANILLA_BUNDLE to previous English bundle")
        changed = changed_original_images(
            create_manifest(previous, self.patched), self.vanilla)
        self.assertEqual(changed, ["images/fileselect_cursor-sheet0.webp",
                                   "images/maps_sprite-sheet0.webp"])
        self.assertTrue(unchanged_atlas_frames(previous, self.vanilla, changed))
        base = atlas_frame_pixels(previous, changed)
        self.assertTrue(base)
        damaged = copy.copy(base)
        key = next(iter(damaged))
        size, pixels, attributes = damaged[key]
        damaged[key] = (size, bytes([pixels[0] ^ 255]) + pixels[1:], attributes)
        with patch("resource_manifest.atlas_frame_pixels", side_effect=[base, damaged]):
            self.assertFalse(unchanged_atlas_frames(previous, self.vanilla, changed))

    def test_dungeon_numbers_are_centered_with_chinese(self):
        """All six splash captions place narrow digits in the middle of a cell."""
        entries, _, start = read_directory(self.patched)
        with open(self.patched, "rb") as fh:
            spec = next(e for e in entries if e["name"] == "data.json")
            fh.seek(start + spec["offset"])
            project = json.loads(fh.read(spec["size"]))["project"]
            sprite = next(o for o in project[3] if isinstance(o, list)
                          and o[0] == "Dungeon_Title")
            frames = {a[0]: a[7][0][:7] for a in sprite[7]}
            specs = {e["name"]: e for e in entries}
            with open(self.patched, "rb") as fh:
                # The same atlas is reused for all six animations.
                atlas_name = frames["1"][0]
                atlas_entry = specs[atlas_name]
                fh.seek(start + atlas_entry["offset"])
                atlas = Image.open(io.BytesIO(fh.read(atlas_entry["size"]))).convert("RGBA")
            for number in range(1, 7):
                _name, _size, x, y, w, h, rotated = frames[str(number)]
                piece = atlas.crop((x, y, x + (h if rotated else w),
                                    y + (w if rotated else h)))
                if rotated:
                    piece = piece.transpose(Image.Transpose.ROTATE_90)
                # "第N层" is centered over a 120px panel; three 8px cells.
                start_x = 4 + (120 - 24) // 2
                centers_twice = []
                for col in range(3):
                    cell = piece.crop((start_x + col * 8, 96,
                                       start_x + (col + 1) * 8, 104))
                    ink_x = [cx for cy in range(8) for cx in range(8)
                             if cell.getpixel((cx, cy)) == (7, 24, 33, 255)]
                    self.assertTrue(ink_x, f"empty dungeon {number} title cell {col}")
                    centers_twice.append(min(ink_x) + max(ink_x))
                self.assertEqual(centers_twice, [6, 6, 6],
                                 f"dungeon {number} digit is off-center")

    def test_save_menu_translates_only_label_pixels(self):
        """All six alternating frames have Chinese labels; cursor art is intact."""
        def frames(bundle):
            entries, _, start = read_directory(bundle)
            index = {entry["name"]: entry for entry in entries}
            with open(bundle, "rb") as fh:
                spec = index["data.json"]
                fh.seek(start + spec["offset"])
                project = json.loads(fh.read(spec["size"]))["project"]
                sprite = next(obj for obj in project[3]
                              if isinstance(obj, list) and obj[0] == "SaveTrinketBack")
                result = {}
                atlases = {}
                for anim in sprite[7]:
                    for number, spec in enumerate(anim[7]):
                        name, size, x, y, w, h, rotated = spec[:7]
                        if name not in atlases:
                            entry = index[name]
                            fh.seek(start + entry["offset"])
                            atlases[name] = Image.open(
                                io.BytesIO(fh.read(entry["size"]))).convert("RGBA")
                            self.assertEqual(size, entry["size"])
                        region = atlases[name].crop((x, y, x + (h if rotated else w),
                                                      y + (w if rotated else h)))
                        result[(anim[0], number)] = (
                            region.transpose(Image.Transpose.ROTATE_90)
                            if rotated else region)
                return result

        vanilla, patched = frames(self.vanilla), frames(self.patched)
        self.assertEqual(set(vanilla), set(patched))
        self.assertEqual(len(patched), 6)
        for key, new in patched.items():
            old = vanilla[key]
            self.assertEqual(old.size, new.size)
            changed = [(x, y) for y in range(old.height) for x in range(old.width)
                       if old.getpixel((x, y)) != new.getpixel((x, y))]
            self.assertTrue(changed, f"still English in {key}")
            for x, y in changed:
                self.assertTrue(96 <= x < 160 and 60 <= y < 84,
                                f"cursor/border changed in {key} at {(x, y)}")
            for y in (60, 68, 76):
                self.assertTrue(any(y <= py < y + 8 for _, py in changed),
                                f"text row {y} unchanged in {key}")
            # Identical labels across frames even when the selection cursor moves.
            self.assertEqual(new.crop((96, 60, 160, 84)).tobytes(),
                             patched[("1", 0)].crop((96, 60, 160, 84)).tobytes())

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
