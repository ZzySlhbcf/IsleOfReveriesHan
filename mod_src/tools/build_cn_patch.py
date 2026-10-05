#!/usr/bin/env python3
"""Build the complete Simplified-Chinese patch for Isle of Reveries.

Steps
  1. copy the vanilla extracted tree to dev/www (clean)
  2. load the merged translation dictionary
  3. work out which characters need glyphs (falling back for glyphs the 8px
     pixel font does not have)
  4. build an extended SpriteFont glyph sheet for every font object type
  5. point each font type at its new sheet (data.json)
  6. append the runtime translation patch to scripts/c3runtime.js
  7. repack www/assets.dat and stage the distributable files
"""
import json
import collections
import os
import shutil
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from bdf import Bdf                                  # noqa: E402
from c3bundle import pack, read_directory            # noqa: E402
import fontsheet                                     # noqa: E402

# 原版包路径：优先取环境变量（update_repack.py 会把新版 assets.dat 的路径传进来），
# 否则用本工作区 extracted/ 里的原版解包快照，再不行才用下面的默认值。
# 这样无论游戏装在哪个盘都能跑通，不必再手改脚本。
DEFAULT_VANILLA_BUNDLE = r"E:\SteamLibrary\steamapps\common\Isle of Reveries\www\assets.dat"


