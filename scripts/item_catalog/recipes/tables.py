"""桌类：餐桌、书桌、茶几、办公桌、边几、台球桌、烫衣板、厨房台面、吧台。

统一约定：`top` 是台面，`leg_*` 是四腿，尺寸取自 editor 目录的实测 dimensions
（宽 X、高 Y、深 Z），坐标原点在底面中心。
"""

from __future__ import annotations

from ..dsl import PI, box, cyl, legs4
from .registry import item


def _table(
    width: float,
    depth: float,
    height: float,
    *,
    top_thickness: float = 0.04,
    leg_radius: float = 0.028,
    leg_inset: float = 0.06,
    apron: bool = True,
    top_material: str = "wood",
    leg_material: str = "wood",
    square_legs: bool = False,
    leg_size: float = 0.06,
) -> list[dict]:
    """四腿桌。`apron` 是台面下的围裙板（挡住腿与台面的接头）。"""

    parts: list[dict] = []
    top_y = height - top_thickness / 2
    leg_h = height - top_thickness
    if square_legs:
        half_w = max(width / 2 - leg_inset, 0.01)
        half_d = max(depth / 2 - leg_inset, 0.01)
        for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
            parts.append(
                box(f"leg_{index}", (leg_size, leg_h, leg_size), (sx * half_w, leg_h / 2, sz * half_d), leg_material)
            )
    else:
        parts += legs4("leg", width, depth, leg_h, inset=leg_inset, radius=leg_radius, material=leg_material)
    parts.append(box("top", (width, top_thickness, depth), (0, top_y, 0), top_material))
    if apron:
        apron_h = min(0.08, max(0.04, height * 0.08))
        apron_y = leg_h - apron_h / 2
        parts.append(box("apron_f", (width - 0.10, apron_h, 0.025), (0, apron_y, depth / 2 - 0.05), top_material))
        parts.append(box("apron_b", (width - 0.10, apron_h, 0.025), (0, apron_y, -depth / 2 + 0.05), top_material))
        parts.append(box("apron_l", (0.025, apron_h, depth - 0.10), (-width / 2 + 0.05, apron_y, 0), top_material))
        parts.append(box("apron_r", (0.025, apron_h, depth - 0.10), (width / 2 - 0.05, apron_y, 0), top_material))
    return parts


def _desk_with_pedestal(width: float, depth: float, height: float) -> list[dict]:
    """一侧抽屉柜、一侧单腿的办公桌 —— 与四腿桌区分开，避免目录里全是同款。"""

    parts: list[dict] = []
    top_t = 0.04
    leg_h = height - top_t
    pedestal_w = min(0.42, width * 0.32)
    pedestal_x = -width / 2 + pedestal_w / 2 + 0.02
    parts.append(box("pedestal", (pedestal_w, leg_h, depth - 0.06), (pedestal_x, leg_h / 2, 0), "wood"))
    for index in range(3):
        drawer_y = leg_h * (0.22 + index * 0.28)
        parts.append(box(f"drawer_{index}", (pedestal_w - 0.05, leg_h * 0.22, 0.02), (pedestal_x, drawer_y, depth / 2 - 0.02), "metal"))
        parts.append(box(f"handle_{index}", (pedestal_w * 0.45, 0.015, 0.02), (pedestal_x, drawer_y, depth / 2 - 0.005), "metal"))
    parts.append(cyl("leg", 0.03, leg_h, (width / 2 - 0.08, leg_h / 2, 0), "metal", segments=12))
    parts.append(box("top", (width, top_t, depth), (0, height - top_t / 2, 0), "wood"))
    return parts


def _base_cabinet(width: float, depth: float, height: float, doors: int = 2, drawers: int = 0) -> list[dict]:
    """落地柜：踢脚 + 柜体 + 门板（带分缝）+ 台面。橱柜与洗手台共用。"""

    plinth = 0.09
    body_h = height - plinth - 0.04
    parts: list[dict] = [box("plinth", (width - 0.06, plinth, depth - 0.08), (0, plinth / 2, -0.02), "accent")]
    parts.append(box("body", (width, body_h, depth), (0, plinth + body_h / 2, 0), "wood"))
    parts.append(box("counter", (width + 0.02, 0.04, depth + 0.02), (0, height - 0.02, 0.01), "stone"))
    drawer_zone = body_h * 0.28 * drawers
    if drawers:
        drawer_h = body_h * 0.28
        for index in range(drawers):
            parts.append(
                box(
                    f"drawer_{index}",
                    (width - 0.08, drawer_h - 0.01, 0.02),
                    (0, plinth + body_h - drawer_h * (index + 0.5), depth / 2 + 0.01),
                    "wood",
                )
            )
    door_h = body_h - drawer_zone
    door_w = (width - 0.08 - 0.01 * max(doors - 1, 0)) / doors
    for index in range(doors):
        center_x = -width / 2 + 0.04 + door_w / 2 + index * (door_w + 0.01)
        parts.append(box(f"door_{index}", (door_w, door_h - 0.02, 0.02), (center_x, plinth + door_h / 2, depth / 2 + 0.01), "wood"))
        parts.append(
            box(
                f"knob_{index}",
                (0.02, 0.10, 0.02),
                (center_x + (door_w / 2 - 0.06) * (1 if index % 2 == 0 else -1), plinth + door_h * 0.62, depth / 2 + 0.03),
                "metal",
            )
        )
    return parts


