"""材质域：材质计划的归一化、程序化配方与材质规划节点。

节点入口 ``material_planner`` 见 :mod:`.workflow` —— **不在此 re-export**：
那个模块依赖模型客户端与资产存储，包初始化不该把它们拉起来（对齐
``generation.architecture`` 的做法）。
"""
from __future__ import annotations

from .plan import (
    OBJECT_ROLE_SPECS,
    ROLE_SPECS,
    compact_asset_catalog,
    material_role_specs,
    resolve_material_plan,
)
from .recipes import (
    compact_procedural_catalog,
    infer_brick_preset,
    resolve_brick_preset,
    without_procedural_materials,
)

__all__ = [
    "OBJECT_ROLE_SPECS",
    "ROLE_SPECS",
    "compact_asset_catalog",
    "compact_procedural_catalog",
    "infer_brick_preset",
    "material_role_specs",
    "resolve_brick_preset",
    "resolve_material_plan",
    "without_procedural_materials",
]
