"""Review/compile parity and post-merge drift. Run by the project owner."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.design.compilation import compile_document, opening_drift, RESOLVER_VERSION
from app.design.resolver import build_design_document, resolve_design, render_design_svg


def document():
    plan = json.loads((Path(__file__).parents[1]/"fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    return build_design_document(plan, session_id="parity", source_request="生成一个别墅")


def test_review_uses_actual_compiled_openings_and_wall_elevations():
    doc = document()
    resolved = resolve_design(doc)
    result = compile_document(doc)
    assert resolved.resolver_version == RESOLVER_VERSION
    entities = {c["id"]:c for c in result.blueprint["geometry"]["components"] if c["type"] in {"door","window","bay_window"}}
    walls = {e["id"]:e for e in result.blueprint["geometry"]["elements"] if e["type"]=="wall"}
    assert {s.id for s in resolved.facade_slots} == set(entities)
    for slot in resolved.facade_slots:
        item = entities[slot.id]
        assert (slot.width, slot.height, slot.parent_wall, slot.local_from) == (item["width"],item["height"],item["parentWall"],item["from"])
        wall = walls[slot.parent_wall]
        assert min(wall["from"][1],wall["to"][1]) <= slot.bottom < max(wall["from"][1],wall["to"][1])
    assert opening_drift(resolved, result.blueprint) == []
    assert resolved.model_dump() == resolve_design(doc).model_dump()


@pytest.mark.parametrize("change", ["width", "parentWall", "from", "missing", "host_moved"])
def test_final_drift_detects_changes_even_when_blueprint_is_valid(change):
    doc = document()
    resolved = resolve_design(doc)
    blueprint = deepcopy(compile_document(doc).blueprint)
    components = blueprint["geometry"]["components"]
    index = next(i for i,c in enumerate(components) if c["id"] == resolved.facade_slots[0].id)
    if change == "host_moved":
        wall = next(e for e in blueprint["geometry"]["elements"] if e["id"]==components[index]["parentWall"])
        wall["from"][0] += 0.5
        wall["to"][0] += 0.5
    elif change == "missing":
        components.pop(index)
    elif change == "width":
        components[index][change] += 0.2
    elif change == "parentWall":
        components[index][change] = "different_wall"
    else:
        components[index][change][0] += 0.2
    assert opening_drift(resolved, blueprint)


def test_stale_or_legacy_resolved_view_is_not_rendered():
    doc = document()
    old = resolve_design(doc)
    old.facade_slots[0].id = "stale-sentinel"
    old.resolver_version = "legacy"
    assert "stale-sentinel" not in render_design_svg(doc, old)
    old = resolve_design(doc)
    changed = doc.model_copy(update={"revision": doc.revision+1})
    svg = render_design_svg(changed, old)
    assert f"DesignDocument r{changed.revision}" in svg


@pytest.mark.parametrize("facing,axis", [("front", 0), ("left", 2)])
def test_svg_opening_width_uses_world_projection(facing, axis):
    from xml.etree import ElementTree
    from app.design.preview import render_compiled_svg

    doc = document()
    resolved = resolve_design(doc)
    slot = resolved.facade_slots[0]
    slot.facing = facing
    slot.world_from = [0, slot.bottom, 0]
    slot.world_to = [slot.width, slot.bottom, slot.width]
    resolved.facade_slots = [slot]

    def width():
        root = ElementTree.fromstring(render_compiled_svg(doc, resolved))
        rect = next(e for e in root.iter() if e.get("data-slot-id") == slot.id)
        return float(rect.get("width"))

    straight_width = width()
    slot.world_to[axis] *= 0.6
    assert width() == pytest.approx(straight_width * 0.6, abs=0.02)
