"""动态执行计划（plan）数据层。

设计依据：《动态节点设计规划》§二（plan 与 state 的核心数据契约）。

分工：
- ``contracts``：PlanItem / PlanDocument 的唯一类型定义（含计划态与执行态两个状态机）。
- ``store``：plan 的确定性 CRUD 与状态推进（对应 Claude Code 的 ``utils/task/framework.ts``）。
- ``expand``：把方案与骨架产物确定性展开为条目列表（不调用模型）。
- ``reconcile``：把蓝图事实回写为条目结果，是**唯一**的交付状态写入口。
- ``tool_registry``：条目可用的工具集（按 (op, kind) 裁剪，fail-closed 默认）。
"""

from app.agent.plan.capability import (
    CAPABILITY_GAPS,
    CapabilityGap,
    capability_gap_items,
    capability_notes,
    detect_capability_gaps,
    requested_presentation_medium,
)
from app.agent.plan.contracts import (
    PLAN_SCHEMA_VERSION,
    OPS,
    TERMINAL_STATUSES,
    ItemRun,
    PlanDocument,
    PlanItem,
)
from app.agent.plan.expand import expand_plan, plan_budget
from app.agent.plan.reconcile import ensure_artifact_consistency, reconcile
from app.agent.plan.replan import (
    MAX_NO_PROGRESS_ROUNDS,
    MAX_REPLACE_PER_ITEM,
    MAX_REVISION,
    REPLAN_ACTIONS,
    ReplanDecision,
    apply_decision,
    deterministic_decision,
    enforce_decision_policy,
    parse_replan,
    plan_needs_replan,
    prepare_finalization,
    replan_summary,
    request_replan,
)
from app.agent.plan.store import (
    append_items,
    find_item,
    new_plan,
    poll_runnable,
    record_result,
    refresh_statuses,
    set_status,
    terminal_stats,
)
from app.agent.plan.tool_registry import (
    TOOL_CATEGORIES,
    TOOL_TYPED_OPS,
    ToolSpec,
    get_tool_registry,
    tool_names_for,
    tool_spec,
    tools_for,
)

__all__ = [
    "CAPABILITY_GAPS",
    "MAX_REVISION",
    "MAX_NO_PROGRESS_ROUNDS",
    "MAX_REPLACE_PER_ITEM",
    "PLAN_SCHEMA_VERSION",
    "OPS",
    "REPLAN_ACTIONS",
    "TERMINAL_STATUSES",
    "TOOL_CATEGORIES",
    "TOOL_TYPED_OPS",
    "CapabilityGap",
    "ItemRun",
    "ReplanDecision",
    "PlanDocument",
    "PlanItem",
    "ToolSpec",
    "append_items",
    "apply_decision",
    "capability_gap_items",
    "capability_notes",
    "detect_capability_gaps",
    "deterministic_decision",
    "enforce_decision_policy",
    "ensure_artifact_consistency",
    "expand_plan",
    "find_item",
    "get_tool_registry",
    "new_plan",
    "parse_replan",
    "plan_budget",
    "plan_needs_replan",
    "prepare_finalization",
    "poll_runnable",
    "reconcile",
    "replan_summary",
    "request_replan",
    "record_result",
    "refresh_statuses",
    "requested_presentation_medium",
    "set_status",
    "terminal_stats",
    "tool_names_for",
    "tool_spec",
    "tools_for",
]
