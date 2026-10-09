"""P6-A：把材质**设计**与资产**匹配**分开。

这一层修的是一个具体的静默降级：旧实现用 ``elif catalog:`` 把"要不要调模型做
材质设计"和"有没有纹理资产"绑成同一个条件，于是**在没有贴图目录的机器上，
用户提了配色要求也整段跳过**，材质意图无声消失，最后看起来"本来就长这样"。

判据不看"调用了 LLM 没有"，只看**最终实体的材质参数**：用户点名了哪个角色，
那个角色的 baseColor / roughness / metallic 就必须真的被设计过。
"""
import pytest

from app.agent.generation.material.plan import (
    ROLE_SPECS,
    material_intent_terms,
    material_mentions,
    named_material_roles,
    needs_material_design,
    resolve_material_plan,
)


# ── 决策门：设计需求与资产有无是两个独立判断 ──────────────────────


@pytest.mark.parametrize(
    ("message", "has_catalog", "expected"),
    [
        ("生成一个两层小楼", False, False),          # 无要求无资产 → 不设计
        ("生成一个两层小楼", True, True),            # 有资产 → 要决定谁配哪张
        ("外墙用红砖", False, True),                 # 🔴 无资产但有要求 → 仍要设计
        ("深灰屋面配浅色外墙", False, True),
        ("想要木色温暖的质感", False, True),
        ("两层小楼", False, False),                  # "楼"不算材质词
    ],
)
def test_needs_material_design_is_independent_of_catalog(message, has_catalog, expected):
    decided, reason = needs_material_design(message, ROLE_SPECS, has_catalog=has_catalog)
    assert decided is expected, reason
    assert reason, "跳过与否都要给出依据（诊断账本靠它区分'没要求'与'被忽略'）"


def test_role_naming_is_recognised_without_inference():
    """只认角色同义词表，不做语义推断 —— 推断是模型的活。"""

    assert named_material_roles("外墙用红砖，屋顶深灰", ROLE_SPECS) == ["facade_primary", "roof"]
    assert named_material_roles("木桌金属腿", {"wood": 1, "metal": 1}) == []
    assert named_material_roles("普通两层小楼", ROLE_SPECS) == []


def test_terms_do_not_fire_on_non_material_wording():
    assert material_intent_terms("两层小楼，带阳台") == []


# ── 复用条件必须与设计依赖一致（P6-A 第 6 条） ────────────────────


@pytest.mark.parametrize(
    ("feedback", "should_refresh"),
    [
        ("屋顶坐标偏了，往北挪两米", False),      # 纯几何修复 → 不动材质
        ("二层栏杆高度不对", False),
        ("外墙颜色太深了，换浅一点", True),       # 明确材质反馈 → 重新评估
        ("材料换成暖色调", True),
        ("门改成玻璃的", True),                   # 材质名+明确改动 → 重新评估
        # 🔴 反例："木""金属"当子串会误判——这句是**结构**变更，不该换全楼颜色。
        ("把木梁换成混凝土柱", False),
    ],
)
def test_material_feedback_terms_follow_design_dependency(feedback, should_refresh):
    """"改变相关表面/材质角色/用户提材质反馈时重新评估；纯几何修复不能无故换色"。"""

    assert bool(material_mentions(feedback)) is should_refresh, feedback


# ── 无资产时：参数材质必须能承载设计 ──────────────────────────────


def _roles(plan):
    return {item["role"]: item["material"] for item in plan["roles"]}


def test_parametric_material_survives_with_zero_assets():
    """合法参数材质可独立存在：没有贴图也要能落地颜色。"""

    raw = {
        "concept": "红砖外墙",
        "roles": [
            {"role": "facade_primary", "assetId": None, "proceduralPresetId": None,
             "baseColor": [0.62, 0.24, 0.16], "roughness": 0.82, "metallic": 0.0},
        ],
    }
    plan = resolve_material_plan(raw, [], {}, "外墙用红砖", role_specs=ROLE_SPECS)
    material = _roles(plan)["facade_primary"]
    assert material["baseColor"] == pytest.approx([0.62, 0.24, 0.16])
    assert "textureSet" not in material
    assert plan["resolvedAssets"] == {}


def test_fabricated_asset_id_is_rejected_not_accepted():
    """🔴 编造 assetId 必须被拒（进白名单外的资产）并留痕。"""

    raw = {
        "roles": [
            {"role": "facade_primary", "assetId": "brick_red_4k_v7",
             "baseColor": [0.6, 0.3, 0.2]},
        ],
    }
    plan = resolve_material_plan(raw, [], {}, "红砖外墙", role_specs=ROLE_SPECS)
    assert plan["rejectedAssetIds"] == ["brick_red_4k_v7"]
    material = _roles(plan)["facade_primary"]
    assert "textureSet" not in material, "拒了资产还把它写进材质= 编造生效"
    assert material["baseColor"] == pytest.approx([0.6, 0.3, 0.2]), "参数部分仍要落地"


def test_no_assets_no_procedural_leaves_plain_parameter_material():
    plan = resolve_material_plan(None, [], {}, "两层小楼", role_specs=ROLE_SPECS)
    assert plan["resolvedAssets"] == {}
    assert plan["rejectedProceduralPresetIds"] == []
    for material in _roles(plan).values():
        assert "textureSet" not in material
        assert "procedural" not in material


