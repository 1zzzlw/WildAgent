"""重复墙、跨层宿主及失败补丁回放；不调用模型或数据库。"""

import asyncio
from copy import deepcopy
import json

import pytest

from app.agent.workflows.design import drafting
from app.agent.workflows.design.architecture import _validation_reason
from app.domain.design.coordinates import DesignCoordinateConflict, wall_covers
from app.domain.design.resolver import build_design_document, resolve_design
from app.domain.design.spatial import host_point, resolve_geometry
from app.infrastructure.llm.invocation import LlmResult
from tests.contracts.test_spatial_design import spatial_plan


def duplicate_plan(kind="rectangle"):
    plan = spatial_plan(kind)
    duplicate = deepcopy(plan["walls"][0])
    duplicate["id"] = "duplicate_wall"
    plan["walls"].append(duplicate)
    plan["components"] = [{
        "id": "window", "type": "window", "host": duplicate["id"],
        "size": {"width": 1, "height": 1},
        "placement": {"mode": "wall", "anchor": "bottom_left", "offset": 2,
                      "elevation": {"level": "L1", "offset": .8}},
    }]
    return plan


def validate(plan):
    document = build_design_document(plan, session_id="patch-replay", source_request="生成建筑")
    return resolve_design(document)


def validation_issue(plan):
    try:
        validate(plan)
    except ValueError as exc:
        return _validation_reason(exc)
    raise AssertionError("预期原稿存在冲突")


def merge_patch(plan):
    return {"operations": [
        {"op": "remove", "path": f"/walls/{len(plan['walls']) - 1}"},
        {"op": "replace", "path": "/components/0/host", "value": plan["walls"][0]["id"]},
    ]}


def test_duplicate_feedback_exposes_both_walls_and_dependent_paths():
    plan = duplicate_plan()
    with pytest.raises(DesignCoordinateConflict) as exc:
        validate(plan)
    conflict = next(item for item in exc.value.conflicts if item["code"] == "floor_wall_facade_conflict")
    assert {"/decisions/walls/0", "/decisions/walls/4", "/components/0/host"} <= set(conflict["related_paths"])
    paths = drafting._repair_paths(validation_issue(plan), plan, set(plan))
    assert {"/walls/0", "/walls/4", "/components/0"} <= set(paths)


def test_repair_context_contains_levels_hosts_and_other_openings_without_widening_scope():
    plan = duplicate_plan()
    plan["components"].append({**deepcopy(plan["components"][0]), "id": "other_window"})
    paths = ["/components/0"]
    prompt = drafting._build_repair_prompt(plan, paths, "错层宿主", "上一补丁失败", "")
    context = json.loads(prompt.split("\n当前相关设计数据：", 1)[1])
    assert context["levels"] == plan["levels"]
    assert context["systems"] == plan["systems"]
    assert context["profiles"] == plan["profiles"]
    assert context["resolved_hosts"][0]["from"][1] == pytest.approx(1.2)
    assert context["hosted_components"]["/components/1"]["id"] == "other_window"
    assert paths == ["/components/0"]
    assert "上一补丁未通过：上一补丁失败" in prompt


def test_stable_id_error_paths_are_converted_to_current_indices():
    plan = duplicate_plan()
    paths = drafting._repair_paths("/components/window/host：宿主未声明", plan, set(plan))
    assert "/components/0" in paths
    assert "/components" not in paths
    assert "/walls/-" in paths


def test_rejected_candidate_wall_indices_map_back_to_the_retained_draft():
    plan = duplicate_plan()
    candidate = deepcopy(plan)
    candidate["walls"].pop(0)
    paths = drafting._repair_paths("/walls/2/geometry：墙几何错误", candidate, set(plan), target_draft=plan)
    assert "/walls/3" in paths
    assert "/walls/2" not in paths


def test_malformed_first_draft_can_still_build_a_targeted_repair_prompt():
    plan = duplicate_plan()
    plan["walls"] = ["not a wall"]
    plan["components"] = ["not a component"]
    paths = drafting._repair_paths("/walls/0：应为对象", plan, set(plan))
    prompt = drafting._build_repair_prompt(plan, paths, "字段类型错误", "字段类型错误", "")
    context = json.loads(prompt.split("\n当前相关设计数据：", 1)[1])
    assert context["repair_targets"]["/walls/0"]["value"] == "not a wall"


@pytest.mark.parametrize("kind", ["rectangle", "circle"])
def test_duplicate_wall_removal_and_reference_migration_are_atomic(kind):
    plan = duplicate_plan(kind)
    original = deepcopy(plan)
    paths = drafting._repair_paths(validation_issue(plan), plan, set(plan))
    candidate = drafting._apply_repair(plan, merge_patch(plan), paths)
    validate(candidate)
    assert len(candidate["walls"]) == len(plan["walls"]) - 1
    assert candidate["components"][0]["id"] == "window"
    assert plan == original


