from app.agent.nodes.material_plan_node import (
    apply_resolved_material_plan,
    compact_asset_catalog,
    resolve_material_plan,
)
from app.agent.procedural_material_recipes import (
    compact_procedural_catalog,
    resolve_brick_preset,
    without_procedural_materials,
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
            "baseColorTint": [0.82, 0.72, 0.58],
            "roughness": 0.74,
            "metallic": 0,
            "normalScale": 0.9,
            "uvScale": [2, 2],
        },
        "createdAt": "2026-01-01T00:00:00+00:00",
    }


def test_prompt_catalog_never_contains_texture_urls():
    catalog = compact_asset_catalog([_asset()])
    prompt = build_material_plan_prompt(
        {"concept": "modern villa"},
        catalog,
        compact_procedural_catalog(),
    )

    assert ASSET_ID in prompt
    assert "/secret-texture-url" not in prompt
    assert "严禁猜测 ID" in prompt
    assert "AVAILABLE_PROCEDURAL_PRESETS" in prompt
    assert "用户没说材质" in prompt
    assert "一张 Base Color" in prompt
    assert "GLSL、Shader 源码" in prompt


def test_compact_catalog_recognizes_new_base_color_only_assets():
    catalog = compact_asset_catalog([_asset(), {"assetId": "invalid"}])

    assert len(catalog) == 1
    assert catalog[0]["kind"] == "pbr_texture_set"
    assert catalog[0]["channels"] == ["baseColor"]
    assert catalog[0]["baseColorOnly"] is True
    assert catalog[0]["sourceType"] == "local_upload"


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
    assert by_role["facade_primary"]["material"]["baseColor"] == [0.82, 0.72, 0.58]
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


def test_resolver_accepts_only_sanitized_procedural_brick_for_facade():
    raw = {
        "roles": [
            {
                "role": "facade_primary",
                "assetId": None,
                "baseColor": [0.52, 0.11, 0.055],
                "procedural": {
                    "type": "brick",
                    "seed": 42,
                    "brickSize": [0.24, 0.065],
                    "mortarWidth": 0.01,
                    "mortarDepth": 0.006,
                    "bond": "running",
                    "secondaryColor": [0.68, 0.19, 0.08],
                    "colorVariation": 0.14,
                    "weathering": {
                        "amount": 0.28,
                        "scale": 1.8,
                        "efflorescence": 0.1,
                        "verticalStreaks": 0.14,
                        "baseDampness": 0.08,
                        "shader": "not allowed",
                    },
                    "shader": "void main(){}",
                },
            },
            {"role": "roof", "procedural": {"type": "brick"}},
        ],
    }

    plan = resolve_material_plan(raw, [], procedural_materials_enabled=True)
    by_role = {item["role"]: item for item in plan["roles"]}
    procedural = by_role["facade_primary"]["material"]["procedural"]

    assert procedural["type"] == "brick"
    assert procedural["brickSize"] == [0.24, 0.065]
    assert procedural["weathering"]["verticalStreaks"] == 0.14
    assert "shader" not in procedural
    assert "shader" not in procedural["weathering"]
    assert "procedural" not in by_role["roof"]["material"]


def test_texture_asset_takes_precedence_over_procedural_material():
    plan = resolve_material_plan({
        "roles": [{
            "role": "facade_primary",
            "assetId": ASSET_ID,
            "procedural": {"type": "brick"},
        }],
    }, [_asset()], procedural_materials_enabled=True)
    facade = next(item for item in plan["roles"] if item["role"] == "facade_primary")

    assert facade["material"]["textureSet"] == ASSET_ID
    assert "procedural" not in facade["material"]


