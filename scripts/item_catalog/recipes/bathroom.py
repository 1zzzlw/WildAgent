"""卫浴：浴缸、马桶、洗手台、淋浴间、洗衣机、毛巾架、脏衣篮、地垫、卷纸。"""

from __future__ import annotations

from ..dsl import PI, box, cyl, sweep
from .registry import item
from .tables import _base_cabinet


@item("toilet", "马桶", "bathroom", tags=("马桶", "坐便器", "toilet"), footprint=(0.42, 0.82, 0.72), source_item="toilet")
def build_toilet() -> list[dict]:
    """座体（前圆后方）+ 水箱 + 座圈 + 盖板。"""

    parts: list[dict] = [box("base", (0.34, 0.36, 0.42), (0, 0.18, 0.06), "stone")]
    parts.append(cyl("bowl", 0.185, 0.10, (0, 0.40, 0.10), "stone", segments=24))
    parts.append(cyl("seat", 0.195, 0.035, (0, 0.455, 0.10), "stone", segments=24))
    parts.append(box("tank", (0.40, 0.32, 0.19), (0, 0.56, -0.26), "stone"))
    parts.append(box("lid", (0.38, 0.025, 0.17), (0, 0.73, -0.26), "stone"))
    parts.append(box("flush", (0.09, 0.014, 0.05), (0.12, 0.735, -0.26), "metal"))
    return parts


@item("bathtub", "浴缸", "bathroom", tags=("浴缸", "泡澡", "bathtub"), footprint=(2.34, 0.79, 1.11), source_item="bathtub")
def build_bathtub() -> list[dict]:
    """四壁 + 底 + 外裙板。内腔靠四壁围合表达，不做布尔挖洞。"""

    width, depth, height = 2.34, 1.11, 0.79
    wall = 0.10
    parts: list[dict] = [
        box("bottom", (width, 0.08, depth), (0, 0.04, 0), "stone"),
        box("wall_f", (width, height - 0.08, wall), (0, (height + 0.08) / 2, depth / 2 - wall / 2), "stone"),
        box("wall_b", (width, height - 0.08, wall), (0, (height + 0.08) / 2, -depth / 2 + wall / 2), "stone"),
        box("wall_l", (wall, height - 0.08, depth - wall * 2), (-width / 2 + wall / 2, (height + 0.08) / 2, 0), "stone"),
        box("wall_r", (wall, height - 0.08, depth - wall * 2), (width / 2 - wall / 2, (height + 0.08) / 2, 0), "stone"),
        box("rim", (width + 0.02, 0.045, depth + 0.02), (0, height - 0.02, 0), "stone"),
    ]
    parts.append(cyl("drain", 0.045, 0.01, (0, 0.085, 0.10), "metal", segments=16))
    parts.append(cyl("faucet", 0.022, 0.18, (-width / 2 + 0.16, height + 0.06, 0), "metal", segments=12))
    parts.append(sweep("spout", [[-0.012, -0.012], [0.012, -0.012], [0.012, 0.012], [-0.012, 0.012]],
                       [(-width / 2 + 0.16, height + 0.14, 0), (-width / 2 + 0.20, height + 0.14, 0.12)], "metal"))
    return parts


@item("bathroom_sink", "洗手台", "bathroom", tags=("洗手台", "台盆", "sink"), footprint=(1.83, 0.97, 0.63), source_item="bathroom-sink")
def build_bathroom_sink() -> list[dict]:
    """双盆柜体 + 两个台盆 + 两个龙头 + 镜子。"""

    width, depth, height = 1.83, 0.63, 0.97
    parts = _base_cabinet(width, depth, height - 0.18, doors=3, drawers=0)
    # 把柜体抬高 0.18（洗手台下方留空）
    for part in parts:
        position = part.get("position")
        if position:
            part["position"] = [position[0], round(position[1] + 0.18, 4), position[2]]
    for index, sx in enumerate((-1, 1)):
        cx = sx * width * 0.24
        parts.append(cyl(f"basin_{index}", 0.20, 0.13, (cx, height - 0.03, 0.02), "stone", segments=28))
        parts.append(cyl(f"faucet_{index}", 0.018, 0.22, (cx, height + 0.11, -0.16), "metal", segments=12))
        parts.append(
            sweep(
                f"spout_{index}",
                [[-0.010, -0.010], [0.010, -0.010], [0.010, 0.010], [-0.010, 0.010]],
                [(cx, height + 0.20, -0.16), (cx, height + 0.20, -0.06)],
                "metal",
            )
        )
    return parts


