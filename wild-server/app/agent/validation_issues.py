"""把文本校验结果转换成稳定、可序列化的修复问题协议。"""

from __future__ import annotations

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
    "validate_collision": "COLLISION",
    "validate_design_brief": "DESIGN_CONSTRAINT",
}

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
        output = str(_field(result, "output", "") or "")
        error_lines = [line.strip() for line in output.splitlines() if "❌" in line]
        if not error_lines:
            error_lines = [output.strip() or f"{validator} 校验失败"]

        for line in error_lines:
            marker = _ENTITY_MARKER.search(line)
            marker_id = marker.group(1) if marker else None
            entity_id = marker_id if marker_id in entities else None
            entity = entities.get(entity_id or "", {})
            message = line[:800]
            quota_match = _MISSING_QUOTA.search(message) if validator == "validate_design_brief" else None
            target_type = quota_match.group(1) if quota_match else None
            key = (validator, entity_id, message)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "code": _VALIDATOR_CODES.get(validator, validator.upper()),
                "validator": validator,
                "severity": "error",
                "entity_id": entity_id,
                "entity_type": entity.get("type") if entity else None,
                "message": message,
                "repair_mode": "model_tool" if entity_id or target_type else "manual",
                "suggested_tools": list(_TOOL_HINTS.get(validator, ["patch_entity"])),
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


def issue_fingerprints(issues: Iterable[dict]) -> set[tuple[str, str | None]]:
    """返回适合比较修复前后问题集合的稳定指纹。"""
    return {
        (str(issue.get("code", "UNKNOWN")), issue.get("entity_id"))
        for issue in issues
    }


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
