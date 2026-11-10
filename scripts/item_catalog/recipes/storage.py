"""柜架类：书架、格子柜、衣柜、斗柜、电视柜、厨柜、壁挂隔板、挂衣架、壁炉。"""

from __future__ import annotations

import math

from ..dsl import PI, box, cyl, ring_profile, sweep
from .registry import item
from .tables import _base_cabinet


def _shelf_unit(
    width: float,
    depth: float,
    height: float,
    *,
    shelves: int = 4,
    columns: int = 1,
    board: float = 0.025,
    material: str = "wood",
    back: bool = True,
) -> list[dict]:
    """敞口书架：两侧立板 + 若干横板 + 可选背板。`columns` 加竖向分隔。"""

    parts: list[dict] = [
        box("side_l", (board, height, depth), (-width / 2 + board / 2, height / 2, 0), material),
        box("side_r", (board, height, depth), (width / 2 - board / 2, height / 2, 0), material),
        box("top", (width, board, depth), (0, height - board / 2, 0), material),
        box("bottom", (width, board, depth), (0, board / 2, 0), material),
    ]
    if back:
        parts.append(box("back", (width - board * 2, height - board * 2, board * 0.6), (0, height / 2, -depth / 2 + board * 0.3), material))
    inner = height - board * 2
    for index in range(max(0, shelves - 1)):
        y = board + inner * (index + 1) / shelves
        parts.append(box(f"shelf_{index}", (width - board * 2, board, depth - 0.01), (0, y, 0), material))
    for index in range(1, columns):
        x = -width / 2 + width * index / columns
        parts.append(box(f"divider_{index}", (board, inner, depth - 0.01), (x, height / 2, 0), material))
    return parts


@item("bookshelf", "书架", "furniture", tags=("书架", "储物", "bookshelf"), footprint=(0.93, 1.99, 0.33), source_item="bookshelf")
def build_bookshelf() -> list[dict]:
    return _shelf_unit(0.93, 0.33, 1.99, shelves=5, board=0.028)


@item("kallax_shelf", "格子柜 2×4", "furniture", tags=("格子柜", "收纳", "kallax"), footprint=(1.09, 2.06, 0.55), source_item="ikea-kallax-1x4-moa2y49n")
def build_kallax() -> list[dict]:
    """2 列 4 行的方格柜：厚板 + 全通分隔。"""

    width, depth, height = 1.09, 0.55, 2.06
    board = 0.035
    rows = 4
    parts: list[dict] = [
        box("side_l", (board, height, depth), (-width / 2 + board / 2, height / 2, 0), "wood"),
        box("side_r", (board, height, depth), (width / 2 - board / 2, height / 2, 0), "wood"),
        box("top", (width - board * 2, board, depth), (0, height - board / 2, 0), "wood"),
        box("bottom", (width - board * 2, board, depth), (0, board / 2, 0), "wood"),
        box("divider", (board, height - board * 2, depth), (0, height / 2, 0), "wood"),
    ]
    for index in range(1, rows):
        y = board + (height - board * 2) * index / rows
        parts.append(box(f"shelf_{index}", (width - board * 2, board, depth), (0, y, 0), "wood"))
    return parts


@item("wall_shelf", "壁挂隔板", "furniture", tags=("隔板", "置物", "shelf"), footprint=(0.74, 0.04, 0.32), source_item="shelf")
def build_wall_shelf() -> list[dict]:
    """单块板 + 两个 L 托架。"""

    parts: list[dict] = [box("board", (0.74, 0.035, 0.32), (0, 0.0, 0), "wood")]
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"bracket_v_{index}", (0.025, 0.14, 0.025), (sx * 0.28, -0.08, -0.13), "metal"))
        parts.append(box(f"bracket_h_{index}", (0.025, 0.025, 0.16), (sx * 0.28, -0.012, -0.06), "metal"))
    return parts


@item("closet", "衣柜", "furniture", tags=("衣柜", "衣橱", "closet", "wardrobe"), footprint=(1.95, 2.26, 0.60), source_item="closet")
def build_closet() -> list[dict]:
    """柜体 + 两扇通高门 + 踢脚 + 长条把手。"""

    width, depth, height = 1.95, 0.60, 2.26
    plinth = 0.07
    body_h = height - plinth
    door_gap = 0.008
    door_w = (width - door_gap * 3) / 2
    parts: list[dict] = [
        box("plinth", (width - 0.04, plinth, depth - 0.06), (0, plinth / 2, -0.02), "accent"),
        box("body", (width, body_h, depth), (0, plinth + body_h / 2, 0), "wood"),
    ]
    for index in range(2):
        x = -(door_w + door_gap) / 2 + index * (door_w + door_gap)
        parts.append(box(f"door_{index}", (door_w, body_h - 0.02, 0.022), (x, plinth + body_h / 2, depth / 2 + 0.011), "wood"))
        parts.append(
            box(
                f"handle_{index}",
                (0.018, 0.34, 0.018),
                (x + (door_w / 2 - 0.05) * (-1 if index == 0 else 1), plinth + body_h * 0.5, depth / 2 + 0.03),
                "metal",
            )
        )
    return parts


