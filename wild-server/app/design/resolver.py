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
    ComponentObject,
    DesignConstraint,
    DesignDocument,
    DesignRequirements,
    EnvelopeDecision,
    MassingDecision,
    ObjectDecisions,
    ResolvedDesign,
    ResolvedFacadeSlot,
    ResolvedLevel,
    RoofDecision,
    RuleTrace,
    VolumeDecision,
    utc_now_iso,
)
from .openings import opening_kind


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


def is_object_plan(plan: dict[str, Any] | None) -> bool:
    """判定一份方案是"物件场景"还是"建筑方案"。

    只看 `target_kind`，不看 `massing` 是否存在——用"有没有 massing"反推会让
    缺失体量的建筑方案被静默降级成物件，那正好是这次要消除的那类错判。
    兼容 `objects` 键是为了让手写/历史方案也能被识别。
    """

    if not isinstance(plan, dict):
        return False
    if str(plan.get("target_kind") or "").strip().lower() == "object":
        return True
    return isinstance(plan.get("objects"), list) and not plan.get("massing")


def build_design_document(
    architecture_plan: dict[str, Any],
    *,
    session_id: str,
    source_request: str,
    building_type: str = "building",
    style_intent: list[str] | None = None,
    previous: DesignDocument | dict[str, Any] | None = None,
) -> DesignDocument:
    """把归一化方案提升为版本化设计契约；按目标类型分派建筑或物件。"""

    old = (
        previous
        if isinstance(previous, DesignDocument)
        else DesignDocument.model_validate(previous)
        if isinstance(previous, dict)
        else None
    )
    plan = deepcopy(architecture_plan)
    now = utc_now_iso()

    if is_object_plan(plan):
        return _build_object_document(
            plan,
            session_id=session_id,
            source_request=source_request,
            building_type=building_type,
            style_intent=style_intent,
            old=old,
            now=now,
        )

    # 保留部分 complexity 字段用于后续验证，但不包含已废弃的 level 字段
    complexity = dict(plan.get("complexity") or {})
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
            components=plan.get("components") or [],
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


def _build_object_document(
    plan: dict[str, Any],
    *,
    session_id: str,
    source_request: str,
    building_type: str,
    style_intent: list[str] | None,
    old: DesignDocument | None,
    now: str,
) -> DesignDocument:
    """物件场景的设计契约：只有物件清单与材质，没有体量、立面与屋顶。"""

    raw_objects = plan.get("objects")
    items: list[ComponentObject] = []
    for entry in raw_objects if isinstance(raw_objects, list) else []:
        if isinstance(entry, ComponentObject):
            items.append(entry)
        elif isinstance(entry, dict):
            items.append(ComponentObject.model_validate(entry))

    raw_unsupported = plan.get("unsupported_objects")
    unsupported = [
        str(entry).strip()[:60]
        for entry in (raw_unsupported if isinstance(raw_unsupported, list) else [])
        if str(entry).strip()
    ][:24]

    # 空清单**不再**一律判失败：`unsupported_objects` 非空表示"点名了但本次表达不了"，
    # 那是一条合法结论（与 §8.1"能力缺失只标记、不阻断"同口径），由计划阶段转成
    # unsupported 条目进交付清单。两者同时为空才是"方案本身不成立"。
    if not items and not unsupported:
        raise ValueError("物件方案必须至少包含一个对象（objects 不能为空）")

    previous_materials = (
        old.decisions.materials
        if old is not None and isinstance(old.decisions, ObjectDecisions)
        else {}
    )
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
            target="/decisions/objects",
            expression="只允许编译当前组件注册表支持的构件类型",
            source="component_registry",
        ),
        DesignConstraint(
            id="object.no-massing",
            kind="system_required",
            target="/decisions/objects",
            expression="物件场景不产生体量、立面与屋顶，只按物件清单生成构件",
            source="design_schema",
        ),
    ]
    if old is not None:
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
            building_type=building_type or "asset",
            profile=str(plan.get("profile") or "object"),
            style_intent=list(style_intent or []),
        ),
        decisions=ObjectDecisions(
            concept=str(plan.get("concept") or ""),
            objects=items,
            unsupported_objects=unsupported,
            materials=previous_materials,
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
                rule_id="object.no-massing",
                classification="engine_hard",
                applies_when="decisions.kind == object",
                schema_targets=["/decisions/objects"],
                enforcement=["schema", "planner", "resolver", "compiler", "validator"],
                source="rules-v3:furniture",
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
    if isinstance(d, ObjectDecisions):
        return _object_plan_from_document(doc, d)
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
        "components": [item.model_dump(mode="json", exclude_none=True) for item in d.components],
        "curtain_wall": d.envelope.system == "curtain_wall",
        "balcony_access_count": d.balcony_access_count,
        "balcony_width": d.balcony_width,
        "required_components": list(d.required_components),
        "unsupported_component_types": list(d.unsupported_component_types),
        "design_rationale": list(d.design_rationale),
    }


