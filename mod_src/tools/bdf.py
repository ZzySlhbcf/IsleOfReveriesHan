#!/usr/bin/env python3
"""Tiny BDF bitmap-font reader + text renderer for 8px pixel CJK fonts."""
import re


class Bdf:
    def __init__(self, path):
        self.glyphs = {}          # codepoint -> (w, h, xoff, yoff, [row bitmasks])
        self.font_bbx = None
        cur = None
        rows = None
        state = None
        with open(path, "r", encoding="latin-1") as f:
            for line in f:
                line = line.strip()
                if line.startswith("FONTBOUNDINGBOX"):
                    self.font_bbx = tuple(int(x) for x in line.split()[1:])
                elif line.startswith("STARTCHAR"):
                    cur = {"name": line[9:], "enc": None, "bbx": None, "rows": []}
                    state = "char"
                elif line.startswith("ENCODING") and cur is not None:
                    cur["enc"] = int(line.split()[1])
                elif line.startswith("BBX") and cur is not None:
                    cur["bbx"] = tuple(int(x) for x in line.split()[1:])
                elif line == "BITMAP":
                    state = "bitmap"
                elif line == "ENDCHAR":
                    if cur is not None and cur["enc"] is not None and cur["enc"] >= 0:
                        self.glyphs[cur["enc"]] = (cur["bbx"], cur["rows"])
                    cur = None
                    state = None
                elif state == "bitmap" and re.fullmatch(r"[0-9A-Fa-f]+", line or ""):
                    cur["rows"].append(int(line, 16))

    def get(self, ch):
        return self.glyphs.get(ord(ch))

    def rows_to_bits(self, ch):
        """Yield (x, y) pixel offsets set for a glyph, in a top-left origin box."""
        g = self.glyphs.get(ord(ch))
        if not g:
            return None
        (bw, bh, xoff, yoff), rows = g
        nb = (bw + 7) // 8
        out = []
        for r, val in enumerate(rows):
            for b in range(bw):
                bit = (val >> (8 * nb - 1 - b)) & 1
                if bit:
                    # BDF y increases upward from baseline; convert to top-down
                    out.append((xoff + b, yoff + (bh - 1 - r)))
        return out, (bw, bh, xoff, yoff)


def render_text(bdf, lines, cell=(8, 8), scale=4, bg=(20, 20, 24), fg=(240, 240, 230),
                line_gap=0, path=None):
    from PIL import Image
    gw, gh = cell
    widths = []
    for ln in lines:
        widths.append(sum(1 for _ in ln))
    W = max(widths) * gw * scale
    H = len(lines) * (gh + line_gap) * scale
    im = Image.new("RGB", (max(W, 1), max(H, 1)), bg)
    px = im.load()
    for li, ln in enumerate(lines):
        for ci, ch in enumerate(ln):
            bits = bdf.rows_to_bits(ch)
            if not bits:
                continue
            pts, (bw, bh, xoff, yoff) = bits
            for (x, y) in pts:
                # glyph box origin: place inside the cell, baseline at bottom of cell
                gx = ci * gw + x
                gy = li * (gh + line_gap) + (gh - 1 - (bh + yoff - 1) - 1) + 1
                for sy in range(scale):
                    for sx in range(scale):
                        X, Y = (gx * scale + sx), (gy * scale + sy)
                        if 0 <= X < im.width and 0 <= Y < im.height:
                            px[X, Y] = fg
    if path:
        im.save(path)
    return im


if __name__ == "__main__":
    import sys
    b = Bdf(sys.argv[1] if len(sys.argv) > 1 else
            "fonts/fusion-pixel-8px-monospaced-zh_hans.bdf")
    print("glyphs:", len(b.glyphs), "font bbx:", b.font_bbx)
    sample = sys.argv[2] if len(sys.argv) > 2 else "幻想之岛"
    for ch in sample:
        print(ch, b.rows_to_bits(ch)[1] if b.rows_to_bits(ch) else "MISSING")
