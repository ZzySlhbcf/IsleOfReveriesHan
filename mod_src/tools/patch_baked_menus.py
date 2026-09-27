"""Repaint player-facing text baked into sprite atlases.

The Construct 3 SpriteFont hook cannot reach these labels: they are pixels in
rotated atlas frames.  Work exclusively from the extracted vanilla art so a
rebuild cannot paint over previously localised images.
"""
import json
import os

from PIL import Image

from bdf import Bdf


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "fonts", "fusion-pixel-8px-monospaced-zh_hans.bdf")
INK = (7, 24, 33, 255)
PAPER = (219, 207, 181, 255)
PALE_PAPER = (235, 223, 193, 255)
SHADOW = (120, 111, 120, 255)
OPTION_PAPER = (200, 183, 141, 255)

WARP_NAMES = {
    "1": "翠绿山谷", "2": "暮色丛林", "3": "垂泪湿地", "4": "雪披峰",
    "5": "灼风沙地", "6": "忧郁草原", "7": "上城", "8": "泥痕台地",
}
BUILD_NAMES = (
    "神殿", "占卜师", "风车", "邮局", "花园", "剧场", "天文台", "试炼之井",
    None, None, "梦者小屋", "英雄之谷",
)
HIDDEN_NAMES = {"CatStatue": "猫雕像", "PhotoHut": "照相小屋",
                "DreamersHut": "梦者小屋", "Windmill1": "风车一", "Windmill2": "风车二"}
WORLD_MAP_NAMES = {
    "1": "雪披峰", "2": "忧郁草原", "3": "灼风沙地", "4": "泥痕台地",
    "5": "上城", "6": "垂泪湿地", "7": "翠绿山谷", "8": "暮色丛林",
}
DUNGEON_NAMES = {
    "1": "朝圣者圣殿", "2": "蔓生神龛", "3": "巨龙遗骸",
    "4": "时间锁定别墅", "5": "雪覆矿场", "6": "岛屿深处",
}

# Speaker names are part of DialogueBox's artwork. Most animation IDs match
# the visible English text; these entries identify the frames that do not.
DIALOGUE_NAME_KEYS = {
    "OldFrog": "OLD FROG", "Rabbit": "MARBLE", "Rabbit_Dying": "MARBLE",
    "Backer_ArmSnake": "PETRISS", "Backer_Quaritz": "QUARTIZ",
    "Shop_Potion": "TOASTY", "Kiwi": "ATLAS", "Mole": "ARTHUR",
    "Mermaid": "GUINEVERE", "GreenDove": "CASSIO", "RedDove": "LUCIO",
    "Akedo": "MR. AKEDO", "AntEater": "ANT", "Musician": "CARMEN",
    "Pufferfish": "PUFFER", "BigTalkingTree": "TALKING TREE",
    "SmallTalkingTree": "TALKING TREE",
}
# Portrait-only, anonymous and unrevealed-name frames contain no English name.
DIALOGUE_UNNAMED = {
    "Default", "Hidden", "Notebook", "Ghost", "Hunter", "HungryMonster",
    "Backer_ArmSnake_Husk",
}
DIALOGUE_NAME_OVERRIDE = {
    "BigTalkingTree": "大树", "SmallTalkingTree": "小树",
}


def dialogue_speaker_names(project, dictionary):
    """Resolve exactly the name-bearing DialogueBox animations."""
    sprite = next(obj for obj in project[3] if isinstance(obj, list)
                  and obj[0] == "DialogueBox")
    resolved = {}
    for animation in sprite[7]:
        name = animation[0]
        if (name.startswith(("Husk_", "GoddessScene_"))
                or name in DIALOGUE_UNNAMED):
            continue
        key = DIALOGUE_NAME_KEYS.get(name, name.removeprefix("Backer_").upper())
        translation = (DIALOGUE_NAME_OVERRIDE.get(name) or dictionary.get(key)
                       or dictionary.get(name))
        if not translation or not any("\u4e00" <= c <= "\u9fff" for c in translation):
            raise ValueError(f"DialogueBox name missing Chinese translation: {name} / {key}")
        resolved[name] = translation
    return resolved


