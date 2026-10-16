from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import design_workflow, workflow
from app.design.coordinates import floor_layout_conflicts


@pytest.mark.parametrize("materials", [
    ("深棕色木质", "深棕色木梁"), ("深棕色木柱", "深棕色木材"),
    ("dark timber", "dark wood beam"), ("金属柱", "钢梁"),
])
def test_same_material_family_is_not_rejected_for_different_component_descriptions(materials):
    components = [{"id": str(i), "material_role": "structure", "form": {"material": material}}
                  for i, material in enumerate(materials)]
    before = deepcopy(components)
    assert workflow._material_role_conflicts(components) == []
    assert components == before


@pytest.mark.parametrize("materials", [("custom finish A", "custom finish B"), ("木纹金属", "木材")])
def test_unknown_or_composite_material_names_are_not_guessed_into_hard_conflicts(materials):
    components = [{"material_role": "accent", "form": {"material": m}} for m in materials]
    assert workflow._material_role_conflicts(components) == []


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("offset", [-17, 0, 20])
def test_partition_feedback_contains_room_and_wall_geometry_without_mutation(axis, offset):
    a, b = [offset, offset], [offset+8, offset+8]
    a[axis] = b[axis] = offset+4
    room = {"id": "corridor", "name": "走廊", "bounds": {"x": offset, "z": offset, "width": 8, "depth": 8}}
    design = {"floor_layouts": [{"floor": 2, "rooms": [room],
                                "walls": [{"id": "partition", "from": a, "to": b}]}]}
    before = deepcopy(design)
    errors = floor_layout_conflicts(design)
    assert len(errors) == 1
    assert all(word in errors[0] for word in ("走廊", "corridor", "partition", "世界 X", "Z", "一侧"))
    assert str(offset+4) in errors[0]
    origin, extent = ("x", "width") if axis == 0 else ("z", "depth")
    assert f"bounds.{origin}={offset+4}" in errors[0] and f"bounds.{extent}=4" in errors[0]
    assert design == before
    room["bounds"]["width" if axis == 0 else "depth"] = 4
    assert floor_layout_conflicts(design) == []


def conflicting_drawing():
    return {"concept": "别墅", "massing": {"shape": "rectangular", "width": 10, "depth": 8,
                "floors": 1, "modeled_floors": 1, "floor_height": 3},
            "volumes": [{"id": "main", "x": 0, "z": 0, "width": 10, "depth": 8, "start_floor": 1, "end_floor": 1}],
            "structural_grid": {"system": "frame", "x_bays": 1, "z_bays": 1},
            "facades": {face: {"bays": 1, "ground_pattern": ["empty"], "upper_pattern": []}
                        for face in ("front", "back", "left", "right")},
            "roof": {"type": "gable", "overhang": 0},
            "components": [
                {"id": "post", "type": "column", "material_role": "structure", "form": {"material": "timber"}},
                {"id": "member", "type": "beam", "material_role": "structure", "form": {"material": "stone"}},
                {"id": "cover", "type": "gable_roof", "host": "main", "size": {"width": 10, "depth": 8, "height": 2},
                 "placement": {"position": [5, 9, 4]}, "form": {"ridge_height_from_wall_top": 2}}],
            "floor_layouts": [{"floor": 1, "level": 0, "rooms": [
                {"id": "hall", "name": "门厅", "bounds": {"x": 0, "z": 0, "width": 10, "depth": 8}}],
                "walls": [{"id": "partition", "from": [4, 0], "to": [4, 8], "thickness": 0.15}]}]}


@pytest.mark.asyncio
async def test_real_architecture_entry_reports_independent_conflicts_in_the_same_attempt(monkeypatch):
    from app.services.agent_service import agent_service

    raw = conflicting_drawing()
    calls = []

    async def model(_llm, messages):
        calls.append(messages)
        return SimpleNamespace(content=json.dumps(raw), token_usage=None, finish_reason="stop")

    monkeypatch.setattr(agent_service.spec_loader, "load_many", lambda *args, **kwargs: "")
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result = await workflow.architecture_planner({"session_id": "aggregate", "user_message": "生成别墅", "thinking_mode": False})
    first = result["architecture_diag"]["rejected_attempts"][0]["issue"]
    assert "/components" in first and "材质" in first
    assert "/floor_layouts/0/rooms/0" in first
    assert "/components/2/placement/position" in first
    assert result["status"] == "failed" and len(calls) == 3


