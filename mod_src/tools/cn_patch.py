#!/usr/bin/env python3
"""Apply the CN font sheet + charset patch to an extracted data.json (dev copy)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CELL = (8, 8)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(d, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))


def font_types(project):
    return {i: ot for i, ot in enumerate(project[3])
            if isinstance(ot, list) and ot[1] == 14}


def iter_font_instances(project):
    """Yield (layout, state-array) for every sprite font instance."""
    for lay in project[5]:
        if not isinstance(lay, list) or len(lay) < 11 or not isinstance(lay[10], list):
            continue
        for layer in lay[10]:
            if not isinstance(layer, list) or len(layer) < 15 or not isinstance(layer[14], list):
                continue
            for inst in layer[14]:
                if not isinstance(inst, list) or len(inst) < 6:
                    continue
                for cand in inst[3:]:
                    if (isinstance(cand, list) and len(cand) >= 13
                            and isinstance(cand[0], str) and isinstance(cand[2], int)
                            and isinstance(cand[3], int) and isinstance(cand[4], str)
                            and len(cand[4]) > 40):
                        yield lay[0], cand
                        break
