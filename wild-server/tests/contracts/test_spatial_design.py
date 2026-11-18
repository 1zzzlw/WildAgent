"""空间协议回归：真实轮廓、宿主、放样与现有执行入口，不调用模型或浏览器。"""

from copy import deepcopy
from math import pi

import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon

from app.domain.design.compilation import compile_document
from app.domain.design.contracts import DesignDocument, architecture_output_schema
from app.domain.design.coordinates import DesignCoordinateConflict
from app.domain.design.preview import render_drawing_svg
from app.domain.design.resolver import (
    architecture_plan_from_document,
    build_design_document,
    resolve_design,
)
from app.domain.design.spatial import host_point, resolve_geometry


def spatial_plan(kind="rectangle"):
    profile = {"id": "outline", "type": "rectangle", "width": 10, "depth": 8}
    if kind == "circle":
        profile = {"id": "outline", "type": "circle", "radius": 5}
    edges = ["perimeter"] if kind == "circle" else ["front", "right", "back", "left"]
    return {
        "concept": "空间协议回归",
        "massing": {
            "shape": kind,
            "width": 20,
            "depth": 20,
            "floors": 1,
            "modeled_floors": 1,
            "floor_height": 3,
        },
        "levels": [
            {"id": "L1", "kind": "storey", "index": 1, "elevation": 1.2},
            {"id": "RF", "kind": "roof", "elevation": 4.2},
        ],
        "profiles": [profile],
        "systems": {
            "wall": {"kind": "wall", "thickness": 0.2, "material_role": "stone"},
            "slab": {"kind": "slab", "thickness": 0.2, "material_role": "floor"},
        },
        "volumes": [
            {
                "id": "main",
                "placement": {"origin_xz": [4, -2], "yaw": 0},
                "geometry": {
                    "type": "extrusion",
                    "profile": "outline",
                    "bottom": {"level": "L1"},
                    "top": {"level": "RF"},
                },
            }
        ],
        "walls": [
            {
                "id": "wall_" + edge,
                "system": "wall",
                "role": "exterior",
                "geometry": {
                    "type": "volume_boundary",
                    "volume": "main",
                    "edge": edge,
                    "bottom": {"level": "L1"},
                    "top": {"level": "RF"},
                },
            }
            for edge in edges
        ],
        "slabs": [
            {
                "id": "slab_L1",
                "system": "slab",
                "top": {"level": "L1"},
                "region": {
                    "type": "volume_union_section",
                    "volumes": ["main"],
                    "level": "L1",
                },
            }
        ],
        "materials": {
            "roles": {
                "stone": {"base_role": "facade_primary", "description": "浅色石材"}
            }
        },
        "components": [],
        "roofs": [],
    }


def document(plan):
    return build_design_document(
        plan, session_id="spatial", source_request="生成指定轮廓建筑"
    )


@pytest.mark.parametrize("kind", ["rectangle", "circle"])
def test_contract_projection_compile_and_svg_share_real_geometry(kind):
    plan = spatial_plan(kind)
    before = deepcopy(plan)
    doc = document(plan)
    resolved = resolve_design(doc)
    compiled = compile_document(doc)
    assert compiled.ok, [error.to_dict() for error in compiled.defects]
    assert not compiled.uncompiled
    assert doc.schema_version == "design/1.0"
    assert (
        DesignDocument.model_validate_json(doc.model_dump_json()).decisions
        == doc.decisions
    )
    assert architecture_plan_from_document(doc)["profiles"][0]["type"] == kind
    assert compiled.blueprint["geometry"]["elements"][0]["material"] == "material_stone"
    assert 'data-volume-id="main"' in render_drawing_svg(doc, resolved)
    assert plan == before
    if kind == "circle":
        assert resolved.bounds["width"] == pytest.approx(10, abs=0.001)
        assert resolved.bounds["depth"] == pytest.approx(10, abs=0.001)
        host = resolved.logical_hosts[0]
        assert host_point(host, host["length"] / 4, 2.2) == pytest.approx(
            [4, 2.2, -7], abs=0.001
        )


