#!/usr/bin/env python3
r"""Audit player-facing text that can bypass the normal dictionary hook.

The report separates three sources:
  * ordinary event literals handled by the SpriteFont SetText hook;
  * strings assembled at runtime from a prefix, number and suffix;
  * English labels baked into sprite images.

Usage:
  python tools/audit_localization.py --bundle "...\www\assets.dat.cn-backup"
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from c3bundle import read_directory  # noqa: E402


ARROW_LITERAL = re.compile(r'\(\)\s*=>\s*"((?:[^"\\]|\\.){2,1000})"')
DYNAMIC_SENTENCE = re.compile(
    r'and\("((?:[^"\\]|\\.)*)"\s*,[^;]{0,300}?\)\s*\+\s*'
    r'"((?:[^"\\]|\\.)*)"')

# Confirmed visible sprite/image objects that still contain English pixels.
# This is deliberately curated: animation/state names are not automatically
# classified as text, because translating an internal identifier breaks logic.
BAKED_PENDING = {
    "TitleScreenBG": "游戏 Logo（美术字）",
}


def read_entry(bundle, name):
    entries, _, data_start = read_directory(bundle)
    entry = next((e for e in entries if e["name"] == name), None)
    if not entry:
        raise FileNotFoundError(f"bundle entry not found: {name}")
    with open(bundle, "rb") as f:
        f.seek(data_start + entry["offset"])
        return f.read(entry["size"])


def decode_js_string(value):
    try:
        return json.loads('"' + value + '"')
    except json.JSONDecodeError:
        return None


def translator(dictionary):
    ci, conflicts = {}, set()
    for key, value in dictionary.items():
        lower = key.lower()
        if lower in ci and ci[lower] != value:
            conflicts.add(lower)
        ci[lower] = value

    def lookup(text):
        if text in dictionary:
            return dictionary[text]
        lower = text.lower()
        if lower not in conflicts:
            return ci.get(lower)
        return None

    def translate(text):
        hit = lookup(text)
        if hit is not None:
            return hit
        trimmed = text.strip()
        if trimmed != text:
            hit = lookup(trimmed)
            if hit is not None:
                return text.replace(trimmed, hit)
        amount = re.match(r"^(.+?)\s+x\s+([0-9]+)$", text)
        if amount:
            hit = lookup(amount.group(1))
            if hit is not None:
                return hit + " x " + amount.group(2)
        dynamic = re.match(r"^Currently built: ([0-9]+)(/1)?$", text)
        if dynamic:
            return "当前已建：" + dynamic.group(1) + (dynamic.group(2) or "")
        dynamic = re.match(
            r"^Hrrmm\.\.\. You have found ([0-9]+) of the 16 bugs scattered across the Isle\.$",
            text)
        if dynamic:
            return f"嗯……散落全岛的16只虫子，你已经找到了{dynamic.group(1)}只。"
        dynamic = re.match(
            r"^You have ([0-9]+) Leaves\. Come back when you've found ([0-9]+)!$", text)
        if dynamic:
            return f"你现在有{dynamic.group(1)}片叶子。找到{dynamic.group(2)}片后再来！"
        dynamic = re.match(r"^Lief has ([0-9]+) Goddess Seeds?\.$", text)
        if dynamic:
            return f"利夫拥有{dynamic.group(1)}颗女神种子。"
        dynamic = re.match(r"^Lief has ([0-9]+) Akedo (?:Leaf|Leaves)\.$", text)
        if dynamic:
            return f"利夫拥有{dynamic.group(1)}片阿凯多之叶。"
        label = re.match(r"^([^:]{2,40}):\s*(.+)$", text)
        if label:
            for candidate in (label.group(1), label.group(1).strip()):
                hit = lookup(candidate)
                if hit is not None:
                    return hit + "：" + label.group(2)
        return text

    return translate


def natural_event_misses(runtime, translate):
    values = set()
    for match in ARROW_LITERAL.finditer(runtime):
        value = decode_js_string(match.group(1))
        if value is not None:
            values.add(value)
    misses = []
    for text in values:
        if translate(text) != text:
            continue
        # Bug-house countdown messages are player-facing single words.  The
        # long-sentence filter below otherwise misses "Ready..."/"Set...".
        if re.fullmatch(r"(?:Ready|Set|Go)(?:\.{2,}|!{2,})", text, re.I):
            misses.append(text)
            continue
        if len(text) < 4 or " " not in text:
            continue
        if not re.search(r"[a-z]{2}", text) or "_" in text or re.search(r"[\\/]", text):
            continue
        if re.match(r"^(https?:|wss?:|Room \d+ - |[A-Za-z]+\s*-\s*"
                    r"(Item|NPC|State|Controls?|Room|Scene|Menu|Event))", text):
            continue
        misses.append(text)
    return sorted(misses, key=lambda text: (-len(text), text))


def dynamic_misses(runtime, translate):
    results = {}
    for match in DYNAMIC_SENTENCE.finditer(runtime):
        prefix = decode_js_string(match.group(1))
        suffix = decode_js_string(match.group(2))
        if prefix is None or suffix is None or not re.search(r"[A-Za-z]", prefix + suffix):
            continue
        sample = prefix + "1" + suffix
        if translate(sample) == sample and (" " in prefix or " " in suffix):
            results[(prefix, suffix)] = sample

    # A frequent form has no suffix: and("Currently built: ", count).
    for prefix in re.findall(r'and\("((?:[^"\\]|\\.)*)"\s*,', runtime):
        prefix = decode_js_string(prefix)
        if prefix == "Currently built: ":
            sample = prefix + "1"
            if translate(sample) == sample:
                results[(prefix, "")] = sample
    return [results[key] for key in sorted(results)]


def static_font_misses(project, translate):
    """Check initial text stored on actual SpriteFont instances.

    Single keyboard letters and blank placeholders are intentional.  Unlike a
    full data.json string walk, this does not confuse animation/state names for
    display text.
    """
    font_types = {
        index for index, item in enumerate(project[3])
        if isinstance(item, list) and len(item) > 1 and item[1] == 14
    }
    misses = set()
    for layout in project[5]:
        if not isinstance(layout, list) or len(layout) <= 10 or not isinstance(layout[10], list):
            continue
        for layer in layout[10]:
            if not isinstance(layer, list) or len(layer) <= 14 or not isinstance(layer[14], list):
                continue
            for instance in layer[14]:
                if not isinstance(instance, list) or len(instance) < 6 or instance[1] not in font_types:
                    continue
                state = next((candidate for candidate in instance[3:]
                              if isinstance(candidate, list) and len(candidate) >= 13
                              and isinstance(candidate[0], str)
                              and isinstance(candidate[2], int)
                              and isinstance(candidate[3], int)
                              and isinstance(candidate[4], str)
                              and len(candidate[4]) > 40), None)
                if not state:
                    continue
                text = state[0]
                if not re.search(r"[A-Za-z]", text) or translate(text) != text:
                    continue
                if re.fullmatch(r"[A-Z0-9]", text):
                    continue
                misses.add(text)
    return sorted(misses)


def baked_inventory(project):
    types = {item[0]: item for item in project[3] if isinstance(item, list) and item}
    found, absent = [], []
    for name, description in BAKED_PENDING.items():
        item = types.get(name)
        if not item:
            absent.append(name)
            continue
        animations = []
        if len(item) > 7 and isinstance(item[7], list):
            animations = [a[0] for a in item[7] if isinstance(a, list) and a]
        found.append((name, description, animations))
    return found, absent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", default=os.environ.get("CN_VANILLA_BUNDLE"))
    parser.add_argument("--dict", default=os.path.join(ROOT, "trans", "dict.json"))
    args = parser.parse_args()
    if not args.bundle or not os.path.isfile(args.bundle):
        parser.error("provide --bundle or set CN_VANILLA_BUNDLE")

    dictionary = json.load(open(args.dict, encoding="utf-8"))
    runtime = read_entry(args.bundle, "scripts/c3runtime.js").decode("utf-8", "ignore")
    project = json.loads(read_entry(args.bundle, "data.json").decode("utf-8"))["project"]
    translate = translator(dictionary)

    exact = natural_event_misses(runtime, translate)
    static = static_font_misses(project, translate)
    dynamic = dynamic_misses(runtime, translate)
    baked, absent = baked_inventory(project)

    print(f"词典: {len(dictionary)} 条")
    print(f"普通自然语言漏译候选: {len(exact)}")
    for text in exact:
        print("  [TEXT]", text)
    print(f"SpriteFont 静态实例漏译: {len(static)}")
    for text in static:
        print("  [STATIC]", text)
    print(f"运行时拼接漏译句型: {len(dynamic)}")
    for text in dynamic:
        print("  [DYNAMIC]", text)
    print(f"确认含英文像素的界面对象: {len(baked)}")
    for name, description, animations in baked:
        suffix = f"；动画: {', '.join(animations)}" if animations else ""
        print(f"  [IMAGE] {name}: {description}{suffix}")
    if absent:
        print("未找到的审计对象:", ", ".join(absent))
    return 1 if exact or static or dynamic or baked else 0


if __name__ == "__main__":
    sys.exit(main())
