#!/usr/bin/env python3
"""Build extended SpriteFont glyph sheets for the Isle of Reveries CN patch.

The game renders text with Construct 3's "Spritefont2" plugin: each font object
type points at a 128x112 rectangle inside a texture atlas that is interpreted as
a grid of (charW x charH) cells (8x8 here).  The instance's "character set"
string maps charset[i] -> cell i (row-major, cols = rectWidth / charW).

To add Chinese glyphs we therefore:
  * keep the vanilla sheet pixel-for-pixel at the top of a new, taller image,
  * write each new glyph into the cell at index len(base_charset) + i
    (cells after the vanilla charset are unused by the game),
  * append extra rows for the rest.
"""
import os
from PIL import Image

from bdf import Bdf


def _blit(px, pts, minx, maxx, miny, maxy, cx, cy, cw, ch, W, H, base_ref=None):
    """Paint a glyph's points into the sheet cell at (cx, cy).

    按“基线”对齐，而不是把每个字单独居中：汉字是满格高的，数字/字母矮一截，
    逐个居中会让不同行的字上下浮动，看起来“行距忽大忽小”。BDF 的 y=0 是基线，
    把基线固定在同一行（top + base_ref）即可。

    BDF y grows upward, the image's Y grows downward: Y = cy + (base_ref - gy).
    The offset must be constant for the whole font: centering each glyph's
    own ink height shifts short strokes such as 一 two pixels below the baseline.
    """
    gw = maxx - minx + 1
    gh = maxy - miny + 1
    left = cx + max(0, (cw - gw) // 2)
    ref = base_ref if base_ref is not None else maxy
    for (gx, gy) in pts:
        X = left + (gx - minx)
        Y = cy + (ref - gy)
        # 只写在本格内：字形比格子大时绝不能溢到邻格去
        if cx <= X < cx + cw and cy <= Y < cy + ch:
            px[X, Y] = (255, 255, 255, 255)


def build(atlas_path, rect, base_charset, extra_chars, bdf, out_path,
          cell=(8, 8), glyph_top=0, rerender_all=False, base_ref=None):
    x, y, w, h = rect
    cw, ch = cell
    cols = w // cw
    if rerender_all:
        # 整张表都用 bdf 重画（换字号时用；原 ASCII 位图与新的格子尺寸不兼容）
        count = len(base_charset) + len(extra_chars)
        rows = (count + cols - 1) // cols
        H = rows * ch
        out = Image.new("RGBA", (w, H), (0, 0, 0, 0))
        order = list(base_charset) + list(extra_chars)
        px = out.load()
        missing = []
        for i, c in enumerate(order):
            got = bdf.rows_to_bits(c)
            if not got or not got[0]:
                if c not in " \n\t":
                    missing.append(c)
                continue
            pts = got[0]
            minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
            miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
            _blit(px, pts, minx, maxx, miny, maxy, (i % cols) * cw, (i // cols) * ch,
                  cw, ch, w, H, base_ref)
        out.save(out_path, "WEBP", lossless=True, quality=100, method=4)
        return dict(cells=count, cols=cols, height=H, missing=missing,
                    charmap={c: i for i, c in enumerate(order)})

    atlas = Image.open(atlas_path).convert("RGBA")
    sheet = atlas.crop((x, y, x + w, y + h))

    start = len(base_charset)
    total_cells = start + len(extra_chars)
    rows = (total_cells + cols - 1) // cols
    H = max(h, rows * ch)
    out = Image.new("RGBA", (w, H), (0, 0, 0, 0))
    out.paste(sheet, (0, 0))

    px = out.load()
    missing = []
    for i, ch_ in enumerate(extra_chars):
        idx = start + i
        cx = (idx % cols) * cw
        cy = (idx // cols) * ch
        # 先清空目标格子：原图集在未使用格子里可能残留别的字形像素
        for yy in range(cy, min(cy + ch, H)):
            for xx in range(cx, cx + cw):
                px[xx, yy] = (0, 0, 0, 0)
        got = bdf.rows_to_bits(ch_)
        if not got or not got[0]:
            missing.append(ch_)
            continue
        pts = got[0]
        minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
        miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
        _blit(px, pts, minx, maxx, miny, maxy, cx, cy, cw, ch, w, H, base_ref)
    out.save(out_path, "WEBP", lossless=True, quality=100, method=4)
    return dict(cells=total_cells, cols=cols, height=H, missing=missing,
                charmap={c: start + i for i, c in enumerate(extra_chars)})


def batch(bdf_path, tasks):
    bdf = Bdf(bdf_path)
    for t in tasks:
        info = build(t["atlas"], t["rect"], t["charset"], t["extra"], bdf, t["out"])
        print(f"{os.path.basename(t['out'])}: {info['cells']} cells, {info['cols']} cols, "
              f"h={info['height']}, missing={len(info['missing'])}")
        if info["missing"]:
            print("   missing:", "".join(info["missing"])[:80])


if __name__ == "__main__":
    import json
    import sys
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    batch(spec["bdf"], spec["tasks"])