def test_rotated_wall_position_comes_from_host_local_coordinates():
    plan = spatial_plan()
    plan["volumes"][0]["placement"]["yaw"] = pi / 2
    plan["components"] = [
        {
            "id": "window",
            "type": "window",
            "host": "wall_front",
            "size": {"width": 1.2, "height": 1.4},
            "placement": {
                "mode": "wall",
                "anchor": "bottom_left",
                "offset": 2,
                "elevation": {"level": "L1", "offset": 0.8},
            },
        }
    ]
    resolved = resolve_design(document(plan))
    marker = next(item for item in resolved.component_markers if item["id"] == "window")
    assert marker["entity"]["from"] == pytest.approx([2, 2, 0])
    assert marker["entity"]["position_hint"] == pytest.approx([0, 2, 1])


def test_loft_generates_sloping_walls_and_reports_opening_limit():
    plan = spatial_plan()
    plan["volumes"][0]["geometry"] = {
        "type": "section_loft",
        "sections": [
            {"profile": "outline", "at": {"level": "L1"}},
            {
                "profile": "outline",
                "at": {"level": "RF"},
                "offset_xz": [1, 0],
                "yaw": 0.12,
                "scale": [0.8, 0.8],
            },
        ],
    }
    resolved = resolve_design(document(plan))
    assert all(
        item["type"] == "solid"
        for item in resolved.body_geometry["elements"]
        if item["id"].startswith("wall_")
    )
    assert compile_document(document(plan)).ok
    plan["components"] = [
        {
            "id": "window",
            "type": "window",
            "host": "wall_front",
            "size": {"width": 1, "height": 1},
            "placement": {
                "mode": "wall",
                "anchor": "bottom_left",
                "offset": 2,
                "elevation": {"level": "L1", "offset": 1},
            },
        }
    ]
    assert any(
        gap["code"] == "varying_wall_opening"
        for gap in resolve_design(document(plan)).capability_gaps
    )
    assert not compile_document(document(plan)).ok


def test_profile_hole_and_explicit_void_both_survive_floor_compilation():
    plan = spatial_plan()
    plan["profiles"].extend(
        [
            {"id": "courtyard", "type": "rectangle", "width": 2, "depth": 2},
            {"id": "stair_cut", "type": "circle", "radius": 0.5},
        ]
    )
    plan["profiles"][0]["holes"] = ["courtyard"]
    plan["voids"] = [
        {
            "id": "stair_void",
            "level": "L1",
            "region": {
                "type": "profile_region",
                "profile": "stair_cut",
                "origin_xz": [7, -2],
            },
        }
    ]
    plan["slabs"][0]["holes"] = ["stair_void"]
    floor = resolve_geometry(document(plan).decisions.model_dump(mode="json"))["slabs"][
        0
    ]
    assert len(floor["holes"]) == 2
    assert Polygon(floor["outer"], floor["holes"]).area == pytest.approx(
        80 - 4 - pi * 0.25, abs=0.002
    )


@pytest.mark.parametrize(
    "mutation", ["missing_profile", "duplicate_id", "invalid_wall", "self_intersection"]
)
def test_invalid_geometry_and_references_are_rejected(mutation):
    plan = spatial_plan()
    if mutation == "missing_profile":
        plan["volumes"][0]["geometry"]["profile"] = "missing"
    elif mutation == "duplicate_id":
        plan["levels"][1]["id"] = "main"
    elif mutation == "invalid_wall":
        plan["walls"][0]["geometry"]["edge"] = "missing"
    else:
        plan["profiles"][0] = {
            "id": "outline",
            "type": "polygon",
            "vertices": [
                {"id": str(i), "point": p}
                for i, p in enumerate([[0, 0], [4, 4], [0, 4], [4, 0]])
            ],
            "edges": [
                {"id": str(i), "from": str(i), "to": str((i + 1) % 4)} for i in range(4)
            ],
        }
    with pytest.raises((ValidationError, DesignCoordinateConflict)):
        document(plan)


def test_prompt_schema_omits_history_and_keeps_field_descriptions():
    schema = architecture_output_schema()
    assert "facades" not in schema["properties"]
    assert "x" not in schema["$defs"]["VolumeDecision"]["properties"]
    assert schema["properties"]["walls"]["description"]
    assert schema["$defs"]["ComponentPlacement"]["properties"]["elevation"][
        "description"
    ]


