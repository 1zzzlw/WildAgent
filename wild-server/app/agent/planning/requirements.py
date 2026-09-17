"""把公开动态任务编译为可消费、可验收的受控业务要求。"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable

from app.agent.planning.contracts import (
    AcceptanceResult,
    ExecutionPlan,
    ExecutionProgressItem,
    PlanValidationIssue,
    StructuredRequirement,
)


_PHASE_CONSUMERS = {
    "architecture": ["architecture", "design_review"],
    "material_plan": ["material_plan", "design_review", "skeleton"],
    "skeleton": ["skeleton", "component_generation", "merge", "final_validate"],
    "final_validate": ["final_validate"],
    "patch": ["patch"],
}

_COMPONENT_ALIASES = {
    "door": ("door", "门", "门窗"),
    "window": ("window", "窗户", "窗", "门窗", "opening"),
    "roof": ("roof", "屋顶"),
    "railing": ("railing", "栏杆", "护栏", "扶手"),
    "canopy": ("canopy", "雨棚", "雨篷"),
    "balcony": ("balcony", "阳台", "露台", "挑台"),
    "light": ("light", "灯光", "照明", "灯具", "光源"),
    "ramp": ("ramp", "坡道", "斜坡"),
    "bay_window": ("bay_window", "bay window", "凸窗", "飘窗"),
    "cornice": ("cornice", "檐口", "飞檐"),
    "chimney": ("chimney", "烟囱"),
}

_UNSUPPORTED_COMPONENT_ALIASES = {
    "furniture": ("furniture", "家具", "table", "chair", "桌", "椅"),
}

_ELEMENT_ALIASES = {
    "wall": ("wall", "墙体", "墙"),
    "floor": ("floor", "楼板", "地板"),
    "column": ("column", "柱子", "柱"),
    "beam": ("beam", "梁"),
    "stair": ("stair", "楼梯"),
}

_ROOF_TYPES = ("flat", "gable", "hip", "shed", "dome", "chinese_curved")

# 已知阶段 → (该阶段权威产物, 该阶段可确定检查器)。
# 阶段本身比验收文本里的关键词更强：文本只是描述，phase 才是服务端批准的执行位置。
_PHASE_OUTCOME = {
    "architecture": ("architecture_plan", "architecture_plan_exists"),
    "material_plan": ("material_plan", "material_plan_exists"),
    "skeleton": ("skeleton_blueprint", "skeleton_schema"),
    "final_validate": ("final_blueprint", "final_validation_zero_errors"),
    "patch": ("scene_patch", "scene_patch_exists"),
}

# door/window 的配额由 architecture 阶段的立面 pattern 解析得出（见
# `normalize_architecture_plan`），属于派生值。结构化要求只能对它们做违规检查，
# 不能改写配额，否则立面上的实际槽位数量会与配额互相矛盾。
_PATTERN_GOVERNED_OPENINGS = frozenset({"door", "window"})

# 纯主观验收无法由程序判定。它们既不能假装通过，也不该阻断交付，
# 因此标为 needs_review（warning），由用户在计划审核阶段确认。
_SUBJECTIVE_TERMS = (
    "美观",
    "协调",
    "和谐",
    "合理",
    "舒适",
    "大气",
    "简洁",
    "品质",
    "体验",
    "整体感",
    "效果好",
    "宜居",
    "高级感",
    "现代感",
    "艺术感",
)

_NUMBER_WORDS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _term_present(folded: str, term: str) -> bool:
    """英文别名按词边界匹配，中文别名按子串匹配。

    没有词边界时，`chair` 会命中 `armchair`、`table` 会命中 `comfortable`，
    把普通验收条件误判成“当前系统不支持”，进而在校验阶段硬阻断整轮生成。
    """

    normalized = term.casefold()
    if not normalized:
        return False
    if normalized.isascii():
        pattern = rf"(?<![a-z0-9_]){re.escape(normalized)}(?![a-z0-9_])"
        return re.search(pattern, folded) is not None
    return normalized in folded


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(_term_present(folded, term) for term in terms)


def _parse_number(value: str, default: int = 1) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if value in _NUMBER_WORDS:
        return _NUMBER_WORDS[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + _NUMBER_WORDS.get(value[1], 0)
    if value.endswith("十") and len(value) == 2:
        return _NUMBER_WORDS.get(value[0], 1) * 10
    return default


def _minimum_count(text: str) -> int:
    match = re.search(r"至少(?:添加|生成|布置|包含|配置|存在)?\s*([一二两三四五六七八九十\d]+)", text)
    return _parse_number(match.group(1), 1) if match else 1


def _mentioned(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    return [name for name, terms in aliases.items() if _contains_any(text, terms)]


def _requirement(
    *,
    task_id: str,
    acceptance_index: int,
    description: str,
    phase: str,
    kind: str,
    target: str,
    operator: str,
    expected: Any,
    consumers: list[str] | None = None,
    validator: str,
    severity: str = "error",
    support_status: str = "supported",
) -> StructuredRequirement:
    acceptance_id = f"acc_{task_id}_{acceptance_index}"
    return {
        "id": f"req_{task_id}_{acceptance_index}",
        "source_task_id": task_id,
        "source_acceptance_id": acceptance_id,
        "description": description,
        "phase": phase,
        "kind": kind,
        "target": target,
        "operator": operator,
        "expected": expected,
        "consumers": list(consumers or _PHASE_CONSUMERS.get(phase, [phase])),
        "validator": validator,
        "severity": severity,
        "support_status": support_status,
    }


def _compile_acceptance(
    task_id: str,
    acceptance_index: int,
    description: str,
    phase: str,
) -> StructuredRequirement:
    text = " ".join(description.split())
    folded = text.casefold()

    # 当前主链不再设计房间平面，也没有 furniture 组件。此类计划必须在审核前暴露，
    # 不能让模型写进计划后静默显示 completed。
    unsupported_components = _mentioned(text, _UNSUPPORTED_COMPONENT_ALIASES)
    if unsupported_components:
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="unsupported_capability",
            target=f"component.{unsupported_components[0]}",
            operator="unsupported",
            expected=True,
            validator="unsupported",
            support_status="unsupported",
        )
    if _contains_any(text, ("房间位置", "房间布局", "功能分区平面", "平面草图", "内部隔墙")):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="unsupported_capability",
            target="architecture.floor_plan",
            operator="unsupported",
            expected=True,
            validator="unsupported",
            support_status="unsupported",
        )
    if _contains_any(text, ("车库", "后院", "花园", "garage", "backyard", "garden")):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="unsupported_capability",
            target="architecture.semantic_space",
            operator="unsupported",
            expected=True,
            validator="unsupported",
            support_status="unsupported",
        )

    overhang_match = re.search(
        r"(?:出檐|挑檐|屋檐|overhang).*?(?:至少|不小于|>=|≥)\s*(\d+(?:\.\d+)?)\s*(?:m|米)?",
        text,
        re.IGNORECASE,
    )
    if overhang_match:
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="architecture_roof_overhang",
            target="architecture.roof.overhang",
            operator="gte",
            expected=float(overhang_match.group(1)),
            consumers=["architecture", "component_generation", "final_validate"],
            validator="architecture_roof_overhang",
        )

    # 层数检查必须在 component 检查之前，因为"包含X层"会同时匹配组件规则。
    # 只有明确描述建筑总层数时才识别为 architecture_floor_count。
    # 关键判定条件：
    # (1) 匹配到"X层"的表达
    # (2) 有明确的总层数表达（如"共X层"、"X层几何"、"X层结构"）
    # (3) 不是对某一层的属性描述（如"一层外墙"、"一层层高"）
    floor_matches = re.findall(r"([一二两三四五六七八九十\d]+)\s*层", text)
    if floor_matches:
        # 检查是否是总层数约束
        is_total_floor_count = (
            # 明确的总数表达
            _contains_any(text, ("共", "总共", "分为"))
            # 或者是结构性描述（带"几何"、"结构"等）
            or _contains_any(text, ("层几何", "层结构", "层建筑"))
            # 或者是明确的层数特征
            or _contains_any(text, ("单层", "多层"))
        )
        
        # 排除对单个楼层的属性或位置描述
        is_single_floor_description = _contains_any(
            text,
            (
                # 属性描述
                "层高", "层地板", "层天花", "层外墙", "层内墙", "层空间", "层墙顶",
                "层主要空间", "层楼板", "层门窗", "层开口",
                # 材质/外观描述
                "层使用", "层材质", "层采用",
                # 位置描述
                "位于", "设在", "布置在", "放在",
            )
        )
        
        if is_total_floor_count and not is_single_floor_description:
            floor_count = max(_parse_number(value, 1) for value in floor_matches)
            return _requirement(
                task_id=task_id,
                acceptance_index=acceptance_index,
                description=text,
                phase=phase,
                kind="architecture_floor_count",
                target="architecture.massing.floors",
                operator="eq",
                expected=floor_count,
                consumers=["architecture", "skeleton", "final_validate"],
                validator="architecture_floor_count",
            )

    components = _mentioned(text, _COMPONENT_ALIASES)
    if components and _contains_any(
        text,
        ("至少", "生成", "添加", "包含", "布置", "存在", "配置", "成功", "完成"),
    ):
        # "/" 是纯符号，不能按英文词的词边界判定：在 "door/window" 里斜杠两侧都是
        # 字母，词边界规则会判它不成立，把本来是"任一"的要求错判成"全部"。
        is_alternative = len(components) > 1 and (
            _contains_any(text, ("或", "任选")) or "/" in text
        )
        expected = {
            "types": components,
            "minimum": _minimum_count(text),
        }
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="component_any" if is_alternative else "component_all",
            target="blueprint.components",
            operator="contains_any" if is_alternative else "contains_all",
            expected=expected,
            consumers=["architecture", "skeleton", "component_generation", "final_validate"],
            validator="component_presence",
        )

    elements = _mentioned(text, _ELEMENT_ALIASES)
    if elements and _contains_any(text, ("生成", "包含", "必要", "完整", "所有")):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="element_all",
            target="blueprint.elements",
            operator="contains_all",
            expected={"types": elements, "minimum": 1},
            consumers=["skeleton", "merge", "final_validate"],
            validator="element_presence",
        )

    dimensions = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|米)?\s*[×xX*]\s*(\d+(?:\.\d+)?)", text)
    if dimensions:
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="architecture_dimensions",
            target="architecture.massing",
            operator="near",
            expected={
                "width": float(dimensions.group(1)),
                "depth": float(dimensions.group(2)),
                "tolerance": 0.5,
            },
            consumers=["architecture", "skeleton", "final_validate"],
            validator="architecture_dimensions",
        )

    roof_types = [roof_type for roof_type in _ROOF_TYPES if roof_type in folded]
    explicit_roof = roof_types and not re.search(r"(?:如|例如|比如)\s*`?" + re.escape(roof_types[0]), folded)
    if explicit_roof and _contains_any(text, ("必须", "使用", "采用", "屋顶", "类型")):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="architecture_roof_type",
            target="architecture.roof.type",
            operator="eq",
            expected=roof_types[0],
            consumers=["architecture", "component_generation", "final_validate"],
            validator="architecture_roof_type",
        )

    # 阶段优先：先由 phase 决定权威检查器，关键词只用于补充更精确的判定。
    # 旧实现让 "可校验" 这类通用词先命中 final_validate，导致 patch 阶段的
    # 验收被交给一个在 edit 链路中永远不会运行的检查器。
    outcome = _PHASE_OUTCOME.get(phase)
    if outcome is None:
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="unresolved_acceptance",
            target="uncompiled_acceptance",
            operator="manual_review",
            expected=True,
            consumers=[phase] if phase else [],
            validator="needs_review",
            severity="warning",
            support_status="needs_review",
        )
    target, validator = outcome

    if _contains_any(text, _SUBJECTIVE_TERMS):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="subjective_acceptance",
            target=target,
            operator="manual_review",
            expected=True,
            validator="needs_review",
            severity="warning",
            support_status="needs_review",
        )

    return _requirement(
        task_id=task_id,
        acceptance_index=acceptance_index,
        description=text,
        phase=phase,
        kind="phase_outcome",
        target=target,
        operator="exists",
        expected=True,
        validator=validator,
    )


def compile_structured_requirements(plan: ExecutionPlan | dict[str, Any]) -> list[StructuredRequirement]:
    """把每条自然语言 acceptance 编译成带来源和检查器的受控要求。"""

    requirements: list[StructuredRequirement] = []
    for task in plan.get("dynamic_tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        phase = str(task.get("phase") or "")
        for index, acceptance in enumerate(task.get("acceptance") or [], start=1):
            description = str(acceptance).strip()
            if description:
                requirements.append(
                    _compile_acceptance(task_id, index, description, phase)
                )
    return requirements


def validate_structured_requirements(
    requirements: object,
) -> list[PlanValidationIssue]:
    """检查编译结果是否完整，并在审核前阻断明确不支持的能力。"""

    if not isinstance(requirements, list) or not requirements:
        return [{"code": "missing_structured_requirements", "message": "计划没有可验收的结构化要求"}]
    issues: list[PlanValidationIssue] = []
    ids: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, dict):
            issues.append({"code": "invalid_structured_requirement", "message": "结构化要求必须是对象"})
            continue
        requirement_id = str(requirement.get("id") or "")
        if not requirement_id or requirement_id in ids:
            issues.append({"code": "duplicate_requirement_id", "message": f"结构化要求 ID 缺失或重复：{requirement_id}"})
        ids.add(requirement_id)
        if not requirement.get("consumers") or not str(requirement.get("validator") or ""):
            issues.append({
                "code": "incomplete_structured_requirement",
                "message": f"结构化要求 {requirement_id} 缺少消费者或检查器",
            })
        if requirement.get("support_status") == "unsupported":
            issues.append({
                "code": "unsupported_plan_requirement",
                "message": f"当前 Agent 能力无法执行：{requirement.get('description')}",
            })
    return issues


def initialize_acceptance_results(
    requirements: list[StructuredRequirement],
) -> dict[str, AcceptanceResult]:
    results: dict[str, AcceptanceResult] = {}
    for requirement in requirements:
        support_status = requirement["support_status"]
        if support_status == "unsupported":
            status, message = "unsupported", "当前系统不支持该要求"
        elif support_status == "needs_review":
            status, message = "not_checked", "该验收条件无法由程序判定，需要在计划审核时人工确认"
        else:
            status, message = "pending", "等待对应阶段执行"
        results[requirement["source_acceptance_id"]] = {
            "acceptance_id": requirement["source_acceptance_id"],
            "task_id": requirement["source_task_id"],
            "requirement_id": requirement["id"],
            "status": status,
            "expected": deepcopy(requirement["expected"]),
            "observed": None,
            "validator": requirement["validator"],
            "evidence_refs": [],
            "message": message,
        }
    return results


def initial_execution_progress(intent: str, research_detail: str = "") -> dict[str, ExecutionProgressItem]:
    stages = (
        ("planning_research", "plan_research_summary"),
        ("architecture", "architecture_plan"),
        ("material_plan", "material_plan"),
        ("design_review", "design_document"),
        ("skeleton", "skeleton_blueprint"),
        ("component_generation", "component_fragments"),
        ("merge", "merged_blueprint"),
        ("final_validate", "final_blueprint"),
    ) if intent == "generate" else (
        ("planning_research", "plan_research_summary"),
        ("patch", "scene_patch"),
    )
    return {
        stage: {
            "status": "completed" if stage == "planning_research" else "pending",
            "result_ref": result_ref if stage == "planning_research" else None,
            "detail": research_detail if stage == "planning_research" else "等待执行",
        }
        for stage, result_ref in stages
    }


def update_execution_progress(
    progress: dict[str, ExecutionProgressItem] | None,
    stage: str,
    status: str,
    *,
    result_ref: str | None = None,
    detail: str = "",
) -> dict[str, ExecutionProgressItem]:
    updated = deepcopy(progress or {})
    updated[stage] = {
        "status": status,
        "result_ref": result_ref,
        "detail": detail[:500],
    }
    return updated


def structured_requirement_guidance(
    requirements: list[StructuredRequirement] | None,
    consumer: str,
) -> str:
    """给业务节点提供已编译要求；只输出公开业务数据，不暴露代码对象。"""

    lines = []
    for requirement in requirements or []:
        if consumer not in requirement.get("consumers", []):
            continue
        lines.append(
            f"- [{requirement['id']}] {requirement['description']}；"
            f"目标={requirement['target']}；操作={requirement['operator']}；"
            f"期望={requirement['expected']}"
        )
    return "\n".join(lines)


def required_component_types(
    requirements: list[StructuredRequirement] | None,
) -> list[str]:
    required: list[str] = []
    for requirement in requirements or []:
        if requirement.get("support_status") != "supported":
            continue
        if requirement.get("kind") not in {"component_all", "component_any"}:
            continue
        expected = requirement.get("expected")
        types = expected.get("types", []) if isinstance(expected, dict) else []
        selected_types = types[:1] if requirement.get("kind") == "component_any" else types
        for component_type in selected_types:
            component_type = str(component_type)
            if component_type not in required:
                required.append(component_type)
    return required


def apply_structured_architecture_requirements(
    plan: dict[str, Any],
    requirements: list[StructuredRequirement] | None,
) -> dict[str, Any]:
    """把可安全确定化的批准要求写入归一化总体方案。"""

    updated = deepcopy(plan)
    required_components = list(updated.get("required_components") or [])
    component_quota = deepcopy(updated.get("component_quota") or {})
    roof = deepcopy(updated.get("roof") or {})
    for requirement in requirements or []:
        if requirement.get("support_status") != "supported":
            continue
        kind = requirement.get("kind")
        expected = requirement.get("expected")
        if kind == "architecture_roof_type":
            roof["type"] = str(expected)
            continue
        if kind == "architecture_roof_overhang":
            roof["overhang"] = max(
                float(roof.get("overhang") or 0),
                float(expected),
            )
            continue
        if kind not in {"component_all", "component_any"} or not isinstance(expected, dict):
            continue
        types = list(expected.get("types") or [])
        if kind == "component_any":
            types = types[:1]
        minimum = max(1, int(expected.get("minimum") or 1))
        for component_type in types:
            name = str(component_type)
            if name not in required_components:
                required_components.append(name)
            if name in _PATTERN_GOVERNED_OPENINGS:
                # door/window 的配额由立面 pattern 解析得出，是**派生值**而不是可写约束。
                # 在这里抬高 min 会让配额与实际槽位数量互相矛盾，DesignDocument 的
                # “槽位数量必须落在配额内” 不变量随即失败。是否达标由
                # architecture_requirement_violations 按真实槽位数量判定。
                continue
            quota = dict(component_quota.get(name) or {})
            quota["min"] = max(minimum, int(quota.get("min") or 0))
            quota["max"] = max(quota["min"], int(quota.get("max") or quota["min"]))
            quota.setdefault("note", "来自已批准执行计划的结构化要求")
            component_quota[name] = quota
    updated["required_components"] = required_components
    updated["component_quota"] = component_quota
    updated["roof"] = roof
    return updated


def _opening_slot_counts(plan: dict[str, Any]) -> dict[str, int]:
    """统计该方案立面 pattern 会实际执行的门窗槽位数量。

    与 `DesignDocument` 的校验使用同一个实现，避免“检查认为达标、契约却拒绝”的分歧。
    """

    from app.agent.generation.architecture.planning import _facade_opening_counts

    facades = plan.get("facades") if isinstance(plan.get("facades"), dict) else {}
    massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
    modeled_floors = int(massing.get("modeled_floors") or massing.get("floors") or 1)
    return _facade_opening_counts(facades, modeled_floors)


def architecture_requirement_violations(
    plan: dict[str, Any],
    requirements: list[StructuredRequirement] | None,
) -> list[str]:
    """返回候选违反的可确定检查的 architecture 硬约束 ID。"""

    violations: list[str] = []
    massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
    roof = plan.get("roof") if isinstance(plan.get("roof"), dict) else {}
    required_components = set(plan.get("required_components") or [])
    opening_slots = _opening_slot_counts(plan)
    for requirement in requirements or []:
        if "architecture" not in requirement.get("consumers", []):
            continue
        kind = requirement.get("kind")
        expected = requirement.get("expected")
        matched = True
        if kind == "architecture_floor_count":
            matched = int(massing.get("floors") or 0) == int(expected)
        elif kind == "architecture_dimensions" and isinstance(expected, dict):
            tolerance = float(expected.get("tolerance", 0.5))
            matched = (
                abs(float(massing.get("width") or 0) - float(expected.get("width") or 0)) <= tolerance
                and abs(float(massing.get("depth") or 0) - float(expected.get("depth") or 0)) <= tolerance
            )
        elif kind == "architecture_roof_type":
            matched = str(roof.get("type") or "") == str(expected)
        elif kind == "architecture_roof_overhang":
            matched = float(roof.get("overhang") or 0) >= float(expected)
        elif kind in {"component_all", "component_any"} and isinstance(expected, dict):
            matched = _component_requirement_delivered(
                kind,
                expected,
                required_components,
                opening_slots,
            )
        if not matched:
            violations.append(str(requirement.get("id") or ""))
    return violations


def _component_requirement_delivered(
    kind: str,
    expected: dict[str, Any],
    required_components: set[str],
    opening_slots: dict[str, int],
) -> bool:
    """判断候选是否真的提供了要求的构件数量。

    对 door/window 必须按立面实际槽位数量判断，不能只看 `required_components`：
    要求注入本身就会把这些类型写进 `required_components`，只看名单等于让检查恒为真，
    候选即使少给门窗也会通过筛选，最后在 DesignDocument 契约处才炸掉。
    """

    types = [str(item) for item in expected.get("types", [])]
    if kind == "component_any":
        types = types[:1]
    minimum = max(1, int(expected.get("minimum") or 1))

    def satisfied(component_type: str) -> bool:
        if component_type in _PATTERN_GOVERNED_OPENINGS:
            return opening_slots.get(component_type, 0) >= minimum
        return component_type in required_components

    if kind == "component_any":
        return any(satisfied(item) for item in types)
    return all(satisfied(item) for item in types)


def _blueprint_entities(view: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    blueprint = (
        view.get("final_blueprint")
        or view.get("merged_blueprint")
        or view.get("skeleton_blueprint")
        or {}
    )
    geometry = blueprint.get("geometry", {}) if isinstance(blueprint, dict) else {}
    elements = geometry.get("elements", []) if isinstance(geometry, dict) else []
    components = geometry.get("components", []) if isinstance(geometry, dict) else []
    return (
        [item for item in elements if isinstance(item, dict)],
        [item for item in components if isinstance(item, dict)],
    )


def _check_requirement(
    requirement: StructuredRequirement,
    view: dict[str, Any],
) -> tuple[str, Any, list[str], str]:
    validator = requirement["validator"]
    expected = requirement["expected"]
    if requirement["support_status"] == "unsupported":
        return "unsupported", None, [], "当前系统不支持该要求"
    if requirement["support_status"] == "needs_review":
        # 无法机器判定：既不能算通过，也不作为阻断项。
        return "not_checked", None, [], "该验收条件无法由程序判定，需要人工确认"

    architecture_plan = view.get("architecture_plan") or {}
    if validator == "architecture_plan_exists":
        passed = isinstance(architecture_plan, dict) and bool(architecture_plan)
        return (
            "passed" if passed else "failed",
            passed,
            ["architecture_plan"] if passed else [],
            "总体方案已生成" if passed else "总体方案缺失",
        )
    if validator == "architecture_floor_count":
        observed = (
            (architecture_plan.get("massing") or {}).get("floors")
            if isinstance(architecture_plan, dict)
            else None
        )
        passed = observed == expected
        return (
            "passed" if passed else "failed",
            observed,
            ["architecture_plan.massing.floors"],
            f"实际层数为 {observed}",
        )
    if validator == "architecture_dimensions":
        massing = architecture_plan.get("massing", {}) if isinstance(architecture_plan, dict) else {}
        observed = {"width": massing.get("width"), "depth": massing.get("depth")}
        tolerance = float(expected.get("tolerance", 0.5)) if isinstance(expected, dict) else 0.5
        passed = isinstance(expected, dict) and (
            abs(float(observed["width"] or 0) - float(expected.get("width") or 0)) <= tolerance
            and abs(float(observed["depth"] or 0) - float(expected.get("depth") or 0)) <= tolerance
        )
        return (
            "passed" if passed else "failed",
            observed,
            ["architecture_plan.massing"],
            f"实际尺寸为 {observed}",
        )
    if validator == "architecture_roof_type":
        observed = (
            (architecture_plan.get("roof") or {}).get("type")
            if isinstance(architecture_plan, dict)
            else None
        )
        passed = observed == expected
        return (
            "passed" if passed else "failed",
            observed,
            ["architecture_plan.roof.type"],
            f"实际屋顶类型为 {observed}",
        )
    if validator == "architecture_roof_overhang":
        observed = (
            (architecture_plan.get("roof") or {}).get("overhang")
            if isinstance(architecture_plan, dict)
            else None
        )
        passed = float(observed or 0) >= float(expected)
        return (
            "passed" if passed else "failed",
            observed,
            ["architecture_plan.roof.overhang"],
            f"实际出檐为 {observed}",
        )
    if validator == "material_plan_exists":
        material_plan = view.get("material_plan")
        observed = len(material_plan.get("roles", [])) if isinstance(material_plan, dict) else 0
        passed = observed > 0
        return (
            "passed" if passed else "failed",
            observed,
            ["material_plan"] if passed else [],
            f"材质角色数量为 {observed}",
        )
    if validator == "skeleton_schema":
        skeleton = view.get("skeleton_blueprint")
        passed = isinstance(skeleton, dict) and isinstance(
            (skeleton.get("geometry") or {}).get("elements"),
            list,
        )
        observed = (
            len((skeleton.get("geometry") or {}).get("elements", []))
            if isinstance(skeleton, dict)
            else 0
        )
        return (
            "passed" if passed else "failed",
            observed,
            ["skeleton_blueprint"] if passed else [],
            f"主体元素数量为 {observed}",
        )
    if validator in {"component_presence", "element_presence"}:
        elements, components = _blueprint_entities(view)
        # roof 属于 geometry.elements，其余动态细部通常属于 components。
        # 组件验收同时观察两类实体，避免把合法屋顶误判为缺失。
        entities = components + elements if validator == "component_presence" else elements
        counts: dict[str, int] = {}
        for item in entities:
            entity_type = str(item.get("type") or item.get("componentType") or "").casefold()
            counts[entity_type] = counts.get(entity_type, 0) + 1
        types = [
            str(item).casefold()
            for item in (
                expected.get("types", []) if isinstance(expected, dict) else []
            )
        ]
        minimum = int(expected.get("minimum", 1)) if isinstance(expected, dict) else 1
        if requirement["operator"] == "contains_any":
            passed = any(counts.get(entity_type, 0) >= minimum for entity_type in types)
        else:
            passed = all(counts.get(entity_type, 0) >= minimum for entity_type in types)
        observed = {entity_type: counts.get(entity_type, 0) for entity_type in types}
        evidence = [
            str(item.get("id"))
            for item in entities
            if str(item.get("type") or item.get("componentType") or "").casefold()
            in types
            and item.get("id")
        ]
        return ("passed" if passed else "failed", observed, evidence, f"实际数量：{observed}")
    if validator == "final_validation_zero_errors":
        observed = int(view.get("validation_error_count") or 0)
        passed = (
            view.get("status") == "complete"
            and observed == 0
            and isinstance(view.get("final_blueprint"), dict)
        )
        return ("passed" if passed else "failed", observed, ["validation_results"], f"最终校验错误数为 {observed}")
    if validator == "scene_patch_exists":
        patch = view.get("scene_patch")
        passed = isinstance(patch, dict)
        return (
            "passed" if passed else "failed",
            passed,
            ["scene_patch"] if passed else [],
            "ScenePatch 已生成" if passed else "ScenePatch 缺失",
        )
    return "not_checked", None, [], "没有注册可执行检查器"


def evaluate_acceptance_results(
    *,
    state: dict[str, Any],
    result: dict[str, Any],
    phase: str,
) -> dict[str, AcceptanceResult]:
    """在阶段边界执行适用检查器，并保留其他阶段已有结果。"""

    requirements = state.get("structured_requirements") or []
    updated = deepcopy(state.get("acceptance_results") or {})
    view = {**state, **result}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        consumers = requirement.get("consumers", [])
        if phase != "final_validate" and phase not in consumers:
            continue
        status, observed, evidence_refs, message = _check_requirement(requirement, view)
        # 中间阶段缺少最终组件并不等于已经失败；留给更靠后的消费者复检。
        if status == "failed" and phase != "final_validate" and "final_validate" in consumers:
            status = "pending"
            message = "当前阶段尚未满足，将在最终校验阶段复检"
        updated[requirement["source_acceptance_id"]] = {
            "acceptance_id": requirement["source_acceptance_id"],
            "task_id": requirement["source_task_id"],
            "requirement_id": requirement["id"],
            "status": status,
            "expected": deepcopy(requirement["expected"]),
            "observed": observed,
            "validator": requirement["validator"],
            "evidence_refs": evidence_refs,
            "message": message,
        }
    return updated


def update_dynamic_task_statuses(
    plan: ExecutionPlan | dict[str, Any],
    acceptance_results: dict[str, AcceptanceResult],
    progress: dict[str, ExecutionProgressItem],
    requirements: list[StructuredRequirement] | None = None,
) -> ExecutionPlan:
    """根据逐条验收结果计算动态任务状态，不再按 phase 批量完成。

    只有必需项（severity=error）全部 passed 或 not_applicable 才允许完成；
    needs_review 这类非阻断项保持 not_checked，不会冒充通过，也不会卡死任务。
    """

    blocking_by_acceptance = {
        str(item.get("source_acceptance_id")): str(item.get("severity") or "error") == "error"
        for item in requirements or []
        if isinstance(item, dict)
    }

    def _is_required(item: dict[str, Any]) -> bool:
        # 没有传入结构化要求时按旧行为处理：所有验收都是必需项。
        return blocking_by_acceptance.get(str(item.get("acceptance_id")), True)

    def _settled(item: dict[str, Any]) -> bool:
        status = str(item.get("status"))
        if status in {"passed", "not_applicable"}:
            return True
        return not _is_required(item) and status in {"failed", "not_checked", "unsupported"}

    updated = deepcopy(plan)
    for task in updated.get("dynamic_tasks", []):
        task_id = str(task.get("id") or "")
        task_results = [item for item in acceptance_results.values() if item.get("task_id") == task_id]
        phase_status = (progress.get(str(task.get("phase") or "")) or {}).get("status")
        if any(
            _is_required(item) and str(item.get("status")) in {"failed", "unsupported"}
            for item in task_results
        ):
            task["status"] = "failed"
        elif task_results and all(_settled(item) for item in task_results):
            task["status"] = "completed"
        elif phase_status in {"in_progress", "completed"}:
            task["status"] = "in_progress"
        else:
            task["status"] = "pending"
        passed_refs = [
            ref
            for item in task_results
            if item.get("status") == "passed"
            for ref in item.get("evidence_refs", [])
        ]
        task["result_ref"] = passed_refs[0] if passed_refs else None
    return updated


def blocking_acceptance_failures(
    requirements: list[StructuredRequirement] | None,
    results: dict[str, AcceptanceResult] | None,
) -> list[AcceptanceResult]:
    required_ids = {
        item["source_acceptance_id"]
        for item in requirements or []
        if item.get("severity") == "error"
    }
    return [
        item for acceptance_id, item in (results or {}).items()
        if acceptance_id in required_ids and item.get("status") not in {"passed", "not_applicable"}
    ]
