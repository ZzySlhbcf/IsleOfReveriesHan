# Isle of Reveries 简体中文汉化补丁

为 Steam 版 **Isle of Reveries** 制作的简体中文汉化补丁。项目包含可直接安装的补丁包、汉化词典、像素字体资源、构建工具和校验脚本。

> 当前补丁信息见 [版本.txt](版本.txt)。根目录的 `www/assets.dat` 是可直接使用的汉化资源包，并通过 Git LFS 管理。

## 功能

- 汉化对白、物品说明、菜单、任务、提示、地图、控制设置、存档界面、图鉴和其他玩家可见文本。
- 针对 Construct 3 资源包中的多个 SpriteFont 对象生成中文像素字形。
- 支持对白、菜单、物品说明、HUD 和按键提示等不同字号与字距。
- 按 CJK 规则处理中文换行，并调整中文文本框的布局间距。
- 重绘无法通过普通文本钩子替换的图片内文字，例如地图标记、控制页面和部分菜单标签。
- 安装器会校验游戏资源版本，备份英文原包，并防止用不匹配的补丁覆盖新版游戏。
- 卸载器可以在备份完整且版本匹配时恢复英文资源；官方更新后可重新构建对应版本的汉化包。

## 安装

1. 退出游戏。
2. 安装 Git 和 Git LFS，然后克隆仓库以获取完整补丁资源：

   ```powershell
   git lfs install
   git clone https://github.com/ZzySlhbcf/IsleOfReveriesHan.git
   cd IsleOfReveriesHan
   git lfs pull
   ```

3. 在克隆得到的 `IsleOfReveriesHan` 目录中查看 [版本.txt](版本.txt)，确认补丁适用于当前游戏资源版本。
4. 如果游戏不在安装器默认的 `D:\Games\Steam\steamapps\common\Isle of Reveries`，用记事本打开 `安装.bat` 和 `卸载.bat`，修改开头的 `GAME=` 路径。
5. 双击 `安装.bat`，按脚本提示完成安装。
6. 启动游戏即可使用简体中文。

安装器只替换游戏目录下的 `www/assets.dat`，不会修改游戏可执行文件、存档结构或 Steam 配置。

## 卸载

退出游戏后双击 `卸载.bat`。卸载器会检查当前补丁、英文备份和游戏版本是否匹配，再恢复 `www/assets.dat`。如果英文备份不存在或校验不匹配，请在 Steam 中使用“验证文件完整性”恢复原版资源。

## 官方更新后的处理方式

Steam 更新可能会整体替换 `www/assets.dat`，使游戏恢复英文。更新后不要直接运行旧版 `安装.bat`，请按下面的方式重新生成适配新版资源的补丁：

1. 退出游戏，并确认 Steam 已完成更新。
2. 安装 Python 3，以及 Pillow 和 NumPy：

   ```powershell
   python -m pip install pillow numpy
   ```

3. 修改 `官方更新后重建.bat` 顶部的 `GAME=` 路径（如有需要）。
4. 双击 `官方更新后重建.bat`。脚本会备份新版英文资源、解包、重建字形与运行时补丁、校验并安装。

官方更新后，旧版卸载器保存的英文资源可能已经对应旧版本。需要恢复英文时，优先使用 Steam 的“验证文件完整性”。

## 构建与开发

源码位于 `mod_src/`，主要部分如下：

```text
mod_src/
├── fonts/                 # 像素字体与各字体的许可证
├── trans/dict.json        # 英中译文字典
└── tools/
    ├── c3bundle.py        # Construct 3 资源包解包/重打包
    ├── build_cn_patch.py  # 生成中文字体、词典钩子和资源包
    ├── make_dist.py       # 生成交付目录与安装脚本
    ├── update_repack.py   # 以官方新版资源为底重建补丁
    ├── validate_dist.py   # 资源包完整性校验
    └── verify_glyphs.py   # 字形像素校验
```

官方更新后的自动重建命令也可以在命令行运行：

```powershell
python mod_src/tools/update_repack.py --game "D:\Games\Steam\steamapps\common\Isle of Reveries"
```

只生成而不安装到游戏目录：

```powershell
python mod_src/tools/update_repack.py --game "D:\Games\Steam\steamapps\common\Isle of Reveries" --no-install
```

重建流程需要 Python 3、Pillow 和 NumPy；校验运行时 JavaScript 时还需要 Node.js。新版本游戏如果修改了资源图片，脚本会在检测到原图变化时停止，以避免沿用旧坐标覆盖新版美术资源。

## 当前版本与验证

截至 **2026 年 10 月 5 日**，发布包包含 4,195 条英中对照译文、1,873 个中文字符，资源包信息和 MD5 见 [版本.txt](版本.txt)。已完成的检查包括：

- 资源包解包与重打包结构校验；
- 中文字形逐格像素比对，检查缺字、翻转和错位；
- 安装、卸载和官方更新后重建脚本的测试；
- 译文一致性、审校词条、地图标记、控制页和存档摘要排版回归检查。

2026-10-05 适配版已进行资源、字形及安装流程检查，尚未完成新版实机游玩验证。

部分图片文字和制作人员姓名仍保留英文；标题画面的大型 `Isle of Reveries` Logo 也保留原样。官方后续新增或改写的句子如果尚未加入词典，会原样显示英文，不会显示乱码或空白。

## 项目结构与发布内容

根目录中常用文件：

- `www/assets.dat`：汉化后的游戏资源包；
- `安装.bat`：安装汉化并备份英文资源；
- `卸载.bat`：恢复英文资源；
- `官方更新后重建.bat`：以官方新版资源重建并安装；
- `版本.txt`：当前补丁版本、文件大小与 MD5；
- `替换资源清单.json`：被替换资源的哈希清单；
- `docs/images/`：README 中使用的界面预览；
- `mod_src/`：词典、字体及重建必需的工具。

## 界面预览

![地图标记](docs/images/map-markers.png)

![控制设置](docs/images/controls.png)

## 许可证与第三方内容

本项目原创构建工具、中文译文和项目文档采用 [GNU Lesser General Public License v2.1 (LGPL-2.1)](LICENSE) 发布。

`mod_src/fonts/` 中的字体及其修改和再分发条件以各字体目录内的许可证为准，相关文本位于 `mod_src/fonts/LICENSES/`。游戏本体、原始资源和商标归其权利人所有；本仓库不重新授权游戏本体内容。请支持游戏原作者，并遵守游戏及字体的适用许可条款。

本项目是玩家制作的非官方汉化补丁，与游戏开发商、发行商或 Steam 无隶属关系。
