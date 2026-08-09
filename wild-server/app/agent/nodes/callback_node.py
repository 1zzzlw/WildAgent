"""
Layer 2 扩展: 回调重试节点

校验失败后，对每个失败组件做精准修正：
  RAG(错误类型) + 工具数据 + 骨架上下文 → LLM 只修正失败组件 → 更新对应 fragment

这是 LangGraph 架构中最关键的创新点，详见设计文档 03-回调与重试机制.md。
"""
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.prompts import build_callback_prompt
from app.agent.model_client import create_llm
from app.agent.component_registry import COMPONENT_REGISTRY
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_array


# 模块级导入
from app.services.agent_service import agent_service


async def callback_node(state: GenerationState) -> dict:
    """对校验失败的组件进行精确修正重试

    流程:
    1. 从 failed_components 提取失败信息（含 current_params）
    2. 精准 RAG（按错误类型检索）
    3. 运行组件工具获取空间约束数据（tools 提供"具体错在哪里"）
    4. 构建 callback_payload（含骨架上下文 + 当前参数 + 工具建议 + RAG）
    5. LLM 只输出修正后的组件（支持流式思考）
    6. 更新对应的 fragments
    7. 递增 retry_count
    """
    failed_components = state.get("failed_components", [])
    if not failed_components:
        logger.info("[callback_node] 无失败组件，跳过")
        return {"retry_count": state.get("retry_count", 0) + 1}

    # ── 0. per-component 重试过滤 ──
    max_retries = state.get("max_retries", 3)
    comp_retries = dict(state.get("component_retry_counts", {}))
    retryable: list[dict] = []
    skipped_exhausted: list[str] = []

    for fc in failed_components:
        comp_id = fc.get("component_id", "")
        current = comp_retries.get(comp_id, 0)
        if current >= max_retries:
            skipped_exhausted.append(comp_id)
            logger.warning(f"[callback_node] {comp_id} 已达 per-component 重试上限 ({current}/{max_retries}), 跳过")
        else:
            comp_retries[comp_id] = current + 1
            retryable.append(fc)

    if skipped_exhausted:
        logger.info(f"[callback_node] 跳过 {len(skipped_exhausted)} 个耗尽重试的组件: {skipped_exhausted}")

    if not retryable:
        logger.info("[callback_node] 所有失败组件均已耗尽重试")
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "component_retry_counts": comp_retries,
        }

    logger.info(f"[callback_node] 开始修正 {len(retryable)} 个失败组件 (已跳过 {len(skipped_exhausted)} 个)")

    skeleton_summary = state.get("skeleton_summary", "")
    skeleton_blueprint = state.get("skeleton_blueprint", {})
    passed_ids = state.get("passed_component_ids", [])
    retry_count = state.get("retry_count", 0)
    thinking_mode = state.get("thinking_mode", False)
    on_reasoning_delta = state.get("on_reasoning_delta")

    # ── 1. 精准 RAG + 工具数据（按失败组件类型检索）──
    failed_types = list({fc.get("component_type", "") for fc in retryable})
    queries = []
    for ftype in failed_types:
        if ftype:
            queries.append(SpecQuery(
                f"{ftype} component specification rules",
                {"entity_type": ftype}
            ))

    if not queries:
        queries = [SpecQuery("component rules specification", {})]

    spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
    logger.info(f"[callback_node] RAG 上下文: {len(spec_text)} 字符")

    # ── 2. 运行组件工具，获取空间约束数据 ──
    # 为每个可重试的失败组件构建临时 blueprint 并跑 validate 工具
    enriched_failed = []
    for fc in retryable:
        enriched = dict(fc)  # 拷贝原始失败信息
        comp_type = fc.get("component_type", "")

        # 尝试运行组件校验工具获取精确空间数据
        tool_context = ""
        try:
            from app.tools.component_tools import validate_component

            # 构建只包含该组件的临时 blueprint
            temp_bp = {
                "meta": skeleton_blueprint.get("meta", {"version": "1.1", "type": "building"}),
                "geometry": {
                    "elements": skeleton_blueprint.get("geometry", {}).get("elements", []).copy(),
                    "components": [fc.get("current_params", {})] if fc.get("current_params") else [],
                },
                "materials": skeleton_blueprint.get("materials", {}),
            }
            tool_context = validate_component(comp_type, temp_bp)
            if tool_context:
                logger.info(f"[callback_node] 工具数据 ({comp_type}): {len(tool_context)} 字符")
        except Exception as e:
            logger.warning(f"[callback_node] 工具调用失败 ({comp_type}): {e}")

        enriched["tool_data"] = tool_context
        enriched_failed.append(enriched)

    # ── 3. 构建 callback prompt ──
    system_prompt = build_callback_prompt(
        spec_text=spec_text,
        skeleton_summary=skeleton_summary,
        failed_components=enriched_failed,
        passed_component_ids=passed_ids,
    )

    # ── 4. LLM 修正（支持流式思考）──
    use_streaming = thinking_mode and on_reasoning_delta is not None
    llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请修正以下 {len(enriched_failed)} 个失败组件。"
                f"只输出 JSON 数组，包含每个修正后的组件对象。"
            ),
        },
    ]

    reply_text = ""
    reasoning = ""
    
    try:
        if use_streaming:
            # 流式调用：实时推送思考内容
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "additional_kwargs"):
                    reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
                    if reasoning_delta:
                        reasoning += reasoning_delta
                        await on_reasoning_delta("callback", reasoning_delta)
                
                if hasattr(chunk, "content") and chunk.content:
                    reply_text += chunk.content
            
            logger.info(f"[callback_node] LLM 流式修正完成: {len(reply_text)} 字符, thinking={len(reasoning)}字符")
        else:
            # 非流式调用
            response = await llm.ainvoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)
            logger.info(f"[callback_node] LLM 修正回复: {len(reply_text)} 字符")
    except Exception as e:
        logger.error(f"[callback_node] LLM 调用失败: {e}")
        return {"retry_count": retry_count + 1}

    # ── 4. 提取修正后的组件 ──
    fixed_fragments = extract_json_array(reply_text)
    if not fixed_fragments:
        logger.warning("[callback_node] 未能从 LLM 回复中提取修正组件")
        return {"retry_count": retry_count + 1}

    # ── 5. 按组件类型分组，更新对应的 fragments ──
    updates = _apply_fixes_to_state(state, fixed_fragments, enriched_failed)

    new_retry_count = retry_count + 1
    logger.info(
        f"[callback_node] 修正完成 ({new_retry_count}/{state.get('max_retries', 3)}): "
        f"处理了 {len(fixed_fragments)} 个修正"
    )

    return {
        **updates,
        "retry_count": new_retry_count,
        "component_retry_counts": comp_retries,
    }


