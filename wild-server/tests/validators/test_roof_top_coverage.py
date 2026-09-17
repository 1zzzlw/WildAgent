"""`validate_roof_top_coverage`（墙顶 → 屋顶 反向覆盖）的回归测试。

这个校验器存在的理由：`validate_roof_coverage` 只做 roof → wall **单向**检查，
从不问"这些墙上面有没有屋顶"。实测一份 L 形别墅只给主楼生成了屋顶，侧翼整块
裸露却 10/10 全绿。

下面是实现过程中真实踩到的坑，每条都留一个钉子，防止后人"顺手简化"回去：

1. 缺 `position` 的屋顶必须按前端 `resolver.ts::resolveRoofBoundary` 复原，
   直接跳过会把正常蓝图（bieshu / cabin_v1 只写 span/depth）误报成"完全裸露"。
2. 带 `curve` 的墙必须沿真实曲率采样，走 from→to 直线会把整圈圆墙退化成**一个点**
   （天坛 main_wall 的 from/to XZ 同为 [5.8, 0]）。
3. 重檐屋顶的底层檐口是 `span/2 + eaveOutset`，按 span/2 判覆盖会把圆墙误判裸露。
4. 阳台栏杆（矮、薄）不该参与结构墙判定。
5. 竖向只设下界、不设上界：墙顶略高于屋面基底是重檐 / 穿斗的正常做法；
   "屋顶悬空多高算不合理"归 `validate_roof_coverage` 管。
6. 采样点取等分格**中心**，不是端点：端点采样会把"墙端点落在屋顶外 4cm"
   放大成半个格的裸露（实测 session_1786700051751 报 0.5m）。
"""
from copy import deepcopy

from app.tools.spatial_tools import validate_roof_top_coverage

run_validator = getattr(
    validate_roof_top_coverage, "func", validate_roof_top_coverage,
)

WARNING = "⚠️"


def assert_covered(elements: list[dict]) -> None:
    """断言通过，且**确实走过了逐墙判定**。

    只断言 `startswith("✅")` 有空洞：屋顶被整块漏判时走的是"没有屋顶构件，
    跳过检查"分支，也以 ✅ 开头 —— 用例会假绿。
    """
    message = run_validator(blueprint(elements))
    assert message.startswith("✅"), message
    assert "均被屋顶" in message, message


def blueprint(elements: list[dict]) -> dict:
    return {
        "meta": {"name": "test", "units": "meters"},
        "geometry": {"elements": elements},
    }


def wall(id_, start, end, thickness=0.24, **extra) -> dict:
    return {
        "id": id_, "type": "wall",
        "from": list(start), "to": list(end),
        "thickness": thickness, **extra,
    }


def roof(id_, position, span, depth, roof_type="gable", **extra) -> dict:
    element = {
        "id": id_, "type": "roof", "roofType": roof_type,
        "span": span, "depth": depth, "height": 2.0, "thickness": 0.24,
    }
    if position is not None:
        element["position"] = list(position)
    element.update(extra)
    return element


def floor(id_, start, y=None, end=None, **extra) -> dict:
    start = list(start)
    return {
        "id": id_, "type": "floor",
        "from": start, "to": list(end), "thickness": 0.2, **extra,
    }


# ── 基础形态：主楼 + 侧翼 ────────────────────────────────────────────────
# 主楼 X[0,10] Z[0,8]，侧翼 X[10,16] Z[4,8]，与真实 L 形别墅同构。
L_SHAPE_WALLS = [
    wall("main_front", [0, 0, 0], [10, 3, 0]),
    wall("main_back", [10, 0, 8], [0, 3, 8]),
    wall("main_left", [0, 0, 8], [0, 3, 0]),
    wall("main_right", [10, 0, 0], [10, 3, 4]),
    wall("wing_front", [10, 0, 4], [16, 3, 4]),
    wall("wing_right", [16, 0, 4], [16, 3, 8]),
    wall("wing_back", [16, 0, 8], [10, 3, 8]),
]


