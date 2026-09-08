"""
LangGraph 图定义 —— 可审核计划层 + LLM 骨架生成链

流程:
  classifier (意图分类)
    → PLAN:     planning_research → planner → plan_review → plan_executor
    → GENERATE: architecture (总体方案候选)
                  → material_plan (材质意图+资产解析)
                  → skeleton (LLM 骨架生成：主体蓝图 + 组件建议)
                  → Send 动态派发组件 gen→val 链（并行）
                  → merge → final_validate → done
    → EDIT:     patch (统一 ScenePatch 生成与校验) → done
    → CHAT:     chat (RAG知识问答) → done

平面设计/确定性装配时代（floor_* 与 approved_plan_assembler）已下线：
主链骨架节点即 LLM 骨架实现（nodes/skeleton_node.py），组件由骨架建议
动态派发，gen→val 链仍是当前主链的一部分。
"""
import inspect

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.component_registry import (
    get_implemented_components,
    resolve_component_suggestions,
)
from app.agent.nodes import (
    web_research_node,
    classifier_node,
    chat_node,
    patch_node,
    architecture_planner,
    material_planner,
    skeleton_generator,
    merge_fragments_node,
    complete_execution_step,
    execution_plan_executor,
    execution_plan_review,
    execution_plan_validator,
    execution_planner,
    planning_research,
    route_execution_plan_executor,
    route_execution_plan_review,
)
from app.agent.nodes.callback_node import callback_node
from app.agent.nodes.base_component_node import (
    create_component_generator,
    create_component_validator,
)

def _planned_node(step_type: str, node):
    """包装现有业务节点，仅在 plan_mode 中回写计划步骤状态。"""

    async def run(state: GenerationState) -> dict:
        result = node(state)
        if inspect.isawaitable(result):
            result = await result
        result = dict(result or {})
        result.update(complete_execution_step(state, step_type, result))
        return result

    run.__name__ = f"planned_{step_type}"
    return run

def _dispatch_components(state: GenerationState):
    """LLM 骨架完成后，按组件建议动态派发 gen→val 节点。"""
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
    """意图分类后路由：generate → architecture, edit → patch, chat → chat。"""
    if state.get("terminal_model_error") or state.get("status") == "failed":
        logger.warning("[Graph] 意图分类模型不可用，当前请求立即终止")
        return "__end__"
    intent = state.get("intent")
    logger.info(f"[Graph] 分类完成, intent={intent}")
    if intent not in {"generate", "edit", "chat"}:
        logger.error(f"[Graph] 非法意图 {intent!r}，按只读问答安全降级")
        return "chat"
    if intent == "chat":
        return "chat"
    if state.get("plan_mode"):
        return "planning_research"
    if intent == "edit":
        return "patch"
    if intent == "generate":
        return "architecture"
    return "chat"


def _planning_research_dispatch(state: GenerationState) -> str:
    """本地知识充分 -> planner；不足且 web_research 可用 -> web_research。

    覆盖决策记录在 plan_research_diag.coverage；web_research 节点内部会再次
    检查客户端可用性，未配置 API key 时返回空上下文并回退本地。
    """
    if state.get("terminal_model_error") or state.get("status") == "failed":
        return "__end__"
    diag = state.get("plan_research_diag") or {}
    coverage = diag.get("coverage") if isinstance(diag, dict) else None
    if isinstance(coverage, dict) and coverage.get("trigger_web_research"):
        return "web_research"
    return "planner"


def _after_execution_planner(state: GenerationState) -> str:
    """计划模型失败时直接结束，禁止用空计划继续校验或重规划。"""
    if state.get("terminal_model_error") or state.get("status") == "failed":
        return "__end__"
    return "plan_validator"


def _after_execution_plan_validator(state: GenerationState) -> str:
    """计划校验失败是本轮终态，不能自动回到规划器形成无界循环。"""
    if state.get("execution_plan_status") == "failed" or state.get("error"):
        return "__end__"
    return "plan_review"


def _after_architecture(state: GenerationState) -> str:
    if state.get("terminal_model_error") or state.get("status") == "failed":
        return "plan_executor" if state.get("plan_mode") else "__end__"
    return "plan_executor" if state.get("plan_mode") else "material_plan"


def _after_planned_step(state: GenerationState, legacy_next: str) -> str:
    if state.get("terminal_model_error") or state.get("status") == "failed":
        return "plan_executor" if state.get("plan_mode") else "__end__"
    return "plan_executor" if state.get("plan_mode") else legacy_next


def _after_skeleton(state: GenerationState):
    """LLM 骨架完成后：错误即终止，否则派发组件 gen→val 链（Plan 模式相同）。

    计划步骤回写由 _planned_node 包装在节点返回时完成；组件链结束后
    merge 的条件边会把 Plan 模式路由回执行器继续走剩余步骤。
    """
    return _dispatch_components(state)


def _merge_dispatch(state: GenerationState):
    """合并失败时停止；只有有效 Blueprint 才进入最终建筑校验。"""
    if state.get("terminal_model_error") or state.get("status") == "failed":
        logger.warning("[Graph] 合并阶段失败，短路终止")
        return END
    return "final_validate"


def generation_recursion_limit(
    component_count: int,
    max_retries: int,
    *,
    plan_mode: bool = False,
) -> int:
    """计算当前生成图的安全步数上限。

    上限随组件链和有限 callback 预算增长，但不能替代各路由自己的停止条件。
    """
    components = max(0, int(component_count))
    retries = max(0, int(max_retries))
    base = max(48, 16 + components * 2 + retries * 4)
    return base + 40 if plan_mode else base


