"""片段的资源和几何一起采用；拒绝片段不能污染后续并发装配。"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.plan import implementation as impl
from app.design.markers import component_markers, merge_marker_resources
from app.tools.spatial_tools import get_roof_support_bounds, validate_roof_coverage
from tests.plan.test_drawing_implementation import drawing, empty_state, patch_services, run, task


def material(**extra):
    return {"baseColor": [0.7, 0.8, 0.9], "roughness": 0.1, "metallic": 0,
            "albedo": 1, "lightingCondition": "D65_noon", **extra}


def box(entity_id, material_id="glass"):
    return {"type": "primitive", "shape": "box", "id": entity_id,
            "position": [0, 1, 0], "dimensions": [1, 1, 0.1], "material": material_id}


def response(marker_id, definitions):
    return SimpleNamespace(content=json.dumps({"implementations": [{"id": marker_id,
        "geometry": {"elements": [box(marker_id + "_panel")], "components": []},
        "materials": definitions}]}), token_usage={})


def test_rejected_resources_never_enter_accepted_parts_or_final_materials(monkeypatch):
    state = empty_state()
    glass = material(materialClass="glass", transmission=0.9, ior=1.5)
    state["skeleton_blueprint"]["materials"]["glass"] = glass
    before = deepcopy(state)
    events = patch_services(monkeypatch, [response("lattice", {"glass": {**glass, "opacity": 0.9}}),
                                        response("lattice", {})])
    updates, status, _, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and events == ["rag", "model", "model"]
    assembled = impl.implementation_blueprint({**state, **updates})
    assert assembled["materials"]["glass"] == glass
    assert all(m.get("opacity", 1) == 1 for m in assembled["materials"].values())
    assert not impl.implementation_errors(assembled)
    assert state == before
    assert "opacity" in trace[1]["errors"]["lattice"]


def test_explicit_default_opacity_does_not_force_material_retry(monkeypatch):
    state = empty_state()
    glass = material(materialClass="glass", transmission=0.9, ior=1.5)
    state["skeleton_blueprint"]["materials"]["glass"] = glass
    events = patch_services(monkeypatch, [response("lattice", {"glass": {**glass, "opacity": 1}})])
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and events == ["rag", "model"]
    assert impl.implementation_blueprint({**state, **updates})["materials"] == {"glass": glass}


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0)])
def test_parallel_fragments_can_use_distinct_materials_with_same_local_name(monkeypatch, order):
    state = empty_state()
    markers = [{"id": name, "type": name, "host": "", "depends_on": [], "design": {}}
               for name in ("panel_a", "panel_b", "panel_c")]
    state["resolved_design"]["component_markers"] = markers
    definitions = [material(roughness=v) for v in (0.1, 0.4, 0.8)]
    patch_services(monkeypatch, [response(m["id"], {"glass": v}) for m, v in zip(markers, definitions)])
    combined = deepcopy(state)
    updates_by_marker = []
    for marker in markers:
        updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state, marker["id"])))
        assert status == "succeeded"
        updates_by_marker.append(updates)
    for index in order:
        updates = updates_by_marker[index]
        for key in ("component_fragments", "component_diagnostics"):
            combined[key].update(updates[key])
    blueprint = impl.implementation_blueprint(combined)
    assert len(blueprint["materials"]) == 3
    for entity in blueprint["geometry"]["elements"]:
        intended = definitions[next(i for i, m in enumerate(markers) if entity["id"] == m["id"] + "_panel")]
        assert blueprint["materials"][entity["material"]] == intended
    assert not impl.implementation_errors(blueprint)


def test_true_material_variation_preserves_existing_appearance(monkeypatch):
    state = empty_state()
    original, intended = material(roughness=0.1), material(roughness=0.8)
    state["skeleton_blueprint"]["materials"]["glass"] = original
    events = patch_services(monkeypatch, [response("lattice", {"glass": intended})])
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and events == ["rag", "model"]
    blueprint = impl.implementation_blueprint({**state, **updates})
    assert blueprint["materials"]["glass"] == original
    entity = blueprint["geometry"]["elements"][0]
    assert entity["material"] != "glass"
    assert blueprint["materials"][entity["material"]] == intended


def test_material_binding_updates_native_and_nested_references_without_changing_geometry(monkeypatch):
    state = empty_state()
    state["skeleton_blueprint"]["materials"]["glass"] = material()
    row = {"geometry": {"elements": [{**box("panel"), "frameMaterial": "glass",
        "form": {"parts": [{"glassMaterial": "glass"}]}}]}, "materials": {"glass": material(roughness=0.8)}}
    before = deepcopy(row)
    bound, bindings = impl._bind_materials(state["skeleton_blueprint"], row, {"type": "window"})
    entity = bound["geometry"]["elements"][0]
    assert entity["material"] == entity["frameMaterial"] == entity["form"]["parts"][0]["glassMaterial"]
    assert bound["materials"][entity["material"]] == before["materials"]["glass"]
    assert entity["position"] == before["geometry"]["elements"][0]["position"]
    assert row == before and bindings["glass"] != "glass"


@pytest.mark.parametrize("invalid", [[], None, "glass"])
def test_non_object_materials_are_reported_before_adoption(invalid):
    state = empty_state()
    with pytest.raises(ValueError, match="materials 必须是对象"):
        impl._bind_materials(state["skeleton_blueprint"], {"materials": invalid}, {"type": "window"})


@pytest.mark.parametrize("resource", ["materials", "assets"])
def test_assembly_refuses_conflicting_definitions_instead_of_overwriting(resource):
    base = {"materials": {}, "assets": {}}
    base[resource]["shared"] = {"value": 1}
    before = deepcopy(base)
    with pytest.raises(ValueError, match="片段定义冲突"):
        merge_marker_resources(base, {resource: {"shared": {"value": 2}}})
    assert base == before


@pytest.mark.parametrize("floors,mode,explicit,expected", [
    (1, "full", False, 0), (2, "full", False, 1), (3, "full", False, 1),
    (2, "schematic", False, 0), (2, "full", True, 1),
])
def test_circulation_stair_is_a_plan_marker_without_invented_geometry(floors, mode, explicit, expected):
    document = drawing()
    document.decisions.massing.floors = floors
    document.decisions.massing.modeled_floors = floors
    document.decisions.massing.representation_mode = mode
    document.decisions.volumes[0].end_floor = floors
    document.decisions.circulation.vertical_strategy = "中央楼梯连接各层"
    if explicit:
        document.decisions.components = [{"id": "specified_stair", "type": "stair", "host": "main"}]
    markers = component_markers(document)
    stairs = [m for m in markers if m["type"] == "stair"]
    assert len(stairs) == expected
    if stairs and not explicit:
        assert stairs[0]["entity"] == {}
        assert stairs[0]["design"]["circulation"]["vertical_strategy"] == "中央楼梯连接各层"
        state = empty_state(document)
        body = markers[0]["design"]
        assert stairs[0]["id"] in {m["id"] for m in state["resolved_design"]["component_markers"]}
        assert not body.get("stair_position")


def test_body_leaves_stair_to_its_task_even_when_model_uses_a_body_prefixed_id(monkeypatch):
    document = drawing()
    for facade in document.decisions.facades.values():
        facade.upper_pattern = ["empty"]
    document.decisions.massing.floors = 2
    document.decisions.massing.modeled_floors = 2
    document.decisions.volumes[0].end_floor = 2
    document.decisions.circulation.vertical_strategy = "stair"
    state = empty_state(document)
    body = response("building_body", {"glass": material()})
    payload = json.loads(body.content)
    payload["implementations"][0]["geometry"]["elements"].append({"type": "stair", "id": "building_body_stair",
        "from": [1, 0, 1], "to": [7, 3, 1], "width": 1.2})
    body.content = json.dumps(payload)
    patch_services(monkeypatch, [body])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and ids == ["building_body_panel"]
    assert trace[1]["outside_item_entity_ids"] == ["building_body_stair"]


def test_stair_context_includes_actual_floors_and_circulation_without_fixed_location():
    document = drawing()
    document.decisions.massing.floors = 2
    document.decisions.massing.modeled_floors = 2
    document.decisions.volumes[0].end_floor = 2
    document.decisions.circulation.vertical_strategy = "stair"
    state = empty_state(document)
    marker = next(m for m in state["resolved_design"]["component_markers"] if m["type"] == "stair")
    base = deepcopy(state["skeleton_blueprint"])
    floor = {"type": "floor", "id": "upper", "from": [0, 2.8, 0], "to": [10, 2.8, 8], "thickness": 0.2}
    base["geometry"]["elements"] = [floor]
    context = impl._item_context(state, {marker["id"]: marker}, base)
    assert context["existing_blueprint"]["geometry"]["elements"] == [floor]
    assert context["drawing"]["volumes"] == state["design_document"]["decisions"]["volumes"]
    assert context["drawing"]["circulation"] == state["design_document"]["decisions"]["circulation"]
    assert marker["entity"] == {}


def test_derived_stair_does_not_reserve_an_id_used_by_custom_design():
    document = drawing()
    document.decisions.massing.floors = 2
    document.decisions.massing.modeled_floors = 2
    document.decisions.volumes[0].end_floor = 2
    document.decisions.circulation.vertical_strategy = "stair"
    document.decisions.components[0].id = "circulation_stair"
    markers = component_markers(document)
    assert len({m["id"] for m in markers}) == len(markers)
    assert next(m for m in markers if m["id"] == "circulation_stair")["type"] == "custom_lattice"
    assert next(m for m in markers if m["type"] == "stair")["id"] != "circulation_stair"


@pytest.mark.parametrize("alias,family", [("glazing", "window"), ("entrance", "door")])
def test_facade_alias_does_not_duplicate_an_explicit_opening(alias, family):
    document = drawing()
    document.decisions.facades["front"].ground_pattern = [alias]
    document.decisions.components = [{"id": "explicit_opening",
        "type": family, "host": "wall_main_front_L1", "size": {"width": 2, "height": 2},
        "placement": {"offset": 4, "sill_height": 0.5}}]
    markers = component_markers(document)
    assert [m["id"] for m in markers if m["host"] == "wall_main_front_L1"] == ["explicit_opening"]


@pytest.mark.parametrize("offset,axis", [(0, 0), (-30, 0), (20, 2)])
def test_small_roof_support_does_not_include_columns_from_neighboring_volume(offset, axis):
    def point(x, y, z):
        return [x+offset, y, z+offset] if axis == 0 else [z+offset, y, x+offset]
    walls = [{"id": f"wall_{i}", "type": "wall", "from": point(x, 3.5, z),
              "to": point(xx, 7, zz), "thickness": 0.24}
             for i, (x, z, xx, zz) in enumerate([(0, 0, 12, 0), (0, 10, 12, 10),
                (0, 12, 12, 12), (0, 10, 0, 12), (12, 10, 12, 12)])]
    columns = [{"id": f"column_{i}", "type": "column", "base": point(x, 0, z),
                "height": 7, "bottomRadius": 0.2, "topRadius": 0.2}
               for i, (x, z) in enumerate([(0, 0), (12, 0), (0, 10), (12, 10)])]
    roof = {"id": "local_roof", "type": "roof", "roofType": "flat", "span": 12 if axis == 0 else 2,
            "depth": 2 if axis == 0 else 12, "position": point(6, 7, 11), "height": 0.2, "thickness": 0.2}
    bounds = get_roof_support_bounds(walls, roof, columns=columns)
    assert (bounds["depth"] if axis == 0 else bounds["span"]) == pytest.approx(2.2)
    output = getattr(validate_roof_coverage, "func", validate_roof_coverage)(
        {"geometry": {"elements": [*walls, *columns, roof], "components": []}})
    assert "❌" not in output