@item("dining_table", "餐桌", "furniture", tags=("餐桌", "桌子", "dining", "table"), footprint=(2.0, 0.77, 0.91), source_item="dining-table-mo9ms5yh")
def build_dining_table() -> list[dict]:
    return _table(2.0, 0.91, 0.77, top_thickness=0.045, leg_inset=0.09, leg_radius=0.032)


@item("long_dining_table", "大餐桌", "furniture", tags=("餐桌", "长桌", "dining", "table"), footprint=(2.16, 0.70, 0.95), source_item="dining-table")
def build_long_dining_table() -> list[dict]:
    return _table(2.16, 0.95, 0.70, top_thickness=0.045, leg_inset=0.10, leg_radius=0.034)


@item("bistro_table", "圆餐桌", "furniture", tags=("圆桌", "餐桌", "round"), footprint=(1.10, 0.74, 1.10))
def build_bistro_table() -> list[dict]:
    """圆台面 + 中柱 + 圆底座。"""

    parts: list[dict] = [cyl("top", 0.55, 0.042, (0, 0.72, 0), "wood", segments=40)]
    parts.append(cyl("column", 0.055, 0.66, (0, 0.33, 0), "wood", segments=16))
    parts.append(cyl("base", 0.30, 0.035, (0, 0.018, 0), "metal", segments=32))
    return parts


@item("coffee_table", "茶几", "furniture", tags=("茶几", "客厅", "coffee"), footprint=(1.72, 0.30, 1.04), source_item="coffee-table")
def build_coffee_table() -> list[dict]:
    """矮台面 + 下层搁板。"""

    parts: list[dict] = []
    parts += legs4("leg", 1.72, 1.04, 0.28, inset=0.08, radius=0.022, material="wood")
    parts.append(box("top", (1.72, 0.04, 1.04), (0, 0.28, 0), "wood"))
    parts.append(box("shelf", (1.56, 0.025, 0.90), (0, 0.10, 0), "wood"))
    return parts


@item("side_table", "边几", "furniture", tags=("边几", "小桌", "side"), footprint=(0.45, 0.48, 0.46), source_item="bedside-table")
def build_side_table() -> list[dict]:
    parts: list[dict] = []
    parts += legs4("leg", 0.45, 0.46, 0.44, inset=0.04, radius=0.018, material="metal")
    parts.append(box("top", (0.45, 0.035, 0.46), (0, 0.462, 0), "wood"))
    parts.append(box("drawer", (0.40, 0.10, 0.02), (0, 0.36, 0.225), "wood"))
    return parts


@item("office_table", "办公桌", "furniture", tags=("办公桌", "书桌", "desk"), footprint=(1.51, 0.76, 0.62), source_item="office-table")
def build_office_table() -> list[dict]:
    return _desk_with_pedestal(1.51, 0.62, 0.76)


@item("standing_desk", "升降办公桌", "furniture", tags=("升降桌", "办公桌", "standing"), footprint=(1.41, 0.85, 0.68), source_item="standing-desk-mo8wgz95")
def build_standing_desk() -> list[dict]:
    """双柱升降腿：两根立柱 + 横梁 + 台面。"""

    parts: list[dict] = []
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"column_{index}", (0.07, 0.78, 0.07), (sx * 0.50, 0.39, 0), "metal"))
        parts.append(box(f"foot_{index}", (0.08, 0.03, 0.60), (sx * 0.50, 0.015, 0), "metal"))
    parts.append(box("beam", (0.96, 0.06, 0.06), (0, 0.74, 0), "metal"))
    parts.append(box("top", (1.41, 0.038, 0.68), (0, 0.83, 0), "wood"))
    return parts


