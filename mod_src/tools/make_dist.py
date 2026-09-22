#!/usr/bin/env python3
"""Stage the distributable: install/uninstall scripts + readme."""
import datetime
import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
# 游戏目录：优先环境变量 CN_GAME，其次本机实测路径。安装.bat / 卸载.bat /
# 官方更新后重建.bat 里的 GAME= 都会写成这个值。
GAME = os.environ.get("CN_GAME") or r"D:\Games\Steam\steamapps\common\Isle of Reveries"

# 版本号：每次重建时按当天日期自动生成（官方更新后重建出来的包自然带新日期）。
_BUILD_DAY = os.environ.get("CN_BUILD_DAY") or datetime.date.today().strftime("%Y-%m-%d")
VERSION = os.environ.get("CN_PATCH_VERSION") or (
    f"润色版 对白11x11/菜单与说明9x10 ({_BUILD_DAY})")
VERSION_TAG = os.environ.get("CN_PATCH_TAG") or f"cn_patch_rebuild_{_BUILD_DAY}"
GLYPH_COUNT = os.environ.get("CN_GLYPH_COUNT") or "1857"

INSTALL = r"""@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title Isle of Reveries 简体中文补丁 - 安装

set "GAME={game}"
set "PATCHVER={ver}"
set "BASEMD5={base_md5}"
set "PATCHMD5={patch_md5}"

if not exist "%GAME%\Isle_of_Reveries.exe" (
  echo [错误] 没有找到游戏目录: %GAME%
  echo         请用记事本打开本文件, 把上面的 GAME= 改成你的游戏安装路径后重试.
  pause
  exit /b 1
)

if not exist "%GAME%\www\assets.dat" (
  echo [错误] 没有找到 %GAME%\www\assets.dat
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat"
set "CURMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TARGET -Algorithm MD5).Hash.ToLowerInvariant()"') do set "CURMD5=%%H"
if not defined CURMD5 (
  echo [错误] 无法读取当前游戏资源包的 MD5，安装已取消。
  pause
  exit /b 1
)

if /I "%CURMD5%"=="%PATCHMD5%" goto writepatch
if /I not "%CURMD5%"=="%BASEMD5%" (
  echo [错误] 当前游戏资源版本与本补丁不匹配，安装已取消。
  echo         这通常表示游戏刚刚更新；请运行 官方更新后重建.bat，
  echo         不要用旧 assets.dat 覆盖新版游戏，否则可能出现无声或资源异常。
  pause
  exit /b 1
)

echo 备份当前匹配的英文原版 www\assets.dat -^> www\assets.dat.cn-backup
copy /Y "%GAME%\www\assets.dat" "%GAME%\www\assets.dat.cn-backup" >nul
if errorlevel 1 (
  echo [错误] 备份失败，安装已取消。
  pause
  exit /b 1
)

:writepatch
echo 写入汉化资源包 ^(版本: %PATCHVER%^) ...
copy /Y "%~dp0www\assets.dat" "%GAME%\www\assets.dat" >nul
if errorlevel 1 (
  echo [错误] 写入失败, 请确认游戏没有在运行.
  pause
  exit /b 1
)

for %%I in ("%~dp0www\assets.dat") do set "SRCSIZE=%%~zI"
for %%I in ("%GAME%\www\assets.dat") do set "DSTSIZE=%%~zI"
if not "%SRCSIZE%"=="%DSTSIZE%" (
  echo [错误] 校验失败: 源 %SRCSIZE% 字节, 目标 %DSTSIZE% 字节.
  pause
  exit /b 1
)

echo.
echo 安装完成! 版本 %PATCHVER% ^(%DSTSIZE% 字节^)
echo 启动游戏即为简体中文; 卸载请运行 卸载.bat.
echo.
pause
"""

