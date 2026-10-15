"""图纸修订保留完整原稿，不把截断输出中的内部对象当成图纸。"""

import json
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import design_workflow
from app.design.coordinates import floor_layout_conflicts


def run_without_event_loop(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    else:
        coroutine.close()
        raise AssertionError("替身模型不应等待外部服务")


def test_local_format_repair_preserves_complete_drawing(monkeypatch):
    original = {
        "concept": "写字楼", "design_intent": {"goals": ["办公"]},
        "massing": {"shape": "tower", "width": 24, "depth": 24, "floors": 8},
        "volumes": [{"id": "tower", "x": 0, "z": 0, "width": 24, "depth": 24,
                     "start_floor": 1, "end_floor": 8}],
        "facades": {face: {"bays": 1, "ground_pattern": ["window"],
                           "upper_pattern": ["window"]}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "flat"},
        "components": [{"id": "entrance", "type": "door"}],
        "floor_layouts": [{"floor": 1,
                           "rooms": [{"id": "office", "bounds": {"x": 1, "z": 1,
                                                                      "width": 4, "depth": 4}}],
                           "walls": [{"id": "core_wall_mid", "from": [3, 1], "to": [3, 5]}]}],
    }
    repaired_layouts = [{"floor": 1,
                         "rooms": [{"id": "office", "bounds": {"x": 3, "z": 1,
                                                                    "width": 4, "depth": 4}}],
                         "walls": original["floor_layouts"][0]["walls"]}]
    answers = [
        SimpleNamespace(content=json.dumps(original), token_usage=None, finish_reason="stop"),
        SimpleNamespace(content='{"floor_layouts": [', token_usage=None, finish_reason="length"),
        SimpleNamespace(content=json.dumps({"floor_layouts": repaired_layouts}),
                        token_usage=None, finish_reason="stop"),
    ]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return answers.pop(0)

    def validate(drawing):
        assert drawing["massing"] == original["massing"]
        assert drawing["facades"] == original["facades"]
        conflicts = floor_layout_conflicts(drawing)
        if conflicts:
            raise ValueError("；".join(conflicts))

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = run_without_event_loop(design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成一个写字楼", validate=validate,
    ))

    assert diag["settled"] and diag["model_calls"] == 3
    assert result == {**original, "floor_layouts": repaired_layouts}
    assert original["floor_layouts"] != repaired_layouts
    assert "只返回" in prompts[1] and "floor_layouts" in prompts[1]
    assert "绘制完整图纸" not in prompts[1]
    assert "输出达到长度上限" in diag["rejected_attempts"][1]["issue"]
    assert "floor_layouts" in prompts[2]


def test_truncated_root_does_not_become_nested_design_intent(monkeypatch):
    async def model(_llm, _messages):
        return SimpleNamespace(content='{"concept":"写字楼","design_intent":{"goals":["办公"]},',
                               token_usage=None, finish_reason="length")

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = run_without_event_loop(design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成一个写字楼", max_attempts=1,
    ))

    assert result == {}
    assert "输出达到长度上限" in diag["last_issue"]


def test_full_revision_keeps_volume_and_component_hosts_together(monkeypatch):
    original = {
        "concept": "写字楼", "massing": {"shape": "tower", "floors": 3},
        "volumes": [{"id": "main_office"}], "facades": {"front": {"bays": 1}},
        "roof": {"type": "flat"},
        "components": [
            {"id": "stair", "type": "stair", "form": {"rises": 30}},
            {"id": "entry", "type": "door", "host": "wall_main_office_front_L1"},
            {"id": "parapet", "type": "parapet", "host": "main_office"},
        ],
    }
    revised = {**original, "volumes": [{"id": "main_office_volume"}],
               "components": [
                   {"id": "stair", "type": "stair", "form": {"rises": 10}},
                   {"id": "entry", "type": "door", "host": "wall_main_office_volume_front_L1"},
                   {"id": "parapet", "type": "parapet", "host": "main_office_volume"},
               ]}
    incomplete = {key: value for key, value in revised.items() if key != "facades"}
    answers = [original, incomplete, revised]

    async def model(_llm, _messages):
        return SimpleNamespace(content=json.dumps(answers.pop(0)), token_usage=None,
                               finish_reason="stop")

    def validate(drawing):
        if drawing["components"][0]["form"]["rises"] > 20:
            raise ValueError("/components/0/form：踏步总高差超过楼层高差")
        volume_id = drawing["volumes"][0]["id"]
        assert drawing["components"][1]["host"] == f"wall_{volume_id}_front_L1"
        assert drawing["components"][2]["host"] == volume_id

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = run_without_event_loop(design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成一个写字楼", validate=validate,
    ))

    assert result == revised and diag["settled"]
    assert "局部修订改动了其他字段" in diag["rejected_attempts"][1]["issue"]


