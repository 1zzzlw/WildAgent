"""拆分楼板的连通性与真实缺口必须分开判断。"""
from copy import deepcopy

import pytest

from app.tools.spatial_tools import collect_stair_placement_issues


def test_landing_rectangles_must_share_an_edge_not_only_a_corner():
    from app.tools.spatial_tools import _connected_landing
    assert not _connected_landing([[0, 0, 1, 1], [1, 1, 2, 2]], (0.5, 0.5), (1.5, 1.5))
    assert _connected_landing([[0, 0, 1, 1], [1, 0, 2, 1], [2, 0, 3, 1]], (0.5, 0.5), (2.5, 0.5))

@pytest.mark.parametrize("axis,shift", [(0, 0), (0, -13), (2, 25)])
@pytest.mark.parametrize("gap", [0, 0.2])
def test_flights_share_connected_floor_pieces_but_not_disconnected_islands(axis, shift, gap):
    def point(x, y, z):
        return [x+shift, y, z] if axis == 0 else [z, y, x+shift]
    elements = [
        {"type": "floor", "id": "bottom", "from": point(-1, -0.2, -1), "to": point(6, -0.2, 6), "thickness": 0.2},
        {"type": "floor", "id": "top", "from": point(-1, 5.8, -1), "to": point(6, 5.8, 6), "thickness": 0.2},
        {"type": "floor", "id": "landing_left", "from": point(-1, 2.8, 4), "to": point(2, 2.8, 6), "thickness": 0.2},
        {"type": "floor", "id": "landing_right", "from": point(2+gap, 2.8, 4), "to": point(6, 2.8, 6), "thickness": 0.2},
        {"type": "stair", "id": "lower", "from": point(0, 0, 0), "to": point(0, 3, 5), "width": 1},
        {"type": "stair", "id": "upper", "from": point(4, 3, 5), "to": point(4, 6, 0), "width": 1},
    ]
    bp = {"geometry": {"elements": elements}}
    before = deepcopy(bp)
    issues = collect_stair_placement_issues(bp)
    assert bool([i for i in issues if i["code"] == "disconnected_stair_flights"]) == bool(gap)
    assert bp == before