def draw_text(image, font, text, x, y, width, ink=INK):
    """Draw one 8px row from the same BDF used for the game's small glyphs."""
    if len(text) * 8 > width:
        raise ValueError(f"text exceeds frame width: {text!r}")
    pixels = image.load()
    for col, ch in enumerate(text):
        bits = font.rows_to_bits(ch)
        if not bits or not bits[0]:
            raise ValueError(f"missing 8px glyph: {ch}")
        pts = bits[0]
        min_x = min(a for a, _ in pts)
        glyph_width = max(a for a, _ in pts) - min_x + 1
        # Narrow ASCII glyphs (digits and key labels) otherwise hug the left
        # edge of their 8px cells next to full-width Chinese characters.
        inset = (8 - glyph_width) // 2
        for gx, gy in pts:
            px, py = x + col * 8 + inset + gx - min_x, y + 5 - gy
            if x <= px < x + width and y <= py < y + 8:
                pixels[px, py] = ink


def repaint(project, extracted, dev):
    font = Bdf(FONT)
    types = {ot[0]: ot for ot in project[3] if isinstance(ot, list) and ot}
    atlases = {}

    def image(name):
        if name not in atlases:
            atlases[name] = Image.open(os.path.join(extracted, name)).convert("RGBA")
        return atlases[name]

    def direct(type_name):
        spec = types[type_name][6]
        if not spec or spec[6] or not spec[0].startswith("images/"):
            raise ValueError(f"unexpected direct image geometry: {type_name}")
        return image(spec[0])

    def frame(type_name, animation, edit, frame_number=0):
        anim = next(a for a in types[type_name][7] if a[0] == animation)
        spec = anim[7][frame_number]
        name, _size, x, y, w, h, rotated = spec[:7]
        if not name.startswith("images/"):
            raise ValueError(f"unexpected atlas geometry: {type_name}/{animation}")
        atlas = image(name)
        crop_w, crop_h = (h, w) if rotated else (w, h)
        original = atlas.crop((x, y, x + crop_w, y + crop_h))
        if rotated:
            original = original.transpose(Image.Transpose.ROTATE_90)
        if original.size != (w, h):
            raise ValueError(f"wrong frame size for {type_name}/{animation}")
        edit(original)
        if rotated:
            original = original.transpose(Image.Transpose.ROTATE_270)
        atlas.paste(original, (x, y))

    def label(text, area, align="left", paper=PAPER, ink=INK):
        def edit(img):
            x, y, w, h = area
            if h not in (7, 8) or x + w > img.width or y + h > img.height:
                raise ValueError(f"bad text rectangle: {area}")
            img.paste(paper, (x, y, x + w, y + h))
            start = x + (w - len(text) * 8) // 2 if align == "center" else x
            draw_text(img, font, text, start, y, x + w - start, ink=ink)
        return edit

    def labels(*items):
        def edit(img):
            for text, area, align, paper, ink in items:
                label(text, area, align=align, paper=paper, ink=ink)(img)
        return edit

    # Both headers are pixels in the menu backgrounds.  Only the letter cells
    # inside their existing frame are repainted; the surrounding border stays.
    for obj, text in (("WarpMenuBG", "传送"), ("BuildMenuBG", "建造")):
        spec = types[obj][6]
        name = spec[0]
        label(text, (115, 2, 27, 7), align="center")(image(name))
    label("返回", (72, 119, 29, 8), align="center")(
        atlases[types["WarpMenuBG"][6][0]])

    for anim, text in WARP_NAMES.items():
        # Vanilla destination labels start at pixel 72; preserve the blank
        # sprite around each strip and the hidden "???" animation unchanged.
        def edit_warp(img, text=text):
            pixels = img.load()
            occupied = [x for x in range(img.width) if pixels[x, 0][3]]
            if not occupied or min(occupied) != 72:
                raise ValueError("unexpected warp label alignment")
            img.paste((0, 0, 0, 0), (72, 0, max(occupied) + 1, 8))
            # Hidden "???" remains visible behind short destinations like 上城
            # unless the opaque label strip covers all three question marks.
            img.paste(PAPER, (72, 0, 72 + max(24, len(text) * 8), 8))
            draw_text(img, font, text, 72, 0, 8 * len(text))
        frame("WarpMenu_HiddenText", anim, edit_warp)

    for row, text in enumerate(BUILD_NAMES):
        if text is not None:
            frame("BuildMenu_Pages", "1", label(text, (24, 24 + row * 8, 120, 8)))
    for anim in types["BuildMenu_Pages"][7]:
        if anim[0].startswith("Details_"):
            frame("BuildMenu_Pages", anim[0], label("需要", (24, 64, 32, 8)))
            frame("BuildMenu_Pages", anim[0], label("拥有", (88, 64, 32, 8)))
        elif anim[0].startswith("Destroy_"):
            frame("BuildMenu_Pages", anim[0], label("返还", (24, 64, 32, 8)))

    for anim, text in HIDDEN_NAMES.items():
        def edit_hidden(img, text=text):
            # This sprite is placed 8px to the left of the normal warp labels.
            # Leave its first cell empty to align all rows at the same x=72.
            # The warp background carries three gray question marks under each
            # row, so short names must still cover the full 24px of old ink.
            img.paste((0, 0, 0, 0), (0, 0, img.width, 8))
            width = max(24, 8 * len(text))
            img.paste(PAPER, (8, 0, 8 + width, 8))
            draw_text(img, font, text, 8, 0, width)
        frame("BuildMenu_HiddenText", anim, edit_hidden)

    # World map region names and the expand action.  Animation 0 is the
    # deliberately hidden "???" region and must remain hidden.
    for anim, text in WORLD_MAP_NAMES.items():
        def edit_world_map(img, name=text):
            label(name, (8, 0, 144, 8), align="center")(img)
            # The E binding is a separate SpriteFont at local x=88.
            # Centering "展开" at x=72 used to leave no gap before E.
            img.paste(PAPER, (48, 136, 112, 144))
            draw_text(img, font, "展开", 64, 136, 16)
        frame("WorldMapBG", anim, edit_world_map)

    settings = direct("SettingsBG")
    for text, area in (
        ("设置", (106, 2, 44, 8)),
        ("画面", (56, 16, 40, 8)),
        ("全屏", (74, 24, 22, 8)),
        ("窗口模式", (104, 24, 64, 8)),
        ("音频", (56, 40, 40, 8)),
        ("音乐", (100, 52, 32, 8)),
        ("音效", (100, 68, 32, 8)),
        ("按键图标", (56, 88, 48, 8)),
        ("键位", (74, 112, 32, 8)),
        ("确认", (64, 128, 48, 8)),
    ):
        label(text, area, align="center" if text == "设置" else "left")(settings)

    # The title/pause options panel is a second settings screen, distinct
    # from SettingsBG.  Keep controller glyphs and the option selectors.
    def edit_options(img):
        for text, area in (
            ("画面", (7, 10, 40, 8)),
            ("全屏", (17, 21, 24, 8)),
        ("窗口模式", (49, 21, 70, 8)),
            ("显示", (7, 34, 32, 8)),
            ("手柄", (17, 45, 50, 8)),
            ("键盘", (73, 45, 49, 8)),
            ("音乐", (7, 58, 40, 8)),
            ("音效", (7, 82, 40, 8)),
        ):
            label(text, area, paper=OPTION_PAPER)(img)
    frame("Options_BG", "Options_BG", edit_options)

    for anim in ("1-4_Keyboard", "1-4_Gamepad", "5-6_Keyboard", "5-6_Gamepad"):
        frame("Options_InputPrompt", anim, labels(
            ("选择", (32, 0, 28, 8), "center", PALE_PAPER, INK),
            ("返回", (88, 0, 24, 8), "center", PALE_PAPER, INK),
        ))
    for anim in ("Feats_Keyboard", "Feats_Gamepad"):
        frame("Options_InputPrompt", anim,
              label("返回", (32, 0, 32, 8), paper=PALE_PAPER))

    # The overview's BACK / TOGGLE ALL and title are pixels in Maps_Sprite,
    # not SpriteFont strings.  Leave visited-room cells and key indicators
    # alone; these strips are the existing opaque paper footer and heading.
    for anim in (f"WorldMap_{i}" for i in range(1, 9)):
        def edit_map_overview(img):
            img.paste(PAPER, (0, 136, 128, 144))
            draw_text(img, font, "返回：", 8, 136, 24)
            draw_text(img, font, "全部切换：", 56, 136, 40)
        frame("Maps_Sprite", anim, edit_map_overview)

    def edit_all_map(img):
        img.paste(PAPER, (0, 136, 128, 144))
        draw_text(img, font, "返回：", 8, 136, 24)
        draw_text(img, font, "全部切换：", 56, 136, 40)
        img.paste(PAPER, (16, 0, 112, 8))
        draw_text(img, font, "幻想之岛", 44, 0, 40)
    frame("Maps_Sprite", "WorldMap_All", edit_all_map)

    # Nameplates are baked into the dialogue sprite rather than SpriteFont.
    # Detect each original plaque's paper rail on row 7; its inner area ends
    # before the decorative right corner. Erase the English ink only in rows
    # 9..15, then center the Chinese glyphs in the existing nameplate width.
    with open(os.path.join(ROOT, "trans", "dict.json"), encoding="utf-8") as source:
        name_dictionary = json.load(source)
    for animation, translation in dialogue_speaker_names(project, name_dictionary).items():
        def edit_speaker(img, text=translation, speaker=animation):
            if img.size != (256, 56) or img.getpixel((12, 7)) != PAPER:
                raise ValueError(f"unexpected dialogue nameplate: {speaker}")
            end = 12
            while end < img.width and img.getpixel((end, 7)) == PAPER:
                end += 1
            width = end - 12
            step = 8 if len(text) * 8 <= width else 7
            if len(text) * step > width:
                raise ValueError(f"speaker name exceeds original plaque: {speaker} {text}")
            img.paste(INK, (12, 9, end, 16))
            x = 12 + (width - len(text) * step) // 2
            if step == 8:
                draw_text(img, font, text, x, 9, len(text) * step, ink=PAPER)
            else:
                # CJK 8px glyphs have 7px of ink. Short original plaques
                # (Pox/Iris/Kiwi) fit three characters without blank columns.
                pixels = img.load()
                for col, ch in enumerate(text):
                    bits = font.rows_to_bits(ch)
                    if not bits or not bits[0]:
                        raise ValueError(f"missing speaker glyph: {ch}")
                    min_x = min(gx for gx, _ in bits[0])
                    for gx, gy in bits[0]:
                        px, py = x + col * step + gx - min_x, 9 + 5 - gy
                        if 12 <= px < end and 9 <= py < 16:
                            pixels[px, py] = PAPER
        for number in range(len(next(a for a in types["DialogueBox"][7]
                                     if a[0] == animation)[7])):
            frame("DialogueBox", animation, edit_speaker, frame_number=number)

    # Controls screen: input glyphs (WASD, arrows and controller buttons) are
    # controls rather than prose, so retain them while translating labels.
    controls = direct("ControlsBG")
    for text, area, align in (
        ("控制", (106, 2, 44, 8), "center"),
        ("移动", (64, 16, 32, 8), "left"),
        ("按键重新绑定", (56, 32, 144, 8), "center"),
        ("操作", (56, 44, 48, 8), "center"),
        ("控制器", (120, 44, 40, 8), "left"),
        ("E键", (168, 44, 32, 8), "left"),
        ("互动", (64, 56, 48, 8), "left"),
        ("菜单", (64, 64, 48, 8), "left"),
        ("地图", (64, 72, 48, 8), "left"),
        ("工具1", (64, 80, 48, 8), "left"),
        ("工具2", (64, 88, 48, 8), "left"),
        ("工具3", (64, 96, 48, 8), "left"),
        ("跳跃", (64, 104, 48, 8), "left"),
        ("精灵", (64, 112, 48, 8), "left"),
        ("确认", (64, 128, 48, 8), "left"),
        ("重置", (168, 128, 32, 8), "left"),
    ):
        label(text, area, align=align)(controls)
    frame("ControlsMenu_Move", "Gamepad",
          label("左摇杆/十字键", (0, 8, 80, 8), align="center"))
    for anim in ("Keyboard_WASD", "Keyboard_Arrows"):
        frame("ControlsMenu_Move", anim,
              label("方向键", (43, 8, 37, 8), align="center"))

    # Save selection uses a dark one-pixel foreground over a grey shadow.
    for anim, text in (("LoadGame", "读取"), ("NewGame", "新建"), ("Back", "返回")):
        def edit_file_label(img, text=text):
            img.paste((0, 0, 0, 0), (0, 0, img.width, img.height))
            x = (img.width - len(text) * 8) // 2
            draw_text(img, font, text, x - 1, 3, img.width - x + 1, ink=SHADOW)
            draw_text(img, font, text, x, 4, img.width - x, ink=INK)
        frame("FileSelect_Cursor", anim, edit_file_label)

    # Each of the three selections has two alternating animation frames.
    # All six contain baked SAVE/TRINKET/BACK, so painting only the first
    # frame makes the menu alternate between Chinese and English.
    def edit_save_trinket_back(img):
        if img.size != (256, 144):
            raise ValueError(f"unexpected save-menu frame size: {img.size}")
        # Opaque paper starts at x=86.  Leave the purple selection marker at
        # x=88..94, the border, and every pixel outside the word cells intact.
        for y, text in ((60, "保存"), (68, "饰品"), (76, "返回")):
            img.paste(PAPER, (96, y, 160, y + 8))
            draw_text(img, font, text, 96, y, 64)
    for animation in types["SaveTrinketBack"][7]:
        for frame_number in range(len(animation[7])):
            frame("SaveTrinketBack", animation[0], edit_save_trinket_back,
                  frame_number=frame_number)

    # Confirmation window: preserve the A/B, Space/Z input glyphs and frame.
    for anim in ("GamePad", "Keyboard"):
        frame("Confirm_Load", anim, labels(
            ("确认", (52, 56, 56, 8), "center", PALE_PAPER, INK),
            ("是", (72, 66, 32, 8), "left", PALE_PAPER, INK),
            ("否", (72, 76, 32, 8), "left", PALE_PAPER, INK),
        ))

    # Build bar states use the same geometry, with BUILD greyed out in NoBuild.
    for anim in ("YesBuild", "NoBuild", "DetailsClosed", "Destroy"):
        frame("BuildMenu_BuildPrompt", anim,
              label("返回", (0, 8, 40, 8), align="center"))
    frame("BuildMenu_BuildPrompt", "YesBuild",
          label("建造", (56, 8, 40, 8), align="center"))
    frame("BuildMenu_BuildPrompt", "NoBuild",
          label("建造", (56, 8, 40, 8), align="center", ink=SHADOW))
    frame("BuildMenu_BuildPrompt", "Destroy",
          label("拆除", (56, 8, 56, 8), align="center"))

    # Inventory tabs and compact menu panels.
    label("虫子", (108, 2, 32, 8), align="center")(direct("DisplayBugMenuBG"))
    label("饰品", (104, 2, 48, 8), align="center")(direct("TrinketMenuBG"))
    fashion = direct("FashionMenuBG")
    for text, y in (("绿色", 48), ("蓝色", 56), ("红色", 64),
                    ("紫色", 72), ("取消", 88)):
        label(text, (104, y, 48, 8))(fashion)

    # Album prompts retain the purple keycap glyphs and only replace verbs.
    for anim in ("Arrows_Keyboard-OLD", "Arrows_Gamepad-OLD"):
        frame("Album_InputPrompt", anim, labels(
            ("选择", (34, 8, 24, 8), "center", PAPER, INK),
            ("返回", (90, 8, 22, 8), "center", PAPER, INK),
        ))
    for anim in ("Photos_Keyboard-OLD", "Photos_Gamepad-OLD", "Photos_Gamepad",
                 "Photos_Keyboard", "Arrows_Gamepad", "Arrows_Keyboard"):
        frame("Album_InputPrompt", anim,
              label("返回", (40, 8, 32, 8), align="left"))

    pause = direct("MP_Pause")
    label("继续", (104, 64, 48, 8), align="left")(pause)
    label("醒来", (104, 72, 48, 8), align="left")(pause)

    # The six dungeon splash cards have a dedicated 28px caption panel.
    for anim, text in DUNGEON_NAMES.items():
        frame("Dungeon_Title", anim, labels(
            (f"第{anim}层", (4, 96, 120, 8), "center", PAPER, INK),
            (text, (4, 104, 120, 8), "center", PAPER, INK),
        ))

    sizes = {}
    for name, atlas in atlases.items():
        out = os.path.join(dev, name)
        atlas.save(out, "WEBP", lossless=True, quality=100, method=4, exact=True)
        sizes[name] = os.path.getsize(out)

    def update_sizes(node):
        if isinstance(node, list):
            if len(node) > 1 and isinstance(node[0], str) and node[0] in sizes \
                    and isinstance(node[1], int):
                node[1] = sizes[node[0]]
            for child in node:
                update_sizes(child)
        elif isinstance(node, dict):
            if node.get("name") in sizes and isinstance(node.get("size"), int):
                node["size"] = sizes[node["name"]]
            for child in node.values():
                update_sizes(child)

    update_sizes(project)
    print("重绘菜单图片:", sorted(sizes),
          "(传送、建造、世界地图详情、两套设置页、控制、存档、页签、相册、暂停、地牢标题)")
    return set(sizes)
