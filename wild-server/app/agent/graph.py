"""
LangGraph 图定义 —— 意图分类 → 骨架驱动 + Send 动态并行派发 + gen→val 链 + final_validate

流程:
  classifier (意图分类)
    → GENERATE: architecture (方案候选+评分) → material_plan (材质意图+资产解析)
                  → skeleton (受方案与材质约束) → 建议组件列表
                  → Send 动态派发 gen→val 链（并行）
                  → merge → final_validate → done
    → EDIT:     patch (统一 ScenePatch 生成与校验) → done
    → CHAT:     chat (RAG知识问答) → done

每个组件 gen 节点调用 LLM（有思考内容），val 节点调用工具校验。
未被 skeleton 建议的组件完全不运行。
"""
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.component_registry import (
    get_implemented_components,
    resolve_component_suggestions,
)
from app.agent.nodes import (
    classifier_node,
    chat_node,
    patch_node,
    architecture_planner,
    material_planner,
    skeleton_generator,
    merge_fragments_node,
)
from app.agent.nodes.callback_node import callback_node
from app.agent.nodes.base_component_node import (
    create_component_generator,
    create_component_validator,
)

def _dispatch_components(state: GenerationState):
    """骨架完成后，动态派发到 gen 节点（每个组件 gen→val 链的入口）"""
    if state.get("error") or state.get("status") == "failed":
        logger.warning("[Graph] 骨架生成失败，短路终止")
        return "fail"

    # 极简结构（一面墙/一堵墙/单个构件）只保留结构骨架，不派发门/窗/屋顶等组件。
    architecture_plan = state.get("architecture_plan")
    if isinstance(architecture_plan, dict):
        complexity = architecture_plan.get("complexity")
        if isinstance(complexity, dict) and complexity.get("level") == "minimal":
            logger.info("[Graph] 极简结构，跳过组件派发")
            return "merge"

    design_brief = state.get("design_brief")
    component_quota = (
        design_brief.get("component_quota", {})
        if isinstance(design_brief, dict)
        else {}
    )
    suggested = resolve_component_suggestions(
        state.get("suggested_components", []),
        state.get("user_message", ""),
        component_quota,
    )

    if not suggested:
        logger.warning("[Graph] 无可用组件，直接跳到合并")
        return "merge"

    sends = []
    for comp_type in suggested:
        gen_name = f"{comp_type}_gen"
        sends.append(Send(gen_name, state))

    logger.info(f"[Graph] 骨架建议: {suggested}，派发 {len(sends)} 个 gen→val 链")
    return sends


def _classifier_dispatch(state: GenerationState):
    """意图分类后路由：generate → skeleton, edit → patch, chat → chat。"""
    intent = state.get("intent", "generate")
    logger.info(f"[Graph] 分类完成, intent={intent}")
    if intent == "chat":
        return "chat"
    if intent == "edit":
        return "patch"
    return "architecture"


def _final_validate_dispatch(state: GenerationState):
    """最终校验后决定是否进入 callback 重试路径

    per-component 重试策略：
    - 检查 failed_components 中是否还有未达重试上限的组件
    - 如果所有失败组件都已耗尽各自的 retry，不再进入 callback
    - retry_count 只记录修复轮次，不作为提前截断新失败目标的门禁
    """
    status = state.get("status")
    max_retries = state.get("max_retries", 3)
    component_retry_counts = state.get("component_retry_counts", {})

    if status != "partial":
        logger.info(f"[Graph] 校验完成 (status={status})")
        return END

    # per-component 检查：是否还有可重试的失败组件
    failed_components = state.get("failed_components", [])
    retryable = [
        fc for fc in failed_components
        if component_retry_counts.get(fc.get("component_id", ""), 0) < max_retries
    ]

    if not retryable and failed_components:
        logger.info(
            f"[Graph] 所有 {len(failed_components)} 个失败组件已达 per-component 重试上限, 终止"
        )
        return END

    if retryable:
        logger.info(
            f"[Graph] 校验未通过, {len(retryable)}/{len(failed_components)} 个组件可重试 "
            f"(每目标最多 {max_retries} 次)"
        )
    else:
        logger.info(f"[Graph] 无失败组件, 无需重试")

    return "callback" if retryable else END


def build_generation_graph(enable_callback: bool = False, *, checkpointer=None):
    """构建 LangGraph 生成流程图

    classifier → (generate → architecture → material_plan → skeleton → ...) | (edit → patch → END) | (chat → END)
    architecture → material_plan → skeleton → Send 派发 gen→val 链（并行） → merge → final_validate
    """
    graph = StateGraph(GenerationState)

    # ── Layer -1: 意图分类 ──
    graph.add_node("classifier", classifier_node)
    graph.add_node("chat", chat_node)
    graph.add_node("patch", patch_node)

    # ── Layer -0.5: 建筑方案 ──
    graph.add_node("architecture", architecture_planner)
    graph.add_node("material_plan", material_planner)

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

    if enable_callback:
        # ── Layer 4: 校验失败回调重试 ──
        graph.add_node("callback", callback_node)
        # callback 已对候选蓝图执行全量复检；直接进入最终校验，避免 merge
        # 再次按旧槽位覆盖已经通过复检的定向修复。
        graph.add_edge("callback", "final_validate")

    # ── 路由 ──
    graph.set_entry_point("classifier")

    graph.add_conditional_edges(
        "classifier",
        _classifier_dispatch,
        {"architecture": "architecture", "patch": "patch", "chat": "chat"},
    )

    graph.add_edge("chat", END)
    graph.add_edge("patch", END)
    graph.add_edge("architecture", "material_plan")
    graph.add_edge("material_plan", "skeleton")

    graph.add_conditional_edges(
        "skeleton",
        _dispatch_components,
        {"fail": END, "merge": "merge"},
    )

    # val 节点 → merge（fan-in）
    for cfg in implemented:
        val_name = f"{cfg.component_type}_val"
        graph.add_edge(val_name, "merge")

    # merge → final_validate → callback / END
    graph.add_edge("merge", "final_validate")
    if enable_callback:
        graph.add_conditional_edges(
            "final_validate",
            _final_validate_dispatch,
            {"callback": "callback", END: END},
        )
    else:
        graph.add_conditional_edges(
            "final_validate",
            lambda state: END,
            {END: END},
        )
    compiled = graph.compile(checkpointer=checkpointer)
    component_list = ", ".join(
        f"{c.label}({c.component_type}_gen→{c.component_type}_val)" for c in implemented
    )
    callback_status = "启用" if enable_callback else "关闭"
    logger.info(
        f"LangGraph 图编译完成: 分类 → "
        f"(生成: 方案 → 材质 → 骨架 → Send 动态派发 [{component_list}] → merge → final_validate) | "
        f"(编辑: patch → END) | "
        f"(问答: chat → END) "
        f"(回调: {callback_status})"
    )

    return compiled


# ── 全局单例 ──

_graphs: dict[tuple[bool, int | None], object] = {}


def get_graph(enable_callback: bool = False, *, checkpointer=None):
    """获取编译后的图单例，支持 callback 开关"""
    cache_key = (enable_callback, id(checkpointer) if checkpointer is not None else None)
    if cache_key not in _graphs:
        _graphs[cache_key] = build_generation_graph(
            enable_callback=enable_callback,
            checkpointer=checkpointer,
        )
    return _graphs[cache_key]
