"""把 DesignDocument 确定性解析成 SVG 与 Blueprint 可共用的数据。"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from html import escape
import json
from typing import Any

from .contracts import (
    ArchitectureDecisions,
    ComplexityDecision,
    DesignConstraint,
    DesignDocument,
    DesignRequirements,
    EnvelopeDecision,
    ResolvedDesign,
    ResolvedFacadeSlot,
    ResolvedLevel,
    RuleTrace,
    utc_now_iso,
)


def _stable_hash(document: DesignDocument) -> str:
    payload = {
        "schema_version": document.schema_version,
        "design_id": document.design_id,
        "revision": document.revision,
        "requirements": document.requirements.model_dump(mode="json"),
        "decisions": document.decisions.model_dump(mode="json"),
        "constraints": [item.model_dump(mode="json") for item in document.constraints],
        "locks": document.locks,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + sha256(raw.encode("utf-8")).hexdigest()


def build_design_document(
    architecture_plan: dict[str, Any],
    *,
    session_id: str,
    source_request: str,
    building_type: str = "building",
    style_intent: list[str] | None = None,
    previous: DesignDocument | dict[str, Any] | None = None,
) -> DesignDocument:
    """把归一化 architecture_plan 提升为版本化设计契约。"""

    old = (
        previous
        if isinstance(previous, DesignDocument)
        else DesignDocument.model_validate(previous)
        if isinstance(previous, dict)
        else None
    )
    plan = deepcopy(architecture_plan)
    complexity = dict(plan.get("complexity") or {})
    complexity.setdefault("level", "standard")
    complexity.setdefault("min_volumes", 1)
    complexity.setdefault("min_detail_packages", 0)
    complexity.setdefault("target_structural_elements", 10)
    complexity.setdefault("grid_bays", [2, 2])
    complexity.setdefault("reason", "")
    curtain_wall = bool(plan.get("curtain_wall"))
    profile = str(plan.get("profile") or building_type or "building")
    now = utc_now_iso()
    constraints = [
        DesignConstraint(
            id="request.source",
            kind="user_hard",
            target="/requirements/source_request",
            expression="设计必须保持用户原始需求中明确提出的条件",
            source="user_request",
        ),
        DesignConstraint(
            id="engine.supported-components",
            kind="engine_hard",
            target="/decisions/required_components",
            expression="只允许编译当前组件注册表支持的构件类型",
            source="component_registry",
        ),
        DesignConstraint(
            id="facade.pattern-cardinality",
            kind="system_required",
            target="/decisions/facades",
            expression="每个立面的 pattern 长度必须等于 bays",
            source="design_schema",
        ),
    ]
    if curtain_wall:
        constraints.append(DesignConstraint(
            id="envelope.curtain-wall.alignment",
            kind="system_required",
            target="/decisions/envelope/curtain_wall/grid_strategy",
            expression="幕墙分格必须与楼层和立面开间关系一致",
            source="rules-v3:glass-curtain-wall-assembly",
        ))
    if old:
        current_ids = {item.id for item in constraints}
        constraints.extend(
            item for item in old.constraints
            if item.id not in current_ids
        )

    return DesignDocument(
        design_id=(old.design_id if old else f"design_{session_id}"),
        session_id=session_id,
        revision=(old.revision + 1 if old else 1),
        status="draft",
        created_at=(old.created_at if old else now),
        updated_at=now,
        requirements=DesignRequirements(
            source_request=source_request,
            building_type=building_type or profile,
            profile=profile,
            style_intent=list(style_intent or []),
        ),
        decisions=ArchitectureDecisions(
            concept=str(plan.get("concept") or ""),
            massing=plan["massing"],
            complexity=ComplexityDecision.model_validate(complexity),
            volumes=plan["volumes"],
            structural_grid=plan["structural_grid"],
            envelope=EnvelopeDecision(
                system="curtain_wall" if curtain_wall else "solid_wall",
                curtain_wall={} if curtain_wall else None,
            ),
            facades=plan["facades"],
            roof=plan["roof"],
            circulation={
                "vertical_strategy": str(
                    (plan.get("circulation") or {}).get("vertical_strategy")
                    or ("core_and_stair" if profile == "high_rise" else "stair")
                ),
            },
            materials=(old.decisions.materials if old else {}),
            detail_packages=list(plan.get("detail_packages") or []),
            component_quota=plan.get("component_quota") or {},
            balcony_access_count=int(plan.get("balcony_access_count") or 0),
            balcony_width=plan.get("balcony_width"),
            required_components=list(plan.get("required_components") or []),
            unsupported_component_types=list(plan.get("unsupported_component_types") or []),
            design_rationale=list(plan.get("design_rationale") or []),
        ),
        constraints=constraints,
        locks=list(old.locks if old else []),
        rule_trace=[
            RuleTrace(
                rule_id="wild.schema.contract",
                classification="engine_hard",
                applies_when="always",
                schema_targets=["/decisions"],
                enforcement=["schema", "compiler", "validator"],
                source="WILD schema and component registry",
            ),
            RuleTrace(
                rule_id="envelope.curtain-wall.floor-grid-alignment",
                classification="conditional",
                applies_when="envelope.system == curtain_wall",
                schema_targets=["/decisions/envelope", "/decisions/facades"],
                enforcement=["planner", "resolver", "validator"],
                source="rules-v3:glass-curtain-wall-assembly",
            ),
        ],
    )


def attach_material_plan(
    document: DesignDocument | dict[str, Any],
    material_plan: dict[str, Any],
) -> DesignDocument:
    """把已解析的材质方案写入当前设计 revision，不制造虚假的新设计版本。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    data = doc.model_dump(mode="json")
    concept = str(material_plan.get("concept") or "").strip()
    palette = material_plan.get("palette")
    keywords = [concept] if concept else []
    if isinstance(palette, list):
        keywords.extend(str(item).strip() for item in palette if str(item).strip())
    data["decisions"]["materials"] = {
        "keywords": keywords[:20],
        "resolved_plan": deepcopy(material_plan),
    }
    data["status"] = "draft"
    data["approved_at"] = None
    data["updated_at"] = utc_now_iso()
    return DesignDocument.model_validate(data)


