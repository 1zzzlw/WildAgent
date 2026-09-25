"""垂直交通（电梯井 + 楼梯）与"用户点名细部包"的回归。

三条实测缺陷：

① "生成一个别墅，里面要有家具" —— 规划模型以「家具属于室内设计、不在建筑方案
   职责内」为由把 `detail_packages` 写成 `[]`；归一化照单全收后，用户点名的细部
   连同配额与 `required_components` 一起被静默清空，最终一件家具都没有。
② 核心筒按建筑**包围盒**居中 ⇒ L/U 形平面下井壁伸到建筑轮廓之外（"超模"），
   而且与楼梯重叠 —— 两者都往公共区中心挤。
③ 电梯组件的坐标由模型自由填 ⇒ 轿厢不在井道里、`floorCount` 与井道层数不一致。
"""

from __future__ import annotations

import pytest

from app.agent.generation.architecture import (
    build_deterministic_skeleton,
    normalize_architecture_plan,
)
from app.tools.component_tools import (
    _resolve_core_shaft,
    fix_component,
    validate_component,
)

TOLERANCE = 0.05


def _xz_box(element: dict) -> tuple[float, float, float, float] | None:
    frm, to = element.get("from"), element.get("to")
    if not isinstance(frm, list) or not isinstance(to, list):
        return None
    return (
        min(float(frm[0]), float(to[0])), min(float(frm[2]), float(to[2])),
        max(float(frm[0]), float(to[0])), max(float(frm[2]), float(to[2])),
    )


def _ground_regions(elements: list[dict]) -> list[tuple[float, float, float, float]]:
    """首层楼板投影（标高最小的那批）。"""

    floors = [
        (_xz_box(element), float(element["from"][1]))
        for element in elements
        if element.get("type") == "floor" and _xz_box(element)
    ]
    if not floors:
        return []
    lowest = min(elevation for _, elevation in floors)
    return [box for box, elevation in floors if abs(elevation - lowest) < 1e-6]


def _core_and_stair_plan(shape: str, width: float, depth: float, message: str) -> dict:
    return normalize_architecture_plan(
        {
            "massing": {
                "shape": shape, "width": width, "depth": depth,
                "floors": 2, "modeled_floors": 2, "floor_height": 3.0,
                "representation_mode": "full",
            },
            "circulation": {"vertical_strategy": "core_and_stair"},
        },
        message,
    )


# ── ① 用户点名的细部包不可被模型清空 ──────────────────────────────

def test_requested_detail_packages_survive_empty_model_output() -> None:
    """模型写 `detail_packages: []` 时，用户点名的"家具"必须仍然进入配额。"""

    message = "生成一个别墅，里面要有家具"
    plan = normalize_architecture_plan({"detail_packages": []}, message)

    assert "furniture" in plan["detail_packages"]
    assert plan["component_quota"]["furniture"]["min"] > 0
    assert "furniture" in plan["required_components"]


def test_requested_detail_packages_lead_the_truncated_list() -> None:
    """点名项排在列表最前：末尾有 `[:6]` 截断，排后面会被整段切掉。"""

    message = "生成一个别墅，里面要有家具"
    plan = normalize_architecture_plan(
        {"detail_packages": [
            "canopy", "balcony", "bay_window", "cornice", "railing", "ramp",
        ]},
        message,
    )

    assert len(plan["detail_packages"]) <= 6
    assert plan["detail_packages"][0] == "furniture"


# ── ② 电梯的派发通道 ──────────────────────────────────────────────

def test_elevator_requested_only_for_multi_storey() -> None:
    multi = normalize_architecture_plan({}, "生成一个三层住宅，要装电梯")
    assert "elevator" in multi["detail_packages"]
    assert multi["component_quota"]["elevator"]["min"] > 0
    assert "elevator" in multi["required_components"]
    # 电梯必须有井道：骨架的唯一井道策略是 core_and_stair。
    assert multi["circulation"]["vertical_strategy"] == "core_and_stair"

    single = normalize_architecture_plan(
        {"massing": {"floors": 1, "modeled_floors": 1}},
        "生成一个单层住宅，要装电梯",
    )
    assert "elevator" not in single["detail_packages"]
    assert "elevator" not in single["component_quota"]


def test_elevator_upgrades_model_baseline_strategy() -> None:
    """模型把垂直交通定为 stair 时，用户点名的电梯仍要把策略升到核心筒。"""

    plan = normalize_architecture_plan(
        {"circulation": {"vertical_strategy": "stair"}},
        "生成一个两层别墅，配一部电梯",
    )

    assert plan["detail_packages"][0] == "elevator"
    assert plan["circulation"]["vertical_strategy"] == "core_and_stair"


