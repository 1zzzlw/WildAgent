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
def test_roof_projection_uses_compiled_entities(roof_type):
    from xml.etree import ElementTree as ET
    plan = base_plan()
    plan["roof"] = {"type":roof_type,"ridge_axis":"x","overhang":0.5}
    plan["component_quota"]["roof"] = {"min":1}
    plan["required_components"].append("roof")
    doc = make_document(plan)
    resolved = resolve_design(doc)
    root = ET.fromstring(render_design_svg(doc,resolved))
    shown = {e.get("data-entity-id") for e in root.iter() if e.get("data-design-path")=="/decisions/roof"}
    assert shown == {e["id"] for e in resolved.projection_elements if e["type"]=="roof"}


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