@pytest.mark.parametrize("kind", ["rectangle", "circle", "loft"])
def test_deterministic_body_is_accepted_by_existing_fragment_entry(kind):
    from app.agent.workflows.planning.implementation import _accept_fragment
    from app.domain.blueprint.materials.plan import resolve_material_plan
    from app.domain.design.resolver import attach_material_plan
    from app.domain.design.construction_systems import construct_system

    plan = spatial_plan("circle" if kind == "circle" else "rectangle")
    if kind == "loft":
        plan["volumes"][0]["geometry"] = {
            "type": "section_loft",
            "sections": [
                {"at": {"level": "L1"}, "profile": "outline"},
                {
                    "at": {"level": "RF"},
                    "profile": "outline",
                    "offset_xz": [1, 0],
                    "yaw": 0.1,
                },
            ],
        }
    materials = resolve_material_plan(None, [], plan)
    doc = attach_material_plan(document(plan), materials)
    resolved = resolve_design(doc)
    base = {
        "meta": {"version": "1.0", "type": "building", "name": "回归"},
        "geometry": {"elements": [], "components": []},
        "assets": {},
        "materials": {
            role["materialId"]: role["material"] for role in materials["roles"]
        },
    }
    marker = resolved.component_markers[0]
    candidate, accepted, rejected, record = _accept_fragment(
        base,
        construct_system(marker, base),
        marker,
        dependent_markers=resolved.component_markers,
        diagram_hosts=resolved.logical_hosts,
    )
    assert rejected is None, rejected
    assert record and accepted and candidate["geometry"]["elements"]


def test_polygon_and_bezier_walls_keep_real_outline():
    plan = spatial_plan()
    points = [[-5, -4], [5, -4], [5, 0], [0, 0], [0, 4], [-5, 4]]
    plan["profiles"][0] = {
        "id": "outline",
        "type": "polygon",
        "vertices": [{"id": f"v{i}", "point": point} for i, point in enumerate(points)],
        "edges": [
            {"id": f"edge{i}", "from": f"v{i}", "to": f"v{(i + 1) % len(points)}"}
            for i in range(len(points))
        ],
    }
    plan["walls"] = []
    region = resolve_geometry(document(plan).decisions.model_dump(mode="json"))[
        "slabs"
    ][0]
    assert Polygon(region["outer"]).area == pytest.approx(60)
    plan["profiles"][0] = {
        "id": "outline",
        "type": "curve_loop",
        "segments": [
            {
                "id": "curve",
                "type": "cubic_bezier",
                "points": [[-5, -4], [-2, -6], [2, -6], [5, -4]],
            },
            {"id": "right", "type": "line", "from": [5, -4], "to": [5, 4]},
            {"id": "back", "type": "line", "from": [5, 4], "to": [-5, 4]},
            {"id": "left", "type": "line", "from": [-5, 4], "to": [-5, -4]},
        ],
    }
    plan["walls"] = [
        {
            "id": "curved_wall",
            "role": "exterior",
            "system": "wall",
            "geometry": {
                "type": "volume_boundary",
                "volume": "main",
                "edge": "curve",
                "bottom": {"level": "L1"},
                "top": {"level": "RF"},
            },
        }
    ]
    result = compile_document(document(plan))
    assert result.ok
    assert result.blueprint["geometry"]["elements"][0]["kind"] == "loft"