@item("dresser", "斗柜", "furniture", tags=("斗柜", "抽屉柜", "dresser"), footprint=(1.23, 0.73, 0.61), source_item="dresser")
def build_dresser() -> list[dict]:
    """三层抽屉 + 短腿。"""

    width, depth, height = 1.23, 0.61, 0.73
    leg_h = 0.12
    body_h = height - leg_h
    parts: list[dict] = []
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"leg_{index}", (0.05, leg_h, 0.05), (sx * (width / 2 - 0.06), leg_h / 2, 0), "wood"))
    parts.append(box("body", (width, body_h, depth), (0, leg_h + body_h / 2, 0), "wood"))
    drawer_h = (body_h - 0.04) / 3
    for index in range(3):
        y = leg_h + 0.02 + drawer_h * (index + 0.5)
        parts.append(box(f"drawer_{index}", (width - 0.06, drawer_h - 0.015, 0.02), (0, y, depth / 2 + 0.01), "wood"))
        parts.append(box(f"pull_{index}", (width * 0.30, 0.018, 0.02), (0, y, depth / 2 + 0.026), "metal"))
    return parts


@item("tv_stand", "电视柜", "furniture", tags=("电视柜", "视听柜", "tv"), footprint=(1.86, 0.35, 0.32), source_item="tv-stand")
def build_tv_stand() -> list[dict]:
    """矮柜 + 中间设备格。"""

    width, depth, height = 1.86, 0.32, 0.35
    bay = width * 0.32
    side = (width - bay) / 2
    parts: list[dict] = [
        box("body_l", (side, height - 0.04, depth), (-(bay + side) / 2, (height - 0.04) / 2, 0), "wood"),
        box("body_r", (side, height - 0.04, depth), ((bay + side) / 2, (height - 0.04) / 2, 0), "wood"),
        box("shelf_mid", (bay, 0.025, depth), (0, 0.12, 0), "wood"),
        box("back", (bay, height - 0.04, 0.02), (0, (height - 0.04) / 2, -depth / 2 + 0.01), "wood"),
        box("top", (width, 0.035, depth), (0, height - 0.018, 0), "wood"),
    ]
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"foot_{index}", (0.05, 0.06, 0.05), (sx * (width / 2 - 0.10), 0.03, 0), "metal"))
    return parts


@item("kitchen_cabinet", "厨房橱柜", "kitchen", tags=("橱柜", "厨房", "cabinet"), footprint=(1.65, 1.09, 0.77), source_item="kitchen-cabinet")
def build_kitchen_cabinet() -> list[dict]:
    return _base_cabinet(1.65, 0.77, 1.09, doors=2, drawers=1)


@item("coat_rack", "挂衣架", "furniture", tags=("衣架", "挂衣", "coat"), footprint=(0.33, 1.76, 0.33), source_item="coat-rack")
def build_coat_rack() -> list[dict]:
    """中柱 + 三叉底座 + 顶部挂钩（用扫掠做弯钩）。"""

    parts: list[dict] = [cyl("pole", 0.022, 1.70, (0, 0.85, 0), "metal", segments=12)]
    for index in range(3):
        angle = 2 * PI * index / 3
        parts.append(
            sweep(
                f"foot_{index}",
                [[-0.016, -0.016], [0.016, -0.016], [0.016, 0.016], [-0.016, 0.016]],
                [(0, 0.06, 0), (0.22 * math.cos(angle), 0.02, 0.22 * math.sin(angle))],
                "metal",
            )
        )
    for index in range(4):
        angle = 2 * PI * index / 4 + PI / 4
        parts.append(
            sweep(
                f"hook_{index}",
                ring_profile(0.012, 8),
                [(0, 1.50, 0), (0.10 * math.cos(angle), 1.62, 0.10 * math.sin(angle))],
                "metal",
            )
        )
    return parts


@item("fireplace", "壁炉", "furniture", tags=("壁炉", "取暖", "fireplace"), footprint=(1.00, 0.83, 0.18), source_item="fireplace-movn1fnn")
def build_fireplace() -> list[dict]:
    """壁挂式：外框 + 内腔（深色）+ 顶部搁板 + 两侧石柱。"""

    width, depth, height = 1.00, 0.18, 0.83
    parts: list[dict] = [
        box("frame", (width, height, depth), (0, height / 2, 0), "wood"),
        box("cavity", (width - 0.14, height * 0.52, depth * 0.5), (0, height * 0.30, depth / 2 - depth * 0.25), "accent"),
        box("mantel", (width + 0.06, 0.045, depth + 0.06), (0, height - 0.02, 0), "wood"),
    ]
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"pier_{index}", (0.06, height, depth * 0.8), (sx * (width / 2 - 0.03), height / 2, depth * 0.2), "stone"))
    return parts
