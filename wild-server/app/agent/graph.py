"""
LangGraph 图定义 —— 可审核计划层 + Plan2Build 确定性执行链

流程:
  classifier (意图分类)
    → PLAN:     planning_research → planner → plan_review → plan_executor
    → GENERATE: architecture (总体方案候选) → floor_plan_design (FloorPlanIR v2)
                  → floor_plan_review (确认/修改)
                  → material_plan (材质意图+资产解析)
                  → skeleton/ApprovedPlanAssembler (确定性主体 + G1-G6)
                  → style_review (第二次确认)
                  → decor_assembly (StylePackage → Decor IR + G7)
                  → merge → final_validate → done
    → EDIT:     patch (统一 ScenePatch 生成与校验) → done
    → CHAT:     chat (RAG知识问答) → done

旧组件 gen→val 节点仍为兼容路径；新建筑主链的主体、门窗、屋顶和装饰不再
依赖它们自由生成坐标。
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
    classifier_node,
    chat_node,
    patch_node,
    architecture_planner,
    floor_plan_designer,
    floor_plan_review,
    route_floor_plan_review,
    material_planner,
    approved_plan_assembler,
    skeleton_generator,  # 旧测试/扩展导入兼容；生成主链已不再调用
    style_review,
    route_style_review,
    decor_assembler,
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

# 保留既有 monkeypatch/扩展点名称；它现在指向确定性主体装配器。
# 旧 LLM 骨架实现仍可从 nodes.skeleton_node 显式导入，但不在生成主链运行。
legacy_skeleton_generator = skeleton_generator
skeleton_generator = approved_plan_assembler


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
    """主体完成后进入风格确认；仅旧兼容输入才动态派发组件节点。"""
    if state.get("error") or state.get("status") == "failed":
        logger.warning("[Graph] 骨架生成失败，短路终止")
        return "fail"

    # 已确认方案的主体、门窗、屋顶均由 ApprovedPlanAssembler 一次性确定。
    # 这里直接进入合并/总校验，避免再次调用各组件 LLM 改写坐标或因额度失败。
    if state.get("deterministic_body_complete"):
        logger.info("[Graph] 确定性主体装配完成，进入第二次风格确认")
        return "style_review"

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
    return "planner"


def _after_architecture(state: GenerationState) -> str:
    return "plan_executor" if state.get("plan_mode") else "floor_plan_design"


def _after_planned_step(state: GenerationState, legacy_next: str) -> str:
    return "plan_executor" if state.get("plan_mode") else legacy_next


def _after_skeleton(state: GenerationState):
    if state.get("plan_mode"):
        if state.get("error") or state.get("status") == "failed":
            return "fail"
        return "plan_executor"
    return _dispatch_components(state)


def _after_floor_plan_review(state: GenerationState) -> str:
    if state.get("plan_mode"):
        return "plan_executor"
    return route_floor_plan_review(state)


def _after_style_review(state: GenerationState) -> str:
    if state.get("plan_mode"):
        return "plan_executor"
    return route_style_review(state)


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

    classifier → (generate → architecture → floor_plan_design → floor_plan_review
      → material_plan → deterministic skeleton/G1-G6 → style_review
      → decor_assembly/G7 → merge → final_validate) | (edit → patch → END) | (chat → END)
    """
    graph = StateGraph(GenerationState)

    # ── Layer -1: 意图分类 ──
    graph.add_node("classifier", classifier_node)
    graph.add_node("chat", chat_node)
    graph.add_node("patch", _planned_node("patch", patch_node))

    # ── 可选计划层：只读研究 → 计划 → 校验 → 人工批准 → 白名单调度 ──
    graph.add_node("planning_research", planning_research)
    graph.add_node("planner", execution_planner)
    graph.add_node("plan_validator", execution_plan_validator)
    graph.add_node("plan_review", execution_plan_review)
    graph.add_node("plan_executor", execution_plan_executor)

    # ── Layer -0.5: 建筑方案 ──
    graph.add_node("architecture", _planned_node("architecture", architecture_planner))
    graph.add_node("floor_plan_design", _planned_node("floor_plan_design", floor_plan_designer))
    graph.add_node("floor_plan_review", _planned_node("floor_plan_review", floor_plan_review))
    graph.add_node("material_plan", _planned_node("material_plan", material_planner))

    # ── Layer 0: 骨架 ──
    graph.add_node("skeleton", _planned_node("skeleton", skeleton_generator))
    graph.add_node("style_review", _planned_node("style_review", style_review))
    graph.add_node("decor_assembly", _planned_node("decor_assembly", decor_assembler))

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
        {"planner": "planner"},
    )
    graph.add_conditional_edges(
        "architecture",
        _after_architecture,
        {
            "plan_executor": "plan_executor",
            "floor_plan_design": "floor_plan_design",
        },
    )
    graph.add_edge("planner", "plan_validator")
    graph.add_edge("plan_validator", "plan_review")
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
            "planner": "planner",
            "floor_plan_design": "floor_plan_design",
            "floor_plan_review": "floor_plan_review",
            "material_plan": "material_plan",
            "skeleton": "skeleton",
            "style_review": "style_review",
            "decor_assembly": "decor_assembly",
            "merge": "merge",
            "final_validate": "final_validate",
            "patch": "patch",
        },
    )
    graph.add_conditional_edges(
        "floor_plan_design",
        lambda state: _after_planned_step(state, "floor_plan_review"),
        {"plan_executor": "plan_executor", "floor_plan_review": "floor_plan_review"},
    )
    graph.add_conditional_edges(
        "floor_plan_review",
        _after_floor_plan_review,
        {
            "plan_executor": "plan_executor",
            "floor_plan_design": "floor_plan_design",
            "material_plan": "material_plan",
        },
    )
    graph.add_conditional_edges(
        "material_plan",
        lambda state: _after_planned_step(state, "skeleton"),
        {"plan_executor": "plan_executor", "skeleton": "skeleton"},
    )

    graph.add_conditional_edges(
        "skeleton",
        _after_skeleton,
        {
            "fail": END,
            "plan_executor": "plan_executor",
            "merge": "merge",
            "style_review": "style_review",
        },
    )
    graph.add_conditional_edges(
        "style_review",
        _after_style_review,
        {
            "plan_executor": "plan_executor",
            "style_review": "style_review",
            "decor_assembly": "decor_assembly",
        },
    )
    graph.add_conditional_edges(
        "decor_assembly",
        lambda state: _after_planned_step(state, "merge"),
        {"plan_executor": "plan_executor", "merge": "merge"},
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
        {"plan_executor": "plan_executor", "final_validate": "final_validate", END: END},
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
        f"(生成: 方案 → 平面审核 → 材质 → 确定性主体 → 风格审核 → 装饰 → merge → final_validate；"
        f"旧兼容组件链 [{component_list}]) | "
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
