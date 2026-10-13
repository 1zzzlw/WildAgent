"""SVG projects compiled entities; it must not invent tapering or drop real openings."""

import pytest
from pydantic import ValidationError

from app.design.contracts import DesignDocument
from app.design.resolver import (
    architecture_plan_from_document,
    build_design_document,
    render_design_svg,
    resolve_design,
)


def base_plan(**massing_extra) -> dict:
    plan = {
        "schema_version": "1.1",
        "profile": "ordinary_public",
        "concept": "收分电视塔",
        "massing": {
            "shape": "rectangle",
            "width": 20,
            "depth": 20,
            "floors": 4,
            "modeled_floors": 4,
            "representation_mode": "full",
            "floor_height": 4,
            "symmetry": True,
        },
        "complexity": {
            "level": "standard",
            "min_volumes": 1,
            "min_detail_packages": 0,
            "target_structural_elements": 10,
            "grid_bays": [2, 2],
            "reason": "test",
        },
        "volumes": [{
            "id": "main",
            "role": "primary",
            "x": 0,
            "z": 0,
            "width": 20,
            "depth": 20,
            "start_floor": 1,
            "end_floor": 4,
        }],
        "structural_grid": {"system": "frame", "x_bays": 4, "z_bays": 4},
        "detail_packages": [],
        "facades": {
            "front": {
                "bays": 4,
                "ground_pattern": ["window", "door", "window", "window"],
                "upper_pattern": ["window"] * 4,
            },
            "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
            "left": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
            "right": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
        },
        "roof": {"type": "flat", "ridge_axis": "x", "overhang": 0},
        "component_quota": {},
        "curtain_wall": False,
        "balcony_access_count": 0,
        "balcony_width": None,
        "required_components": ["door", "window"],
        "unsupported_component_types": [],
        "design_rationale": [],
    }
    plan["massing"].update(massing_extra)
    return plan


def make_document(plan: dict) -> DesignDocument:
    return build_design_document(
        plan,
        session_id="session_svg_test",
        source_request="生成一座收分电视塔",
        building_type="tower",
    )


def test_plain_rectangle_flat_roof_keeps_rect_and_all_anchors():
    svg = render_design_svg(make_document(base_plan()))

    assert svg.startswith("<svg")
    assert 'data-design-path="/decisions/massing"' in svg
    assert 'data-design-path="/decisions/volumes/0"' in svg
    assert 'data-design-path="/decisions/facades/front"' in svg
    # 满幅矩形 + 平屋顶：轮廓走 rect 分支，不引入任何 polygon/path。
    assert "<polygon" not in svg
    assert "<path" not in svg
    # 尺寸标注与地平线。
    assert "20.0 m" in svg


@pytest.mark.parametrize("shape", ["rectangle", "tower"])
def test_shape_projection_contains_actual_compiled_walls(shape):
    from xml.etree import ElementTree as ET
    doc = make_document(base_plan(shape=shape))
    resolved = resolve_design(doc)
    root = ET.fromstring(render_design_svg(doc, resolved))
    shown = {e.get("data-entity-id") for e in root.iter()}
    walls = {e["id"] for e in resolved.projection_elements if e["type"] == "wall"}
    assert walls
    assert walls <= shown


def test_tiers_do_not_filter_out_real_compiled_openings():
    from xml.etree import ElementTree as ET
    doc = make_document(base_plan(tiers=[
        {"floors":2,"width_ratio":1.0,"depth_ratio":1.0},
        {"floors":2,"width_ratio":0.6,"depth_ratio":0.6},
    ]))
    resolved = resolve_design(doc)
    root = ET.fromstring(render_design_svg(doc, resolved))
    shown = {e.get("data-slot-id") for e in root.iter() if e.get("data-slot-id")}
    assert shown == {s.id for s in resolved.facade_slots if s.facing in {"front","left"}}


@pytest.mark.parametrize("roof_type", ["flat","gable","hip","dome","chinese_curved","chinese_pagoda"])
def test_floor_plan_lists_roof_markers_without_covering_rooms(roof_type):
    from xml.etree import ElementTree as ET
    plan = base_plan()
    plan["roof"] = {"type":roof_type,"ridge_axis":"x","overhang":0.5}
    plan["component_quota"]["roof"] = {"min":1}
    plan["required_components"].append("roof")
    doc = make_document(plan)
    resolved = resolve_design(doc)
    root = ET.fromstring(render_design_svg(doc,resolved))
    shown = {e.get("data-marker-id") for e in root.iter()}
    assert {m["id"] for m in resolved.component_markers if m["type"]=="roof"} <= shown
    assert "屋面不覆盖平面剖切图" in render_design_svg(doc, resolved)


