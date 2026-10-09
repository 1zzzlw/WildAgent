"""P5-A：逐体量屋顶。

验收口径（来自 `P5-扩展建筑设计表达.md`）：**两个只在一个设计变量上不同的方案，
必须在最终实体上出现对应差异，其它设计保持**。所以这里的每条断言都比"实体里有
roofType"更强 —— 只多一个设计变量，就多一处实体差异。
"""
import copy

import pytest

from app.agent.compiler import compile_design
from app.agent.generation.architecture import normalize_architecture_plan
from app.agent.generation.architecture.facade import _planned_roof_slots

# 两个只在屋顶上不同的体量组合：主楼 12×10、侧翼 6×6，都在 1~2 层。
_PLAN = {
    "massing": {"shape": "l_shape", "width": 20, "depth": 15, "floors": 2},
    "volumes": [
        {"id": "main", "role": "primary", "x": 0, "z": 0,
         "width": 12, "depth": 10, "start_floor": 1, "end_floor": 2},
        {"id": "wing", "role": "secondary", "x": 12, "z": 0,
         "width": 6, "depth": 6, "start_floor": 1, "end_floor": 2},
    ],
    "roof": {"type": "gable", "overhang": 0.6},
}


def compile_roof(roof):
    plan = copy.deepcopy(_PLAN)
    plan["roof"] = roof
    normalized = normalize_architecture_plan(plan, "L 形住宅")
    return compile_design(normalized, user_message="L 形住宅")


def roofs_of(result):
    return [
        item for item in result.blueprint["geometry"]["elements"]
        if item.get("type") == "roof"
    ]


def slots_by_volume(result):
    return {
        slot.get("volume"): slot
        for slot in (result.design_brief.get("roof_slots") or [])
    }


# ── 核心：一个设计变量 ⇒ 一处实体差异 ──────────────────────────────


def test_per_volume_override_changes_only_that_volume_roof():
    """主楼 gable + 侧翼 flat：两块屋面各按自己的形态生成。"""

    baseline = compile_roof({"type": "gable", "overhang": 0.6})
    override = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat"}],
    })
    assert [item["roofType"] for item in roofs_of(baseline)] == ["gable", "gable"]
    assert [item["roofType"] for item in roofs_of(override)] == ["gable", "flat"]
    # 未被覆盖的体量：位置与跨度**逐字段不变**（证明"只多一个设计变量"）。
    assert roofs_of(override)[0]["position"] == roofs_of(baseline)[0]["position"]
    assert roofs_of(override)[0]["span"] == roofs_of(baseline)[0]["span"]


def test_per_volume_overhang_changes_only_that_volume_span():
    baseline = compile_roof({"type": "gable", "overhang": 0.6})
    override = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "overhang": 0.2}],
    })
    wing_baseline = next(
        item for item in roofs_of(baseline)
        if item["position"][0] > 10
    )
    wing_override = next(
        item for item in roofs_of(override)
        if item["position"][0] > 10
    )
    assert wing_override["span"] < wing_baseline["span"]
    main_baseline = next(
        item for item in roofs_of(baseline) if item["position"][0] <= 10
    )
    main_override = next(
        item for item in roofs_of(override) if item["position"][0] <= 10
    )
    assert main_override["span"] == main_baseline["span"]


def test_flat_override_gets_zero_ridge_height():
    """flat 的脊高必须是 0 —— 派生规则按 roofType 判，不是按"这块是不是默认那块"。"""

    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat"}],
    })
    heights = {item["roofType"]: item["height"] for item in roofs_of(result)}
    assert heights["flat"] == 0.0
    assert heights["gable"] > 0.0


# ── 旧文档迁移等价 ────────────────────────────────────────────────


def test_empty_overrides_reproduce_the_pre_p5_blueprint_exactly():
    """🔴 迁移红线：不加这个字段时，产物必须与引入前**逐字段相同**。"""

    legacy = compile_roof({"type": "gable", "overhang": 0.6})
    with_empty = compile_roof({"type": "gable", "overhang": 0.6, "volumes": []})
    assert roofs_of(with_empty) == roofs_of(legacy)


