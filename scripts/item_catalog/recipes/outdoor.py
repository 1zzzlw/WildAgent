"""户外与交通：乔木、灌木、篮球架、停车位、躺床、滑板、遮阳伞、柱、车辆。"""

from __future__ import annotations

import math

from ..dsl import PI, box, cyl, sphere, sweep
from .registry import item


@item("tree_broadleaf", "阔叶树", "outdoor", tags=("树", "乔木", "tree"), footprint=(0.80, 5.00, 0.85), source_item="tree")
def build_tree() -> list[dict]:
    """干 + 三级枝 + 三个树冠球。"""

    parts: list[dict] = [cyl("trunk", 0.12, 2.60, (0, 1.30, 0), "wood", radius_top=0.085, segments=14)]
    for index in range(3):
        angle = 2 * PI * index / 3
        parts.append(
            sweep(
                f"branch_{index}",
                [[-0.05, -0.05], [0.05, -0.05], [0.05, 0.05], [-0.05, 0.05]],
                [(0, 2.20, 0), (0.55 * math.cos(angle), 3.10, 0.55 * math.sin(angle))],
                "wood",
            )
        )
    for index, (cx, cy, cz, radius) in enumerate(
        ((0.0, 4.30, 0.0, 1.05), (0.62, 3.70, 0.35, 0.72), (-0.55, 3.85, -0.30, 0.68))
    ):
        parts.append(sphere(f"crown_{index}", radius, (cx, cy, cz), "foliage", segments=18))
    return parts


@item("fir_tree", "杉树", "outdoor", tags=("杉树", "针叶", "fir"), footprint=(0.90, 3.00, 0.90), source_item="fir-tree")
def build_fir_tree() -> list[dict]:
    """圆锥分层：三层倒圆台叠起来。"""

    parts: list[dict] = [cyl("trunk", 0.07, 0.45, (0, 0.22, 0), "wood", segments=12)]
    layers = ((1.45, 0.00, 0.42), (1.10, 0.55, 0.32), (0.72, 1.35, 0.22))
    for index, (radius, base_y, top_radius) in enumerate(layers):
        parts.append(
            cyl(
                f"crown_{index}",
                radius,
                1.25 - index * 0.15,
                (0, base_y + (1.25 - index * 0.15) / 2 + 0.35, 0),
                "foliage",
                radius_top=top_radius,
                segments=22,
            )
        )
    return parts


@item("palm_tree", "棕榈树", "outdoor", tags=("棕榈", "热带", "palm"), footprint=(0.60, 4.50, 0.60), source_item="palm")
def build_palm() -> list[dict]:
    """微弯树干（分段盒体）+ 6 片下垂叶。"""

    parts: list[dict] = []
    segments = 6
    for index in range(segments):
        t = index / segments
        parts.append(
            cyl(
                f"trunk_{index}",
                0.10 - t * 0.02,
                0.80,
                (0.28 * t * t, 0.40 + index * 0.76, 0.0),
                "wood",
                segments=12,
                rot=(0, 0, -0.12 * t),
            )
        )
    top = (0.28, 4.50, 0.0)
    for index in range(6):
        angle = 2 * PI * index / 6
        parts.append(
            sweep(
                f"frond_{index}",
                [[-0.11, -0.012], [0.11, -0.012], [0.11, 0.012], [-0.11, 0.012]],
                [
                    top,
                    (top[0] + 0.55 * math.cos(angle), top[1] + 0.28, 0.55 * math.sin(angle)),
                    (top[0] + 1.05 * math.cos(angle), top[1] - 0.18, 1.05 * math.sin(angle)),
                ],
                "foliage",
            )
        )
    return parts


