"""图纸格式说明、错误定位与模型定向修订的回归。"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import design_workflow
from app.agent.generation.architecture.workflow import (
    DesignContractError,
    _validation_reason,
    build_design_document_or_error,
)
from app.agent.prompts.planning import build_architecture_plan_prompt


@pytest.fixture
def drawing():
    return {
        "concept": "自由曲面别墅",
        "design_intent": {"goals": ["曲面屋顶"], "assumptions": ["两层"]},
        "massing": {"shape": "自由组合", "width": 18, "depth": 12,
                    "floors": 2, "modeled_floors": 2, "floor_height": 3.6},
        "volumes": [{"id": name, "x": x, "z": 0, "width": 9, "depth": 12,
                     "start_floor": 1, "end_floor": 2}
                    for name, x in (("main", 0), ("wing", 9))],
        "structural_grid": {"system": "自拟结构", "x_bays": 3, "z_bays": 2},
        "facades": {face: {"bays": 1, "ground_pattern": ["custom_opening"],
                           "upper_pattern": ["custom_opening"]}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "custom_curved_roof", "curvature": 0.8},
        "components": [{"id": "sculpture", "type": "custom_sculpture", "host": "main",
                        "size": {"width": 1.2, "height": 2},
                        "form": {"twist": 45}, "placement": {"normal_offset": -0.2}}],
    }


def document(drawing):
    return build_design_document_or_error(drawing, session_id="format_feedback",
        source_request="设计曲面别墅", building_type="villa", style_intent=[], previous=None)


def test_prompt_explains_fields_without_a_fixed_building_template(drawing):
    prompt = build_architecture_plan_prompt("")
    result = document(drawing)
    assert set(result.decisions.facades) == {"front", "back", "left", "right"}
    assert "volumes | 对象数组" in prompt and "x、z 是平面起点" in prompt
    assert "volume 是固定字段名" in prompt
    assert '"massing":' not in prompt and "```json" not in prompt


def test_missing_coordinates_report_every_path_without_mutating_design(drawing):
    for volume in drawing["volumes"]:
        volume["x_start"] = volume.pop("x")
        volume["z_start"] = volume.pop("z")
    original = deepcopy(drawing)
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    reason = str(caught.value)
    for index in range(2):
        for axis in ("x", "z"):
            assert f"/volumes/{index}/{axis}：缺少必填字段" in reason
    assert "Field required" not in reason
    assert drawing == original


def test_facade_key_errors_identify_the_key_and_accepted_names(drawing):
    drawing["facades"] = {"north": drawing["facades"]["front"]}
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    reason = str(caught.value)
    assert "/facades/north/[key]" in reason
    assert all(face in reason for face in ("front", "back", "left", "right"))


@pytest.mark.parametrize("field", ["massing", "volumes", "structural_grid", "facades", "roof"])
def test_missing_root_field_has_an_actionable_path(drawing, field):
    drawing.pop(field)
    with pytest.raises(DesignContractError, match=f"/{field}：缺少必填字段"):
        document(drawing)


def test_design_intent_type_error_is_located(drawing):
    drawing["design_intent"] = "模型将设计意图写成了一句话"
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    assert "/design_intent" in str(caught.value)


@pytest.mark.parametrize("host", [None, "", "main", "sculpture_base"])
def test_optional_host_preserves_explicit_value_and_marker_position(drawing, host):
    from app.design.resolver import resolve_design, architecture_plan_from_document
    drawing["components"][0]["host"] = host
    drawing["components"][0]["placement"] = {"position": [-3, 1, 7]}
    before = deepcopy(drawing)
    doc = document(drawing)
    assert doc.decisions.components[0].host == host
    marker = next(m for m in resolve_design(doc).component_markers if m["id"] == "sculpture")
    assert marker["host"] == host and marker["entity"]["position"] == [-3, 1, 7]
    assert architecture_plan_from_document(doc)["components"][0]["host"] == host
    assert drawing == before


def test_omitted_host_keeps_the_existing_default_and_schema_accepts_null(drawing):
    from app.design.contracts import ComponentInstance
    drawing["components"][0].pop("host")
    assert document(drawing).decisions.components[0].host == ""
    schema = ComponentInstance.model_json_schema()["properties"]["host"]
    assert {s["type"] for s in schema["anyOf"]} == {"string", "null"}
    assert "引用 ID 字符串" in build_architecture_plan_prompt("")


@pytest.mark.parametrize("host", [42, False, ["main"], {"id": "main"}])
def test_non_reference_host_types_are_not_stringified_or_guessed(drawing, host):
    drawing["components"][0]["host"] = host
    before = deepcopy(drawing)
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    assert "/components/0/host" in str(caught.value)
    assert "字符串或 null" in str(caught.value) and "placement" in str(caught.value)
    assert drawing == before


@pytest.mark.asyncio
async def test_independent_component_null_host_does_not_spend_a_format_retry(monkeypatch, drawing):
    drawing["components"][0].update(host=None, placement={"position": [3, 1, 4]})
    calls = []
    async def model(*_args, **_kwargs):
        calls.append(True)
        return SimpleNamespace(content=json.dumps(drawing), token_usage={})
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    raw, diag = await design_workflow.draft_design(base_prompt=build_architecture_plan_prompt(""),
        user_request="生成独立构件", validate=document)
    assert diag["settled"] and diag["model_calls"] == 1 and calls == [True]
    assert raw["components"][0]["host"] is None and raw == drawing


def test_plain_business_error_remains_readable():
    assert _validation_reason(ValueError("体量范围不一致")) == "体量范围不一致"


@pytest.mark.parametrize("scope", ["shared", "volume"])
@pytest.mark.parametrize("field", ["ground_pattern", "upper_pattern"])
@pytest.mark.parametrize("bays", [1, 3, 9])
def test_explicit_empty_pattern_is_equivalent_without_an_extra_model_call(drawing, scope, field, bays):
    face = {"bays": bays, "ground_pattern": ["empty"]*bays, "upper_pattern": ["empty"]*bays}
    face[field] = []
    if scope == "shared":
        drawing["facades"]["front"] = face
        path = f"/decisions/facades/front/{field}"
    else:
        drawing["volumes"][0]["facades"] = {"front": face}
        path = f"/decisions/volumes/0/facades/front/{field}"
    before = deepcopy(drawing)
    result = document(drawing)
    actual = result.decisions.facades["front"] if scope == "shared" else result.decisions.volumes[0].facades["front"]
    assert getattr(actual, field) == ["empty"]*bays and drawing == before
    changes = [c for t in result.rule_trace for c in t.changes if c["path"] == path]
    assert len(changes) == 1 and changes[0]["before"] == []
    assert changes[0]["after"] == ["empty"]*bays and changes[0]["semantic_change"] is False


def test_nonempty_pattern_count_error_reports_expected_and_both_actual_lengths(drawing):
    drawing["facades"]["front"] = {"bays": 4, "ground_pattern": ["window", "door"], "upper_pattern": ["window"]}
    before = deepcopy(drawing)
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    assert "bays=4" in str(caught.value) and "ground_pattern=2" in str(caught.value)
    assert "upper_pattern=1" in str(caught.value) and drawing == before


@pytest.mark.asyncio
async def test_unused_upper_pattern_does_not_trigger_design_revision(monkeypatch, drawing):
    drawing["massing"].update(floors=1, modeled_floors=1)
    drawing["design_intent"]["assumptions"] = ["单层"]
    for volume in drawing["volumes"]:
        volume["end_floor"] = 1
    for facade in drawing["facades"].values():
        facade["upper_pattern"] = []
    calls, progress = [], []
    async def model(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(content=json.dumps(drawing), token_usage={})
    async def emit(_stage, message):
        progress.append(message)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    raw, diag = await design_workflow.draft_design(base_prompt="字段说明", user_request="生成单层建筑",
        validate=document, on_reasoning_delta=emit)
    assert raw == drawing and calls == [True]
    assert diag["settled"] and diag["model_calls"] == 1 and progress == []


def test_face_and_all_size_errors_are_reported_together_with_exact_paths(drawing):
    drawing["components"] = [
        {"id": "living_room_window_01", "type": "floor_window_group", "host": "main",
         "size": {"width": 4.5, "height": 3, "sill_height": 0},
         "placement": {"face": "back", "floor": 1, "offset": 1.5}},
        {"id": "kitchen_door", "type": "glass_sliding_door", "host": "main",
         "size": {"width": 3, "height": 2.4, "sill_height": 0},
         "placement": {"face": "front", "floor": 1, "offset": 2}},
        {"id": "roof_soffit", "type": "eave_soffit", "host": "wing",
         "size": {"width": 6.5, "depth": 1.2}, "placement": {"face": "top", "floor": 1}},
    ]
    before = deepcopy(drawing)
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    reason = str(caught.value)
    assert "/components/0/size/sill_height" in reason
    assert "/components/1/size/sill_height" in reason
    assert "/components/2/placement/face" in reason
    assert "placement.sill_height" in reason and "可以为 0" in reason
    assert "placement.position" in reason and "top" in reason
    assert drawing == before


@pytest.mark.parametrize("field", ["width", "height", "depth", "radius", "custom_length"])
@pytest.mark.parametrize("value", [0, -0.5, float("nan"), float("inf")])
def test_invalid_size_reports_its_field_without_replacing_the_value(drawing, field, value):
    drawing["components"][0]["size"][field] = value
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    assert f"/components/0/size/{field}" in str(caught.value)
    assert drawing["components"][0]["size"][field] is value


def test_zero_sill_height_and_negative_normal_offset_are_positions(drawing):
    drawing["components"][0]["placement"].update(sill_height=0, normal_offset=-0.2)
    result = document(drawing).decisions.components[0]
    assert result.placement.sill_height == 0
    assert result.placement.normal_offset == -0.2
    assert result.size == drawing["components"][0]["size"]


@pytest.mark.parametrize("field", ["sill_height", "offset", "normal_offset", "floor"])
def test_positive_position_parameter_in_size_is_not_silently_ignored(drawing, field):
    drawing["components"][0]["size"][field] = 0.6 if field != "floor" else 1
    with pytest.raises(DesignContractError) as caught:
        document(drawing)
    reason = str(caught.value)
    assert f"/components/0/size/{field}" in reason and f"placement.{field}" in reason
    assert "[key]" not in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
async def test_format_retry_repairs_face_and_sill_in_one_call_without_deep_thinking(drawing, monkeypatch, streaming):
    drawing["components"] = [
        {"id": "living_room_window_01", "type": "floor_window_group", "host": "main",
         "size": {"width": 4.5, "height": 3, "sill_height": 0},
         "placement": {"face": "back", "floor": 1, "offset": 1.5}},
        {"id": "roof_soffit", "type": "eave_soffit", "host": "wing",
         "size": {"width": 6.5, "depth": 1.2}, "placement": {"face": "top", "floor": 1}},
    ]
    options, prompts, notes = [], [], []
    async def model(_llm, messages, **kwargs):
        prompts.append(messages[0]["content"])
        output = deepcopy(drawing)
        if len(prompts) == 2:
            assert "/components/0/size/sill_height" in prompts[-1]
            assert "/components/1/placement/face" in prompts[-1]
            output["components"][0]["placement"]["sill_height"] = output["components"][0]["size"].pop("sill_height")
            output["components"][1]["placement"] = {"position": [13.5, 3.3, 4]}
        return SimpleNamespace(content=json.dumps(output), token_usage=None)
    async def collect(node, text):
        notes.append((node, text))
    monkeypatch.setattr(design_workflow, "stream_llm", model)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: options.append(kwargs))
    raw, diag = await design_workflow.draft_design(
        base_prompt=build_architecture_plan_prompt(""), user_request="设计别墅",
        validate=document, thinking_mode=True, on_reasoning_delta=collect if streaming else None)
    assert diag["settled"] and diag["model_calls"] == 2
    assert [o["enable_thinking"] for o in options] == [True, False]
    assert len(notes) == (1 if streaming else 0)
    if streaming:
        assert "size/sill_height" in notes[0][1] and "placement/face" in notes[0][1]
    assert raw["components"][0]["size"] == {"width": 4.5, "height": 3}
    assert raw["components"][0]["placement"]["sill_height"] == 0
    assert raw["components"][1]["placement"]["position"] == [13.5, 3.3, 4]
    assert raw["roof"] == drawing["roof"] and raw["volumes"] == drawing["volumes"]


def test_retry_receives_all_missing_paths_and_preserves_free_design(drawing, monkeypatch):
    rejected = deepcopy(drawing)
    for volume in rejected["volumes"]:
        volume["x_start"] = volume.pop("x")
        volume["z_start"] = volume.pop("z")
    prompts, notes = [], []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        output = deepcopy(rejected)
        if len(prompts) > 1:
            assert "/volumes/1/z：缺少必填字段" in prompts[-1]
            for volume in output["volumes"]:
                volume["x"] = volume.pop("x_start")
                volume["z"] = volume.pop("z_start")
        return SimpleNamespace(content=json.dumps(output), token_usage=None)

    async def collect(node, text):
        notes.append((node, text))

    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    coroutine = design_workflow.draft_design(
        base_prompt=build_architecture_plan_prompt(""), user_request="设计曲面别墅",
        validate=document, on_reasoning_delta=collect)
    try:
        coroutine.send(None)
    except StopIteration as completed:
        raw, diag = completed.value
    else:
        coroutine.close()
        pytest.fail("替身模型不应等待外部服务")
    assert raw == drawing
    assert diag["settled"] and diag["model_calls"] == 2
    assert len(diag["rejected_attempts"]) == 1
    assert "/volumes/1/z：缺少必填字段" in notes[0][1]
    assert notes[0][0] == "architecture:progress"
    result = document(raw).decisions
    assert result.roof.type == "custom_curved_roof"
    assert result.components[0].form == {"twist": 45}
    assert result.components[0].placement.normal_offset == -0.2


@pytest.fixture
def extended_drawing(drawing):
    drawing["massing"].update(width=18, depth=14, floors=3, modeled_floors=3)
    drawing["volumes"] = [
        {"id": "main_body", "x": -9, "z": -7, "width": 18, "depth": 14,
         "start_floor": 1, "end_floor": 3},
        {"id": "east_pavilion", "x": 5, "z": 1, "width": 4, "depth": 5,
         "start_floor": 1, "end_floor": 1},
        {"id": "garage_wing", "x": -9, "z": -10, "width": 6, "depth": 3,
         "start_floor": 1, "end_floor": 2},
    ]
    drawing["components"][0]["host"] = "main_body"
    return drawing


@pytest.mark.parametrize("roof_volumes", [["main_body"], [{"ref": "main_body"}, {"ref": "garage_wing"}]])
def test_roof_format_and_coordinate_conflict_are_reported_together(extended_drawing, roof_volumes):
    extended_drawing["roof"]["volumes"] = roof_volumes
    original = deepcopy(extended_drawing)
    with pytest.raises(DesignContractError) as caught:
        document(extended_drawing)
    reason = str(caught.value)
    assert "/roof/volumes/0" in reason
    assert '{"volume":' in reason
    assert "/massing/depth" in reason
    assert "17" in reason and "14" in reason
    assert "用户" in reason
    assert extended_drawing == original


@pytest.mark.parametrize("scale,dx,dz", [(1, 0, 0), (2, 30, -20), (0.5, -100, 50)])
def test_coordinate_feedback_names_actual_extent_and_preserves_layout(extended_drawing, scale, dx, dz):
    massing = extended_drawing["massing"]
    for key in ("width", "depth"):
        massing[key] *= scale
    for volume in extended_drawing["volumes"]:
        volume["x"] = volume["x"] * scale + dx
        volume["z"] = volume["z"] * scale + dz
        volume["width"] *= scale
        volume["depth"] *= scale
    original = deepcopy(extended_drawing)
    with pytest.raises(DesignContractError) as caught:
        document(extended_drawing)
    reason = str(caught.value)
    assert "/massing/depth" in reason
    assert f"{17*scale:g} 米" in reason and f"{14*scale:g} 米" in reason
    assert "design_coordinate_conflict" not in reason
    assert extended_drawing == original


def test_roof_and_extent_can_be_revised_within_the_same_retry(extended_drawing, monkeypatch):
    rejected = deepcopy(extended_drawing)
    rejected["roof"]["volumes"] = [{"ref": "main_body"}, {"ref": "garage_wing"}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        output = deepcopy(rejected)
        if len(prompts) > 1:
            assert "/massing/depth" in prompts[-1]
            assert "/roof/volumes/1/volume" in prompts[-1]
            output["massing"]["depth"] = 17
            output["roof"]["volumes"] = [{"volume": "main_body"}, {"volume": "garage_wing"}]
        return SimpleNamespace(content=json.dumps(output), token_usage=None)

    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    coroutine = design_workflow.draft_design(base_prompt=build_architecture_plan_prompt(""),
        user_request="设计欧式别墅", validate=document)
    try:
        coroutine.send(None)
    except StopIteration as completed:
        raw, diag = completed.value
    else:
        coroutine.close()
        pytest.fail("替身模型不应等待外部服务")
    assert diag["settled"] and diag["model_calls"] == 2
    assert raw["volumes"] == rejected["volumes"]
    assert raw["components"] == rejected["components"]
    assert raw["massing"]["depth"] == 17 and rejected["massing"]["depth"] == 14
    assert raw["roof"]["type"] == rejected["roof"]["type"]
    assert document(raw).decisions.roof.volumes[1].volume == "garage_wing"