def architecture_plan_from_document(document: DesignDocument | dict[str, Any]) -> dict[str, Any]:
    """将批准后的设计决策编译回现有生成节点能够消费的方案协议。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    d = doc.decisions
    return {
        "schema_version": "1.1",
        "profile": doc.requirements.profile,
        "concept": d.concept,
        "massing": d.massing.model_dump(mode="json"),
        "complexity": d.complexity.model_dump(mode="json"),
        "volumes": [item.model_dump(mode="json") for item in d.volumes],
        "structural_grid": d.structural_grid.model_dump(mode="json"),
        "circulation": d.circulation.model_dump(mode="json"),
        "detail_packages": list(d.detail_packages),
        "facades": {key: value.model_dump(mode="json", exclude_none=True) for key, value in d.facades.items()},
        "roof": d.roof.model_dump(mode="json"),
        "component_quota": {key: value.model_dump(mode="json", exclude_none=True) for key, value in d.component_quota.items()},
        "curtain_wall": d.envelope.system == "curtain_wall",
        "balcony_access_count": d.balcony_access_count,
        "balcony_width": d.balcony_width,
        "required_components": list(d.required_components),
        "unsupported_component_types": list(d.unsupported_component_types),
        "design_rationale": list(d.design_rationale),
    }


def resolve_design(document: DesignDocument | dict[str, Any]) -> ResolvedDesign:
    """只从设计契约推导稳定标高、体量和抽象立面槽位。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    d = doc.decisions
    massing = d.massing
    if massing.representation_mode == "schematic" and massing.modeled_floors > 1:
        floor_indices = [
            1 + round(index * (massing.floors - 1) / (massing.modeled_floors - 1))
            for index in range(massing.modeled_floors)
        ]
    else:
        floor_indices = list(range(1, massing.modeled_floors + 1))
    levels = [
        ResolvedLevel(
            index=index,
            base_y=round((index - 1) * massing.floor_height, 3),
            top_y=round(index * massing.floor_height, 3),
        )
        for index in floor_indices
    ]
    slots: list[ResolvedFacadeSlot] = []
    quantities = {key: value.min for key, value in d.component_quota.items()}
    for facing, facade in d.facades.items():
        span = massing.width if facing in {"front", "back"} else massing.depth
        bay_width = span / facade.bays
        for level in levels:
            floor = level.index
            pattern = facade.ground_pattern if floor == 1 else facade.upper_pattern
            for index, opening_type in enumerate(pattern, start=1):
                if opening_type == "empty":
                    continue
                width = min(
                    bay_width * (0.9 if d.envelope.system == "curtain_wall" else 0.62),
                    max(0.8, bay_width - 0.3),
                )
                bottom = 0.0 if opening_type == "door" else min(1.0, massing.floor_height * 0.3)
                height = (
                    min(2.4, massing.floor_height - 0.2)
                    if opening_type == "door"
                    else min(
                        massing.floor_height - bottom - 0.25,
                        massing.floor_height * (0.82 if d.envelope.system == "curtain_wall" else 0.48),
                    )
                )
                slots.append(ResolvedFacadeSlot(
                    id=f"{facing}:floor_{floor}:{opening_type}:{index}",
                    facing=facing,
                    floor=floor,
                    bay=index,
                    type=opening_type,
                    offset=round((index - 0.5) * bay_width - width / 2, 3),
                    width=round(width, 3),
                    bottom=round(level.base_y + bottom, 3),
                    height=round(max(0.8, height), 3),
                ))
    quantities["door"] = sum(slot.type == "door" for slot in slots)
    quantities["window"] = sum(slot.type == "window" for slot in slots)
    warnings = [
        f"以下构件尚未被当前编译器支持：{', '.join(d.unsupported_component_types)}"
    ] if d.unsupported_component_types else []
    return ResolvedDesign(
        design_id=doc.design_id,
        design_revision=doc.revision,
        design_hash=_stable_hash(doc),
        bounds={
            "width": massing.width,
            "depth": massing.depth,
            "height": round(massing.floors * massing.floor_height, 3),
        },
        levels=levels,
        volumes=d.volumes,
        facade_slots=slots,
        component_quantities=quantities,
        warnings=warnings,
    )