def test_no_elevator_keeps_plain_stair_single_volume() -> None:
    """反向：没有点名电梯时不该被"升级"污染 —— 单层/两层普通住宅仍走 stair。"""

    plan = normalize_architecture_plan(
        {"massing": {"floors": 2, "modeled_floors": 2}},
        "生成一个两层住宅",
    )

    assert "elevator" not in plan["detail_packages"]
    assert plan["circulation"]["vertical_strategy"] == "stair"


# ── ③ 核心筒与楼梯的几何 ──────────────────────────────────────────

@pytest.mark.parametrize(
    ("label", "shape", "width", "depth"),
    [
        ("L 形", "l_shape", 16.0, 12.0),
        ("矩形", "rectangle", 14.0, 10.0),
        ("U 形", "u_shape", 20.0, 14.0),
    ],
)
def test_core_and_stairs_stay_inside_footprint(label, shape, width, depth) -> None:
    message = f"生成一个两层{label}别墅"
    plan = _core_and_stair_plan(shape, width, depth, message)
    elements = build_deterministic_skeleton(plan, message)["geometry"]["elements"]

    regions = _ground_regions(elements)
    assert regions, "没有首层楼板，无法判定轮廓"

    core_walls = [
        element for element in elements
        if str(element.get("id") or "").startswith("wall_core_")
    ]
    assert len(core_walls) >= 4
    for wall in core_walls:
        box = _xz_box(wall)
        assert box is not None
        assert any(
            x0 - TOLERANCE <= box[0] and box[1] >= z0 - TOLERANCE
            and box[2] <= x1 + TOLERANCE and box[3] <= z1 + TOLERANCE
            for x0, z0, x1, z1 in regions
        ), f"[{wall['id']}] 核心筒超出楼板投影 {box}，可用区域 {regions}"

    core_boxes = [box for box in (_xz_box(wall) for wall in core_walls) if box]
    core_box = (
        min(box[0] for box in core_boxes), min(box[1] for box in core_boxes),
        max(box[2] for box in core_boxes), max(box[3] for box in core_boxes),
    )
    stairs = [element for element in elements if element.get("type") == "stair"]
    assert stairs, "core_and_stair 策略没有生成楼梯"
    for stair in stairs:
        frm, to = stair["from"], stair["to"]
        half = float(stair["width"]) / 2
        sx0, sx1 = min(frm[0], to[0]), max(frm[0], to[0])
        sz0, sz1 = min(frm[2], to[2]), max(frm[2], to[2])
        # 楼梯宽度垂直于跑向：只往跑向的垂直方向膨胀。
        box = (
            (sx0 - half, sz0, sx1 + half, sz1) if (sz1 - sz0) >= (sx1 - sx0)
            else (sx0, sz0 - half, sx1, sz1 + half)
        )
        assert (
            box[2] <= core_box[0] + TOLERANCE or box[0] >= core_box[2] - TOLERANCE
            or box[3] <= core_box[1] + TOLERANCE or box[1] >= core_box[3] - TOLERANCE
        ), f"[{stair['id']}] 与核心筒重叠（楼梯 {box} / 核心筒 {core_box}）"


# ── ④ 轿厢与井道的确定性对齐 ──────────────────────────────────────

def test_elevator_fixer_aligns_cab_into_shaft_bay() -> None:
    message = "生成一个两层 L 形别墅"
    plan = _core_and_stair_plan("l_shape", 16.0, 12.0, message)
    blueprint = build_deterministic_skeleton(plan, message)
    blueprint["geometry"].setdefault("components", []).append({
        "type": "elevator", "id": "elevator_main",
        # 模型给的坐标与井道毫无关系：修复器必须把它拉回井格里。
        "position": [50.0, 0.0, 50.0],
        "dimensions": {"width": 1.4, "depth": 1.6, "height": 2.2},
        "floorHeight": 3.3, "floorCount": 5, "initialFloor": 4,
    })

    assert "❌" in validate_component("elevator", blueprint)

    fix_component("elevator", blueprint)
    assert "❌" not in validate_component("elevator", blueprint)

    elevator = blueprint["geometry"]["components"][-1]
    assert elevator["floorHeight"] == 3.0, "floorHeight 未对齐骨架层高"
    assert elevator["floorCount"] == 2, "floorCount 未对齐井道层数"
    assert elevator["initialFloor"] == 0, "层数收敛后 initialFloor 越界未复检"

    shaft = _resolve_core_shaft(blueprint)
    assert shaft is not None
    cx, cz = elevator["position"][0], elevator["position"][2]
    half_w = elevator["dimensions"]["width"] / 2
    half_d = elevator["dimensions"]["depth"] / 2
    assert any(
        cx - half_w >= x0 - TOLERANCE and cx + half_w <= x1 + TOLERANCE
        and cz - half_d >= z0 - TOLERANCE and cz + half_d <= z1 + TOLERANCE
        for x0, x1, z0, z1 in shaft["bays"]
    ), "轿厢没有被放进任何一格井道净空内"


