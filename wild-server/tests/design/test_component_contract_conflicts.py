from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.design import coordinates
from app.design.relations import component_geometry_review, roof_design_errors


@pytest.mark.parametrize("axis", ["x", "z"])
def test_beam_direction_conflict_is_rejected_without_swapping_the_design(axis):
    size = {"width": 0.2 if axis == "x" else 8, "height": 0.3,
            "depth": 8 if axis == "x" else 0.2}
    design = {"components": [{"id": "member", "type": "beam", "size": size,
                              "form": {"span_direction": axis}}]}
    before = deepcopy(design)
    errors = coordinates.component_dimension_conflicts(design)
    assert len(errors) == 1
    assert "/components/0/size" in errors[0] and "世界 X/Y/Z" in errors[0]
    assert design == before
    size["width"], size["depth"] = size["depth"], size["width"]
    assert coordinates.component_dimension_conflicts(design) == []


@pytest.mark.parametrize("base,height,rise", [(0, 2.6, 2.6), (-4, 1.2, 1.8), (7, 3, 3)])
def test_explicit_roof_center_and_wall_relative_ridge_must_agree(base, height, rise):
    wall_top = base + 6.6
    component = {"id": "cover", "type": "gable_roof", "host": "main",
                 "size": {"width": 13.2, "height": height, "depth": 10.2},
                 "placement": {"position": [6, wall_top + rise, 4.5]},
                 "form": {"ridge_height_from_wall_top": rise}}
    design = {"massing": {"floor_height": 3.3, "floors": 2},
              "floor_layouts": [{"floor": 1, "level": base}],
              "volumes": [{"id": "main", "end_floor": 2}], "components": [component]}
    before = deepcopy(design)
    errors = coordinates.component_dimension_conflicts(design)
    assert len(errors) == 1 and "/components/0/placement/position" in errors[0]
    assert "中心Y" in errors[0] and "墙顶" in errors[0]
    assert design == before
    component["placement"]["position"][1] = wall_top + rise - height / 2
    assert coordinates.component_dimension_conflicts(design) == []
    component["form"].pop("ridge_height_from_wall_top")
    component["placement"]["position"][1] += 2
    assert coordinates.component_dimension_conflicts(design) == []  # 未声明相对标高时不猜测支承


@pytest.mark.parametrize("family,role,field", [
    ("door", "door", "leafMaterial"), ("door", "frame", "frameMaterial"),
    ("window", "frame", "frameMaterial"), ("window", "glass", "glassMaterial"),
    ("roof", "roof", "material"), ("primitive", "accent", "material"),
])
def test_material_roles_read_the_actual_surface_field(family, role, field):
    material = {"baseColor": [0.15, 0.15, 0.15], "metallic": 0.7}
    blueprint = {"materials": {"expected": material, "local": {**material, "opacity": 1},
                               "wrong": {"baseColor": [0.8, 0.5, 0.3]}}}
    marker = {"id": "part", "type": family, "material_id": "expected",
              "design": {"material_role": role}}
    entity = {"id": "part", "type": family, field: "local"}
    assert component_geometry_review(blueprint, [entity], marker)["errors"] == []
    entity[field] = "wrong"
    assert component_geometry_review(blueprint, [entity], marker)["errors"]


def test_door_frame_cannot_stand_in_for_leaf_material():
    blueprint = {"materials": {"metal": {"metallic": 0.8}, "wood": {"metallic": 0}}}
    marker = {"id": "entry", "type": "door", "material_id": "metal",
              "design": {"material_role": "door"}}
    door = {"id": "entry", "type": "door", "frameMaterial": "metal", "leafMaterial": "wood"}
    assert component_geometry_review(blueprint, [door], marker)["errors"]


def test_native_roof_below_design_reports_elevation_instead_of_missing_footprint():
    marker = {"id": "cover", "type": "gable_roof", "entity": {"position": [6, 9.5, 4.5]},
              "design": {"volume": {"x": 0, "z": 0, "width": 12, "depth": 9},
                         "overhang": 0.6, "placement": {"position": [6, 9.5, 4.5]},
                         "size": {"height": 2.6}}}
    roof = {"id": "cover", "type": "roof", "roofType": "gable", "position": [6, 6.6, 4.5],
            "span": 13.2, "depth": 10.2, "height": 2.6, "thickness": 0.15}
    errors = roof_design_errors({"geometry": {"elements": [roof]}}, [roof], marker)
    assert len(errors) == 1 and "平面投影已覆盖" in errors[0]
    assert "6.600" in errors[0] and "8.200" in errors[0]
    assert "中心" in errors[0]


@pytest.mark.asyncio
async def test_dimension_conflict_uses_existing_local_design_revision(monkeypatch):
    from app.agent.generation.architecture import design_workflow

    original = {"massing": {"floor_height": 3.3, "floors": 2},
                "volumes": [{"id": "main", "end_floor": 2}],
                "components": [{"id": "member", "type": "beam", "form": {"span_direction": "x"},
                                "size": {"width": 0.2, "height": 0.35, "depth": 12.5}}]}
    repaired = deepcopy(original["components"])
    repaired[0]["size"] = {"width": 12.5, "height": 0.35, "depth": 0.2}
    answers = [original, {"components": repaired}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(answers.pop(0)), token_usage=None, finish_reason="stop")

    def validate(plan):
        errors = coordinates.component_dimension_conflicts(plan)
        if errors:
            raise ValueError("；".join(errors))

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = await design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成别墅", validate=validate, max_attempts=2)

    assert diag["settled"] and diag["model_calls"] == 2
    assert result == {**original, "components": repaired}
    assert "仅包含待修顶层字段：components" in prompts[1]
