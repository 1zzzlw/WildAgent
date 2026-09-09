"""建筑设计文档、解析结果与版本化修改协议。"""

from .contracts import DesignDocument, DesignPatch, ResolvedDesign
from .repository import design_repository
from .resolver import (
    architecture_plan_from_document,
    build_design_document,
    resolve_design,
    render_design_svg,
)

__all__ = [
    "DesignDocument",
    "DesignPatch",
    "ResolvedDesign",
    "architecture_plan_from_document",
    "build_design_document",
    "design_repository",
    "resolve_design",
    "render_design_svg",
]
