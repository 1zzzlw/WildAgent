"""建筑设计文档、解析结果与版本化修改协议。"""

from agent.utils.design.contracts import DesignDocument
from agent.utils.design.contracts import DesignPatch
from agent.utils.design.contracts import ResolvedDesign
from agent.utils.design.resolver import architecture_plan_from_document
from agent.utils.design.resolver import build_design_document
from agent.utils.design.resolver import resolve_design

__all__ = [
    "DesignDocument",
    "DesignPatch",
    "ResolvedDesign",
    "architecture_plan_from_document",
    "build_design_document",
    "resolve_design",
]