def test_elevator_without_shaft_is_only_warned() -> None:
    """骨架没有井道时只标记（能力缺失不阻断），不制造 ❌ 把条目判死。"""

    blueprint = {
        "meta": {"version": "1.1", "type": "building"},
        "geometry": {
            "elements": [],
            "components": [{
                "type": "elevator", "id": "elevator_main",
                "position": [0.0, 0.0, 0.0],
                "dimensions": {"width": 1.4, "depth": 1.6, "height": 2.2},
                "floorHeight": 3.0, "floorCount": 2,
            }],
        },
        "materials": {},
    }

    result = validate_component("elevator", blueprint)
    assert "⚠️" in result
    assert "❌" not in result


# ── ⑤ 井道朝向与井格尺寸 ──────────────────────────────────────────
# 布局函数允许核心筒沿公共区长轴的**任一轴**排布，而 `_append_vertical_core` 早期把
# 分隔墙与门洞都写死在 x 轴：长轴沿 x 时，井道的「进深」被当「面宽」对半切开，
# 双联井变成两格 1.0×4.2m 的长条，修复器只能把轿厢宽度夹到 0.9m（实测）。


def _span_axis(wall: dict) -> str:
    """墙的**跨越轴**：跨 x（常 z 的横墙）→ 'x'；跨 z（常 x 的竖墙）→ 'z'。"""

    frm, to = wall["from"], wall["to"]
    return "x" if abs(float(to[2]) - float(frm[2])) < 1e-6 else "z"


def _core_walls(elements: list[dict]) -> dict[str, dict]:
    return {
        str(element["id"]): element for element in elements
        if str(element.get("id") or "").startswith("wall_core_")
    }


@pytest.mark.parametrize(
    ("label", "shape", "width", "depth", "partition_axis"),
    [
        # 公共区长轴沿 z → 候梯面是 front（跨 x）、分隔墙跨 z。
        ("L 形", "l_shape", 16.0, 12.0, "z"),
        # 公共区长轴沿 x → 候梯面是 left（跨 z）、分隔墙跨 x。
        ("矩形", "rectangle", 14.0, 10.0, "x"),
        ("U 形", "u_shape", 20.0, 14.0, "z"),
    ],
)
def test_partition_is_perpendicular_to_door_wall(
    label, shape, width, depth, partition_axis,
) -> None:
    message = f"生成一个两层{label}别墅"
    plan = _core_and_stair_plan(shape, width, depth, message)
    elements = build_deterministic_skeleton(plan, message)["geometry"]["elements"]

    walls = _core_walls(elements)
    doors = [
        element for element in elements
        if str(element.get("id") or "").startswith("elevator_door_")
    ]
    assert doors, "没有电梯门洞，无法判定候梯面"

    door_wall = walls[str(doors[0]["parentWall"])]
    partitions = [wall for wid, wall in walls.items() if "partition" in wid]
    assert partitions, "双联井必须有分隔墙"

    assert _span_axis(partitions[0]) == partition_axis, (
        f"分隔墙跨越轴 {_span_axis(partitions[0])} ≠ 期望 {partition_axis}"
        f"（候梯墙跨越轴 {_span_axis(door_wall)}）"
    )
    assert _span_axis(door_wall) != partition_axis, "分隔墙与候梯墙同向 → 井道被沿进深切开"


