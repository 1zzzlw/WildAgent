"""把文本校验结果转换成稳定、可序列化的修复问题协议。"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable


_ENTITY_MARKER = re.compile(r"[❌⚠️]\s*\[(?:component:)?([\w.-]+)\]")

_VALIDATOR_CODES = {
    "validate_blueprint_structure": "BLUEPRINT_STRUCTURE",
    "validate_element_required_fields": "REQUIRED_FIELD",
    "validate_reference_integrity": "REFERENCE_INTEGRITY",
    "validate_opening_coords": "OPENING_COORDINATES",
    "validate_opening_fit": "OPENING_FIT",
    "validate_wall_junctions": "WALL_JUNCTION",
    "validate_stair_alignment": "STAIR_ALIGNMENT",
    "validate_roof_coverage": "ROOF_COVERAGE",
    "validate_element_dimensions": "ELEMENT_DIMENSIONS",
    "validate_model_quality": "MODEL_QUALITY",
    "validate_collision": "COLLISION",
    "validate_design_brief": "DESIGN_CONSTRAINT",
}

_ISSUE_CLASSIFICATION = {
    "validate_blueprint_structure": ("schema_contract", "validator"),
    "validate_element_required_fields": ("schema_contract", "prompt"),
    "validate_reference_integrity": ("host_relation", "validator"),
    "validate_opening_coords": ("coordinate_frame", "deterministic_fix"),
    "validate_opening_fit": ("host_relation", "deterministic_fix"),
    "validate_wall_junctions": ("coordinate_frame", "deterministic_fix"),
    "validate_stair_alignment": ("level_continuity", "deterministic_fix"),
    "validate_roof_coverage": ("coverage_geometry", "deterministic_fix"),
    "validate_element_dimensions": ("schema_contract", "deterministic_fix"),
    "validate_model_quality": ("model_instruction", "prompt"),
    "validate_collision": ("coverage_geometry", "deterministic_fix"),
    "validate_design_brief": ("model_instruction", "prompt"),
}


def classify_validation_issue(validator: str) -> tuple[str, str]:
    """将不断增长的具体错误收敛到有限根因类别和修复层级。"""
    if validator in _ISSUE_CLASSIFICATION:
        return _ISSUE_CLASSIFICATION[validator]
    if validator.startswith("validate_") and validator.endswith("_placement"):
        return "host_relation", "deterministic_fix"
    return "schema_contract", "validator"

_TOOL_HINTS = {
    "validate_element_required_fields": ["patch_entity"],
    "validate_reference_integrity": ["set_material_reference", "reparent_opening"],
    "validate_opening_coords": ["move_opening", "reparent_opening"],
    "validate_opening_fit": ["move_opening", "resize_opening", "reparent_opening"],
    "validate_wall_junctions": ["patch_entity"],
    "validate_stair_alignment": ["patch_entity"],
    "validate_roof_coverage": ["patch_entity"],
    "validate_element_dimensions": ["patch_entity"],
    "validate_collision": ["move_opening", "resize_opening", "patch_entity"],
    "validate_design_brief": ["add_entity"],
}

_MISSING_QUOTA = re.compile(r"\b([a-z_]+)\s+数量\s+\d+\s+少于设计下限")
_FACADE_OVERAGE = re.compile(
    r"墙\s+([\w.-]+)\s+有\s+\d+\s+个门窗，超过立面上限\s+\d+"
)


def _field(result: object, name: str, default=None):
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _entity_index(blueprint: dict) -> dict[str, dict]:
    geometry = blueprint.get("geometry", {})
    entities = [
        *geometry.get("elements", []),
        *geometry.get("components", []),
    ]
    return {
        entity["id"]: entity
        for entity in entities
        if isinstance(entity, dict) and entity.get("id")
    }


def validation_issues_from_results(
    results: Iterable[object],
    blueprint: dict,
) -> list[dict]:
    """将最终校验器输出拆为逐行问题，并尽可能绑定到具体实体。"""
    entities = _entity_index(blueprint)
    issues: list[dict] = []
    seen: set[tuple[str, str | None, str]] = set()

    for result in results:
        if not _field(result, "has_error", False):
            continue
        validator = str(_field(result, "name", "unknown")).replace(" [recheck]", "")
        category, repair_level = classify_validation_issue(validator)
        output = str(_field(result, "output", "") or "")
        error_lines = [line.strip() for line in output.splitlines() if "❌" in line]
        if not error_lines:
            error_lines = [output.strip() or f"{validator} 校验失败"]

        for line in error_lines:
            facade_match = (
                _FACADE_OVERAGE.search(line)
                if validator == "validate_design_brief"
                else None
            )
            marker = _ENTITY_MARKER.search(line)
            marker_id = facade_match.group(1) if facade_match else (
                marker.group(1) if marker else None
            )
            entity_id = marker_id if marker_id in entities else None
            entity = entities.get(entity_id or "", {})
            message = line[:800]
            quota_match = _MISSING_QUOTA.search(message) if validator == "validate_design_brief" else None
            target_type = quota_match.group(1) if quota_match else None
            related_entity_ids = []
            if facade_match and entity_id:
                related_entity_ids = [
                    candidate_id
                    for candidate_id, candidate in entities.items()
                    if candidate.get("type") in {"door", "window"}
                    and candidate.get("parentWall") == entity_id
                ]
            suggested_tools = (
                ["remove_entity", "reparent_opening"]
                if facade_match
                else list(_TOOL_HINTS.get(validator, ["patch_entity"]))
            )
            key = (validator, entity_id, message)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "code": _VALIDATOR_CODES.get(validator, validator.upper()),
                "category": category,
                "validator": validator,
                "severity": "error",
                "entity_id": entity_id,
                "entity_type": entity.get("type") if entity else None,
                "related_entity_ids": related_entity_ids,
                "message": message,
                "repair_mode": "model_tool" if entity_id or target_type else "manual",
                "recommended_repair_level": repair_level,
                "suggested_tools": suggested_tools,
                "repair_target": f"design:{target_type}" if target_type else None,
                "target_type": target_type,
            })

    return issues


def group_issues_by_entity(issues: Iterable[dict]) -> dict[str, list[dict]]:
    """按实体 ID 聚合问题；没有实体归属的全局问题不会进入模型局部修复。"""
    grouped: dict[str, list[dict]] = {}
    for issue in issues:
        entity_id = issue.get("entity_id")
        if entity_id:
            grouped.setdefault(entity_id, []).append(issue)
    return grouped


def _issue_fingerprint(issue: dict) -> tuple[str, str | None, str]:
    """单个问题的稳定指纹。

    仅用 ``(code, entity_id)`` 无法区分同一校验器在同一实体上的不同错误：
    例如同一扇门“超出墙右端”与修复后新出现的“与窗重叠”都落在
    ``OPENING_FIT`` 上，旧错误换新错误会通过复检。加入消息哈希后，
    只有错误消息本身减少才算改善。
    """
    code = str(issue.get("code", "UNKNOWN"))
    entity_id = issue.get("entity_id")
    message = str(issue.get("message", "") or "")
    digest = hashlib.sha1(message.encode("utf-8", errors="replace")).hexdigest()[:12]
    return code, entity_id, digest


def issue_fingerprints(issues: Iterable[dict]) -> set[tuple[str, str | None, str]]:
    """返回适合比较修复前后问题集合的稳定指纹。"""
    return {_issue_fingerprint(issue) for issue in issues}


def compare_issue_sets(before: list[dict], after: list[dict]) -> dict:
    """只有错误严格减少且未引入新类型/实体组合时才允许提交修复。"""
    before_fingerprints = issue_fingerprints(before)
    after_fingerprints = issue_fingerprints(after)
    introduced = sorted(
        after_fingerprints - before_fingerprints,
        key=lambda item: (item[0], item[1] or ""),
    )
    return {
        "accepted": len(after) < len(before) and not introduced,
        "before_count": len(before),
        "after_count": len(after),
        "introduced_issues": introduced,
    }