@item("mirror_round", "圆镜", "decor", tags=("镜子", "圆形", "mirror"), footprint=(0.57, 0.57, 0.05), source_item="round-mirror")
def build_mirror_round() -> list[dict]:
    """镜面朝 +Z，原点在镜子底边中心（挂放时按底面吸附）。"""

    parts: list[dict] = [cyl("frame", 0.285, 0.035, (0, 0.30, 0), "metal", segments=36)]
    parts.append(cyl("glass", 0.265, 0.012, (0, 0.30, 0.022), "glass", segments=36))
    return parts


@item("mirror_rect", "方镜", "decor", tags=("镜子", "方形", "mirror"), footprint=(0.60, 0.80, 0.05), source_item="rectangular-mirror")
def build_mirror_rect() -> list[dict]:
    parts: list[dict] = [box("frame", (0.60, 0.80, 0.035), (0, 0.40, 0), "metal")]
    parts.append(box("glass", (0.56, 0.76, 0.012), (0, 0.40, 0.022), "glass"))
    return parts


@item("shower_square", "方形淋浴间", "bathroom", tags=("淋浴", "淋浴房", "shower"), footprint=(0.81, 1.80, 0.81), source_item="shower-square")
def build_shower_square() -> list[dict]:
    """底盘 + 两面玻璃围挡 + 立柱 + 顶喷。"""

    size, height = 0.81, 1.80
    glass_t = 0.012
    parts: list[dict] = [box("tray", (size, 0.06, size), (0, 0.03, 0), "stone")]
    parts.append(box("glass_back", (size, height - 0.06, glass_t), (0, (height + 0.06) / 2, -size / 2 + glass_t / 2), "glass"))
    parts.append(box("glass_side", (glass_t, height - 0.06, size), (-size / 2 + glass_t / 2, (height + 0.06) / 2, 0), "glass"))
    parts.append(cyl("column", 0.028, height, (size / 2 - 0.06, height / 2, -size / 2 + 0.06), "metal", segments=12))
    parts.append(cyl("head", 0.11, 0.025, (size / 2 - 0.06, height - 0.10, -size / 2 + 0.18), "metal", segments=24))
    parts.append(cyl("drain", 0.04, 0.008, (0, 0.066, 0), "metal", segments=16))
    return parts


@item("shower_angle", "转角淋浴间", "bathroom", tags=("淋浴", "转角", "shower"), footprint=(0.83, 1.81, 0.83), source_item="shower-angle")
def build_shower_angle() -> list[dict]:
    """两面玻璃 + 扇形底盘（用圆柱近似）。"""

    size, height = 0.83, 1.81
    parts: list[dict] = [cyl("tray", size / 2, 0.06, (0, 0.03, 0), "stone", segments=32)]
    parts.append(box("glass_back", (size, height - 0.06, 0.012), (0, (height + 0.06) / 2, -size / 2 + 0.006), "glass"))
    parts.append(box("glass_side", (0.012, height - 0.06, size), (-size / 2 + 0.006, (height + 0.06) / 2, 0), "glass"))
    parts.append(cyl("column", 0.026, height, (0, height / 2, -size / 2 + 0.08), "metal", segments=12))
    parts.append(cyl("head", 0.10, 0.022, (0, height - 0.08, -size / 2 + 0.22), "metal", segments=22))
    return parts


@item("washing_machine", "洗衣机", "bathroom", tags=("洗衣机", "家电", "washing"), footprint=(0.60, 0.86, 0.53), source_item="washing-machine")
def build_washing_machine() -> list[dict]:
    """箱体 + 前面板 + 圆形舱门 + 控制旋钮。"""

    width, depth, height = 0.60, 0.53, 0.86
    parts: list[dict] = [box("cabinet", (width, height - 0.04, depth), (0, (height - 0.04) / 2 + 0.04, 0), "stone")]
    parts.append(cyl("door", 0.19, 0.05, (0, 0.44, depth / 2 - 0.01), "glass", segments=32, rot=(PI / 2, 0, 0)))
    parts.append(cyl("rim", 0.205, 0.012, (0, 0.44, depth / 2 + 0.008), "metal", segments=32, rot=(PI / 2, 0, 0)))
    parts.append(cyl("knob", 0.035, 0.03, (0.17, height - 0.10, depth / 2 + 0.01), "metal", segments=16, rot=(PI / 2, 0, 0)))
    parts.append(box("panel", (width - 0.04, 0.10, 0.02), (0, height - 0.10, depth / 2 + 0.002), "metal"))
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"foot_{index}", (0.05, 0.04, 0.05), (sx * (width / 2 - 0.08), 0.02, 0), "metal"))
    return parts