def _vanilla_bundle():
    cands = [os.environ.get("CN_VANILLA_BUNDLE"), DEFAULT_VANILLA_BUNDLE,
             os.path.join(ROOT, "extracted", "assets.dat")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return cands[0] if cands[0] else DEFAULT_VANILLA_BUNDLE


VANILLA_BUNDLE = _vanilla_bundle()
EXTRACTED = os.path.join(ROOT, "extracted")
DEV = os.path.join(ROOT, "dev", "www")
DIST = os.path.join(ROOT, "dist")
BDF_PATH = os.path.join(ROOT, "fonts", "fusion-pixel-8px-monospaced-zh_hans.bdf")
BDF_PATH_10 = os.path.join(ROOT, "fonts", "fusion-pixel-10px-monospaced-zh_hans.bdf")
BDF_PATH_12 = os.path.join(ROOT, "fonts", "fusion-pixel-12px-monospaced-zh_hans.bdf")

# 每个文字对象用多大的字格（像素）。8 = 原版不动；11 = 12px 字库（墨迹 11x11，1:1 落格）；
# 10 = 10px 字库（墨迹 9x9），给菜单/说明这类版面紧的界面用。
# 字格用 (宽, 高)：宽度决定字距步长，高度比字形多留 1px —— 游戏里“物品名”和
# “物品说明”常常是两个挨着的对象，格子高度不留白的话两行会贴死（行距管不到对象之间）。
CELL_BY_TYPE = {
    # 对白/钓鱼/制作名单/标题：保持原来的方形 11x11（标题“任务”等的观感不要变）
    "SpriteFont_Dialogue": (11, 11), "SpriteFont_Fishing": (11, 11),
    "SpriteFont_Credits": (11, 11), "TitleTexts": (11, 11), "TitleScreenText": (11, 11),
    # 菜单/物品说明/笔记：9 宽 x 10 高。
    # 注意：这里**不能**降到 8x8——8px 字库的 ASCII 字母比 8px 格子窄，
    # 字母之间会出现明显的空隙（实测玩家一眼看出“字符间距被拉大”）。
    # 9 宽则用 10px 字库，ASCII 字形饱满，观感与原版一致。
    "MenuName": (9, 10), "ItemDescription": (9, 10), "TrinketMenuName": (9, 10),
    "BuildMenuName": (9, 10), "BugMuseumMenuText": (9, 10), "NoteMenuName": (9, 10),
}

# “名字 / 说明”这类紧贴文本框的类型：运行时按实例把下面那个推下去一点
GAP_TYPES = ["MenuName", "ItemDescription", "TrinketMenuName",
             "BuildMenuName", "BugMuseumMenuText", "NoteMenuName"]
GAP_NUDGE = 2        # 运行时下移像素（8px 字格本身已自带 1px 缝）

# 原来字格不是 8x8、被降到 8px 的类型：ASCII 部分必须跟着重画（见下面的 rerender_all）
RERENDER_8PX = {"MenuName", "ItemDescription", "TrinketMenuName",
                "BuildMenuName", "BugMuseumMenuText", "NoteMenuName"}
CELL_SPACING = 1          # 汉字之间的额外字距（像素）——只给 11 号用
# 所有字形共用固定基线；不要按单字墨迹高度额外下移，否则“一”等矮字偏低。
CELL_SPACING_BY_CELL = {9: 0, 10: 1, 11: 1}   # 按格宽配字距，小格不再留缝
# 行距加值（按格宽给）：行步长 = 格高 + 该值。菜单格高 11 且字形 9 -> 换行缝 2px；
# 11x11 方形格字形满格，需要 +2 才有 2px 缝。
LINE_HEIGHT_BY_CELL = {9: 0, 11: 2}
LINE_HEIGHT = 2           # 兜底（8x8 类型不动）

# 正文类字体换成 12x12 点阵（8x8 装不下汉字笔画）；数字/按键类保持 8x8 以免破坏 HUD 版面
DICT_PATH = os.path.join(ROOT, "trans", "dict.json")
ORDER_JSON = os.path.join(ROOT, "trans", "bundle_order.json")

# glyphs absent from the pixel font -> print the ascii equivalent instead
FALLBACK = {
    # "，": ",", "。": ".", "！": "!", "？": "?", "：": ":", "；": ";",
    # "、": ",", "（": "(", "）": ")", "《": "<", "》": ">", "「": "[",
    # "」": "]", "『": "[", "』": "]", "“": '"', "”": '"', "‘": "'", "’": "'",
    "桠": "丫",   # 12px 有、10px 字库没有，降级成同义字
    # "—": "-", "～": "~", "…": "...", "\u3000": " ", "·": "*", "・": "*",
    # "＜": "<", "＞": ">", "％": "%", "＋": "+", "－": "-", "＝": "=",
}


def font_types(project):
    return {i: ot for i, ot in enumerate(project[3])
            if isinstance(ot, list) and ot[1] == 14}


def iter_type_states(project, tid):
    """Yield the plugin state arrays of every instance of an object type."""
    for lay in project[5]:
        if not isinstance(lay, list) or len(lay) < 11 or not isinstance(lay[10], list):
            continue
        for layer in lay[10]:
            if not isinstance(layer, list) or len(layer) < 15 or not isinstance(layer[14], list):
                continue
            for inst in layer[14]:
                if not isinstance(inst, list) or len(inst) < 6 or inst[1] != tid:
                    continue
                for cand in inst[3:]:
                    if (isinstance(cand, list) and len(cand) >= 13
                            and isinstance(cand[0], str) and isinstance(cand[2], int)
                            and isinstance(cand[3], int) and isinstance(cand[4], str)
                            and len(cand[4]) > 40):
                        yield cand
                        break


def charsets_of(project, tid):
    out = set()
    for lay in project[5]:
        if not isinstance(lay, list) or len(lay) < 11 or not isinstance(lay[10], list):
            continue
        for layer in lay[10]:
            if not isinstance(layer, list) or len(layer) < 15 or not isinstance(layer[14], list):
                continue
            for inst in layer[14]:
                if not isinstance(inst, list) or len(inst) < 6 or inst[1] != tid:
                    continue
                for cand in inst[3:]:
                    if (isinstance(cand, list) and len(cand) >= 13
                            and isinstance(cand[0], str) and isinstance(cand[2], int)
                            and isinstance(cand[3], int) and isinstance(cand[4], str)
                            and len(cand[4]) > 40):
                        out.add(cand[4])
                        break
    return out


def main(use_stub=False):
    bdf8 = Bdf(BDF_PATH)
    bdf12 = Bdf(BDF_PATH_12)
    bdf10 = Bdf(BDF_PATH_10)
    print("pixel font glyphs: 8px =", len(bdf8.glyphs), "| 10px =", len(bdf10.glyphs),
          "| 12px =", len(bdf12.glyphs))
    BDF_FOR_CELL = {8: bdf8, 9: bdf10, 10: bdf10, 11: bdf12}
    # 每个字库的“汉字顶线”（基线以上高度），用于把字形按基线对齐
    BASE_REF = {}
    for size, bdf in ((8, bdf8), (10, bdf10), (11, bdf12)):
        sample = [chr(cp) for cp in bdf.glyphs if 0x4E00 <= cp <= 0x9FFF][:300]
        ys = []
        for c in sample:
            g = bdf.rows_to_bits(c)
            if g and g[0]:
                ys.append(max(q[1] for q in g[0]))
        BASE_REF[size] = max(set(ys), key=ys.count) if ys else 0
    BASE_REF[9] = BASE_REF[10]
    print("基线参考行:", BASE_REF)

    dict_ = json.load(open(DICT_PATH if os.path.exists(DICT_PATH) else
                           os.path.join(ROOT, "trans", "dict_stub.json"), encoding="utf-8"))
    print("dictionary entries:", len(dict_))

    # --- 3) characters needing glyphs -----------------------------------
    src_chars = set()
    for v in dict_.values():
        src_chars.update(v)
    cjk = sorted(c for c in src_chars if ord(c) > 0x2000 and c not in FALLBACK)
    have = [c for c in cjk if bdf12.get(c) and bdf10.get(c) and bdf8.get(c)]
    missing = [c for c in cjk if not (bdf12.get(c) and bdf10.get(c) and bdf8.get(c))]
    print(f"chars: {len(src_chars)} total, {len(cjk)} cjk, {len(have)} with glyphs, "
          f"{len(missing)} missing -> fallback")
    if missing:
        print("   missing sample:", "".join(missing[:60]))
    # apply fallbacks in the dictionary so the game never shows blanks
    fixed = {}
    for k, v in dict_.items():
        nv = v
        for ch in missing:
            nv = nv.replace(ch, FALLBACK.get(ch, ""))
        fixed[k] = nv
    # keep only chars present in the font for the charset
    cn_chars = "".join(have)
    print("cn charset length:", len(cn_chars))

    # --- 1) clean dev tree ----------------------------------------------
    vanilla_entries, _, _ = read_directory(VANILLA_BUNDLE)
    vanilla_order = [entry["name"] for entry in vanilla_entries]
    vanilla_names = set(vanilla_order)
    if os.path.isdir(DEV):
        shutil.rmtree(DEV)
    shutil.copytree(EXTRACTED, DEV)
    # extracted/ may also contain screenshots or audit reports made during
    # development.  Keep only paths present in the vanilla bundle before the
    # patch adds its own cnfont images, so local artifacts cannot ship.
    removed_artifacts = []
    for dirpath, _dirnames, filenames in os.walk(DEV):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, DEV).replace(os.sep, "/")
            if rel not in vanilla_names:
                os.remove(full)
                removed_artifacts.append(rel)
    if removed_artifacts:
        print("忽略非原版解包文件:", sorted(removed_artifacts))

    data_path = os.path.join(DEV, "data.json")
    project = json.load(open(data_path, encoding="utf-8"))["project"]
    fts = font_types(project)
    print("font object types:", len(fts))

    # --- 4/5) build sheets + repoint types ------------------------------
    os.makedirs(os.path.join(DEV, "images"), exist_ok=True)
    # 没有实例的类型也要用“标准字符集”打底，否则中文字形会落在错误格子上
    all_cs = collections.Counter()
    for tid in fts:
        for c in charsets_of(project, tid):
            all_cs[c] += 1
    canonical = all_cs.most_common(1)[0][0] if all_cs else " !\"   &'() +,-./0123456789:; = ?\nabcdefghijklmnopqrstuvwxyz"
    print(f"标准字符集长度: {len(canonical)}（{all_cs.most_common(3)}）")

    charset_map = {}
    type_cell = {}
    type_cell2 = {}
    type_charset = {}
    type_spacing = {}
    totals = {"cells": 0, "imgs": 0, "cell12": 0}
    for tid, ot in sorted(fts.items(), key=lambda kv: kv[1][0]):
        atlas, size, x, y, w, h, rot = ot[6]
        cs = charsets_of(project, tid)
        base = max(cs, key=len) if cs else canonical
        outimg = os.path.join(DEV, "images", f"cnfont_{ot[0]}.webp")
        cell = CELL_BY_TYPE.get(ot[0], (8, 8))
        cw_, ch_ = cell
        spacing = CELL_SPACING_BY_CELL.get(cw_, 0) if cw_ != 8 else 0
        if cw_ != 8:
            info = fontsheet.build(os.path.join(DEV, atlas), (x, y, w, h), base, cn_chars,
                                   BDF_FOR_CELL[cw_], outimg, cell=cell, rerender_all=True,
                                   base_ref=BASE_REF[cw_])
            for cand in iter_type_states(project, tid):
                cand[2] = cw_
                cand[3] = ch_
                cand[7] = spacing          # characterSpacing：字与字之间留缝
                cand[8] = LINE_HEIGHT_BY_CELL.get(cw_, LINE_HEIGHT)   # lineHeight
            totals["cell12"] += 1
        else:
            cell = (8, 8)
            kw = {"base_ref": BASE_REF[8]}
            if ot[0] in RERENDER_8PX:
                # 原版这套类型是 11x11 字格：只重画汉字、照旧格拷 ASCII 会让数字/字母错位消失
                kw["rerender_all"] = True
            info = fontsheet.build(os.path.join(DEV, atlas), (x, y, w, h), base, cn_chars,
                                   bdf8, outimg, **kw)
            for cand in iter_type_states(project, tid):
                cand[2] = 8
                cand[3] = 8
        ot[6] = [f"images/cnfont_{ot[0]}.webp", os.path.getsize(outimg), 0, 0, w,
                 info["height"], False]
        charset_map[base] = base + cn_chars
        type_charset[ot[0]] = base + cn_chars
        type_cell[ot[0]] = cw_
        type_cell2[ot[0]] = [cw_, ch_]
        if spacing:
            type_spacing[ot[0]] = spacing
        totals["cells"] += info["cells"]
        totals["imgs"] += 1
        if info["missing"]:
            print("   !! missing glyphs for", ot[0], len(info["missing"]))
    print(f"built {totals['imgs']} sheets ({totals['cell12']} 张放大字格, "
          f"其余 8x8, 字距 {CELL_SPACING}px, 行距 +{LINE_HEIGHT}px)")

    # --- 5b) 版面微调：名字↔说明 的箱子紧贴 0px，把下面的多行框下移 3px --------
    import layout_nudge
    print("存档摘要排版调整:", layout_nudge.adjust_save_summary(project))
    # 静态坐标会被游戏运行时重新算出来（实测无效），改成运行时钩子里按实例下移，
    # 所以这里保持原版坐标不动（DY=0）。
    moved = layout_nudge.nudge_flush_texts(project, 0)
    print(f"版面微调：下移 {len(moved)} 个紧贴的说明框（各 +{layout_nudge.DY}px）")
    for m in moved[:3]:
        print("   例:", m)

    # --- 5c) 像素美术中的菜单文字：传送页目的地、建造页建筑名 ---------
    # 这些标签不是 SpriteFont 文本，而是烘焙在旋转图集帧里的像素，运行时
    # SetText 钩子碰不到。仍然从 extracted/ 原版图重绘，避免重复构建叠加修改。
    import patch_baked_menus
    patch_baked_menus.repaint(project, EXTRACTED, DEV)

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"project": project}, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json:", os.path.getsize(data_path))

    # --- 6) runtime patch ------------------------------------------------
    tmpl = open(os.path.join(ROOT, "tools", "cn_runtime_template.js"), encoding="utf-8").read()
    ci_dict = {}
    ci_conflict = set()
    for k, v in fixed.items():
        lk = k.lower()
        if lk in ci_dict and ci_dict[lk] != v:
            ci_conflict.add(lk)
        else:
            ci_dict[lk] = v
    for lk in ci_conflict:
        ci_dict.pop(lk, None)
    print(f"大小写兜底词典: {len(ci_dict)} 条（{len(ci_conflict)} 个键因大小写冲突被丢弃）")

    js = (tmpl
          .replace("__DICT__", json.dumps(fixed, ensure_ascii=False, separators=(",", ":")))
          .replace("__DICT_CI__", json.dumps(ci_dict, ensure_ascii=False,
                                             separators=(",", ":")))
          .replace("__CN_CHARS__", json.dumps(cn_chars, ensure_ascii=False))
          .replace("__CHARSET_MAP__", json.dumps(charset_map, ensure_ascii=False,
                                                 separators=(",", ":")))
          .replace("__TYPE_CELL__", json.dumps(type_cell2, ensure_ascii=False))
          .replace("__TYPE_CHARSET__", json.dumps(type_charset, ensure_ascii=False))
          .replace("__TYPE_SPACING__", json.dumps(type_spacing, ensure_ascii=False))
          .replace("__GAP_TYPES__", json.dumps(GAP_TYPES, ensure_ascii=False))
          .replace("__GAP_NUDGE__", str(GAP_NUDGE)))
    rt = os.path.join(DEV, "scripts", "c3runtime.js")
    src = open(rt, encoding="utf-8").read()
    marker = "/* ============================================================\n * Isle of Reveries"
    if marker in src:
        src = src[:src.index(marker)]
    with open(rt, "w", encoding="utf-8") as f:
        f.write(src.rstrip("\n") + "\n\n" + js + "\n")
    print("c3runtime.js:", os.path.getsize(rt))

    # --- 7) repack ---------------------------------------------------------
    json.dump(vanilla_order, open(ORDER_JSON, "w", encoding="utf-8"))
    os.makedirs(os.path.join(DIST, "www"), exist_ok=True)
    n, dsz, bsz = pack(DEV, os.path.join(DIST, "www", "assets.dat"), order=vanilla_order)
    print(f"packed {n} files -> dist/www/assets.dat "
          f"({os.path.getsize(os.path.join(DIST, 'www', 'assets.dat'))} bytes)")

    json.dump({"entries": len(fixed), "cn_chars": len(cn_chars),
               "missing": missing}, open(os.path.join(ROOT, "trans", "build_report.json"),
                                         "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main("--stub" in sys.argv)