UNINSTALL = r"""@echo off
chcp 936 >nul
setlocal
title Isle of Reveries 简体中文补丁 - 卸载

set "GAME={game}"
set "BASEMD5={base_md5}"
set "PATCHMD5={patch_md5}"


if not exist "%GAME%\www\assets.dat.cn-backup" (
  echo [错误] 没有找到备份文件 www\assets.dat.cn-backup, 无法自动还原.
  echo         可在 Steam 里右键游戏 - 属性 - 已安装文件 - 验证文件完整性 来还原.
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat"
set "CURMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TARGET -Algorithm MD5).Hash.ToLowerInvariant()"') do set "CURMD5=%%H"
if /I "%CURMD5%"=="%BASEMD5%" (
  echo 当前已经是与本补丁匹配的英文原版，无需卸载。
  pause
  exit /b 0
)
if /I not "%CURMD5%"=="%PATCHMD5%" (
  echo [错误] 当前资源包不是本补丁安装的版本，拒绝用旧备份覆盖。
  echo         若游戏刚更新，请使用 Steam 的“验证文件完整性”还原。
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat.cn-backup"
set "BAKMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TARGET -Algorithm MD5).Hash.ToLowerInvariant()"') do set "BAKMD5=%%H"
if /I not "%BAKMD5%"=="%BASEMD5%" (
  echo [错误] 备份文件与本补丁对应的英文原版不匹配，拒绝还原。
  echo         请使用 Steam 的“验证文件完整性”。
  pause
  exit /b 1
)

copy /Y "%GAME%\www\assets.dat.cn-backup" "%GAME%\www\assets.dat" >nul
echo 已还原为英文原版. 备份文件保留在 www\assets.dat.cn-backup
pause
"""

