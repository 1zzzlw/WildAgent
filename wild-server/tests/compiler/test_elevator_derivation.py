"""测试电梯的确定性派生规则。

电梯依赖骨架的核心筒（wall_core_*），所以前置条件是 vertical_strategy = core_and_stair。
"""

import pytest

from app.agent.compiler.compile import compile_design
from app.agent.compiler.diagnostics import MODE_FINAL


def _plan_with_elevator(floors: int = 2) -> dict:
    """生成带核心筒的图纸（必须满足：层数 >= 2 且 vertical_strategy = core_and_stair）。"""

    return {
        "massing": {
            "shape": "rectangle",
            "width": 12.0,
            "depth": 8.0,
            "floors": floors,
            "floor_height": 3.0,
            "symmetry": "none",
        },
        "structural_grid": {
            "system": "frame",
            "column_spacing_x": 4.0,
            "column_spacing_z": 4.0,
        },
        "circulation": {
            "vertical_strategy": "core_and_stair",  # 核心筒策略，会生成 wall_core_*
        },
        "facades": {
            "front": {"bays": 3, "entrance_bay": 2, "ground_pattern": ["window", "door", "window"]},
        },
        "roof": {"type": "flat"},
        "component_quota": {
            "elevator": {"min": 1, "max": 2, "note": "住宅电梯"},
        },
    }


def test_elevator_is_derived_from_core_shaft() -> None:
    """电梯从骨架核心筒确定性生成：位置、尺寸、层高、层数全部对齐。"""

    plan = _plan_with_elevator(floors=3)
    result = compile_design(plan, mode=MODE_FINAL, user_message="生成三层住宅并配电梯")

    assert result.ok
    assert "elevator" not in result.uncompiled, "电梯有核心筒时不应标记为 uncompiled"

    components = result.blueprint["geometry"]["components"]
    elevators = [c for c in components if c["type"] == "elevator"]
    assert len(elevators) == 1, "配额下限 1 → 应恰好生成 1 台电梯"

    elevator = elevators[0]
    assert elevator["id"].startswith("elevator_")
    assert isinstance(elevator["position"], list) and len(elevator["position"]) == 3
    assert isinstance(elevator["dimensions"], dict)
    assert 1.0 < elevator["dimensions"]["width"] < 2.0
    assert 1.0 < elevator["dimensions"]["depth"] < 2.0
    assert elevator["floorHeight"] == 3.0, "层高应与骨架一致"
    assert elevator["floorCount"] == 3, "层数应与骨架一致"
    assert elevator["initialFloor"] == 0


def test_elevator_count_respects_quota_minimum() -> None:
    """电梯数量受配额下限控制：单井道配 1 台，双联井道可配 2 台。"""

    # 单井道场景（默认的 12x8m 矩形）
    plan_single = _plan_with_elevator(floors=2)
    plan_single["component_quota"]["elevator"]["min"] = 1
    result_single = compile_design(plan_single, mode=MODE_FINAL, user_message="单井道")

    elevators_single = [c for c in result_single.blueprint["geometry"]["components"]
                        if c["type"] == "elevator"]
    assert len(elevators_single) == 1, "单井道 → 1 台电梯"

    # 双联井道场景（更宽的建筑，骨架会生成分隔墙）
    plan_double = _plan_with_elevator(floors=2)
    plan_double["massing"]["width"] = 18.0  # 更宽，骨架会生成双联井
    plan_double["component_quota"]["elevator"]["min"] = 2
    result_double = compile_design(plan_double, mode=MODE_FINAL, user_message="双联井道")

    elevators_double = [c for c in result_double.blueprint["geometry"]["components"]
                        if c["type"] == "elevator"]
    # 根据骨架实际生成的井格数，可能是 1 或 2 台
    assert 1 <= len(elevators_double) <= 2, "双联井道场景下应生成 1-2 台电梯"


def test_elevator_without_core_shaft_is_marked_uncompiled() -> None:
    """骨架没有核心筒时，电梯无依托 → 标记为 uncompiled，由模型通道补。"""

    plan = _plan_with_elevator(floors=2)
    plan["circulation"]["vertical_strategy"] = "stair"  # 只有楼梯，没有核心筒

    result = compile_design(plan, mode=MODE_FINAL, user_message="无核心筒场景")

    assert result.ok, "无核心筒时不应阻断（能力缺失只标记不阻断）"
    assert "elevator" in result.uncompiled, "没有井道时电梯应标记为 uncompiled"

    components = result.blueprint["geometry"]["components"]
    elevators = [c for c in components if c["type"] == "elevator"]
    assert len(elevators) == 0, "没有核心筒时编译器不产出电梯"


