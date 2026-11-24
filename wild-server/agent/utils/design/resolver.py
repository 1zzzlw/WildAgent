"""构建和解析 DesignDocument。"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from agent.utils.design.contracts import ArchitectureDecisions
from agent.utils.design.contracts import ComponentObject
from agent.utils.design.contracts import DesignConstraint
from agent.utils.design.contracts import DesignDocument
from agent.utils.design.contracts import DesignRequirements
from agent.utils.design.contracts import ObjectDecisions
from agent.utils.design.contracts import ResolvedDesign
from agent.utils.design.contracts import RuleTrace
from agent.utils.design.contracts import utc_now_iso


def _stable_hash(document: DesignDocument) -> str:
    payload = {
        "schema_version": document.schema_version,
        "design_id": document.design_id,
        "revision": document.revision,
        "requirements": document.requirements.model_dump(mode="json"),
        "decisions": document.decisions.model_dump(mode="json"),
        "constraints": [item.model_dump(mode="json") for item in document.constraints],
        "locks": document.locks,
        "normalization_evidence": [
            t.model_dump(mode="json") for t in document.rule_trace if t.changes
        ],
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
    """把完整方案保存为版本化设计文档；按目标类型分派建筑或物件。"""

    if isinstance(previous, DesignDocument):
        old = previous
    elif isinstance(previous, dict):
        old = DesignDocument.model_validate(previous)
    else:
        old = None
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

    empty_pattern_changes = _normalize_empty_facade_patterns(plan)

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
    constraints = _design_constraints(plan, old, source_request, revision_feedback)

    materials = _merge_material_intent(plan, old)

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
        decisions=_architecture_decisions(
            plan, complexity, profile, curtain_wall, materials
        ),
        constraints=constraints,
        locks=list(old.locks if old else []),
        rule_trace=[],
    )

    changes = _record_normalization(
        document, plan, empty_pattern_changes, old, constraints
    )

    if changes:
        _update_normalized_rationale(document)
    return document


def _normalize_empty_facade_patterns(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """将显式空立面展开为空开间，并记录等价的协议规范化。"""
    from agent.utils.design.normalization import field_changes

    empty_pattern_changes = []
    layouts = [("/decisions/facades", plan.get("facades"))]
    layouts.extend(
        (f"/decisions/volumes/{index}/facades", volume.get("facades"))
        for index, volume in enumerate(
            plan.get("volumes", []) if isinstance(plan.get("volumes"), list) else []
        )
        if isinstance(volume, dict)
    )
    for path, facades in layouts:
        for face, facade in facades.items() if isinstance(facades, dict) else []:
            if (
                not isinstance(facade, dict)
                or type(facade.get("bays")) is not int
                or facade["bays"] < 1
            ):
                continue
            for key in ("ground_pattern", "upper_pattern"):
                if facade.get(key) == []:
                    facade[key] = ["empty"] * facade["bays"]
                    change = field_changes(
                        [],
                        facade[key],
                        path=f"{path}/{face}/{key}",
                        rule="architecture.facade_empty_pattern",
                        source="model",
                    )[0]
                    change.update(
                        category="protocol",
                        semantic_change=False,
                        reason="显式空数组表示没有开口，与逐开间 empty 等价；不改变围护或构件设计",
                    )
                    empty_pattern_changes.append(change)
    return empty_pattern_changes


def _design_constraints(
    plan, old, source_request, revision_feedback
) -> list[DesignConstraint]:
    """继承旧约束，再合并当前需求中可追溯的设计约束。"""
    constraints = [
        DesignConstraint(
            id="request.source",
            kind="user_hard",
            target="/requirements/source_request",
            expression="设计必须保持用户原始需求中明确提出的条件",
            source="user_request",
        ),
    ]
    if old:
        current_ids = {item.id for item in constraints}
        constraints.extend(
            item for item in old.constraints if item.id not in current_ids
        )

    from agent.utils.design.completeness import merge_design_constraints

    constraints = merge_design_constraints(
        constraints, plan.get("design_constraints"), source_request, revision_feedback
    )
    return constraints


def _merge_material_intent(plan, old) -> dict[str, Any]:
    """继承材质意图；新方案不直接覆盖已经解析的材质实现。"""
    materials = old.decisions.materials.model_dump(mode="json") if old else {}
    if isinstance(plan.get("materials"), dict):
        for key, value in plan["materials"].items():
            if key != "resolved_plan":
                materials[key] = value
    if isinstance(plan.get("materials"), dict) and "regions" in plan["materials"]:
        materials["regions"] = (plan.get("materials") or {}).get("regions", [])
    elif "material_regions" in plan:
        materials["regions"] = plan["material_regions"]
    return materials


def _architecture_decisions(plan, complexity, profile, curtain_wall, materials) -> ArchitectureDecisions:
    """完整保留设计字段；公共契约负责默认值，避免手写字段映射遗漏新增模块。"""
    metadata = {
        "schema_version", "profile", "design_constraints", "normalization_changes",
        "curtain_wall", "material_regions", "parameters",
    }
    payload = {key: value for key, value in plan.items() if key not in metadata}
    payload["complexity"] = complexity
    payload["materials"] = materials
    if not payload.get("envelope"):
        payload["envelope"] = {"system": "curtain_wall" if curtain_wall else "unspecified",
                               "curtain_wall": {} if curtain_wall else None}
    return ArchitectureDecisions.model_validate(payload)


def _record_normalization(
    document, plan, empty_pattern_changes, old, constraints
) -> list[dict[str, Any]]:
    """为规范化结果绑定约束和来源，并继承历史变更证据。"""
    from agent.utils.design.normalization import field_changes

    changes = empty_pattern_changes + (plan.get("normalization_changes") or [])
    raw_roof = plan.get("roof")
    if (
        isinstance(raw_roof, dict)
        and "ridge_axis" in raw_roof
        and raw_roof["ridge_axis"] != document.decisions.roof.ridge_axis
    ):
        axis_changes = field_changes(
            raw_roof["ridge_axis"],
            document.decisions.roof.ridge_axis,
            path="/decisions/roof/ridge_axis",
            rule="roof.axis_applicability",
            source="model",
        )
        for change in axis_changes:
            change.update(
                category="protocol",
                semantic_change=False,
                reason="当前已知屋型没有可选屋脊方向；使用兼容默认值，不改变屋面形态",
            )
        changes.extend(axis_changes)
    if old:
        document.rule_trace.extend(t for t in old.rule_trace if t.changes)
    if changes:
        for change in changes:
            target = change["path"]
            change["constraint_ids"] = [
                c.id
                for c in constraints
                if c.target == target
                or c.target.startswith(target + "/")
                or target.startswith(c.target + "/")
            ]
            for c in constraints:
                if (
                    c.id in change["constraint_ids"]
                    and c.kind == "user_hard"
                    and c.source_quote
                    and c.check == "equals"
                    and c.target == target
                ):
                    if change["before"] == c.expected:
                        change["input_source"] = "user"
                    if change["after"] == c.expected:
                        change["output_source"] = "user"
        document.rule_trace.append(
            RuleTrace(
                rule_id="architecture.normalize",
                classification="reference",
                enforcement=["planner", "validator"],
                source="architecture normalization",
                design_revision=document.revision,
                changes=changes,
            )
        )
    return changes


def _update_normalized_rationale(document: DesignDocument) -> None:
    """同步规范化后的决策说明，保留尚需核对的设计状态。"""
    from agent.utils.design.normalization import decision_summary

    document.decisions.design_rationale = [
        decision_summary(architecture_plan_from_document(document)),
        *[
            text
            for text in document.decisions.design_rationale
            if not text.removeprefix("[待核对] ").startswith("[决策事实]")
        ][:11],
    ]

    # Keep prose explicitly unverified when it no longer has reliable decision evidence.
    from agent.utils.design.completeness import evaluate_design

    gaps = evaluate_design(document, _stable_hash(document))
    if any(g.status != "satisfied" for g in gaps):
        document.decisions.design_rationale = [
            (
                text
                if text.startswith(("[待核对]", "[决策事实]"))
                else "[待核对] " + text
            )
            for text in document.decisions.design_rationale
        ]
        has_semantic_change = False
        for trace in document.rule_trace:
            if any(change.get("semantic_change") for change in trace.changes):
                has_semantic_change = True
                break
        if has_semantic_change:
            concept = document.decisions.concept
            document.decisions.concept = (
                concept
                if concept.startswith("[待核对]")
                else ("[待核对] " + concept)[:240]
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
            item for item in old.constraints if item.id not in current_ids
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
                source="rules-v1:furniture",
            ),
        ],
    )


def attach_material_plan(
    document: DesignDocument | dict[str, Any],
    material_plan: dict[str, Any],
) -> DesignDocument:
    """附加材质实现，不改写原始构件材质意图。"""
    doc = (
        document
        if isinstance(document, DesignDocument)
        else DesignDocument.model_validate(document)
    )
    data = doc.model_dump(mode="json")
    concept = str(material_plan.get("concept") or "").strip()
    palette = material_plan.get("palette")
    keywords = [concept] if concept else []
    if isinstance(palette, list):
        keywords.extend(str(item).strip() for item in palette if str(item).strip())
    data["decisions"]["materials"] = {
        **data["decisions"]["materials"],
        "keywords": list(
            dict.fromkeys(
                [*data["decisions"]["materials"].get("keywords", []), *keywords]
            )
        ),
        "resolved_plan": deepcopy(material_plan),
    }
    data["status"] = "draft"
    data["approved_at"] = None
    data["updated_at"] = utc_now_iso()
    return DesignDocument.model_validate(data)


def architecture_plan_from_document(
    document: DesignDocument | dict[str, Any],
) -> dict[str, Any]:
    """输出同一设计决定的平铺视图，保留轮廓、宿主、构造与完整材料意图。"""
    doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
    if isinstance(doc.decisions, ObjectDecisions):
        return _object_plan_from_document(doc, doc.decisions)
    plan = doc.decisions.model_dump(mode="json", exclude_none=True)
    plan.update(
        schema_version="1.0",
        profile=doc.requirements.profile,
        design_constraints=[item.model_dump(mode="json") for item in doc.constraints],
        curtain_wall=doc.decisions.envelope.system == "curtain_wall",
    )
    return plan


def _object_plan_from_document(
    doc: DesignDocument, d: ObjectDecisions
) -> dict[str, Any]:
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
        "schema_version": "1.0",
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
    """解析设计文档，供计划按图纸标记落实。"""

    doc = (
        document
        if isinstance(document, DesignDocument)
        else DesignDocument.model_validate(document)
    )
    d = doc.decisions
    if isinstance(d, ObjectDecisions):
        return _resolve_object_design(doc, d)
    from agent.utils.design.compilation import project_drawing

    return project_drawing(doc)


def _resolve_object_design(doc: DesignDocument, d: ObjectDecisions) -> ResolvedDesign:
    """物件场景的可执行视图：没有标高、没有体量、没有立面槽位。"""
    from agent.utils.design.compilation import RESOLVER_VERSION
    from agent.utils.design.markers import component_markers

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
        resolver_version=RESOLVER_VERSION,
        component_markers=component_markers(doc),
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
