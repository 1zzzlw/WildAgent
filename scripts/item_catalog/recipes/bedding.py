"""床类：单人床、双人床、上下铺。"""

from __future__ import annotations

from ..dsl import box, cyl, legs4
from .registry import item


def _bed(
    width: float,
    depth: float,
    height: float,
    *,
    pillows: int = 2,
    quilt: bool = True,
    headboard_h: float | None = None,
    leg_h: float = 0.12,
) -> list[dict]:
    """床架 + 床垫 + 床头板 + 枕头 + 被子。

    `depth` 是床长方向（Z），床头在 -Z 侧，与物品"正面 +Z"的约定一致。
    """

    frame_h = 0.16
    mattress_h = 0.22
    frame_top = leg_h + frame_h
    head_h = headboard_h if headboard_h is not None else height
    edge = 0.05

    parts: list[dict] = []
    parts += legs4("leg", width, depth, leg_h, inset=0.07, radius=0.028, material="wood")
    # 床架四边板
    parts.append(box("frame_l", (edge, frame_h, depth), (-width / 2 + edge / 2, leg_h + frame_h / 2, 0), "wood"))
    parts.append(box("frame_r", (edge, frame_h, depth), (width / 2 - edge / 2, leg_h + frame_h / 2, 0), "wood"))
    parts.append(box("frame_f", (width - edge * 2, frame_h, edge), (0, leg_h + frame_h / 2, depth / 2 - edge / 2), "wood"))
    parts.append(box("frame_b", (width - edge * 2, frame_h, edge), (0, leg_h + frame_h / 2, -depth / 2 + edge / 2), "wood"))
    parts.append(box("mattress", (width - 0.08, mattress_h, depth - 0.10), (0, frame_top + mattress_h / 2, 0), "fabric"))
    # 床头板
    parts.append(
        box("headboard", (width, head_h - leg_h, 0.07), (0, leg_h + (head_h - leg_h) / 2, -depth / 2 - 0.02), "wood")
    )
    # 枕头
    pillow_w = (width - 0.20) / max(pillows, 1) - 0.06
    for index in range(pillows):
        x = (index - (pillows - 1) / 2) * ((width - 0.20) / max(pillows, 1))
        parts.append(
            box(f"pillow_{index}", (pillow_w, 0.11, 0.32), (x, frame_top + mattress_h + 0.055, -depth / 2 + 0.42), "fabric")
        )
    if quilt:
        quilt_len = depth * 0.66
        parts.append(
            box(
                "quilt",
                (width - 0.06, 0.055, quilt_len),
                (0, frame_top + mattress_h + 0.028, depth / 2 - quilt_len / 2 - 0.04),
                "accent",
            )
        )
    return parts


@item("single_bed", "单人床", "furniture", tags=("床", "单人床", "bed"), footprint=(1.08, 0.60, 2.14), source_item="single-bed")
def build_single_bed() -> list[dict]:
    return _bed(1.08, 2.14, 0.60, pillows=1)


@item("double_bed", "双人床", "furniture", tags=("床", "双人床", "bed"), footprint=(1.52, 0.71, 2.00), source_item="double-bed")
def build_double_bed() -> list[dict]:
    return _bed(1.52, 2.00, 0.71, pillows=2)


@item("bunk_bed", "上下铺", "furniture", tags=("床", "上下铺", "bunk"), footprint=(1.00, 1.55, 2.00), source_item="bunkbed")
def build_bunk_bed() -> list[dict]:
    """四根角柱 + 上下两层床板 + 上层护栏 + 侧边爬梯。"""

    width, depth, height = 1.00, 2.00, 1.55
    post = 0.06
    lower_y = 0.28
    upper_y = 1.05
    parts: list[dict] = []
    for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        parts.append(
            box(
                f"post_{index}",
                (post, height, post),
                (sx * (width / 2 - post / 2), height / 2, sz * (depth / 2 - post / 2)),
                "wood",
            )
        )
    for level, y in enumerate((lower_y, upper_y)):
        parts.append(box(f"deck_{level}", (width - post, 0.05, depth - post), (0, y, 0), "wood"))
        parts.append(box(f"mattress_{level}", (width - 0.10, 0.14, depth - 0.14), (0, y + 0.095, 0), "fabric"))
    # 上层护栏（前侧 + 两端）
    parts.append(box("guard_front", (width - post, 0.28, 0.04), (0, upper_y + 0.28, depth / 2 - post), "wood"))
    parts.append(box("guard_back", (width - post, 0.28, 0.04), (0, upper_y + 0.28, -depth / 2 + post), "wood"))
    # 爬梯：两根立杆 + 4 根横档
    ladder_x = width / 2 - post - 0.02
    for index, sz in enumerate((depth / 2 - 0.42, depth / 2 - 0.18)):
        parts.append(box(f"ladder_rail_{index}", (0.035, upper_y, 0.035), (ladder_x, upper_y / 2, sz), "wood"))
    for index in range(4):
        rung_y = 0.20 + index * 0.24
        parts.append(box(f"rung_{index}", (0.035, 0.03, 0.30), (ladder_x, rung_y, depth / 2 - 0.30), "wood"))
    return parts
