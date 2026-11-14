"""材质库 -> 材质计划 -> WILD，以及已解析计划复用的回归。"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agent.generation.material.plan import resolve_material_plan, apply_resolved_material_plan, ROLE_SPECS, OBJECT_ROLE_SPECS
from app.agent.generation.material.surfaces import SURFACE_PRESETS
from app.agent.prompts.planning import build_material_plan_prompt
from app.design.contracts import DesignDocument, ResolvedMaterialPlan
from app.design.repository import DesignRepository
from app.design.resolver import attach_material_plan, build_design_document


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


def architecture_document():
    return build_design_document({
        "massing": {"shape": "rectangle", "width": 8, "depth": 6, "floors": 1,
                    "modeled_floors": 1, "floor_height": 3},
        "volumes": [{"id": "main", "x": 0, "z": 0, "width": 8, "depth": 6,
                     "start_floor": 1, "end_floor": 1}],
        "structural_grid": {"system": "wall", "x_bays": 1, "z_bays": 1},
        "facades": {face: {"bays": 1, "ground_pattern": ["window"], "upper_pattern": ["window"]}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "flat"},
    }, session_id="surface_contract_regression", source_request="生成一层建筑")


@pytest.mark.parametrize("role_specs", [ROLE_SPECS, OBJECT_ROLE_SPECS], ids=["architecture", "object"])
def test_resolved_surface_plan_passes_design_document_contract(role_specs):
    plan = resolve_material_plan(None, [], role_specs=role_specs)
    parsed = ResolvedMaterialPlan.model_validate(plan)
    assert parsed.model_dump(mode="json") == plan
    for preset_id, preset in SURFACE_PRESETS.items():
        for role in preset["recommendedRoles"]:
            if role not in role_specs:
                continue
            selected = resolve_material_plan({"roles": [{"role": role, "surfacePresetId": preset_id}]}, [], role_specs=role_specs)
            assert ResolvedMaterialPlan.model_validate(selected).model_dump(mode="json") == selected


def test_surface_plan_survives_document_persistence_and_projection(tmp_path):
    source = architecture_document()
    plan = resolve_material_plan(None, [])
    document = attach_material_plan(source, plan)
    repository = DesignRepository(tmp_path)
    saved, resolved = repository.save(document)
    loaded = repository.get(saved.session_id)
    assert loaded is not None
    assert loaded.decisions.materials.resolved_plan.model_dump(mode="json") == plan
    assert source.decisions.materials.resolved_plan is None
    assert resolved["component_markers"]
    assert DesignDocument.model_validate_json(saved.model_dump_json()) == loaded
    roles = {item["role"]: item for item in plan["roles"]}
    blueprint = apply_resolved_material_plan({"geometry": {"elements": []}},
                                            loaded.decisions.materials.resolved_plan.model_dump(mode="json"))
    assert blueprint["materials"][roles["glass"]["materialId"]]["transmission"] > 0.9
    assert blueprint["materials"][roles["door"]["materialId"]]["surfacePattern"] == "planks"


def test_legacy_material_plan_and_unknown_fields_remain_strict():
    plan = resolve_material_plan(None, [])
    for item in plan["roles"]:
        item.pop("surfacePresetId")
    parsed = ResolvedMaterialPlan.model_validate(plan)
    assert all(item.surfacePresetId is None for item in parsed.roles)
    plan["roles"][0]["unrecognized_surface_field"] = "plaster_lime"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ResolvedMaterialPlan.model_validate(plan)


def test_material_node_saves_surface_plan_and_reaches_implementation_plan(tmp_path, monkeypatch):
    from app.agent.generation.material import workflow
    from app.agent.plan.workflow import plan_node
    from app.design import repository
    from app.design.resolver import architecture_plan_from_document

    store = DesignRepository(tmp_path)
    monkeypatch.setattr(repository, "design_repository", store)
    monkeypatch.setattr(workflow.asset_storage, "list_manifests", lambda: [])
    monkeypatch.setattr(workflow, "create_llm", lambda **kwargs: object())
    calls = []

    async def recorded_material_response(*args):
        calls.append(True)
        return SimpleNamespace(content=json.dumps({"roles": [
            {"role": "facade_primary", "surfacePresetId": "plaster_lime"},
            {"role": "door", "surfacePresetId": "planks_walnut"},
        ]}), token_usage=None)

    monkeypatch.setattr(workflow, "invoke_llm", recorded_material_response)
    document = architecture_document()
    state = {"session_id": document.session_id, "user_message": "白色抹灰外墙和木纹门",
             "architecture_plan": architecture_plan_from_document(document),
             "design_document": document.model_dump(mode="json")}

    async def run():
        output = await workflow.material_planner(state)
        assert calls == [True]
        saved = store.get(document.session_id)
        assert output["design_document"] == saved.model_dump(mode="json")
        assert saved.status == "approved" and saved.approved_at
        assert saved.decisions.materials.resolved_plan.roles[0].surfacePresetId == "plaster_lime"
        planned = await plan_node({**state, **output})
        assert planned["plan_diag"]["marker_count"] > 0
        assert planned["plan"]["items"]
        roles = {role.role: role for role in saved.decisions.materials.resolved_plan.roles}
        assert planned["skeleton_blueprint"]["materials"][roles["door"].materialId]["surfacePattern"] == "planks"

    asyncio.run(run())