def _object_plan_from_document(doc: DesignDocument, d: ObjectDecisions) -> dict[str, Any]:
    """物件文档 → 生成侧方案协议。

    关键是把 `objects` 折算成 `component_quota` 与 `required_components`：
    后续 `plan/expand.py` 正是靠这两个字段决定"派发哪些构件、每条要几个"。
    不做这一步，方案批了也不会有人生成。
    """

    # `count` 的语义是**物件数**，而 `component_quota` 的消费点把配额下限当
    # **元素数**要求（`design_constraints` 按下限判错；配额上限已废——用户决策
    # 2026-09-29 删除上限白名单，max 只是参考值）。两者**同单位**只在
    # "一个物件 = 一个元素"时成立：
    #
    # - `furniture` / `body`：引擎有原生 builder，一个元素自带全部细部 ⇒ 同单位；
    # - 通用几何组合：一个物件由若干 `primitive` 零件拼成（WILD 没有"组合元素"这种
    #   契约，`geometry.elements` 里每个 primitive 就是一个零件）⇒ 元素数 = 零件数，
    #   那是**模型的表达粒度**，不是计划的管辖对象。
    #
    # 曾经这里无条件 `max += item.count`，而按上限剃元素的机制还在时，
    # "一个花瓶 = 4 个零件"被读成"4 个花瓶、超过上限 1"，收尾归一把它削成
    # 一块底座圆盘（0.16 × 0.04 × 0.16 m）——**而且削完还校验通过**，只剩一块
    # 底座这种事没有任何地方会报。上限剔除机制已整体删除；分解成零件的物件
    # 仍然只留下限（每件至少落地一块几何），**不设上限**。
    quota: dict[str, dict[str, Any]] = {}
    decomposed_kinds: set[str] = set()
    for item in d.objects:
        entry = quota.setdefault(item.kind, {"min": 0, "max": 0, "note": ""})
        entry["min"] += item.count
        entry["max"] += item.count
        if item.parts:
            decomposed_kinds.add(item.kind)
    for kind in decomposed_kinds:
        # 去掉上限而不是设成 0：消费点都用 `.get("max")` 取值，缺键即"不设上限"。
        quota[kind].pop("max", None)
    for item in d.objects:
        note = str(item.placement or "").strip()
        if note and not quota[item.kind]["note"]:
            quota[item.kind]["note"] = note[:300]
    # 配额键就是 `kind` —— 通道新增（furniture / primitive / body）时这里不需要改，
    # 因为"谁被派发"取决于物件条目自己声明了什么，而不是一份类型白名单。
    kinds = list(quota)
    return {
        "schema_version": "1.1",
        "target_kind": "object",
        "profile": doc.requirements.profile,
        "concept": d.concept,
        "objects": [item.model_dump(mode="json") for item in d.objects],
        # 转发"点名了但表达不了"的物件：计划阶段据此加 unsupported 条目（非阻断）。
        "unsupported_objects": list(d.unsupported_objects),
        "component_quota": quota,
        "required_components": kinds,
        "detail_packages": kinds,
        "unsupported_component_types": [],
        "design_rationale": list(d.design_rationale),
    }


