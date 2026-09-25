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
