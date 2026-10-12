"""门窗修订反馈指出真实越界方向，不让模型靠移动另一轴绕过错误。"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import design_workflow
from app.agent.prompts.planning import build_architecture_plan_prompt
from app.design.coordinates import opening_coordinate_errors
from app.design.resolver import build_design_document, resolve_design
from tests.plan.test_drawing_implementation import run


def marker(*, face="front", floor=2, sill=2.5, height=2.1, offset=5.25,
           width=1.5, length=12, dx=0, dz=0, position=None):
    bottom = (floor-1)*3.3
    a, b = {
        "front": ([dx, bottom, dz], [dx+length, bottom+3.3, dz]),
        "back": ([dx+length, bottom, dz], [dx, bottom+3.3, dz]),
        "right": ([dx, bottom, dz], [dx, bottom+3.3, dz+length]),
        "left": ([dx, bottom, dz+length], [dx, bottom+3.3, dz]),
    }[face]
    placement = {"offset": offset, "sill_height": sill} if position is None else {"position": position}
    return {"id": "test_window", "type": "arched_window", "design_path": "/decisions/components/9",
            "design": {"size": {"width": width, "height": height}, "placement": placement},
            "entity": {"from": [offset, bottom+sill, 0]},
            "diagram_host": {"id": "wall_host", "type": "wall", "from": a, "to": b}}


@pytest.mark.parametrize("face", ["front", "back", "left", "right"])
@pytest.mark.parametrize("floor,dx,dz", [(1, 0, 0), (2, 30, -15), (5, -90, 25)])
def test_vertical_feedback_reports_relative_sill_and_two_valid_repair_choices(face, floor, dx, dz):
    item = marker(face=face, floor=floor, dx=dx, dz=dz)
    before = deepcopy(item)
    errors = opening_coordinate_errors([item])
    assert len(errors) == 1
    message = errors[0]
    assert "/decisions/components/9/placement" in message
    assert "竖向范围" in message and "sill_height=2.5" in message
    assert "窗高=2.1" in message and "墙高=3.3" in message
    assert "sill_height 的可用范围 [0, 1.2]" in message
    assert "height 的可用范围 (0, 0.8]" in message
    assert "offset" not in message and "世界 X/Z" not in message
    assert item == before


@pytest.mark.parametrize("offset,width", [(-0.2, 1.5), (11, 1.5), (1, 13)])
def test_horizontal_feedback_reports_only_along_wall_failure(offset, width):
    item = marker(offset=offset, width=width, sill=0.9, height=1.5)
    message = opening_coordinate_errors([item])[0]
    assert "沿墙范围" in message
    if width <= 12:
        assert "沿墙局部距离" in message
    assert "竖向范围" not in message and "sill_height" not in message
    assert "offset 的可用范围 [0, 10.5]" in message if width <= 12 else "没有可用 offset" in message


def test_both_axes_are_reported_together_and_oversized_height_is_not_given_an_invalid_range():
    item = marker(offset=11, height=4, sill=0)
    message = opening_coordinate_errors([item])[0]
    assert "沿墙范围" in message and "竖向范围" in message
    assert "没有可用 sill_height" in message
    assert "[0, -" not in message


def test_world_center_feedback_does_not_ask_for_a_local_sill_or_offset():
    item = marker(position=[6, 6.85, 0])
    message = opening_coordinate_errors([item])[0]
    assert "position[1] 是世界中心 Y" in message
    assert "position[1] 的可用范围 [4.35, 5.55]" in message
    assert "sill_height" not in message


@pytest.mark.parametrize("offset,width", [(-0.2, 1.5), (1, 13)])
def test_world_horizontal_feedback_keeps_world_placement_instead_of_inventing_offset(offset, width):
    item = marker(offset=offset, width=width, sill=0.9, height=1.5,
                  position=[offset+width/2, 4.95, 0])
    message = opening_coordinate_errors([item])[0]
    assert "沿墙范围" in message and "offset" not in message
    assert "中心距离" in message if width <= 12 else "没有可用沿墙位置" in message


def test_window_bottom_below_wall_requires_placement_revision_even_if_height_is_reduced():
    message = opening_coordinate_errors([marker(sill=-0.5, height=1.5)])[0]
    assert "sill_height 的可用范围" in message
    assert "不能只改窗高" in message and "保留窗底时 height 的可用范围" not in message


def test_world_window_taller_than_wall_has_no_valid_center_position():
    message = opening_coordinate_errors([marker(sill=0, height=4, position=[6, 5.3, 0])])[0]
    assert "当前窗高没有可用中心位置" in message
    assert "position[1] 的可用范围" not in message and "sill_height" not in message


@pytest.mark.parametrize("sill,height", [(0, 3.3), (1.2, 2.1), (0.9, 1.5)])
def test_valid_sill_and_exact_wall_top_pass_without_changing_design(sill, height):
    item = marker(sill=sill, height=height)
    before = deepcopy(item)
    assert opening_coordinate_errors([item]) == []
    assert item == before


def test_one_format_revision_can_fix_actual_height_conflict_and_preserve_high_window_intent(monkeypatch):
    plan = {
        "concept": "欧式别墅", "massing": {"shape": "自由组合", "width": 12, "depth": 10,
            "floors": 2, "modeled_floors": 2, "floor_height": 3.3},
        "volumes": [{"id": "main", "x": 0, "z": 0, "width": 12, "depth": 10,
                     "start_floor": 1, "end_floor": 2}],
        "structural_grid": {"system": "frame", "x_bays": 3, "z_bays": 2},
        "facades": {f: {"bays": 1, "ground_pattern": ["empty"], "upper_pattern": ["empty"]}
                    for f in ("front", "back", "left", "right")},
        "roof": {"type": "custom_roof"},
        "components": [{"id": "high_window", "type": "arched_window", "host": "wall_main_front_L2",
            "size": {"width": 1.5, "height": 2.1}, "placement": {"offset": 5.25, "sill_height": 2.5},
            "description": "阳台门上方的高窗", "form": {"arch": "自由拱形"}},
            {"id": "bath_window", "type": "window", "host": "wall_main_left_L1",
             "size": {"width": 1.5, "height": 2.1}, "placement": {"offset": 6, "sill_height": 1.5}}],
    }
    before = deepcopy(plan)
    prompts, options = [], []
    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        output = deepcopy(plan)
        if len(prompts) > 1:
            assert "height 的可用范围 (0, 0.8]" in prompts[-1]
            assert "height 的可用范围 (0, 1.8]" in prompts[-1]
            output["components"][0]["size"]["height"] = 0.8
            output["components"][1]["size"]["height"] = 1.8
        return SimpleNamespace(content=json.dumps(output), token_usage=None)
    def validate(output):
        document = build_design_document(output, session_id="height_feedback", source_request="欧式别墅")
        errors = opening_coordinate_errors(resolve_design(document).component_markers)
        if errors:
            raise ValueError("；".join(errors))
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: options.append(kwargs))
    output, diag = run(design_workflow.draft_design(base_prompt=build_architecture_plan_prompt(""),
        user_request="欧式别墅", thinking_mode=True, validate=validate))
    assert diag["settled"] and diag["model_calls"] == 2
    assert [o["enable_thinking"] for o in options] == [True, False]
    expected = deepcopy(before)
    expected["components"][0]["size"]["height"] = 0.8
    expected["components"][1]["size"]["height"] = 1.8
    assert output == expected and plan == before
