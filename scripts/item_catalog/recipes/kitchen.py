"""厨房：整体橱柜、抽油烟机、灶台、置物架、餐具小件。"""

from __future__ import annotations

from ..dsl import PI, box, cyl, sphere
from .registry import item
from .tables import _base_cabinet


@item("kitchen_set", "整体厨房", "kitchen", tags=("厨房", "橱柜", "kitchen"), footprint=(2.38, 1.03, 0.84), source_item="kitchen")
def build_kitchen_set() -> list[dict]:
    """地柜 + 台面 + 吊柜 + 台上灶具与水槽。"""

    width, depth, height = 2.38, 0.84, 1.03
    parts = _base_cabinet(width, depth, 0.90, doors=4, drawers=1)
    # 吊柜（挂在 1.45～2.15，物品整体高度只到 1.03，故用相对高度的上方体量表达）
    cabinet_h = 0.70
    parts.append(box("wall_cabinet", (width, cabinet_h, 0.34), (0, height + cabinet_h / 2 + 0.20, -depth / 2 + 0.17), "wood"))
    for index in range(4):
        door_w = (width - 0.08) / 4
        parts.append(
            box(
                f"wall_door_{index}",
                (door_w - 0.012, cabinet_h - 0.04, 0.02),
                (-width / 2 + 0.04 + door_w * (index + 0.5), height + cabinet_h / 2 + 0.20, -depth / 2 + 0.345),
                "wood",
            )
        )
    # 灶具 + 水槽
    parts.append(box("hob", (0.60, 0.02, 0.50), (-0.55, 0.915, 0.02), "metal"))
    for index in range(2):
        parts.append(cyl(f"burner_{index}", 0.10, 0.012, (-0.75 + index * 0.40, 0.928, 0.02), "accent", segments=20))
    parts.append(box("sink", (0.56, 0.06, 0.44), (0.55, 0.90, 0.02), "metal"))
    parts.append(cyl("faucet", 0.018, 0.26, (0.55, 1.03, -0.20), "metal", segments=12))
    return parts


@item("range_hood", "抽油烟机", "kitchen", tags=("油烟机", "厨房", "hood"), footprint=(1.21, 0.62, 0.51), source_item="hood")
def build_range_hood() -> list[dict]:
    """T 形：下罩 + 上风管。挂装，原点在罩底。"""

    width, depth, height = 1.21, 0.51, 0.62
    parts: list[dict] = [box("canopy", (width, 0.10, depth), (0, 0.05, 0), "metal")]
    parts.append(box("slope", (width * 0.55, 0.16, depth * 0.62), (0, 0.18, -0.02), "metal"))
    parts.append(box("duct", (0.30, height - 0.26, 0.26), (0, 0.26 + (height - 0.26) / 2, -0.06), "metal"))
    parts.append(box("filter", (width - 0.10, 0.02, depth - 0.10), (0, 0.005, 0), "accent"))
    return parts


@item("stove", "灶台", "kitchen", tags=("灶台", "烤箱", "stove"), footprint=(0.92, 0.85, 0.76), source_item="stove")
def build_stove() -> list[dict]:
    """立式灶：烤箱门 + 台面灶头 + 控制旋钮。"""

    width, depth, height = 0.92, 0.76, 0.85
    parts: list[dict] = [box("body", (width, height - 0.06, depth), (0, (height - 0.06) / 2 + 0.06, 0), "metal")]
    parts.append(box("oven_door", (width - 0.08, 0.42, 0.02), (0, 0.32, depth / 2 + 0.01), "glass"))
    parts.append(box("oven_handle", (width - 0.20, 0.03, 0.03), (0, 0.56, depth / 2 + 0.035), "metal"))
    parts.append(box("top", (width, 0.03, depth), (0, height - 0.015, 0), "metal"))
    for index in range(4):
        cx = -width / 4 + (index % 2) * (width / 2)
        cz = -depth / 4 + (index // 2) * (depth / 2)
        parts.append(cyl(f"burner_{index}", 0.09, 0.014, (cx, height + 0.005, cz), "accent", segments=18))
    for index in range(5):
        parts.append(cyl(f"knob_{index}", 0.022, 0.025, (-width / 2 + 0.12 + index * 0.10, height - 0.10, depth / 2 + 0.018), "metal", segments=12, rot=(PI / 2, 0, 0)))
    return parts


@item("kitchen_shelf", "厨房置物架", "kitchen", tags=("置物架", "厨房", "shelf"), footprint=(2.21, 0.89, 0.52), source_item="kitchen-shelf")
def build_kitchen_shelf() -> list[dict]:
    """两层开放搁架 + 背挡。"""

    width, depth, height = 2.21, 0.52, 0.89
    parts: list[dict] = []
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"side_{index}", (0.035, height, depth), (sx * (width / 2 - 0.018), height / 2, 0), "metal"))
    for index in range(2):
        y = 0.12 + index * 0.42
        parts.append(box(f"board_{index}", (width - 0.07, 0.03, depth), (0, y, 0), "wood"))
    parts.append(box("back", (width - 0.07, height, 0.02), (0, height / 2, -depth / 2 + 0.01), "metal"))
    for index in range(4):
        parts.append(box(f"hook_{index}", (0.02, 0.06, 0.10), (-width / 2 + 0.30 + index * 0.50, height - 0.16, depth / 2 - 0.05), "metal"))
    return parts