def test_resolver_expands_semantic_shader_preset_with_stable_parameters():
    raw = {
        "roles": [{
            "role": "facade_primary",
            "proceduralPresetId": "brick_aged_red",
            "shaderAdjustments": {
                "tone": "dark",
                "mortarDepth": "deep",
                "weathering": "moderate",
                "efflorescence": "subtle",
                "verticalStreaks": "subtle",
                "baseDampness": "none",
                "cleanliness": "clean",
            },
        }],
    }
    first = resolve_material_plan(
        raw, [], {"concept": "warm villa"}, "生成一个别墅",
        procedural_materials_enabled=True,
    )
    second = resolve_material_plan(
        raw, [], {"concept": "warm villa"}, "生成一个别墅",
        procedural_materials_enabled=True,
    )
    facade = next(item for item in first["roles"] if item["role"] == "facade_primary")
    procedural = facade["material"]["procedural"]

    assert facade["proceduralPresetId"] == "brick_aged_red"
    assert procedural["mortarDepth"] == 0.009
    assert procedural["weathering"]["amount"] == 0.12
    assert procedural["weathering"]["efflorescence"] == 0.1
    assert procedural["weathering"]["verticalStreaks"] == 0.08
    assert procedural["weathering"]["baseDampness"] == 0
    assert 1.45 <= procedural["weathering"]["scale"] <= 2.1
    assert procedural["seed"] == next(
        item for item in second["roles"] if item["role"] == "facade_primary"
    )["material"]["procedural"]["seed"]
    assert facade["material"]["baseColor"][0] < 0.52


def test_brick_recipe_varies_visual_parameters_by_stable_context():
    first = resolve_brick_preset("brick_aged_red", stable_context="villa-a")
    repeated = resolve_brick_preset("brick_aged_red", stable_context="villa-a")
    second = resolve_brick_preset("brick_aged_red", stable_context="villa-b")

    assert first == repeated
    assert first is not None and second is not None
    first_visual = {
        "baseColor": first["baseColor"],
        "roughness": first["roughness"],
        **{
            key: value
            for key, value in first["procedural"].items()
            if key != "seed"
        },
    }
    second_visual = {
        "baseColor": second["baseColor"],
        "roughness": second["roughness"],
        **{
            key: value
            for key, value in second["procedural"].items()
            if key != "seed"
        },
    }

    assert first_visual != second_visual


def test_procedural_shader_requires_explicit_opt_in():
    raw = {
        "roles": [{
            "role": "facade_primary",
            "proceduralPresetId": "brick_aged_red",
            "procedural": {"type": "brick"},
        }],
    }

    disabled = resolve_material_plan(
        raw,
        [],
        {"concept": "brick villa"},
        "生成红砖别墅",
        procedural_materials_enabled=False,
    )
    enabled = resolve_material_plan(
        raw,
        [],
        {"concept": "brick villa"},
        "生成红砖别墅",
        procedural_materials_enabled=True,
    )
    disabled_facade = next(
        item for item in disabled["roles"] if item["role"] == "facade_primary"
    )
    enabled_facade = next(
        item for item in enabled["roles"] if item["role"] == "facade_primary"
    )

    assert disabled_facade["proceduralPresetId"] is None
    assert "procedural" not in disabled_facade["material"]
    assert enabled_facade["proceduralPresetId"] == "brick_aged_red"
    assert enabled_facade["material"]["procedural"]["type"] == "brick"


def test_delivery_shader_guard_does_not_mutate_source_blueprint():
    source = {
        "materials": {
            "wall": {
                "baseColor": [0.5, 0.1, 0.05],
                "procedural": {"type": "brick"},
            },
            "roof": {"baseColor": [0.2, 0.2, 0.2]},
        },
    }

    guarded = without_procedural_materials(source)

    assert "procedural" not in guarded["materials"]["wall"]
    assert source["materials"]["wall"]["procedural"] == {"type": "brick"}


def test_resolver_uses_deterministic_brick_fallback_only_for_explicit_brick_intent():
    brick_plan = resolve_material_plan(
        None,
        [],
        {"concept": "乡村住宅"},
        "生成一栋有轻微返碱红砖墙的别墅",
        procedural_materials_enabled=True,
    )
    generic_plan = resolve_material_plan(
        None,
        [],
        {"concept": "现代别墅"},
        "生成一个别墅",
        procedural_materials_enabled=True,
    )
    brick_facade = next(item for item in brick_plan["roles"] if item["role"] == "facade_primary")
    generic_facade = next(item for item in generic_plan["roles"] if item["role"] == "facade_primary")

    assert brick_facade["proceduralPresetId"] == "brick_salt_weathered"
    assert brick_facade["material"]["procedural"]["type"] == "brick"
    assert generic_facade["proceduralPresetId"] is None
    assert "procedural" not in generic_facade["material"]