# ── 用户开关：procedural_materials_enabled=false 必须真的生效 ──────


def test_procedural_switch_off_blocks_preset_even_if_model_asks():
    """🔴 模型写了 proceduralPresetId 也不行 —— 开关不是建议。"""

    raw = {
        "roles": [
            {"role": "facade_primary", "assetId": None,
             "proceduralPresetId": "red_brick_clean", "procedural": {"brick": True}},
        ],
    }
    plan = resolve_material_plan(
        raw, [], {}, "红砖小楼", procedural_materials_enabled=False, role_specs=ROLE_SPECS,
    )
    role = next(item for item in plan["roles"] if item["role"] == "facade_primary")
    assert role["proceduralPresetId"] is None
    assert "procedural" not in role["material"], "开关关着却把程序化材质写进了实体"


def test_procedural_switch_on_still_requires_a_legal_preset():
    raw = {
        "roles": [
            {"role": "facade_primary", "assetId": None,
             "proceduralPresetId": "no_such_preset"},
        ],
    }
    plan = resolve_material_plan(
        raw, [], {}, "红砖小楼", procedural_materials_enabled=True, role_specs=ROLE_SPECS,
    )
    assert plan["rejectedProceduralPresetIds"] == ["no_such_preset"]


def test_glass_role_is_never_allowed_to_bind_an_asset():
    """规则 6：玻璃不选纹理资产（物理玻璃由系统给）。"""

    manifests = [{
        "assetId": "wood_plank", "kind": "pbr_texture_set",
        "maps": {"baseColor": "x"},
        "classification": {"recommendedRoles": ["facade_primary"], "materialClass": "wood"},
        "defaults": {"baseColorTint": [0.4, 0.3, 0.2], "roughness": 0.6, "metallic": 0.0},
    }]
    raw = {"roles": [{"role": "glass", "assetId": "wood_plank"}]}
    plan = resolve_material_plan(raw, manifests, {}, "玻璃幕墙", role_specs=ROLE_SPECS)
    role = next(item for item in plan["roles"] if item["role"] == "glass")
    assert role["assetId"] is None
    assert "textureSet" not in role["material"]
    assert role["material"]["materialClass"] == "glass"


# ── 有资产时：资产与角色的对应仍然受白名单约束 ────────────────────


def test_asset_recommended_roles_are_enforced():
    """规则 7：资产声明的 recommendedRoles 之外的角色不得使用。"""

    manifests = [{
        "assetId": "brick_red", "kind": "pbr_texture_set",
        "maps": {"baseColor": "x"},
        "classification": {"recommendedRoles": ["facade_primary"], "materialClass": "brick"},
        "defaults": {"baseColorTint": [0.55, 0.2, 0.15], "roughness": 0.85, "metallic": 0.0},
    }]
    raw = {"roles": [
        {"role": "facade_primary", "assetId": "brick_red"},
        {"role": "floor", "assetId": "brick_red"},
    ]}
    plan = resolve_material_plan(raw, manifests, {}, "红砖小楼", role_specs=ROLE_SPECS)
    facade = next(item for item in plan["roles"] if item["role"] == "facade_primary")
    floor = next(item for item in plan["roles"] if item["role"] == "floor")
    assert facade["assetId"] == "brick_red"
    assert floor["assetId"] is None, "砖纹理不该被允许铺楼板"
    assert "brick_red" in plan["rejectedAssetIds"]


def test_metallic_bounds_are_enforced_per_material_class():
    """规则 5：非金属压到 ≤0.15，金属角色抬到 ≥0.5。"""

    raw = {"roles": [
        {"role": "facade_primary", "baseColor": [0.5, 0.5, 0.5], "roughness": 0.7, "metallic": 0.9},
        {"role": "frame", "baseColor": [0.1, 0.1, 0.1], "roughness": 0.3, "metallic": 0.05},
    ]}
    plan = resolve_material_plan(raw, [], {}, "小楼", role_specs=ROLE_SPECS)
    roles = _roles(plan)
    assert roles["facade_primary"]["metallic"] <= 0.15
    assert roles["frame"]["metallic"] >= 0.5


# ── 模型失败：确定性回退必须仍在，但意图丢失要能被看见 ─────────────


def test_deterministic_fallback_always_yields_every_role():
    plan = resolve_material_plan(None, [], {}, "两层小楼", role_specs=ROLE_SPECS)
    assert {item["role"] for item in plan["roles"]} == set(ROLE_SPECS)


def test_malformed_color_is_rejected_not_written():
    """非法 baseColor（不是 3 个 0–1 数）必须退回角色表，而不是照写。"""

    raw = {"roles": [
        {"role": "facade_primary", "baseColor": [9.0, -1.0], "roughness": 0.7},
    ]}
    plan = resolve_material_plan(raw, [], {}, "小楼", role_specs=ROLE_SPECS)
    material = _roles(plan)["facade_primary"]
    for value in material["baseColor"]:
        assert 0.0 <= value <= 1.0
        assert material["baseColor"] == pytest.approx(ROLE_SPECS["facade_primary"]["baseColor"])