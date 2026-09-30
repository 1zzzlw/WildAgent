"""分片合并的分桶契约：**发到哪个桶由注册表的 `is_element` 决定，不看类型名**。

这条契约曾经是硬编码的 `item_type == "roof"`，家具因此被并进 `geometry.components`；
而对账（`plan/reconcile._landed_count`）与组件校验都按 `is_element` 去
`geometry.elements` 里找。两边错位的后果不是报错，而是**条目永远判不到产物已落地**，
于是一直重试到放弃——用户明明拿到了家具，系统却认为什么都没生成出来。

所以这里不只钉 roof 与 furniture 两个已知类型，而是把**整张注册表**都过一遍：
以后新增 element 类型时，这条测试会立刻失败，而不是等线上出现"生成成功却重试到放弃"。
"""

from __future__ import annotations

import pytest

from app.agent.generation.components import COMPONENT_REGISTRY
from app.utils.fragment_merger import merge_fragment_batch, merge_fragments

_ELEMENT_TYPES = {name for name, config in COMPONENT_REGISTRY.items() if config.is_element}
_COMPONENT_TYPES = set(COMPONENT_REGISTRY) - _ELEMENT_TYPES


def _empty_skeleton() -> dict:
    return {
        "meta": {"name": "bucket-test"},
        "geometry": {"elements": [], "components": []},
    }


def _buckets(blueprint: dict) -> tuple[set[str], set[str]]:
    geometry = blueprint["geometry"]
    return (
        {item["type"] for item in geometry["elements"]},
        {item["type"] for item in geometry["components"]},
    )


def test_merge_puts_every_kind_in_the_bucket_its_registry_declares():
    fragments = [{"type": name, "id": f"{name}_1"} for name in sorted(COMPONENT_REGISTRY)]

    elements, components = _buckets(merge_fragments(_empty_skeleton(), fragments))

    assert elements == _ELEMENT_TYPES
    assert components == _COMPONENT_TYPES


def test_incremental_merge_uses_the_same_bucket_rule():
    fragments = [{"type": name, "id": f"{name}_1"} for name in sorted(COMPONENT_REGISTRY)]

    elements, components = _buckets(merge_fragment_batch(_empty_skeleton(), fragments))

    assert elements == _ELEMENT_TYPES
    assert components == _COMPONENT_TYPES


def test_furniture_lands_where_reconcile_looks_for_it():
    """对账只认 `is_element` 那一桶：分桶写错的直接症状就是这条断言失败。"""

    from app.agent.plan.reconcile import _landed_count

    blueprint = merge_fragments(
        _empty_skeleton(), [{"type": "furniture", "id": "furniture_table_1"}]
    )
    geometry = blueprint["geometry"]

    assert _landed_count("furniture", geometry["elements"], geometry["components"]) == 1


def test_roof_bucket_is_unchanged_by_the_refactor():
    """roof 的历史行为必须一字不变：它是修复前的唯一 element 类型。"""

    blueprint = merge_fragments(_empty_skeleton(), [{"type": "roof", "id": "roof_main"}])

    elements, components = _buckets(blueprint)
    assert elements == {"roof"}
    assert components == set()


@pytest.mark.parametrize("item_type", ["wall", "floor", "openings"])
def test_unknown_types_still_go_to_components(item_type):
    """注册表里没有的类型按组合构件处理：骨架自带主体不经合并，走的不是这条路。"""

    blueprint = merge_fragments(_empty_skeleton(), [{"type": item_type, "id": f"{item_type}_1"}])

    elements, components = _buckets(blueprint)
    assert elements == set()
    assert components == {item_type}


def test_string_numbers_in_model_fragments_are_normalized():
    """模型 JSON 的字符串数字必须在合并入口归一成 number。

    实测事故：真模型产出的 column 元素 base=[3.0, "0.0", 2.0]——Python 侧校验器
    （_aabb 加固后）能宽容通过，但 wild-core 引擎的 schema 只认 number，
    parseBlueprint 直接拒收整份蓝图 ⇒ 渲染重建全部失败。
    "校验器全绿 ≠ 引擎能重建"的这一变体，正解是在合并入口归一。
    """

    column = {
        "type": "column",
        "id": "column_porch_01",
        "base": [3.0, "0.0", "2.0"],
        "height": "3.6",
        "bottomRadius": 0.24,
        "topRadius": "0.2",
        "style": "corinthian",
    }
    blueprint = merge_fragments(_empty_skeleton(), [column])

    (merged,) = blueprint["geometry"]["elements"]
    assert merged["base"] == [3.0, 0.0, 2.0]
    assert all(isinstance(v, float) for v in merged["base"])
    assert merged["height"] == 3.6
    assert merged["topRadius"] == 0.2
    # 非几何字段不许被顺手转换：style 是语义字符串
    assert merged["style"] == "corinthian"

    # 增量路径（merge_fragment_batch）与首并路径同口径
    incremental = merge_fragment_batch(_empty_skeleton(), [dict(column)])
    (merged_inc,) = incremental["geometry"]["elements"]
    assert merged_inc["base"] == [3.0, 0.0, 2.0]

    # dimensions 表里的字符串数字也要归一（furniture 走这条路；注册表里它是 element）
    furniture = {
        "type": "furniture",
        "id": "furn_1",
        "position": [1, "2", 3],
        "dimensions": {"width": "1.5", "depth": 0.8, "height": "0.75"},
    }
    blueprint2 = merge_fragments(_empty_skeleton(), [furniture])
    (merged_f,) = blueprint2["geometry"]["elements"]
    assert merged_f["dimensions"] == {"width": 1.5, "depth": 0.8, "height": 0.75}
    assert merged_f["position"] == [1.0, 2.0, 3.0]


def test_unparseable_strings_pass_through_untouched():
    """转不动的字符串不是数值抖动，原样保留（不能把语义文本吃掉）。"""

    weird = {
        "type": "furniture",
        "id": "furn_x",
        "height": "auto",
        "position": [1, "two", 3],
    }
    blueprint = merge_fragments(_empty_skeleton(), [weird])
    (merged,) = blueprint["geometry"]["elements"]
    assert merged["height"] == "auto"
    assert merged["position"] == [1.0, "two", 3.0]
