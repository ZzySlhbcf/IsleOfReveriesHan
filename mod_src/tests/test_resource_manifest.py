"""Regression checks for the release inventory and update guard."""
import json
import io
import os
import sys
import unittest
from collections import Counter

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mod_src", "tools"))

from resource_manifest import (EXPECTED_CHANGED, IMAGE_LABELS,  # noqa: E402
                               changed_original_images, create_manifest,
                               atlas_frame_pixels, unchanged_atlas_frames,
                               atlas_frames_match_delta, bundle_md5, bundle_entries)
from c3bundle import read_directory  # noqa: E402
from audit_localization import (read_entry, natural_event_misses, translator,
                                ARROW_LITERAL, decode_js_string)  # noqa: E402
from patch_baked_menus import (dialogue_speaker_names, HIDDEN_NAMES,
                               MAP_PIN_NAMES, MAP_SAVE_LABEL, draw_text, FONT, PAPER)  # noqa: E402
from bdf import Bdf  # noqa: E402
from build_cn_patch import CELL_BY_TYPE, charsets_of, FALLBACK  # noqa: E402


def historical_vanilla(expected_md5):
    """Find preserved official bundles for tests of historical update deltas."""
    previous = os.environ.get("CN_PREVIOUS_VANILLA_BUNDLE")
    if not previous:
        return None
    directory = os.path.dirname(previous)
    candidates = [previous] + [os.path.join(directory, name)
                               for name in reversed(sorted(os.listdir(directory)))
                               if name.startswith("assets.dat.cn-backup")]
    return next((path for path in dict.fromkeys(candidates)
                 if os.path.isfile(path) and bundle_md5(path) == expected_md5), None)


class ManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vanilla = os.environ.get("CN_VANILLA_BUNDLE")
        cls.patched = os.environ.get("CN_PATCH_BUNDLE") or os.path.join(ROOT, "www", "assets.dat")
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
        old_images = bundle_entries(previous, IMAGE_LABELS)
        current_images = bundle_entries(self.vanilla, IMAGE_LABELS)
        changed_all = [name for name in old_images.keys() & current_images.keys()
                       if old_images[name] != current_images[name]]
        changed = [name for name in changed_all
                   if unchanged_atlas_frames(previous, self.vanilla, {name})]
        self.assertTrue(changed, "Update should include at least one unchanged repacked atlas")
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
        old, new = images("images/maps_sprite-sheet0.webp",
                          "Maps_Sprite", "DungeonCrypt_HasMap1")
        self.assertEqual(old.tobytes(), new.tobytes())
        old, new = images("images/shared-4-sheet1.webp",
                          "BuildMenu_BuildPrompt", "DetailsClosed")
        self.assertEqual(old.crop((40, 0, 112, 16)).tobytes(),
                         new.crop((40, 0, 112, 16)).tobytes())

    def test_september_28_dialogue_and_removed_transition(self):
        runtime = read_entry(self.vanilla, "scripts/c3runtime.js").decode("utf-8")
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        additions = (
            "'It seems this is my only path to reach the great desert on a plateau.'",
            "Further north is a shrine built into a huge tree. Is that where you're headed?",
            "How do I know that? Because you can't swim! And neither can I...",
            "Hoy, Lief! So your travels have brought you to the desert, eh?",
            "I'll be heading through the Snowcloaked Summit in the northeast.",
            "I've gotta get me one of those!", "North: Overgrown Shrine.",
            "That's what's north of us, but you can't get through this way.",
            "What? You magically learned how to swim!?",
            "You'll have to find another way around.",
        )
        localized = read_entry(self.patched, "scripts/c3runtime.js").decode("utf-8")
        for text in additions:
            self.assertIn(text, runtime)
            self.assertTrue(any("\u4e00" <= c <= "\u9fff"
                                for c in dictionary[text]), text)
            self.assertIn(json.dumps(text, ensure_ascii=False) + ":" +
                          json.dumps(dictionary[text], ensure_ascii=False), localized)
        self.assertEqual(natural_event_misses(runtime, translator(dictionary)), [])

        changed = {"images/dialoguebox-sheet0.webp",
                   "images/dungeon_title-sheet0.webp",
                   "images/fileselect_cursor-sheet0.webp",
                   "images/maps_sprite-sheet0.webp",
                   "images/shared-9-sheet6.webp"}
        before = os.environ.get("CN_PREVIOUS_VANILLA_BUNDLE")
        if (before and os.path.isfile(before)
                and bundle_md5(before) == "06e9ffd80556cef82791cc1a84d0557d"):
            old = atlas_frame_pixels(before, changed)
            current = atlas_frame_pixels(self.vanilla, changed)
            self.assertEqual(set(old) - set(current),
                             {("images/shared-9-sheet6.webp",
                               "FileSelectSwipe", "Animation 1", 0)})
            self.assertEqual(set(current) - set(old), set())
            self.assertEqual({k: old[k] for k in current}, current)
        vanilla_frames = atlas_frame_pixels(self.vanilla, changed)
        patched_frames = atlas_frame_pixels(self.patched, changed)
        self.assertEqual(set(vanilla_frames), set(patched_frames))
        self.assertNotIn(("images/shared-9-sheet6.webp",
                          "FileSelectSwipe", "Animation 1", 0), patched_frames)

    def test_september_30_mine_dialogue_and_anonymous_portrait(self):
        image = "images/dialoguebox-sheet0.webp"
        key = (image, "DialogueBox", "MineGhost", 0)
        original = atlas_frame_pixels(self.vanilla, {image})
        localized = atlas_frame_pixels(self.patched, {image})
        self.assertIn(key, original)
        self.assertEqual(original[key], localized[key])
        previous = historical_vanilla("1819ebb21f6d71f873c5d6ba73126642")
        morning = historical_vanilla("926fe43e69dae4fda2455ce5052e5a8c")
        if not previous or not morning:
            self.skipTest("Historical September 28/29 English bundles are unavailable")
        old_runtime = read_entry(previous, "scripts/c3runtime.js").decode("utf-8")
        runtime = read_entry(morning, "scripts/c3runtime.js").decode("utf-8")
        literal_values = lambda text: {
            decode_js_string(match.group(1)) for match in ARROW_LITERAL.finditer(text)
        }
        additions = literal_values(runtime) - literal_values(old_runtime)
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        translate = translator(dictionary)
        self.assertEqual({text for text in additions if translate(text) == text},
                         {"MineGhost"})  # This animation ID is game logic.
        self.assertEqual(len(additions), 26)  # 24 new lines, two animation IDs.
        patched_runtime = read_entry(self.patched, "scripts/c3runtime.js").decode("utf-8")
        for text in additions - {"MineGhost"}:
            self.assertIn(json.dumps(text, ensure_ascii=False) + ":" +
                          json.dumps(dictionary[text], ensure_ascii=False), patched_runtime)

    def test_reviewed_mine_portrait_delta_rejects_other_art_changes(self):
        import copy
        from unittest.mock import patch

        previous = historical_vanilla("1819ebb21f6d71f873c5d6ba73126642")
        morning = historical_vanilla("926fe43e69dae4fda2455ce5052e5a8c")
        if not previous or not morning:
            self.skipTest("Historical September 28/29 English bundles are unavailable")
        changed = {"images/buildmenu_pages-sheet0.webp",
                   "images/dialoguebox-sheet0.webp",
                   "images/dungeon_title-sheet0.webp",
                   "images/fileselect_cursor-sheet0.webp",
                   "images/maps_sprite-sheet0.webp"}
        added = {("images/dialoguebox-sheet0.webp", "DialogueBox", "MineGhost", 0)}
        self.assertFalse(unchanged_atlas_frames(previous, morning, changed))
        self.assertTrue(atlas_frames_match_delta(previous, morning, changed,
                                                added=added))
        before = atlas_frame_pixels(previous, changed)
        after = atlas_frame_pixels(morning, changed)
        damaged = copy.copy(after)
        key = next(iter(before))
        size, pixels, attrs = damaged[key]
        damaged[key] = (size, bytes([pixels[0] ^ 255]) + pixels[1:], attrs)
        with patch("resource_manifest.atlas_frame_pixels", side_effect=[before, damaged]):
            self.assertFalse(atlas_frames_match_delta(previous, morning, changed,
                                                     added=added))
        unexpected = copy.copy(after)
        unexpected[(key[0], key[1], "Unreviewed", 0)] = after[key]
        with patch("resource_manifest.atlas_frame_pixels", side_effect=[before, unexpected]):
            self.assertFalse(atlas_frames_match_delta(previous, morning, changed,
                                                     added=added))

    def test_september_30_afternoon_preserves_updated_map(self):
        atlas = "images/maps_sprite-sheet0.webp"
        original = atlas_frame_pixels(self.vanilla, {atlas})
        patched = atlas_frame_pixels(self.patched, {atlas})
        key = (atlas, "Maps_Sprite", "WorldMap_2", 0)
        size, pixels, attrs = original[key]
        new_size, new_pixels, new_attrs = patched[key]
        self.assertEqual((size, attrs), (new_size, new_attrs))
        old = Image.frombytes("RGBA", size, pixels)
        new = Image.frombytes("RGBA", new_size, new_pixels)
        # All official map cells survive; only the existing footer is repainted.
        self.assertEqual(old.crop((0, 0, 128, 136)).tobytes(),
                         new.crop((0, 0, 128, 136)).tobytes())
        self.assertNotEqual(old.crop((0, 136, 128, 144)).tobytes(),
                            new.crop((0, 136, 128, 144)).tobytes())
        renamed = (atlas, "Maps_Sprite", "Dungeon2_HasMap2", 0)
        self.assertIn(renamed, original)
        self.assertEqual(original[renamed], patched[renamed])
        # October 5 moves the official DungeonCrypt frame back to sheet 0.
        crypt = (atlas, "Maps_Sprite", "DungeonCrypt", 0)
        if crypt in original:
            self.assertEqual(original[crypt], patched[crypt])
        text = "Wow! Zelen marked locations of all unplanted Goddess Soil on Lief's map!"
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        self.assertIn(text, read_entry(self.vanilla, "scripts/c3runtime.js").decode("utf-8"))
        self.assertIn(json.dumps(text, ensure_ascii=False) + ":" +
                      json.dumps(dictionary[text], ensure_ascii=False),
                      read_entry(self.patched, "scripts/c3runtime.js").decode("utf-8"))

    def test_afternoon_map_guard_rejects_unreviewed_pixels_and_attributes(self):
        import copy
        from unittest.mock import patch

        previous = historical_vanilla("926fe43e69dae4fda2455ce5052e5a8c")
        afternoon = historical_vanilla("936aaed59f17c1b53eb5b1b2563a51aa")
        if not previous or not afternoon:
            self.skipTest("September 29 English bundle is unavailable")
        changed = {"images/buildmenu_pages-sheet0.webp",
                   "images/dialoguebox-sheet0.webp", "images/maps_sprite-sheet0.webp"}
        atlas = "images/maps_sprite-sheet0.webp"
        key = (atlas, "Maps_Sprite", "WorldMap_2", 0)
        policy = dict(removed={(atlas, "Maps_Sprite", "DungeonCrypt", 0)},
                      added={(atlas, "Maps_Sprite", "Dungeon2_HasMap2", 0)},
                      changed_regions={key: [(24, 16, 32, 24)]})
        self.assertFalse(atlas_frames_match_delta(previous, afternoon, changed))
        self.assertTrue(atlas_frames_match_delta(previous, afternoon, changed, **policy))
        before = atlas_frame_pixels(previous, changed)
        after = atlas_frame_pixels(afternoon, changed)
        damaged = copy.copy(after)
        size, pixels, attrs = damaged[key]
        # An unexpected footer change is outside the reviewed 8x8 room cell.
        offset = (136 * size[0] + 8) * 4
        damaged[key] = (size, pixels[:offset] + bytes([pixels[offset] ^ 255]) +
                        pixels[offset + 1:], attrs)
        with patch("resource_manifest.atlas_frame_pixels", side_effect=[before, damaged]):
            self.assertFalse(atlas_frames_match_delta(previous, afternoon, changed, **policy))
        damaged = copy.copy(after)
        damaged[key] = (size, pixels, attrs + ["unreviewed anchor"])
        with patch("resource_manifest.atlas_frame_pixels", side_effect=[before, damaged]):
            self.assertFalse(atlas_frames_match_delta(previous, afternoon, changed, **policy))

    def test_october_5_map_ui_preserves_art_and_all_animation_frames(self):
        names = {"images/shared-0-sheet0.webp", "images/shared-0-sheet1.webp",
                 "images/shared-9-sheet7.webp", "images/pinselect-sheet0.webp"}
        original = atlas_frame_pixels(self.vanilla, names)
        localized = atlas_frame_pixels(self.patched, names)
        self.assertEqual(original.keys(), localized.keys())
        expected = {}
        for key, (size, pixels, attrs) in original.items():
            obj, anim, number = key[1:]
            regions = []
            if obj == "NewMapOverview":
                regions = [(16, 136, 144, 144)]
            elif obj in ("NewMap_Legend", "WorldMapLegend"):
                rows = 11 if obj == "WorldMapLegend" else (10 if anim == "HasSoil" else 9)
                regions = [(8, 4, 56, 12), (16, 16, 60, 16 + rows * 8)]
            elif obj == "PinSelect":
                regions = [(4, 3, 52, 11)]
            elif obj in ("FindLief", "ZoomCancel"):
                regions = [(4, 7, 44, 14)]
            self.assertEqual((size, attrs), (localized[key][0], localized[key][2]), key)
            if not regions:
                self.assertEqual(original[key], localized[key], key)
                continue
            expected[key] = regions
            old = Image.frombytes("RGBA", size, pixels)
            new = Image.frombytes("RGBA", size, localized[key][1])
            for region in regions:
                self.assertNotEqual(old.crop(region).tobytes(), new.crop(region).tobytes(), key)
                self.assertTrue(any(new.getpixel((x, y)) == (7, 24, 33, 255)
                                    for y in range(region[1], region[3])
                                    for x in range(region[0], region[2])), key)
                old.paste((0, 0, 0, 0), region)
                new.paste((0, 0, 0, 0), region)
            self.assertEqual(old.tobytes(), new.tobytes(), key)
        self.assertEqual(len(expected), 20)
        counts = Counter(key[1] for key in expected)
        self.assertEqual(counts["PinSelect"], 12)
        self.assertEqual(counts["NewMapOverview"], 2)

    def test_october_5_new_terms_follow_existing_translation(self):
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        self.assertEqual(dictionary["Pin: Tablet"], "标记：" + dictionary["Tablet"])
        soil_context = dictionary["Wow! Zelen marked locations of all unplanted Goddess Soil on Lief's map!"]
        self.assertIn("女神土壤", soil_context)
        self.assertEqual(dictionary["Pin: Soil"], "标记：女神土壤")
        self.assertEqual(dictionary["Pin: Chest"], "标记：" +
                         dictionary["Opening Chest"].removeprefix("打开"))
        self.assertEqual(dictionary["Pin: Petal"], "标记：" +
                         dictionary["GODDESS PETALS"])
        self.assertEqual(MAP_SAVE_LABEL, "存档点")
        self.assertEqual(dictionary["Pin: X"], "标记：X")
        self.assertEqual(MAP_PIN_NAMES["Pin6"], "X")
        for pin, term in zip(range(1, 7), ("Star", "Petal", "Soil", "Tablet", "Chest", "X")):
            self.assertEqual("标记：" + MAP_PIN_NAMES[f"Pin{pin}"], dictionary[f"Pin: {term}"])
        # Check the shipped pixels, including both blinking frames per pin.
        frames = atlas_frame_pixels(self.patched, {"images/pinselect-sheet0.webp",
                                    "images/shared-0-sheet1.webp",
                                    "images/shared-9-sheet7.webp"})
        font = Bdf(FONT)
        checked = 0
        for key, (size, pixels, attrs) in frames.items():
            labels = []
            if key[1] == "PinSelect":
                labels = [(MAP_PIN_NAMES[key[2]], (4, 3, 48, 8), True)]
            elif key[1] == "WorldMapLegend":
                labels = [(MAP_SAVE_LABEL, (16, 16, 44, 8), False),
                          (MAP_PIN_NAMES["Pin3"], (16, 64, 44, 8), False),
                          (MAP_PIN_NAMES["Pin2"], (16, 72, 44, 8), False)]
            elif key[1] == "NewMap_Legend":
                labels = [(MAP_SAVE_LABEL, (16, 16, 44, 8), False)]
                if key[2] == "HasSoil":
                    labels.append((MAP_PIN_NAMES["Pin3"], (16, 56, 44, 8), False))
            actual = Image.frombytes("RGBA", size, pixels)
            for text, (x, y, w, h), centered in labels:
                expected = Image.new("RGBA", (w, h), PAPER)
                start = (w - len(text) * 8) // 2 if centered else 0
                draw_text(expected, font, text, start, 0, w - start)
                self.assertEqual(actual.crop((x, y, x + w, y + h)).tobytes(),
                                 expected.tobytes(), (key, text))
                checked += 1
        self.assertEqual(checked, 21)
        before = dictionary["The mine is labyrinthian and complex."]
        after = dictionary["The mine is labyrinthian and complex, to be sure."]
        self.assertEqual(after.replace("确实", ""), before)
        translate = translator(dictionary)
        for value in ("Pin1", "Pin2", "Pin3", "Pin4", "Pin5", "Pin6",
                      "FindLief", "ZoomCancel", "Soil_Hidden", "Tablet_CH_16"):
            self.assertEqual(translate(value), value)

    def test_october_5_dungeon_maps_survive_new_geometry(self):
        names = {"images/maps_sprite-sheet0.webp"}
        original = atlas_frame_pixels(self.vanilla, names)
        localized = atlas_frame_pixels(self.patched, names)
        dungeons = {key for key in original if key[1] == "Maps_Sprite"
                    and key[2].startswith("Dungeon")}
        self.assertEqual(len(dungeons), 34)
        for key in dungeons:
            self.assertEqual(original[key][0], (144, 96), key)
            self.assertEqual(original[key], localized[key], key)
        self.assertEqual(original[("images/maps_sprite-sheet0.webp",
                                   "Maps_Sprite", "Hidden", 0)],
                         localized[("images/maps_sprite-sheet0.webp",
                                    "Maps_Sprite", "Hidden", 0)])

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

    def test_all_font_sizes_share_baseline_without_clipping(self):
        """Check actual shipped cells against fixed BDF baseline coordinates."""
        vanilla = json.loads(read_entry(self.vanilla, "data.json"))["project"]
        patched = json.loads(read_entry(self.patched, "data.json"))["project"]
        with open(os.path.join(ROOT, "mod_src", "trans", "dict.json"),
                  encoding="utf-8") as source:
            dictionary = json.load(source)
        font_for_width = {
            8: Bdf(os.path.join(ROOT, "mod_src", "fonts",
                                "fusion-pixel-8px-monospaced-zh_hans.bdf")),
            9: Bdf(os.path.join(ROOT, "mod_src", "fonts",
                                "fusion-pixel-10px-monospaced-zh_hans.bdf")),
            11: Bdf(os.path.join(ROOT, "mod_src", "fonts",
                                 "fusion-pixel-12px-monospaced-zh_hans.bdf")),
        }
        chars = sorted({c for text in dictionary.values() for c in text
                        if ord(c) > 0x2000 and c not in FALLBACK
                        and all(font.get(c) for font in font_for_width.values())})
        self.assertIn("一", chars)
        counts = Counter(cs for i, obj in enumerate(vanilla[3])
                         if isinstance(obj, list) and obj[1] == 14
                         for cs in charsets_of(vanilla, i))
        common = counts.most_common(1)[0][0]
        names = {obj[0]: obj for obj in patched[3]
                 if isinstance(obj, list) and obj[1] == 14}
        self.assertEqual(len(names), 24)
        # BDF 8/10/12px: the stroke in 一 is at y=3/4/5 respectively.
        expected_rows = {8: 3, 9: 4, 11: 5}
        for i, old in enumerate(vanilla[3]):
            if not isinstance(old, list) or old[1] != 14:
                continue
            name = old[0]
            width, height = CELL_BY_TYPE.get(name, (8, 8))
            font = font_for_width[width]
            original_charsets = charsets_of(vanilla, i)
            base = max(original_charsets, key=len) if original_charsets else common
            image = Image.open(io.BytesIO(read_entry(self.patched, names[name][6][0])))
            columns = image.width // width
            index = len(base) + chars.index("一")
            x, y = (index % columns) * width, (index // columns) * height
            glyph = image.crop((x, y, x + width, y + height)).convert("RGBA")
            stroke_width = len({px for px, _ in font.rows_to_bits("一")[0]})
            left = (width - stroke_width) // 2
            self.assertEqual(glyph.getbbox(),
                             (left, expected_rows[width], left + stroke_width,
                              expected_rows[width] + 1), name)
            # All font glyphs used by the translation fit at this fixed baseline.
            baseline = {8: 5, 9: 7, 11: 8}[width]
            for char in chars:
                points = font.rows_to_bits(char)[0]
                self.assertTrue(all(0 <= baseline - gy < height for _, gy in points),
                                (name, char))

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
