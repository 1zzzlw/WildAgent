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


def build_execution_plan(
    *,
    request_id: str,
    intent: str,
    user_message: str,
    architecture_plan: dict[str, Any] | None = None,
    research_summary: str = "",
    feedback: str = "",
    previous_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建确定、可校验的计划；LLM 不能添加未知步骤或改变安全顺序。"""

    previous_version = int((previous_plan or {}).get("version") or 0)
    version = previous_version + 1
    constraints = ["所有执行步骤只能使用服务端已注册能力"]
    if intent == "generate":
        constraints.extend(
            [
                "用户确认执行计划后才继续平面与三维链路",
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
            status="completed" if isinstance(architecture_plan, dict) else "pending",
            detail=str((architecture_plan or {}).get("concept") or "总体方案待生成")[
                :300
            ],
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
        if isinstance(massing, dict):
            width = massing.get("width", "?")
            depth = massing.get("depth", "?")
            floors = massing.get("floors", "?")
            floor_plan["detail"] = f"将在 {width}×{depth}m、{floors} 层体量内规划空间"
            skeleton["detail"] = f"将从批准平面装配 {floors} 层主体"
        if any(
            term in user_message.casefold()
            for term in ("玻璃", "curtain wall", "glass")
        ):
            materials["detail"] = "重点校验玻璃的 transmission、ior、opacity 和幕墙引用"
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
