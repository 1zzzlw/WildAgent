"""validate_stacked_member_containment 的回归用例。

覆盖三种情形：
  1. 退台建筑中贯通核心筒伸进只存在于低层的翼体量 → 必须检出（真实缺陷的最小复现）。
  2. 核心筒收进顶层外墙轮廓 → 必须通过（不误报）。
  3. 裙房通高外壳（本身即底层外轮廓）→ 必须跳过（不误报）。
"""

from app.tools.spatial_tools import validate_stacked_member_containment


def _run(blueprint: dict) -> str:
    tool = validate_stacked_member_containment
    return getattr(tool, "func", tool)(blueprint)


def _wall(id_: str, from_, to_, thickness: float = 0.24) -> dict:
    return {"id": id_, "type": "wall", "from": from_, "to": to_, "thickness": thickness}


def _rectangle_walls(prefix: str, bottom: float, top: float, x0, z0, x1, z1) -> list[dict]:
    """按四个角生成一面矩形外墙（顺序不影响结果）。"""
    return [
        _wall(f"{prefix}_front", [x0, bottom, z0], [x1, top, z0]),
        _wall(f"{prefix}_right", [x1, bottom, z0], [x1, top, z1]),
        _wall(f"{prefix}_back", [x1, bottom, z1], [x0, top, z1]),
        _wall(f"{prefix}_left", [x0, bottom, z1], [x0, top, z0]),
    ]


def _core_walls(z_max: float) -> list[dict]:
    """贯通三层（0→9.6）的核心筒，其 Z 方向延伸到 z_max。"""
    return [
        _wall("wall_core_front", [4.0, 0.0, 4.5], [8.0, 9.6, 4.5]),
        _wall("wall_core_right", [8.0, 0.0, 4.5], [8.0, 9.6, z_max]),
        _wall("wall_core_back", [8.0, 0.0, z_max], [4.0, 9.6, z_max]),
        _wall("wall_core_left", [4.0, 0.0, z_max], [4.0, 9.6, 4.5]),
        _wall("wall_core_partition", [6.0, 0.0, 4.5], [6.0, 9.6, z_max]),
    ]


def _stacked_house(core_z_max: float) -> dict:
    """三层退台住宅：底层两层为 12×13（含翼），顶层收进为 12×8。"""
    elements = []
    # 底层两层（0→6.4）整块 12×13 外壳
    elements += _rectangle_walls("wall_1", 0.0, 3.2, 0.0, 0.0, 12.0, 13.0)
    elements += _rectangle_walls("wall_2", 3.2, 6.4, 0.0, 0.0, 12.0, 13.0)
    # 顶层（6.4→9.6）退台，只保留 12×8
    elements += _rectangle_walls("wall_3", 6.4, 9.6, 0.0, 0.0, 12.0, 8.0)
    elements += _core_walls(core_z_max)
    return {"geometry": {"elements": elements}}


def test_through_core_protruding_into_setback_wing_is_flagged() -> None:
    """核心筒按底层轮廓通高到底、伸进顶层已退掉的翼体量 → 检出。"""
    output = _run(_stacked_house(core_z_max=8.5))

    assert "❌ [wall_core_back]" in output
    assert "第 6.40m 层" in output
    assert "Z 0.50m" in output
    # 内圈（z=4.5）不越界，不应被误报
    assert "❌ [wall_core_front]" not in output


def test_through_core_contained_in_every_floor_passes() -> None:
    """核心筒收进顶层 12×8 轮廓内 → 不误报。"""
    output = _run(_stacked_house(core_z_max=8.0))

    assert "❌" not in output


def test_podium_shell_is_not_flagged() -> None:
    """裙房通高外壳本身就是底层外轮廓，不应被当作外凸的贯通墙。"""
    elements = []
    # 裙房外壳 0→28，占 X[0,42] Z[0,36]
    elements += _rectangle_walls("shell", 0.0, 28.0, 0.0, 0.0, 42.0, 36.0)
    # 内部逐层空间（4/8/12/16），占 X[12,30] Z[5.04,30.96]
    for index, bottom in enumerate((4.0, 8.0, 12.0, 16.0)):
        elements += _rectangle_walls(
            f"zone_{index}", bottom, bottom + 4.0, 12.0, 5.04, 30.0, 30.96
        )
    # 贯通核心（0→40）位于内部空间之内
    elements += [
        _wall("core_front", [18.0, 0.0, 12.96], [24.0, 40.0, 12.96]),
        _wall("core_right", [24.0, 0.0, 12.96], [24.0, 40.0, 23.04]),
        _wall("core_back", [24.0, 0.0, 23.04], [18.0, 40.0, 23.04]),
        _wall("core_left", [18.0, 0.0, 23.04], [18.0, 40.0, 12.96]),
    ]

    output = _run({"geometry": {"elements": elements}})

    assert "❌" not in output


def test_single_story_building_skips() -> None:
    """只有一层（无贯通墙）→ 明确跳过且不报错。"""
    elements = _rectangle_walls("wall", 0.0, 3.0, 0.0, 0.0, 10.0, 8.0)
    output = _run({"geometry": {"elements": elements}})

    assert "❌" not in output