def test_union_schema_and_room_relations_survive_projection():
    from app.domain.design.completeness import path_schema

    plan = spatial_plan("circle")
    plan["floor_layouts"] = [
        {
            "level": "L1",
            "rooms": [
                {
                    "id": "hall",
                    "name": "大厅",
                    "region": {
                        "type": "volume_union_section",
                        "volumes": ["main"],
                        "level": "L1",
                    },
                }
            ],
        }
    ]
    plan["relations"] = [
        {"id": "alignment", "type": "aligned", "subject": "main", "target": "hall"}
    ]
    plan["circulation"] = {
        "required_connections": [{"from": "L1", "to": "hall"}],
        "clearance_paths": [
            {
                "id": "path",
                "level": "L1",
                "points": [[3, -2], [5, -2]],
                "width": 1.2,
                "height": 2.2,
            }
        ],
    }
    doc = document(plan)
    assert path_schema(doc, "/decisions/profiles/0/radius")["type"] == "number"
    assert path_schema(doc, "/decisions/volumes/0/geometry/profile")["type"] == "string"
    resolved = resolve_design(doc)
    assert any(
        gap.target == "alignment" and gap.status == "needs_review"
        for gap in resolved.design_gaps
    )
    assert any(gap.target == "path" for gap in resolved.design_gaps)


def test_round_wall_opening_placement_and_validation_share_local_frame():
    from app.domain.design.relations import opening_design_errors, place_opening_group

    plan = spatial_plan("circle")
    plan["components"] = [
        {
            "id": "window",
            "type": "window",
            "host": "wall_perimeter",
            "size": {"width": 1.2, "height": 1.4},
            "placement": {
                "mode": "wall",
                "anchor": "bottom_left",
                "offset": 2,
                "elevation": {"level": "L1", "offset": 0.8},
            },
        }
    ]
    resolved = resolve_design(document(plan))
    marker = resolved.component_markers[1]
    base = {"geometry": resolved.body_geometry, "materials": {}}
    row = {
        "geometry": {
            "components": [
                {
                    "id": "native_window",
                    "type": "window",
                    "parentWall": "wall_perimeter",
                    "from": [0, 1.2, 0],
                    "width": 1.2,
                    "height": 1.4,
                }
            ]
        }
    }
    assert opening_design_errors(base, row["geometry"]["components"], marker)
    fixed, changes = place_opening_group(base, row, marker)
    assert changes
    assert fixed["geometry"]["components"][0]["from"] == pytest.approx([2, 2, 0])
    assert not opening_design_errors(base, fixed["geometry"]["components"], marker)


def test_roof_does_not_fill_a_designed_courtyard_with_its_bounding_box():
    from app.domain.design.relations import roof_design_errors

    plan = spatial_plan()
    plan["profiles"].append(
        {"id": "courtyard", "type": "rectangle", "width": 2, "depth": 2}
    )
    plan["profiles"][0]["holes"] = ["courtyard"]
    plan["roofs"] = [
        {
            "id": "roof",
            "host": "main",
            "support": {"level": "RF"},
            "geometry": {"type": "flat", "overhang": 0},
        }
    ]
    resolved = resolve_design(document(plan))
    marker = next(item for item in resolved.component_markers if item["id"] == "roof")
    filled = {
        "id": "roof_slab",
        "type": "floor",
        "shape": "rect",
        "from": [-1, 4.2, -6],
        "to": [9, 4.2, 2],
        "thickness": 0.2,
    }
    assert any(
        "庭院" in message
        for message in roof_design_errors(
            {"geometry": resolved.body_geometry}, [filled], marker
        )
    )
    outline = marker["resolved_outline"]
    correct = {
        "id": "roof_slab",
        "type": "floor",
        "shape": "polygon",
        "from": [0, 4.2, 0],
        "polygon": outline["outer"],
        "holes": outline["holes"],
        "thickness": 0.2,
    }
    assert not roof_design_errors(
        {"geometry": resolved.body_geometry}, [correct], marker
    )