@pytest.mark.parametrize("reference", ["host", "relation", "circulation"])
def test_deleting_a_wall_with_unmigrated_references_is_rejected(reference):
    plan = duplicate_plan()
    if reference != "host":
        plan["components"][0]["host"] = plan["walls"][0]["id"]
    if reference == "relation":
        plan["relations"] = [{"id": "alignment", "type": "aligned", "subject": "window", "targets": ["duplicate_wall"]}]
    if reference == "circulation":
        plan["circulation"] = {"required_connections": [{"from": "window", "to": "duplicate_wall"}]}
    original = deepcopy(plan)
    patch = {"operations": [{"op": "remove", "path": "/walls/4"}]}
    with pytest.raises(ValueError, match="同一补丁迁移引用"):
        drafting._apply_repair(plan, patch, ["/walls/4"])
    assert plan == original


def test_multiple_deletions_keep_original_indices_for_remaining_edits():
    plan = duplicate_plan()
    plan["components"] = []
    duplicate = deepcopy(plan["walls"][1])
    duplicate["id"] = "second_duplicate"
    plan["walls"].append(duplicate)
    patch = {"operations": [
        {"op": "remove", "path": "/walls/0"},
        {"op": "remove", "path": "/walls/1"},
        {"op": "add", "path": "/walls/2/geometry/top/offset", "value": -.1},
    ]}
    candidate = drafting._apply_repair(plan, patch, ["/walls/0", "/walls/1", "/walls/2"])
    assert [wall["id"] for wall in candidate["walls"]] == ["wall_back", "wall_left", "duplicate_wall", "second_duplicate"]
    assert candidate["walls"][0]["geometry"]["top"]["offset"] == -.1
    validate(candidate)


@pytest.mark.parametrize("change", ["nonduplicate", "partial_height", "moved_retainer"])
def test_nonredundant_wall_cannot_be_deleted_to_pass_validation(change):
    plan = duplicate_plan()
    plan["components"] = []
    if change == "nonduplicate":
        plan["walls"].pop()
    if change == "partial_height":
        plan["walls"][0]["geometry"]["top"]["offset"] = -1
    patch = {"operations": [{"op": "remove", "path": f"/walls/{len(plan['walls']) - 1}"}]}
    if change == "moved_retainer":
        patch["operations"].append({"op": "replace", "path": "/walls/0/geometry/edge", "value": "right"})
    with pytest.raises(ValueError, match="未被保留墙完整覆盖"):
        drafting._apply_repair(plan, patch, ["/walls"])


def test_partial_overlap_is_not_complete_coverage():
    removed = {"from": [0, 0, 0], "to": [10, 3, 0], "path": [[0, 0], [10, 0]]}
    retained = {"from": [0, 0, 0], "to": [5, 3, 0], "path": [[0, 0], [5, 0]]}
    assert not wall_covers(retained, removed)
    assert wall_covers(removed, retained)
    retained["path"] = [[10, 0], [0, 0]]
    assert wall_covers(retained, removed)


def test_tilted_wall_cannot_be_merged_based_only_on_its_bottom_path():
    removed = {"from": [0, 0, 0], "to": [10, 3, 0], "path": [[0, 0], [10, 0]]}
    retained = deepcopy(removed)
    retained["sections"] = [
        {"y": 0, "path": [[0, 0], [10, 0]]},
        {"y": 3, "path": [[0, 1], [10, 1]]},
    ]
    assert not wall_covers(retained, removed)


@pytest.mark.parametrize("path,value,op", [
    ("/walls", [], "replace"), ("/components", [], "replace"),
    ("/components/0", None, "remove"), ("/walls/0/id", "renamed", "replace"),
])
def test_repair_cannot_erase_arrays_components_or_stable_ids(path, value, op):
    with pytest.raises(ValueError):
        drafting._apply_repair(duplicate_plan(), {"operations": [{"op": op, "path": path, "value": value}]}, ["/walls", "/components"])


def test_wrong_floor_door_is_still_rejected_after_structural_merge():
    plan = duplicate_plan()
    plan["levels"].insert(1, {"id": "L2", "kind": "storey", "index": 2, "elevation": 4.2})
    plan["levels"][-1]["elevation"] = 7.2
    plan["massing"].update(floors=2, modeled_floors=2)
    for wall in plan["walls"]:
        wall["geometry"]["top"] = {"level": "L2"}
    plan["components"][0]["placement"]["elevation"] = {"level": "L2"}
    candidate = drafting._apply_repair(plan, merge_patch(plan), ["/walls/4", "/components/0"])
    with pytest.raises(DesignCoordinateConflict, match="范围超出宿主"):
        validate(candidate)
    upper = deepcopy(candidate["walls"][0])
    upper["id"] = "upper_wall"
    upper["geometry"].update(bottom={"level": "L2"}, top={"level": "RF"})
    patch = {"operations": [
        {"op": "add", "path": "/walls/-", "value": upper},
        {"op": "replace", "path": "/components/0/host", "value": "upper_wall"},
    ]}
    validate(drafting._apply_repair(candidate, patch, ["/walls/-", "/components/0"]))


