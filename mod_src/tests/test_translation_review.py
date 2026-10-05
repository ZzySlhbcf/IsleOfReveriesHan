"""Regression checks for translator-approved dialogue and controls captions."""
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mod_src/tools"))
from audit_localization import read_entry
from bdf import Bdf
from verify_glyphs import canon


class TranslationReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.environ.get("CN_VANILLA_BUNDLE")
        cls.bundle = os.environ.get("CN_PATCH_BUNDLE") or str(ROOT / "www/assets.dat")
        if not cls.base or not Path(cls.base).is_file():
            raise unittest.SkipTest("Set CN_VANILLA_BUNDLE to the reviewed English game bundle")

    def test_reviewed_dialogue_is_in_dictionary_and_runtime(self):
        expected = json.loads(Path(__file__).with_name("translation_review_expected.json").read_text("utf-8"))
        dictionary = json.loads((ROOT / "mod_src/trans/dict.json").read_text("utf-8"))
        runtime = read_entry(self.bundle, "scripts/c3runtime.js").decode("utf-8")
        for row in expected:
            with self.subTest(review_id=row["id"]):
                self.assertEqual(dictionary[row["en"]], row["after"])
                self.assertIn(json.dumps(row["en"], ensure_ascii=False) + ":" +
                              json.dumps(row["after"], ensure_ascii=False), runtime)
                if row["review_status"] == "待上下文复核":
                    self.assertIn("兄弟", row["after"])
                    self.assertNotIn("哥哥", row["after"])
                    self.assertNotIn("弟弟", row["after"])
        self.assertEqual(dictionary["Pin: Petal"], "标记：女神花瓣")
        self.assertEqual(dictionary["Pin: X"], "标记：X")

    def test_save_summary_rows_do_not_overlap(self):
        from layout_nudge import adjust_save_summary
        original = json.loads(read_entry(self.base, "data.json"))["project"]
        self.assertEqual(len(adjust_save_summary(original)), 4)
        self.assertEqual(adjust_save_summary(original), [])
        project = json.loads(read_entry(self.bundle, "data.json"))["project"]
        tid = next(i for i, obj in enumerate(project[3])
                   if isinstance(obj, list) and obj and obj[0] == "TitleTexts")
        rows = []
        for layout in project[5]:
            if layout[0] != "Title Screen":
                continue
            for container in layout[10:]:
                if not isinstance(container, list):
                    continue
                for layer in container:
                    if not (isinstance(layer, list) and len(layer) > 14
                            and layer[0] == "LoadLayer" and isinstance(layer[14], list)):
                        continue
                    rows.extend(inst[0] for inst in layer[14]
                                if isinstance(inst, list) and inst[1] == tid)
        self.assertEqual(sorted(row[1] for row in rows), [48, 62, 96, 110])
        self.assertTrue(all(row[4] >= 11 for row in rows))
        self.assertTrue(all(row[1] + 11 <= 144 for row in rows))

    def test_description_gap_ignores_other_layers_and_single_row_names(self):
        template = (ROOT / "mod_src/tools/cn_runtime_template.js").read_text("utf-8")
        values = {"DICT": {}, "DICT_CI": {}, "CN_CHARS": "", "CHARSET_MAP": {},
                  "TYPE_CELL": {"ItemDescription": [9, 10]},
                  "TYPE_CHARSET": {}, "TYPE_SPACING": {}, "GAP_NUDGE": 2,
                  "GAP_TYPES": ["ItemDescription"]}
        for key, value in values.items():
            template = template.replace("__" + key + "__", json.dumps(value))
        harness = r"""
const assert = require('node:assert/strict');
global.self = global;
global.setInterval = () => 1;
const layerA = {}, layerB = {};
let instances = [];
const objectClass = {GetName: () => 'ItemDescription', GetInstances: () => instances};
const runtime = {GetObjectClassByName: () => objectClass};
class Instance { _SetText() {} }
global.C3 = {Plugins: {Spritefont2: {Instance}}};
function box(y, height, layer) {
  const inst = new Instance();
  inst._runtime = runtime;
  const world = {GetY: () => y, SetY: value => {y = value},
    GetHeight: () => height, GetWidth: () => 112, GetX: () => 72,
    IsVisible: () => true, GetLayer: () => layer};
  inst.GetWorldInfo = () => world;
  inst.GetObjectClass = () => objectClass;
  return inst;
}
"""
        checks = r"""
// The old sweep pushed a quest title because a different menu's
// 40px notebook text ended at the same coordinate.
const foreign = box(72, 40, layerB);
const name = box(112, 8, layerA);
const description = box(120, 24, layerA);
instances = [foreign, name, description];
description._SetText('a');
assert.equal(name.GetWorldInfo().GetY(), 112);
assert.equal(description.GetWorldInfo().GetY(), 122);
description._SetText('b');
assert.equal(description.GetWorldInfo().GetY(), 122);
// No cross-layer pair can create an artificial description offset.
const otherName = box(0, 8, layerB);
const otherDescription = box(8, 24, layerA);
instances = [otherName, otherDescription];
otherDescription._SetText('c');
assert.equal(otherDescription.GetWorldInfo().GetY(), 8);
console.log('Gap geometry regression passed');
"""
        result = subprocess.run(["node", "-e", harness + template + checks],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_controls_captions_and_preserved_input_glyphs(self):
        path = "images/controlsbg-sheet0.webp"
        image = Image.open(io.BytesIO(read_entry(self.bundle, path))).convert("RGBA")
        vanilla = Image.open(io.BytesIO(read_entry(self.base, path))).convert("RGBA")
        # Key labels use the original dark ASCII cells, not new white CJK glyphs.
        project = json.loads(read_entry(self.bundle, "data.json"))["project"]
        base_project = json.loads(read_entry(self.base, "data.json"))["project"]
        key_type = next(x for x in project[3] if x[0] == "ControlsMenu_Keyboard")
        base_type = next(x for x in base_project[3] if x[0] == "ControlsMenu_Keyboard")
        spec = base_type[6]
        atlas = Image.open(io.BytesIO(read_entry(self.base, spec[0]))).convert("RGBA")
        sheet = Image.open(io.BytesIO(read_entry(self.bundle, key_type[6][0]))).convert("RGBA")
        charset = next(inst[5][4] for lay in base_project[5] for layer in lay[10]
                       for inst in layer[14] if inst[1] == base_project[3].index(base_type))
        for character in "SPA":
            index = charset.index(character)
            x, y = (index % (spec[4] // 8)) * 8, (index // (spec[4] // 8)) * 8
            cell = sheet.crop((x, y, x+8, y+8))
            self.assertEqual(cell.tobytes(), atlas.crop((spec[2]+x, spec[3]+y,
                                                       spec[2]+x+8, spec[3]+y+8)).tobytes())
            self.assertTrue(any(pixel == (7, 24, 33, 255) for pixel in cell.getdata()))
            self.assertFalse(any(pixel == (255, 255, 255, 255) for pixel in cell.getdata()))
        self.assertEqual(json.loads((ROOT / "mod_src/trans/dict.json").read_text("utf-8"))["SPC"], "SPA")
        # Movement input cells are independent of the translated ARROWS label.
        self.assertEqual(image.crop((120, 15, 160, 25)).tobytes(),
                         vanilla.crop((120, 15, 160, 25)).tobytes())
        font = Bdf(str(ROOT / "mod_src/fonts/fusion-pixel-8px-monospaced-zh_hans.bdf"))
        # Decode directly from the font reference, not the image repaint helper.
        for text, x, y in [("键盘", 168, 44), ("方向键", 162, 16)]:
            for i, ch in enumerate(text):
                with self.subTest(caption=text, character=ch):
                    reference = canon(font, ch, (8, 8), base_ref=5).astype(bool)
                    tile = np.array(image.crop((x + i*8, y, x + (i+1)*8, y+8)))
                    actual = np.all(tile == [7, 24, 33, 255], axis=2)
                    self.assertTrue(np.array_equal(actual, reference))


if __name__ == "__main__":
    unittest.main()