@item("paper_roll_holder", "卷纸架", "bathroom", tags=("卷纸", "卫浴", "paper"), footprint=(0.26, 0.27, 0.24), source_item="toilet-paper")
def build_paper_roll_holder() -> list[dict]:
    parts: list[dict] = [cyl("roll", 0.055, 0.11, (0, 0.18, 0), "fabric", segments=24, rot=(0, 0, PI / 2))]
    parts.append(box("holder", (0.02, 0.10, 0.20), (-0.075, 0.18, 0), "metal"))
    parts.append(box("wall_plate", (0.03, 0.14, 0.12), (-0.095, 0.15, 0), "metal"))
    return parts


@item("laundry_bag", "脏衣篮", "bathroom", tags=("脏衣篮", "收纳", "laundry"), footprint=(0.46, 0.78, 0.48), source_item="laundry-bag")
def build_laundry_bag() -> list[dict]:
    """圆柱布袋 + 顶部束口。"""

    parts: list[dict] = [cyl("bag", 0.23, 0.70, (0, 0.35, 0), "fabric", radius_top=0.21, segments=28)]
    parts.append(cyl("collar", 0.215, 0.045, (0, 0.72, 0), "fabric", segments=28))
    parts.append(cyl("rim", 0.218, 0.012, (0, 0.745, 0), "metal", segments=28))
    return parts


@item("drying_rack", "晾衣架", "bathroom", tags=("晾衣架", "阳台", "drying"), footprint=(1.79, 1.05, 0.58), source_item="drying-rack")
def build_drying_rack() -> list[dict]:
    """两侧 A 形支架 + 多根横杆 + 轮子。"""

    width, depth, height = 1.79, 0.58, 1.05
    parts: list[dict] = []
    # A 形支架：顶点在顶部，两条腿张到两个脚点。用扫掠而不是旋转盒体 ——
    # 绕中点旋转会让腿的中点落不到顶，侧视看着像交叉的 X。
    for index, sx in enumerate((-1, 1)):
        x = sx * (width / 2 - 0.08)
        parts.append(
            sweep(
                f"leg_a_{index}",
                [[-0.017, -0.017], [0.017, -0.017], [0.017, 0.017], [-0.017, 0.017]],
                [(x, height, 0), (x, 0.04, depth / 2 - 0.12)],
                "metal",
            )
        )
        parts.append(
            sweep(
                f"leg_b_{index}",
                [[-0.017, -0.017], [0.017, -0.017], [0.017, 0.017], [-0.017, 0.017]],
                [(x, height, 0), (x, 0.04, -depth / 2 + 0.12)],
                "metal",
            )
        )
        for wheel_index, sz in enumerate((depth / 2 - 0.14, -depth / 2 + 0.14)):
            parts.append(cyl(f"wheel_{index}_{wheel_index}", 0.035, 0.02, (x, 0.035, sz), "metal", segments=12, rot=(0, 0, PI / 2)))
    for index in range(5):
        y = 0.55 + index * 0.10
        parts.append(cyl(f"bar_{index}", 0.011, width - 0.16, (0, y, 0), "metal", segments=10, rot=(0, 0, PI / 2)))
    parts.append(cyl("top_bar", 0.013, width - 0.12, (0, height - 0.02, 0), "metal", segments=10, rot=(0, 0, PI / 2)))
    return parts


@item("shower_rug", "浴室地垫", "bathroom", tags=("地垫", "浴室", "rug"), footprint=(0.77, 0.03, 0.48), source_item="shower-rug")
def build_shower_rug() -> list[dict]:
    return [box("mat", (0.77, 0.024, 0.48), (0, 0.012, 0), "fabric")]
