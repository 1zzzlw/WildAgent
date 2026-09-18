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
    RequirementSeverity,
    RequirementSupportStatus,
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

# 真实能力缺失：主链不设计内部空间（无房间坐标、无隔墙），也不处理场地语义。
# 这些要求必须**被标记出来**，但不能阻断整轮生成：把一份结构合法的计划判死，
# 用户拿到的是一张图都没有；照常生成、把缺的能力写进验收结果，用户至少拿到蓝图。
# 判定准则是"系统真的做不到 vs 做得到但表述不一致"，两者现在都不阻断，
# 区别只在 support_status 记的是"缺能力"还是"待人工确认"。
_UNSUPPORTED_INTERIOR_TERMS = ("房间位置", "房间布局", "功能分区平面", "内部隔墙")
_UNSUPPORTED_SITE_TERMS = ("车库", "后院", "花园", "garage", "backyard", "garden")

# 只是交付媒介与系统产物不一致：主链不产出 2D 平面图，但体量、立面与尺寸会由
# design_review 的 SVG 预览和 DesignDocument 呈现。这类表述降级为人工确认，
# 不阻断整轮生成——否则用户只要顺口说一句"出个平面草图"就会让计划直接判死。
# 注意：该判定放在所有量化抽取分支之后，句子里只要给出了层数、尺寸、屋顶或构件
# 等可执行指标，就按指标编译，不再按媒介判级。
_PRESENTATION_MEDIUM_TERMS = ("平面草图", "平面图", "二维平面", "2d 平面", "2d平面")

_ELEMENT_ALIASES = {
    "wall": ("wall", "墙体", "墙"),
    "floor": ("floor", "楼板", "地板"),
    "column": ("column", "柱子", "柱"),
    "beam": ("beam", "梁"),
    "stair": ("stair", "楼梯"),
}

# 材质类要求必须由 material_plan 消费，而且**必须排在构件分支之前**：
# 构件分支只看到"门窗、屋顶"就会把"材质至少N种"编译成 component_presence，
# 把种类数错读成每种构件的实例下限。这类"分支优先级"教训在文件里已出现过
# （媒介降级分支必须排在量化抽取之后），规律一样：**更具体的语义先判**。
_MATERIAL_TERMS = ("材质", "材料")

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


# 量词决定"数的是种类还是实例"：「至少3种材质」数的是种类数，
# 把它当成"每种至少3个"会让一条本该通过的要求变成阻断点。
# 真实事故（2026-09-17，req_1789634516108_eu82yreb4）：验收原文
# "材质方案包含墙体、屋顶、门窗至少3种材质" 被编译成
# types=[door, window, roof] + minimum=3（门/窗/屋顶每种>=3），
# 实际 door=1 / roof=1 → failed（severity=error）→ 整轮判死，
# 而已合并的 23 元素蓝图因 final_blueprint=None 被丢弃。
# 长量词必须排在短量词前面，否则"类型"会被"类"先吃掉。
_KIND_QUANTIFIERS = ("类型", "品种", "系列", "种", "类", "款")
_KIND_QUANTIFIER_PATTERN = "|".join(_KIND_QUANTIFIERS)

_MINIMUM_COUNT_PATTERN = re.compile(
    r"(?:至少|最少)\s*"
    r"(?:添加|生成|布置|包含|配置|存在|使用|采用|有)?\s*"
    r"(\d+|[一二两三四五六七八九十]+)\s*"
    rf"({_KIND_QUANTIFIER_PATTERN})?"
)


def _quantified_minimum(text: str) -> tuple[int | None, bool]:
    """解析「至少N<量词>」，返回 (数量, 量词是否表示种类)。

    找不到「至少N」时返回 (None, False)。
    """

    match = _MINIMUM_COUNT_PATTERN.search(text)
    if match is None:
        return None, False
    count = _parse_number(match.group(1), 1)
    return count, (match.group(2) or "") in _KIND_QUANTIFIERS


def _minimum_count(text: str) -> int:
    """实例数量下限。

    **种类量词不构成实例下限**：「至少3种材质」说的是种类数，
    不是"每种至少3个"，此时退回默认下限 1。
    """

    count, is_kind = _quantified_minimum(text)
    if count is None or is_kind:
        return 1
    return count


def _minimum_kind_count(text: str) -> int | None:
    """种类数量下限（「至少3种」→3）。不是种类量词时返回 None。"""

    count, is_kind = _quantified_minimum(text)
    return count if is_kind else None