def _final_validate_dispatch(state: GenerationState):
    """最终校验后决定是否进入 callback 重试路径

    per-component 重试策略：
    - 检查 failed_components 中是否还有未达重试上限的组件
    - 如果所有失败组件都已耗尽各自的 retry，不再进入 callback
    - retry_count 只记录修复轮次，不作为提前截断新失败目标的门禁
    """
    if state.get("terminal_model_error"):
        logger.warning("[Graph] 模型服务故障，禁止进入 callback 建筑修复循环")
        return END

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
        logger.info("[Graph] 无失败组件, 无需重试")

    return "callback" if retryable else END


def build_generation_graph(enable_callback: bool = False, *, checkpointer=None):
    """构建 LangGraph 生成流程图

    classifier → (generate → architecture → material_plan
      → LLM skeleton → 动态组件 gen→val → merge → final_validate)
      | (edit → patch → END) | (chat → END)
    """
    graph = StateGraph(GenerationState)

    # ── Layer -1: 意图分类 ──
    graph.add_node("classifier", classifier_node)
    graph.add_node("chat", chat_node)
    graph.add_node("patch", _planned_node("patch", patch_node))

    # ── 可选计划层：只读研究 → 计划 → 校验 → 人工批准 → 白名单调度 ──
    graph.add_node("planning_research", planning_research)
    graph.add_node("web_research", web_research_node)
    graph.add_node("planner", execution_planner)
    graph.add_node("plan_validator", execution_plan_validator)
    graph.add_node("plan_review", execution_plan_review)
    graph.add_node("plan_executor", execution_plan_executor)

    # ── Layer -0.5: 建筑方案 ──
    graph.add_node("architecture", _planned_node("architecture", architecture_planner))
    graph.add_node("material_plan", _planned_node("material_plan", material_planner))

    # ── Layer 0: 骨架（LLM 实现，输出主体蓝图与组件建议）──
    graph.add_node("skeleton", _planned_node("skeleton", skeleton_generator))

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
    graph.add_node("merge", _planned_node("merge", merge_fragments_node))

    # ── Layer 3: 最终校验 ──
    from app.agent.nodes.validate_node import validate_node
    graph.add_node("final_validate", _planned_node("final_validate", validate_node))

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
        {
            "architecture": "architecture",
            "planning_research": "planning_research",
            "patch": "patch",
            "chat": "chat",
            "__end__": END,
        },
    )

    graph.add_edge("chat", END)
    graph.add_conditional_edges(
        "patch",
        lambda state: _after_planned_step(state, "__end__"),
        {"plan_executor": "plan_executor", "__end__": END},
    )
    graph.add_conditional_edges(
        "planning_research",
        _planning_research_dispatch,
        {"planner": "planner", "web_research": "web_research", "__end__": END},
    )
    graph.add_edge("web_research", "planner")
    graph.add_conditional_edges(
        "architecture",
        _after_architecture,
        {
            "plan_executor": "plan_executor",
            "material_plan": "material_plan",
            "__end__": END,
        },
    )
    graph.add_conditional_edges(
        "planner",
        _after_execution_planner,
        {"plan_validator": "plan_validator", "__end__": END},
    )
    graph.add_conditional_edges(
        "plan_validator",
        _after_execution_plan_validator,
        {"plan_review": "plan_review", "__end__": END},
    )
    graph.add_conditional_edges(
        "plan_review",
        route_execution_plan_review,
        {
            "__end__": END,
            "plan_executor": "plan_executor",
            "planner": "planner",
        },
    )
    graph.add_conditional_edges(
        "plan_executor",
        route_execution_plan_executor,
        {
            "__end__": END,
            "architecture": "architecture",
            "material_plan": "material_plan",
            "skeleton": "skeleton",
            "merge": "merge",
            "final_validate": "final_validate",
            "patch": "patch",
        },
    )
    graph.add_conditional_edges(
        "material_plan",
        lambda state: _after_planned_step(state, "skeleton"),
        {"plan_executor": "plan_executor", "skeleton": "skeleton", "__end__": END},
    )

    graph.add_conditional_edges(
        "skeleton",
        _after_skeleton,
        {
            "fail": END,
            "merge": "merge",
        },
    )

    # val 节点 → merge（fan-in）
    for cfg in implemented:
        val_name = f"{cfg.component_type}_val"
        graph.add_edge(val_name, "merge")

    # merge → final_validate → callback / END。模型服务故障在 merge 处直接停止，
    # 不允许把空组件分片当作建筑问题送进 callback。
    graph.add_conditional_edges(
        "merge",
        lambda state: (
            END
            if _merge_dispatch(state) == END
            else _after_planned_step(state, "final_validate")
        ),
        {"plan_executor": "plan_executor", "final_validate": "final_validate", "__end__": END, END: END},
    )
    if enable_callback:
        graph.add_conditional_edges(
            "final_validate",
            lambda state: (
                "callback"
                if _final_validate_dispatch(state) == "callback"
                else _after_planned_step(state, "__end__")
            ),
            {"callback": "callback", "plan_executor": "plan_executor", "__end__": END},
        )
    else:
        graph.add_conditional_edges(
            "final_validate",
            lambda state: _after_planned_step(state, "__end__"),
            {"plan_executor": "plan_executor", "__end__": END},
        )
    compiled = graph.compile(checkpointer=checkpointer)
    component_list = ", ".join(
        f"{c.label}({c.component_type}_gen→{c.component_type}_val)" for c in implemented
    )
    callback_status = "启用" if enable_callback else "关闭"
    logger.info(
        f"LangGraph 图编译完成: 分类 → 可选动态计划审核 → "
        f"(生成: 方案 → 材质 → LLM 骨架 → 组件链 → merge → final_validate；"
        f"gen→val 链 [{component_list}] 由骨架建议动态派发) | "
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