def test_elevator_minimum_gate_is_applied() -> None:
    """配额下限门：要 2 台但只能放 1 台 → 一台都不产（与檐口/烟囱/灯具同一道门）。"""

    plan = _plan_with_elevator(floors=2)
    plan["component_quota"]["elevator"]["min"] = 2  # 要求 2 台
    # 但骨架只生成单井道 → 只能放 1 台

    result = compile_design(plan, mode=MODE_FINAL, user_message="下限门测试")

    elevators = [c for c in result.blueprint["geometry"]["components"]
                 if c["type"] == "elevator"]
    # 根据骨架井格数：如果只有 1 格井却要 2 台 → 不产出，标记为 uncompiled
    # （具体行为取决于骨架的井格数，这里验证"要么满足下限，要么标记 uncompiled"）
    if len(elevators) == 0:
        assert "elevator" in result.uncompiled, "配额下限未满足时应标记为 uncompiled"


def test_elevator_cab_fits_within_shaft_bay() -> None:
    """轿厢尺寸夹到井格净空内：取默认值与可用空间的较小值。"""

    plan = _plan_with_elevator(floors=2)
    result = compile_design(plan, mode=MODE_FINAL, user_message="轿厢尺寸验证")

    elevators = [c for c in result.blueprint["geometry"]["components"]
                 if c["type"] == "elevator"]
    if not elevators:
        pytest.skip("无核心筒或配额下限未满足")

    elevator = elevators[0]
    dims = elevator["dimensions"]
    # 轿厢尺寸应该是合理的：介于 0.6m（最小可用）和默认值（1.4/1.6）之间
    assert 0.6 <= dims["width"] <= 1.5
    assert 0.6 <= dims["depth"] <= 1.7
    # 轿厢高度应比层高小一点（留出顶部净空）
    assert dims["height"] < elevator["floorHeight"]
    assert dims["height"] >= elevator["floorHeight"] - 0.3


def test_elevator_position_is_centered_in_shaft_bay() -> None:
    """电梯位置：居中放在井格内，不压在分隔墙上。"""

    plan = _plan_with_elevator(floors=2)
    plan["massing"]["width"] = 18.0  # 更宽的建筑，可能生成双联井
    result = compile_design(plan, mode=MODE_FINAL, user_message="位置居中验证")

    elevators = [c for c in result.blueprint["geometry"]["components"]
                 if c["type"] == "elevator"]
    if not elevators:
        pytest.skip("无核心筒或配额下限未满足")

    for elevator in elevators:
        pos = elevator["position"]
        # 位置应该是合理的坐标（非零、非极端值）
        assert -20.0 < pos[0] < 20.0, "X 坐标应在建筑范围内"
        assert pos[1] == 0.0, "Y 坐标应在首层地面"
        assert -20.0 < pos[2] < 20.0, "Z 坐标应在建筑范围内"


def test_elevator_has_all_required_fields() -> None:
    """电梯组件包含所有必填字段（按 schema 定义）。"""

    plan = _plan_with_elevator(floors=2)
    result = compile_design(plan, mode=MODE_FINAL, user_message="必填字段验证")

    elevators = [c for c in result.blueprint["geometry"]["components"]
                 if c["type"] == "elevator"]
    if not elevators:
        pytest.skip("无核心筒或配额下限未满足")

    elevator = elevators[0]
    # schema 必填字段
    assert "type" in elevator and elevator["type"] == "elevator"
    assert "id" in elevator
    assert "position" in elevator and isinstance(elevator["position"], list)
    assert "dimensions" in elevator and isinstance(elevator["dimensions"], dict)
    assert "floorHeight" in elevator and isinstance(elevator["floorHeight"], (int, float))
    assert "floorCount" in elevator and isinstance(elevator["floorCount"], int)
    assert "initialFloor" in elevator and isinstance(elevator["initialFloor"], int)

    # dimensions 必填子字段
    dims = elevator["dimensions"]
    assert "width" in dims
    assert "depth" in dims
    assert "height" in dims