@item("bush", "灌木丛", "outdoor", tags=("灌木", "绿植", "bush"), footprint=(3.00, 1.04, 1.01), source_item="bush")
def build_bush() -> list[dict]:
    """五个交叠球体，横向铺开。"""

    parts: list[dict] = []
    for index, (cx, cz, radius) in enumerate(
        ((-1.05, 0.0, 0.42), (-0.45, 0.18, 0.50), (0.20, -0.10, 0.52), (0.85, 0.14, 0.45), (1.32, -0.06, 0.36))
    ):
        parts.append(sphere(f"clump_{index}", radius, (cx, radius * 0.92, cz), "foliage", segments=16))
    return parts


@item("ball", "球", "outdoor", tags=("球", "体育", "ball"), footprint=(0.24, 0.24, 0.24), source_item="ball")
def build_ball() -> list[dict]:
    return [sphere("ball", 0.12, (0, 0.12, 0), "accent", segments=22)]


@item("basketball_hoop", "篮球架", "outdoor", tags=("篮球架", "体育", "hoop"), footprint=(1.40, 1.78, 0.56), source_item="basket-hoop")
def build_basketball_hoop() -> list[dict]:
    """立柱 + 斜撑 + 篮板 + 篮圈 + 网（用圆台近似）。"""

    parts: list[dict] = [cyl("post", 0.06, 1.70, (0, 0.85, -0.22), "metal", segments=14)]
    parts.append(cyl("base", 0.20, 0.05, (0, 0.025, -0.22), "metal", segments=18))
    parts.append(box("arm", (0.06, 0.06, 0.30), (0, 1.62, -0.06), "metal"))
    parts.append(box("board", (1.10, 0.72, 0.04), (0, 1.44, 0.10), "glass"))
    parts.append(box("target", (0.45, 0.30, 0.012), (0, 1.36, 0.125), "accent"))
    parts.append(cyl("rim", 0.225, 0.02, (0, 1.18, 0.30), "accent", segments=28))
    parts.append(cyl("net", 0.20, 0.30, (0, 1.02, 0.30), "fabric", radius_top=0.225, segments=20))
    return parts


@item("parking_spot", "停车位", "outdoor", tags=("停车位", "标线", "parking"), footprint=(4.95, 0.12, 2.28), source_item="parking-spot")
def build_parking_spot() -> list[dict]:
    """地面标线（薄片）+ 后挡车器。"""

    width, depth = 4.95, 2.28
    parts: list[dict] = [box("line_l", (0.10, 0.012, depth), (-width / 2 + 0.05, 0.006, 0), "accent")]
    parts.append(box("line_r", (0.10, 0.012, depth), (width / 2 - 0.05, 0.006, 0), "accent"))
    parts.append(box("line_b", (width, 0.012, 0.10), (0, 0.006, -depth / 2 + 0.05), "accent"))
    parts.append(box("stop", (1.60, 0.11, 0.16), (0, 0.055, -depth / 2 + 0.18), "stone"))
    return parts


@item("sunbed", "户外躺床", "outdoor", tags=("躺床", "泳池", "sunbed"), footprint=(0.86, 1.13, 1.01), source_item="sunbed")
def build_sunbed() -> list[dict]:
    """平躺段 + 可抬靠背 + 四腿。"""

    parts: list[dict] = []
    for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        parts.append(box(f"leg_{index}", (0.05, 0.28, 0.05), (sx * 0.34, 0.14, sz * 0.40), "metal"))
    parts.append(box("frame", (0.78, 0.06, 0.90), (0, 0.31, 0.06), "wood"))
    parts.append(box("mattress", (0.72, 0.06, 0.86), (0, 0.37, 0.06), "fabric"))
    parts.append(box("backrest", (0.72, 0.06, 0.56), (0, 0.62, -0.44), "fabric", rot=(-0.72, 0, 0)))
    return parts