README = r"""Isle of Reveries 简体中文汉化补丁
======================================

一、安装
--------
1. 关闭游戏（也可以在 Steam 里先退出）。
2. 双击 安装.bat
   - 它会先确认游戏资源版本与本补丁匹配；不匹配时会拒绝覆盖
   - 确认匹配后，把原版 www\assets.dat 备份成 www\assets.dat.cn-backup
   - 然后把汉化包写入 www\assets.dat
3. 启动游戏，即为简体中文。

如果你的游戏不在 {game}，
用记事本打开 安装.bat / 卸载.bat，改开头的 GAME= 那一行即可。

二、卸载
--------
双击 卸载.bat，会把 www\assets.dat 还原成英文原版。
若备份丢失，可在 Steam 里：右键游戏 → 属性 → 已安装文件 → 验证文件完整性。

三、原理与范围
--------------
游戏是 Construct 3（Scirra）引擎导出，全部资源打包在 www\assets.dat 里。
本补丁替换了该文件，改动包括：
  * 游戏内全部文本（对白、物品说明、菜单、任务、提示）在“显示层”被替换为简体中文；
  * 字体：正文类文字（对白/物品说明/菜单/任务/制作名单，共 11 个文字对象）
    换成 11x11 点阵中文字形表 + 1px 字距；HUD 数字与按键字母保持原 8x8 不动（避免破坏版面）；
  * 每个字体对象都用开源像素字体 Fusion Pixel Font 重画/扩字，共 {glyphs} 个汉字，无缺字；
  * 中文按 CJK 规则自动换行。
补丁不改动游戏逻辑、事件表与存档结构：
  * 显示层拦截，所以存档、多人联机、成就判定用的仍是原始英文串；
  * 因此存档与官方版本完全兼容。

已知限制 / 可调项
------------------
1. 标题 Logo、菜单背景、部分 UI 是“烘焙在图里的美术字”，无法通过文本替换翻译；
   （标题画面的 \"Isle of Reveries\"、\"START GAME\" 等属于图片）
2. 中文字号：正文用 11x11 点阵（字库 12px 字体的汉字墨迹本就 11x11，所以是 1:1 落格，
   不缩样），字与字之间留 1px 缝。原版英文是 8x8，汉字在 8x8 下笔画会糊成一团，
   所以正文放到 11x11（清晰度换版面）。副作用：文字比原版大，个别很窄的文本框可能换行。
   想再调大小：改 mod_src\tools\build_cn_patch.py 的 CELL12（字格）与 CELL_SPACING（字距）
   后重跑构建脚本即可（CELL12=10 会更接近原版面、CELL12=12 更清楚）。
3. 制作人员名单里的个人姓名保留英文；
4. Steam 若执行“验证文件完整性”会覆盖 assets.dat，需重新运行 安装.bat。

官方更新了游戏怎么办
--------------------
Steam 更新会整体覆盖 www\assets.dat，补丁会被冲掉（游戏回到英文）。
补丁的内容只在这一个文件里，被覆盖后不留任何残留，所以不会导致游戏出错。
更新后想恢复中文，有两条路：
  A. 运行本目录里的 官方更新后重建.bat —— 它会以新版资源包为底重新生成并安装汉化
     （先退出游戏；脚本会自动备份新版英文包、重新解包、重建、校验、安装）。
  B. 让我来重建（把新版 assets.dat 或游戏目录给我即可，几分钟出成品）。
两点要注意：
  * 更新后不要直接运行旧版 安装.bat；新版安装器会检测资源包 MD5 并拒绝覆盖，
    请改为运行 官方更新后重建.bat。
  * 更新后**不要**再运行 卸载.bat：它还原的是更新前的旧英文包，旧资源配新程序可能出问题。
    要还原英文请用 Steam 的“验证文件完整性”。
  * 官方新增或改写的英文句子会原样显示英文（补丁只按“英文原文”精确匹配译文，
    匹配不到就不动它，绝不会显示乱码或空白）。补译时把新句子加进
    mod_src\trans\dict.json 再重跑重建脚本即可。

已做的验证
----------
* 资源包解包→重打包结果与原文件逐字节一致（保证不会破坏资源结构）；
* 中文字形渲染正确：24 个字体对象 × {glyphs} 个汉字，逐格与字体文件点阵做像素比对，
  **全部一致、无上下翻转、无错位**；
* 全部译文用字（{glyphs} 个不同汉字）在使用的开源像素字体中均有字形，无缺字；
* 补丁安装后游戏可正常启动；实机确认对白/菜单/物品说明显示为中文，
  字格 11x11、字距 1px 生效；
* 安装/卸载/官方更新后重建三个脚本均在测试副本上实测通过；
* 补丁只改 www\assets.dat 一个文件，不改动 exe、存档与 Steam 配置；
* 弹琴传送页与建造页原本烘焙在图片里的菜单文字也已重绘为中文。

已知会影响观感的地方
--------------------
* 个别很窄的文本框可能换行（中文比英文占位大）；
* 由游戏运行时拼接的文本（例如“掉落：”+ 物品名）按整体匹配翻译，个别可能未译；
* 制作人员名单里的个人姓名、少量内部标识（BGM、XBOXONE 等）保留英文。
如果发现漏译（仍显示英文）或排版问题，把截图和出现位置发我，我来补译或调整。

四、文件清单
------------
www\assets.dat ......... 汉化后的资源包（直接使用）
安装.bat ................ 安装汉化（会先备份英文原版）
卸载.bat ................ 还原英文原版
官方更新后重建.bat ...... 官方更新游戏后，用它以新版资源包重建汉化
版本.txt ................ 本补丁的版本号、字节数与 md5（装完可核对）
说明.txt ................ 本文件
mod_src\ ................ 源码与工具（可自行修改后重新构建；需要 Python3 + pillow）
    tools\c3bundle.py            Construct 3 资源包解包/重打包
    tools\fontsheet.py           字形表生成（从 BDF 点阵字体造中文字形表）
    tools\bdf.py                 像素字体（BDF）解析
    tools\build_cn_patch.py      一键重新构建本补丁（读 trans\dict.json）
    tools\update_repack.py       官方更新后重建
    tools\verify_glyphs.py       逐格字形校验（对照字体原件）
    tools\normalize_terms.py     术语归一
    tools\make_dist.py          生成 dist 交付目录
    trans\dict.json              英中对照表（4012 条，可自行修订）
    trans\dict_round1.json       最初的机翻版本（留档对比）
    fonts\                       所用开源像素字体（Fusion Pixel Font）及许可证 OFL
"""


