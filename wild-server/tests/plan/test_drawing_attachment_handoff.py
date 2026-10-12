"""立面实例、真实依附坐标与片段反馈在同一交接边界核对。"""
from copy import deepcopy

import pytest

from app.agent.plan import implementation as impl
from app.design.contracts import ComponentInstance, FacadeDecision
from app.design.markers import component_markers
from app.tools.component_tools import validate_balcony_placement
from app.tools.spatial_tools import validate_reference_integrity
from tests.plan.test_drawing_implementation import drawing, empty_state


@pytest.mark.parametrize("face", ["front", "back", "left", "right"])
@pytest.mark.parametrize("origin", [-20, 15])
def test_explicit_balcony_replaces_its_facade_hint_without_removing_windows(face, origin):
    doc = drawing()
    doc.decisions.massing.floors = doc.decisions.massing.modeled_floors = 2
    volume = doc.decisions.volumes[0]
    volume.end_floor = 2
    volume.x = volume.z = origin
    doc.decisions.facades[face] = FacadeDecision(bays=2, ground_pattern=["empty", "empty"],
                                              upper_pattern=["balcony", "window"])
    doc.decisions.components = [ComponentInstance(id="explicit_balcony", type="balcony", host=volume.id,
        placement={"face": face, "floor": 2, "offset": 1, "sill_height": 0},
        size={"width": 6, "depth": 1.5, "height": 0.15})]
    before = doc.model_dump(mode="json")
    markers = component_markers(doc)
    explicit = next(m for m in markers if m["id"] == "explicit_balcony")
    assert explicit["host"] == f"wall_main_{face}_L2"
    assert f"balcony_main_{face}_L2_1" not in {m["id"] for m in markers}
    assert f"window_main_{face}_L2_2" in {m["id"] for m in markers}
    assert doc.model_dump(mode="json") == before


def test_world_balcony_center_at_top_floor_resolves_once_and_does_not_shift_design():
    doc = drawing()
    doc.decisions.massing.floors = doc.decisions.massing.modeled_floors = 2
    doc.decisions.volumes[0].end_floor = 2
    doc.decisions.facades["front"].upper_pattern = ["balcony"]
    doc.decisions.components = [ComponentInstance(id="explicit", type="balcony", host="main",
        placement={"position": [5, 6, 0.5]}, size={"width": 4, "depth": 1.5, "height": 0.1})]
    markers = component_markers(doc)
    assert [m["id"] for m in markers if m["type"] == "balcony"] == ["explicit"]
    assert next(m for m in markers if m["id"] == "explicit")["entity"]["position"] == [5, 6, 0.5]


def attached_case():
    state = empty_state()
    state["skeleton_blueprint"]["geometry"]["elements"] = [
        {"type": "wall", "id": "wall", "from": [0, 3, 0], "to": [10, 6, 0], "thickness": 0.2},
        {"type": "wall", "id": "back", "from": [10, 3, 8], "to": [0, 6, 8], "thickness": 0.2}]
    balcony = {"type": "balcony", "id": "actual_balcony", "parentWall": "wall", "from": [2, 3, 0],
               "width": 4, "depth": 1.5, "slabThickness": 0.15}
    state["skeleton_blueprint"]["geometry"]["components"] = [balcony]
    state["component_diagnostics"] = {"balcony_task": {"implementations": {
        "drawing_balcony": {"status": "implemented", "entity_ids": [balcony["id"]]}}}}
    marker = {"id": "guard", "type": "railing", "host": "drawing_balcony", "depends_on": ["drawing_balcony"],
              "design": {}, "entity": {}}
    return state, balcony, marker


def test_railing_context_uses_actual_balcony_perimeter_in_world_coordinates():
    state, balcony, marker = attached_case()
    before = deepcopy(state)
    context = impl._item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    attachment = context["attachment_geometry"][marker["id"]]
    assert attachment["host_entity_id"] == balcony["id"]
    assert attachment["path"] == [[2, 3, -0.1], [2, 3, -1.6], [6, 3, -1.6], [6, 3, -0.1]]
    assert state == before


@pytest.mark.parametrize("field,kind", [("parentWall", "wall"), ("parentFloor", "floor"), ("parentRoof", "roof")])
def test_native_attachment_reference_checks_type_not_only_existing_id(field, kind):
    state, balcony, _ = attached_case()
    base = state["skeleton_blueprint"]
    component = {"type": "railing", "id": "guard", field: balcony["id"], "path": [[0, 0, 0], [1, 0, 0]], "height": 1}
    base["geometry"]["components"].append(component)
    output = validate_reference_integrity.func(base)
    assert "❌" in output and field in output and kind in output


def test_balconies_that_overlap_are_rejected_without_mutating_or_merging_them():
    state, balcony, _ = attached_case()
    base = state["skeleton_blueprint"]
    other = {**balcony, "id": "second", "from": [5.5, 3, 0]}
    base["geometry"]["components"].append(other)
    before = deepcopy(base)
    assert "重叠" in validate_balcony_placement(base)
    assert base == before
    other["from"][0] = 6
    assert "❌" not in validate_balcony_placement(base)
    other["from"] = [2, 6, 0]
    assert "❌" not in validate_balcony_placement(base)