@item("skateboard", "滑板", "outdoor", tags=("滑板", "运动", "skate"), footprint=(0.86, 0.11, 0.20), source_item="skate")
def build_skateboard() -> list[dict]:
    parts: list[dict] = [box("deck", (0.80, 0.012, 0.20), (0, 0.085, 0), "wood")]
    parts.append(box("grip", (0.78, 0.004, 0.19), (0, 0.092, 0), "accent"))
    for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        parts.append(cyl(f"wheel_{index}", 0.028, 0.032, (sx * 0.28, 0.028, sz * 0.07), "accent", segments=12, rot=(PI / 2, 0, 0)))
        parts.append(box(f"truck_{index}", (0.06, 0.03, 0.14), (sx * 0.28, 0.062, 0), "metal"))
    return parts


@item("playhouse", "儿童玩具屋", "outdoor", tags=("玩具屋", "儿童", "playhouse"), footprint=(0.72, 0.47, 0.60), source_item="outdoor-playhouse")
def build_playhouse() -> list[dict]:
    """墙身 + 双坡顶 + 门洞。"""

    width, depth, height = 0.72, 0.60, 0.30
    parts: list[dict] = [box("body", (width, height, depth), (0, height / 2, 0), "wood")]
    parts.append(box("roof_l", (width * 0.62, 0.03, depth * 1.05), (-width * 0.26, height + 0.09, 0), "accent", rot=(0, 0, 0.62)))
    parts.append(box("roof_r", (width * 0.62, 0.03, depth * 1.05), (width * 0.26, height + 0.09, 0), "accent", rot=(0, 0, -0.62)))
    parts.append(box("door", (0.26, 0.22, 0.02), (0, 0.11, depth / 2 + 0.01), "accent"))
    return parts


@item("patio_umbrella", "遮阳伞", "outdoor", tags=("遮阳伞", "户外", "umbrella"), footprint=(2.40, 2.40, 2.40), source_item="patio-umbrella")
def build_patio_umbrella() -> list[dict]:
    """底座 + 杆 + 八边形伞面（倒圆台）+ 顶帽。"""

    parts: list[dict] = [cyl("base", 0.30, 0.08, (0, 0.04, 0), "stone", segments=24)]
    parts.append(cyl("pole", 0.025, 2.10, (0, 1.05, 0), "metal", segments=12))
    parts.append(cyl("canopy", 1.20, 0.42, (0, 2.10, 0), "fabric", radius_top=0.10, segments=8))
    parts.append(cyl("cap", 0.05, 0.06, (0, 2.34, 0), "metal", segments=12))
    for index in range(8):
        angle = 2 * PI * index / 8
        parts.append(
            sweep(
                f"rib_{index}",
                [[-0.010, -0.010], [0.010, -0.010], [0.010, 0.010], [-0.010, 0.010]],
                [(0, 2.32, 0), (1.18 * math.cos(angle), 1.94, 1.18 * math.sin(angle))],
                "metal",
            )
        )
    return parts


@item("pillar", "装饰柱", "outdoor", tags=("柱", "门廊", "pillar"), footprint=(0.34, 1.26, 0.30), source_item="pillar")
def build_pillar() -> list[dict]:
    """柱础 + 柱身 + 柱头。真正的承重柱请用 `column` 构件（参与结构校验）。"""

    height = 1.26
    parts: list[dict] = [box("base", (0.34, 0.10, 0.30), (0, 0.05, 0), "stone")]
    parts.append(box("shaft", (0.24, height - 0.20, 0.22), (0, height / 2, 0), "stone"))
    parts.append(box("capital", (0.34, 0.10, 0.30), (0, height - 0.05, 0), "stone"))
    return parts


