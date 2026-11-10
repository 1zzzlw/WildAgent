"""装饰与陈设：画框、地毯、书籍、绿植、垃圾桶、玩具、吉他、钢琴、画架。"""

from __future__ import annotations

import math

from ..dsl import PI, box, cyl, ring_profile, sphere, sweep
from .registry import item


@item("picture_frame", "装饰画", "decor", tags=("画", "挂画", "picture"), footprint=(1.47, 0.82, 0.06), source_item="picture")
def build_picture_frame() -> list[dict]:
    """外框 + 内画。挂画，原点在底边中心。"""

    width, height = 1.47, 0.82
    parts: list[dict] = [box("frame", (width, height, 0.045), (0, height / 2, 0), "wood")]
    parts.append(box("canvas", (width - 0.12, height - 0.12, 0.012), (0, height / 2, 0.028), "accent"))
    return parts


@item("rug_rect", "长方形地毯", "decor", tags=("地毯", "rug"), footprint=(2.78, 0.04, 1.81), source_item="rectangular-carpet")
def build_rug_rect() -> list[dict]:
    parts: list[dict] = [box("rug", (2.78, 0.022, 1.81), (0, 0.011, 0), "fabric")]
    parts.append(box("border", (2.78, 0.012, 1.81), (0, 0.026, 0), "accent"))
    parts.append(box("field", (2.60, 0.008, 1.63), (0, 0.030, 0), "fabric"))
    return parts


@item("rug_round", "圆形地毯", "decor", tags=("地毯", "圆形", "rug"), footprint=(1.99, 0.04, 1.99), source_item="round-carpet")
def build_rug_round() -> list[dict]:
    parts: list[dict] = [cyl("rug", 0.995, 0.020, (0, 0.010, 0), "fabric", segments=44)]
    parts.append(cyl("ring", 0.93, 0.010, (0, 0.024, 0), "accent", segments=44))
    parts.append(cyl("field", 0.90, 0.008, (0, 0.028, 0), "fabric", segments=44))
    return parts


@item("books_stack", "一摞书", "decor", tags=("书", "陈设", "books"), footprint=(0.22, 0.22, 0.18), source_item="books")
def build_books_stack() -> list[dict]:
    parts: list[dict] = []
    for index in range(5):
        parts.append(
            box(
                f"book_{index}",
                (0.20 - index * 0.008, 0.035, 0.15 + (index % 2) * 0.02),
                (0.006 * (index % 3 - 1), 0.018 + index * 0.036, 0.004 * (index % 2)),
                "accent" if index % 2 == 0 else "wood",
                rot=(0, 0.02 * (index - 2), 0),
            )
        )
    return parts


@item("cactus", "仙人掌", "decor", tags=("植物", "仙人掌", "cactus"), footprint=(0.34, 0.39, 0.27), source_item="cactus")
def build_cactus() -> list[dict]:
    parts: list[dict] = [cyl("pot", 0.10, 0.14, (0, 0.07, 0), "stone", radius_top=0.115, segments=20)]
    parts.append(cyl("stem", 0.045, 0.24, (0, 0.26, 0), "foliage", segments=16))
    parts.append(cyl("arm_l", 0.028, 0.10, (-0.075, 0.28, 0), "foliage", segments=12, rot=(0, 0, 0.5)))
    parts.append(cyl("arm_r", 0.026, 0.08, (0.07, 0.24, 0), "foliage", segments=12, rot=(0, 0, -0.5)))
    return parts


@item("plant_small", "小盆栽", "decor", tags=("植物", "盆栽", "plant"), footprint=(0.40, 0.67, 0.38), source_item="small-indoor-plant")
def build_plant_small() -> list[dict]:
    parts: list[dict] = [cyl("pot", 0.11, 0.18, (0, 0.09, 0), "stone", radius_top=0.13, segments=18)]
    for index in range(5):
        angle = 2 * PI * index / 5
        parts.append(
            sweep(
                f"leaf_{index}",
                [[-0.055, -0.008], [0.055, -0.008], [0.055, 0.008], [-0.055, 0.008]],
                [(0, 0.18, 0), (0.16 * math.cos(angle), 0.52, 0.16 * math.sin(angle))],
                "foliage",
            )
        )
    return parts


@item("plant_large", "大型绿植", "decor", tags=("植物", "绿植", "plant"), footprint=(0.69, 1.63, 0.83), source_item="indoor-plant")
def build_plant_large() -> list[dict]:
    """花盆 + 三根主干 + 顶部叶团。"""

    parts: list[dict] = [cyl("pot", 0.22, 0.38, (0, 0.19, 0), "stone", radius_top=0.25, segments=22)]
    parts.append(cyl("soil", 0.235, 0.02, (0, 0.37, 0), "accent", segments=22))
    for index in range(3):
        angle = 2 * PI * index / 3
        parts.append(
            sweep(
                f"stem_{index}",
                ring_profile(0.018, 8),
                [(0, 0.36, 0), (0.12 * math.cos(angle), 0.86, 0.12 * math.sin(angle)), (0.16 * math.cos(angle), 1.28, 0.16 * math.sin(angle))],
                "wood",
            )
        )
    for index, (cx, cy, cz, radius) in enumerate(((0.0, 1.42, 0.0, 0.30), (0.22, 1.28, 0.14, 0.24), (-0.20, 1.24, -0.12, 0.22))):
        parts.append(sphere(f"foliage_{index}", radius, (cx, cy, cz), "foliage", segments=16))
    return parts