@pytest.mark.parametrize("kind", ["rectangle", "circle"])
def test_construct_systems_orders_hosts_before_named_opening_tasks(kind):
    from types import SimpleNamespace
    from app.agent.workflows.planning.implementation import _MarkerGeneration
    from app.domain.blueprint.materials.plan import resolve_material_plan
    from app.domain.design.resolver import attach_material_plan

    plan = spatial_plan(kind)
    plan["components"] = [
        {
            "id": "A_window",
            "type": "window",
            "host": "wall_perimeter" if kind == "circle" else "wall_front",
            "size": {"width": 1.2, "height": 1.4},
            "placement": {
                "mode": "wall",
                "anchor": "bottom_left",
                "offset": 2,
                "elevation": {"level": "L1", "offset": 0.8},
            },
            "form": {
                "construction": {
                    "system": "framed_opening",
                    "frameMaterial": "frame",
                    "frameWidth": 0.07,
                    "frameDepth": 0.2,
                    "glassMaterial": "glass",
                    "glassDepth": 0.02,
                    "verticalMullions": 1,
                    "horizontalMullions": 0,
                    "mullionWidth": 0.04,
                }
            },
        }
    ]
    materials = resolve_material_plan(None, [], plan)
    doc = attach_material_plan(document(plan), materials)
    resolved = resolve_design(doc)
    markers = {marker["id"]: marker for marker in resolved.component_markers}
    state = SimpleNamespace(
        pending=deepcopy(markers),
        markers=markers,
        state={"drawing_hosts": resolved.logical_hosts},
        base={
            "meta": {"version": "1.0", "type": "building", "name": "回归"},
            "geometry": {"elements": [], "components": []},
            "assets": {},
            "materials": {
                role["materialId"]: role["material"] for role in materials["roles"]
            },
        },
        trace=[],
        records={},
        fragments=[],
        buckets={"elements": [], "components": []},
        failures={},
        failure_evidence={},
        _record_failure=lambda *_args: [],
    )
    _MarkerGeneration._construct_systems(state)
    assert state.trace[0]["marker_ids"] == ["building_body"]
    assert not state.failures, state.failures
    assert not state.pending


def test_actual_architecture_node_accepts_spatial_schema_without_legacy_fields(
    monkeypatch,
):
    import asyncio
    import json
    from types import SimpleNamespace
    from app.agent.runtime import agent_runtime
    from app.agent.workflows.design import architecture, drafting
    from app.infrastructure.llm.invocation import LlmResult

    plan = spatial_plan("circle")
    calls = []

    async def reply(_model, messages, **_kwargs):
        calls.append(messages)
        return LlmResult(content=json.dumps(plan, ensure_ascii=False))

    monkeypatch.setattr(
        agent_runtime.spec_loader,
        "load_many_result",
        lambda *_a, **_kw: SimpleNamespace(text="", hits=[]),
    )
    monkeypatch.setattr(architecture, "get_reasoning_callback", lambda: None)
    monkeypatch.setattr(drafting, "create_llm", lambda **_kw: object())
    monkeypatch.setattr(drafting, "invoke_llm", reply)
    result = asyncio.run(
        architecture.architecture_planner(
            {
                "user_message": "生成圆形建筑",
                "detail_level": "minimal",
                "intent_profile": "custom",
                "session_id": "spatial-node",
                "thinking_mode": False,
            }
        )
    )
    assert result.get("error") is None, result.get("error")
    assert len(calls) == 1
    assert result["design_document"]["schema_version"] == "design/1.0"
    assert result["architecture_plan"]["volumes"][0]["geometry"]["type"] == "extrusion"
    assert result["resolved_design"]["body_geometry"]["elements"]


def test_arc_and_straight_volume_joint_is_one_floor_despite_trig_noise():
    plan = spatial_plan()
    plan["profiles"].append(
        {
            "id": "half_circle",
            "type": "curve_loop",
            "segments": [
                {
                    "id": "arc",
                    "type": "arc",
                    "center": [0, 0],
                    "radius": 2,
                    "start_angle": 0,
                    "sweep_angle": pi,
                },
                {"id": "chord", "type": "line", "from": [-2, 0], "to": [2, 0]},
            ],
        }
    )
    plan["volumes"].append(
        {
            "id": "rotunda",
            "placement": {"origin_xz": [4, -6], "yaw": 0},
            "geometry": {
                "type": "extrusion",
                "profile": "half_circle",
                "bottom": {"level": "L1"},
                "top": {"level": "RF"},
            },
        }
    )
    plan["slabs"][0]["region"]["volumes"].append("rotunda")
    before = deepcopy(plan)
    geometry = resolve_geometry(document(plan).decisions.model_dump(mode="json"))
    assert len(geometry["slabs"]) == 1
    floor = geometry["slabs"][0]
    assert Polygon(floor["outer"]).area == pytest.approx(80 + 2 * pi, abs=0.002)
    assert plan == before