@pytest.mark.asyncio
async def test_unchanged_repair_is_identified_in_the_remaining_bounded_attempt(monkeypatch):
    raw = conflicting_drawing()
    fixed_layouts = deepcopy(raw["floor_layouts"])
    fixed_layouts[0]["rooms"][0]["bounds"]["width"] = 4
    replies = [raw, {"floor_layouts": raw["floor_layouts"]}, {"floor_layouts": fixed_layouts}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(replies.pop(0)), token_usage=None, finish_reason="stop")

    def validate(drawing):
        errors = floor_layout_conflicts(drawing)
        if errors:
            raise ValueError("；".join(errors))

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = await design_workflow.draft_design(base_prompt="完整图纸", user_request="别墅", validate=validate)
    assert diag["settled"] and diag["model_calls"] == 3
    assert diag["rejected_attempts"][1]["unchanged"] is True
    assert "未修改" in prompts[2]
    assert result == {**raw, "floor_layouts": fixed_layouts}


@pytest.mark.asyncio
async def test_layout_revision_can_supply_its_explicit_passage_in_components(monkeypatch):
    raw = conflicting_drawing()
    raw["components"] = []
    door = {"id": "passage", "type": "door", "host": "partition", "size": {"width": 1, "height": 2}}
    replies = [raw, {"components": [door]}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(replies.pop(0)), token_usage=None, finish_reason="stop")

    def validate(drawing):
        if not drawing["components"]:
            raise ValueError("/floor_layouts/0/rooms/0：已设计的连通隔墙需要明确的通行开口")

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = await design_workflow.draft_design(base_prompt="完整图纸", user_request="别墅", validate=validate, max_attempts=2)
    assert diag["settled"] and diag["model_calls"] == 2
    assert result == {**raw, "components": [door]}
    assert "components" in prompts[1] and "floor_layouts" in prompts[1]


@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.asyncio
async def test_semantic_revision_honors_the_users_thinking_selection(monkeypatch, thinking):
    raw = conflicting_drawing()
    fixed = deepcopy(raw["floor_layouts"])
    fixed[0]["rooms"][0]["bounds"]["width"] = 4
    replies = [raw, {"floor_layouts": fixed}]
    options = []

    async def model(_llm, _messages):
        return SimpleNamespace(content=json.dumps(replies.pop(0)), token_usage=None, finish_reason="stop")

    def validate(drawing):
        if floor_layout_conflicts(drawing):
            raise ValueError("/floor_layouts/0/rooms/0：内墙贯穿房间范围")

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: options.append(kwargs))
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = await design_workflow.draft_design(base_prompt="图纸", user_request="别墅", validate=validate,
                                                     thinking_mode=thinking, max_attempts=2)
    assert diag["settled"] and len(options) == 2
    assert [option["enable_thinking"] for option in options] == [thinking, thinking]


def test_wall_conflict_feedback_also_identifies_overlapping_neighbor_room():
    design = {"floor_layouts": [{"floor": 2, "rooms": [
        {"id": "bath", "name": "卫生间", "bounds": {"x": 4, "z": 6.5, "width": 2.5, "depth": 2.5}},
        {"id": "corridor", "name": "走廊", "bounds": {"x": 0, "z": 6.5, "width": 12, "depth": 1.5}},
    ], "walls": [{"id": "side", "from": [6.5, 6.5], "to": [6.5, 9]}]}]}
    errors = floor_layout_conflicts(design)
    assert len(errors) == 1
    assert "bath" in errors[0] and "卫生间" in errors[0] and "重叠" in errors[0]
    assert "bounds.x=6.5" in errors[0] and "bounds.width=5.5" in errors[0]