def _mentioned(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    return [name for name, terms in aliases.items() if _contains_any(text, terms)]


# 平面宽深的两种常见表述：
#   1) 紧凑写法 "12×10"、"12x10"、"12*10"
#   2) 自然语言 "宽12米，深10米"、"宽度约12米、进深约10米"
_PLAN_DIMENSION_PAIR = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:m|米)?\s*[×xX*]\s*(\d+(?:\.\d+)?)"
)
_PLAN_WIDTH_DEPTH_PAIR = re.compile(
    r"宽(?:度)?\s*(?:约|大约|为|是|在)?\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:m|米)?"
    r"[^0-9]{0,10}?"
    r"(?:进深|深(?:度)?|长(?:度)?)\s*(?:约|大约|为|是|在)?\s*[:：]?\s*(\d+(?:\.\d+)?)"
)
# 紧邻尺寸之前的"举例"引导词。举例值只是说明量级，不能变成 near 硬判定，
# 否则模型按示例写了 12×10、架构节点算出 14×9 就会被判验收失败并阻断交付。
_ILLUSTRATIVE_LEADS = (
    "例如", "比如", "示例", "例", "如",
    "例如：", "例如:", "比如：", "比如:", "示例：", "示例:",
    "如：", "如:", "（如", "(如",
)