def test_rejected_candidate_does_not_replace_the_working_drawing(monkeypatch):
    plan = duplicate_plan()
    other = deepcopy(plan["walls"][1])
    other["id"] = "other_duplicate"
    plan["walls"].append(other)
    bad = merge_patch(plan)
    bad["operations"][0]["path"] = "/walls/4"
    bad["operations"].append({"op": "replace", "path": "/components/0/size/height", "value": 100})
    good = deepcopy(bad)
    good["operations"][-1] = {"op": "remove", "path": "/walls/5"}
    outputs = iter([plan, bad, good])
    prompts = []

    async def reply(messages, **_kwargs):
        prompts.append(messages[0]["content"])
        return LlmResult(content=json.dumps(next(outputs)))

    def check(candidate):
        try:
            validate(candidate)
        except ValueError as exc:
            raise ValueError(_validation_reason(exc)) from exc

    monkeypatch.setattr(drafting, "_request_draft", reply)
    result, diag = asyncio.run(drafting.draft_design(base_prompt="生成建筑", user_request="别墅", validate=check))
    assert diag["settled"] and diag["model_calls"] == 3
    assert [item["validated"] for item in diag["repairs"]] == [False, True]
    assert [item["adopted"] for item in diag["repairs"]] == [False, True]
    assert result["components"][0]["size"]["height"] == 1
    assert len(result["walls"]) == 4
    context = json.loads(prompts[2].split("\n当前相关设计数据：", 1)[1])
    assert len(context["walls"]) == 6
    assert context["repair_targets"]["/components/0"]["value"]["size"]["height"] == 1
    validate(result)


def test_partial_repair_is_kept_only_when_the_remaining_problem_set_strictly_shrinks(monkeypatch):
    plan = duplicate_plan()
    other = deepcopy(plan["walls"][1])
    other["id"] = "other_duplicate"
    plan["walls"].append(other)
    first = merge_patch(plan)
    first["operations"][0]["path"] = "/walls/4"
    second = {"operations": [{"op": "remove", "path": "/walls/4"}]}
    outputs = iter([plan, first, second])

    async def reply(*_args, **_kwargs):
        return LlmResult(content=json.dumps(next(outputs)))

    def check(candidate):
        try:
            validate(candidate)
        except ValueError as exc:
            raise ValueError(_validation_reason(exc)) from exc

    monkeypatch.setattr(drafting, "_request_draft", reply)
    result, diag = asyncio.run(drafting.draft_design(base_prompt="生成建筑", user_request="别墅", validate=check))
    assert diag["settled"]
    assert [item["adopted"] for item in diag["repairs"]] == [True, True]
    assert [item["validated"] for item in diag["repairs"]] == [False, True]
    validate(result)


def test_new_partition_conflict_can_be_repaired_without_adopting_the_failed_candidate(monkeypatch):
    plan = duplicate_plan()
    window = deepcopy(plan["components"][0])
    window.update(id="right_window", host="wall_right")
    plan["components"].append(window)
    hosts = {host["id"]: host for host in resolve_geometry(plan)["hosts"]}
    point = host_point(hosts["wall_right"], 2.5, 2)
    partition = {
        "id": "new_partition", "system": "wall", "role": "interior",
        "geometry": {"type": "path", "frame": "world", "bottom": {"level": "L1"}, "top": {"level": "RF"},
                     "segments": [{"id": "line", "type": "line", "from": [point[0]-3, point[2]], "to": [point[0], point[2]]}]},
    }
    bad = merge_patch(plan)
    bad["operations"].append({"op": "add", "path": "/walls/-", "value": partition})
    good = deepcopy(bad)
    good["operations"].append({"op": "replace", "path": "/components/1/placement/offset", "value": 5})
    outputs = iter([plan, bad, good])
    prompts = []

    async def reply(messages, **_kwargs):
        prompts.append(messages[0]["content"])
        return LlmResult(content=json.dumps(next(outputs)))

    def check(candidate):
        try:
            validate(candidate)
        except ValueError as exc:
            raise ValueError(_validation_reason(exc)) from exc

    monkeypatch.setattr(drafting, "_request_draft", reply)
    result, diag = asyncio.run(drafting.draft_design(base_prompt="生成建筑", user_request="别墅", validate=check))
    assert diag["settled"]
    assert [item["adopted"] for item in diag["repairs"]] == [False, True]
    context = json.loads(prompts[2].split("\n当前相关设计数据：", 1)[1])
    assert context["rejected_patch"] == bad
    assert context["repair_targets"]["/components/1"]["value"]["id"] == "right_window"
    assert context["repair_targets"]["/walls/4"]["value"]["id"] == "duplicate_wall"
    validate(result)
