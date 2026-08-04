"""
通用组件节点工厂 —— 消除 door/window/roof/railing 的 85% 代码重复

用法：
    from .base_component_node import create_component_node
    from app.agent.component_registry import COMPONENT_REGISTRY

    door_generator = create_component_node(COMPONENT_REGISTRY["door"])

每个节点返回诊断数据（{comp_type}_diag），供 precision_mode 前端展示。
"""
import asyncio
import time as _time
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.prompts import build_component_prompt
from app.agent.model_client import create_llm
from app.agent.component_registry import ComponentConfig
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_array, extract_json_object

# 模块级导入
from app.services.agent_service import agent_service

# 全局 LLM 并发信号量（防止并行节点同时调用 LLM 触发限流）
_LLM_SEMAPHORE = asyncio.Semaphore(3)


def create_component_node(config: ComponentConfig):
    """工厂函数：根据 ComponentConfig 创建组件生成节点"""

    async def generator(state: GenerationState) -> dict:
        t0 = _time.time()
        user_message = state["user_message"]
        skeleton_summary = state.get("skeleton_summary", "")
        output_key = config.output_key
        diag_key = f"{config.component_type}_diag"

        # ── 1. 跳过检查 ──
        if _should_skip(state, config):
            logger.info(f"[{config.component_type}] 跳过（{config.label} 未被建议）")
            return {
                output_key: [] if config.is_list else None,
                diag_key: {
                    "skipped": True,
                    "reason": "用户未提及" if config.need_keywords else "用户明确排除",
                    "label": config.label,
                },
            }

        logger.info(f"[{config.component_type}] 开始生成 {config.label}")

        # ── 2. RAG 检索 ──
        rag_t0 = _time.time()
        queries = [
            SpecQuery(user_message, {"entity_type": config.entity_type}),
        ]
        for extra_query in config.rag_extra_queries:
            queries.append(SpecQuery(extra_query, {"doc_type": "component"}))

        spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
        rag_ms = int((_time.time() - rag_t0) * 1000)
        rag_chars = len(spec_text)
        logger.info(f"[{config.component_type}] RAG 完成: {rag_chars} 字符, {rag_ms}ms")

        # ── 3. 构建 Prompt ──
        system_prompt = build_component_prompt(
            spec_text=spec_text,
            component_type=config.component_type,
            skeleton_summary=skeleton_summary,
            extra_rules=config.extra_rules,
        )
        prompt_chars = len(system_prompt)

        # ── 4. LLM 调用（流式以支持思考展示）──
        thinking_mode = state.get("thinking_mode", False)
        on_reasoning_delta = state.get("on_reasoning_delta")
        use_streaming = thinking_mode and on_reasoning_delta is not None
        
        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_message(user_message, config)},
        ]

        llm_t0 = _time.time()
        reply_text = ""
        reasoning = ""
        token_usage = None
        
        try:
            async with _LLM_SEMAPHORE:
                if use_streaming:
                    # 流式调用：实时推送思考内容
                    async for chunk in llm.astream(messages):
                        if hasattr(chunk, "additional_kwargs"):
                            reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
                            if reasoning_delta:
                                reasoning += reasoning_delta
                                await on_reasoning_delta(config.component_type, reasoning_delta)
                        
                        if hasattr(chunk, "content") and chunk.content:
                            reply_text += chunk.content
                else:
                    # 非流式调用
                    response = await llm.ainvoke(messages)
                    reply_text = response.content if hasattr(response, "content") else str(response)
                    
                    if hasattr(response, "additional_kwargs"):
                        reasoning = response.additional_kwargs.get("reasoning_content", "") or ""
                    if not reasoning and hasattr(response, "response_metadata"):
                        reasoning = response.response_metadata.get("reasoning_content", "") or ""
                    
                    if hasattr(response, "response_metadata"):
                        usage = response.response_metadata.get("token_usage", {})
                        if usage:
                            token_usage = {
                                "input": usage.get("prompt_tokens", 0),
                                "output": usage.get("completion_tokens", 0),
                                "total": usage.get("total_tokens", 0),
                            }
        
        except Exception as e:
            logger.error(f"[{config.component_type}] LLM 调用失败: {e}")
            return {
                output_key: [] if config.is_list else None,
                diag_key: {
                    "skipped": False,
                    "label": config.label,
                    "rag_chars": rag_chars,
                    "rag_ms": rag_ms,
                    "error": str(e),
                },
            }

        llm_ms = int((_time.time() - llm_t0) * 1000)
        llm_chars = len(reply_text)
        reasoning_chars = len(reasoning)
        
        logger.info(
            f"[{config.component_type}] LLM 回复: {llm_chars} 字符, {llm_ms}ms"
            + (f", thinking={reasoning_chars}字符" if reasoning_chars else "")
            + (f", tokens={token_usage['total']}" if token_usage else "")
        )

        # ── 5. 提取 JSON ──
        if config.is_list:
            fragments = extract_json_array(reply_text)
        else:
            obj = extract_json_object(reply_text)
            fragments = [obj] if obj else []

        if not fragments or (not config.is_list and fragments[0] is None):
            logger.warning(f"[{config.component_type}] 未能提取 JSON")
            return {
                output_key: [] if config.is_list else None,
                diag_key: {
                    "skipped": False,
                    "label": config.label,
                    "rag_chars": rag_chars,
                    "rag_ms": rag_ms,
                    "prompt_chars": prompt_chars,
                    "llm_chars": llm_chars,
                    "llm_ms": llm_ms,
                    "token_usage": token_usage,
                    "reasoning_chars": reasoning_chars,
                    "fragment_count": 0,
                    "error": "JSON 提取失败",
                },
            }

        # ── 6. 基本校验 ──
        valid = _validate_fragments(fragments, config)
        
        # ── 7. 立即调用专用工具校验修复 ──
        skeleton_blueprint = state.get("skeleton_blueprint", {})
        validated, fixed = _validate_and_fix_with_tools(
            valid, 
            config.component_type, 
            skeleton_blueprint,
            config.is_element
        )
        
        total_ms = int((_time.time() - t0) * 1000)

        logger.info(f"[{config.component_type}] 完成: {len(validated)} 个 {config.label}, {total_ms}ms")

        return {
            output_key: validated if config.is_list else (validated[0] if validated else None),
            diag_key: {
                "skipped": False,
                "label": config.label,
                "rag_chars": rag_chars,
                "rag_ms": rag_ms,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars,
                "llm_ms": llm_ms,
                "token_usage": token_usage,
                "reasoning_chars": reasoning_chars,
                "reasoning_preview": reasoning[:800] if reasoning else "",
                "fragment_count": len(validated),
                "validation_applied": fixed,  # 是否应用了修复
                "total_ms": total_ms,
            },
        }

    generator.__name__ = f"{config.component_type}_generator"
    return generator


