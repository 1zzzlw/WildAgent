"""把设计审核决定整理成设计领域字段。

本模块只处理 `app.design` 领域对象，不依赖 `app.agent`：
计划层字段与执行进度由审核节点自己拼接，避免 design 反向依赖 agent。
"""

from __future__ import annotations

from typing import Any

from app.design.contracts import DesignDocument
from app.design.resolver import architecture_plan_from_document, resolve_design


def build_design_review_interrupt(
    document: DesignDocument,
    resolved: Any,
) -> dict[str, Any]:
    """构造交给前端的人工审核请求。"""

    return {
        "type": "design_review",
        "question": "请审核建筑设计，然后在恢复输入中批准或提出修改意见。",
        "document": document.model_dump(mode="json"),
        "resolved": resolved.model_dump(mode="json"),
        "preview_url": (
            f"/api/designs/{document.session_id}/preview.svg?revision={document.revision}"
        ),
        "resume_examples": {
            "confirm": {"action": "confirm"},
            "revise": {
                "action": "revise",
                "feedback": "请填写需要修改的建筑设计内容",
            },
        },
    }


def _resolved_material_plan(
    document: DesignDocument,
    material_fallback: Any,
) -> Any:
    """文档已解析材质时用文档结果，否则保留当前 State 中的材质方案。"""

    resolved_plan = document.decisions.materials.resolved_plan
    if resolved_plan is None:
        return material_fallback
    return resolved_plan.model_dump(mode="json")


def approved_design_fields(
    approved: DesignDocument,
    approved_resolved: Any,
    *,
    material_fallback: Any = None,
) -> dict[str, Any]:
    """用户批准后需要写回 State 的设计领域字段。"""

    return {
        "design_document": approved.model_dump(mode="json"),
        "resolved_design": approved_resolved,
        "architecture_plan": architecture_plan_from_document(approved),
        "material_plan": _resolved_material_plan(approved, material_fallback),
        "design_review_status": "approved",
        "design_feedback": "",
    }


def revision_design_fields(
    document: DesignDocument,
    feedback: str,
    *,
    material_fallback: Any = None,
) -> dict[str, Any]:
    """用户要求修改时保留当前文档并记录修改意见。"""

    return {
        "design_document": document.model_dump(mode="json"),
        "resolved_design": resolve_design(document).model_dump(mode="json"),
        "architecture_plan": architecture_plan_from_document(document),
        "material_plan": _resolved_material_plan(document, material_fallback),
        "design_review_status": "revise",
        "design_feedback": feedback,
    }
