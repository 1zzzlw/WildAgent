"""可审核的 Agent 执行计划协议与建筑能力白名单。

ExecutionPlan 只描述「准备做什么」；GenerationJob 负责「后台任务正在怎么跑」。
模型和用户都不能通过计划填写 Python 函数名，实际节点只能来自本文件的注册表。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


PLAN_STEP_STATUSES = {"pending", "in_progress", "completed", "failed", "skipped"}
PLAN_STATUSES = {
    "draft",
    "reviewing",
    "approved",
    "executing",
    "revising",
    "completed",
    "failed",
}

DYNAMIC_TASK_PHASES = {
    "generate": {
        "architecture",
        "floor_plan_design",
        "material_plan",
        "skeleton",
        "decor_assembly",
        "final_validate",
    },
    "edit": {"patch"},
}

_DYNAMIC_PHASE_LABELS = {
    "architecture": "总体方案",
    "floor_plan_design": "平面设计",
    "material_plan": "材质方案",
    "skeleton": "主体装配",
    "decor_assembly": "装饰装配",
    "final_validate": "最终校验",
    "patch": "场景修改",
}


@dataclass(frozen=True, slots=True)
class PlanCapability:
    """计划可引用的受控能力；node 永远由服务端注册，不接受模型输入。"""

    type: str
    node: str
    label: str
    description: str
    read_only: bool
    allowed_intents: tuple[str, ...]
    requires_user_review: bool = False


_CAPABILITIES = (
    PlanCapability(
        "planning_research",
        "planning_research",
        "需求与知识研究",
        "读取用户需求、当前场景和建筑知识，形成计划依据。",
        True,
        ("generate", "edit"),
    ),
    PlanCapability(
        "architecture",
        "architecture",
        "总体建筑方案",
        "确定建筑体量、层数、功能层次、立面轴网和屋顶意图。",
        True,
        ("generate",),
    ),
    PlanCapability(
        "floor_plan_design",
        "floor_plan_design",
        "平面设计",
        "生成 FloorPlanIR，并执行空间、墙体、洞口和工程预审。",
        True,
        ("generate",),
    ),
    PlanCapability(
        "floor_plan_review",
        "floor_plan_review",
        "平面确认",
        "暂停并等待用户确认平面；未确认时禁止生成三维。",
        True,
        ("generate",),
        True,
    ),
    PlanCapability(
        "material_plan",
        "material_plan",
        "材质方案",
        "将审美意图解析成受控材质角色和真实资产引用。",
        True,
        ("generate",),
    ),
    PlanCapability(
        "skeleton",
        "skeleton",
        "主体装配",
        "从批准平面确定性装配墙、板、竖向交通、门窗和屋顶，并执行 G1-G6。",
        False,
        ("generate",),
    ),
    PlanCapability(
        "style_review",
        "style_review",
        "风格确认",
        "在主体通过后暂停，等待用户确认受控建筑风格。",
        True,
        ("generate",),
        True,
    ),
    PlanCapability(
        "decor_assembly",
        "decor_assembly",
        "装饰装配",
        "把风格包编译为 Decor IR，参数化装配并执行 G7。",
        False,
        ("generate",),
    ),
    PlanCapability(
        "merge",
        "merge",
        "结果合并",
        "合并主体与装饰产物，执行确定性归一化和引用闭合。",
        False,
        ("generate",),
    ),
    PlanCapability(
        "final_validate",
        "final_validate",
        "最终校验",
        "运行完整 Blueprint 校验；只有零错误结果才允许保存和加载。",
        True,
        ("generate",),
    ),
    PlanCapability(
        "patch",
        "patch",
        "场景修改提案",
        "分析当前 Blueprint 并生成仍需用户单独应用的 ScenePatch。",
        True,
        ("edit",),
        True,
    ),
)

CAPABILITY_REGISTRY: dict[str, PlanCapability] = {
    capability.type: capability for capability in _CAPABILITIES
}


def public_capabilities(intent: str) -> list[dict[str, Any]]:
    """返回可展示的能力说明，不暴露服务端可调用对象。"""

    return [
        asdict(capability)
        for capability in _CAPABILITIES
        if intent in capability.allowed_intents
    ]


def _step(
    step_type: str,
    *,
    depends_on: list[str],
    acceptance: list[str],
    status: str = "pending",
    detail: str = "",
) -> dict[str, Any]:
    capability = CAPABILITY_REGISTRY[step_type]
    return {
        "id": f"step_{step_type}",
        "type": step_type,
        "node": capability.node,
        "title": capability.label,
        "description": capability.description,
        "depends_on": list(depends_on),
        "acceptance": list(acceptance),
        "permission": "read" if capability.read_only else "mutate",
        "requires_user_review": capability.requires_user_review,
        "status": status,
        "detail": detail,
        "result_ref": None,
    }


def _text(value: Any, *, limit: int) -> str:
    """把模型字段收敛为可展示的单行文本。"""

    return " ".join(str(value or "").split())[:limit]


def fallback_dynamic_tasks(user_message: str, intent: str) -> list[dict[str, Any]]:
    """模型不可用时，根据任务语义生成确定性的本次任务，而不是空计划。"""

    if intent == "edit":
        return [
            {
                "title": "分析并形成安全修改提案",
                "objective": f"定位当前场景中与“{_text(user_message, limit=100)}”相关的对象和约束，生成可审核的 ScenePatch。",
                "phase": "patch",
                "acceptance": ["只修改用户要求的目标", "引用有效且 ScenePatch 可校验"],
                "basis": "用户修改请求与当前 Blueprint",
            }
        ]

    folded = user_message.casefold()
    is_high_rise = any(
        term in folded for term in ("高层", "塔楼", "超高层", "high-rise", "tower")
    )
    is_glass = any(
        term in folded for term in ("玻璃", "幕墙", "curtain wall", "glass")
    )
    is_commercial = any(
        term in folded for term in ("商业", "综合体", "办公", "商场", "commercial", "office")
    )

    tasks: list[dict[str, Any]] = [
        {
            "title": "确定建筑体量与约束",
            "objective": "把层数、功能、场地比例和风格要求转成可建模的体量、轴网与屋顶意图。",
            "phase": "architecture",
            "acceptance": ["体量和层数明确", "候选方案可进入平面设计"],
            "basis": "用户需求与建筑类型知识",
        },
        {
            "title": "组织功能平面与流线",
            "objective": "按体量边界安排功能分区、入口、门窗、疏散路径与竖向交通。",
            "phase": "floor_plan_design",
            "acceptance": ["空间关系可解释", "平面规则检查可通过或给出明确修复"],
            "basis": "总体方案与平面规则",
        },
    ]
    if is_high_rise:
        tasks[1]["objective"] = (
            "按高层体量组织首层入口、标准层功能、疏散楼梯和覆盖全部楼层的电梯竖向交通。"
        )
        tasks[1]["acceptance"].append("竖向交通覆盖全部楼层")
    if is_commercial:
        tasks[0]["objective"] = (
            "把商业功能、公共入口、基座与上部体量关系转成可建模的体量、轴网和屋顶意图。"
        )

    tasks.append(
        {
            "title": "建立幕墙与材质系统" if is_glass else "建立统一材质系统",
            "objective": (
                "定义真实玻璃、金属龙骨、主体结构与室内楼板的材质角色和引用关系。"
                if is_glass
                else "定义立面、结构、门窗、屋顶和楼板的材质角色与资产引用关系。"
            ),
            "phase": "material_plan",
            "acceptance": (
                ["玻璃使用 transmission 与 ior", "幕墙面板和框架角色清晰"]
                if is_glass
                else ["材质角色齐全", "资产引用闭合"]
            ),
            "basis": "总体方案与受控材质协议",
        }
    )
    tasks.extend(
        [
            {
                "title": "装配可校验的三维主体",
                "objective": "从已确认平面确定性装配墙、板、柱梁、门窗、竖向交通和屋顶。",
                "phase": "skeleton",
                "acceptance": ["几何来自已确认平面", "主体 G1-G6 全部通过"],
                "basis": "批准平面与 Plan2Build 装配协议",
            },
            {
                "title": "完成建筑细部表达",
                "objective": "把用户确认的风格编译为受控装饰构件，并保持与主体槽位和边界一致。",
                "phase": "decor_assembly",
                "acceptance": ["装饰构件有合法宿主", "G7 通过"],
                "basis": "风格包与 Decor IR 协议",
            },
            {
                "title": "验证最终建筑产物",
                "objective": "检查结构、引用、碰撞、尺寸、设计约束和渲染前置条件。",
                "phase": "final_validate",
                "acceptance": ["完整校验零错误", "Blueprint 可以安全保存和加载"],
                "basis": "WILD Schema 与全量校验器",
            },
        ]
    )
    return tasks


def normalize_dynamic_tasks(
    raw_tasks: Any,
    *,
    user_message: str,
    intent: str,
) -> tuple[list[dict[str, Any]], bool]:
    """把模型任务编译到受控阶段；返回任务和是否使用了回退。"""

    allowed_phases = DYNAMIC_TASK_PHASES.get(intent, set())
    minimum = 3 if intent == "generate" else 1
    maximum = 8 if intent == "generate" else 4
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_tasks, list):
        for raw in raw_tasks[:maximum]:
            if not isinstance(raw, dict):
                continue
            phase = _text(raw.get("phase"), limit=40)
            title = _text(raw.get("title"), limit=80)
            objective = _text(raw.get("objective"), limit=300)
            if phase not in allowed_phases or not title or not objective:
                continue
            raw_acceptance = raw.get("acceptance")
            if not isinstance(raw_acceptance, list):
                raw_acceptance = []
            acceptance = [
                _text(item, limit=120)
                for item in raw_acceptance[:4]
                if _text(item, limit=120)
            ]
            if not acceptance:
                acceptance = [f"完成{_DYNAMIC_PHASE_LABELS.get(phase, phase)}并通过对应校验"]
            normalized.append(
                {
                    "title": title,
                    "objective": objective,
                    "phase": phase,
                    "acceptance": acceptance,
                    "basis": _text(raw.get("basis"), limit=160) or "用户需求与研究上下文",
                }
            )

    required_phases = {"architecture", "final_validate"} if intent == "generate" else {"patch"}
    phases = {task["phase"] for task in normalized}
    used_fallback = len(normalized) < minimum or not required_phases.issubset(phases)
    if used_fallback:
        normalized = fallback_dynamic_tasks(user_message, intent)
    phase_order = {
        phase: index
        for index, phase in enumerate(
            (
                "architecture",
                "floor_plan_design",
                "material_plan",
                "skeleton",
                "decor_assembly",
                "final_validate",
                "patch",
            )
        )
    }
    normalized.sort(key=lambda task: phase_order.get(str(task.get("phase")), 99))

    task_ids: list[str] = []
    tasks: list[dict[str, Any]] = []
    for index, task in enumerate(normalized[:maximum], start=1):
        task_id = f"task_{index}"
        tasks.append(
            {
                "id": task_id,
                **task,
                "depends_on": [task_ids[-1]] if task_ids else [],
                "status": "pending",
                "result_ref": None,
            }
        )
        task_ids.append(task_id)
    return tasks, used_fallback


def execution_plan_phase_guidance(
    plan: dict[str, Any] | None,
    phase: str,
) -> str:
    """给业务节点提供已批准计划中与当前阶段相关的公开任务说明。"""

    lines: list[str] = []
    for task in (plan or {}).get("dynamic_tasks", []):
        if not isinstance(task, dict) or task.get("phase") != phase:
            continue
        acceptance = "；".join(str(item) for item in task.get("acceptance") or [])
        lines.append(
            f"- {task.get('title')}：{task.get('objective')}"
            + (f"；验收：{acceptance}" if acceptance else "")
        )
    return "\n".join(lines)


def build_execution_plan(
    *,
    request_id: str,
    intent: str,
    user_message: str,
    architecture_plan: dict[str, Any] | None = None,
    research_summary: str = "",
    feedback: str = "",
    previous_plan: dict[str, Any] | None = None,
    planned_tasks: Any = None,
    planner_source: str = "fallback",
    planner_summary: str = "",
) -> dict[str, Any]:
    """把动态建筑任务编译进确定、可校验的安全主流程。"""

    previous_version = int((previous_plan or {}).get("version") or 0)
    version = previous_version + 1
    constraints = ["所有执行步骤只能使用服务端已注册能力"]
    if intent == "generate":
        constraints.extend(
            [
                "用户确认执行计划后才生成总体方案、平面和三维",
                "用户确认平面前不得生成三维",
                "G1-G7 未通过不得保存或加载 Blueprint",
            ]
        )
    else:
        constraints.append("ScenePatch 仍需用户单独确认后才应用到当前场景")
    if feedback:
        constraints.append(f"用户对上一版计划的修改意见：{feedback[:500]}")

    research = _step(
        "planning_research",
        depends_on=[],
        acceptance=["已读取任务目标和当前场景", "已获得与任务相关的知识依据"],
        status="completed",
        detail=research_summary[:300] or "已完成只读研究",
    )
    if intent == "generate":
        architecture = _step(
            "architecture",
            depends_on=[research["id"]],
            acceptance=["体量和层数明确", "立面、屋顶和功能层次可进入平面设计"],
            status="pending",
            detail="批准计划后生成总体方案",
        )
        floor_plan = _step(
            "floor_plan_design",
            depends_on=[architecture["id"]],
            acceptance=["FloorPlanIR 可解析", "几何检查通过", "工程预审结果可解释"],
        )
        floor_review = _step(
            "floor_plan_review",
            depends_on=[floor_plan["id"]],
            acceptance=["用户明确确认当前平面"],
        )
        materials = _step(
            "material_plan",
            depends_on=[floor_review["id"]],
            acceptance=["材质角色引用闭合", "物理玻璃等关键材质满足真实协议"],
        )
        skeleton = _step(
            "skeleton",
            depends_on=[materials["id"]],
            acceptance=["主体由批准平面确定性装配", "G1-G6 全部通过"],
        )
        style = _step(
            "style_review",
            depends_on=[skeleton["id"]],
            acceptance=["用户确认一个可用风格包"],
        )
        decor = _step(
            "decor_assembly",
            depends_on=[style["id"]],
            acceptance=["Decor IR 合法", "G7 通过"],
        )
        merge = _step(
            "merge",
            depends_on=[decor["id"]],
            acceptance=["引用闭合", "合并后不存在阻断错误"],
        )
        final_validate = _step(
            "final_validate",
            depends_on=[merge["id"]],
            acceptance=["完整校验零错误", "产物可以安全保存和加载"],
        )
        massing = (architecture_plan or {}).get("massing")
        if isinstance(massing, dict) and not feedback:
            width = massing.get("width", "?")
            depth = massing.get("depth", "?")
            floors = massing.get("floors", "?")
            floor_plan["detail"] = f"将在 {width}×{depth}m、{floors} 层体量内规划空间"
            skeleton["detail"] = f"将从批准平面装配 {floors} 层主体"
        if any(
            term in user_message.casefold()
            for term in ("玻璃", "curtain wall", "glass")
        ):
            materials["detail"] = "重点校验玻璃的 transmission、ior、thickness 和幕墙引用"
        steps = [
            research,
            architecture,
            floor_plan,
            floor_review,
            materials,
            skeleton,
            style,
            decor,
            merge,
            final_validate,
        ]
        goal = f"根据用户需求生成经过确认与校验的建筑：{user_message[:240]}"
    elif intent == "edit":
        patch = _step(
            "patch",
            depends_on=[research["id"]],
            acceptance=[
                "ScenePatch Schema 合法",
                "不直接修改当前场景",
                "等待用户应用提案",
            ],
        )
        steps = [research, patch]
        goal = f"为当前建筑制定并生成安全修改提案：{user_message[:240]}"
    else:
        raise ValueError(f"执行计划不支持 intent={intent!r}")

    dynamic_tasks, used_fallback = normalize_dynamic_tasks(
        planned_tasks,
        user_message=user_message,
        intent=intent,
    )
    actual_source = "fallback" if used_fallback else planner_source
    previous_titles = [
        str(task.get("title") or "")
        for task in (previous_plan or {}).get("dynamic_tasks", [])
        if isinstance(task, dict)
    ]
    current_titles = [str(task.get("title") or "") for task in dynamic_tasks]
    change_summary: list[str] = []
    if previous_plan:
        added = [title for title in current_titles if title not in previous_titles]
        removed = [title for title in previous_titles if title not in current_titles]
        if added:
            change_summary.append("新增任务：" + "、".join(added[:4]))
        if removed:
            change_summary.append("移除任务：" + "、".join(removed[:4]))
        if feedback:
            change_summary.append("已按本轮意见重新规划：" + _text(feedback, limit=180))
        if not change_summary:
            change_summary.append("任务结构未改变，已重新核对目标与验收条件")

    return {
        "plan_id": f"plan_{request_id}",
        "version": version,
        "intent": intent,
        "goal": goal,
        "status": "draft",
        "valid": False,
        "review_status": "pending",
        "constraints": constraints,
        "assumptions": [
            "计划描述的是公开执行步骤，不包含模型隐藏思维链",
            "相同的批准方案继续交给现有确定性 Plan2Build 执行器",
        ],
        "planner_source": actual_source,
        "planner_summary": (
            "模型不可用或计划不满足安全协议，已按任务语义生成确定性计划"
            if used_fallback
            else _text(planner_summary, limit=400) or "已生成任务专属建筑计划"
        ),
        "feedback": _text(feedback, limit=500),
        "change_summary": change_summary,
        "dynamic_tasks": dynamic_tasks,
        "capabilities": public_capabilities(intent),
        "steps": steps,
        "validation_issues": [],
    }


def validate_execution_plan(plan: dict[str, Any], intent: str) -> list[dict[str, str]]:
    """校验白名单、依赖图、步骤顺序和建筑硬门禁。"""

    issues: list[dict[str, str]] = []
    if not isinstance(plan, dict):
        return [{"code": "plan_not_object", "message": "执行计划必须是对象"}]
    if str(plan.get("intent")) != intent:
        issues.append(
            {"code": "plan_intent_mismatch", "message": "计划意图与分类结果不一致"}
        )
    if str(plan.get("status") or "draft") not in PLAN_STATUSES:
        issues.append({"code": "invalid_plan_status", "message": "计划状态不受支持"})
    if str(plan.get("planner_source") or "") not in {"llm", "fallback"}:
        issues.append(
            {"code": "invalid_planner_source", "message": "动态计划来源无效"}
        )

    dynamic_tasks = plan.get("dynamic_tasks")
    minimum = 3 if intent == "generate" else 1
    maximum = 8 if intent == "generate" else 4
    if not isinstance(dynamic_tasks, list) or not (
        minimum <= len(dynamic_tasks) <= maximum
    ):
        issues.append(
            {
                "code": "invalid_dynamic_task_count",
                "message": f"本次任务数量必须为 {minimum}～{maximum} 项",
            }
        )
    else:
        dynamic_ids: set[str] = set()
        allowed_phases = DYNAMIC_TASK_PHASES.get(intent, set())
        phases: set[str] = set()
        for index, task in enumerate(dynamic_tasks):
            if not isinstance(task, dict):
                issues.append(
                    {
                        "code": "invalid_dynamic_task",
                        "message": f"本次任务第 {index + 1} 项不是对象",
                    }
                )
                continue
            task_id = str(task.get("id") or "")
            phase = str(task.get("phase") or "")
            if not task_id or task_id in dynamic_ids:
                issues.append(
                    {
                        "code": "duplicate_dynamic_task_id",
                        "message": f"本次任务 ID 缺失或重复：{task_id}",
                    }
                )
            dynamic_ids.add(task_id)
            if phase not in allowed_phases:
                issues.append(
                    {
                        "code": "unsupported_dynamic_task_phase",
                        "message": f"本次任务不能映射到阶段：{phase}",
                    }
                )
            phases.add(phase)
            if not str(task.get("title") or "").strip() or not str(
                task.get("objective") or ""
            ).strip():
                issues.append(
                    {
                        "code": "incomplete_dynamic_task",
                        "message": f"本次任务 {task_id} 缺少标题或目标",
                    }
                )
            if str(task.get("status") or "") not in PLAN_STEP_STATUSES:
                issues.append(
                    {
                        "code": "invalid_dynamic_task_status",
                        "message": f"本次任务 {task_id} 状态无效",
                    }
                )
            for dependency in task.get("depends_on") or []:
                if str(dependency) not in dynamic_ids:
                    issues.append(
                        {
                            "code": "invalid_dynamic_task_dependency",
                            "message": f"本次任务 {task_id} 依赖尚未定义：{dependency}",
                        }
                    )
        required_phases = (
            {"architecture", "final_validate"} if intent == "generate" else {"patch"}
        )
        if not required_phases.issubset(phases):
            issues.append(
                {
                    "code": "missing_dynamic_task_phase",
                    "message": (
                        "本次任务缺少总体方案或最终验证阶段"
                        if intent == "generate"
                        else "本次任务缺少场景修改阶段"
                    ),
                }
            )

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return issues + [{"code": "missing_plan_steps", "message": "执行计划没有步骤"}]

    ids: set[str] = set()
    step_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            issues.append(
                {"code": "invalid_plan_step", "message": f"第 {index + 1} 步不是对象"}
            )
            continue
        step_id = str(raw.get("id") or "")
        step_type = str(raw.get("type") or "")
        capability = CAPABILITY_REGISTRY.get(step_type)
        if not step_id or step_id in ids:
            issues.append(
                {
                    "code": "duplicate_plan_step_id",
                    "message": f"步骤 ID 缺失或重复：{step_id}",
                }
            )
        else:
            ids.add(step_id)
            step_by_id[step_id] = raw
        if capability is None or intent not in capability.allowed_intents:
            issues.append(
                {
                    "code": "unsupported_plan_capability",
                    "message": f"步骤能力不受支持：{step_type}",
                }
            )
        elif str(raw.get("node") or "") != capability.node:
            issues.append(
                {
                    "code": "plan_node_tampered",
                    "message": f"步骤 {step_id} 的执行节点不是注册值",
                }
            )
        if str(raw.get("status") or "") not in PLAN_STEP_STATUSES:
            issues.append(
                {
                    "code": "invalid_plan_step_status",
                    "message": f"步骤 {step_id} 状态无效",
                }
            )

    for step_id, step in step_by_id.items():
        dependencies = step.get("depends_on") or []
        if not isinstance(dependencies, list):
            issues.append(
                {
                    "code": "invalid_plan_dependencies",
                    "message": f"步骤 {step_id} 依赖必须是数组",
                }
            )
            continue
        for dependency in dependencies:
            if dependency not in ids:
                issues.append(
                    {
                        "code": "missing_plan_dependency",
                        "message": f"步骤 {step_id} 依赖不存在：{dependency}",
                    }
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            issues.append(
                {
                    "code": "cyclic_plan_dependency",
                    "message": f"计划依赖存在循环：{step_id}",
                }
            )
            return
        if step_id in visited or step_id not in step_by_id:
            return
        visiting.add(step_id)
        for dependency in step_by_id[step_id].get("depends_on") or []:
            visit(str(dependency))
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in step_by_id:
        visit(step_id)

    required = (
        {
            "planning_research",
            "architecture",
            "floor_plan_design",
            "floor_plan_review",
            "material_plan",
            "skeleton",
            "style_review",
            "decor_assembly",
            "merge",
            "final_validate",
        }
        if intent == "generate"
        else {"planning_research", "patch"}
    )
    present = {str(step.get("type") or "") for step in step_by_id.values()}
    for missing in sorted(required - present):
        issues.append(
            {
                "code": "missing_required_plan_step",
                "message": f"计划缺少必要步骤：{missing}",
            }
        )
    return issues


def update_plan_step(
    plan: dict[str, Any] | None,
    step_type: str,
    status: str,
    *,
    detail: str = "",
    result_ref: str | None = None,
) -> dict[str, Any]:
    """不可变更新指定步骤，避免 LangGraph checkpoint 中的新旧对象互相污染。"""

    updated = deepcopy(plan or {})
    for step in updated.get("steps", []):
        if isinstance(step, dict) and step.get("type") == step_type:
            step["status"] = status
            if detail:
                step["detail"] = detail[:500]
            if result_ref is not None:
                step["result_ref"] = result_ref
            break
    for task in updated.get("dynamic_tasks", []):
        if isinstance(task, dict) and task.get("phase") == step_type:
            task["status"] = status
            if result_ref is not None:
                task["result_ref"] = result_ref
    return updated


def reset_plan_from(plan: dict[str, Any] | None, step_type: str) -> dict[str, Any]:
    """把某一步及依赖它的所有下游步骤恢复为 pending。"""

    updated = deepcopy(plan or {})
    steps = [step for step in updated.get("steps", []) if isinstance(step, dict)]
    target_ids = {
        str(step.get("id")) for step in steps if step.get("type") == step_type
    }
    changed = True
    while changed:
        changed = False
        for step in steps:
            if str(step.get("id")) in target_ids:
                continue
            if any(str(dep) in target_ids for dep in (step.get("depends_on") or [])):
                target_ids.add(str(step.get("id")))
                changed = True
    for step in steps:
        if str(step.get("id")) in target_ids:
            step["status"] = "pending"
            step["result_ref"] = None
            step["detail"] = "等待重新执行"
    reset_phases = {
        str(step.get("type"))
        for step in steps
        if str(step.get("id")) in target_ids
    }
    for task in updated.get("dynamic_tasks", []):
        if isinstance(task, dict) and task.get("phase") in reset_phases:
            task["status"] = "pending"
            task["result_ref"] = None
    updated["status"] = "executing"
    return updated


def next_ready_step(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """返回依赖均完成的第一条 pending 步骤，顺序稳定且可复现。"""

    steps = [step for step in (plan or {}).get("steps", []) if isinstance(step, dict)]
    completed = {
        str(step.get("id"))
        for step in steps
        if step.get("status") in {"completed", "skipped"}
    }
    for step in steps:
        if step.get("status") != "pending":
            continue
        if all(str(dep) in completed for dep in (step.get("depends_on") or [])):
            return deepcopy(step)
    return None


def plan_is_complete(plan: dict[str, Any] | None) -> bool:
    steps = [step for step in (plan or {}).get("steps", []) if isinstance(step, dict)]
    return bool(steps) and all(
        step.get("status") in {"completed", "skipped"} for step in steps
    )
