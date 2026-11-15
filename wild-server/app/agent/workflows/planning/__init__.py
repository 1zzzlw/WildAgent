"""动态执行计划（plan）数据层。

设计依据：《动态节点设计规划》§二（plan 与 state 的核心数据契约）。

分工：
- ``contracts``：PlanItem / PlanDocument 的唯一类型定义（含计划态与执行态两个状态机）。
- ``store``：plan 的确定性 CRUD 与状态推进（对应 Claude Code 的 ``utils/task/framework.ts``）。
- ``expand``：把方案与骨架产物确定性展开为条目列表（不调用模型）。
- ``reconcile``：把蓝图事实回写为条目结果，是**唯一**的交付状态写入口。
- ``tool_registry``：条目可用的工具集（按 (op, kind) 裁剪，fail-closed 默认）。
"""

from app.agent.workflows.planning.capability import CAPABILITY_GAPS
from app.agent.workflows.planning.capability import CapabilityGap
from app.agent.workflows.planning.capability import capability_gap_items
from app.agent.workflows.planning.capability import capability_notes
from app.agent.workflows.planning.capability import detect_capability_gaps
from app.agent.workflows.planning.capability import requested_presentation_medium
from app.domain.planning.contracts import PLAN_SCHEMA_VERSION
from app.domain.planning.contracts import OPS
from app.domain.planning.contracts import TERMINAL_STATUSES
from app.domain.planning.contracts import ItemRun
from app.domain.planning.contracts import PlanDocument
from app.domain.planning.contracts import PlanItem
from app.agent.workflows.planning.expand import expand_plan
from app.agent.workflows.planning.expand import plan_budget
from app.agent.workflows.planning.reconcile import ensure_artifact_consistency
from app.agent.workflows.planning.reconcile import reconcile
from app.agent.workflows.planning.replan import MAX_NO_PROGRESS_ROUNDS
from app.agent.workflows.planning.replan import MAX_REPLACE_PER_ITEM
from app.agent.workflows.planning.replan import MAX_REVISION
from app.agent.workflows.planning.replan import REPLAN_ACTIONS
from app.agent.workflows.planning.replan import ReplanDecision
from app.agent.workflows.planning.replan import apply_decision
from app.agent.workflows.planning.replan import deterministic_decision
from app.agent.workflows.planning.replan import enforce_decision_policy
from app.agent.workflows.planning.replan import parse_replan
from app.agent.workflows.planning.replan import plan_needs_replan
from app.agent.workflows.planning.replan import prepare_finalization
from app.agent.workflows.planning.replan import replan_summary
from app.agent.workflows.planning.replan import request_replan
from app.domain.planning.store import append_items
from app.domain.planning.store import find_item
from app.domain.planning.store import new_plan
from app.domain.planning.store import poll_runnable
from app.domain.planning.store import record_result
from app.domain.planning.store import refresh_statuses
from app.domain.planning.store import set_status
from app.domain.planning.store import terminal_stats
from app.agent.workflows.planning.tool_registry import TOOL_CATEGORIES
from app.agent.workflows.planning.tool_registry import TOOL_TYPED_OPS
from app.agent.workflows.planning.tool_registry import ToolSpec
from app.agent.workflows.planning.tool_registry import get_tool_registry
from app.agent.workflows.planning.tool_registry import tool_names_for
from app.agent.workflows.planning.tool_registry import tool_spec
from app.agent.workflows.planning.tool_registry import tools_for

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
