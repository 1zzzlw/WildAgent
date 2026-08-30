"""确定性成墙回归测试：空间公共边界推导 + 错位墙吸附。"""

import pytest

from app.agent.spatial_plan import normalize_spatial_plan
from app.agent.wall_derivation import (
    derive_interior_walls,
    shared_boundary_segments,
    snap_wall_to_boundary,
    space_polygons,
)


def _massing(width=10, depth=8, floors=1):
    return {"width": width, "depth": depth, "floors": floors,
            "modeled_floors": floors, "floor_height": 3.2}


def _raw_level(spaces, walls=None, openings=None):
    return {
        "level": 1,
        "spaces": spaces,
        "walls": walls or [],
        "openings": openings or [],
        "entrance_space_id": spaces[0]["id"],
        "voids": [],
    }


# ── 公共边界推导 ──

def test_adjacent_rectangles_derive_shared_wall():
    spaces = [
        {"id": "s1", "bounds": [0, 0, 3, 3]},
        {"id": "s2", "bounds": [3, 0, 6, 3]},
    ]
    walls = derive_interior_walls(spaces)
    assert len(walls) == 1
    # 分隔墙应在 x=3 的公共边界。
    assert abs(walls[0]["from"][0] - 3.0) < 1e-6
    assert abs(walls[0]["to"][0] - 3.0) < 1e-6


def test_l_shaped_layout_derives_all_partitions():
    spaces = [
        {"id": "a", "bounds": [0, 0, 6, 4]},
        {"id": "b", "bounds": [0, 4, 4, 6]},
        {"id": "c", "bounds": [4, 4, 6, 6]},
    ]
    walls = derive_interior_walls(spaces)
    # a-b, a-c, b-c 三条公共边。
    assert len(walls) == 3


def test_deduplicates_same_partition():
    spaces = [
        {"id": "a", "bounds": [0, 0, 4, 4]},
        {"id": "b", "bounds": [4, 0, 8, 4]},
    ]
    walls = derive_interior_walls(spaces)
    assert len(walls) == 1  # 同一条边不重复生成


# ── 错位墙吸附 ──

def test_misaligned_wall_snaps_to_boundary():
    spaces = [
        {"id": "a", "bounds": [0, 0, 4, 4]},
        {"id": "b", "bounds": [4, 0, 8, 4]},
    ]
    misaligned = {"id": "w", "kind": "interior", "from": [4.15, 0], "to": [4.15, 4]}
    snapped = snap_wall_to_boundary(misaligned, spaces)
    assert abs(snapped["from"][0] - 4.0) < 1e-6
    assert abs(snapped["to"][0] - 4.0) < 1e-6


def test_wall_far_from_boundary_kept():
    spaces = [
        {"id": "a", "bounds": [0, 0, 4, 4]},
        {"id": "b", "bounds": [4, 0, 8, 4]},
    ]
    # 距离公共边超过容差（0.25），不应被吸附。
    far = {"id": "w", "kind": "interior", "from": [4.8, 0], "to": [4.8, 4]}
    kept = snap_wall_to_boundary(far, spaces)
    assert abs(kept["from"][0] - 4.8) < 1e-6


# ── 端到端：normalize 吸附生效 ──

@pytest.mark.parametrize("misalign", [0.05, 0.1, 0.2])
def test_normalize_snaps_misaligned_walls(misalign):
    spaces = [
        {"id": "s1", "space_type": "living", "bounds": [0, 0, 5, 8]},
        {"id": "s2", "space_type": "bedroom", "bounds": [5, 0, 10, 8]},
    ]
    openings = [{
        "id": "d1", "type": "door", "host_wall_id": "w1",
        "offset": 3, "width": 0.9, "connects": ["s1", "s2"],
    }]
    raw = {"levels": [_raw_level(
        spaces,
        walls=[{"id": "w1", "kind": "interior", "from": [5 + misalign, 0], "to": [5 + misalign, 8]}],
        openings=openings,
    )]}
    plan = normalize_spatial_plan(raw, _massing())
    assert plan.get("source") == "model", f"plan should stay model, got {plan.get('source')}"
    level = plan["levels"][0]
    wall = next(w for w in level["walls"] if w["id"].endswith("w1"))
    # 吸附到公共边界 x=5。
    assert abs(float(wall["from"][0]) - 5.0) < 1e-6
    assert abs(float(wall["to"][0]) - 5.0) < 1e-6
