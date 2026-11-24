"""材质归一化与程序化配方。"""
from __future__ import annotations

from agent.utils.blueprint.materials.plan import OBJECT_ROLE_SPECS
from agent.utils.blueprint.materials.plan import ROLE_SPECS
from agent.utils.blueprint.materials.plan import material_role_specs
from agent.utils.blueprint.materials.plan import resolve_material_plan
from agent.utils.blueprint.materials.recipes import infer_brick_preset
from agent.utils.blueprint.materials.recipes import resolve_brick_preset
from agent.utils.blueprint.materials.recipes import without_procedural_materials

__all__ = [
    "OBJECT_ROLE_SPECS",
    "ROLE_SPECS",
    "infer_brick_preset",
    "material_role_specs",
    "resolve_brick_preset",
    "resolve_material_plan",
    "without_procedural_materials",
]
