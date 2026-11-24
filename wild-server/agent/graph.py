"""生成请求共用设计、材质、计划、执行、装配和校验。"""

from typing import get_args

from langgraph.graph import END, StateGraph
from loguru import logger

from agent.workflows.design import architecture_planner
from agent.workflows.knowledge import chat_node
from agent.workflows.intent import classifier_node
from agent.workflows.assembly import compile_node
from agent.workflows.planning import execute_node
from agent.workflows.editing import patch_node
from agent.workflows.planning import plan_node
from agent.workflows.planning import replanner_node
from agent.workflows.validation import validate_node
from agent.utils.planning.contracts import PlanDocument
from agent.workflows.planning.replan import MAX_NO_PROGRESS_ROUNDS
from agent.utils.planning.store import poll_runnable
from agent.utils.planning.store import refresh_statuses
from agent.state import GenerationInput
from agent.state import GenerationState
from agent.utils.design.types import DetailLevel


def plan_recursion_limit(plan_item_count: int, max_retries: int = 3) -> int:
    """按任务/标记数估算图步骤：最多五次 execute/replanner 和对应装配检查。"""
    items = max(0, int(plan_item_count))
    retries = max(0, int(max_retries))
    return max(48, 16 + items * 15 + retries * 4)


def _terminal(state: dict) -> bool:
    return bool(state.get("terminal_model_error")) or state.get("status") == "failed"


def _plan_of(state: dict) -> PlanDocument | None:
    plan = state.get("plan")
    if not isinstance(plan, dict) or not plan:
        return None
    try:
        parsed = PlanDocument.model_validate(plan)
    except Exception as exc:  # 计划本身不合法：让最终校验去拦，不在路由里炸
        logger.warning(f"[graph] plan 反序列化失败: {exc}")
        return None
    # 路由前先推一次状态：依赖已落定的 pending 条目视同 ready。refresh_statuses 是纯函数，
    # 放在这里意味着"谁忘了刷新"都不会让条目被永久丢弃在 pending。
    return refresh_statuses(parsed)


# ── 路由 ──


async def _classify_request(state: GenerationState) -> dict:
    """分类入口为网页和 Studio 统一处理图纸档位。"""
    result = await classifier_node(state)
    if state.get("detail_level") not in get_args(DetailLevel):
        result["detail_level"] = "minimal"
    return result


def _classifier_dispatch(state: GenerationState):
    """
    意图分类：generate → 建筑方案或物件方案，edit → patch，chat → chat。
    """

    if _terminal(state):
        return "__end__"
    intent = state.get("intent")
    if intent == "chat":
        return "chat"
    if intent == "edit":
        return "patch"
    if intent == "generate":
        return "architecture"
    return "chat"


def _after_architecture(state: GenerationState) -> str:
    return "__end__" if _terminal(state) else "plan"


def _after_plan(state: GenerationState) -> str:
    if _terminal(state):
        return "__end__"
    plan = _plan_of(state)
    if plan is None:
        logger.warning("[graph] plan 缺失，跳过执行循环")
        return "compile"
    if poll_runnable(plan) is None:
        return "compile"
    return "execute"


def _after_execute(state: GenerationState) -> str:
    # 故障停止模型工作，仍装配并交付已有分片。
    return "compile" if _terminal(state) else "replanner"


def _after_replanner(state: GenerationState) -> str:
    if _terminal(state):
        return "compile"
    plan = _plan_of(state)
    if plan is None:
        return "compile"
    budget = plan.budget or {}
    # give_up 只停止模型工作；replanner 已把其余模型条目收束，确定性 merge 仍需跑完。
    if plan.give_up:
        next_item = poll_runnable(plan)
        if next_item is not None and next_item.op == "merge":
            logger.info(f"[graph] 有界退出后继续确定性收尾：{next_item.id}")
            return "execute"
        logger.warning("[graph] replanner 判定 give_up，确定性收尾已结束")
        return "compile"
    # 五重有界终止条件（§5.4）：replanner 会先把计划转换为 give_up 收尾态；这里的
    # 分支只兼容旧 checkpoint，避免旧状态绕过最终校验。
    if plan.iterations >= int(budget.get("iterations", 5)):
        logger.info(f"[graph] 达到迭代上限 {plan.iterations}，收尾交付")
        return "compile"
    if plan.no_progress_rounds >= MAX_NO_PROGRESS_ROUNDS and not any(
        i.params.get("design_markers") for i in plan.items
    ):
        logger.info(f"[graph] 连续 {plan.no_progress_rounds} 轮无进展，收尾交付")
        return "compile"
    if plan.llm_budget_exhausted():
        logger.info(f"[graph] 模型调用预算用尽（{plan.llm_calls}），收尾交付")
        return "compile"
    if poll_runnable(plan) is None:
        return "compile"
    return "execute"


def build_generation_graph(*, checkpointer=None):
    """构建生成链。"""

    graph = StateGraph(GenerationState, input_schema=GenerationInput)
    graph.add_node("classifier", _classify_request)
    graph.add_node("chat", chat_node)
    graph.add_node("patch", patch_node)
    graph.add_node("architecture", architecture_planner)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("replanner", replanner_node)
    graph.add_node("compile", compile_node)
    graph.add_node("final_validate", validate_node)

    # 图的入口节点，标志 classifier 是图的起点
    graph.set_entry_point("classifier")

    # 第一条路由节点
    graph.add_conditional_edges(
        "classifier",
        _classifier_dispatch,
        {
            "architecture": "architecture",
            "patch": "patch",
            "chat": "chat",
            "__end__": END,
        },
    )

    graph.add_edge("chat", END)
    graph.add_edge("patch", END)

    graph.add_conditional_edges(
        "architecture",
        _after_architecture,
        {"plan": "plan", "__end__": END},
    )
    graph.add_edge("compile", "final_validate")
    graph.add_edge("final_validate", END)

    graph.add_conditional_edges(
        "plan",
        _after_plan,
        {
            "execute": "execute",
            "compile": "compile",
            "__end__": END,
        },
    )
    graph.add_conditional_edges(
        "execute",
        _after_execute,
        {
            "replanner": "replanner",
            "compile": "compile",
        },
    )
    graph.add_conditional_edges(
        "replanner",
        _after_replanner,
        {
            "execute": "execute",
            "compile": "compile",
            "__end__": END,
        },
    )

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        "LangGraph 图编译完成: classifier → architecture → plan → "
        "(execute ⇄ replanner) → compile → final_validate"
    )
    return compiled


# ── 全局单例 ──

_graphs: dict[int | None, object] = {}


def get_graph(*, checkpointer=None):
    """获取指定检查点配置的生成图。"""
    cache_key = id(checkpointer) if checkpointer is not None else None
    if cache_key not in _graphs:
        _graphs[cache_key] = build_generation_graph(checkpointer=checkpointer)
    return _graphs[cache_key]


__all__ = [
    "build_generation_graph",
    "get_graph",
    "plan_recursion_limit",
    "MAX_NO_PROGRESS_ROUNDS",
]
