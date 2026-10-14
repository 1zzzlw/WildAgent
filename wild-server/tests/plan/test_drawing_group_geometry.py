from copy import deepcopy

import pytest

from app.agent.plan import implementation as impl
from app.design.relations import component_geometry_review, stair_design_errors


def boxes(offset=0):
    return [{"id": f"part_{i}", "type": "primitive", "shape": "box",
             "position": [offset + i - 0.5, 1, 0], "dimensions": [1, 2, 1]} for i in (0, 1)]


def group_marker(offset=0):
    return {"id": "compound", "type": "new_shape",
            "design": {"size": {"width": 2, "height": 2, "depth": 1},
                       "placement": {"position": [offset, 1, 0]}}}


@pytest.mark.parametrize("offset", [-20, 0, 25])
def test_exact_box_group_dimensions_and_center_are_translation_invariant(offset):
    entities, marker = boxes(offset), group_marker(offset)
    review = component_geometry_review({}, entities, marker)
    assert review["status"] == "checked" and not review["errors"]
    entities[1]["position"][0] += 0.3
    assert component_geometry_review({}, entities, marker)["errors"]


def test_wrong_group_size_is_not_salvaged_as_individually_valid_boxes():
    base = {"meta": {"version": "1.1", "type": "building", "name": "group"},
            "materials": {}, "assets": {}, "geometry": {"elements": [], "components": []}}
    entities = boxes()
    entities[1]["position"][0] += 0.3
    _, accepted, rejected, record = impl._accept_fragment(
        base, {"geometry": {"elements": entities, "components": []}}, group_marker())
    assert accepted is None and record is None
    assert "组合设计尺寸" in rejected["error"]


@pytest.mark.parametrize("transform,value", [("rotation", [0, 0.5, 0]), ("scale", [2, 1, 1])])
def test_transformed_group_is_reviewed_without_guessing_world_axis_sizes(transform, value):
    entities = boxes()
    entities[0][transform] = value
    review = component_geometry_review({}, entities, group_marker())
    assert review["status"] == "needs_review" and not review["errors"]


def test_explicit_floor_connections_require_the_middle_floor_and_reject_extra_roof_flight():
    marker = {"id": "stairs", "floor_connections": [
        {"from_floor": 1, "to_floor": 2, "from_y": 0.45, "to_y": 3.45},
        {"from_floor": 2, "to_floor": 3, "from_y": 3.45, "to_y": 6.45}]}
    flights = [{"id": "flight_a", "type": "stair", "from": [1, 0.45, 1], "to": [1, 3.45, 6]},
               {"id": "flight_b", "type": "stair", "from": [1, 3.45, 6], "to": [1, 6.45, 1]}]
    assert not stair_design_errors({}, flights, marker)
    missing = deepcopy(flights)
    missing[0]["to"][1] = 6.45
    assert stair_design_errors({}, missing, marker)
    flights.append({"id": "extra", "type": "stair", "from": [1, 6.45, 1], "to": [1, 9.45, 6]})
    assert "超出明确连接标高" in stair_design_errors({}, flights, marker)[0]


def test_declared_material_role_needs_actual_material_usage():
    marker = {"id": "detail", "type": "new_shape", "material_id": "timber", "design": {"material_role": "wood"}}
    bp = {"materials": {"timber": {"baseColor": [0.4, 0.2, 0.1]}, "stone": {"baseColor": [0.7, 0.7, 0.7]}}}
    assert component_geometry_review(bp, [{"material": "stone"}], marker)["errors"]
    assert not component_geometry_review(bp, [{"material": "timber"}], marker)["errors"]


def test_structured_geometry_issue_survives_serialization_and_attribution():
    from app.agent.validation.diagnostics import step_result_to_dict
    from app.agent.validation.issues import validation_issues_from_results
    from app.services.agent_service import PipelineStepResult

    result = PipelineStepResult("design", "design_component_geometry", "❌ 组合尺寸错误", True, False,
        issues=[{"code": "component_group_size", "marker_id": "compound", "entity_ids": ["a", "b"],
                 "design_path": "/decisions/components/0", "expected": 2, "actual": 3}])
    row = step_result_to_dict(result)
    issues = validation_issues_from_results([row], {"geometry": {}})
    assert issues[0]["marker_id"] == "compound" and issues[0]["entity_ids"] == ["a", "b"]
    assert issues[0]["expected"] == 2 and issues[0]["actual"] == 3