@item("cutting_board", "砧板", "kitchen", tags=("砧板", "厨房", "board"), footprint=(0.27, 0.07, 0.41), source_item="cutting-board")
def build_cutting_board() -> list[dict]:
    parts: list[dict] = [box("board", (0.27, 0.032, 0.41), (0, 0.016, 0), "wood")]
    parts.append(box("rail", (0.27, 0.02, 0.03), (0, 0.042, 0.19), "wood"))
    return parts


@item("frying_pan", "平底锅", "kitchen", tags=("锅", "厨具", "pan"), footprint=(0.36, 0.09, 0.64), source_item="frying-pan")
def build_frying_pan() -> list[dict]:
    parts: list[dict] = [cyl("pan", 0.18, 0.045, (0, 0.022, 0), "metal", segments=32)]
    parts.append(cyl("inner", 0.168, 0.03, (0, 0.032, 0), "accent", segments=32))
    parts.append(box("handle", (0.03, 0.02, 0.26), (0, 0.035, 0.30), "accent"))
    return parts


@item("wine_bottles", "酒瓶架", "kitchen", tags=("酒瓶", "厨房", "wine"), footprint=(0.38, 0.35, 0.17), source_item="wine-bottle")
def build_wine_bottles() -> list[dict]:
    """三只酒瓶并排。"""

    parts: list[dict] = []
    for index in range(3):
        x = -0.12 + index * 0.12
        parts.append(cyl(f"body_{index}", 0.042, 0.24, (x, 0.12, 0), "glass", segments=16))
        parts.append(cyl(f"neck_{index}", 0.016, 0.07, (x, 0.275, 0), "glass", segments=12))
        parts.append(cyl(f"cap_{index}", 0.018, 0.02, (x, 0.315, 0), "accent", segments=12))
    return parts


@item("fruit_bowl", "果盘", "kitchen", tags=("水果", "果盘", "fruit"), footprint=(0.39, 0.27, 0.39), source_item="fruits")
def build_fruit_bowl() -> list[dict]:
    parts: list[dict] = [cyl("bowl", 0.19, 0.09, (0, 0.045, 0), "stone", radius_top=0.20, segments=32)]
    for index, (fx, fz, radius) in enumerate(((0.0, 0.0, 0.055), (0.08, 0.05, 0.045), (-0.07, 0.06, 0.048), (0.02, -0.08, 0.042))):
        parts.append(sphere(f"fruit_{index}", radius, (fx, 0.115 + radius * 0.4, fz), "accent", segments=12))
    return parts


@item("utensil_holder", "刀架", "kitchen", tags=("厨具", "刀架", "utensil"), footprint=(0.23, 0.49, 0.21), source_item="kitchen-utensils")
def build_utensil_holder() -> list[dict]:
    parts: list[dict] = [cyl("crock", 0.09, 0.16, (0, 0.08, 0), "stone", segments=20)]
    for index in range(5):
        angle = -0.5 + index * 0.25
        parts.append(box(f"tool_{index}", (0.018, 0.34, 0.018), (0.0 + index * 0.012, 0.28, 0.0 + index * 0.008), "wood", rot=(0.10, angle, 0)))
    return parts
