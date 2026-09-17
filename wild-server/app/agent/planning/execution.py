"""可审核的 Agent 动态任务协议。

ExecutionPlan 只描述本次「要完成什么」；固定节点顺序由 LangGraph 独占管理。
模型不能通过计划填写 Python 函数名、节点名或检查器名称。
"""

from __future__ import annotations

from typing import Any, get_args

from app.agent.planning.contracts import (
    DynamicTaskStatus,
    ExecutionDynamicTask,
    ExecutionPlan,
    ExecutionPlanStatus,
    PlanValidationIssue,
)


# 状态值以共享类型契约为唯一来源，避免常量和类型声明分别维护。
DYNAMIC_TASK_STATUSES = set(get_args(DynamicTaskStatus))
PLAN_STATUSES = set(get_args(ExecutionPlanStatus))

DYNAMIC_TASK_PHASES = {
    "generate": {
        "architecture",
        "material_plan",
        "skeleton",
        "final_validate",
    },
    "edit": {"patch"},
}

_DYNAMIC_PHASE_LABELS = {
    "architecture": "总体方案",
    "material_plan": "材质方案",
    "skeleton": "主体装配",
    "final_validate": "最终校验",
    "patch": "场景修改",
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
            "objective": "把层数、功能、场地比例和风格要求转成可建模的体量、轴网、屋顶意图与空间关系。",
            "phase": "architecture",
            "acceptance": ["体量和层数明确", "空间关系可进入材质与骨架阶段"],
            "basis": "用户需求与建筑类型知识",
        },
        {
            "title": "建立统一材质系统",
            "objective": "定义立面、结构、门窗、屋顶和楼板的材质角色与资产引用关系。",
            "phase": "material_plan",
            "acceptance": ["材质角色齐全", "资产引用闭合"],
            "basis": "总体方案与受控材质协议",
        },
    ]
    if is_high_rise:
        tasks[0]["objective"] += " 按高层体量组织标准层与竖向交通关系。"
        tasks[0]["acceptance"].append("竖向交通意图明确")
    if is_commercial:
        tasks[0]["objective"] += " 明确商业功能、公共入口、基座与上部体量关系。"

    if is_glass:
        tasks[1]["title"] = "建立幕墙与材质系统"
        tasks[1]["objective"] = "定义真实玻璃、金属龙骨、主体结构与室内楼板的材质角色和引用关系。"
        tasks[1]["acceptance"] = ["玻璃使用 transmission 与 ior", "幕墙面板和框架角色清晰"]

    tasks.extend(
        [
            {
                "title": "生成可校验的三维主体",
                "objective": "依据总体方案与空间关系生成墙、板、柱梁、楼梯等主体骨架，并列出组件建议清单。",
                "phase": "skeleton",
                "acceptance": ["主体 Schema 预检通过", "结构表达完整且组件建议清单明确"],
                "basis": "总体方案与建筑类型知识",
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
) -> tuple[list[ExecutionDynamicTask], bool]:
    """把模型任务编译到受控阶段；返回任务和是否使用了回退。"""

    # 根据意图限制白名单阶段和任务数量，过滤掉不符合要求的模型输出。
    allowed_phases = DYNAMIC_TASK_PHASES.get(intent, set())

    # 任务应该有的最小和最大数量；
    minimum = 3 if intent == "generate" else 1
    maximum = 8 if intent == "generate" else 4

    normalized: list[dict[str, Any]] = []
    # 遍历模型输出的每个任务，过滤掉不符合要求的任务，并将其编译为受控阶段。
    if isinstance(raw_tasks, list):
        for raw in raw_tasks[:maximum]:
            if not isinstance(raw, dict):
                continue
            phase = _text(raw.get("phase"), limit=40)
            title = _text(raw.get("title"), limit=80)
            objective = _text(raw.get("objective"), limit=300)

            # 检查阶段是否在白名单中，并确保标题和目标不为空。
            if phase not in allowed_phases or not title or not objective:
                continue

            # 确保验收条件是一个列表，并将其限制为最多 4 条，每条不超过 120 个字符。
            raw_acceptance = raw.get("acceptance")
            # 如果不是列表，则将其设置为空列表。
            if not isinstance(raw_acceptance, list):
                raw_acceptance = []

            acceptance = [
                _text(item, limit=120)
                for item in raw_acceptance[:4]
                if _text(item, limit=120)
            ]
            if not acceptance:
                acceptance = [f"完成{_DYNAMIC_PHASE_LABELS.get(phase, phase)}并通过对应校验"]

            # 最终，通过层层检查，加入规范列表
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
        # 放弃 LLM 输出，使用确定性生成
        normalized = fallback_dynamic_tasks(user_message, intent)

    # 按阶段顺序排序，确保 architecture 在前，final_validate 在后，其他阶段按定义顺序排列。
    phase_order = {
        phase: index
        for index, phase in enumerate(
            (
                "architecture",
                "material_plan",
                "skeleton",
                "final_validate",
                "patch",
            )
        )
    }
    normalized.sort(key=lambda task: phase_order.get(str(task.get("phase")), 99))

    # 为每个任务分配唯一 ID，并设置依赖关系，确保每个任务依赖于前一个任务。
    task_ids: list[str] = []
    tasks: list[ExecutionDynamicTask] = []
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
    plan: ExecutionPlan | None,
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
    research_summary: str = "",
    feedback: str = "",
    previous_plan: ExecutionPlan | None = None,
    planned_tasks: Any = None,
    planner_source: str = "fallback",
    planner_summary: str = "",
) -> ExecutionPlan:
    """构建只描述本次业务目标的可审核计划，不复制 LangGraph 节点顺序。"""

    previous_version = int((previous_plan or {}).get("version") or 0)
    version = previous_version + 1
    constraints = ["实际节点顺序和可执行能力只能由服务端 LangGraph 定义"]
    if intent == "generate":
        constraints.extend(
            [
                "用户确认执行计划后才生成总体方案与三维",
                "完整校验未通过不得保存或加载 Blueprint",
            ]
        )
    else:
        constraints.append("ScenePatch 仍需用户单独确认后才应用到当前场景")
    if feedback:
        constraints.append(f"用户对上一版计划的修改意见：{feedback[:500]}")

    # 根据用户意图生成可展示的总体目标，避免模型在计划中写入 Python 函数名、节点名或检查器名称。
    if intent == "generate":
        goal = f"根据用户需求生成经过确认与校验的建筑：{user_message[:240]}"
    elif intent == "edit":
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

    # 生成计划时，比较与上一版的任务标题差异，形成简短的变更摘要。
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
            "计划描述公开业务目标，不包含模型隐藏思维链",
            "批准计划不会改变服务端 LangGraph 固定的安全执行边界",
            f"规划前研究已完成：{research_summary[:200] or '已读取本地能力协议'}",
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
    }


def validate_execution_plan(plan: object, intent: str) -> list[PlanValidationIssue]:
    """校验动态任务结构、阶段白名单和依赖，不再校验重复的固定 steps。"""

    issues: list[PlanValidationIssue] = []
    if not isinstance(plan, dict):
        return [{"code": "plan_not_object", "message": "执行计划必须是对象"}]
    contract_fields = ExecutionPlan.__required_keys__ | ExecutionPlan.__optional_keys__
    missing_fields = sorted(ExecutionPlan.__required_keys__ - plan.keys())
    unknown_fields = sorted(plan.keys() - contract_fields)
    if missing_fields:
        issues.append({
            "code": "missing_plan_fields",
            "message": "执行计划缺少字段：" + "、".join(missing_fields),
        })
    if unknown_fields:
        issues.append({
            "code": "unknown_plan_fields",
            "message": "执行计划包含未声明字段：" + "、".join(unknown_fields),
        })
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
            if str(task.get("status") or "") not in DYNAMIC_TASK_STATUSES:
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

    return issues
