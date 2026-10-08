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
    ObjectDecisions,
    ResolvedDesign,
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
        "normalization_evidence": [t.model_dump(mode="json") for t in document.rule_trace if t.changes],
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
    revision_feedback: str = "",
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

    from .completeness import merge_design_constraints
    constraints = merge_design_constraints(constraints, plan.get("design_constraints"), source_request, revision_feedback)

    document = DesignDocument(
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

    changes = plan.get("normalization_changes") or []
    if old:
        document.rule_trace.extend(t for t in old.rule_trace if t.changes)
    if changes:
        for change in changes:
            target = change["path"]
            change["constraint_ids"] = [c.id for c in constraints if
                c.target == target or c.target.startswith(target+"/") or target.startswith(c.target+"/")]
            for c in constraints:
                if (c.id in change["constraint_ids"] and c.kind == "user_hard"
                        and c.source_quote and c.check == "equals" and c.target == target):
                    if change["before"] == c.expected:
                        change["input_source"] = "user"
                    if change["after"] == c.expected:
                        change["output_source"] = "user"
        document.rule_trace.append(RuleTrace(
            rule_id="architecture.normalize", classification="reference",
            enforcement=["planner", "validator"], source="architecture normalization",
            design_revision=document.revision, changes=changes,
        ))

    from .normalization import decision_summary
    document.decisions.design_rationale = [
        decision_summary(architecture_plan_from_document(document)),
        *[text for text in document.decisions.design_rationale
          if not text.removeprefix("[待核对] ").startswith("[决策事实]")][:5],
    ]

    # Keep prose explicitly unverified when it no longer has reliable decision evidence.
    from .completeness import evaluate_design
    gaps = evaluate_design(document, _stable_hash(document))
    if any(g.status != "satisfied" for g in gaps):
        document.decisions.design_rationale = [
            text if text.startswith(("[待核对]", "[决策事实]")) else "[待核对] " + text
            for text in document.decisions.design_rationale
        ]
        if any(c.get("semantic_change") for t in document.rule_trace for c in t.changes):
            concept = document.decisions.concept
            document.decisions.concept = concept if concept.startswith("[待核对]") else ("[待核对] " + concept)[:240]
    return document


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


def _repair_instance_material_roles(
    data: dict[str, Any],
    material_plan: dict[str, Any],
) -> list[str]:
    """把实例的 ``material_role`` 归一成**本方案里真实存在的角色名**。

    判据全部来自方案自身，不另抄一张别名表：命中 ``role`` 即原样；否则查
    ``materialId → role`` 的反查表（``metal`` → ``frame``、``wood`` → ``door``）；
    两者都不中，说明这个名字在本方案的蓝图里落不到任何材质，**降级为"没表态"并记账**，
    不抛异常（宁缺毋错：这一条是造型偏好，不是可交付性）。

    为什么必须在这里做：`ComponentInstance.material_role` 的字面量是**建筑 ∪ 物件
    并集**（`MaterialRoleName`），所以模型在建筑方案里写物件侧的材质名 `metal` 过得了
    字面量校验、也过得了块级 `ComponentInstance.model_validate`，却在
    `DesignDocument` 的引用完整性校验上被 raise —— 而那是
    `DesignDocument.model_validate` 里的硬失败，会让**整轮生成**终止在材质节点
    （2026-10-08 玻璃幕墙场景实测）。口径与编译器一致：
    `compile._material_name_for_role` 本来就同时认角色名与蓝图材质名。
    """

    roles = {
        str(item["role"]): item
        for item in material_plan.get("roles") or []
        if isinstance(item, dict) and isinstance(item.get("role"), str)
    }
    by_material_id = {
        str(item["materialId"]): str(item["role"])
        for item in roles.values()
        if isinstance(item.get("materialId"), str)
    }
    decisions = data.get("decisions")
    instances = decisions.get("components") if isinstance(decisions, dict) else None
    if not isinstance(instances, list):
        return []
    repairs: list[str] = []
    for index, instance in enumerate(instances):
        if not isinstance(instance, dict):
            continue
        role = instance.get("material_role")
        if not role or str(role) in roles:
            continue
        canonical = by_material_id.get(str(role))
        if canonical:
            instance["material_role"] = canonical
            repairs.append(f"components[{index}]: {role} → {canonical}（材质名换成角色名）")
        else:
            instance["material_role"] = None
            repairs.append(
                f"components[{index}]: {role} 在本材质方案里没有对应材质，降级为未表态"
            )
    return repairs


def attach_material_plan(
    document: DesignDocument | dict[str, Any],
    material_plan: dict[str, Any],
    *,
    role_repairs: list[str] | None = None,
) -> DesignDocument:
    """把已解析的材质方案写入当前设计 revision，不制造虚假的新设计版本。

    ``role_repairs`` 是可选出参：把实例角色名的归一记录（见
    :func:`_repair_instance_material_roles`）回给调用方进诊断账本。用出参而不是改
    返回值，是为了让"记录"这件事**只发生在材质方案与图纸相遇的这一个收口点**上。
    """

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    data = doc.model_dump(mode="json")
    # 归一必须在写入方案**之前**：校验器要求实例角色名能落到方案里的材质，
    # 而这些名字本来就是方案给的（先写方案再归一也不影响结果，但顺序反了会误导读者）。
    repairs = _repair_instance_material_roles(data, material_plan)
    if repairs:
        from .normalization import field_changes
        changes = field_changes(doc.model_dump(mode="json")["decisions"]["components"],
                                data["decisions"]["components"], path="/decisions/components",
                                rule="materials.instance_roles", source="unknown")
        role_map = {r["role"]: r.get("materialId") for r in material_plan.get("roles", [])}
        for change in changes:
            if change["path"].endswith("/material_role") and role_map.get(change["after"]) == change["before"]:
                change.update(category="protocol", semantic_change=False, reason="材质名转换为指向相同材质的角色名")
        data["rule_trace"].append(RuleTrace(
            rule_id="materials.instance_roles", classification="reference", enforcement=["resolver"],
            source="material_plan roles", design_revision=doc.revision, changes=changes,
        ).model_dump(mode="json"))
    if role_repairs is not None:
        role_repairs.extend(repairs)
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
        "design_constraints": [c.model_dump(mode="json") for c in doc.constraints],
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
    """建筑投影同一确定性编译结果；物件保持原有示意解析。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    d = doc.decisions
    if isinstance(d, ObjectDecisions):
        return _resolve_object_design(doc, d)
    from .compilation import compile_document, project_compilation
    return project_compilation(doc, compile_document(doc))


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


def render_design_svg(document: DesignDocument | dict[str, Any], resolved: ResolvedDesign | None = None) -> str:
    """建筑使用编译实体的正投影；物件保留原有轮廓与尺寸表。"""

    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    from .compilation import RESOLVER_VERSION
    result = resolved
    if (result is None or result.design_hash != _stable_hash(doc)
            or (not isinstance(doc.decisions, ObjectDecisions) and (result.resolver_version != RESOLVER_VERSION or not result.projection_elements))):
        result = resolve_design(doc)
    if isinstance(doc.decisions, ObjectDecisions):
        return _render_object_svg(doc, result)
    from .preview import render_compiled_svg
    return render_compiled_svg(doc, result)
