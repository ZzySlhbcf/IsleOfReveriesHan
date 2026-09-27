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
from audit_localization import read_entry, natural_event_misses, translator  # noqa: E402
from patch_baked_menus import dialogue_speaker_names, HIDDEN_NAMES  # noqa: E402


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
        # Compare the two historically repacked atlases; newly translated
        # portraits are audited separately by test_anteater_portrait_and_countdown.
        changed_all = changed_original_images(
            create_manifest(previous, self.patched), self.vanilla)
        repacked = ["images/fileselect_cursor-sheet0.webp",
                    "images/maps_sprite-sheet0.webp"]
        self.assertTrue(set(repacked).issubset(changed_all))
        changed = repacked
        self.assertTrue(unchanged_atlas_frames(previous, self.vanilla, changed))
        base = atlas_frame_pixels(previous, changed)
        self.assertTrue(base)
        damaged = copy.copy(base)
        key = next(iter(damaged))
        size, pixels, attributes = damaged[key]
        damaged[key] = (size, bytes([pixels[0] ^ 255]) + pixels[1:], attributes)
        with patch("resource_manifest.atlas_frame_pixels", side_effect=[base, damaged]):
            self.assertFalse(unchanged_atlas_frames(previous, self.vanilla, changed))

    def test_countdown_short_phrases_are_audited(self):
        entries, _, start = read_directory(self.vanilla)
        runtime = next(row for row in entries if row["name"] == "scripts/c3runtime.js")
        with open(self.vanilla, "rb") as source:
            source.seek(start + runtime["offset"])
            text = source.read(runtime["size"]).decode("utf-8")
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        self.assertNotIn("Ready...", natural_event_misses(text, translator(dictionary)))
        self.assertNotIn("Set...", natural_event_misses(text, translator(dictionary)))
        dictionary.pop("Ready...")
        dictionary.pop("Set...")
        misses = natural_event_misses(text, translator(dictionary))
        self.assertIn("Ready...", misses)
        self.assertIn("Set...", misses)

    def test_all_dialogue_speaker_nameplates(self):
        """Every named portrait has translated ink; anonymous art is intact."""
        image = "images/dialoguebox-sheet0.webp"
        original = atlas_frame_pixels(self.vanilla, {image})
        localized = atlas_frame_pixels(self.patched, {image})
        self.assertEqual(set(original), set(localized))
        entries, _, start = read_directory(self.vanilla)
        data = next(item for item in entries if item["name"] == "data.json")
        with open(self.vanilla, "rb") as source:
            source.seek(start + data["offset"])
            project = json.loads(source.read(data["size"]))["project"]
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        names = dialogue_speaker_names(project, dictionary)
        self.assertEqual(len(names), 71)
        changed_keys = {key for key in original if original[key] != localized[key]}
        named_keys = {key for key in original
                      if key[1] == "DialogueBox" and key[2] in names}
        self.assertEqual(changed_keys, named_keys)
        for key in sorted(named_keys):
            (size, old_pixels, attributes) = original[key]
            (new_size, new_pixels, new_attributes) = localized[key]
            self.assertEqual((new_size, new_attributes), (size, attributes))
            before = Image.frombytes("RGBA", size, old_pixels)
            after = Image.frombytes("RGBA", size, new_pixels)
            end = 12
            while before.getpixel((end, 7)) == (219, 207, 181, 255):
                end += 1
            width = end - 12
            self.assertLessEqual(len(names[key[2]]) * 7, width)
            changed = [(x, y) for y in range(size[1]) for x in range(size[0])
                       if before.getpixel((x, y)) != after.getpixel((x, y))]
            self.assertTrue(changed, key)
            self.assertTrue(all(12 <= x < end and 9 <= y < 16
                                for x, y in changed), key)
            self.assertTrue(any(after.getpixel((x, y)) == (219, 207, 181, 255)
                                for y in range(9, 16) for x in range(12, end)), key)

    def test_bughouse_countdown_still_translates(self):
        entries, _, start = read_directory(self.patched)
        runtime = next(item for item in entries if item["name"] == "scripts/c3runtime.js")
        with open(self.patched, "rb") as fh:
            fh.seek(start + runtime["offset"])
            text = fh.read(runtime["size"]).decode("utf-8")
        for source, target in (("Ready...", "准备……"), ("Set...", "预备……"),
                               ("Go!!!", "开始！！！")):
            self.assertIn(json.dumps(source, ensure_ascii=False) + ":" +
                          json.dumps(target, ensure_ascii=False), text)

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

    def test_september_27_new_building_and_preserved_art(self):
        """The new crypt map and building icon survive repainted text."""
        names = {"images/buildmenu_pages-sheet0.webp",
                 "images/buildmenu_pages-sheet1.webp",
                 "images/maps_sprite-sheet0.webp",
                 "images/shared-4-sheet1.webp",
                 "images/shared-9-sheet6.webp"}
        original = atlas_frame_pixels(self.vanilla, names)
        localized = atlas_frame_pixels(self.patched, names)
        self.assertEqual(set(original), set(localized))

        def images(name, obj, animation):
            key = next(key for key in original if key[0] == name
                       and key[1] == obj and key[2] == animation)
            before, after = original[key], localized[key]
            self.assertEqual(before[0], after[0])
            self.assertEqual(before[2], after[2])
            return (Image.frombytes("RGBA", before[0], before[1]),
                    Image.frombytes("RGBA", after[0], after[1]))

        old, new = images("images/buildmenu_pages-sheet1.webp",
                          "BuildMenu_Pages", "1")
        self.assertNotEqual(old.crop((24, 112, 144, 120)).tobytes(),
                            new.crop((24, 112, 144, 120)).tobytes())
        ink, paper = (7, 24, 33, 255), (219, 207, 181, 255)
        for character in range(4):
            self.assertTrue(any(new.getpixel((x, y)) == ink
                                for x in range(24 + 8 * character, 32 + 8 * character)
                                for y in range(112, 120)), character)
        for y in range(112, 120):
            for x in range(56, 144):
                self.assertEqual(new.getpixel((x, y)), paper)
        self.assertEqual(old.crop((0, 120, 160, 144)).tobytes(),
                         new.crop((0, 120, 160, 144)).tobytes())
        for animation, regions in (
            ("Details_Hollow", [(24, 64, 56, 72), (88, 64, 120, 72)]),
            ("Destroy_Hollow", [(24, 64, 56, 72)]),
        ):
            old, new = images("images/buildmenu_pages-sheet0.webp",
                              "BuildMenu_Pages", animation)
            self.assertEqual(old.crop((0, 0, 48, 56)).tobytes(),
                             new.crop((0, 0, 48, 56)).tobytes())
            for region in regions:
                self.assertNotEqual(old.crop(region).tobytes(),
                                    new.crop(region).tobytes())
        for name, obj, animation in (
            ("images/maps_sprite-sheet0.webp", "Maps_Sprite", "DungeonCrypt_HasMap1"),
            ("images/shared-9-sheet6.webp", "FileSelectSwipe", "Animation 1"),
        ):
            old, new = images(name, obj, animation)
            self.assertEqual(old.tobytes(), new.tobytes(), animation)
        old, new = images("images/shared-4-sheet1.webp",
                          "BuildMenu_BuildPrompt", "DetailsClosed")
        self.assertEqual(old.crop((40, 0, 112, 16)).tobytes(),
                         new.crop((40, 0, 112, 16)).tobytes())

    def test_official_update_dialogue_coverage(self):
        runtime = read_entry(self.vanilla, "scripts/c3runtime.js").decode("utf-8")
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        for text in ("Hero's Hollow", "HERO'S HOLLOW",
                     "Have you been to Strya's Bazaar? It's just over there, near the big tree.",
                     "I don't sense a Reverie in this dungeon...",
                     "Lief's jump slash has been powered up!"):
            self.assertIn(text, runtime)
            self.assertIn(text, dictionary)
            self.assertTrue(any("\u4e00" <= c <= "\u9fff" for c in dictionary[text]))
        self.assertEqual(natural_event_misses(runtime, translator(dictionary)), [])
        patched_runtime = read_entry(self.patched, "scripts/c3runtime.js").decode("utf-8")
        for text in ("Hero's Hollow", "HERO'S HOLLOW",
                     "Have you been to Strya's Bazaar? It's just over there, near the big tree.",
                     "I don't sense a Reverie in this dungeon...",
                     "Lief's jump slash has been powered up!"):
            pair = (json.dumps(text, ensure_ascii=False) + ":" +
                    json.dumps(dictionary[text], ensure_ascii=False))
            self.assertIn(pair, patched_runtime)

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

        # Build-menu destinations share the same warp background. Their sprite
        # origin sits 8px left of the regular rows; all must hide the gray ???.
        for anim, text in HIDDEN_NAMES.items():
            hidden = frame("BuildMenu_HiddenText", anim)
            self.assertEqual(hidden.size, (160, 8))
            for y in range(8):
                for x in range(8):
                    self.assertEqual(hidden.getpixel((x, y))[3], 0, anim)
                for x in range(8, 32):
                    self.assertEqual(hidden.getpixel((x, y))[3], 255,
                                     (anim, x, y))
                for x in range(8 + max(24, 8 * len(text)), hidden.width):
                    self.assertEqual(hidden.getpixel((x, y))[3], 0,
                                     (anim, x, y))
            self.assertTrue(all(any(hidden.getpixel((x, y))[:3] == (7, 24, 33)
                                for x in range(8 + 8 * i, 16 + 8 * i)
                                for y in range(8))
                            for i in range(len(text))), anim)
        self.assertNotEqual(frame("BuildMenu_HiddenText", "Windmill1").tobytes(),
                            frame("BuildMenu_HiddenText", "Windmill2").tobytes())


if __name__ == "__main__":
    unittest.main()
