"""物件的**通用表达通道**：任意命名物件都能被表达与派发。

这组测试锁的是"通用性"，不是某个名字能不能通过：

1. 判据不依赖物件名词表（名字列不完），只依赖**闭集**：
   建筑类型闭集（目标判定）+ 四种几何方式闭集（形状表达）+ 图鉴预设闭集（精确几何）；
2. 三个通道（furniture / primitive / body）都能从方案一路走到计划条目；
3. 认不出来时**如实标记**，绝不用品类相近的预设顶替。
"""

from __future__ import annotations

import pytest

from app.agent.generation.components import (
    COMPONENT_REGISTRY,
    resolve_component_suggestions,
)
from app.agent.generation.objects.planning import (
    normalize_object_item,
    normalize_object_plan,
    normalize_primitive_part,
    parts_bounds,
)
from app.agent.generation.objects.subtypes import OBJECT_COMPONENT_KINDS
from app.agent.plan.capability import object_gap_items
from app.agent.plan.expand import expand_plan
from app.design.contracts import DesignDocument
from app.design.resolver import architecture_plan_from_document, is_object_plan

VASE = {
    "kind": "primitive",
    "name": "花瓶",
    "count": 1,
    "placement": "立于场景中央",
    "material": "stone",
    "parts": [
        {"shape": "cylinder", "radius": 0.09, "height": 0.36, "position": [0, 0.18, 0]},
        {
            "shape": "cylinder",
            "radiusBottom": 0.09,
            "radiusTop": 0.05,
            "height": 0.14,
            "position": [0, 0.43, 0],
        },
    ],
}

FIGURE = {
    "kind": "body",
    "name": "小人",
    "height": 1.72,
    "placement": "站在场景一侧、面向 +Z",
    "material": "accent",
    "params": {
        "height": 1.72,
        "build": "lean",
        "headShape": "oval",
        "armLength": 1.0,
        "legLength": 1.0,
        "cloakLength": 0.4,
        "hoodUp": False,
    },
}


# ── 通道声明 ──


def test_every_channel_is_a_registered_component_type():
    """通道名必须都是生成侧真的能派发的类型，否则方案批了也没人生成。"""

    for kind in OBJECT_COMPONENT_KINDS:
        config = COMPONENT_REGISTRY.get(kind)
        assert config is not None, f"通道 {kind} 没有注册"
        assert config.implemented
        assert config.is_element, "物件通道写进 geometry.elements，不是 components"


def test_generic_channels_are_never_dispatched_by_keyword():
    """通用通道**不能**靠关键词自动派发，否则又变成"靠名字表判定"。

    它们只能由设计清单的配额点名（物件方案里写了哪个 kind）。
    """

    for kind in ("primitive", "body"):
        assert list(COMPONENT_REGISTRY[kind].need_keywords) == []


# ── 形状参数归一化 ──


@pytest.mark.parametrize(
    "raw,ok",
    [
        ({"shape": "box", "dimensions": [0.4, 0.75, 0.8]}, True),
        ({"shape": "box"}, False),                                   # 缺必填几何参数
        ({"shape": "box", "dimensions": [0.4, 0, 0.8]}, False),      # 非正数
        ({"shape": "sphere", "radius": 0.12}, True),
        ({"shape": "sphere"}, False),
        ({"shape": "cylinder", "radius": 0.1, "height": 0.3}, True),
        ({"shape": "cylinder", "height": 0.3}, False),               # 圆柱必须给半径
        ({"shape": "cylinder", "radiusTop": 0.05, "radiusBottom": 0.1, "height": 0.3}, True),
        ({"shape": "cylinder", "radiusTop": 0.05, "height": 0.3}, False),  # 锥台半径必须成对
        ({"shape": "profile_sweep", "path": [[0, 0, 0], [1, 0, 0]]}, True),
        ({"shape": "profile_sweep", "path": [[0, 0, 0]]}, False),    # path 至少 2 点
        ({"shape": "torus", "radius": 0.1}, False),                  # 不在四种几何方式里
        ({"shape": "box", "dimensions": float("nan")}, False),
    ],
)
def test_primitive_part_is_accepted_only_when_geometry_is_complete(raw, ok):
    assert (normalize_primitive_part(raw) is not None) is ok


def test_primitive_part_keeps_geometry_verbatim_instead_of_guessing():
    """零件就是要交付的几何：只做取值域收口，不替模型改数值、改形状。"""

    part = normalize_primitive_part(
        {"shape": "box", "dimensions": [0.4, 0.75, 0.8], "position": [0, 0.375, 0]}
    )

    assert part == {
        "shape": "box",
        "dimensions": [0.4, 0.75, 0.8],
        "position": [0.0, 0.375, 0.0],
    }


def test_parts_bounds_is_derived_from_the_parts():
    bounds = parts_bounds(normalize_object_item(VASE, "生成一个花瓶")["parts"])

    assert bounds[0] == pytest.approx(0.18)    # 宽 = 最大圆柱直径（半径 0.09）
    assert bounds[2] == pytest.approx(0.5)     # 高 = 0 + 0.36 + 0.14


# ── 归一化分发（按"已给的表达"走，不按名字走）──


def test_kind_dispatch_covers_all_three_channels():
    assert normalize_object_item({"subtype": "table"}, "生成一个桌子")["kind"] == "furniture"
    assert normalize_object_item(VASE, "生成一个花瓶")["kind"] == "primitive"
    assert normalize_object_item(FIGURE, "生成一个小人")["kind"] == "body"


