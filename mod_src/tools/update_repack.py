#!/usr/bin/env python3
"""Re-build the Chinese patch after an official game update.

Steam updates replace www/assets.dat wholesale, which wipes the patch (the game
just goes back to English -- nothing of ours survives, so nothing can break).
This script takes the *new* vanilla bundle and regenerates the patch from it:

  1. refuse to run while the game is running
  2. back the current (new vanilla) assets.dat up as assets.dat.cn-backup,
     never overwriting a backup with an already-patched bundle
  3. re-extract the new bundle (old snapshot kept as extracted_prev/)
  4. rebuild the patched bundle (fonts, charset, dictionary, runtime hook)
  5. validate it (repack identity, node --check, per-glyph pixel compare)
  6. optionally install it into the game

Everything version-specific (font object types, glyph sheets, instance data) is
re-derived from the new data.json, so a normal content update needs no code
change.  New or reworded English strings simply stay English until the
dictionary is topped up: the runtime hook falls back to the original text.

Usage:
  python3 tools/update_repack.py                    # default game path
  python3 tools/update_repack.py --game "D:\\Games\\Isle of Reveries" --no-install
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

# 默认游戏目录：优先环境变量 CN_GAME，其次本机实测路径，也可以用 --game 指定。
DEFAULT_GAME = os.environ.get("CN_GAME") or \
    r"D:\Games\Steam\steamapps\common\Isle of Reveries"
PATCH_IMAGE_PREFIX = "images/cnfont_"
PATCH_JS_MARKER = "\u7b80\u4f53\u4e2d\u6587\u8865\u4e01"   # 简体中文补丁


def check_art_inputs(bundle):
    """An atlas update may move baked text; do not install blindly."""
    from resource_manifest import (MANIFEST_NAME, changed_original_images,
                                   unchanged_atlas_frames)

    inventory_path = os.path.join(os.path.dirname(ROOT), MANIFEST_NAME)
    if not os.path.isfile(inventory_path):
        sys.exit(f"[失败] 找不到 {inventory_path}，无法确认旧版贴图坐标；"
                 "请先生成替换资源清单，或请维护者手动检查后重建。")
    with open(inventory_path, encoding="utf-8") as f:
        inventory = json.load(f)
    try:
        changed = changed_original_images(inventory, bundle)
    except (KeyError, TypeError, ValueError) as exc:
        sys.exit(f"[失败] 资源清单无效：{exc}；请维护者核对后重建。")
    if changed:
        old_md5 = inventory.get("base_bundle", {}).get("md5")
        # September 27 update: inspected all changed frames against the old
        # English bundle. BuildMenu gained Hero's Hollow; the crypt map changed
        # room markers, the build prompt changed its decorative rail. Other
        # changed atlases were repacked with pixel-identical existing frames.
        # Pin both complete bundle hashes and the atlas list so later updates
        # still stop for review if any of this artwork changes again.
        reviewed = {
            ("c129bb8fa4beb49a4e8f23d0748be5fc",
             "06e9ffd80556cef82791cc1a84d0557d"): {
                "images/buildmenu_pages-sheet0.webp",
                "images/buildmenu_pages-sheet1.webp",
                "images/dialoguebox-sheet0.webp",
                "images/dungeon_title-sheet0.webp",
                "images/fileselect_cursor-sheet0.webp",
                "images/maps_sprite-sheet0.webp",
                "images/shared-4-sheet1.webp",
                "images/shared-9-sheet6.webp",
            },
        }
        if set(changed) == reviewed.get((old_md5, md5(bundle))):
            print("  已复核本次官方更新的 8 张汉化图集：新建筑及地图画面保留，文字区域可重绘。")
            return
        # September 28: five atlases were repacked. Every surviving named
        # frame is pixel/attribute identical; one obsolete FileSelectSwipe
        # animation was removed. Check that exact frame delta against the
        # preserved English backup before accepting the new atlas geometry.
        if (old_md5, md5(bundle)) == (
            "06e9ffd80556cef82791cc1a84d0557d",
            "1819ebb21f6d71f873c5d6ba73126642",
        ) and set(changed) == {
            "images/dialoguebox-sheet0.webp",
            "images/dungeon_title-sheet0.webp",
            "images/fileselect_cursor-sheet0.webp",
            "images/maps_sprite-sheet0.webp",
            "images/shared-9-sheet6.webp",
        }:
            from resource_manifest import atlas_frame_pixels
            previous = bundle + ".cn-backup"
            if os.path.isfile(previous) and md5(previous) == old_md5:
                old_frames = atlas_frame_pixels(previous, changed)
                new_frames = atlas_frame_pixels(bundle, changed)
                removed = {("images/shared-9-sheet6.webp",
                            "FileSelectSwipe", "Animation 1", 0)}
                if (old_frames.keys() - new_frames.keys() == removed
                        and not new_frames.keys() - old_frames.keys()
                        and all(old_frames[key] == new_frames[key]
                                for key in new_frames)):
                    print("  已逐帧复核本次官方更新的 5 张图集；移除一帧旧存档转场，其他画面未变。")
                    return
        # September 29 bundle (reviewed September 30): five atlases were
        # repacked, with one new anonymous MineGhost dialogue portrait (???).
        # Keep the new artwork intact and require identical existing frames.
        if (old_md5, md5(bundle)) == (
            "1819ebb21f6d71f873c5d6ba73126642",
            "926fe43e69dae4fda2455ce5052e5a8c",
        ) and set(changed) == {
            "images/buildmenu_pages-sheet0.webp",
            "images/dialoguebox-sheet0.webp",
            "images/dungeon_title-sheet0.webp",
            "images/fileselect_cursor-sheet0.webp",
            "images/maps_sprite-sheet0.webp",
        }:
            from resource_manifest import atlas_frames_match_delta
            previous = bundle + ".cn-backup"
            added = {("images/dialoguebox-sheet0.webp",
                      "DialogueBox", "MineGhost", 0)}
            if (os.path.isfile(previous) and md5(previous) == old_md5
                    and atlas_frames_match_delta(previous, bundle, changed,
                                                 added=added)):
                print("  已逐帧复核本次官方更新的 5 张图集；保留新增矿洞幽灵肖像及匿名名牌，其他画面未变。")
                return
        # September 30 afternoon: reviewed a renamed dungeon map and one
        # 8x8 room cell on WorldMap_2. Chinese footer coordinates are intact.
        if (old_md5, md5(bundle)) == (
            "926fe43e69dae4fda2455ce5052e5a8c",
            "936aaed59f17c1b53eb5b1b2563a51aa",
        ) and set(changed) == {
            "images/buildmenu_pages-sheet0.webp",
            "images/dialoguebox-sheet0.webp",
            "images/maps_sprite-sheet0.webp",
        }:
            from resource_manifest import atlas_frames_match_delta
            previous = bundle + ".cn-backup"
            atlas = "images/maps_sprite-sheet0.webp"
            if (os.path.isfile(previous) and md5(previous) == old_md5
                    and atlas_frames_match_delta(
                        previous, bundle, changed,
                        removed={(atlas, "Maps_Sprite", "DungeonCrypt", 0)},
                        added={(atlas, "Maps_Sprite", "Dungeon2_HasMap2", 0)},
                        changed_regions={(atlas, "Maps_Sprite", "WorldMap_2", 0):
                                         [(24, 16, 32, 24)]})):
                print("  已复核 9 月 30 日下午更新：保留新版地图格子与地牢地图，汉化文字区域未变。")
                return
        # October 5: reviewed cross-atlas moves (same frame pixels/anchors),
        # enlarged dungeon maps (112x88 -> 144x96), Hidden map and the new
        # overview/pin/legend UI. Repaint uses current project frame geometry.
        # Exact whole-bundle hashes keep later content changes behind review.
        if (old_md5, md5(bundle)) == (
            "936aaed59f17c1b53eb5b1b2563a51aa",
            "75ebd11d427862ac41df62eee4057650",
        ) and set(changed) == {
            "images/dialoguebox-sheet0.webp", "images/maps_sprite-sheet0.webp",
            "images/shared-1-sheet0.webp", "images/shared-3-sheet0.webp",
            "images/shared-4-sheet1.webp", "images/shared-9-sheet6.webp",
            "images/worldmapbg-sheet0.webp",
        }:
            print("  已复核 10 月 5 日更新：适配新版地图图例与标记界面，保留扩大的地牢地图和新版图集位置。")
            return
        # October 6: compared all 17,952 named frames in unrotated game
        # orientation. Only MiniMap changed; it is not repainted by the patch.
        # The seven localized atlases only repack/move existing frames across
        # sheets. No sprite pixels, anchors or collision data changed there.
        # Repaint uses the new project geometry; pin this reviewed input pair.
        if (old_md5, md5(bundle)) == (
            "75ebd11d427862ac41df62eee4057650",
            "82005493a00b8184dbf7dc9101f7e5a9",
        ) and set(changed) == {
            "images/dialoguebox-sheet0.webp", "images/shared-0-sheet0.webp",
            "images/shared-10-sheet0.webp", "images/shared-3-sheet0.webp",
            "images/shared-4-sheet1.webp", "images/shared-9-sheet7.webp",
            "images/worldmapbg-sheet0.webp",
        }:
            print("  已复核 10 月 6 日更新：汉化帧画面与属性未变，按新版图集位置重绘，并保留官方小地图修改。")
            return
        # October 7 (Steam Build 25769935): all 17,952 named frames retain
        # their pixels and attributes. Five localized atlases are repacked;
        # two unlocalized character pages move between sheets. Keep the new
        # minecart event/runtime references by rebuilding from the new bundle.
        if (old_md5, md5(bundle)) == (
            "82005493a00b8184dbf7dc9101f7e5a9",
            "de010887cb6fa586eb6b08bd1e302573",
        ) and set(changed) == {
            "images/dialoguebox-sheet0.webp", "images/dungeon_title-sheet0.webp",
            "images/fileselect_cursor-sheet0.webp", "images/maps_sprite-sheet0.webp",
            "images/worldmapbg-sheet0.webp",
        }:
            print("  已复核 10 月 7 日更新：所有动画帧画面与属性未变，按新版图集重绘并保留矿车脚本更新。")
            return
        # October 9 (Steam Build 25818045): reviewed all 17,987 frames.
        # The minimap and two lever sprites change; 35 new frames include
        # the four-option save menu. Existing text frames move across sheets
        # with unchanged pixels. Pin the exact official bundles and inventory.
        if (old_md5, md5(bundle)) == (
            "de010887cb6fa586eb6b08bd1e302573",
            "f4d502c77ac83211267fece9df8f33a9",
        ) and set(changed) == {
            "images/album_inputprompt-sheet0.webp",
            "images/buildmenu_pages-sheet0.webp",
            "images/dialoguebox-sheet0.webp",
            "images/dungeon_title-sheet0.webp",
            "images/fileselect_cursor-sheet0.webp",
            "images/maps_sprite-sheet0.webp",
            "images/pinselect-sheet0.webp",
            "images/shared-0-sheet0.webp",
            "images/shared-0-sheet1.webp",
            "images/shared-3-sheet0.webp",
            "images/shared-4-sheet1.webp",
            "images/shared-9-sheet6.webp",
            "images/shared-9-sheet7.webp",
            "images/worldmapbg-sheet0.webp",
        }:
            print("  已复核 10 月 9 日更新：按新版图集重绘文字，保留小地图、机关及新增区域资源。")
            return
        old_bundle = next((path for path in sorted(
            (bundle + ".cn-backup", *[os.path.join(os.path.dirname(bundle), name)
              for name in os.listdir(os.path.dirname(bundle))
              if name.startswith(os.path.basename(bundle) + ".cn-backup.")]))
            if os.path.isfile(path) and md5(path) == old_md5), None)
        if old_bundle and unchanged_atlas_frames(old_bundle, bundle, changed):
            print(f"  已逐帧对照 {len(changed)} 张重新排布的图集：画面和帧属性一致，可安全重绘。")
            for name in changed:
                print("   ", name)
        else:
            print("[停止] 官方更新改动了以下汉化贴图的英文原图：")
            for name in changed:
                print("  ", name)
            if old_bundle:
                print("  已找到旧英文备份，但新版帧内容或帧名称发生变化，不能按图集重排自动放行。")
            else:
                print("  未找到与本补丁匹配的旧英文备份，无法逐帧检查新版图集。")
            sys.exit("当前游戏更新尚未完成贴图适配，请使用适配该游戏版本的新补丁。"
                     "游戏文件与备份均未改动。")
    print(f"  已检查替换资源清单中 {len(inventory['modified']) - 2} 张英文原图。")


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def is_patched(bundle):
    """True if this bundle already carries our patch."""
    try:
        from c3bundle import read_directory
        ents, _, ds = read_directory(bundle)
        if any(e["name"].startswith(PATCH_IMAGE_PREFIX) for e in ents):
            return True
        f = open(bundle, "rb")
        e = next(x for x in ents if x["name"] == "scripts/c3runtime.js")
        f.seek(ds + e["offset"])
        return PATCH_JS_MARKER in f.read(e["size"]).decode("utf-8", "ignore")
    except Exception as exc:
        print(f"  [警告] 无法判断该包是否已汉化（{exc}）；按“未汉化”处理")
        return False


def game_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Isle_of_Reveries.exe"],
                         capture_output=True).stdout.decode("utf-8", "ignore")
    return "Isle_of_Reveries" in out


def work_root():
    """Where the pipeline runs.

    The development workspace has an extracted/ source snapshot. A shipped
    copy (dist/mod_src/tools/...) has no snapshot: stage its tools, translations
    and fonts in a temp directory so the release folder stays clean.
    """
    if os.path.isdir(os.path.join(ROOT, "extracted")):
        return ROOT
    work = os.path.join(os.environ.get("TEMP") or tempfile.gettempdir(), "isle_cn_rebuild")
    for sub in ("tools", "trans", "fonts"):
        src = os.path.join(ROOT, sub)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(work, sub)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                    "*.orig"))
    print(f"  （从交付目录运行：中间产物写到 {work}）")
    return work


def pipeline_env(game):
    """子进程环境：告诉 build_cn_patch/validate_dist 原版参照包在哪。"""
    env = os.environ.copy()
    env["CN_VANILLA_BUNDLE"] = os.path.join(game, "www", "assets.dat")
    env["CN_GAME"] = game
    env["PYTHONIOENCODING"] = "utf-8:replace"
    env["PYTHONUTF8"] = "1"
    return env


def run(cmd, cwd, capture=False, env=None):
    # 子进程一律 UTF-8 输出（pipeline_env 里设了 PYTHONUTF8=1）；
    # 不指定 encoding 的话 Python 会拿系统 ANSI(GBK) 去解 UTF-8，
    # 中文一多就抛 UnicodeDecodeError 把校验结果吞掉。errors="replace"
    # 保证最坏情况也只是显示成问号，不会让校验步骤整个挂掉。
    if not capture:
        # The batch console uses GBK, while builders deliberately output UTF-8.
        # Decode child output before the parent's configured encoding prints it.
        with subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace") as process:
            for line in process.stdout:
                print(line, end="", flush=True)
            return process.wait()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, env=env,
                       text=True, encoding="utf-8", errors="replace")
    if capture:
        tail = "\n".join(((r.stdout or r.stderr or "").strip().splitlines())[-5:])
        print(tail)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--no-install", action="store_true")
    a = ap.parse_args()
    game = a.game
    bundle = os.path.join(game, "www", "assets.dat")
    if not os.path.exists(bundle):
        sys.exit(f"[错误] 找不到 {bundle}")

    patched = is_patched(bundle)
    print(f"游戏资源包: {bundle}")
    print(f"  大小 {os.path.getsize(bundle):,} 字节  md5 {md5(bundle)[:12]}  "
          f"{'（已汉化）' if patched else '（英文原版）'}")

    # 1) 备份：只在当前是真·原版时才覆盖 .cn-backup
    bak = bundle + ".cn-backup"
    if patched:
        print("  → 当前包已经是汉化版，无需重建。")
        print("     要安装已发布的汉化修订，请退出游戏并运行新版 安装.bat。")
        print("     官方更新将资源包替换为英文原版后，再运行本脚本重建。")
        return 0
    if game_running():
        sys.exit("[停止] 检测到 Isle_of_Reveries.exe 进程。请先退出游戏，再重建并安装。")
    else:
        check_art_inputs(bundle)
        if os.path.exists(bak):
            arch = f"{bak}.{datetime.datetime.now():%Y%m%d-%H%M%S}"
            shutil.copy(bak, arch)
            print(f"  旧备份存档 -> {os.path.basename(arch)}")
        shutil.copy(bundle, bak)
        print(f"  备份英文原版 -> {os.path.basename(bak)}")

    # 2) 解包新版（在工作区里做）
    work = work_root()
    extracted = os.path.join(work, "extracted")
    prev = os.path.join(work, "extracted_prev")
    if os.path.isdir(prev):
        shutil.rmtree(prev)
    if os.path.isdir(extracted):
        shutil.move(extracted, prev)
        print("  旧解包快照 -> extracted_prev/")
    sys.path.insert(0, os.path.join(work, "tools"))
    from c3bundle import extract            # noqa: E402
    extract(bundle, extracted)
    print("  已解包新版 -> extracted/")

    tools = os.path.join(work, "tools")
    dist_bundle = os.path.join(work, "dist", "www", "assets.dat")

    # 3) 重建
    print("\n--- 重建汉化包 ---")
    penv = pipeline_env(game)
    for name in ("build_cn_patch.py", "make_dist.py"):
        rc = run([sys.executable, os.path.join(tools, name)], work, env=penv)
        if rc:
            sys.exit(f"[失败] {name} 退出码 {rc}")

    # 4) 校验
    print("\n--- 校验 ---")
    ok = True
    rc = run([sys.executable, os.path.join(tools, "validate_dist.py")], work,
             capture=True, env=penv)
    ok &= rc == 0
    rc = run([sys.executable, os.path.join(tools, "verify_glyphs.py"), "sheet", dist_bundle],
             work, capture=True, env=penv)
    ok &= rc == 0
    if not ok:
        sys.exit("[失败] 校验未通过：没有安装生成的资源包；请把上面的输出发给维护者")

    src, tag = "?", "?"
    try:
        sys.path.insert(0, tools)
        import make_dist
        src, tag = make_dist.VERSION, make_dist.VERSION_TAG
    except Exception as exc:
        print(f"  （读不到版本号：{exc}）")
    print(f"\n新汉化包: {dist_bundle}  {os.path.getsize(dist_bundle):,} 字节  "
          f"md5 {md5(dist_bundle)[:12]}")
    print(f"版本: {src} ({tag})")

    # 5) 安装
    if a.no_install:
        print("（--no-install：未安装，可自行运行 dist\\安装.bat）")
        return
    shutil.copy(dist_bundle, bundle)
    if md5(dist_bundle) != md5(bundle):
        sys.exit("[失败] 安装后的资源包 MD5 不一致；请关闭游戏并重新安装。")
    print(f"已安装到游戏: {bundle}  一致校验: True")

    # Keep the distributable in sync.  In particular, the uninstaller needs
    # the new original/patch hashes after every official game update.
    delivery = os.path.dirname(ROOT)
    try:
        os.makedirs(os.path.join(delivery, "www"), exist_ok=True)
        shutil.copy2(dist_bundle, os.path.join(delivery, "www", "assets.dat"))
        for filename in ("安装.bat", "卸载.bat", "版本.txt", "说明.txt",
                         "官方更新后重建.bat", "替换资源清单.json"):
            shutil.copy2(os.path.join(work, "dist", filename),
                         os.path.join(delivery, filename))
        print(f"交付目录已同步（含新版卸载器和资源清单）: {delivery}")
    except OSError as exc:
        print(f"[警告] 游戏已安装汉化，但无法同步交付目录：{exc}")
        print(f"        新版文件仍在 {os.path.join(work, 'dist')}")
    d = json.load(open(os.path.join(work, "trans", "dict.json"), encoding="utf-8"))
    print(f"词典 {len(d)} 条；官方新增/改写的英文句子会自动回退为英文，"
          f"需要补译时把它们加进 trans/dict.json 后重跑本脚本即可。")


if __name__ == "__main__":
    main()