def test_tiers_sum_must_equal_floors():
    plan = base_plan(tiers=[{"floors": 2, "width_ratio": 1.0}, {"floors": 1, "width_ratio": 0.6}])
    with pytest.raises(ValidationError, match="floors 之和"):
        make_document(plan)


def test_tiers_flow_through_architecture_plan():
    document = make_document(base_plan(
        tiers=[
            {"floors": 3, "width_ratio": 1.0},
            {"floors": 1, "width_ratio": 0.55},
        ],
    ))
    plan = architecture_plan_from_document(document)

    assert plan["massing"]["tiers"] == [
        {"floors": 3, "width_ratio": 1.0, "depth_ratio": 1.0},
        {"floors": 1, "width_ratio": 0.55, "depth_ratio": 1.0},
    ]


def test_schematic_tower_keeps_full_height_projection():
    plan = base_plan(
        shape="tower",
        floors=30,
        modeled_floors=10,
        representation_mode="schematic",
    )
    plan["volumes"][0]["end_floor"] = 10
    svg = render_design_svg(make_document(plan))

    # schematic 代表层铺到全高：高度标注必须是 120.0 m（30 × 4），不是 40。
    assert "120.0 m" in svg


@pytest.mark.parametrize("origin", [(0, 0), (-30, 70)])
def test_floor_selection_keeps_world_coordinates_and_draws_declared_rooms_and_partition_openings(origin):
    from xml.etree import ElementTree as ET
    x, z = origin
    plan = base_plan()
    plan["volumes"][0].update(x=x, z=z)
    plan["floor_layouts"] = [{"floor": 2, "level": 3.9,
        "rooms": [{"id": "study", "name": "书房<&>", "bounds": {"x": x, "z": z, "width": 7, "depth": 8}},
                  {"id": "void", "name": "客厅上空", "void": True,
                   "bounds": {"x": x+7, "z": z, "width": 4, "depth": 8}}],
        "walls": [{"id": "partition", "from": [x+7, z], "to": [x+7, z+8], "thickness": 0.15}]}]
    plan["components"] = [{"id": "study_door", "type": "door", "host": "partition",
        "placement": {"offset": 2, "sill_height": 0}, "size": {"width": 1, "height": 2.1},
        "form": {"hinge": "start", "swing_side": "left"}}]
    doc = make_document(plan)
    before = doc.model_dump(mode="json")
    resolved = resolve_design(doc)
    partition = next(w for w in resolved.projection_elements if w["id"] == "partition")
    assert partition["from"] == [x+7, 3.9, z]
    assert partition["to"] == [x+7, 8, z+8]
    opening = next(m for m in resolved.component_markers if m["id"] == "study_door")
    assert opening["entity"]["from"] == [2, 3.9, 0]
    svg = render_design_svg(doc, resolved, floor=2)
    root = ET.fromstring(svg)
    assert [e.get("data-floor") for e in root.iter() if e.get("data-floor")] == ["2"]
    assert {e.get("data-room-id") for e in root.iter()} >= {"study", "void"}
    assert "base 3.900" in svg and "书房&lt;&amp;&gt;" in svg and "<path" in svg
    assert "study_door" not in render_design_svg(doc, resolved, floor=1)
    assert doc.model_dump(mode="json") == before


def test_missing_room_or_opening_size_is_not_invented_and_absent_floor_is_rejected():
    doc = make_document(base_plan())
    svg = render_design_svg(doc, floor=1)
    assert "本层尚未提供房间分区" in svg and "<path" not in svg
    assert "点标记" in svg
    with pytest.raises(ValueError, match="没有第 9 层"):
        render_design_svg(doc, floor=9)


@pytest.mark.parametrize("layouts,path", [("一层平面", "/floor_layouts"), (["房间"], "/floor_layouts/0"),
                                         ([{"floor": 1, "rooms": ["卧室"]}], "/floor_layouts/0/rooms")])
def test_invalid_layout_structure_has_field_feedback_instead_of_a_preview_crash(layouts, path):
    plan = base_plan()
    plan["floor_layouts"] = layouts
    with pytest.raises(ValueError, match=path):
        render_design_svg(make_document(plan))


@pytest.mark.asyncio
async def test_floor_preview_api_returns_selected_sheet_and_field_error_for_absent_floor(monkeypatch):
    from fastapi import HTTPException
    from app.api import designs
    doc = make_document(base_plan())
    monkeypatch.setattr(designs.design_repository, "get", lambda _session: doc)
    response = await designs.get_design_preview(doc.session_id, revision=doc.revision, floor=2)
    assert response.media_type == "image/svg+xml"
    assert b'data-floor="2"' in response.body and b'data-floor="1"' not in response.body
    with pytest.raises(HTTPException) as caught:
        await designs.get_design_preview(doc.session_id, floor=9)
    assert caught.value.status_code == 422 and "没有第 9 层" in caught.value.detail
