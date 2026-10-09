"""设计完善与视觉修订共用的块级补丁权限边界。"""
from __future__ import annotations

from copy import deepcopy
from app.design.contracts import DesignDocument
from app.design.completeness import value_at
from app.design.normalization import without_null_fields
from app.design.resolver import architecture_plan_from_document, build_design_document
from .design_blocks import ordered_blocks


def apply_design_patch(current: DesignDocument, patch: dict, *, allowed_blocks: list[str],
                       user_message: str, complexity_profile, architecture_profile):
    """返回候选文档及归一化、派生字段记录；不修改输入或编译候选。"""
    from .planning import normalize_architecture_plan

    plan = architecture_plan_from_document(current)
    patch = deepcopy(patch)
    allowed: set[str] = set()
    for block in ordered_blocks("standard"):
        if block.name in allowed_blocks:
            allowed.update(f for f in block.fields if f != "design_constraints")
    if "design_constraints" in patch and patch["design_constraints"] != plan.get(
            "design_constraints"):
        raise ValueError("补丁试图改变采用决定，已拒绝")
    patch.pop("design_constraints", None)
    if set(patch) - allowed:
        raise ValueError(f"补丁包含未授权设计字段 {sorted(set(patch) - allowed)}")
    if not patch:
        raise ValueError("补丁为空")

    merged = {**plan, **patch}
    normalization_changes: list[dict] = []
    normalized = normalize_architecture_plan(
        merged, user_message=user_message, complexity_profile=complexity_profile,
        architecture_profile=architecture_profile,
        normalization_changes=normalization_changes, input_source="model",
    )
    # 派生字段是既有确定性结果，记录但不要求第二个模型去抄。
    derived = {"component_quota", "required_components", "detail_packages",
               "balcony_access_count", "balcony_width"}
    semantic_roots = {"massing", "volumes", "roof", "facades", "structural_grid",
                      "circulation", "components", "curtain_wall", "materials", "design_intent"}
    for field in semantic_roots - allowed:
        if field in normalized and without_null_fields(normalized[field]) != without_null_fields(plan.get(field)):
            raise ValueError(f"归一化越权修改 {field}，保留当前设计")
    derived_changes = {key: {"before": plan.get(key), "after": normalized[key]}
                       for key in derived if key in normalized and normalized[key] != plan.get(key)}
    normalized = {**plan, **{k: v for k, v in normalized.items() if k in allowed | derived}}
    normalized["design_constraints"] = plan["design_constraints"]
    normalized["normalization_changes"] = normalization_changes
    candidate = build_design_document(
        normalized, session_id=current.session_id,
        source_request=current.requirements.source_request,
        building_type=current.requirements.building_type,
        style_intent=current.requirements.style_intent, previous=current,
    )
    for lock in current.locks:
        if value_at(current.model_dump(mode="json"), lock) != value_at(
                candidate.model_dump(mode="json"), lock):
            raise ValueError(f"补丁修改锁定字段 {lock}")
    if candidate.decisions == current.decisions:
        raise ValueError("没有有效设计变化")
    return candidate, normalization_changes, derived_changes
