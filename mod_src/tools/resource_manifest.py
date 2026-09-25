#!/usr/bin/env python3
"""Inventory the exact resource changes inside a Chinese patch bundle."""
import hashlib
import io
import json
import os

from c3bundle import read_directory
from PIL import Image


MANIFEST_NAME = "替换资源清单.json"
IMAGE_LABELS = {
    "images/album_inputprompt-sheet0.webp": "相册操作提示",
    "images/buildmenu_pages-sheet0.webp": "建造列表及详情",
    "images/buildmenu_pages-sheet1.webp": "建造列表及详情",
    "images/buildmenubg-sheet0.webp": "建造页标题",
    "images/controlsbg-sheet0.webp": "控制设置背景文字",
    "images/displaybugmenubg-sheet0.webp": "虫子图鉴页签",
    "images/dungeon_title-sheet0.webp": "地牢开场标题",
    "images/dialoguebox-sheet0.webp": "对话框角色名（已知名牌全帧）",
    "images/fashionmenubg-sheet0.webp": "外观颜色选项",
    "images/fileselect_cursor-sheet0.webp": "存档选择按钮",
    "images/mp_pause-sheet0.webp": "多人暂停选项",
    "images/maps_sprite-sheet0.webp": "世界地图详情标题及操作提示",
    "images/settingsbg-sheet0.webp": "游戏设置页面标签",
    "images/shared-1-sheet0.webp": "移动控制提示",
    "images/shared-3-sheet0.webp": "标题设置面板及游戏内存档菜单",
    "images/shared-3-sheet1.webp": "标题菜单设置操作提示",
    "images/shared-4-sheet1.webp": "建造操作条",
    "images/shared-9-sheet6.webp": "读取存档确认框",
    "images/trinketmenubg-sheet0.webp": "饰品页签",
    "images/warpmenu_hiddentext-sheet0.webp": "传送目的地及建筑解锁名称",
    "images/warpmenubg-sheet0.webp": "传送页标题和返回",
    "images/worldmapbg-sheet0.webp": "世界地图地区名及展开",
}

# A separate allowlist stops a newly changed game resource from quietly
# entering the patch just because it appears in a generated inventory.
EXPECTED_CHANGED = set(IMAGE_LABELS) | {"data.json", "scripts/c3runtime.js"}


def bundle_entries(path, names=None):
    """Hash selected embedded files; offsets are relative to the c3ab data."""
    entries, _, start = read_directory(path)
    if names is not None:
        names = set(names)
        entries = [entry for entry in entries if entry["name"] in names]
    result = {}
    with open(path, "rb") as bundle:
        for entry in entries:
            digest = hashlib.sha256()
            bundle.seek(start + entry["offset"])
            remaining = entry["size"]
            while remaining:
                chunk = bundle.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError(f"truncated bundle entry: {entry['name']}")
                digest.update(chunk)
                remaining -= len(chunk)
            result[entry["name"]] = {
                "size": entry["size"], "sha256": digest.hexdigest(),
            }
    return result


