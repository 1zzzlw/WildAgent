"""灯具：台灯、落地灯、吊灯、筒灯。

物品里的灯**不发光** —— 需要真实照明用 `light` 组件（有独立的调光与投影）。
这一条与 `subtypes.py` 里 lamp 的 `height_meaning` 说明一致，不要拆成两种说法。
"""

from __future__ import annotations

import math

from ..dsl import PI, box, cyl, sweep
from .registry import item


def _shade(radius_bottom: float, radius_top: float, height: float, y: float, material: str = "fabric", segments: int = 28) -> dict:
    """灯罩：倒圆台（下大上小）。"""

    return cyl(
        "shade",
        radius_bottom,
        height,
        (0, y, 0),
        material,
        radius_top=radius_top,
        segments=segments,
    )


@item("table_lamp", "台灯", "lighting", tags=("台灯", "灯具", "lamp"), footprint=(0.29, 0.74, 0.29), source_item="table-lamp")
def build_table_lamp() -> list[dict]:
    parts: list[dict] = [cyl("base", 0.09, 0.03, (0, 0.015, 0), "metal", radius_top=0.075, segments=20)]
    parts.append(cyl("stem", 0.016, 0.46, (0, 0.26, 0), "metal", segments=12))
    parts.append(_shade(0.145, 0.10, 0.22, 0.60))
    return parts


@item("floor_lamp", "落地灯", "lighting", tags=("落地灯", "灯具", "lamp"), footprint=(0.30, 1.70, 0.30), source_item="floor-lamp")
def build_floor_lamp() -> list[dict]:
    """单杆落地灯：重底座 + 立杆 + 大灯罩。"""

    parts: list[dict] = [cyl("base", 0.16, 0.035, (0, 0.018, 0), "metal", segments=28)]
    parts.append(cyl("stem", 0.018, 1.42, (0, 0.73, 0), "metal", segments=12))
    parts.append(_shade(0.185, 0.13, 0.28, 1.56))
    return parts


@item("tripod_floor_lamp", "三脚落地灯", "lighting", tags=("落地灯", "三脚", "lamp"), footprint=(0.70, 1.86, 0.69), source_item="floor-lamp")
def build_tripod_floor_lamp() -> list[dict]:
    """三条外撇腿 + 灯罩 —— 与单杆款区分，避免目录里重复。"""

    parts: list[dict] = []
    for index in range(3):
        angle = 2 * PI * index / 3
        parts.append(
            sweep(
                f"leg_{index}",
                [[-0.018, -0.018], [0.018, -0.018], [0.018, 0.018], [-0.018, 0.018]],
                [(0, 1.18, 0), (0.30 * math.cos(angle), 0.02, 0.30 * math.sin(angle))],
                "wood",
            )
        )
    parts.append(_shade(0.21, 0.15, 0.30, 1.30))
    return parts


@item("ceiling_lamp", "吊灯", "lighting", tags=("吊灯", "灯具", "pendant"), footprint=(0.55, 0.86, 0.55), source_item="ceiling-lamp")
def build_ceiling_lamp() -> list[dict]:
    """吊线 + 倒圆台灯罩。挂点在上方，物品原点在灯罩底。"""

    parts: list[dict] = [cyl("cord", 0.006, 0.42, (0, 1.16, 0), "metal", segments=8)]
    parts.append(cyl("cap", 0.045, 0.03, (0, 0.94, 0), "metal", segments=16))
    parts.append(_shade(0.275, 0.09, 0.30, 0.74))
    return parts


@item("ceiling_light_round", "吸顶灯", "lighting", tags=("吸顶灯", "灯具", "ceiling"), footprint=(0.55, 0.12, 0.55), source_item="circular-ceiling-light")
def build_ceiling_light() -> list[dict]:
    parts: list[dict] = [cyl("plate", 0.26, 0.03, (0, 0.10, 0), "metal", segments=32)]
    parts.append(cyl("diffuser", 0.24, 0.06, (0, 0.055, 0), "glass", segments=32))
    return parts


@item("recessed_light", "筒灯", "lighting", tags=("筒灯", "射灯", "recessed"), footprint=(0.23, 0.06, 0.23), source_item="recessed-light")
def build_recessed_light() -> list[dict]:
    parts: list[dict] = [cyl("ring", 0.115, 0.022, (0, 0.011, 0), "metal", segments=24)]
    parts.append(cyl("lens", 0.095, 0.01, (0, 0.0, 0), "glass", segments=24))
    return parts
