"""建筑：图纸 → 材质解析 → 审核 → 标记任务 → 最终编译；物件沿用骨架链。"""
from langgraph.graph import END, StateGraph
from loguru import logger

from app.agent.nodes.architecture_node import architecture_planner
from app.agent.nodes.callback_node import callback_node
from app.agent.nodes.chat_node import chat_node
from app.agent.nodes.classifier_node import classifier_node
from app.agent.nodes.compile_node import compile_node
from app.agent.nodes.design_review_node import design_review, route_design_review
from app.agent.nodes.execute_node import execute_node
from app.agent.nodes.material_plan_node import material_planner
from app.agent.nodes.object_design_node import object_planner
from app.agent.nodes.patch_node import patch_node
from app.agent.nodes.plan_node import plan_node
from app.agent.nodes.replanner_node import replanner_node
from app.agent.nodes.skeleton_node import skeleton_generator
from app.agent.nodes.validate_node import validate_node
from app.agent.plan.contracts import PlanDocument
from app.agent.plan.replan import MAX_NO_PROGRESS_ROUNDS
from app.agent.plan.store import poll_runnable, refresh_statuses
from app.agent.state import GenerationInput, GenerationState

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
        return "object_design" if state.get("intent_target_kind") == "object" else "architecture"
    return "chat"


def _after_architecture(state: GenerationState) -> str:
    return "__end__" if _terminal(state) else "material_plan"


def _after_object_design(state: GenerationState) -> str:
    # 物件方案与建筑方案之后是同一条链：材质 → 人工审核 → 骨架 → 计划 → 执行。
    return "__end__" if _terminal(state) else "material_plan"


def _after_material_plan(state: GenerationState) -> str:
    return "__end__" if _terminal(state) else "design_review"


def _after_skeleton(state: GenerationState) -> str:
    return "__end__" if _terminal(state) or state.get("error") else "plan"


def _after_compile(state: GenerationState) -> str:
    if _terminal(state):
        return "__end__"
    if (state.get("compile_report") or {}).get("retry_implementation"):
        return "execute"
    return "final_validate"


def _execution_end(state: GenerationState) -> str:
    kind = (state.get("design_document") or {}).get("decisions", {}).get("kind")
    return "compile" if kind == "architecture" else "final_validate"


def _after_plan(state: GenerationState) -> str:
    if _terminal(state):
        return "__end__"
    if state.get("design_review_status") == "pending":
        return "design_review"
    if state.get("design_review_status") == "revise":
        return "architecture"
    plan = _plan_of(state)
    if plan is None:
        logger.warning("[graph] plan 缺失，跳过执行循环")
        return _execution_end(state)
    if poll_runnable(plan) is None:
        return _execution_end(state)
    return "execute"


def _after_execute(state: GenerationState) -> str:
    # 模型服务故障立即终止整轮，不进循环（沿用既有分类，不做重试）。
    return "__end__" if _terminal(state) else "replanner"


def _after_replanner(state: GenerationState) -> str:
    if _terminal(state):
        return "__end__"
    plan = _plan_of(state)
    if plan is None:
        return _execution_end(state)
    budget = plan.budget or {}
    # give_up 只停止模型工作；replanner 已把其余模型条目收束，确定性 merge 仍需跑完。
    if plan.give_up:
        next_item = poll_runnable(plan)
        if next_item is not None and next_item.op == "merge":
            logger.info(f"[graph] 有界退出后继续确定性收尾：{next_item.id}")
            return "execute"
        logger.warning("[graph] replanner 判定 give_up，确定性收尾已结束")
        return _execution_end(state)
    # 五重有界终止条件（§5.4）：replanner 会先把计划转换为 give_up 收尾态；这里的
    # 分支只兼容旧 checkpoint，避免旧状态绕过最终校验。
    if plan.iterations >= int(budget.get("iterations", 5)):
        logger.info(f"[graph] 达到迭代上限 {plan.iterations}，收尾交付")
        return _execution_end(state)
    if plan.no_progress_rounds >= MAX_NO_PROGRESS_ROUNDS and not any(i.params.get("design_markers") for i in plan.items):
        logger.info(f"[graph] 连续 {plan.no_progress_rounds} 轮无进展，收尾交付")
        return _execution_end(state)
    if plan.llm_budget_exhausted():
        logger.info(f"[graph] 模型调用预算用尽（{plan.llm_calls}），收尾交付")
        return _execution_end(state)
    if poll_runnable(plan) is None:
        return _execution_end(state)
    return "execute"


