"""ExecutionPlan 在节点之间传递时使用的共享数据契约。"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


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
DynamicTaskStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PlannerSource = Literal["llm", "fallback"]
RequirementSupportStatus = Literal["supported", "needs_review", "unsupported"]
RequirementSeverity = Literal["error", "warning"]
AcceptanceStatus = Literal[
    "pending",
    "passed",
    "failed",
    "not_checked",
    "not_applicable",
    "unsupported",
]
ExecutionProgressStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]


class PlanValidationIssue(TypedDict):
    """执行计划校验器返回的一条问题。"""

    code: str  # 稳定的问题代码，供测试和调用方判断。
    message: str  # 给开发者或用户查看的问题说明。
    # error 会让本轮终止；warning 只展示并交给 plan_review 人工裁决。
    # 省略时按 error 处理，保持既有调用方的语义。
    severity: NotRequired[RequirementSeverity]


class ExecutionDynamicTask(TypedDict):
    """模型任务经过白名单归一化后的任务描述。"""

    id: str  # 当前计划内唯一任务 ID。
    title: str  # 展示给用户的任务标题。
    objective: str  # 当前任务需要完成的目标。
    phase: str  # 映射后的受控业务阶段，例如 architecture。
    acceptance: list[str]  # 当前任务的验收条件。
    basis: str  # 任务所依据的用户需求或研究信息。
    depends_on: list[str]  # 必须先完成的动态任务 ID。
    status: DynamicTaskStatus  # 当前动态任务执行状态；由验收结果计算，不由节点完成推定。
    result_ref: str | None  # 完成后对应的 GenerationState 字段名称。


class StructuredRequirement(TypedDict):
    """由已批准动态任务编译出的、程序可消费和校验的业务要求。"""

    id: str  # 稳定要求 ID，例如 req_task_1_1。
    source_task_id: str  # 来源动态任务 ID。
    source_acceptance_id: str  # 来源验收条件 ID，例如 acc_task_1_1。
    description: str  # 原始公开验收描述。
    phase: str  # 主要落实阶段。
    kind: str  # 受控要求类型，例如 component_min_count。
    target: str  # 受控业务目标，不是 Python 属性表达式。
    operator: str  # eq、gte、contains_any、exists 等受控操作符。
    expected: Any  # 期望值，必须可序列化。
    consumers: list[str]  # 需要消费该要求的已注册业务阶段。
    validator: str  # 后端注册的确定性检查器名称。
    severity: RequirementSeverity  # error 阻断交付，warning 仅记录。
    support_status: RequirementSupportStatus  # 当前系统是否能够执行和检查。


class AcceptanceResult(TypedDict):
    """一条结构化业务要求的验收结果与可追踪证据。"""

    acceptance_id: str  # 对应来源验收条件 ID。
    task_id: str  # 对应动态任务 ID。
    requirement_id: str  # 对应结构化要求 ID。
    status: AcceptanceStatus  # pending、passed、failed 等有限状态。
    expected: Any  # 校验期望值。
    observed: Any  # 实际观察值；尚未检查时为 None。
    validator: str  # 实际使用的检查器名称。
    evidence_refs: list[str]  # State 字段、实体 ID 或校验结果引用。
    message: str  # 给用户和 Trace 阅读的简短说明。


class ExecutionProgressItem(TypedDict):
    """一个固定 LangGraph 阶段的运行进度；不参与节点路由。"""

    status: ExecutionProgressStatus  # 节点尚未运行、完成或失败。
    result_ref: str | None  # 该阶段权威输出所在的 State 字段。
    detail: str  # 当前结果摘要或错误。


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


class ExecutionPlanHistoryEntry(TypedDict):
    """重新规划时保留的上一版本摘要。"""

    version: int | None  # 上一版本号。
    status: ExecutionPlanStatus | None  # 上一版本结束时的状态。
    feedback: str  # 触发下一版本的用户修改意见。
