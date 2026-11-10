"""座具：沙发、扶手椅、长凳、单椅、吧凳。

所有尺寸单位为米，坐标原点在**底面中心**，+Z 为正面（靠背在 -Z 侧）。
"""

from __future__ import annotations

from ..dsl import PI, box, cyl, legs4, merge, sweep, ring_profile
from .registry import item

LEG_H = 0.10


def _sofa(width: float, depth: float, height: float, seats: int, arm: float = 0.16) -> list[dict]:
    """沙发：腿 + 底座 + 整宽靠背 + 两侧扶手 + 分块坐垫 + 分块靠垫。"""

    base_h = 0.22
    base_top = LEG_H + base_h
    back_d = 0.16
    back_h = max(height - base_top, 0.2)
    inner_w = max(width - 2 * arm, 0.3)
    cushion_w = inner_w / seats - 0.02
    cushion_h = 0.14
    seat_z = 0.04

    parts: list[dict] = []
    parts += legs4("leg", width, depth, LEG_H, inset=0.10, radius=0.022, material="wood")
    parts.append(box("base", (width, base_h, depth), (0, LEG_H + base_h / 2, 0), "fabric"))
    parts.append(
        box("back", (width, back_h, back_d), (0, base_top + back_h / 2, -depth / 2 + back_d / 2), "fabric")
    )
    for index, sx in enumerate((-1, 1)):
        parts.append(
            box(
                f"arm_{index}",
                (arm, 0.42, depth),
                (sx * (width / 2 - arm / 2), base_top + 0.21, 0),
                "fabric",
            )
        )
    for index in range(seats):
        offset = (index - (seats - 1) / 2) * (inner_w / seats)
        parts.append(
            box(
                f"cushion_{index}",
                (cushion_w, cushion_h, depth - 0.20),
                (offset, base_top + cushion_h / 2, seat_z),
                "fabric",
            )
        )
        parts.append(
            box(
                f"pillow_{index}",
                (cushion_w, min(0.34, back_h * 0.68), 0.10),
                (offset, base_top + 0.20, -depth / 2 + back_d + 0.05),
                "accent",
            )
        )
    return parts


def _armchair(width: float, depth: float, height: float) -> list[dict]:
    """单人扶手椅：比沙发窄，扶手只到座面以上 0.34。"""

    base_h = 0.20
    base_top = LEG_H + base_h
    back_d = 0.15
    back_h = max(height - base_top, 0.2)
    arm = 0.14
    inner_w = max(width - 2 * arm, 0.24)

    parts: list[dict] = []
    parts += legs4("leg", width, depth, LEG_H, inset=0.07, radius=0.02, material="wood")
    parts.append(box("base", (width, base_h, depth), (0, LEG_H + base_h / 2, 0), "fabric"))
    parts.append(
        box("back", (width, back_h, back_d), (0, base_top + back_h / 2, -depth / 2 + back_d / 2), "fabric")
    )
    for index, sx in enumerate((-1, 1)):
        parts.append(
            box(
                f"arm_{index}",
                (arm, 0.34, depth),
                (sx * (width / 2 - arm / 2), base_top + 0.17, 0),
                "fabric",
            )
        )
    parts.append(
        box("cushion", (inner_w, 0.13, depth - 0.18), (0, base_top + 0.065, 0.03), "fabric")
    )
    parts.append(
        box("pillow", (inner_w, 0.30, 0.09), (0, base_top + 0.26, -depth / 2 + back_d + 0.045), "accent")
    )
    return parts


@item(
    "sofa_three",
    "三人沙发",
    "furniture",
    tags=("沙发", "客厅", "布艺", "坐具", "sofa"),
    footprint=(2.10, 0.82, 0.92),
    source_item="couch-medium",
)
def build_sofa_three() -> list[dict]:
    return _sofa(2.10, 0.92, 0.82, 3)


@item(
    "sofa_two",
    "双人沙发",
    "furniture",
    tags=("沙发", "客厅", "布艺", "坐具", "sofa"),
    footprint=(1.62, 0.80, 0.88),
    source_item="couch-small",
)
def build_sofa_two() -> list[dict]:
    return _sofa(1.62, 0.88, 0.80, 2)


@item(
    "armchair",
    "单人扶手椅",
    "furniture",
    tags=("扶手椅", "休闲椅", "客厅", "armchair"),
    footprint=(0.86, 0.86, 0.88),
    source_item="livingroom-chair",
)
def build_armchair() -> list[dict]:
    return _armchair(0.86, 0.88, 0.86)


@item(
    "lounge_chair",
    "休闲躺椅",
    "furniture",
    tags=("躺椅", "休闲椅", "lounge"),
    footprint=(0.78, 0.78, 0.86),
    source_item="lounge-chair",
)
def build_lounge_chair() -> list[dict]:
    """后仰座面 + 高靠背：用倾斜的盒体表达，不追求布料褶皱。"""

    parts: list[dict] = []
    parts += legs4("leg", 0.72, 0.80, 0.14, inset=0.06, radius=0.022, material="wood")
    parts.append(box("seat", (0.72, 0.12, 0.72), (0, 0.22, 0.04), "fabric", rot=(0.06, 0, 0)))
    parts.append(box("back", (0.72, 0.52, 0.12), (0, 0.50, -0.32), "fabric", rot=(0.20, 0, 0)))
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"arm_{index}", (0.10, 0.24, 0.70), (sx * 0.31, 0.34, 0.03), "fabric"))
    return parts


