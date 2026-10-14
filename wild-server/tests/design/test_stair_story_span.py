"""显式楼梯尺度必须与图纸楼面标高相容。"""

from copy import deepcopy

from app.design.coordinates import stair_span_conflicts


def drawing(floors=3):
    return {
        "massing": {"floors": floors, "floor_height": 3.0},
        "floor_layouts": [{"floor": index, "level": 0.45 + (index - 1) * 3.0}
                          for index in range(1, floors + 1)],
        "components": [{"id": "main_stair", "type": "stair", "size": {"height": 6.0},
                        "form": {"flights": 2, "rises": 20, "riser_height": 0.15}}],
    }


def test_three_storey_stair_rejects_roof_level_and_excess_rises():
    plan = drawing()
    plan["components"][0]["size"]["height"] = 8.85
    plan["components"][0]["form"].update(flights=3, rises=18)
    errors = stair_span_conflicts(plan)
    assert len(errors) == 2
    assert "8.85m" in errors[0] and "6m" in errors[0]
    assert "8.1m" in errors[1] and "6m" in errors[1]


def test_stair_span_uses_actual_floor_levels_and_allows_explicit_roof_access():
    plan = drawing()
    assert stair_span_conflicts(plan) == []
    plan["components"][0]["form"]["rises"] = 18
    assert "踏步总高差 5.4m" in stair_span_conflicts(plan)[0]
    plan["components"][0]["form"]["rises"] = 20
    plan["floor_layouts"][2]["level"] = 6.1
    assert stair_span_conflicts(plan)
    roof_stair = deepcopy(plan)
    roof_stair["components"][0]["form"]["roof_access"] = True
    assert stair_span_conflicts(roof_stair) == []


def test_stair_span_does_not_restrict_other_components():
    plan = drawing()
    plan["components"][0]["type"] = "column"
    plan["components"][0]["size"]["height"] = 20
    assert stair_span_conflicts(plan) == []


def test_raised_single_storey_entrance_steps_are_not_floor_connections():
    plan = drawing(floors=1)
    plan["components"][0]["size"]["height"] = 0.45
    assert stair_span_conflicts(plan) == []
