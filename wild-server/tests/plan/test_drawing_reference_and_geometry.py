"""参考目录不限制设计；定位与共面问题在各粒度共用入口检查。"""
import pytest
import json
from types import SimpleNamespace

from app.agent.knowledge import component_names as naming
from app.agent.plan import implementation as impl
from app.agent.prompts.planning import build_architecture_plan_prompt
from app.design.contracts import ComponentInstance
from app.design.markers import component_markers
from app.tools.spatial_tools import validate_model_quality, validate_element_dimensions
from tests.plan.test_drawing_integration import drawing


def test_reference_catalog_contains_sources_and_preserves_unknown_components():
    text = naming.component_reference_prompt()
    assert "stair.md" in text and "chinese-lattice-openings.md" in text
    assert "非白名单" in text
    assert all(f"{kind}=" in text for kind in ("wall", "floor", "beam"))
    assert naming.resolve_component_name("new_twisted_canopy")["kind"] == "new_twisted_canopy"
    assert text in build_architecture_plan_prompt("")


def test_generated_catalog_is_navigation_and_matches_live_metadata():
    from app.spec.loader import MarkdownChunker
    from pathlib import Path
    root = Path(__file__).parents[2] / "storage/knowledge_base"
    path = root / "knowledge/components/component-catalog.md"
    assert path.read_text(encoding="utf-8") == naming.component_catalog_document()
    chunks = MarkdownChunker(metadata_config_path=root / "config.yaml").split_file(path, namespace="catalog_test")
    assert chunks and all(c.metadata["knowledge_role"] == "navigation" for c in chunks)


@pytest.mark.parametrize("face,offset", [("front", 0), ("back", -12), ("right", 25), ("left", 0)])
def test_volume_local_opening_selects_wall_and_floor_without_duplicate_bay(face, offset):
    document = drawing()
    volume = document.decisions.volumes[0]
    volume.x += offset
    volume.z += offset
    document.decisions.components = [ComponentInstance(id="explicit_window", type="chinese_lattice_window", host="main",
        placement={"face": face, "floor": 2, "offset": 3.0, "sill_height": 1.0}, size={"width": 1.5, "height": 1.5})]
    before = document.model_dump(mode="json")
    markers = component_markers(document)
    explicit = next(m for m in markers if m["id"] == "explicit_window")
    assert explicit["host"] == f"wall_main_{face}_L2"
    assert explicit["entity"]["from"] == [3.0, 4.0, 0]
    assert f"window_main_{face}_L2_2" not in {m["id"] for m in markers}
    assert document.model_dump(mode="json") == before


def structure(kind, thickness, offset):
    wall = {"type": "wall", "id": "host_wall", "from": [offset, 0, 0], "to": [offset+10, 3, 0],
            "thickness": 0.2, "material": "plaster"}
    member = ({"type": "beam", "id": "frame", "from": [offset, 2.5, 0], "to": [offset+10, 2.5, 0],
               "width": thickness, "height": 0.3, "crossSection": "rect", "material": "timber"} if kind == "beam" else
              {"type": "primitive", "id": "frame", "shape": "box", "position": [offset+5, 1.5, 0],
               "dimensions": [0.3, 3, thickness], "material": "timber"})
    return {"geometry": {"elements": [wall, member], "components": []}}


@pytest.mark.parametrize("kind,offset", [("beam", 0), ("beam", -20), ("box", 25)])
def test_coplanar_frame_surfaces_are_rejected_but_inset_and_exposed_frames_are_valid(kind, offset):
    assert "共面" in validate_model_quality.func(structure(kind, 0.2, offset))
    assert "❌" not in validate_model_quality.func(structure(kind, 0.16, offset))
    assert "❌" not in validate_model_quality.func(structure(kind, 0.24, offset))


def test_mullion_width_that_closes_clear_cell_is_local_error():
    bp = {"geometry": {"elements": [], "components": [{"type": "window", "id": "dense_window",
        "parentWall": "wall", "from": [1, 1, 0], "width": 1.8, "height": 1.6,
        "frameWidth": 0.09, "verticalMullions": 15, "horizontalMullions": 13, "mullionWidth": 0.12}]}}
    assert "mullionWidth" in validate_element_dimensions.func(bp)
    bp["geometry"]["components"][0]["mullionWidth"] = 0.02
    assert "❌" not in validate_element_dimensions.func(bp)


@pytest.mark.parametrize("axis", [0, 2])
@pytest.mark.parametrize("offset", [-25, 0, 13])
def test_coplanar_check_works_for_both_wall_directions_and_translations(axis, offset):
    bp = structure("beam", 0.2, offset)
    if axis == 2:
        for e in bp["geometry"]["elements"]:
            for key in ("from", "to"):
                e[key][0], e[key][2] = e[key][2], e[key][0]
    assert "共面" in validate_model_quality.func(bp)


