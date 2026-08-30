"""平面新增闸门（FP1/4/5/7/8）测试。"""

from app.agent.floor_plan_gates import (
    gate_fp1_functional_completeness,
    gate_fp4_privacy_zones,
    gate_fp5_wet_space_shaft,
    gate_fp7_stair_double_height,
    gate_fp8_exterior_attachments,
)


def _plan_with(spaces, *, vertical_spaces=None, circulation=None, attachments=None):
    return {
        "levels": [{
            "id": "level_1", "level": 1,
            "spaces": spaces,
            "openings": [
                {"id": f"o{i}", "type": "door", "connects": [s["id"], spaces[(i+1) % len(spaces)]["id"]]}
                for i, s in enumerate(spaces[:2])
            ],
        }],
        "vertical_spaces": vertical_spaces or [],
        "vertical_circulation": circulation or [],
        "exterior_attachments": attachments or [],
    }


def test_fp1_missing_space():
    plan = _plan_with([{"id": "living", "space_type": "living", "zone": "semi_private"}])
    issues = gate_fp1_functional_completeness(plan, ["bedroom", "bathroom"])
    assert any(i["code"] == "fp1_missing_space" for i in issues)
    assert "bedroom" in issues[0]["message"]


def test_fp1_no_required_no_issues():
    plan = _plan_with([{"id": "living", "space_type": "living"}])
    assert gate_fp1_functional_completeness(plan, None) == []


def test_fp4_private_to_private_warning():
    plan = _plan_with([
        {"id": "bed1", "space_type": "bedroom", "zone": "private", "privacy_level": 3},
        {"id": "bed2", "space_type": "bedroom", "zone": "private", "privacy_level": 3},
    ])
    issues = gate_fp4_privacy_zones(plan)
    assert any(i["code"] == "fp4_private_to_private" for i in issues)


def test_fp5_wet_space_requires_shaft():
    plan = _plan_with([
        {"id": "bath", "space_type": "bathroom", "zone": "service", "wet_space": True},
        {"id": "bed", "space_type": "bedroom", "zone": "private"},
    ])
    issues = gate_fp5_wet_space_shaft(plan)
    assert any(i["code"] == "fp5_wet_space_without_shaft" for i in issues)


def test_fp5_wet_space_with_shaft_ok():
    plan = _plan_with([
        {"id": "bath", "space_type": "bathroom", "zone": "service", "wet_space": True, "served_by_shaft": "shaft_1"},
        {"id": "bed", "space_type": "bedroom", "zone": "private"},
    ])
    assert gate_fp5_wet_space_shaft(plan) == []


def test_fp7_double_height_no_edge_protection():
    plan = _plan_with(
        [{"id": "living", "space_type": "living"}],
        vertical_spaces=[{"id": "atrium_1", "type": "double_height", "edge_protection_required": False}],
    )
    issues = gate_fp7_stair_double_height(plan)
    assert any(i["code"] == "fp7_double_height_no_edge_protection" for i in issues)


def test_fp8_attachment_host_missing():
    plan = _plan_with(
        [{"id": "living", "space_type": "living"}],
        attachments=[{"id": "balc", "type": "balcony", "host_space_id": "ghost"}],
    )
    issues = gate_fp8_exterior_attachments(plan)
    assert any(i["code"] == "fp8_attachment_host_missing" for i in issues)