def test_successive_field_repairs_keep_earlier_facade_fix(monkeypatch):
    faces = {face: {"bays": 1, "ground_pattern": ["open"], "upper_pattern": []}
             for face in ("front", "back", "left", "right")}
    fixed_faces = {**faces, "front": {"bays": 1, "ground_pattern": ["door"],
                                       "upper_pattern": []}}
    original = {
        "concept": "写字楼", "massing": {"shape": "tower", "floors": 1},
        "volumes": [{"id": "main"}], "facades": {"shared": faces},
        "roof": {"type": "flat"},
        "components": [{"id": "entry", "type": "door", "host": "wall_main_front_L1"},
                       {"id": "light", "type": "downlight", "host": "ceiling_main_L1"}],
    }
    fixed_components = [original["components"][0],
                        {"id": "light", "type": "downlight", "host": "main"}]
    answers = [original, {"facades": fixed_faces}, {"components": fixed_components}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(answers.pop(0)), token_usage=None,
                               finish_reason="stop")

    def validate(drawing):
        if "front" not in drawing["facades"]:
            raise ValueError("图纸缺少关键设计字段：/facades/front/bays")
        if drawing["components"][1]["host"] != "main":
            raise ValueError("/decisions/components/1/host：引用目标未在图纸声明")
        assert drawing["facades"]["front"]["ground_pattern"] == ["door"]

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = run_without_event_loop(design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成一个写字楼", validate=validate,
    ))

    assert diag["settled"] and diag["model_calls"] == 3
    assert result == {**original, "facades": fixed_faces, "components": fixed_components}
    assert "components" in prompts[1] and "facades" in prompts[2]
    assert "open" in prompts[1] and "open" in prompts[2]


@pytest.mark.parametrize("missing,problem", [
    ("facades", "/facades/front/bays"),
    ("roof", "/roof/type"),
])
def test_missing_top_level_field_is_repaired_without_rewriting_drawing(monkeypatch, missing, problem):
    original = {"concept": "写字楼", "massing": {"shape": "tower", "floors": 3},
                "volumes": [{"id": "office"}],
                "facades": {face: {"bays": 1, "ground_pattern": ["window"],
                                   "upper_pattern": ["window"]}
                            for face in ("front", "back", "left", "right")},
                "roof": {"type": "flat"}, "components": []}
    incomplete = {key: value for key, value in original.items() if key != missing}
    answers = [incomplete, {missing: original[missing]}]

    async def model(_llm, _messages):
        return SimpleNamespace(content=json.dumps(answers.pop(0)), token_usage=None,
                               finish_reason="stop")

    def validate(drawing):
        if missing not in drawing:
            raise ValueError("图纸缺少关键设计字段：" + problem)

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = run_without_event_loop(design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成一个写字楼", validate=validate,
    ))

    assert result == original and diag["settled"] and diag["model_calls"] == 2


@pytest.mark.parametrize("repair_target", ["components", "facades", "volumes"])
def test_open_facade_host_repair_accepts_each_related_design_field(monkeypatch, repair_target):
    from app.design.resolver import build_design_document, resolve_design
    from app.design.coordinates import opening_coordinate_errors

    original = {
        "concept": "办公楼", "massing": {"shape": "rectangular", "width": 10, "depth": 8,
                                   "floors": 1, "modeled_floors": 1, "floor_height": 3},
        "volumes": [{"id": "main", "x": 0, "z": 0, "width": 10, "depth": 8,
                     "start_floor": 1, "end_floor": 1}],
        "structural_grid": {"system": "frame", "x_bays": 2, "z_bays": 2},
        "facades": {face: {"bays": 1, "ground_pattern": ["empty" if face == "back" else "open"],
                           "upper_pattern": []}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "flat"},
        "components": [{"id": "entry", "type": "door", "host": "main",
                        "size": {"width": 1, "height": 2},
                        "placement": {"face": "front", "floor": 1, "offset": 2,
                                      "sill_height": 0}}],
    }
    changes = {
        "components": [{**original["components"][0], "placement": {
            **original["components"][0]["placement"], "face": "back"}}],
        "facades": {**original["facades"], "front": {
            **original["facades"]["front"], "ground_pattern": ["empty"]}},
        "volumes": [{**original["volumes"][0], "facades": {
            "front": {"bays": 1, "ground_pattern": ["empty"], "upper_pattern": []}}}],
    }
    answers = [original, {repair_target: changes[repair_target]}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(answers.pop(0)), token_usage=None,
                               finish_reason="stop")

    def validate(drawing):
        document = build_design_document(drawing, session_id="host_repair", source_request="办公楼")
        errors = opening_coordinate_errors(resolve_design(document).component_markers)
        if errors:
            raise ValueError("；".join(errors))

    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    result, diag = run_without_event_loop(design_workflow.draft_design(
        base_prompt="绘制完整图纸", user_request="生成办公楼", validate=validate,
        max_attempts=2,
    ))

    assert diag["settled"] and diag["model_calls"] == 2, (
        diag["last_issue"].encode("unicode_escape"),
        diag["rejected_attempts"][0]["issue"].encode("unicode_escape"),
    )
    assert result == {**original, repair_target: changes[repair_target]}
    assert all(field in prompts[1] for field in ("components", "facades", "volumes"))
    assert "不要凭空增删门窗" in prompts[1]