@item("trash_bin", "垃圾桶", "decor", tags=("垃圾桶", "收纳", "bin"), footprint=(0.35, 0.59, 0.42), source_item="trash-bin")
def build_trash_bin() -> list[dict]:
    parts: list[dict] = [cyl("body", 0.17, 0.52, (0, 0.26, 0), "metal", radius_top=0.185, segments=24)]
    parts.append(cyl("rim", 0.19, 0.03, (0, 0.535, 0), "metal", segments=24))
    parts.append(box("pedal", (0.10, 0.02, 0.06), (0, 0.02, 0.19), "metal"))
    return parts


@item("toy_block", "玩具", "decor", tags=("玩具", "儿童", "toy"), footprint=(0.29, 0.49, 0.34), source_item="toy")
def build_toy() -> list[dict]:
    """积木塔 + 一个球。"""

    parts: list[dict] = []
    for index in range(4):
        size = 0.16 - index * 0.02
        parts.append(box(f"block_{index}", (size, 0.10, size), (0.02 * (index % 2), 0.05 + index * 0.10, 0), "accent" if index % 2 else "wood"))
    parts.append(sphere("ball", 0.09, (-0.09, 0.09, 0.08), "accent", segments=14))
    return parts


@item("guitar", "吉他", "decor", tags=("吉他", "乐器", "guitar"), footprint=(0.40, 1.18, 0.10), source_item="guitar")
def build_guitar() -> list[dict]:
    """上下两个扁圆琴身 + 琴颈 + 琴头 + 弦枕，靠墙站立。"""

    parts: list[dict] = [cyl("body_low", 0.20, 0.085, (0, 0.28, 0), "wood", segments=28)]
    parts.append(cyl("body_up", 0.155, 0.075, (0, 0.50, 0), "wood", segments=28))
    parts.append(cyl("soundhole", 0.055, 0.01, (0, 0.40, 0.045), "accent", segments=20, rot=(PI / 2, 0, 0)))
    parts.append(box("neck", (0.055, 0.56, 0.028), (0, 0.86, 0.012), "wood"))
    parts.append(box("head", (0.075, 0.14, 0.024), (0, 1.14, 0.012), "wood"))
    parts.append(box("bridge", (0.12, 0.02, 0.014), (0, 0.30, 0.045), "accent"))
    return parts


@item("piano", "立式钢琴", "decor", tags=("钢琴", "乐器", "piano"), footprint=(1.54, 1.44, 0.69), source_item="piano")
def build_piano() -> list[dict]:
    """琴体 + 键盘（白键条 + 黑键组）+ 顶盖 + 踏板。"""

    width, depth, height = 1.54, 0.69, 1.44
    key_h = 0.09
    key_y = 0.70
    parts: list[dict] = []
    # 键盘以上是箱体，键盘以下只有两侧前腿 —— 否则键盘会像嵌在柜子中间。
    upper_h = height - key_y
    parts.append(box("case", (width, upper_h, depth), (0, key_y + upper_h / 2, -0.02), "wood"))
    parts.append(box("lid", (width + 0.02, 0.03, depth + 0.02), (0, height - 0.015, 0), "wood"))
    parts.append(box("keybed", (width - 0.06, key_h, 0.26), (0, key_y - key_h / 2, depth / 2 + 0.05), "wood"))
    parts.append(box("keys_white", (width - 0.14, 0.016, 0.15), (0, key_y + 0.008, depth / 2 + 0.05), "accent"))
    key_w = (width - 0.14) / 35
    for index in range(35):
        group, position = divmod(index, 5)
        if position >= 3:
            position += 1
        x = -(width - 0.14) / 2 + (group * 7 + position + 1) * key_w
        parts.append(box(f"key_black_{index}", (0.014, 0.022, 0.09), (x, key_y + 0.024, depth / 2 + 0.03), "metal"))
    for index, sx in enumerate((-1, 1)):
        parts.append(
            box(
                f"leg_{index}",
                (0.10, key_y - key_h, depth * 0.86),
                (sx * (width / 2 - 0.06), (key_y - key_h) / 2, -0.02),
                "wood",
            )
        )
    for index, sx in enumerate((-0.10, 0.0, 0.10)):
        parts.append(box(f"pedal_{index}", (0.05, 0.02, 0.10), (sx, 0.02, depth / 2 - 0.10), "metal"))
    return parts


@item("easel", "画架", "decor", tags=("画架", "美术", "easel"), footprint=(0.99, 2.32, 0.55), source_item="easel")
def build_easel() -> list[dict]:
    """A 形三腿 + 横托 + 画卷。"""

    height = 2.32
    parts: list[dict] = []
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"leg_front_{index}", (0.04, height, 0.04), (sx * 0.40, height / 2, 0.10), "wood", rot=(0.06, 0, sx * -0.05)))
    parts.append(box("leg_back", (0.04, height * 0.92, 0.04), (0, height * 0.46, -0.24), "wood", rot=(-0.26, 0, 0)))
    parts.append(box("tray", (0.92, 0.035, 0.10), (0, height * 0.46, 0.10), "wood"))
    parts.append(box("canvas", (0.86, 0.98, 0.02), (0, height * 0.72, 0.09), "accent", rot=(0.06, 0, 0)))
    parts.append(box("top_clamp", (0.10, 0.05, 0.06), (0, height * 0.92, 0.08), "metal"))
    return parts