def test_missing_wing_roof_is_reported() -> None:
    """只给主楼一块屋顶时，侧翼必须被点名 —— 这是本校验器的立身之本。"""
    elements = deepcopy(L_SHAPE_WALLS)
    elements.append(roof("roof_main", [5, 3, 4], 11, 9))
    elements.append(floor("floor_1", [0, 0, 0], end=[10, 0, 8]))

    message = run_validator(blueprint(elements))

    assert message.startswith(WARNING)
    for wall_id in ("wing_front", "wing_right", "wing_back"):
        assert wall_id in message
    assert "main_back" not in message


def test_every_volume_roofed_passes() -> None:
    """每个体量各配一块屋顶后应当通过。"""
    elements = deepcopy(L_SHAPE_WALLS)
    elements.append(roof("roof_main", [5, 3, 4], 11, 9))
    elements.append(roof("roof_wing", [13, 3, 6], 7, 5))

    assert_covered(elements)


def test_building_without_any_roof_is_reported() -> None:
    """有墙有楼板却零屋顶 —— 必须报「一块屋顶都没有」。"""
    elements = deepcopy(L_SHAPE_WALLS)
    elements.append(floor("floor_1", [0, 0, 0], end=[10, 0, 8]))

    message = run_validator(blueprint(elements))

    assert message.startswith(WARNING)
    assert "一块屋顶都没有" in message


def test_railing_walls_are_ignored() -> None:
    """栏杆矮（1.0m）且薄（0.08m），本就不该有屋顶，不得参与判定。"""
    elements = [
        wall("main_front", [0, 0, 0], [10, 3, 0]),
        wall("main_back", [10, 0, 8], [0, 3, 8]),
        wall("main_left", [0, 0, 8], [0, 3, 0]),
        wall("main_right", [10, 0, 0], [10, 3, 8]),
        roof("roof_main", [5, 3, 4], 11, 9),
        # 屋顶露台栏杆：from[1]=3.0 → to[1]=4.0，高 1.0m，厚 0.08m
        wall("railing_front", [0, 3, 8], [10, 4, 8], thickness=0.08),
        wall("railing_left", [0, 3, 8], [0, 4, 0], thickness=0.08),
    ]

    assert_covered(elements)


def test_roof_without_position_is_inferred_from_support_walls() -> None:
    """只写 span/depth、不写 position 的屋顶要被复原，不能整块漏判。"""
    elements = [
        wall("front", [0, 0, 0], [10, 3, 0]),
        wall("back", [10, 0, 8], [0, 3, 8]),
        wall("left", [0, 0, 8], [0, 3, 0]),
        wall("right", [10, 0, 0], [10, 3, 8]),
        roof("roof_main", None, 10, 8),
    ]

    assert_covered(elements)


# ── 曲线墙：天坛式的整圈圆墙 ──────────────────────────────────────────
# from/to 的 XZ 同为 [5.8, 0]，走直线采样会退化成一点。
CIRCULAR_WALL = [
    wall(
        "main_wall", [5.8, 1.2, 0], [5.8, 7.7, 0], thickness=0.25,
        curve={"type": "arc", "center": [0, 0, 0], "sweep": 360, "segments": 48},
    ),
]


def test_curved_wall_is_sampled_along_its_curve() -> None:
    """屋顶只盖住圆墙东侧一小块时，另外 ~34m 必须被报出来。

    如果退回 from→to 直线采样，采样点只有 (5.8, 0) 这一个，而它恰好在这块小屋顶
    里 —— 输出会变成 ✅，整圈墙的裸露被完全吞掉。
    """
    elements = deepcopy(CIRCULAR_WALL)
    elements.append(roof("patch", [5.8, 7.7, 0], 2, 2, roof_type="flat"))

    message = run_validator(blueprint(elements))

    assert message.startswith(WARNING)
    assert "main_wall" in message


