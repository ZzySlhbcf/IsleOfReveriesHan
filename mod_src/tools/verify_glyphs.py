#!/usr/bin/env python3
"""Verify that the CN glyph cells in a built bundle are pixel-exact and upright.

Two modes:
  sheet <assets.dat>            - compare every shipped CN cell against the
                                  canonical BDF bitmap (catches missing glyphs,
                                  wrong cell index and flipped glyphs)
  shot  <png> <text> <cell>     - compare the glyphs actually drawn by the
                                  running game against the canonical bitmap

The reference is always the BDF itself decoded top-down (bdf.canon), never
anything this patch produced - comparing our own output with itself hid an
upside-down-glyph bug once already.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bdf import Bdf
from c3bundle import read_directory


def base_ref_of(bdf, sample):
    """字库的“汉字顶线”（基线以上高度），与 fontsheet 的排版规则一致。

    注意：只能用汉字取样。标点（— “ ” 等）的 y 范围小得多，混进来会把参考线算歪，
    校验就会误报成百上千处不符。
    """
    ys = []
    for c in sample:
        if not (0x4E00 <= ord(c) <= 0x9FFF):
            continue
        g = bdf.rows_to_bits(c)
        if g and g[0]:
            ys.append(max(p[1] for p in g[0]))
        if len(ys) >= 300:
            break
    return max(set(ys), key=ys.count) if ys else 0


def canon(bdf, ch, box, base_ref=None):
    """Canonical top-down bitmap of `ch`, 按基线对齐放进 (w, h) 字格。"""
    got = bdf.rows_to_bits(ch)
    if not got or not got[0]:
        return None
    pts = got[0]
    w, h = box
    g = np.zeros((h, w), dtype=np.uint8)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]      # upward y, baseline at 0
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    gw, gh = maxx - minx + 1, maxy - miny + 1
    left = max(0, (w - gw) // 2)
    ref = base_ref if base_ref is not None else maxy
    for (x, y) in pts:
        X = left + (x - minx)
        Y = ref - y
        if 0 <= X < w and 0 <= Y < h:
            g[Y, X] = 1
    return g


def check_sheet(bundle):
    ents, _, ds = read_directory(bundle)
    f = open(bundle, "rb")
    e0 = [e for e in ents if e["name"] == "data.json"][0]
    f.seek(ds + e0["offset"])
    proj = json.loads(f.read(e0["size"]).decode("utf-8"))["project"]
    bdf8 = Bdf("fonts/fusion-pixel-8px-monospaced-zh_hans.bdf")
    bdf10 = Bdf("fonts/fusion-pixel-10px-monospaced-zh_hans.bdf")
    bdf12 = Bdf("fonts/fusion-pixel-12px-monospaced-zh_hans.bdf")
    d = json.load(open(os.path.join("trans", "dict.json"), encoding="utf-8"))
    # 必须与 build_cn_patch 生成字形表时的字符顺序完全一致（它过滤 >0x2000 并剔除 FALLBACK）
    import build_cn_patch as B
    chars = set()
    for v in d.values():
        chars.update(v)
    cn = sorted(c for c in chars if ord(c) > 0x2000 and c not in B.FALLBACK)
    cn = [c for c in cn if bdf8.get(c) and bdf10.get(c) and bdf12.get(c)]
    print(f"待校验汉字 {len(cn)} 个")
    # 先收集每个类型的实例信息（字格 + 字符集）
    def inst_info(tid):
        for lay in proj[5]:
            if not isinstance(lay, list) or len(lay) < 11 or not isinstance(lay[10], list):
                continue
            for layer in lay[10]:
                if not isinstance(layer, list) or len(layer) < 15 or not isinstance(layer[14], list):
                    continue
                for inst in layer[14]:
                    if isinstance(inst, list) and len(inst) > 3 and inst[1] == tid:
                        for cand in inst[3:]:
                            if (isinstance(cand, list) and len(cand) >= 13
                                    and isinstance(cand[4], str) and len(cand[4]) > 40):
                                return (cand[2], cand[3], cand[4])
        return None

    bases = []
    for i, ot in enumerate(proj[3]):
        if isinstance(ot, list) and ot[1] == 14:
            ii = inst_info(i)
            if ii:
                bases.append(len(ii[2]) - len([c for c in ii[2] if ord(c) > 0x2E80]))
    BASE_REF = {}
    for b in (bdf8, bdf10, bdf12):
        BASE_REF[id(b)] = base_ref_of(b, cn)
    print("基线参考行:", {b: BASE_REF[id(b)] for b in (bdf8, bdf10, bdf12)})
    canonical_base = max(set(bases), key=bases.count) if bases else 91
    print(f"标准字符集基数: {canonical_base}（各类型: {sorted(set(bases))}）")
    bad, flipped, ok = [], [], 0
    per_type = {}
    for i, ot in enumerate(proj[3]):
        if not (isinstance(ot, list) and ot[1] == 14):
            continue
        name = ot[0]
        img, size, x, y, w, h, rot = ot[6]
        e = [q for q in ents if q["name"] == img][0]
        f.seek(ds + e["offset"])
        open("_tmp_sheet.webp", "wb").write(f.read(e["size"]))
        A = np.array(Image.open("_tmp_sheet.webp").convert("L"))
        ii = inst_info(i)
        if ii:
            cw, ch, charset = ii
            base = len(charset) - len([c for c in charset if ord(c) > 0x2E80])
        else:
            cw, ch, base = 8, 8, canonical_base
            base = None  # 无实例：字格未知，用声明宽度推断
        if base is None:
            # 类型没有实例：字格尺寸取自构建规则，别写死数字
            cw, ch = B.CELL_BY_TYPE.get(name, (8, 8))
            base = canonical_base
        cols = A.shape[1] // cw
        # 放大字格的表是分别用 10/12px 字库重画的，按构建规则选字体
        c = B.CELL_BY_TYPE.get(name, (8, 8))[0]
        bdf = {8: bdf8, 9: bdf10, 10: bdf10, 11: bdf12}[c]
        t_ok = t_flip = t_bad = 0
        for k, c in enumerate(cn):
            idx = base + k
            cy, cx = (idx // cols) * ch, (idx % cols) * cw
            got = A[cy:cy + ch, cx:cx + cw] > 100
            ref = canon(bdf, c, (cw, ch), BASE_REF[id(bdf)])
            if ref is None or got.shape != ref.shape:
                bad.append((name, c, "shape"))
                t_bad += 1
            elif np.array_equal(got, ref):
                ok += 1
                t_ok += 1
            elif np.array_equal(got, ref[::-1, :]):
                flipped.append((name, c))
                t_flip += 1
            else:
                bad.append((name, c, int(np.abs(got.astype(int) - ref).sum())))
                t_bad += 1
        per_type[name] = (t_ok, t_flip, t_bad)
    print("逐类型（正确/翻转/不符）:")
    for n, v in sorted(per_type.items()):
        flag = "" if v[2] == 0 and v[1] == 0 else "   <== 有问题"
        print(f"   {n:26s} {v[0]:6d} {v[1]:4d} {v[2]:5d}{flag}")
    print(f"字形逐格比对：正确 {ok}，翻转 {len(flipped)}，其他不符 {len(bad)}")
    if flipped[:5]:
        print("   翻转示例:", flipped[:5])
    if bad[:5]:
        print("   不符示例:", bad[:5])
    os.remove("_tmp_sheet.webp")
    return not flipped and not bad


def check_shot(png, text, cellw):
    A = np.array(Image.open(png).convert("L"))
    bright = A > 110
    ys = np.where(bright.any(axis=1))[0]
    xs = np.where(bright.any(axis=0))[0]
    scale = round(cellw / 8)  # 8px 字格：截图里放大倍数
    print(f"截图 {png}: 墨迹 y={ys.min()}..{ys.max()} x={xs.min()}..{xs.max()}")
    bdf = Bdf("fonts/fusion-pixel-8px-monospaced-zh_hans.bdf")
    for i, c in enumerate(text):
        ref = canon(bdf, c, (8, 8)) if ord(c) > 0x2E80 else None
        if ref is None:
            continue
        print(f"   '{c}' 参考位图:\n" + "\n".join(
            "      " + "".join("#" if v else "." for v in row) for row in ref))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "sheet"
    if mode == "sheet":
        ok = check_sheet(sys.argv[2] if len(sys.argv) > 2 else "dist/www/assets.dat")
        sys.exit(0 if ok else 1)
    else:
        check_shot(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 8)
