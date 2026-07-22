"""Tools 模块 —— Agent 工具集

现在：spatial_tools（空间校验 + 自动修正）
以后：design_tools、scene_read_tools 等按需扩展

所有工具都是 @tool 装饰的纯函数，可以被 LangChain Agent 或 LangGraph 节点调用。
"""
from app.tools.spatial_tools import (
    validate_opening_coords,
    validate_wall_junctions,
    validate_roof_coverage,
    validate_stair_alignment,
    validate_blueprint_structure,
    validate_element_required_fields,
    fix_opening_coords,
)

__all__ = [
    "validate_opening_coords",
    "validate_wall_junctions",
    "validate_roof_coverage",
    "validate_stair_alignment",
    "validate_blueprint_structure",
    "validate_element_required_fields",
    "fix_opening_coords",
]