def test_pagoda_eave_outset_extends_coverage() -> None:
    """重檐屋顶底层檐口 = span/2 + eaveOutset = 5.5 + 1 = 6.5 > 圆墙半径 5.8。

    忽略 eaveOutset 会把已经盖住的天坛圆墙误报成裸露。
    """
    elements = deepcopy(CIRCULAR_WALL)
    elements.append(roof(
        "main_roof", [0, 9.2, 0], 11, 11,
        roof_type="chinese_pagoda", eaveOutset=1, tiers=3, tierHeight=2,
        shrinkFactor=0.65,
    ))

    assert_covered(elements)


# ── 竖向判据 ────────────────────────────────────────────────────────────
def test_wall_top_above_lower_eave_but_under_upper_eave_is_covered() -> None:
    """重檐：墙与柱穿过下层檐口（7.5）继续上到上层檐（10.5），墙顶 8.0 不算裸露。"""
    elements = [
        wall("hall_front", [0, 2.4, 0], [10, 8.0, 0], thickness=0.5),
        roof("roof_lower_eave", [5, 7.5, 0], 14, 14, roof_type="hip"),
        roof("roof_upper_eave", [5, 10.5, 0], 14, 14, roof_type="hip"),
    ]

    assert_covered(elements)


def test_lower_wall_kept_by_slab_above_is_covered() -> None:
    """退台：下层墙顶被上层楼板压住，即使上层屋顶缩进不覆盖它，也不算裸露。"""
    elements = [
        # 下层满铺轮廓
        wall("base_front", [0, 0, 0], [10, 3, 0]),
        wall("base_back", [10, 0, 8], [0, 3, 8]),
        wall("base_left", [0, 0, 8], [0, 3, 0]),
        wall("base_right", [10, 0, 0], [10, 3, 8]),
        # 上层楼板：满铺，正是"被压住"的那一块
        floor("floor_2", [0, 3, 0], end=[10, 3, 8]),
        # 上层缩进体量 + 缩进的屋顶
        wall("upper_front", [3, 3, 2], [7, 6, 2]),
        wall("upper_back", [7, 3, 6], [3, 6, 6]),
        wall("upper_left", [3, 3, 6], [3, 6, 2]),
        wall("upper_right", [7, 3, 2], [7, 6, 6]),
        roof("roof_upper", [5, 6, 4], 5, 5),
    ]

    assert_covered(elements)


def test_endpoint_sliver_below_threshold_is_not_reported() -> None:
    """真实蓝图 session_1786700051751：墙端点只落在屋顶外 4cm，不该报 0.5m 裸露。"""
    elements = [
        floor("floor_1_base", [0.0, 0.0, 0.0], end=[12.0, 0.0, 9.0]),
        wall("wall_front_1_base", [0.0, 0.0, 0.0], [12.0, 3.2, 0.0]),
        wall("wall_right_1_base", [12.0, 0.0, 0.0], [12.0, 3.2, 9.0]),
        wall("wall_back_1_base", [12.0, 0.0, 9.0], [0.0, 3.2, 9.0]),
        wall("wall_left_1_base", [0.0, 0.0, 9.0], [0.0, 3.2, 0.0]),
        floor("floor_2_base", [0.0, 3.2, 0.0], end=[12.0, 3.2, 9.0]),
        wall("wall_front_2_upper_setback", [0.96, 3.2, 0.54], [10.8, 6.4, 0.54]),
        wall("wall_right_2_upper_setback", [10.8, 3.2, 0.54], [10.8, 6.4, 7.56]),
        wall("wall_back_2_upper_setback", [10.8, 3.2, 7.56], [0.96, 6.4, 7.56]),
        wall("wall_left_2_upper_setback", [0.96, 3.2, 7.56], [0.96, 6.4, 0.54]),
        roof("roof_01", [5.88, 6.4, 4.05], 9.84, 7.02, roof_type="flat"),
    ]

    assert_covered(elements)


def test_no_wall_means_skip() -> None:
    """没有墙的场景（纯场地 / 构件）不打扰。"""
    assert "跳过" in run_validator(blueprint([]))
