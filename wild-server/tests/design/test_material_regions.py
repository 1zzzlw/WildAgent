"""P5-C：区域/构件材质分区。

这一层的意义（`P5-扩展建筑设计表达.md`）：避免"所有墙强制共用一种效果"。
引入前材质角色**只按元素类型**分配（`ELEMENT_ROLE`），所以同类型的墙/柱/灯具
必然共用一个材质；引入后可以按"这一类实体"单独换引用。
"""
import collections

import pytest

from app.agent.compiler import compile_design
from app.agent.generation.architecture import normalize_architecture_plan
from app.agent.generation.material.plan import apply_material_regions

def _role(role):
    # baseColor 必须给全：少给就是 schema_invalid，测试会在带 error 的产物上"通过"。
    return {"role": role, "materialId": f"m_{role}", "material": {"baseColor": [0.5, 0.5, 0.5]}}


_MATERIAL_PLAN = {
    "roles": [
        _role("structure"),
        _role("roof"),
        _role("facade_primary"),
        _role("floor"),
    ],
    "resolvedAssets": {},
}

_BASE_PLAN = {
    "massing": {"shape": "rectangular", "width": 12, "depth": 9, "floors": 2},
    "component_quota": {"light": {"min": 3, "max": 6}},
}


def _compile(regions=None, message="小楼"):
    plan = {**_BASE_PLAN, "material_regions": list(regions or [])}
    normalized = normalize_architecture_plan(plan, message)
    return compile_design(
        normalized, user_message=message, material_plan=_MATERIAL_PLAN,
    )


def _materials_by_type(blueprint, kind):
    key = "elements" if kind == "element" else "components"
    return collections.Counter(
        (str(item.get("type")), str(item.get("material")))
        for item in blueprint["geometry"][key]
    )


# ── 核心：一个绑定 ⇒ 只改那一类实体 ────────────────────────────────


def test_element_region_binding_changes_only_that_type():
    baseline = _compile()
    bound = _compile([{"role": "roof", "type": "roof"}])
    assert _materials_by_type(baseline.blueprint, "element")[("roof", "roof")] == 1
    assert _materials_by_type(bound.blueprint, "element")[("roof", "m_roof")] == 1
    # 其它元素类型逐项不变 —— 这就是"避免所有墙强制共用一种效果"的最小可测形态。
    for kind in ("wall", "floor"):
        assert sorted(
            material for (etype, material) in _materials_by_type(baseline.blueprint, "element")
            if etype == kind
        ) == sorted(
            material for (etype, material) in _materials_by_type(bound.blueprint, "element")
            if etype == kind
        ), kind


def test_component_region_binding_changes_only_that_type():
    bound = _compile([{"role": "structure", "type": "light"}])
    lights = [
        material for (etype, material) in _materials_by_type(bound.blueprint, "component")
        if etype == "light"
    ]
    assert lights and set(lights) == {"m_structure"}


def test_binding_never_leaves_a_dangling_material_reference():
    """🔴 只换引用的硬判据：绑完不能出现指向不存在材质的实体。"""

    for regions in ([{"role": "roof", "type": "roof"}], [{"role": "structure", "type": "light"}]):
        result = _compile(regions)
        known = set(result.blueprint.get("materials") or {})
        used = {
            item["material"]
            for key in ("elements", "components")
            for item in result.blueprint["geometry"][key]
            if item.get("material")
        }
        assert not used - known, regions
        assert not [item for item in result.defects if item.severity == "error"]


def test_empty_regions_reproduce_the_pre_p5_blueprint():
    """🔴 迁移等价：没有绑定时产物必须与引入前逐字段相同。"""

    legacy = _compile()
    empty = _compile([])
    assert _materials_by_type(legacy.blueprint, "element") == _materials_by_type(empty.blueprint, "element")
    assert _materials_by_type(legacy.blueprint, "component") == _materials_by_type(empty.blueprint, "component")


# ── 只标记不阻断 ──────────────────────────────────────────────────


def test_unknown_role_is_reported_and_changes_nothing():
    """材质方案里没有这个角色 ⇒ 绑定不生效、逐条报出，但产物仍合法。"""

    result = _compile([{"role": "ghost", "type": "wall"}])
    stats = result.stats.get("material_regions")
    assert stats and stats[0]["role"] == "ghost"
    assert stats[0]["applied"] == 0 and "没有角色" in stats[0]["reason"]
    # 墙的默认角色是 facade_primary（见 ELEMENT_ROLE），不是角色名 facade。
    assert _materials_by_type(result.blueprint, "element")[("wall", "m_facade_primary")] == 8


def test_region_with_no_matching_entity_is_reported():
    result = _compile([{"role": "structure", "type": "railing"}])
    stats = result.stats.get("material_regions")
    assert stats and stats[0]["applied"] == 0 and "railing" in stats[0]["reason"]


