from app.agent.nodes.material_plan_node import (
    apply_resolved_material_plan,
    compact_asset_catalog,
    resolve_material_plan,
)
from app.agent.prompts import build_material_plan_prompt


ASSET_ID = "pbr_111111111111111111111111"


def _asset(*, roles=None):
    return {
        "schemaVersion": "1.0",
        "assetId": ASSET_ID,
        "kind": "pbr_texture_set",
        "name": "Warm limestone",
        "contentHash": "sha256:" + "1" * 64,
        "source": {"type": "local_upload"},
        "license": "CC0",
        "maps": {"baseColor": {"uri": "/secret-texture-url"}},
        "classification": {
            "materialClass": "stone",
            "tags": ["warm_gray", "seamless"],
            "recommendedRoles": roles or ["facade_primary"],
        },
        "realWorldSizeMeters": [2, 2],
        "defaults": {
            "roughness": 0.74,
            "metallic": 0,
            "normalScale": 0.9,
            "uvScale": [2, 2],
        },
        "createdAt": "2026-01-01T00:00:00+00:00",
    }


def test_prompt_catalog_never_contains_texture_urls():
    catalog = compact_asset_catalog([_asset()])
    prompt = build_material_plan_prompt({"concept": "modern villa"}, catalog)

    assert ASSET_ID in prompt
    assert "/secret-texture-url" not in prompt
    assert "严禁猜测 ID" in prompt


def test_resolver_accepts_only_existing_role_compatible_assets():
    raw = {
        "concept": "warm stone",
        "roles": [
            {"role": "facade_primary", "assetId": ASSET_ID},
            {"role": "roof", "assetId": "pbr_999999999999999999999999"},
            {"role": "glass", "assetId": ASSET_ID},
        ],
    }
    plan = resolve_material_plan(raw, [_asset()])
    by_role = {item["role"]: item for item in plan["roles"]}

    assert by_role["facade_primary"]["assetId"] == ASSET_ID
    assert by_role["facade_primary"]["material"]["textureSet"] == ASSET_ID
    assert by_role["roof"]["assetId"] is None
    assert by_role["glass"]["assetId"] is None
    assert by_role["glass"]["material"]["materialClass"] == "glass"
    assert by_role["glass"]["material"]["transmission"] == 0.92
    assert sorted(plan["rejectedAssetIds"]) == sorted([
        ASSET_ID,
        "pbr_999999999999999999999999",
    ])


def test_resolved_plan_rebinds_skeleton_and_closes_asset_references():
    plan = resolve_material_plan(
        {"roles": [{"role": "facade_primary", "assetId": ASSET_ID}]},
        [_asset()],
    )
    blueprint = {
        "geometry": {
            "elements": [
                {"id": "wall_1", "type": "wall", "material": "made_up"},
                {"id": "floor_1", "type": "floor", "material": "made_up"},
            ],
        },
        "materials": {"made_up": {"baseColor": [1, 0, 0]}},
    }

    result = apply_resolved_material_plan(blueprint, plan)

    assert result["geometry"]["elements"][0]["material"] == "wall_finish"
    assert result["geometry"]["elements"][1]["material"] == "floor_finish"
    assert result["materials"]["wall_finish"]["textureSet"] == ASSET_ID
    assert list(result["assets"]) == [ASSET_ID]
