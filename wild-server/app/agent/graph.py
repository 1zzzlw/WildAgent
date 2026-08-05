"""
LangGraph 图定义 —— 骨架驱动 + Send 动态并行派发 + gen→val 链 + final_validate

流程:
  skeleton (RAG+丰富描述) → 建议组件列表
    → Send 动态派发 gen→val 链（并行）
    → merge → final_validate → done

每个组件 gen 节点调用 LLM（有思考内容），val 节点调用工具校验。
未被 skeleton 建议的组件完全不运行。
"""
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.component_registry import get_implemented_components, COMPONENT_REGISTRY
from app.agent.nodes import (
    skeleton_generator,
    merge_fragments_node,
)
from app.agent.nodes.base_component_node import (
    create_component_generator,
    create_component_validator,
)

# ── 关键词 fallback ──
_COMPONENT_KEYWORDS: dict[str, list[str]] = {
    "door": ["门", "入口", "大门"],
    "window": ["窗", "窗户", "玻璃"],
    "roof": ["屋顶", "房顶", "顶"],
    "railing": ["栏杆", "护栏", "扶手", "阳台", "楼梯", "露台"],
    "canopy": ["雨棚", "雨篷", "遮阳", "入口遮", "门廊"],
    "balcony": ["阳台", "露台", "挑台", "凉台"],
    "light": ["灯", "照明", "光源", "吊灯", "壁灯", "室内", "温馨"],
    "ramp": ["坡道", "斜坡", "无障碍", "车道"],
    "bay_window": ["凸窗", "飘窗", "bay window"],
    "cornice": ["檐口", "飞檐", "挑檐", "中式", "传统", "古建", "斗拱"],
    "chimney": ["烟囱", "壁炉", "排烟", "欧式"],
}


def _keyword_fallback(user_message: str) -> list[str]:
    """骨架未输出 _components: 时，用关键词匹配作为兜底"""
    components = ["door", "window", "roof"]
    for comp_type, keywords in _COMPONENT_KEYWORDS.items():
        if comp_type in components:
            continue
        if any(kw in user_message for kw in keywords):
            components.append(comp_type)
    logger.info(f"[Graph] 关键词 fallback: {components}")
    return components


def _dispatch_components(state: GenerationState):
    """骨架完成后，动态派发到 gen 节点（每个组件 gen→val 链的入口）"""
    if state.get("error") or state.get("status") == "failed":
        logger.warning("[Graph] 骨架生成失败，短路终止")
        return "fail"

    suggested = state.get("suggested_components", [])

    if not suggested:
        user_msg = state.get("user_message", "")
        suggested = _keyword_fallback(user_msg)

    if not suggested:
        logger.warning("[Graph] 无可用组件，直接跳到合并")
        return "merge"

    sends = []
    for comp_type in suggested:
        gen_name = f"{comp_type}_gen"
        sends.append(Send(gen_name, state))

    logger.info(f"[Graph] 骨架建议: {suggested}，派发 {len(sends)} 个 gen→val 链")
    return sends


def build_generation_graph(enable_callback: bool = False):
    """构建 LangGraph 生成流程图

    骨架 → Send 派发 gen→val 链（并行） → merge → final_validate
    """
    graph = StateGraph(GenerationState)

    # ── Layer 0: 骨架 ──
    graph.add_node("skeleton", skeleton_generator)

    # ── Layer 1: 每个组件的 gen→val 链 ──
    implemented = get_implemented_components()
    gen_node_names: list[str] = []

    for cfg in implemented:
        ct = cfg.component_type
        gen_name = f"{ct}_gen"
        val_name = f"{ct}_val"

        # 生成器（LLM 调用，有思考内容）
        graph.add_node(gen_name, create_component_generator(cfg))
        # 校验器（工具调用，有诊断输出）
        graph.add_node(val_name, create_component_validator(cfg))
        # gen → val 串行
        graph.add_edge(gen_name, val_name)

        gen_node_names.append(gen_name)

    # ── Layer 2: 合并 ──
    graph.add_node("merge", merge_fragments_node)

    # ── Layer 3: 最终校验 ──
    from app.agent.nodes.validate_node import validate_node
    graph.add_node("final_validate", validate_node)

    # ── 路由 ──
    graph.set_entry_point("skeleton")
    graph.add_conditional_edges(
        "skeleton",
        _dispatch_components,
        {"fail": END, "merge": "merge"},
    )

    # val 节点 → merge（fan-in）
    for cfg in implemented:
        val_name = f"{cfg.component_type}_val"
        graph.add_edge(val_name, "merge")

    # merge → final_validate → END
    graph.add_edge("merge", "final_validate")
    graph.set_finish_point("final_validate")

    compiled = graph.compile()
    component_list = ", ".join(
        f"{c.label}({c.component_type}_gen→{c.component_type}_val)" for c in implemented
    )
    callback_status = "启用" if enable_callback else "关闭"
    logger.info(
        f"LangGraph 图编译完成: 骨架 → Send 动态派发 [{component_list}] → merge → final_validate "
        f"(回调: {callback_status})"
    )

    return compiled


# ── 全局单例 ──

_graph = None


def get_graph(enable_callback: bool = False):
    """获取编译后的图单例"""
    global _graph
    if _graph is None:
        _graph = build_generation_graph(enable_callback=enable_callback)
    return _graph