def test_kind_less_shorthand_with_shape_goes_to_the_generic_channel():
    item = normalize_object_item({"shape": "sphere", "radius": 0.12}, "生成一个球")

    assert item["kind"] == "primitive"
    assert item["parts"][0]["shape"] == "sphere"


def test_business_word_kind_is_not_guessed():
    """模型写业务名词当 kind（"couch"/"ornament"）时不猜语义。"""

    item = normalize_object_item({"kind": "ornament", "subtype": "table"}, "生成一个桌子")

    assert item["kind"] == "furniture"


def test_two_generic_objects_are_not_merged_into_one():
    """"花瓶"和"路灯"都是 primitive 且都没有 subtype，不能折成同一条。"""

    plan = normalize_object_plan(
        {
            "objects": [
                VASE,
                {
                    "kind": "primitive",
                    "name": "路灯",
                    "count": 2,
                    "parts": [
                        {"shape": "cylinder", "radius": 0.05, "height": 3.0, "position": [0, 1.5, 0]}
                    ],
                },
            ]
        },
        "生成一个花瓶和两盏路灯",
    )

    assert [item["name"] for item in plan["objects"]] == ["花瓶", "路灯"]


# ── 交付契约：空方案必须有缺口说明 ──


def _document(plan: dict) -> DesignDocument:
    return DesignDocument.model_validate(
        {
            "design_id": "design_t",
            "session_id": "sess_t",
            "revision": 1,
            "requirements": {"source_request": "生成一个东西", "building_type": "asset"},
            "decisions": {
                "kind": "object",
                "concept": plan.get("concept", ""),
                "objects": plan.get("objects", []),
                "unsupported_objects": plan.get("unsupported_objects", []),
            },
        }
    )


def test_empty_objects_is_legal_only_with_an_explicit_gap():
    with pytest.raises(ValueError):
        _document({"objects": [], "unsupported_objects": []})

    document = _document({"objects": [], "unsupported_objects": ["生成一个小人"]})
    assert document.decisions.unsupported_objects == ["生成一个小人"]


def test_duplicate_object_entries_are_rejected_by_name_not_only_subtype():
    with pytest.raises(ValueError):
        _document(
            {
                "objects": [
                    {"kind": "primitive", "name": "花瓶", "width": 0.2, "depth": 0.2, "height": 0.5},
                    {"kind": "primitive", "name": "花瓶", "width": 0.2, "depth": 0.2, "height": 0.5},
                ]
            }
        )


# ── 计划层：配额键 = kind，通用通道能被派发 ──


def _object_state(**overrides):
    plan = {
        "target_kind": "object",
        "concept": "一个花瓶和一个小人",
        "objects": [
            normalize_object_item(VASE, "生成一个花瓶"),
            normalize_object_item(FIGURE, "生成一个小人"),
        ],
        "unsupported_objects": [],
        "component_quota": {"primitive": {"min": 1, "max": 1}, "body": {"min": 1, "max": 1}},
        "required_components": ["primitive", "body"],
    }
    state = {
        "user_message": "生成一个花瓶和一个小人",
        "architecture_plan": plan,
        "suggested_components": list(plan["required_components"]),
        "design_brief": {"component_quota": plan["component_quota"]},
    }
    state.update(overrides)
    return state


def test_object_scene_never_falls_back_to_building_components():
    """"没有建议"在物件场景里等于"没有要生成的东西"，不能变成门/窗/屋顶。"""

    assert resolve_component_suggestions([], "生成一个花瓶", {}, object_scene=True) == []
    assert resolve_component_suggestions([], "生成一个别墅") == ["door", "window", "roof"]


def test_expand_dispatches_generic_channels_and_no_building_components():
    plan = expand_plan(_object_state())
    generated = [item.kind for item in plan.items_by_op("generate")]

    assert set(generated) == {"primitive", "body"}
    assert not ({"door", "window", "roof", "wall"} & set(generated))


def test_unsupported_object_becomes_a_terminal_item_not_a_substitute():
    """"表达不了"必须进交付清单，而不是被换成别的物件。"""

    state = _object_state(
        architecture_plan={
            "target_kind": "object",
            "concept": "生成一个小人",
            "objects": [],
            "unsupported_objects": ["生成一个小人"],
            "component_quota": {},
            "required_components": [],
        },
        suggested_components=[],
        design_brief={"component_quota": {}},
    )

    plan = expand_plan(state)
    assert plan.items_by_op("generate") == []
    unsupported = [
        item for item in plan.items
        if item.status == "unsupported" and item.kind == "object_expression"
    ]
    assert len(unsupported) == 1
    assert "生成一个小人" in unsupported[0].run.evidence
    # 终态：不会被调度
    assert unsupported[0] in plan.items


def test_object_gap_items_is_empty_without_unsupported_objects():
    assert object_gap_items({"target_kind": "object", "objects": []}) == []
    assert object_gap_items(None) == []


def test_back_compiled_quota_keys_follow_the_object_kinds():
    """方案 → 生成侧协议的折算按 kind 走，不认识"某个具体物件"，只认识通道。"""

    document = _document(
        {
            "concept": "一个花瓶和一个小人",
            "objects": [
                normalize_object_item(VASE, "生成一个花瓶"),
                normalize_object_item(FIGURE, "生成一个小人"),
            ],
        }
    )
    plan = architecture_plan_from_document(document)

    assert is_object_plan(plan) is True
    assert set(plan["component_quota"]) == {"primitive", "body"}
    body_quota = plan["component_quota"]["body"]
    assert (body_quota["min"], body_quota["max"]) == (1, 1)
    assert set(plan["required_components"]) == {"primitive", "body"}
