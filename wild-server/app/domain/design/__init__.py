"""建筑设计文档、解析结果与版本化修改协议。"""

from app.domain.design.contracts import DesignDocument
from app.domain.design.contracts import DesignPatch
from app.domain.design.contracts import ResolvedDesign
from app.domain.design.resolver import architecture_plan_from_document
from app.domain.design.resolver import build_design_document
from app.domain.design.resolver import resolve_design
from app.domain.design.resolver import render_design_svg

__all__ = [
    "DesignDocument",
    "DesignPatch",
    "ResolvedDesign",
    "architecture_plan_from_document",
    "build_design_document",
    "resolve_design",
    "render_design_svg",
]