def bundle_md5(path):
    digest = hashlib.md5()
    with open(path, "rb") as bundle:
        for chunk in iter(lambda: bundle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(vanilla, patch):
    base = bundle_entries(vanilla)
    localized = bundle_entries(patch)
    changed = sorted(name for name in base.keys() & localized.keys()
                     if base[name]["sha256"] != localized[name]["sha256"])
    added = sorted(localized.keys() - base.keys())
    removed = sorted(base.keys() - localized.keys())
    return {
        "schema_version": 1,
        "note": "assets.dat 为整包替换；卸载时还原英文原包，不逐张覆盖贴图。",
        "base_bundle": {"size": os.path.getsize(vanilla), "md5": bundle_md5(vanilla)},
        "patch_bundle": {"size": os.path.getsize(patch), "md5": bundle_md5(patch)},
        "modified": [
            {"path": name, "purpose": IMAGE_LABELS.get(name, "汉化文字与字形元数据"),
             "original": base[name], "localized": localized[name]}
            for name in changed
        ],
        "added": [
            {"path": name, "purpose": "新增中文字形图集" if
             name.startswith("images/cnfont_") else "新增补丁资源",
             "localized": localized[name]} for name in added
        ],
        "removed": [{"path": name, "original": base[name]} for name in removed],
    }


def write_manifest(vanilla, patch, output):
    inventory = create_manifest(vanilla, patch)
    with open(output, "w", encoding="utf-8") as dest:
        json.dump(inventory, dest, ensure_ascii=False, indent=2)
        dest.write("\n")
    return inventory


def changed_original_images(manifest, new_vanilla):
    """Detect changed atlas inputs before any updated game file is overwritten."""
    old = {item["path"]: item["original"]["sha256"]
           for item in manifest["modified"] if item["path"] in IMAGE_LABELS}
    if manifest.get("schema_version") != 1 or set(old) != set(IMAGE_LABELS):
        raise ValueError("resource inventory is missing original image fingerprints")
    current = bundle_entries(new_vanilla, old)
    return sorted(name for name, sha in old.items()
                  if name not in current or current[name]["sha256"] != sha)


def atlas_frame_pixels(bundle, atlas_names):
    """Read each referenced animation frame in its unrotated game orientation.

    A game's atlas packer can change sheet bytes and frame coordinates without
    changing any pixels shown to the player.  Unreferenced sheet pixels do not
    qualify as evidence that a baked text area has moved.
    """
    names = set(atlas_names)
    entries, _, start = read_directory(bundle)
    index = {entry["name"]: entry for entry in entries}
    if "data.json" not in index or not names <= index.keys():
        raise ValueError("missing atlas or project data")
    raw = {}
    with open(bundle, "rb") as source:
        for name in names | {"data.json"}:
            spec = index[name]
            source.seek(start + spec["offset"])
            raw[name] = source.read(spec["size"])
            if len(raw[name]) != spec["size"]:
                raise ValueError(f"truncated atlas/project data: {name}")
    project = json.loads(raw["data.json"])["project"]
    sheets = {name: Image.open(io.BytesIO(raw[name])).convert("RGBA") for name in names}
    found = {}
    for obj in project[3]:
        if not isinstance(obj, list) or len(obj) < 8 or not isinstance(obj[7], list):
            continue
        for anim in obj[7]:
            if not isinstance(anim, list) or len(anim) < 8 or not isinstance(anim[7], list):
                continue
            for frame_number, spec in enumerate(anim[7]):
                if not isinstance(spec, list) or len(spec) < 7 or spec[0] not in names:
                    continue
                name, _size, x, y, w, h, rotated = spec[:7]
                image = sheets[name]
                crop_w, crop_h = (h, w) if rotated else (w, h)
                if (min(x, y, w, h) < 0 or not w or not h
                        or x + crop_w > image.width or y + crop_h > image.height):
                    raise ValueError(f"invalid atlas frame bounds: {obj[0]}/{anim[0]}")
                crop = image.crop((x, y, x + crop_w, y + crop_h))
                if rotated:
                    crop = crop.transpose(Image.Transpose.ROTATE_90)
                key = (name, obj[0], anim[0], frame_number)
                if key in found:
                    raise ValueError(f"duplicate atlas frame: {key}")
                # Pixel equality alone is not enough if an anchor or collision
                # polygon changes; those are part of the frame's presentation.
                found[key] = (crop.size, crop.tobytes(), spec[7:])
    for name in names:
        if not any(key[0] == name for key in found):
            raise ValueError(f"atlas contains no referenced frames: {name}")
    return found


def unchanged_atlas_frames(previous_vanilla, new_vanilla, atlas_names):
    """Return True only if every named sprite frame survives pixel-for-pixel."""
    names = set(atlas_names)
    if not names:
        return True
    try:
        return atlas_frame_pixels(previous_vanilla, names) == atlas_frame_pixels(new_vanilla, names)
    except (ValueError, KeyError, IndexError, TypeError, OSError):
        return False
