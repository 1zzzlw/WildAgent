"""ExecutionPlan 在节点之间传递时使用的共享数据契约。"""

from __future__ import annotations

from typing import Literal, TypedDict


PlanIntent = Literal["generate", "edit"]
ExecutionPlanStatus = Literal[
    "draft",
    "reviewing",
    "approved",
    "executing",
    "revising",
    "completed",
    "failed",
]
ExecutionPlanReviewStatus = Literal["pending", "approved", "revise"]
ExecutionPlanReviewState = Literal["pending", "approved", "revise", "rejected"]
PlanStepStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PlannerSource = Literal["llm", "fallback"]
PlanPermission = Literal["read", "mutate"]


class PlanValidationIssue(TypedDict):
    """执行计划校验器返回的一条问题。"""

    code: str  # 稳定的问题代码，供测试和调用方判断。
    message: str  # 给开发者或用户查看的问题说明。


class ExecutionDynamicTask(TypedDict):
    """模型任务经过白名单归一化后的任务描述。"""

    id: str  # 当前计划内唯一任务 ID。
    title: str  # 展示给用户的任务标题。
    objective: str  # 当前任务需要完成的目标。
    phase: str  # 映射后的受控业务阶段，例如 architecture。
    acceptance: list[str]  # 当前任务的验收条件。
    basis: str  # 任务所依据的用户需求或研究信息。
    depends_on: list[str]  # 必须先完成的动态任务 ID。
    status: PlanStepStatus  # 当前动态任务执行状态。
    result_ref: str | None  # 完成后对应的 GenerationState 字段名称。


class ExecutionStep(TypedDict):
    """由服务端白名单构建的可执行步骤。"""

    id: str  # 当前计划内唯一步骤 ID。
    type: str  # 注册能力类型，例如 architecture、merge。
    node: str  # 实际调度的 LangGraph 节点名称。
    title: str  # 展示给用户的步骤名称。
    description: str  # 步骤职责说明。
    depends_on: list[str]  # 必须先完成的步骤 ID。
    acceptance: list[str]  # 步骤完成时需要满足的条件。
    permission: PlanPermission  # read 表示只读，mutate 表示会生成或修改产物。
    requires_user_review: bool  # 当前步骤是否要求额外人工审核。
    status: PlanStepStatus  # 当前步骤执行状态。
    detail: str  # 当前进度或执行结果摘要。
    result_ref: str | None  # 完成后对应的 GenerationState 字段名称。


class ExecutionPlan(TypedDict):
    """经过服务端构建和校验、可由 LangGraph 持久化的执行计划。"""

    plan_id: str  # 由 request_id 生成的计划 ID。
    version: int  # 每次重新规划后递增的版本号。
    intent: PlanIntent  # 当前计划服务的用户意图。
    goal: str  # 结合用户消息生成的总体目标。
    status: ExecutionPlanStatus  # 计划整体执行状态。
    valid: bool  # 是否通过服务端结构与白名单校验。
    review_status: ExecutionPlanReviewStatus  # 用户对当前计划的审核结果。
    constraints: list[str]  # 整个执行计划必须遵守的安全约束。
    assumptions: list[str]  # 对计划含义和执行边界的公开说明。
    planner_source: PlannerSource  # 动态任务来自模型还是确定性回退。
    planner_summary: str  # 模型或回退逻辑给出的计划摘要。
    feedback: str  # 生成当前版本时采用的用户修改意见。
    change_summary: list[str]  # 相对上一版本增加、删除或保留了哪些任务。
    dynamic_tasks: list[ExecutionDynamicTask]  # 本次需求特有、经白名单归一化的任务。
    steps: list[ExecutionStep]  # 服务端固定构建、供执行器调度的安全步骤。


class ExecutionPlanHistoryEntry(TypedDict):
    """重新规划时保留的上一版本摘要。"""

    version: int | None  # 上一版本号。
    status: ExecutionPlanStatus | None  # 上一版本结束时的状态。
    feedback: str  # 触发下一版本的用户修改意见。