def _apply_fixes_to_state(
    state: GenerationState,
    fixed_fragments: list[dict],
    failed_components: list[dict],
) -> dict:
    """将 LLM 修正后的组件写回对应的 state 字段

    策略: 用修正后的 fragment 替换同 ID 的旧 fragment。
    未匹配到的修正视为新增。
    """
    # 建立修正组件 ID → 修正后对象的映射
    fix_map: dict[str, dict] = {}
    for frag in fixed_fragments:
        frag_id = frag.get("id")
        if frag_id:
            fix_map[frag_id] = frag

    # 找出失败组件的类型 → state key 映射
    failed_ids = {fc.get("component_id") for fc in failed_components if fc.get("component_id")}

    updates: dict = {}

    # 遍历所有已实现的组件类型，更新包含失败 ID 的 fragments
    for comp_type, cfg in COMPONENT_REGISTRY.items():
        if not cfg.implemented:
            continue

        old_fragments = state.get(cfg.output_key)

        if cfg.is_list and isinstance(old_fragments, list):
            new_list = []
            for frag in old_fragments:
                frag_id = frag.get("id", "")
                if frag_id in fix_map:
                    # 用修正后的版本替换
                    new_list.append(fix_map[frag_id])
                    logger.info(f"[callback_node] 更新 {cfg.label}: {frag_id}")
                else:
                    new_list.append(frag)

            # 修正中有新增的同类型组件（未匹配到旧 ID）
            for fix_id, fix_frag in fix_map.items():
                if fix_frag.get("type") == comp_type and fix_id not in {
                    f.get("id") for f in old_fragments
                }:
                    new_list.append(fix_frag)
                    logger.info(f"[callback_node] 新增 {cfg.label}: {fix_id}")

            updates[cfg.output_key] = new_list

        elif not cfg.is_list and isinstance(old_fragments, dict):
            frag_id = old_fragments.get("id", "")
            if frag_id in fix_map:
                updates[cfg.output_key] = fix_map[frag_id]
                logger.info(f"[callback_node] 更新 {cfg.label}: {frag_id}")

    return updates