@item("scooter", "电动滑板车", "outdoor", tags=("滑板车", "代步", "scooter"), footprint=(0.85, 1.10, 0.45), source_item="scooter")
def build_scooter() -> list[dict]:
    parts: list[dict] = [box("deck", (0.14, 0.04, 0.72), (0, 0.11, 0.0), "metal")]
    parts.append(sweep("stem", [[-0.025, -0.025], [0.025, -0.025], [0.025, 0.025], [-0.025, 0.025]],
                       [(0, 0.13, -0.34), (0, 1.02, -0.44)], "metal"))
    parts.append(box("handlebar", (0.46, 0.03, 0.03), (0, 1.04, -0.44), "metal"))
    for index, sz in enumerate((0.36, -0.40)):
        parts.append(cyl(f"wheel_{index}", 0.10, 0.06, (0, 0.10, sz), "accent", segments=18, rot=(0, 0, PI / 2)))
    return parts


def _car(
    length: float,
    width: float,
    height: float,
    *,
    roof_ratio: float = 0.52,
    roof_height: float = 0.46,
    body_material: str = "metal",
) -> list[dict]:
    """车身 + 座舱 + 四轮 + 前后灯。原点在底面中心，车头朝 +Z。"""

    wheel_r = 0.32
    body_h = height - roof_height - wheel_r
    body_y = wheel_r + body_h / 2
    parts: list[dict] = [box("body", (width, body_h, length), (0, body_y, 0), body_material)]
    cabin_len = length * roof_ratio
    cabin_y = wheel_r + body_h + roof_height / 2
    parts.append(box("cabin", (width * 0.90, roof_height, cabin_len), (0, cabin_y, -length * 0.04), body_material))
    parts.append(
        box(
            "windshield",
            (width * 0.84, roof_height * 0.70, 0.03),
            (0, cabin_y - roof_height * 0.08, -length * 0.04 + cabin_len / 2),
            "glass",
        )
    )
    for index, sz in enumerate((length / 2 - 0.62, -length / 2 + 0.62)):
        for side, sx in enumerate((-1, 1)):
            parts.append(
                cyl(
                    f"wheel_{index}_{side}",
                    wheel_r,
                    0.20,
                    (sx * (width / 2 - 0.06), wheel_r, sz),
                    "accent",
                    segments=18,
                    rot=(0, 0, PI / 2),
                )
            )
    for side, sx in enumerate((-1, 1)):
        parts.append(box(f"headlight_{side}", (0.16, 0.10, 0.04), (sx * width * 0.28, wheel_r + body_h * 0.6, length / 2 + 0.01), "glass"))
        parts.append(box(f"taillight_{side}", (0.14, 0.08, 0.04), (sx * width * 0.28, wheel_r + body_h * 0.6, -length / 2 - 0.01), "accent"))
    return parts


@item("car_sedan", "轿车", "outdoor", tags=("汽车", "轿车", "car"), footprint=(4.76, 1.52, 1.98), source_item="tesla")
def build_car_sedan() -> list[dict]:
    return _car(4.76, 1.98, 1.62, roof_ratio=0.50, roof_height=0.52)


@item("car_hatchback", "两厢车", "outdoor", tags=("汽车", "两厢", "car"), footprint=(4.09, 1.40, 1.89), source_item="1967-chevrolet-camaro-moa24wsf")
def build_car_hatchback() -> list[dict]:
    return _car(4.09, 1.89, 1.40, roof_ratio=0.46, roof_height=0.44)


@item("car_toy", "玩具车", "outdoor", tags=("玩具", "车", "toy"), footprint=(0.60, 0.34, 0.31), source_item="car-toy")
def build_car_toy() -> list[dict]:
    parts: list[dict] = [box("body", (0.26, 0.12, 0.56), (0, 0.16, 0), "accent")]
    parts.append(box("cabin", (0.22, 0.09, 0.26), (0, 0.255, -0.04), "accent"))
    parts.append(box("windshield", (0.20, 0.07, 0.012), (0, 0.255, 0.093), "screen"))
    for index, sz in enumerate((0.18, -0.18)):
        for side, sx in enumerate((-1, 1)):
            parts.append(cyl(f"wheel_{index}_{side}", 0.06, 0.03, (sx * 0.12, 0.06, sz), "metal", segments=12, rot=(0, 0, PI / 2)))
    return parts
