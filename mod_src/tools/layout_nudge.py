"""版面微调：中文比原版英文占篇幅，游戏里“名字”和“说明”往往是两个独立文本框，
原版箱子紧贴（间距 0px），换成中文后看起来就是两行贴死。这里把**下面那个多行框**
整体下移 dy 像素，只影响箱子坐标，不动文字内容、不动逻辑。

原则：
  * 只挪“下面紧贴上面文本框（间距 -1..1px）且水平方向有重叠”的框，且该框高度 >= 16
    （多行说明框），单个单行标签不动，避免误伤 UI 元素；
  * 每个框最多挪一次；重复构建是幂等的（每次从 extracted/ 的原始数据出发）。
"""

DY = 3          # 下移像素，用户要求“2-3px 即可”


def nudge_flush_texts(project, dy=DY):
    ots = project[3]
    names = {}
    for i, o in enumerate(ots):
        if isinstance(o, list) and o and isinstance(o[0], str):
            names.setdefault(o[0], i)
    text_ids = {i for n, i in names.items()
                if any(w in n for w in ("Text", "Name", "Description"))}
    moved = []
    for lay in project[5]:
        for cont in lay[10:]:
            if not isinstance(cont, list):
                continue
            for lyr in cont:
                if not (isinstance(lyr, list) and len(lyr) > 14
                        and isinstance(lyr[0], str) and isinstance(lyr[14], list)):
                    continue
                boxes = [(ins, ins[0]) for ins in lyr[14]
                         if isinstance(ins, list) and len(ins) > 2 and ins[1] in text_ids
                         and isinstance(ins[0], list) and len(ins[0]) > 4]
                for ins, b in boxes:
                    if b[4] < 16:            # 只动多行框
                        continue
                    for ins2, b2 in boxes:
                        if ins2 is ins:
                            continue
                        if b2[4] > 9:
                            # 上一行是“已经被我们加高过的名字框”（原版单行框高 8~9），
                            # 跳过 -> 重复构建/在已汉化的包上重建都不会越挪越多
                            continue
                        flush = abs(b[1] - (b2[1] + b2[4])) <= 1
                        overlap = b[0] < b2[0] + b2[3] and b2[0] < b[0] + b[3]
                        if flush and overlap:
                            b[1] += dy                 # 说明框下移
                            b2[4] += dy                # 同时把上面“名字框”的高度也加 dy：
                            #   游戏很可能在运行时按“名字框底部”重新摆说明框（实测它无视
                            #   静态坐标），加高名字框就等于把它往下推；若游戏用的是静态坐标，
                            #   这条改动不影响观感。
                            moved.append((lay[0], lyr[0], b2[1] + b2[4], b[1]))
                            break
    return moved