def _svg_opening(slot: ResolvedFacadeSlot, x: float, baseline: float, sx: float, sy: float) -> str:
    color = "#5aa7d7" if slot.type == "window" else "#b78350"
    rect_x = x + slot.offset * sx
    rect_y = baseline - (slot.bottom + slot.height) * sy
    return (
        f'<rect x="{rect_x:.2f}" y="{rect_y:.2f}" width="{slot.width * sx:.2f}" '
        f'height="{slot.height * sy:.2f}" fill="{color}" opacity="0.82" '
        f'data-design-path="/decisions/facades/{slot.facing}" data-slot-id="{escape(slot.id)}"/>'
    )


def render_design_svg(document: DesignDocument | dict[str, Any], resolved: ResolvedDesign | None = None) -> str:
    """生成包含平面、主立面和侧立面的单文件 SVG 方案图。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    result = resolved or resolve_design(doc)
    width = result.bounds["width"]
    depth = result.bounds["depth"]
    height = result.bounds["height"]
    plan_s = min(470 / max(width, 1), 300 / max(depth, 1))
    elev_sx = 470 / max(width, 1)
    elev_sy = 270 / max(height, 1)
    side_sx = 470 / max(depth, 1)
    title = escape(doc.decisions.concept or doc.requirements.building_type)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="820" viewBox="0 0 1200 820" role="img">',
        '<rect width="1200" height="820" fill="#171a20"/>',
        f'<text x="38" y="42" fill="#f2f4f8" font-size="20" font-family="sans-serif">{title}</text>',
        f'<text x="38" y="68" fill="#9da8b8" font-size="12" font-family="sans-serif">DesignDocument r{doc.revision} · {doc.status} · {escape(result.design_hash[:22])}</text>',
        '<text x="38" y="105" fill="#d8dde7" font-size="14" font-family="sans-serif">体量平面</text>',
        '<rect x="38" y="120" width="520" height="330" fill="#20252d" stroke="#3b4655"/>',
    ]
    plan_x, plan_y = 58.0, 140.0
    for index, volume in enumerate(result.volumes):
        fill = "#487aa1" if volume.role == "primary" else "#5f7184"
        parts.append(
            f'<rect x="{plan_x + volume.x * plan_s:.2f}" y="{plan_y + volume.z * plan_s:.2f}" '
            f'width="{volume.width * plan_s:.2f}" height="{volume.depth * plan_s:.2f}" '
            f'fill="{fill}" fill-opacity="0.66" stroke="#9bc3e0" '
            f'data-design-path="/decisions/volumes/{index}" data-volume-id="{escape(volume.id)}"/>'
        )
        parts.append(
            f'<text x="{plan_x + (volume.x + 0.2) * plan_s:.2f}" y="{plan_y + (volume.z + 0.6) * plan_s:.2f}" '
            f'fill="#edf5fb" font-size="11" font-family="sans-serif">{escape(volume.id)}</text>'
        )

    elev_x, elev_base = 650.0, 450.0
    parts.extend([
        '<text x="630" y="105" fill="#d8dde7" font-size="14" font-family="sans-serif">主立面</text>',
        '<rect x="630" y="120" width="530" height="330" fill="#20252d" stroke="#3b4655"/>',
        f'<rect x="{elev_x}" y="{elev_base - height * elev_sy:.2f}" width="{width * elev_sx:.2f}" height="{height * elev_sy:.2f}" fill="#303945" stroke="#9aa7b5" data-design-path="/decisions/massing"/>',
    ])
    for level in result.levels[:-1]:
        y = elev_base - level.top_y * elev_sy
        parts.append(f'<line x1="{elev_x}" y1="{y:.2f}" x2="{elev_x + width * elev_sx:.2f}" y2="{y:.2f}" stroke="#596573" stroke-width="1"/>')
    for slot in result.facade_slots:
        if slot.facing == "front":
            parts.append(_svg_opening(slot, elev_x, elev_base, elev_sx, elev_sy))

    side_x, side_base = 58.0, 785.0
    side_sy = 245 / max(height, 1)
    parts.extend([
        '<text x="38" y="505" fill="#d8dde7" font-size="14" font-family="sans-serif">侧立面</text>',
        '<rect x="38" y="520" width="1122" height="275" fill="#20252d" stroke="#3b4655"/>',
        f'<rect x="{side_x}" y="{side_base - height * side_sy:.2f}" width="{depth * side_sx:.2f}" height="{height * side_sy:.2f}" fill="#303945" stroke="#9aa7b5" data-design-path="/decisions/massing"/>',
    ])
    for slot in result.facade_slots:
        if slot.facing == "left":
            parts.append(_svg_opening(slot, side_x, side_base, side_sx, side_sy))
    parts.append('</svg>')
    return "".join(parts)
