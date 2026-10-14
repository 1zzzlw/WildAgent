"""局部修订保留有效实体，重复响应不应变成改名后的重叠构件。"""
from copy import deepcopy
import json

import pytest

from app.agent.plan import implementation as impl
from app.design.markers import implementation_records
from app.tools.spatial_tools import validate_element_dimensions
from tests.plan.test_drawing_implementation import drawing, empty_state, patch_services, reply, run, task


def column(entity_id="stable_column", offset=0):
    return {"type": "column", "id": entity_id, "base": [offset, 0, 0], "height": 3,
            "bottomRadius": 0.1, "topRadius": 0.1, "style": "modern"}


def test_body_cannot_add_an_unmarked_column_to_a_resolved_drawing():
    base = empty_state()["skeleton_blueprint"]
    marker = {"type": "building_body", "design": {"floor_layouts": [{"rooms": [{"id": "living"}]}]}}
    with pytest.raises(ValueError, match="图纸未标注的独立柱"):
        impl._accept_group(base, {"geometry": {"elements": [column()]}}, marker)


def slab(entity_id="slab", offset=0, valid=True):
    return {"type": "floor", "id": entity_id, "from": [offset, -0.18, 0],
            "to": [offset+2 if valid else offset, -0.18, 2], "thickness": 0.18}


def test_body_omits_unmarked_columns_when_drawing_has_rooms(monkeypatch):
    document = drawing()
    document.decisions.floor_layouts = [{"floor": 1, "level": 0,
        "rooms": [{"id": "living", "bounds": {"x": 0, "z": 0, "width": 4, "depth": 4}}], "walls": []}]
    state = empty_state(document)
    patch_services(monkeypatch, [reply("building_body", [slab(), column()])])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and ids == ["slab"]
    assert next(t for t in trace if t.get("tool") == "generate_wild")["outside_item_entity_ids"] == ["stable_column"]


@pytest.mark.parametrize("marker_id", ["building_body", "lattice"])
def test_repair_repeated_column_is_kept_once_and_bad_slab_is_replaced(monkeypatch, marker_id):
    state = empty_state()
    stable, bad = column(), slab(valid=False)
    events = patch_services(monkeypatch, [reply(marker_id, [stable, bad]),
                                        reply(marker_id, [stable, slab()])])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state, marker_id)))
    assert status == "succeeded" and set(ids) == {"stable_column", "slab"}
    assert events == ["rag", "model", "model"]
    entities = updates["component_fragments"][task(state, marker_id).id]
    assert entities.count(stable) == 1 and bad not in entities
    record = implementation_records(updates)[marker_id]
    assert record["attempted_stages"] == ["generate", "repair_1"]
    assert sum(t.get("model_calls", 0) for t in trace) == 2
    assert record["attempts"][-1]["repeated_entity_ids"][marker_id] == [stable["id"]]


def test_echo_without_corrected_geometry_keeps_original_failed_fragment(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    stable, bad = column(), slab(valid=False)
    patch_services(monkeypatch, [])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return reply("building_body", [stable, bad] if len(contexts) == 1 else [stable])
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, _, message, trace = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "aborted" and not updates["component_fragments"][task(state, "building_body").id]
    assert contexts[1]["failed_implementations"]["building_body"]["geometry"]["elements"] == [bad]
    assert contexts[2]["failed_implementations"]["building_body"]["geometry"]["elements"] == [bad]
    assert "没有生成有效实体" not in message
    assert "slab" in message
    assert contexts[2]["validation_feedback"] == contexts[1]["validation_feedback"]
    echoes = [t for t in trace if t.get("stage") in {"repair_1", "repair_2"}]
    assert all(t["repeated_entity_ids"]["building_body"] == [stable["id"]] for t in echoes)


@pytest.mark.parametrize("geometry", [None, [], "invalid"])
def test_malformed_repair_geometry_stays_a_local_failure(monkeypatch, geometry):
    state = empty_state()
    bad = slab(valid=False)
    malformed = reply("building_body")
    malformed.content = json.dumps({"implementations": [{"id": "building_body", "geometry": geometry}]})
    patch_services(monkeypatch, [reply("building_body", [column(), bad]), malformed,
                                reply("building_body", [slab()])])
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and set(ids) == {"stable_column", "slab"}
    assert implementation_records(updates)["building_body"]["attempted_stages"] == ["generate", "repair_1", "repair_2"]


@pytest.mark.parametrize("change", ["height", "id", "material"])
def test_repair_cannot_overwrite_or_rename_a_retained_column(monkeypatch, change):
    state = empty_state()
    stable, bad = column(), slab(valid=False)
    changed = {**stable, change: {"height": 4, "id": "renamed_column", "material": "new_material"}[change]}
    events = patch_services(monkeypatch, [reply("building_body", [stable, bad]),
                                        reply("building_body", [changed, slab()]),
                                        reply("building_body", [changed])])
    updates, status, _, message, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "aborted" and events == ["rag", "model", "model", "model"]
    assert "重叠柱" in message if change == "id" else "已采用" in message
    assert not updates["component_fragments"][task(state, "building_body").id]


def test_entities_owned_by_another_marker_are_not_treated_as_repeat_echoes():
    base = empty_state()["skeleton_blueprint"]
    stable = column()
    base["geometry"]["elements"] = [stable]
    with pytest.raises(ValueError, match="已采用") as error:
        impl._accept_group(base, {"geometry": {"elements": [stable]}},
                           {"type": "custom_lattice", "design": {}})
    assert stable["id"] in str(error.value) and "前缀" not in str(error.value)


def test_partial_failure_feedback_contains_bad_slab_and_overlapping_column():
    base = empty_state()["skeleton_blueprint"]
    stable, bad = column(), slab(valid=False)
    original = deepcopy(base)
    _, accepted, rejected, _ = impl._accept_fragment(base,
        {"geometry": {"elements": [stable, bad, column("duplicate_column")]}},
        {"type": "building_body", "design": {}})
    assert accepted["geometry"]["elements"] == [stable]
    assert {e["id"] for e in rejected["row"]["geometry"]["elements"]} == {"slab", "duplicate_column"}
    assert "slab" in rejected["error"] and "重叠柱" in rejected["error"]
    assert base == original


@pytest.mark.parametrize("axis,offset", [(0, -10), (0, 0), (2, 15)])
def test_zero_area_rectangular_floor_fails_dimensions(axis, offset):
    floor = slab(offset=offset)
    floor["to"][axis] = floor["from"][axis]
    bp = {"geometry": {"elements": [floor], "components": []}}
    original = deepcopy(bp)
    assert "❌" in validate_element_dimensions.func(bp)
    assert bp == original


def test_valid_rectangular_and_circular_floors_still_pass_dimensions():
    bp = {"geometry": {"elements": [slab(), {"type": "floor", "id": "round_slab",
          "shape": "circle", "from": [4, -0.18, 0], "radius": 2, "thickness": 0.18}], "components": []}}
    assert "❌" not in validate_element_dimensions.func(bp)
