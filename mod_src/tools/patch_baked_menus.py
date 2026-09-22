"""Repaint text baked into the warp/build sprite atlases, retaining frame geometry.

The Construct 3 SpriteFont hook cannot reach these labels: they are pixels in
rotated atlas frames.  Work exclusively from the extracted vanilla art so a
rebuild cannot paint over previously localised images.
"""
import os

from PIL import Image

from bdf import Bdf


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "fonts", "fusion-pixel-8px-monospaced-zh_hans.bdf")
INK = (7, 24, 33, 255)
PAPER = (219, 207, 181, 255)

WARP_NAMES = {
    "1": "翠绿山谷", "2": "暮色丛林", "3": "垂泪湿地", "4": "雪披峰",
    "5": "灼风沙地", "6": "忧郁草原", "7": "上城", "8": "泥痕台地",
}
BUILD_NAMES = (
    "神殿", "占卜师", "风车", "邮局", "花园", "剧场", "天文台", "试炼之井",
    None, None, "梦者小屋",
)
HIDDEN_NAMES = {"CatStatue": "猫雕像", "PhotoHut": "照相小屋",
                "DreamersHut": "梦者小屋", "Windmill1": "风车", "Windmill2": "风车"}


def draw_text(image, font, text, x, y, width):
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
        for gx, gy in pts:
            px, py = x + col * 8 + gx - min_x, y + 5 - gy
            if x <= px < x + width and y <= py < y + 8:
                pixels[px, py] = INK


def repaint(project, extracted, dev):
    font = Bdf(FONT)
    types = {ot[0]: ot for ot in project[3] if isinstance(ot, list) and ot}
    atlases = {}

    def frame(type_name, animation, edit):
        anim = next(a for a in types[type_name][7] if a[0] == animation)
        spec = anim[7][0]
        name, _size, x, y, w, h, rotated = spec[:7]
        if not rotated or not name.startswith("images/"):
            raise ValueError(f"unexpected atlas geometry: {type_name}/{animation}")
        if name not in atlases:
            atlases[name] = Image.open(os.path.join(extracted, name)).convert("RGBA")
        atlas = atlases[name]
        original = atlas.crop((x, y, x + h, y + w)).transpose(Image.Transpose.ROTATE_90)
        if original.size != (w, h):
            raise ValueError(f"wrong frame size for {type_name}/{animation}")
        edit(original)
        atlas.paste(original.transpose(Image.Transpose.ROTATE_270), (x, y))

    def label(text, area, align="left", paper=PAPER):
        def edit(img):
            x, y, w, h = area
            if h not in (7, 8) or x + w > img.width or y + h > img.height:
                raise ValueError(f"bad text rectangle: {area}")
            img.paste(paper, (x, y, x + w, y + h))
            start = x + (w - len(text) * 8) // 2 if align == "center" else x
            draw_text(img, font, text, start, y, x + w - start)
        return edit

    # Both headers are pixels in the menu backgrounds.  Only the letter cells
    # inside their existing frame are repainted; the surrounding border stays.
    for obj, text in (("WarpMenuBG", "传送"), ("BuildMenuBG", "建造")):
        spec = types[obj][6]
        name = spec[0]
        if name not in atlases:
            atlases[name] = Image.open(os.path.join(extracted, name)).convert("RGBA")
        label(text, (115, 2, 27, 7), align="center")(atlases[name])
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
            img.paste(PAPER, (72, 0, 72 + len(text) * 8, 8))
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
            img.paste((0, 0, 0, 0), (0, 0, 128, 8))
            img.paste(PAPER, (0, 0, 8 * len(text), 8))
            draw_text(img, font, text, 0, 0, 8 * len(text))
        frame("BuildMenu_HiddenText", anim, edit_hidden)

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
    print("重绘菜单图片:", sorted(sizes), "(传送目的地 8、建筑清单 9、解锁名称 5)")
    return set(sizes)
