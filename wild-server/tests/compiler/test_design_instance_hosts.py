"""设计期语义宿主按体量和楼层解析，不能猜未来的墙名。"""

from copy import deepcopy

import pytest

from app.agent.compiler.compile import _opening_expression


PLAN = {
    "massing": {"floor_height": 3},
    "volumes": [{"id": "wing", "x": 0, "z": 0, "width": 8, "depth": 12,
                 "start_floor": 1, "end_floor": 2}],
}
WALLS = {
    "wall_left_1_1": {"from": [0, 0, 12], "to": [0, 3, 0]},
    "wall_left_2_1": {"from": [0, 3, 12], "to": [0, 6, 0]},
    "wall_back_1_1": {"from": [8, 0, 12], "to": [0, 3, 12]},
}


@pytest.mark.parametrize(("host", "expected"), [
    ("wing_L1_left", ("wall_left_1_1", 1)),
    ("wing_L2_left:2", ("wall_left_2_1", 2)),
    ("wing_L1_back", ("wall_back_1_1", 1)),
    ("missing_L1_left", (None, 1)),
    ("wing_L3_left", (None, 1)),
    ("wing_L1_south", (None, 1)),
    ("wall_left_2_1:2", ("wall_left_2_1", 2)),
])
def test_semantic_host_selects_only_the_requested_volume_and_floor(host, expected):
    assert _opening_expression({"host": host}, WALLS, PLAN) == expected


def test_ambiguous_or_cross_volume_wall_is_not_guessed():
    walls = deepcopy(WALLS)
    walls["duplicate"] = deepcopy(walls["wall_left_1_1"])
    assert _opening_expression({"host": "wing_L1_left"}, walls, PLAN)[0] is None
    walls = {"merged": {"from": [0, 0, 15], "to": [0, 3, 0]}}
    assert _opening_expression({"host": "wing_L1_left"}, walls, PLAN)[0] is None
