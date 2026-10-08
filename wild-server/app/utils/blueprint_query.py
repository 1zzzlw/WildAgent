"""蓝图的只读查询：不改数据、不校验，只回答"关于蓝图结构"的问题。

与同目录两个模块的分工：

- :mod:`app.utils.blueprint_parser`：解析（蓝图 → 内部结构）；
- :mod:`app.utils.blueprint_normalizer`：写回（把蓝图修复为可交付形态）；
- 本模块：**读**。任何"问蓝图一个问题"的工具函数放这里，保持纯函数、无 IO。
"""
from __future__ import annotations

from typing import Any


def has_scene_content(blueprint: Any) -> bool:
    """是否真的存在可编辑场景内容：按 elements/components 判空，而非 blueprint dict 的 truthiness。

    前端在新建/清空场景时可能传一个"空蓝图骨架"（有 meta/geometry/materials 键、
    elements=[]、components=[]），`bool(骨架)` 是 True，会把"没有场景"误判成"有场景"，
    于是空场景下的"生成一个玻璃幕墙"被当成 edit（`normalize_intent_decision` 里
    `edit && !has_current_scene → chat` 的兜底因此不触发）。
    """
    if not isinstance(blueprint, dict):
        return False
    geometry = blueprint.get("geometry")
    if not isinstance(geometry, dict):
        return False
    elements = geometry.get("elements")
    components = geometry.get("components")
    return bool(elements) or bool(components)


__all__ = ["has_scene_content"]
