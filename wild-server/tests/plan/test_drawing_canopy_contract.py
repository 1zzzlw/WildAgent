"""雨棚的中心、沿墙起点与 Core 安装范围必须一致。"""
from copy import deepcopy

import pytest

from app.agent.plan import implementation as impl
from app.design.relations import canopy_design_errors, canopy_mount_target, wall_attached_point
from app.tools.component_tools import validate_canopy_placement
from tests.plan.test_drawing_implementation import empty_state


@pytest.mark.parametrize("axis,offset", [(0, 0), (0, -20), (2, 13)])
@pytest.mark.parametrize("reverse", [False, True])
def test_canopy_center_is_converted_without_changing_approved_size(axis, offset, reverse):
    def point(x, y, z):
        return [offset+x, y, offset+z] if axis == 0 else [offset+z, y, offset+x]
    base = empty_state()["skeleton_blueprint"]
    walls = [{"id": f"wall_{i}", "type": "wall", "from": point(*a), "to": point(*b), "thickness": 0.24}
             for i, (a, b) in enumerate([((0, 0, 0), (20, 4.5, 0)), ((0, 0, 8), (20, 4.5, 8)),
                                        ((0, 0, 0), (0, 4.5, 8)), ((20, 0, 0), (20, 4.5, 8))])]
    if reverse:
        walls[0]["from"], walls[0]["to"] = walls[0]["to"], walls[0]["from"]
    base["geometry"]["elements"] = walls
    marker = {"id": "canopy", "type": "canopy", "entity": {"parentWall": "wall_0", "position": point(10, 3.9, -1.25)},
              "design": {"size": {"width": 12, "depth": 2.5, "thickness": 0.18}}}
    before = deepcopy(marker)
    target = canopy_mount_target(base, marker)
    canopy = {"type": "canopy", "id": "canopy", **target, "width": 12, "depth": 2.5, "thickness": 0.18}
    assert target["from"][0] == pytest.approx(4)
    assert wall_attached_point(base, canopy, 10, 3.9, 1.25) == pytest.approx(marker["entity"]["position"])
    assert canopy_design_errors(base, [canopy], marker) == []
    assert impl._accept_fragment(base, {"geometry": {"components": [canopy]}}, marker)[2] is None
    canopy["from"][0] = 10
    invalid = deepcopy(base)
    invalid["geometry"]["components"] = [canopy]
    assert "超出父墙水平范围" in validate_canopy_placement(invalid)
    assert any("雨棚" in e for e in impl.implementation_errors(invalid))
    assert canopy_design_errors(base, [canopy], marker)
    support = {"id": "support", "type": "primitive", "shape": "box", "position": point(0, 2, 0), "dimensions": [0.1, 2, 0.1]}
    accepted = impl._accept_fragment(base, {"geometry": {"components": [canopy], "elements": [support]}}, marker)
    assert accepted[1] is None and accepted[2] is not None
    assert marker == before


def test_native_canopy_with_decorations_still_keeps_explicit_dimensions():
    base = empty_state()["skeleton_blueprint"]
    canopy = {"id": "canopy", "type": "canopy", "width": 2, "depth": 2, "thickness": 0.2}
    marker = {"id": "canopy", "type": "canopy", "entity": {}, "design": {"size": {"width": 3}}}
    decoration = {"id": "trim", "type": "primitive", "shape": "box", "dimensions": [0.1, 0.1, 0.1]}
    assert canopy_design_errors(base, [canopy, decoration], marker)