def resolve_design(document: DesignDocument | dict[str, Any]) -> ResolvedDesign:
    """只从设计契约推导稳定标高、体量和抽象立面槽位。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    d = doc.decisions
    if isinstance(d, ObjectDecisions):
        return _resolve_object_design(doc, d)
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
            for index, raw_opening in enumerate(pattern, start=1):
                # §3.3：pattern 项是 token（`"window"` / `"door:slide"`）。这里只用**类型**——
                # 把形态写进 `id` / `type` 会让下游按 id 对齐槽位时分叉。
                opening_type = opening_kind(raw_opening)
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


def _resolve_object_design(doc: DesignDocument, d: ObjectDecisions) -> ResolvedDesign:
    """物件场景的可执行视图：没有标高、没有体量、没有立面槽位。"""

    quantities: dict[str, int] = {}
    for item in d.objects:
        quantities[item.kind] = quantities.get(item.kind, 0) + item.count

    # 场景外廓是**估算**：真实摆位由构件生成节点按行走面标高算出，方案层不写死坐标。
    # 这里按"沿 X 依次排列、间距 0.3m"给出保守范围，只服务审核图纸的取景与人读标注。
    cursor = 0.0
    max_depth = 0.0
    max_height = 0.0
    for item in d.objects:
        cursor += item.width + 0.3
        max_depth = max(max_depth, item.depth)
        max_height = max(max_height, item.height)
    width = round(max(cursor - 0.3, 0.1), 3)

    return ResolvedDesign(
        design_id=doc.design_id,
        design_revision=doc.revision,
        design_hash=_stable_hash(doc),
        bounds={
            "width": width,
            "depth": round(max(max_depth, 0.1), 3),
            "height": round(max(max_height, 0.1), 3),
        },
        levels=[],
        volumes=[],
        facade_slots=[],
        component_quantities=quantities,
        warnings=[],
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


def _render_object_svg(doc: DesignDocument, result: ResolvedDesign) -> str:
    """物件场景的审核图：逐件画正面轮廓与占地轮廓，并列出尺寸与摆位。

    刻意不画"体量平面/主立面/侧立面"——那是建筑的语言。物件没有立面和层数，
    画上去就是虚假信息。人机确认要审的是"做几件、多大、怎么摆"。
    """

    decisions = doc.decisions
    assert isinstance(decisions, ObjectDecisions)
    title = escape(decisions.concept or doc.requirements.source_request[:40])
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="820" viewBox="0 0 1200 820" role="img">',
        '<rect width="1200" height="820" fill="#171a20"/>',
        f'<text x="38" y="42" fill="#f2f4f8" font-size="20" font-family="sans-serif">{title}</text>',
        f'<text x="38" y="68" fill="#9da8b8" font-size="12" font-family="sans-serif">DesignDocument r{doc.revision} · {doc.status} · 物件场景 · {escape(result.design_hash[:22])}</text>',
        '<text x="38" y="105" fill="#d8dde7" font-size="14" font-family="sans-serif">物件正面轮廓（按比例）</text>',
        '<rect x="38" y="120" width="1122" height="330" fill="#20252d" stroke="#3b4655"/>',
    ]

    # 统一比例：最高的那件占 250px，总宽不超过 1040px。
    total_w = sum(item.width for item in decisions.objects) or 1.0
    max_h = max((item.height for item in decisions.objects), default=1.0)
    sx = min(1040 / total_w, 250 / max(max_h, 0.1))
    base_y = 420.0
    cursor = 58.0
    for index, item in enumerate(decisions.objects):
        fill = "#487aa1" if index % 2 == 0 else "#5f7184"
        w = item.width * sx
        h = item.height * sx
        parts.append(
            f'<rect x="{cursor:.2f}" y="{base_y - h:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{fill}" fill-opacity="0.7" stroke="#9bc3e0" '
            f'data-design-path="/decisions/objects/{index}"/>'
        )
        parts.append(
            f'<text x="{cursor:.2f}" y="{base_y + 18:.2f}" fill="#edf5fb" font-size="11" '
            f'font-family="sans-serif">{escape(f"{item.kind}/{item.subtype or '-'}")}</text>'
        )
        parts.append(
            f'<text x="{cursor:.2f}" y="{base_y + 34:.2f}" fill="#9da8b8" font-size="11" '
            f'font-family="sans-serif">{escape(f"×{item.count}  {item.width:.2f}W")}</text>'
        )
        cursor += w + 24.0

    parts.extend([
        '<text x="38" y="505" fill="#d8dde7" font-size="14" font-family="sans-serif">尺寸与摆位</text>',
        '<rect x="38" y="520" width="1122" height="275" fill="#20252d" stroke="#3b4655"/>',
    ])
    line_y = 552.0
    for item in decisions.objects:
        label = f"{item.kind}/{item.subtype or '-'} × {item.count}"
        size = f"W{item.width:.2f} × D{item.depth:.2f} × H{item.height:.2f}m"
        placement = item.placement or "未指定摆位"
        parts.append(
            f'<text x="58" y="{line_y:.2f}" fill="#edf5fb" font-size="13" '
            f'font-family="sans-serif">{escape(label)}　{escape(size)}　{escape(placement[:70])}</text>'
        )
        line_y += 26.0
        if line_y > 780:
            break

    if decisions.design_rationale:
        parts.append(
            f'<text x="58" y="{min(line_y + 8, 786):.2f}" fill="#9da8b8" font-size="12" '
            f'font-family="sans-serif">{escape("；".join(decisions.design_rationale)[:150])}</text>'
        )
    parts.append('</svg>')
    return "".join(parts)


def _elevation_floor_spans(
    massing: MassingDecision,
    volumes: list[VolumeDecision],
    axis: str = "width",
) -> list[tuple[float, float]]:
    """逐层立面跨度：(左缘比例, 宽度比例)，比例相对对应向尺寸。

    立面轮廓的**唯一投影口径**，优先级：massing.tiers 表态 > 体量落层
    （分层不齐时派生退台/塔座）> shape 派生（塔形收分）> 满幅矩形。
    这是**审核图纸的投影**，不是物理事实——编译器与 3D 引擎不受它约束；
    反过来说，想让图纸画出塔形，必须在 massing 上表态（tiers/shape/volumes），
    图纸不会自己发明轮廓。
    """
    floors = max(massing.modeled_floors, 1)
    if massing.tiers:
        spans: list[tuple[float, float]] = []
        for tier in massing.tiers:
            ratio = tier.width_ratio if axis == "width" else tier.depth_ratio
            spans.extend([(round((1 - ratio) / 2, 4), ratio)] * tier.floors)
        return spans[:floors]
    if volumes:
        covers: list[tuple[float, float]] = []
        for floor in range(1, floors + 1):
            covering = [v for v in volumes if v.start_floor <= floor <= v.end_floor]
            if not covering:
                covers.append((0.0, 1.0))
                continue
            if axis == "width":
                left = min(v.x for v in covering)
                right = max(v.x + v.width for v in covering)
                dim = massing.width
            else:
                left = min(v.z for v in covering)
                right = max(v.z + v.depth for v in covering)
                dim = massing.depth
            covers.append((round(left / dim, 4), round((right - left) / dim, 4)))
        if len(set(covers)) > 1:
            # 体量分层不齐（塔座/退台）才据此投影；整齐时与满幅等价，落到通用分支。
            return covers
    if massing.shape == "tower":
        # 塔形收分：逐层线性收窄到底部宽度的 55%，居中放置。
        return [
            (
                round(0.225 * (floor - 0.5) / floors, 4),
                round(1 - 0.45 * (floor - 0.5) / floors, 4),
            )
            for floor in range(1, floors + 1)
        ]
    return [(0.0, 1.0)] * floors


def _silhouette_element(
    spans: list[tuple[float, float]],
    level_tops: list[float],
    axis_dim: float,
    sx: float,
    sy: float,
    x0: float,
    base: float,
) -> str:
    """把逐层跨度压成**一个**轮廓元素：满幅单段画 rect（兼容旧图），其余画台阶/收分 polygon。

    data-design-path 恒为 ``/decisions/massing``——它是前端点击回写设计的锚点，
    换元素形状不能换锚点。层高取 level_tops（schematic 档各代表层间距不均匀，
    不能按 floor_height 均分）。
    """

    def top_of(floor: int) -> float:
        return level_tops[min(floor, len(level_tops)) - 1]

    bands: list[tuple[float, float, int, int]] = []  # (左缘比例, 宽度比例, 起层, 止层)
    for floor, (left_r, w_r) in enumerate(spans, start=1):
        if bands and abs(bands[-1][0] - left_r) < 1e-6 and abs(bands[-1][1] - w_r) < 1e-6:
            prev_left, prev_w, f0, _ = bands[-1]
            bands[-1] = (prev_left, prev_w, f0, floor)
        else:
            bands.append((left_r, w_r, floor, floor))
    if len(bands) == 1 and abs(bands[0][1] - 1.0) < 1e-6 and bands[0][2] == 1:
        height = top_of(bands[0][3])
        return (
            f'<rect x="{x0:.2f}" y="{base - height * sy:.2f}" width="{axis_dim * sx:.2f}" '
            f'height="{height * sy:.2f}" fill="#303945" stroke="#9aa7b5" '
            f'data-design-path="/decisions/massing"/>'
        )
    right_pts: list[str] = []
    left_pts: list[str] = []
    for left_r, w_r, _f0, f1 in bands:
        y_top = base - top_of(f1) * sy
        right_pts.append(f"{x0 + (left_r + w_r) * axis_dim * sx:.2f},{y_top:.2f}")
        left_pts.append(f"{x0 + left_r * axis_dim * sx:.2f},{y_top:.2f}")
    bottom_y = base - (top_of(bands[0][2] - 1) if bands[0][2] >= 2 else 0.0) * sy
    points = " ".join([
        f"{x0 + (bands[0][0] + bands[0][1]) * axis_dim * sx:.2f},{bottom_y:.2f}",
        *right_pts,
        *reversed(left_pts),
        f"{x0 + bands[0][0] * axis_dim * sx:.2f},{bottom_y:.2f}",
    ])
    return (
        f'<polygon points="{points}" fill="#303945" stroke="#9aa7b5" '
        f'data-design-path="/decisions/massing"/>'
    )


def _roof_elements(roof: RoofDecision, cx: float, y: float, span_px: float, sx: float) -> list[str]:
    """屋顶在立面上的轮廓投影。y = 承托面（屋顶底沿），span_px = 承托跨度像素宽。

    flat 由体量轮廓的顶边承担，不另画。data-design-path 恒为 ``/decisions/roof``。
    """
    span = span_px + 2 * roof.overhang * sx
    x0, x1 = cx - span / 2, cx + span / 2
    common = 'fill="#3d4a5a" fill-opacity="0.55" stroke="#9aa7b5" data-design-path="/decisions/roof"'
    if roof.type == "flat":
        return []
    if roof.type == "gable":
        rise = min(span * 0.28, 46.0)
        pts = f"{x0:.2f},{y:.2f} {cx:.2f},{y - rise:.2f} {x1:.2f},{y:.2f}"
        return [f'<polygon points="{pts}" {common}/>']
    if roof.type == "hip":
        rise = min(span * 0.18, 32.0)
        top = span * 0.2
        pts = (
            f"{x0:.2f},{y:.2f} {cx - top:.2f},{y - rise:.2f} "
            f"{cx + top:.2f},{y - rise:.2f} {x1:.2f},{y:.2f}"
        )
        return [f'<polygon points="{pts}" {common}/>']
    if roof.type == "dome":
        rx, ry = span / 2, min(span * 0.42, 56.0)
        return [f'<path d="M {x0:.2f},{y:.2f} A {rx:.2f},{ry:.2f} 0 0 1 {x1:.2f},{y:.2f} Z" {common}/>']
    if roof.type == "chinese_curved":
        # 曲线屋面：檐角上翘（高于檐中），经二次贝塞尔收至正脊。
        rise = min(span * 0.24, 40.0)
        tip, sag = y - rise * 0.55, y + rise * 0.12
        d = (
            f"M {x0:.2f},{tip:.2f} "
            f"Q {cx - span * 0.27:.2f},{sag:.2f} {cx:.2f},{y - rise:.2f} "
            f"Q {cx + span * 0.27:.2f},{sag:.2f} {x1:.2f},{tip:.2f} Z"
        )
        return [f'<path d="{d}" {common}/>']
    # chinese_pagoda：三层递收的挑檐 + 宝顶。
    parts: list[str] = []
    step = min(span * 0.16, 22.0)
    slab_h = max(5.0, span * 0.07)
    for index in range(3):
        slab_w = span * (1 - 0.26 * index)
        slab_y = y - index * step - slab_h
        parts.append(
            f'<rect x="{cx - slab_w / 2:.2f}" y="{slab_y:.2f}" width="{slab_w:.2f}" '
            f'height="{slab_h:.2f}" {common}/>'
        )
    tip_y = y - 2 * step - slab_h
    parts.append(
        f'<line x1="{cx:.2f}" y1="{tip_y:.2f}" x2="{cx:.2f}" y2="{tip_y - 14:.2f}" stroke="#9aa7b5"/>'
    )
    return parts


def _slot_in_span(slot: ResolvedFacadeSlot, span: tuple[float, float], axis_dim: float) -> bool:
    """槽位是否落在该层的立面跨度内。出界的不画——缩进体量外的开口是虚假信息。"""
    left_m, width_m = span[0] * axis_dim, span[1] * axis_dim
    return slot.offset >= left_m - 0.05 and slot.offset + slot.width <= left_m + width_m + 0.05


def _dim_line_h(x: float, y: float, length: float, label: str) -> str:
    stroke = 'stroke="#7f8b9a"'
    return (
        f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x + length:.2f}" y2="{y:.2f}" {stroke}/>'
        f'<line x1="{x:.2f}" y1="{y - 4:.2f}" x2="{x:.2f}" y2="{y + 4:.2f}" {stroke}/>'
        f'<line x1="{x + length:.2f}" y1="{y - 4:.2f}" x2="{x + length:.2f}" y2="{y + 4:.2f}" {stroke}/>'
        f'<text x="{x + length / 2:.2f}" y="{y - 6:.2f}" fill="#9da8b8" font-size="11" '
        f'font-family="sans-serif" text-anchor="middle">{escape(label)}</text>'
    )


def _dim_line_v(x: float, y_top: float, y_bottom: float, label: str) -> str:
    stroke = 'stroke="#7f8b9a"'
    mid_y = (y_top + y_bottom) / 2
    text_x, text_y = x + 10, mid_y
    return (
        f'<line x1="{x:.2f}" y1="{y_top:.2f}" x2="{x:.2f}" y2="{y_bottom:.2f}" {stroke}/>'
        f'<line x1="{x - 4:.2f}" y1="{y_top:.2f}" x2="{x + 4:.2f}" y2="{y_top:.2f}" {stroke}/>'
        f'<line x1="{x - 4:.2f}" y1="{y_bottom:.2f}" x2="{x + 4:.2f}" y2="{y_bottom:.2f}" {stroke}/>'
        f'<text x="{text_x:.2f}" y="{text_y:.2f}" fill="#9da8b8" font-size="11" '
        f'font-family="sans-serif" text-anchor="middle" '
        f'transform="rotate(-90 {text_x:.2f} {text_y:.2f})">{escape(label)}</text>'
    )


def render_design_svg(document: DesignDocument | dict[str, Any], resolved: ResolvedDesign | None = None) -> str:
    """生成单文件 SVG 方案图；建筑画平面/立面，物件画轮廓与尺寸表。

    立面不再是无条件大矩形：按 massing.tiers / 体量落层 / shape 派生逐层跨度，
    画出台阶、收分（塔形）轮廓；屋顶按 RoofDecision 画六种示意轮廓；附总宽/总高
    标注与地平线。所有 data-design-path 锚点保持不变。
    """

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    result = resolved or resolve_design(doc)
    if isinstance(doc.decisions, ObjectDecisions):
        return _render_object_svg(doc, result)
    decisions = doc.decisions
    massing = decisions.massing
    width = result.bounds["width"]
    depth = result.bounds["depth"]
    height = result.bounds["height"]
    level_tops = [level.top_y for level in result.levels]
    drawn_height = level_tops[-1] if level_tops else height
    plan_s = min(470 / max(width, 1), 300 / max(depth, 1))
    elev_sx = 470 / max(width, 1)
    elev_sy = 270 / max(height, 1)
    side_sx = 470 / max(depth, 1)
    side_sy = 245 / max(height, 1)
    title = escape(decisions.concept or doc.requirements.building_type)
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

    # 主立面：逐层跨度画轮廓（tiers 表态 / 退台 / 塔形收分），屋顶画在顶段承托面上。
    front_spans = _elevation_floor_spans(massing, result.volumes, axis="width")
    elev_x, elev_base = 650.0, 436.0
    parts.extend([
        '<text x="630" y="105" fill="#d8dde7" font-size="14" font-family="sans-serif">主立面</text>',
        '<rect x="630" y="120" width="530" height="330" fill="#20252d" stroke="#3b4655"/>',
        _silhouette_element(front_spans, level_tops, width, elev_sx, elev_sy, elev_x, elev_base),
        f'<line x1="634" y1="{elev_base:.2f}" x2="1156" y2="{elev_base:.2f}" stroke="#6b7684" stroke-width="2"/>',
    ])
    front_top = elev_base - drawn_height * elev_sy
    for level in result.levels[:-1]:
        span = front_spans[min(level.index + 1, len(front_spans)) - 1]
        y = elev_base - level.top_y * elev_sy
        line_x1 = elev_x + span[0] * width * elev_sx
        line_x2 = elev_x + (span[0] + span[1]) * width * elev_sx
        parts.append(
            f'<line x1="{line_x1:.2f}" y1="{y:.2f}" x2="{line_x2:.2f}" y2="{y:.2f}" '
            f'stroke="#596573" stroke-width="1"/>'
        )
    for slot in result.facade_slots:
        if slot.facing == "front":
            span = front_spans[min(slot.floor, len(front_spans)) - 1]
            if _slot_in_span(slot, span, width):
                parts.append(_svg_opening(slot, elev_x, elev_base, elev_sx, elev_sy))
    top_left, top_ratio = front_spans[-1]
    parts.extend(_roof_elements(
        decisions.roof,
        cx=elev_x + (top_left + top_ratio / 2) * width * elev_sx,
        y=front_top,
        span_px=top_ratio * width * elev_sx,
        sx=elev_sx,
    ))
    # 尺寸标注：人眼审图没有比例尺就没法核对设计。高度标的是**画出来的**轮廓高
    # （schematic 档代表层只铺到 drawn_height，不虚标全高）。
    parts.append(_dim_line_h(elev_x, elev_base + 11, width * elev_sx, f"{width:.1f} m"))
    parts.append(_dim_line_v(elev_x + width * elev_sx + 14, front_top, elev_base, f"{drawn_height:.1f} m"))

    # 侧立面：同一条投影口径，轴换成 depth。
    side_spans = _elevation_floor_spans(massing, result.volumes, axis="depth")
    side_x, side_base = 58.0, 785.0
    parts.extend([
        '<text x="38" y="505" fill="#d8dde7" font-size="14" font-family="sans-serif">侧立面</text>',
        '<rect x="38" y="520" width="1122" height="275" fill="#20252d" stroke="#3b4655"/>',
        _silhouette_element(side_spans, level_tops, depth, side_sx, side_sy, side_x, side_base),
        f'<line x1="42" y1="{side_base:.2f}" x2="1156" y2="{side_base:.2f}" stroke="#6b7684" stroke-width="2"/>',
    ])
    for slot in result.facade_slots:
        if slot.facing == "left":
            span = side_spans[min(slot.floor, len(side_spans)) - 1]
            if _slot_in_span(slot, span, depth):
                parts.append(_svg_opening(slot, side_x, side_base, side_sx, side_sy))
    side_top = side_base - drawn_height * side_sy
    parts.append(_dim_line_v(side_x + depth * side_sx + 14, side_top, side_base, f"{drawn_height:.1f} m"))
    parts.append('</svg>')
    return "".join(parts)