def test_diagonal_and_rotated_members_are_not_guessed_by_coplanar_check():
    bp = structure("box", 0.2, 0)
    bp["geometry"]["elements"][1]["rotation"] = [0, 0.3, 0]
    assert "❌" not in validate_model_quality.func(bp)
    bp = structure("beam", 0.2, 0)
    bp["geometry"]["elements"][1]["to"][2] = 3
    assert "❌" not in validate_model_quality.func(bp)


@pytest.mark.parametrize("field,value", [("frameWidth", 0.9), ("frameWidth", None), ("verticalMullions", 1.5)])
def test_invalid_window_dimensions_report_errors_without_breaking_validation(field, value):
    bp = {"geometry": {"elements": [], "components": [{"type": "window", "id": "invalid_window",
        "parentWall": "wall", "from": [1, 1, 0], "width": 1.8, "height": 1.6, field: value}]}}
    assert "❌" in validate_element_dimensions.func(bp)


def test_body_quality_validator_is_also_in_fragment_acceptance():
    bp = structure("beam", 0.2, 0)
    base = {"meta": {"version": "1.1", "type": "building", "name": "coplanar"},
        "geometry": {"elements": [], "components": []}, "materials": {}, "assets": {}}
    for entity in bp["geometry"]["elements"]:
        entity.pop("material")
    with pytest.raises(ValueError, match="共面"):
        impl._accept_group(base, {"geometry": bp["geometry"]}, {"type": "building_body", "design": {}})


def test_automatic_window_marker_distinguishes_bay_center_from_opening_start():
    markers = component_markers(drawing())
    lattice = next(m for m in markers if m["id"] == "chinese_lattice_window_annex_front_L1_2")
    assert lattice["entity"] == {"parentWall": "wall_annex_front_L1", "centerAlong": 1.5, "bottomY": 1}
    assert "from" not in lattice["entity"]


def test_named_variant_cannot_silently_change_explicit_size():
    base = {"meta": {"version": "1.1", "type": "building", "name": "size"}, "materials": {}, "assets": {},
        "geometry": {"elements": [{"type": "wall", "id": "wall", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}],
                     "components": []}}
    row = {"geometry": {"components": [{"type": "window", "id": "lattice", "parentWall": "wall",
                                        "from": [1, 1, 0], "width": 1.8, "height": 1.4}]}}
    with pytest.raises(ValueError, match="设计尺寸 height"):
        impl._accept_group(base, row, {"type": "chinese_lattice_window", "design": {"size": {"height": 1.6}}})


def test_window_context_includes_real_body_frame_members():
    document = drawing()
    marker = next(m for m in component_markers(document) if m["id"] == "window_main_front_L2_3")
    base = structure("beam", 0.24, 0)
    base["geometry"]["elements"][0]["id"] = marker["host"]
    state = {"design_document": document.model_dump(mode="json"), "component_fragments": {},
        "component_diagnostics": {"body": {"implementations": {"building_body": {"entity_ids": [marker["host"], "frame"]}}}}}
    context = impl._item_context(state, {marker["id"]: marker}, base)
    assert {e["id"] for e in context["existing_blueprint"]["geometry"]["elements"]} == {marker["host"], "frame"}


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed"])
async def test_missing_opening_location_is_revised_in_drawing_at_every_detail_level(level, monkeypatch):
    from app.agent.generation.architecture import design_workflow
    from app.agent.generation.architecture.workflow import architecture_planner
    from app.utils.json_extractor import extract_json_object
    raw = extract_json_object(build_architecture_plan_prompt(""))
    raw["components"] = [{"type": "chinese_lattice_window", "id": "lattice", "host": "main",
                          "placement": {"offset": 3, "sill_height": 1}, "size": {"width": 1.5, "height": 1.5}}]
    calls = []
    async def model(_llm, messages):
        calls.append(messages)
        if len(calls) == 2:
            raw["components"][0]["placement"].update(face="front", floor=2)
        return SimpleNamespace(content=json.dumps(raw), token_usage=None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kw: None)
    result = await architecture_planner({"user_message": "生成别墅", "session_id": "locations", "detail_level": level})
    assert not result.get("error"), result
    assert len(calls) == 2 and "/components/0/placement" in calls[1][0]["content"]
    doc = result["design_document"]
    from app.design.contracts import DesignDocument
    lattice = next(m for m in component_markers(DesignDocument.model_validate(doc)) if m["id"] == "lattice")
    assert lattice["host"] == "wall_main_front_L2" and lattice["entity"]["from"] == [3, 4, 0]