@item(
    "bench",
    "长凳",
    "furniture",
    tags=("长凳", "餐椅", "bench"),
    footprint=(1.80, 0.45, 0.42),
    source_item="bench",
)
def build_bench() -> list[dict]:
    """木条座面：3 条板 + 4 条腿 + 一根横撑。"""

    width, depth, height = 1.80, 0.42, 0.45
    parts: list[dict] = []
    parts += legs4("leg", width, depth, height - 0.05, inset=0.05, radius=0.028, material="wood")
    plank = (depth - 0.02) / 3
    for index in range(3):
        z = -depth / 2 + plank / 2 + index * plank + 0.01 * (index - 1)
        parts.append(box(f"plank_{index}", (width, 0.045, plank - 0.015), (0, height - 0.0225, z), "wood"))
    parts.append(
        cyl("stretcher", 0.02, width - 0.16, (0, height * 0.35, 0), "wood", segments=12, rot=(0, 0, PI / 2))
    )
    return parts


def _chair(width: float, depth: float, height: float, seat_h: float) -> list[dict]:
    """通用靠背椅：4 腿 + 座板 + 靠背框 + 两根竖挡。"""

    seat_t = 0.045
    parts: list[dict] = []
    parts += legs4("leg", width, depth, seat_h, inset=0.045, radius=0.022, material="wood")
    parts.append(box("seat", (width, seat_t, depth), (0, seat_h - seat_t / 2, 0), "wood"))
    back_h = max(height - seat_h, 0.15)
    parts.append(
        box("back_rail", (width, 0.09, 0.04), (0, height - 0.045, -depth / 2 + 0.06), "wood")
    )
    for index, sx in enumerate((-1, 1)):
        parts.append(
            box(
                f"back_post_{index}",
                (0.04, back_h, 0.04),
                (sx * (width / 2 - 0.045), seat_h + back_h / 2, -depth / 2 + 0.06),
                "wood",
            )
        )
    parts.append(
        box("back_panel", (width - 0.13, back_h * 0.5, 0.02), (0, seat_h + back_h * 0.55, -depth / 2 + 0.06), "wood")
    )
    return parts


@item(
    "dining_chair",
    "餐椅",
    "furniture",
    tags=("餐椅", "椅子", "dining", "chair"),
    footprint=(0.45, 0.90, 0.50),
    source_item="dining-chair",
)
def build_dining_chair() -> list[dict]:
    return _chair(0.45, 0.50, 0.90, 0.44)


@item(
    "office_chair",
    "办公椅",
    "furniture",
    tags=("办公椅", "转椅", "office", "chair"),
    footprint=(0.62, 1.08, 0.62),
    source_item="office-chair",
)
def build_office_chair() -> list[dict]:
    """五星脚 + 气杆 + 座板 + 靠背：五个支脚用矩形截面扫掠。"""

    parts: list[dict] = []
    for index in range(5):
        angle = 2 * PI * index / 5
        import math

        tip = (0.30 * math.cos(angle), 0.055, 0.30 * math.sin(angle))
        parts.append(
            sweep(
                f"foot_{index}",
                [[-0.022, -0.022], [0.022, -0.022], [0.022, 0.022], [-0.022, 0.022]],
                [(0, 0.11, 0), tip],
                "metal",
                closed=True,
                caps=True,
            )
        )
        parts.append(cyl(f"caster_{index}", 0.028, 0.055, (tip[0], 0.028, tip[2]), "metal", segments=12))
    parts.append(cyl("gas_lift", 0.028, 0.34, (0, 0.11 + 0.17, 0), "metal", segments=16))
    parts.append(box("seat", (0.50, 0.08, 0.48), (0, 0.48, 0), "fabric"))
    parts.append(box("back", (0.46, 0.52, 0.06), (0, 0.78, -0.22), "fabric", rot=(0.10, 0, 0)))
    parts.append(box("armrest_l", (0.05, 0.04, 0.26), (-0.25, 0.60, 0.02), "metal"))
    parts.append(box("armrest_r", (0.05, 0.04, 0.26), (0.25, 0.60, 0.02), "metal"))
    return parts


@item(
    "stool_bar",
    "吧凳",
    "furniture",
    tags=("吧凳", "凳子", "stool"),
    footprint=(0.38, 1.00, 0.38),
    source_item="stool",
)
def build_stool() -> list[dict]:
    """圆座 + 四腿 + 踏圈。"""

    parts: list[dict] = []
    parts += legs4("leg", 0.34, 0.34, 0.72, inset=0.02, radius=0.020, material="wood")
    parts.append(cyl("top", 0.19, 0.06, (0, 0.75, 0), "wood", segments=24))
    parts.append(cyl("ring", 0.16, 0.02, (0, 0.26, 0), "metal", radius_top=0.17, segments=16))
    return parts