def test_native_canopy_dimension_feedback_names_the_actual_field_and_expected_value():
    state, _, _ = attached_case()
    base = state["skeleton_blueprint"]
    row = {"geometry": {"components": [{"type": "canopy", "id": "canopy", "parentWall": "wall",
           "from": [2, 4, 0], "width": 3, "depth": 2, "thickness": 0.15}]}}
    marker = {"id": "canopy", "type": "canopy", "design": {"size": {"height": 0.3}}}
    with pytest.raises(ValueError) as error:
        impl._accept_group(base, row, marker)
    assert "/geometry/components/0/thickness" in str(error.value)
    assert "thickness=0.3" in str(error.value)
    context = impl._item_context(state, {marker["id"]: marker}, base)
    assert context["native_size_targets"]["canopy"] == {"thickness": 0.3}


def test_misplaced_railing_and_its_decorations_are_repaired_as_one_group():
    state, balcony, marker = attached_case()
    marker["host_entity_ids"] = [balcony["id"]]
    row = {"geometry": {"elements": [{"type": "primitive", "id": "decoration", "shape": "box",
        "position": [3, 3.5, 1.5], "dimensions": [0.02, 1, 0.02]}], "components": [
        {"type": "railing", "id": "guard", "path": [[2, 3, 0], [2, 3, 1.5], [6, 3, 1.5]], "height": 1.1}]}}
    base = state["skeleton_blueprint"]
    before = deepcopy(base)
    candidate, accepted, failed, record = impl._accept_fragment(base, row, marker)
    assert candidate == before and accepted is None and record is None
    assert failed["row"] == {**row, "repeated_entity_ids": []}
    assert "实际阳台" in failed["error"] and "室外方向" in failed["error"]
    row["geometry"]["components"][0]["path"] = [[2, 3, -0.1], [2, 3, -1.6], [6, 3, -1.6]]
    row["geometry"]["elements"][0]["position"][2] = -1.6
    assert impl._accept_group(base, row, marker)[2]["status"] == "implemented"


def test_railing_handoff_only_disables_builtin_guard_when_child_is_implemented():
    from app.agent.design_flow.compile import _assemble_with_relations
    from app.agent.validation.diagnostics import blueprint_fingerprint
    from app.design.resolver import resolve_design
    doc = drawing()
    doc.decisions.components = [ComponentInstance(id="balcony", type="balcony", host="main"),
                               ComponentInstance(id="guard", type="railing", host="balcony")]
    state, balcony, _ = attached_case()
    state["design_document"] = doc.model_dump(mode="json")
    state["resolved_design"] = resolve_design(doc).model_dump(mode="json")
    geometry = state["skeleton_blueprint"]["geometry"]
    geometry["components"] = []
    balcony["railingEnabled"] = True
    guard = {"type": "railing", "id": "guard", "path": [[2, 3, -1.6], [6, 3, -1.6]], "height": 1.1}
    state["component_fragments"] = {"balcony_task": [balcony], "guard_task": [guard]}
    state["component_diagnostics"] = {task: {"components": [entity["id"]], "implementations": {
        marker_id: {"status": "implemented", "entity_ids": [entity["id"]],
                    "entity_fingerprint": blueprint_fingerprint([entity])}}}
        for task, marker_id, entity in [("balcony_task", "balcony", balcony), ("guard_task", "guard", guard)]}
    before = deepcopy(state)
    output, _, records = _assemble_with_relations(doc, state)
    assert output["geometry"]["components"][0]["railingEnabled"] is False
    assert records["balcony"]["assembly_changes"][0]["rule"] == "compiler.separate_railing"
    assert state == before
    state["component_fragments"]["guard_task"] = []
    state["component_diagnostics"]["guard_task"] = {"implementations": {"guard": {"status": "abandoned", "entity_ids": []}}}
    output, _, _ = _assemble_with_relations(doc, state)
    assert output["geometry"]["components"][0]["railingEnabled"] is True


def test_final_validation_rechecks_actual_railing_relation_even_with_valid_fingerprint(monkeypatch):
    from app.agent.validation.candidate import evaluate_candidate
    from app.agent.validation.diagnostics import blueprint_fingerprint
    from app.design.resolver import _stable_hash
    import app.services.agent_service as service
    doc = drawing()
    doc.decisions.components = [ComponentInstance(id="balcony", type="balcony", host="main"),
                               ComponentInstance(id="guard", type="railing", host="balcony")]
    state, balcony, _ = attached_case()
    base = state["skeleton_blueprint"]
    guard = {"type": "railing", "id": "guard", "path": [[2, 3, 0], [2, 3, 1.5]], "height": 1.1}
    base["geometry"]["components"].append(guard)
    brief = {"implementation": {"design_hash": _stable_hash(doc), "records": {
        marker_id: {"status": "implemented", "entity_ids": [entity["id"]],
                    "entity_fingerprint": blueprint_fingerprint([entity])}
        for marker_id, entity in [("balcony", balcony), ("guard", guard)]}}}
    monkeypatch.setattr(service, "run_validation_pipeline", lambda *a, **kw: [])
    before = deepcopy(base)
    result = evaluate_candidate(base, design_document=doc.model_dump(mode="json"), design_brief=brief)
    assert any(r.name == "design_railing_placement" and r.has_error for r in result["results"])
    assert base == before