def _should_skip(state: GenerationState, config: ComponentConfig) -> bool:
    """检查是否应跳过该组件
    
    优先检查 skeleton 节点的建议列表，如果有建议列表则只运行被建议的组件
    """
    suggested_components = state.get("suggested_components", [])
    
    # 如果骨架节点已经给出建议列表，则只运行被建议的组件
    if suggested_components:
        return config.component_type not in suggested_components
    
    # 降级：如果没有建议列表，使用关键词逻辑（兼容旧版）
    user_message = state["user_message"]
    if any(kw in user_message for kw in config.skip_keywords):
        return True

    if config.need_keywords:
        if not any(kw in user_message for kw in config.need_keywords):
            return True

    return False


def _validate_fragments(fragments: list[dict], config: ComponentConfig) -> list[dict]:
    """基本校验：类型匹配 + 必填字段检查"""
    valid = []
    for frag in fragments:
        if not isinstance(frag, dict):
            continue

        if frag.get("type") != config.component_type:
            logger.warning(f"[{config.component_type}] 跳过类型不匹配: {frag.get('type')}")
            continue

        missing = [f for f in config.required_fields if not frag.get(f)]
        if missing:
            logger.warning(
                f"[{config.component_type}] 跳过 {frag.get('id', '?')}：缺少必填字段 {missing}"
            )
            continue

        valid.append(frag)

    return valid


def _build_user_message(user_message: str, config: ComponentConfig) -> str:
    """构建发给 LLM 的用户消息"""
    if config.is_list:
        return f"{user_message}\n\n请生成 {config.label} 组件（只输出 JSON 数组，不要其他文字）"
    else:
        return f"{user_message}\n\n请生成 {config.label} 构件（只输出单个 JSON 对象，不要数组）"


def _validate_and_fix_with_tools(
    fragments: list[dict], 
    component_type: str, 
    skeleton_blueprint: dict,
    is_element: bool
) -> tuple[list[dict], bool]:
    """使用专用工具校验并修复组件
    
    Returns:
        (修复后的组件列表, 是否应用了修复)
    """
    if not fragments:
        return [], False
    
    # 导入组件工具
    try:
        from app.tools.component_tools import validate_component, fix_component
    except ImportError:
        logger.warning(f"[{component_type}] 组件工具未找到，跳过校验修复")
        return fragments, False
    
    # 构建临时 Blueprint 用于校验
    temp_blueprint = {
        "meta": skeleton_blueprint.get("meta", {"version": "1.1", "type": "building"}),
        "geometry": {
            "elements": skeleton_blueprint.get("geometry", {}).get("elements", []).copy(),
            "components": skeleton_blueprint.get("geometry", {}).get("components", []).copy(),
        },
        "materials": skeleton_blueprint.get("materials", {}),
    }
    
    # 将新生成的组件加入临时 Blueprint
    if is_element:
        temp_blueprint["geometry"]["elements"].extend(fragments)
    else:
        temp_blueprint["geometry"]["components"].extend(fragments)
    
    # 校验
    validation_result = validate_component(component_type, temp_blueprint)
    
    # 如果有错误，立即修复
    if "❌" in validation_result:
        logger.warning(f"[{component_type}] 检测到错误，自动修复中...")
        logger.info(f"[{component_type}] 校验结果:\n{validation_result}")
        
        fix_result = fix_component(component_type, temp_blueprint)
        logger.info(f"[{component_type}] 修复结果:\n{fix_result}")
        
        # 提取修复后的组件
        if is_element:
            fixed_fragments = temp_blueprint["geometry"]["elements"][-len(fragments):]
        else:
            fixed_fragments = temp_blueprint["geometry"]["components"][-len(fragments):]
        
        return fixed_fragments, True
    else:
        logger.info(f"[{component_type}] 校验通过: {validation_result}")
        return fragments, False