@item("pool_table", "台球桌", "furniture", tags=("台球桌", "娱乐", "pool"), footprint=(2.11, 0.98, 3.50), source_item="pool-table")
def build_pool_table() -> list[dict]:
    """台面 + 四周边框 + 6 个袋口 + 4 条粗腿。"""

    width, depth, height = 2.11, 3.50, 0.98
    rail = 0.12
    parts: list[dict] = []
    for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        parts.append(box(f"leg_{index}", (0.16, 0.72, 0.16), (sx * (width / 2 - 0.18), 0.36, sz * (depth / 2 - 0.18)), "wood"))
    parts.append(box("bed", (width, 0.10, depth), (0, 0.77, 0), "accent"))
    parts.append(box("rail_l", (rail, 0.06, depth), (-width / 2 + rail / 2, 0.85, 0), "wood"))
    parts.append(box("rail_r", (rail, 0.06, depth), (width / 2 - rail / 2, 0.85, 0), "wood"))
    parts.append(box("rail_f", (width - rail * 2, 0.06, rail), (0, 0.85, depth / 2 - rail / 2), "wood"))
    parts.append(box("rail_b", (width - rail * 2, 0.06, rail), (0, 0.85, -depth / 2 + rail / 2), "wood"))
    for index, (px, pz) in enumerate(
        (
            (-width / 2, -depth / 2),
            (width / 2, -depth / 2),
            (-width / 2, 0),
            (width / 2, 0),
            (-width / 2, depth / 2),
            (width / 2, depth / 2),
        )
    ):
        parts.append(cyl(f"pocket_{index}", 0.055, 0.07, (px * 0.96, 0.86, pz * 0.97), "metal", segments=14))
    return parts


@item("ironing_board", "烫衣板", "furniture", tags=("烫衣板", "家务", "ironing"), footprint=(1.31, 0.96, 0.48), source_item="ironing-board")
def build_ironing_board() -> list[dict]:
    """斜撑 + 窄台面。台面是平盒体，不做曲面。"""

    parts: list[dict] = [box("top", (1.26, 0.035, 0.40), (0, 0.92, 0), "fabric")]
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"leg_{index}", (0.035, 0.88, 0.035), (sx * 0.42, 0.44, -0.04), "metal", rot=(0.24, 0, 0)))
    parts.append(box("brace", (0.80, 0.03, 0.03), (0, 0.38, 0.04), "metal"))
    parts.append(box("iron_rest", (0.20, 0.03, 0.14), (0.45, 0.90, 0.12), "metal"))
    return parts


@item("kitchen_counter", "橱柜台面", "kitchen", tags=("橱柜", "台面", "counter"), footprint=(1.96, 0.73, 0.63), source_item="kitchen-counter")
def build_kitchen_counter() -> list[dict]:
    """下柜 + 台面 + 门板分缝。"""

    return _base_cabinet(1.96, 0.63, 0.73, doors=3, drawers=1)


@item("kitchen_bar", "木吧台", "kitchen", tags=("吧台", "厨房", "bar"), footprint=(2.50, 1.06, 0.96), source_item="wooden-kitchen-bar-moa2hhh4")
def build_kitchen_bar() -> list[dict]:
    """高台面 + 前板 + 两条高脚 + 脚踏杆。"""

    width, depth, height = 2.50, 0.96, 1.06
    parts: list[dict] = [box("top", (width, 0.06, depth), (0, height - 0.03, 0), "wood")]
    parts.append(box("front", (width - 0.08, height - 0.20, 0.05), (0, (height - 0.20) / 2 + 0.10, depth / 2 - 0.05), "wood"))
    # 两端侧板封口：只有前板时侧视是"台面浮在一条腿上"，看不出是柜体
    for index, sx in enumerate((-1, 1)):
        parts.append(
            box(
                f"side_{index}",
                (0.05, height - 0.16, depth - 0.04),
                (sx * (width / 2 - 0.025), (height - 0.16) / 2 + 0.10, 0),
                "wood",
            )
        )
    parts.append(box("back", (width - 0.10, height - 0.24, 0.04), (0, (height - 0.24) / 2 + 0.10, -depth / 2 + 0.02), "wood"))
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"leg_{index}", (0.07, height - 0.06, 0.07), (sx * (width / 2 - 0.10), (height - 0.06) / 2, -depth / 2 + 0.08), "wood"))
    parts.append(box("shelf", (width - 0.30, 0.03, 0.28), (0, 0.22, -depth / 2 + 0.22), "wood"))
    parts.append(cyl("rail", 0.018, width - 0.20, (0, 0.78, depth / 2 - 0.06), "metal", segments=12, rot=(0, 0, PI / 2)))
    return parts
