"""设计示意投影；保留离线视觉修订使用的旧编译适配器。"""

from __future__ import annotations

from collections import Counter

from app.domain.design.contracts import DesignDocument
from app.domain.design.contracts import ResolvedDesign
from app.domain.design.contracts import ResolvedLevel

RESOLVER_VERSION = "drawing-projection/1"


def compile_document(document: DesignDocument):
    # Lazy boundary: the compiler consumes plan data and never imports this adapter.
    from app.domain.compilation import compile_design
    from app.domain.design.resolver import architecture_plan_from_document

    materials = document.decisions.materials.resolved_plan
    return compile_design(
        architecture_plan_from_document(document),
        user_message=document.requirements.source_request,
        material_plan=materials.model_dump(mode="json") if materials else None,
        normalized_input=True,
    )


def project_drawing(document: DesignDocument) -> ResolvedDesign:
    """从同一空间解析结果生成图纸、任务宿主和确定性主体，版本始终为1。"""
    from app.domain.design.resolver import _stable_hash
    from app.domain.design.markers import component_markers
    from app.domain.design.spatial import execution_view, resolve_geometry
    from app.domain.design.coordinates import (
        DesignCoordinateConflict,
        opening_coordinate_errors,
    )
    from app.domain.design.layout import (
        floor_circulation_checks,
        opening_partition_conflicts,
    )
    from app.domain.design.coordinates import (
        design_relation_checks,
        floor_layout_conflicts,
        stair_span_conflicts,
    )

    data = document.decisions.model_dump(mode="json")
    geometry = resolve_geometry(data)
    drawing = execution_view(data, geometry)
    markers = component_markers(document, geometry)
    hosts = {host["id"]: host for host in geometry["hosts"]}
    errors = []
    for code, messages in (
        ("design_floor_layout_conflict", floor_layout_conflicts(drawing)),
        ("design_stair_span_conflict", stair_span_conflicts(drawing)),
        ("design_opening_conflict", opening_coordinate_errors(markers)),
    ):
        errors.extend(
            {"code": code, "path": "/decisions", "reason": message}
            for message in messages
        )
    relation_errors, relation_reviews = design_relation_checks(drawing, markers, hosts)
    errors.extend(relation_errors)
    circulation_errors, reviews = floor_circulation_checks(drawing, markers, hosts)
    reviews.extend(relation_reviews)
    for relation in data.get("relations", []):
        reviews.append(
            {
                "marker_id": relation["id"],
                "reason": f"设计关系{relation['type']}的引用已核对，实际承托、连通或对齐仍需实体证据",
            }
        )
    for condition in (data.get("circulation") or {}).get("clearance_paths", []):
        reviews.append(
            {
                "marker_id": condition["id"],
                "reason": "已声明通行净宽净高，墙、构件与实际通道的净空验收尚未完成",
            }
        )
    for number, condition in enumerate(
        (data.get("circulation") or {}).get("required_connections", [])
    ):
        reviews.append(
            {
                "marker_id": f"required_connection_{number}",
                "actual": condition,
                "reason": "通行要求已保留，指定起终点和经由构件仍须逐项核对实际路径",
            }
        )
    errors.extend(circulation_errors)
    errors.extend(opening_partition_conflicts(markers, hosts))
    if errors:
        raise DesignCoordinateConflict(errors)
    levels = []
    for level in geometry["levels"]:
        levels.append(
            ResolvedLevel(
                index=level["index"],
                id=level["id"],
                kind=level["kind"],
                base_y=level["base_y"],
                top_y=level["top_y"],
            )
        )
    gaps = []
    for number, review in enumerate(reviews):
        gaps.append(
            {
                "id": f"relation.{number}",
                "constraint_id": "design.relationship",
                "status": "needs_review",
                "design_hash": _stable_hash(document),
                "target": review.get("marker_id", "circulation"),
                "expected": review.get("expected"),
                "actual": review.get("actual"),
                "evidence": review["reason"],
            }
        )
    capabilities = list(geometry["capability_gaps"])
    for marker in markers:
        capabilities.extend(marker.get("capability_gaps", []))
    for number, gap in enumerate(capabilities):
        gaps.append(
            {
                "id": f"capability.{number}",
                "constraint_id": "design.capability",
                "status": "unsupported",
                "design_hash": _stable_hash(document),
                "target": gap["entity"],
                "expected": gap["expected"],
                "actual": gap["actual"],
                "evidence": gap["code"],
            }
        )
    facts = {
        key: value
        for key, value in geometry.items()
        if key not in {"source", "body_geometry"}
    }
    return ResolvedDesign(
        design_id=document.design_id,
        design_revision=document.revision,
        design_hash=_stable_hash(document),
        resolver_version=RESOLVER_VERSION,
        bounds=geometry["bounds"],
        levels=levels,
        volumes=document.decisions.volumes,
        facade_slots=[],
        projection_elements=geometry["hosts"],
        logical_hosts=geometry["hosts"],
        geometry_context=facts,
        body_geometry=geometry["body_geometry"],
        capability_gaps=capabilities,
        design_gaps=gaps,
        component_markers=markers,
        component_quantities=dict(Counter(marker["type"] for marker in markers)),
        warnings=["图纸为设计示意；几何有效、设计履约和实际视觉效果分别验收。"],
    )
