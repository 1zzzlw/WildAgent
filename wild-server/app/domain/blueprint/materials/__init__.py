"""材质计划归一化与程序化配方；模型规划位于 Agent 工作流。"""
from __future__ import annotations

from app.domain.blueprint.materials.plan import OBJECT_ROLE_SPECS
from app.domain.blueprint.materials.plan import ROLE_SPECS
from app.domain.blueprint.materials.plan import compact_asset_catalog
from app.domain.blueprint.materials.plan import material_role_specs
from app.domain.blueprint.materials.plan import resolve_material_plan
from app.domain.blueprint.materials.recipes import compact_procedural_catalog
from app.domain.blueprint.materials.recipes import infer_brick_preset
from app.domain.blueprint.materials.recipes import resolve_brick_preset
from app.domain.blueprint.materials.recipes import without_procedural_materials

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