def _extract_plan_dimensions(text: str) -> tuple[float, float] | None:
    """提取平面宽深；被"例如/如"引导的示例值不作为可判定要求。"""

    for pattern in (_PLAN_DIMENSION_PAIR, _PLAN_WIDTH_DEPTH_PAIR):
        for match in pattern.finditer(text):
            lead = text[: match.start()].rstrip()
            if lead.endswith(_ILLUSTRATIVE_LEADS):
                continue
            return float(match.group(1)), float(match.group(2))
    return None


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
    severity: RequirementSeverity = "error",
    support_status: RequirementSupportStatus = "supported",
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

    # 当前主链不再设计房间平面，也没有 furniture 组件。此类计划必须让用户看见，
    # 但**不阻断**：引擎仍能产出可用的建筑蓝图，把它判死等于让用户连一张图都拿不到。
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
            severity="warning",
            support_status="unsupported",
        )
    if _contains_any(text, _UNSUPPORTED_INTERIOR_TERMS):
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
            severity="warning",
            support_status="unsupported",
        )
    if _contains_any(text, _UNSUPPORTED_SITE_TERMS):
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
            severity="warning",
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

    # 材质要求先于构件分支判定，且只认「N种」这种种类量词，
    # 不能让构件分支把"材质至少3种"读成"门窗屋顶每种至少3个"。
    material_kind_minimum = _minimum_kind_count(text)
    if material_kind_minimum is not None and _contains_any(text, _MATERIAL_TERMS):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="material_role_count",
            target="material_plan.roles",
            operator="gte",
            expected={"minimum": material_kind_minimum},
            consumers=["material_plan", "design_review", "skeleton", "final_validate"],
            validator="material_plan_exists",
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
    # 区分"要求存在元素"和"元素质量检查"以及"规划性描述"
    # 质量检查的关键词：对齐、一致、精确、无间隙、无重叠、合理、符合
    is_quality_check = _contains_any(
        text,
        (
            "对齐", "一致", "精确", "无间隙", "无重叠", "合理", "符合",
            "正确", "端点", "转角", "连接", "衔接",
        )
    )
    # 规划性描述：定义范围、标高体系、初步划分等，不是要求真的生成
    is_planning_description = _contains_any(
        text,
        (
            "定义", "划分", "范围", "标高体系", "初步", "大致",
            "确定", "指定", "给出", "提供依据",
        )
    )
    # element_all 只应用于 skeleton/merge/final_validate 阶段
    # architecture 阶段不生成 elements，不应该检查元素存在性
    is_element_generation_phase = phase in ("skeleton", "merge", "final_validate")
    
    if (elements 
        and not is_quality_check 
        and not is_planning_description
        and is_element_generation_phase
        and _contains_any(text, ("生成", "包含", "必要", "完整", "所有"))):
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

    dimensions = _extract_plan_dimensions(text)
    if dimensions:
        # 检测是否有"约"、"大约"、"左右"等模糊词，使用更大的容差
        is_approximate = _contains_any(text, ("约", "大约", "左右", "大致", "接近"))
        tolerance = 1.5 if is_approximate else 0.5

        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="architecture_dimensions",
            target="architecture.massing",
            operator="near",
            expected={
                "width": dimensions[0],
                "depth": dimensions[1],
                "tolerance": tolerance,
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

    # 走到这里说明层数、尺寸、屋顶、构件等量化分支都没命中，句子只剩"要一张平面图"
    # 这类表现层诉求。系统确实不产出 2D 平面图，但几何与尺寸会由 design_review 的
    # SVG 预览和 DesignDocument 呈现，因此降级为人工确认而不是终止整轮生成。
    if _contains_any(text, _PRESENTATION_MEDIUM_TERMS):
        return _requirement(
            task_id=task_id,
            acceptance_index=acceptance_index,
            description=text,
            phase=phase,
            kind="presentation_medium_mismatch",
            target="delivery.presentation",
            operator="manual_review",
            expected=True,
            consumers=[phase] if phase else [],
            validator="needs_review",
            severity="warning",
            support_status="needs_review",
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
    # 遍历每个任务的每条验收条件
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
    """检查编译结果是否完整，并把能力缺失报成非阻断提示。

    返回的每条问题都带 severity，调用方据此决定是否终止本轮：

    - **结构类问题**（缺消费者/检查器、ID 重复、类型错误）固定 `error`——
      这类计划对象本身不合法，放过去下游必然崩。
    - **能力缺失**（`support_status="unsupported"`）沿用要求自身的 severity，
      当前一律编译为 `warning`：只提示，不阻断。
    - `needs_review` 不在这里上报，它已经通过 `initialize_acceptance_results`
      的 `not_checked` 出现在计划审核面板里，多报一次只会造成同一信号两份来源。
    """

    if not isinstance(requirements, list) or not requirements:
        return [{
            "code": "missing_structured_requirements",
            "message": "计划没有可验收的结构化要求",
            "severity": "error",
        }]
    issues: list[PlanValidationIssue] = []
    ids: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, dict):
            issues.append({
                "code": "invalid_structured_requirement",
                "message": "结构化要求必须是对象",
                "severity": "error",
            })
            continue
        requirement_id = str(requirement.get("id") or "")
        if not requirement_id or requirement_id in ids:
            issues.append({
                "code": "duplicate_requirement_id",
                "message": f"结构化要求 ID 缺失或重复：{requirement_id}",
                "severity": "error",
            })
        ids.add(requirement_id)
        if not requirement.get("consumers") or not str(requirement.get("validator") or ""):
            issues.append({
                "code": "incomplete_structured_requirement",
                "message": f"结构化要求 {requirement_id} 缺少消费者或检查器",
                "severity": "error",
            })
        if requirement.get("support_status") == "unsupported":
            issues.append({
                "code": "unsupported_plan_requirement",
                "message": (
                    f"当前 Agent 不具备该能力，将按可达范围生成并标记："
                    f"{requirement.get('description')}"
                ),
                "severity": str(requirement.get("severity") or "error"),
            })
    return issues


def initialize_acceptance_results(
    requirements: list[StructuredRequirement],
) -> dict[str, AcceptanceResult]:
    results: dict[str, AcceptanceResult] = {}
    for requirement in requirements:
        support_status = requirement["support_status"]
        if support_status == "unsupported":
            status, message = (
                "unsupported",
                "当前 Agent 不具备该能力，将按可达范围生成并在交付结果中标记",
            )
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
        return (
            "unsupported",
            None,
            [],
            "当前 Agent 不具备该能力，将按可达范围生成并在交付结果中标记",
        )
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
        roles = material_plan.get("roles") if isinstance(material_plan, dict) else None
        observed = len(roles) if isinstance(roles, list) else 0
        # expected.minimum 缺省为 1，与旧行为（roles 非空即通过）完全等价。
        minimum = int(expected.get("minimum", 1)) if isinstance(expected, dict) else 1
        passed = observed >= minimum
        return (
            "passed" if passed else "failed",
            observed,
            ["material_plan"] if passed else [],
            f"材质角色数量为 {observed}（要求不少于 {minimum}）"
            if minimum > 1
            else f"材质角色数量为 {observed}",
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
        
        # balcony 内嵌 U 形栏杆，不需要独立 railing 组件
        # 如果有 balcony，则认为已经满足 railing 要求
        if "balcony" in counts and counts["balcony"] > 0:
            counts.setdefault("railing", 0)
            counts["railing"] += counts["balcony"]
        
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
            # edit（patch）链路只产 scene_patch，不跑 architecture/skeleton/material_plan 等
            # generate 阶段。planner 若把"生成宽6米建筑"这类 generate 语义塞进 edit 计划，
            # 其 consumers 指向 generate 阶段、永无消费者评估它，停在 pending 会被
            # blocking_acceptance_failures 误判阻断（实测"生成一个玻璃幕墙"报
            # "业务验收未通过：等待对应阶段执行"）。这类验收在 edit 链路不适用，直接标
            # not_applicable：既不假装通过，也不阻断交付。
            if phase == "patch" and consumers:
                updated[requirement["source_acceptance_id"]] = {
                    "acceptance_id": requirement["source_acceptance_id"],
                    "task_id": requirement["source_task_id"],
                    "requirement_id": requirement["id"],
                    "status": "not_applicable",
                    "expected": deepcopy(requirement.get("expected")),
                    "observed": None,
                    "validator": requirement.get("validator"),
                    "evidence_refs": [],
                    "message": "该验收属于生成链路阶段，编辑链路不适用",
                }
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
    # 只有 status=failed 才算"业务验收失败"，才配阻断一次交付。
    # pending 表示"尚未轮到对应阶段评估"（占位文案"等待对应阶段执行"），不是失败；
    # unsupported / not_checked(needs_review) 按项目政策"能力缺失只标记、不阻断"同样不算。
    # 历史上把"非 passed/not_applicable"一网打尽，导致 edit 链路里一条 consumers 指向
    # generate 阶段、永远停在 pending 的验收（如"生成宽6米建筑"）把整轮修改判死。
    return [
        item for acceptance_id, item in (results or {}).items()
        if acceptance_id in required_ids and item.get("status") == "failed"
    ]
