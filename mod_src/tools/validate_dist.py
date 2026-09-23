#!/usr/bin/env python3
"""Final integrity check of dist/www/assets.dat (the shippable patch)."""
import json
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from c3bundle import extract, read_directory, pack      # noqa: E402
from PIL import Image                                   # noqa: E402

BUNDLE = os.path.join(ROOT, "dist", "www", "assets.dat")
# 原版参照包：优先环境变量（update_repack.py 注入），否则用工作区 extracted/ 快照，
# 再不行退回默认路径；找不到时只跳过「与原版对比」这一步，不影响主校验。
DEFAULT_VANILLA = r"E:\SteamLibrary\steamapps\common\Isle of Reveries\www\assets.dat"


def _vanilla():
    for c in (os.environ.get("CN_VANILLA_BUNDLE"), DEFAULT_VANILLA,
              os.path.join(ROOT, "extracted", "assets.dat")):
        if c and os.path.isfile(c):
            return c
    return None


VANILLA = _vanilla()

SIGS = {".webp": b"RIFF", ".webm": b"\x1aE\xdf\xa3", ".png": b"\x89PNG",
        ".json": b"{", ".html": b"<!DOCTYPE"}


def main():
    tmp = tempfile.mkdtemp()
    ents, _, _ = extract(BUNDLE, tmp, verbose=False)
    print(f"文件数: {len(ents)}")
    bad = []
    for e in ents:
        p = os.path.join(tmp, e["name"].replace("/", os.sep))
        blob = open(p, "rb").read()
        if len(blob) != e["size"]:
            bad.append((e["name"], "size mismatch"))
        sig = SIGS.get(os.path.splitext(e["name"])[1])
        if sig and not blob.startswith(sig):
            bad.append((e["name"], "bad magic", blob[:8]))
    print("签名/尺寸异常:", bad[:5], "count", len(bad))

    proj = json.load(open(os.path.join(tmp, "data.json"), encoding="utf-8"))["project"]
    fonts = [(i, ot) for i, ot in enumerate(proj[3]) if isinstance(ot, list) and ot[1] == 14]
    print("字体对象类型:", len(fonts))
    font_bad = []
    for i, ot in fonts:
        name, size, x, y, w, h, _ = ot[6]
        path = os.path.join(tmp, name.replace("/", os.sep))
        if not os.path.exists(path):
            print("  !! 缺图:", name)
            font_bad.append((ot[0], "missing", name))
            continue
        im = Image.open(path)
        if im.size != (w, h) or os.path.getsize(path) != size:
            print(f"  !! {ot[0]}: 声明 {w}x{h}/{size}B, 实际 {im.size}/{os.path.getsize(path)}B")
            font_bad.append((ot[0], "declaration mismatch"))
    print("字体图与 data.json 声明一致")

    rt = os.path.join(tmp, "scripts", "c3runtime.js")
    src = open(rt, encoding="utf-8").read()
    runtime_ok = "__isleCNPatched" in src
    print("运行时补丁存在:", runtime_ok, "| 文件大小", len(src))
    mjs = os.path.join(tempfile.mkdtemp(), "check.mjs")
    open(mjs, "w", encoding="utf-8").write(src)
    r = subprocess.run(["node", "--check", mjs], capture_output=True)
    print("node --check:", "OK" if r.returncode == 0 else r.stderr.decode()[:400])

    # 重新打包必须仍然逐字节一致（证明补丁包结构合法）
    out = os.path.join(tmp, "repack.dat")
    order = [e["name"] for e in ents]
    n, dsz, bsz = pack(tmp, out, order=order)
    same = open(out, "rb").read() == open(BUNDLE, "rb").read()
    print("重打包一致性:", same)

    # 与原版对比：只有 data.json / c3runtime.js 变化 + 新增 24 张图
    failures = list(bad) + font_bad
    if not runtime_ok:
        failures.append(("scripts/c3runtime.js", "missing runtime marker"))
    if r.returncode != 0:
        failures.append(("scripts/c3runtime.js", "node --check failed"))
    if not same:
        failures.append((BUNDLE, "repack mismatch"))

    if not VANILLA:
        print("（找不到原版参照包，跳过与原版对比）")
        if failures:
            print("校验失败:", failures[:10], "count", len(failures))
            return 1
        return 0
    ve, _, vdata = read_directory(VANILLA)
    vnames = {e["name"]: e for e in ve}
    pnames = {e["name"]: e for e in ents}
    added = [e["name"] for e in ents if e["name"] not in vnames]
    removed = [e["name"] for e in ve if e["name"] not in pnames]

    with open(VANILLA, "rb") as f:
        vanilla_hashes = {}
        for e in ve:
            f.seek(vdata + e["offset"])
            vanilla_hashes[e["name"]] = hashlib.sha256(f.read(e["size"])).digest()

    changed = []
    for name in sorted(set(vnames) & set(pnames)):
        p = os.path.join(tmp, name.replace("/", os.sep))
        if hashlib.sha256(open(p, "rb").read()).digest() != vanilla_hashes[name]:
            changed.append(name)
    print("新增文件:", len(added), added[:3], "...")
    print("删除文件:", removed)
    print("内容变化的原文件:", changed)

    expected_changed = {
        "data.json", "scripts/c3runtime.js",
        "images/warpmenubg-sheet0.webp", "images/warpmenu_hiddentext-sheet0.webp",
        "images/buildmenubg-sheet0.webp", "images/buildmenu_pages-sheet0.webp",
        "images/buildmenu_pages-sheet1.webp", "images/shared-4-sheet1.webp",
        "images/worldmapbg-sheet0.webp", "images/controlsbg-sheet0.webp",
        "images/shared-1-sheet0.webp", "images/fileselect_cursor-sheet0.webp",
        "images/shared-9-sheet6.webp", "images/displaybugmenubg-sheet0.webp",
        "images/trinketmenubg-sheet0.webp", "images/fashionmenubg-sheet0.webp",
        "images/album_inputprompt-sheet0.webp", "images/mp_pause-sheet0.webp",
        "images/dungeon_title-sheet0.webp",
    }
    if removed:
        failures.append(("removed files", removed[:10]))
    if len(added) != 24 or any(not n.startswith("images/cnfont_") for n in added):
        failures.append(("unexpected added files", added[:30]))
    if set(changed) != expected_changed:
        failures.append(("unexpected changed files", changed))

    if failures:
        print("校验失败:", failures[:10], "count", len(failures))
        return 1
    print("完整性校验通过：除预定汉化文件外，原版音频/图片/脚本均逐文件保持一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