def test_resolver_rejects_unknown_procedural_preset_id():
    plan = resolve_material_plan({
        "roles": [{
            "role": "facade_primary",
            "proceduralPresetId": "brick_for_one_special_building",
        }],
    }, [], procedural_materials_enabled=True)
    facade = next(item for item in plan["roles"] if item["role"] == "facade_primary")

    assert facade["proceduralPresetId"] is None
    assert "procedural" not in facade["material"]
    assert plan["rejectedProceduralPresetIds"] == ["brick_for_one_special_building"]


def test_weathering_none_disables_inherited_weather_effects():
    plan = resolve_material_plan({
        "roles": [{
            "role": "facade_primary",
            "proceduralPresetId": "brick_aged_red",
            "shaderAdjustments": {"weathering": "none"},
        }],
    }, [], procedural_materials_enabled=True)
    facade = next(item for item in plan["roles"] if item["role"] == "facade_primary")

    weathering = facade["material"]["procedural"]["weathering"]
    assert weathering["amount"] == 0
    assert weathering["efflorescence"] == 0
    assert weathering["verticalStreaks"] == 0
    assert weathering["baseDampness"] == 0
    assert 1.45 <= weathering["scale"] <= 2.1


def test_glass_curtain_wall_keeps_opaque_neutral_facade():
    """玻璃幕墙：外墙宿主保持不透明中性墙板，玻璃由窗构件的 glassMaterial 表达。"""
    plan = resolve_material_plan(None, [], user_message="生成一个玻璃幕墙商业综合体")
    assert plan["curtainWall"] is True

    blueprint = {
        "meta": {"version": "1.1", "type": "building", "name": "玻璃幕墙"},
        "geometry": {
            "elements": [
                {"id": "wall_front", "type": "wall", "from": [0, 0, 0], "to": [42, 120, 0], "thickness": 0.3},
                {"id": "col_1", "type": "column", "base": [0.5, 0, 0.5], "height": 120, "bottomRadius": 0.4, "topRadius": 0.4},
            ],
            "components": [],
        },
        "materials": {},
    }
    apply_resolved_material_plan(blueprint, plan)

    wall = blueprint["geometry"]["elements"][0]
    column = blueprint["geometry"]["elements"][1]
    assert wall["material"] == "wall_finish"  # 外墙宿主保持中性墙板，不是玻璃也不是深色金属
    assert column["material"] == "concrete"  # 结构柱仍用结构材质
    assert blueprint["materials"]["glass"].get("materialClass") == "glass"  # 玻璃材质保留给窗
    assert blueprint["materials"]["glass"].get("transmission") == 0.92
    assert blueprint["materials"]["metal"]["metallic"] >= 0.5  # 金属框材质保留给窗框


def test_non_curtain_wall_keeps_opaque_facade():
    """非玻璃幕墙请求不应把外墙改成玻璃。"""
    plan = resolve_material_plan(None, [], user_message="生成一个混凝土办公楼")
    assert plan.get("curtainWall") is False


def test_curtain_wall_keeps_all_walls_neutral():
    """玻璃幕墙不把任何墙改成玻璃或深色金属，全部保持中性墙板；分格由窗承担。"""
    plan = resolve_material_plan(None, [], user_message="生成一个玻璃幕墙办公楼")
    blueprint = {
        "geometry": {
            "elements": [
                {"id": "wall_front", "type": "wall", "from": [0, 0, 0], "to": [42, 120, 0], "thickness": 0.3},
                {"id": "wall_back", "type": "wall", "from": [0, 0, 36], "to": [42, 120, 36], "thickness": 0.3},
                {"id": "wall_left", "type": "wall", "from": [0, 0, 0], "to": [0, 120, 36], "thickness": 0.3},
                {"id": "wall_right", "type": "wall", "from": [42, 0, 0], "to": [42, 120, 36], "thickness": 0.3},
                {"id": "wall_core", "type": "wall", "from": [21, 0, 16], "to": [21, 120, 20], "thickness": 0.2},
            ],
        },
        "materials": {},
    }
    apply_resolved_material_plan(blueprint, plan)
    by_id = {element["id"]: element for element in blueprint["geometry"]["elements"]}
    for wall_id in ("wall_front", "wall_back", "wall_left", "wall_right", "wall_core"):
        assert by_id[wall_id]["material"] == "wall_finish"
