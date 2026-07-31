"""Tools 模块 —— Agent 工具集

现在：spatial_tools（空间校验 + 自动修正）
以后：design_tools、scene_read_tools 等按需扩展

所有导出对象都是 @tool 装饰函数，可以被 LangChain Agent 或 LangGraph 节点调用。
这里保留的是早期公共导出子集；当前 AgentService 会从 spatial_tools 直接导入完整工具集。
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