@pytest.mark.parametrize(
    ("label", "shape", "width", "depth"),
    [
        ("L 形", "l_shape", 16.0, 12.0),
        ("矩形", "rectangle", 14.0, 10.0),
        ("长宽比大的矩形", "rectangle", 9.0, 20.0),
        ("窄矩形（单井）", "rectangle", 4.6, 16.0),
    ],
)
def test_shaft_bays_can_hold_a_real_cab(label, shape, width, depth) -> None:
    """每格井净空须装得进住宅轿厢；修复后的轿厢宽度必须像电梯。"""

    message = f"生成一个两层{label}住宅"
    plan = _core_and_stair_plan(shape, width, depth, message)
    blueprint = build_deterministic_skeleton(plan, message)

    shaft = _resolve_core_shaft(blueprint)
    assert shaft is not None, "骨架没有生成可识别的井道"
    for index, (x0, x1, z0, z1) in enumerate(shaft["bays"]):
        assert min(x1 - x0, z1 - z0) >= 1.8, (
            f"井格{index} 净空 {x1 - x0:.2f}×{z1 - z0:.2f} 装不进住宅轿厢"
        )

    blueprint["geometry"].setdefault("components", []).append({
        "type": "elevator", "id": "elevator_main",
        "position": [0.5, 0.0, 0.5],
        "dimensions": {"width": 3.6, "depth": 3.6, "height": 2.6},
        "floorHeight": 9.9, "floorCount": 7, "initialFloor": 6,
    })
    fix_component("elevator", blueprint)
    elevator = blueprint["geometry"]["components"][-1]
    assert elevator["dimensions"]["width"] >= 1.3, (
        f"修复后轿厢宽仅 {elevator['dimensions']['width']}m —— 井格被切错了"
    )
    assert "❌" not in validate_component("elevator", blueprint)


def test_single_shaft_has_no_partition() -> None:
    """单轿厢井不得有分隔墙：加了会把 2.4m 面宽切成两格 0.9m，居中那扇门正好压在墙上。"""

    message = "生成一个两层窄矩形住宅"
    plan = _core_and_stair_plan("rectangle", 4.6, 16.0, message)
    elements = build_deterministic_skeleton(plan, message)["geometry"]["elements"]

    walls = _core_walls(elements)
    partitions = [wall for wid, wall in walls.items() if "partition" in wid]
    assert not partitions, f"单井不该有分隔墙，却生成了 {[w['id'] for w in partitions]}"

    doors = [
        element for element in elements
        if str(element.get("id") or "").startswith("elevator_door_")
    ]
    assert len(doors) == 1, "单井每层只该有一扇居中电梯门"
    door_wall = walls[str(doors[0]["parentWall"])]
    wall_length = abs(
        (float(door_wall["to"][2]) - float(door_wall["from"][2]))
        or (float(door_wall["to"][0]) - float(door_wall["from"][0]))
    )
    door_width = float(doors[0]["width"])
    offset = float(doors[0]["from"][0])
    assert offset + door_width <= wall_length + TOLERANCE, "单井门洞越出候梯墙"
    # 居中：门洞中心应贴近墙中点
    assert abs((offset + door_width / 2) - wall_length / 2) <= TOLERANCE


def test_resolver_splits_on_horizontal_partition() -> None:
    """水平分隔墙（跨 x）也要能切出两格井 —— 旧实现只认竖直分隔墙，会当成一整格。"""

    def _wall(wall_id: str, x0: float, z0: float, x1: float, z1: float) -> dict:
        return {
            "type": "wall", "id": wall_id,
            "from": [x0, 0.0, z0], "to": [x1, 3.0, z1],
            "thickness": 0.2, "material": "concrete",
        }

    blueprint = {
        "meta": {"version": "1.1", "type": "building"},
        "geometry": {
            "elements": [
                _wall("wall_core_front_1", 0.0, 0.0, 4.6, 0.0),
                _wall("wall_core_right_1", 4.6, 0.0, 4.6, 2.6),
                _wall("wall_core_back_1", 4.6, 2.6, 0.0, 2.6),
                _wall("wall_core_left_1", 0.0, 2.6, 0.0, 0.0),
                _wall("wall_core_partition_1", 0.0, 1.3, 4.6, 1.3),
            ],
            "components": [],
        },
        "materials": {},
    }

    shaft = _resolve_core_shaft(blueprint)
    assert shaft is not None
    assert len(shaft["bays"]) == 2, "水平分隔墙没有被识别，井道被当成一整格"
    (x0, x1, z0, z1), (bx0, bx1, bz0, bz1) = shaft["bays"]
    assert x0 == bx0 and x1 == bx1
    assert z1 < bz0, "两格井沿 z 分列，中间应留分隔墙的缝"
    for bay_z0, bay_z1 in ((z0, z1), (bz0, bz1)):
        assert abs((bay_z1 - bay_z0) - 1.0) <= TOLERANCE
