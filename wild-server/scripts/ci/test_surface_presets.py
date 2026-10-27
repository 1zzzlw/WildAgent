"""材质库 -> 材质计划 -> WILD，以及已解析计划复用的回归。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agent.generation.material.plan import resolve_material_plan, apply_resolved_material_plan, ROLE_SPECS, OBJECT_ROLE_SPECS
from app.agent.generation.material.surfaces import SURFACE_PRESETS
from app.agent.prompts.planning import build_material_plan_prompt


def test_catalog_mirror():
    root = Path(__file__).resolve().parents[3]
    assert json.loads((root / "wild-core/material-presets.json").read_text("utf-8")) == json.loads((root / "wild-server/storage/knowledge_base/material-presets.json").read_text("utf-8"))


def test_all_surface_presets_survive_plan_and_reuse():
    for preset_id, preset in SURFACE_PRESETS.items():
        role = preset["recommendedRoles"][0]
        specs = OBJECT_ROLE_SPECS if role in {"wood", "metal", "stone", "fabric"} else ROLE_SPECS
        raw = {"roles": [{"role": role, "surfacePresetId": preset_id}]}
        plan = resolve_material_plan(raw, [], role_specs=specs)
        entry = next(item for item in plan["roles"] if item["role"] == role)
        assert entry["surfacePresetId"] == preset_id
        for key, value in preset["material"].items():
            assert entry["material"][key] == value, (preset_id, key)
        reused = resolve_material_plan(plan, [], role_specs=specs)
        assert reused["roles"] == plan["roles"]
        bp = apply_resolved_material_plan({"geometry": {"elements": []}}, plan, role_specs=specs)
        assert bp["materials"][entry["materialId"]] == entry["material"]


def test_incompatible_or_unknown_preset_does_not_inject_surface():
    for value in ("made_up", "glass_clear", [], 5):
        plan = resolve_material_plan({"roles": [{"role": "door", "surfacePresetId": value}]}, [])
        entry = next(item for item in plan["roles"] if item["role"] == "door")
        assert entry["surfacePresetId"] is None
        assert "transmission" not in entry["material"]


def test_prompt_lists_every_builtin_without_asset_dependency():
    prompt = build_material_plan_prompt({}, [])
    assert "surfacePresetId" in prompt
    assert all(preset_id in prompt for preset_id in SURFACE_PRESETS)


def test_no_model_fallback_uses_surfaces_and_preserves_explicit_color():
    plan = resolve_material_plan({"roles": [{"role": "door", "baseColor": [0.2, 0.3, 0.4]}]}, [])
    roles = {item["role"]: item for item in plan["roles"]}
    assert roles["door"]["material"]["baseColor"] == [0.2, 0.3, 0.4]
    assert roles["door"]["material"]["surfacePattern"] == "planks"
    assert roles["floor"]["material"]["surfacePattern"] == "tiles"
    assert roles["glass"]["material"]["transmission"] > 0.9


def test_metal_preset_retains_physical_metallic_on_structure():
    plan = resolve_material_plan({"roles": [{"role": "structure", "surfacePresetId": "metal_brushed"}]}, [])
    material = next(item["material"] for item in plan["roles"] if item["role"] == "structure")
    assert material["metallic"] == 0.85
    assert material["anisotropy"] == 0.65
