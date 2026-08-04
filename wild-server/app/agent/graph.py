"""
LangGraph 图定义 —— 注册表驱动 + 骨架短路 + 回调重试

全部 10 种组件: skeleton → 10个并行组件 → merge → validate → [done | callback → retry]
"""
from langgraph.graph import StateGraph, END
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.component_registry import get_implemented_components
from app.agent.nodes import (
    skeleton_generator,
    door_generator,
    window_generator,
    roof_generator,
    railing_generator,
    canopy_generator,
    balcony_generator,
    light_generator,
    ramp_generator,
    bay_window_generator,
    cornice_generator,
    chimney_generator,
    merge_fragments_node,
    validate_node,
)

# ── 组件节点名 → 节点函数 映射 ──
_NODE_FUNCTIONS: dict[str, object] = {
    "door": door_generator,
    "window": window_generator,
    "roof": roof_generator,
    "railing": railing_generator,
    "canopy": canopy_generator,
    "balcony": balcony_generator,
    "light": light_generator,
    "ramp": ramp_generator,
    "bay_window": bay_window_generator,
    "cornice": cornice_generator,
    "chimney": chimney_generator,
}


def build_generation_graph(enable_callback: bool = False):
    """构建 LangGraph 生成流程图

    Args:
        enable_callback: 是否启用回调重试（Phase 3 扩展，默认关闭）
    """
    graph = StateGraph(GenerationState)

    # ── Layer 0: 骨架生成 ──
    graph.add_node("skeleton", skeleton_generator)

    # ── Layer 1: 组件生成（并行，注册表驱动）──
    implemented = get_implemented_components()
    component_node_names = []

    for cfg in implemented:
        node_func = _NODE_FUNCTIONS.get(cfg.component_type)
        if node_func is None:
            logger.warning(f"组件 '{cfg.component_type}' 已注册但无节点函数，跳过")
            continue

        graph.add_node(cfg.component_type, node_func)
        component_node_names.append(cfg.component_type)

    # ── Layer 2: 合并（校验由 ws_agent 直接调用以获取实时进度）──
    graph.add_node("merge", merge_fragments_node)

    # ── 骨架短路路由 ──
    graph.set_entry_point("skeleton")
    graph.add_conditional_edges(
        "skeleton",
        _should_proceed_to_components,
        {
            "ok": component_node_names[0] if component_node_names else "merge",
            "fail": END,
        },
    )

    # ── Layer 0 → Layer 1: fan-out ──
    for node_name in component_node_names:
        graph.add_edge("skeleton", node_name)

    # ── Layer 1 → Layer 2: fan-in ──
    for node_name in component_node_names:
        graph.add_edge(node_name, "merge")

    # ── Layer 2 流程：合并后结束（校验由 ws_agent 直接驱动，展示实时进度）──
    graph.set_finish_point("merge")

    compiled = graph.compile()
    component_list = ", ".join(f"{c.label}({c.component_type})" for c in implemented)
    callback_status = "启用" if enable_callback else "关闭"
    logger.info(f"LangGraph 图编译完成: 骨架 + [{component_list}] 并行 + 合并 + 校验 (回调: {callback_status})")

    return compiled


def _should_proceed_to_components(state: GenerationState) -> str:
    """骨架生成后：通过 → 进入组件层，失败 → 直接终止"""
    if state.get("error") or state.get("status") == "failed":
        logger.warning(f"[Graph] 骨架生成失败，短路终止: {state.get('error', 'unknown')}")
        return "fail"

    if not state.get("skeleton_blueprint"):
        logger.warning("[Graph] 骨架 Blueprint 为空，短路终止")
        return "fail"

    logger.info("[Graph] 骨架生成完成，进入并行组件层")
    return "ok"


def _evaluate_validation(state: GenerationState) -> str:
    """校验结果路由：通过 → done | 有错 + 次数够 → retry | 超限 → escalate"""
    failed = state.get("failed_components", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if not failed:
        logger.info("[Graph] 校验全部通过 → 完成")
        return "done"

    if retry_count < max_retries:
        logger.info(f"[Graph] 校验发现 {len(failed)} 个失败组件, 重试 {retry_count + 1}/{max_retries}")
        return "retry"

    logger.warning(f"[Graph] 重试次数用尽 ({retry_count}/{max_retries}), {len(failed)} 个组件未修复 → 降级")
    return "escalate"


# ── 全局单例 ──

_graph = None


def get_graph(enable_callback: bool = False):
    """获取编译后的图单例"""
    global _graph
    if _graph is None:
        _graph = build_generation_graph(enable_callback=enable_callback)
    return _graph