def _final_validate_dispatch(state: GenerationState) -> str:
    """兼容既有修复路径：还有未耗尽重试额度的失败目标时进 callback。"""

    if state.get("terminal_model_error"):
        return "__end__"
    if (state.get("design_document") or {}).get("decisions", {}).get("kind") == "architecture":
        return "__end__"
    if (state.get("repair_audit") or {}).get("stop_reason") in {
        "design_revision_required", "repeated_candidate", "incomplete_candidate", "no_change", "no_action",
    }:
        return "__end__"
    if state.get("status") != "partial":
        return "__end__"
    retry_counts = state.get("component_retry_counts", {}) or {}
    max_retries = state.get("max_retries", 3)
    retryable = [
        failed
        for failed in state.get("failed_components", []) or []
        if retry_counts.get(failed.get("component_id", ""), 0) < max_retries
    ]
    return "callback" if retryable else "__end__"


def build_generation_graph(enable_callback: bool = False, *, checkpointer=None):
    """构建生成链。"""

    graph = StateGraph(GenerationState, input_schema=GenerationInput)

    # ── 入口：意图分类 ──
    graph.add_node("classifier", classifier_node)
    graph.add_node("chat", chat_node)
    graph.add_node("patch", patch_node)

    # 建筑与物件分别形成设计，再共享材质解析和审核。
    graph.add_node("architecture", architecture_planner)
    graph.add_node("object_design", object_planner)
    graph.add_node("material_plan", material_planner)
    graph.add_node("design_review", design_review)
    graph.add_node("skeleton", skeleton_generator)
    # 建筑构件任务完成后统一装配；物件继续使用现有合并链。
    graph.add_node("compile", compile_node)

    # ── 动态部分：拓扑固定，业务顺序在 plan 数据里 ──
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("replanner", replanner_node)

    # ── 收尾 ──
    graph.add_node("final_validate", validate_node)
    if enable_callback:
        graph.add_node("callback", callback_node)
        graph.add_edge("callback", "final_validate")

    # 图的入口节点，标志 classifier 是图的起点
    graph.set_entry_point("classifier")

    # 第一条路由节点
    graph.add_conditional_edges(
        "classifier",
        _classifier_dispatch,
        {
            "architecture": "architecture",
            "object_design": "object_design",
            "patch": "patch",
            "chat": "chat",
            "__end__": END,
        },
    )

    graph.add_edge("chat", END)
    graph.add_edge("patch", END)

    graph.add_conditional_edges("architecture", _after_architecture,
                                {"material_plan": "material_plan", "__end__": END})
    graph.add_conditional_edges("object_design", _after_object_design,
                                {"material_plan": "material_plan", "__end__": END})
    graph.add_conditional_edges("material_plan", _after_material_plan,
                                {"design_review": "design_review", "__end__": END})
    graph.add_conditional_edges(
        "design_review",
        route_design_review,
        {
            "architecture": "architecture",
            "object_design": "object_design",
            "skeleton": "skeleton",
            "plan": "plan",
            "__end__": END,
        },
    )
    graph.add_conditional_edges("skeleton", _after_skeleton,
                                {"plan": "plan", "__end__": END})
    # 版本失效回到审核；装配完成后使用同一候选做最终校验。
    graph.add_conditional_edges("compile", _after_compile, {"execute": "execute", "final_validate": "final_validate", "__end__": END})

    graph.add_conditional_edges("plan", _after_plan,
                                {"execute": "execute", "final_validate": "final_validate", "compile": "compile",
                                 "design_review": "design_review", "architecture": "architecture", "__end__": END})
    graph.add_conditional_edges("execute", _after_execute,
                                {"replanner": "replanner", "__end__": END})
    graph.add_conditional_edges("replanner", _after_replanner,
                                {"execute": "execute", "final_validate": "final_validate", "compile": "compile",
                                 "design_review": "design_review", "architecture": "architecture", "__end__": END})

    if enable_callback:
        graph.add_conditional_edges("final_validate", _final_validate_dispatch,
                                    {"callback": "callback", "__end__": END})
    else:
        graph.add_edge("final_validate", END)

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        "LangGraph 图编译完成: classifier → (architecture | object_design) → material_plan → "
        "design_review → (skeleton | plan) → "
        "(execute ⇄ replanner) → 建筑最终compile / 物件合并 → final_validate"
    )
    return compiled


# ── 全局单例 ──

_graphs: dict[tuple[bool, int | None], object] = {}


def get_graph(enable_callback: bool = False, *, checkpointer=None):
    """获取编译后的图单例，支持 callback 开关。"""
    cache_key = (enable_callback, id(checkpointer) if checkpointer is not None else None)
    if cache_key not in _graphs:
        _graphs[cache_key] = build_generation_graph(
            enable_callback=enable_callback,
            checkpointer=checkpointer,
        )
    return _graphs[cache_key]


__all__ = [
    "build_generation_graph",
    "get_graph",
    "plan_recursion_limit",
    "MAX_NO_PROGRESS_ROUNDS",
]