def test_unknown_volume_is_warned_and_falls_back_to_the_template():
    """非法宿主：记缺陷、**不阻断**，产物退回整栋模板且仍合法。"""

    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "nope", "type": "flat"}],
    })
    codes = [item for item in result.defects if item.code == "roof_override_unknown_volume"]
    assert codes and all(item.severity == "warn" for item in codes)
    assert result.ok, "有兜底就不许把合法产物判失败"
    assert [item["roofType"] for item in roofs_of(result)] == ["gable", "gable"]


def test_conflicting_overrides_are_reported_once():
    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [
            {"volume": "wing", "type": "flat"},
            {"volume": "wing", "type": "hip"},
        ],
    })
    assert [item.code for item in result.defects if "conflict" in item.code]
    assert result.ok


# ── 门禁①改成逐体量判定 ──────────────────────────────────────────


def test_unsplittable_template_still_blocks_split():
    """dome 是整栋造型，不能按体量切 ⇒ 没有槽位，单块屋顶（既有行为不变）。"""

    assert _planned_roof_slots(
        {"roof": {"type": "dome", "overhang": 0.6}}, _REALIZATION,
    ) == []


def test_unsplittable_override_reports_a_compile_blocker():
    """不能用整体包围盒伪造多体量屋面；未支持的组合必须显式阻断。"""

    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "dome"}],
    })
    assert not roofs_of(result)
    assert any(d.code == "roof_layout_unsupported" and d.severity == "error" for d in result.defects)


_REALIZATION = {
    "modeled_floors": 2,
    "floor_height": 3.2,
    "volumes": _PLAN["volumes"],
}


# ── 槽位把体量与形态一起下发 ──────────────────────────────────────


def test_slots_carry_volume_and_roof_type():
    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat", "overhang": 0.25}],
    })
    slots = slots_by_volume(result)
    assert slots["wing"]["roofType"] == "flat"
    assert slots["main"]["roofType"] == "gable"
    # 同为 0~2m 契约；相邻内边不出檐，外侧忠实保留 1.5m。
    clamped = slots_by_volume(compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "overhang": 1.5}],
    }))
    assert clamped["wing"]["span"] == pytest.approx(6 + 1.5, abs=1e-6)
    # 显式零出檐不能被默认值或夹取吞掉。
    floored = slots_by_volume(compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "overhang": 0.0}],
    }))
    assert floored["wing"]["span"] == pytest.approx(6, abs=1e-6)


def test_out_of_contract_overhang_is_dropped_by_validation_not_by_the_clamp():
    """🔴 两条不同的通道，别混：契约范围（0~2）由 pydantic 拒、编译器钳制（0.15~0.8）
    在契约之内生效。超范围的整条覆盖被丢 ⇒ 退回模板，不是被钳到上限。"""

    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat", "overhang": 9.0}],
    })
    slots = slots_by_volume(result)
    assert slots["wing"]["roofType"] == "gable", "超范围让整条覆盖失效，不是只丢 overhang"
    assert slots["wing"]["span"] == pytest.approx(6 + 0.6, abs=1e-6)


def test_repeated_compile_is_stable():
    """重复编译同方案结果稳定（P5 每批验收条件之一）。"""

    first = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat", "overhang": 0.25}],
    })
    second = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat", "overhang": 0.25}],
    })
    assert roofs_of(first) == roofs_of(second)
    assert slots_by_volume(first) == slots_by_volume(second)


def test_blueprint_stays_valid_with_mixed_roof_types():
    """交付流水线必须仍然全绿（覆盖引入的是 warn，不是缺陷）。"""

    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": "flat"}],
    })
    assert result.ok
    assert not [item for item in result.defects if item.severity == "error"]


@pytest.mark.parametrize("roof_type", ["gable", "hip", "flat"])
def test_every_splittable_type_is_accepted_per_volume(roof_type):
    result = compile_roof({
        "type": "gable", "overhang": 0.6,
        "volumes": [{"volume": "wing", "type": roof_type}],
    })
    assert result.ok
    assert result.blueprint["geometry"]["elements"]
    types = [item["roofType"] for item in roofs_of(result)]
    assert types == ["gable", roof_type]