def main():
    os.makedirs(DIST, exist_ok=True)
    bundle = os.path.join(DIST, "www", "assets.dat")
    vanilla = os.environ.get("CN_VANILLA_BUNDLE")
    if not vanilla or not os.path.isfile(vanilla):
        sys.exit("[错误] 缺少 CN_VANILLA_BUNDLE，无法生成带版本保护的安装器")
    if not os.path.isfile(bundle):
        sys.exit(f"[错误] 找不到待发布资源包: {bundle}")
    base_md5 = hashlib.md5(open(vanilla, "rb").read()).hexdigest()
    patch_md5 = hashlib.md5(open(bundle, "rb").read()).hexdigest()
    with open(os.path.join(DIST, "安装.bat"), "w", encoding="gbk", newline="\r\n") as f:
        f.write(INSTALL.replace("{game}", GAME).replace("{ver}", VERSION)
                .replace("{base_md5}", base_md5).replace("{patch_md5}", patch_md5))
    with open(os.path.join(DIST, "卸载.bat"), "w", encoding="gbk", newline="\r\n") as f:
        f.write(UNINSTALL.replace("{game}", GAME)
                .replace("{base_md5}", base_md5).replace("{patch_md5}", patch_md5))
    with open(os.path.join(DIST, "说明.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(README.replace("{game}", GAME).replace("{glyphs}", GLYPH_COUNT))
    # 官方更新后重建脚本（模板见 tools/repack_bat.txt）
    tpl = os.path.join(ROOT, "tools", "repack_bat.txt")
    if os.path.exists(tpl):
        with open(tpl, encoding="utf-8") as f:
            body = f.read()
        with open(os.path.join(DIST, "官方更新后重建.bat"), "w", encoding="gbk",
                  newline="\r\n") as f:
            f.write(body.replace("{game}", GAME))
        print("官方更新后重建.bat",
              os.path.getsize(os.path.join(DIST, "官方更新后重建.bat")))

    # mod_src：源码与工具（每次重建都同步一份，避免与 tools/ 脱节）
    ms = os.path.join(DIST, "mod_src")
    for sub in ("tools", "trans", "fonts"):
        os.makedirs(os.path.join(ms, sub), exist_ok=True)
    # 只带运行需要的工具；一次性/测试脚本、__pycache__、*.orig 不进交付
    SKIP = {"test_repack_bat.py", "verify_zip.py", "verify_ingame.py",
            "render_font_cmp.py", "mk_batches.py", "mk_corpus.py", "mk_credits.py",
            "coverage_check.py", "coverage_check_data.py", "normalize_terms.py",
            "normalize_terms2.py", "inventory.py", "detect_orientation.py",
            "merge_trans.py", "make_zip.py", "deploy.py", "cdp.py"}
    for fn in sorted(os.listdir(os.path.join(ROOT, "tools"))):
        if fn in SKIP or fn.endswith((".pyc", ".orig")):
            continue
        if fn.endswith((".py", ".js", ".txt")):
            shutil.copy(os.path.join(ROOT, "tools", fn), os.path.join(ms, "tools", fn))
    for fn in ("dict.json", "dict_round1.json"):
        p = os.path.join(ROOT, "trans", fn)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(ms, "trans", fn))
    for fn in sorted(os.listdir(os.path.join(ROOT, "fonts"))):
        p = os.path.join(ROOT, "fonts", fn)
        if os.path.isfile(p) and fn.endswith((".bdf", ".txt", ".md")):
            shutil.copy(p, os.path.join(ms, "fonts", fn))
    if os.path.isdir(os.path.join(ROOT, "fonts", "LICENSES")):
        dst = os.path.join(ms, "fonts", "LICENSES")
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(ROOT, "fonts", "LICENSES"), dst)
    for dirpath, dirnames, _fn in os.walk(ms):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
                dirnames.remove(d)
    print("mod_src 已同步:", len(os.listdir(os.path.join(ms, "tools"))), "个工具文件")

    # 版本标记：便于确认装的是哪一版
    h = hashlib.md5(open(bundle, "rb").read()).hexdigest() if os.path.exists(bundle) else "-"
    with open(os.path.join(DIST, "版本.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(f"Isle of Reveries 汉化补丁\n版本: {VERSION} ({VERSION_TAG})\n"
                f"构建日期: {_BUILD_DAY}\n"
                f"字符数: {GLYPH_COUNT}\n"
                f"资源包: www\\assets.dat\n字节数: "
                f"{os.path.getsize(bundle) if os.path.exists(bundle) else '-'}\n"
                f"md5: {h}\n"
                f"安装后 www\\assets.dat 的字节数/md5 应与此一致；\n"
                f"若不一致说明没装上（多半是安装时游戏没关）。\n")
    for n in ("安装.bat", "卸载.bat", "说明.txt", "版本.txt"):
        print(n, os.path.getsize(os.path.join(DIST, n)))


if __name__ == "__main__":
    main()