def test_blueprint_stays_valid_with_a_bad_region():
    """材质分区写错**不许**让整栋房子的墙消失（只标记不阻断）。"""

    result = _compile([{"role": "ghost", "type": "wall"}, {"role": "roof", "type": "roof"}])
    walls = [item for item in result.blueprint["geometry"]["elements"] if item.get("type") == "wall"]
    assert walls, "墙不能因为一条坏绑定消失"
    assert not [item for item in result.defects if item.severity == "error"]


# ── 归一化只做形状过滤，不解释角色 ────────────────────────────────


def test_normalization_passes_regions_through_without_validating_roles():
    normalized = normalize_architecture_plan(
        {**_BASE_PLAN, "material_regions": [{"role": "not_a_real_role", "type": "wall"}]},
        "小楼",
    )
    assert normalized["materials"]["regions"] == [{"role": "not_a_real_role", "type": "wall"}]


def test_normalization_drops_entries_without_a_role():
    normalized = normalize_architecture_plan(
        {**_BASE_PLAN, "material_regions": [{"type": "wall"}, {"role": "roof", "type": "roof"}]},
        "小楼",
    )
    assert normalized["materials"]["regions"] == [{"role": "roof", "type": "roof"}]


def test_regions_absent_means_no_key_at_all():
    """没有绑定时**不留空键**：方案里多个空列表也会让"有没有表达过"变成不可判。"""

    normalized = normalize_architecture_plan(_BASE_PLAN, "小楼")
    assert "material_regions" not in normalized


# ── 单元层：只换引用，不新增材质 ──────────────────────────────────


def test_apply_material_regions_only_rewrites_references():
    blueprint = {
        "materials": {"m_a": {}, "m_b": {}},
        "geometry": {
            "elements": [{"id": "wall_1", "type": "wall", "material": "m_a"}],
            "components": [{"id": "door_1", "type": "door", "material": "m_a"}],
        },
    }
    applied = apply_material_regions(
        blueprint, [{"role": "b", "type": "wall"}], {"a": "m_a", "b": "m_b"},
    )
    assert applied == [{"role": "b", "target": "wall", "applied": 1, "reason": ""}]
    assert blueprint["geometry"]["elements"][0]["material"] == "m_b"
    assert blueprint["geometry"]["components"][0]["material"] == "m_a", "门不该被墙的绑定带走"
    assert set(blueprint["materials"]) == {"m_a", "m_b"}, "不新增材质实体"


def test_apply_material_regions_on_a_blueprint_without_geometry_is_a_noop():
    assert apply_material_regions({}, [{"role": "a", "type": "wall"}], {"a": "m"}) == []


# ── 契约 ──────────────────────────────────────────────────────────


def test_contract_requires_both_role_and_type():
    from pydantic import ValidationError

    from app.design.contracts import MaterialIntent

    MaterialIntent(regions=[{"role": "roof", "type": "roof"}])
    with pytest.raises(ValidationError):
        MaterialIntent(regions=[{"role": "roof"}])
    with pytest.raises(ValidationError):
        MaterialIntent(regions=[{"type": "roof"}])


def test_design_document_round_trips_regions():
    from app.design.resolver import architecture_plan_from_document, build_design_document

    doc = build_design_document(
        {
            "massing": {"shape": "rectangular", "width": 12, "depth": 9, "floors": 2,
                        "modeled_floors": 2, "floor_height": 3.2},
            "volumes": [{"id": "main", "role": "primary", "x": 0, "z": 0,
                         "width": 12, "depth": 9, "start_floor": 1, "end_floor": 2}],
            "structural_grid": {"system": "wall_bearing", "x_bays": 3, "z_bays": 2},
            "facades": {face: {"bays": 3, "ground_pattern": ["window", "door", "window"],
                               "upper_pattern": ["window", "window", "window"]}
                        for face in ("front", "back", "left", "right")},
            "roof": {"type": "gable"},
            "materials": {"regions": [{"role": "structure", "type": "roof"}]},
        },
        session_id="intent", source_request="小楼",
    )
    # 走model_validate 而非 model_copy：真实链路是JSON 反序列化，
    # model_copy(update=) 不校验，dict 会一路漏到 resolver 里。
    doc = type(doc).model_validate({
        **doc.model_dump(),
        "decisions": {
            **doc.decisions.model_dump(),
            "materials": {
                **doc.decisions.materials.model_dump(),
                "regions": [{"role": "structure", "type": "roof"}],
            },
        },
    })
    assert architecture_plan_from_document(doc)["materials"]["regions"] == [
        {"role": "structure", "type": "roof"},
    ]