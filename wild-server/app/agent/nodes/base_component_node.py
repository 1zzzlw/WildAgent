"""
通用组件节点工厂 —— gen（LLM生成）+ val（工具校验）两段式

用法:
    from .base_component_node import create_component_generator, create_component_validator
    from app.agent.component_registry import COMPONENT_REGISTRY

    door_gen = create_component_generator(COMPONENT_REGISTRY["door"])
    door_val = create_component_validator(COMPONENT_REGISTRY["door"])
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

from app.services.agent_service import agent_service

# 全局 LLM 并发信号量
_LLM_SEMAPHORE = asyncio.Semaphore(3)


# ═══════════════════════════════════════════════════════════════
# 生成器工厂（LLM 调用，有思考内容）
# ═══════════════════════════════════════════════════════════════

def create_component_generator(config: ComponentConfig):
    """创建组件生成节点（只做 LLM 生成，不做工具校验）"""

    async def generator(state: GenerationState) -> dict:
        t0 = _time.time()
        user_message = state["user_message"]
        skeleton_summary = state.get("skeleton_summary", "")
        output_key = config.output_key
        gen_diag_key = f"{config.component_type}_gen_diag"

        logger.info(f"[{config.component_type}_gen] 开始生成 {config.label}")

        # ── 1. RAG 检索 ──
        rag_t0 = _time.time()
        queries = [
            SpecQuery(user_message, {"entity_type": config.entity_type}),
        ]
        for extra_query in config.rag_extra_queries:
            queries.append(SpecQuery(extra_query, {"doc_type": "component"}))

        spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
        rag_ms = int((_time.time() - rag_t0) * 1000)
        rag_chars = len(spec_text)

        # ── 2. 构建 Prompt ──
        system_prompt = build_component_prompt(
            spec_text=spec_text,
            component_type=config.component_type,
            skeleton_summary=skeleton_summary,
            extra_rules=config.extra_rules,
        )
        prompt_chars = len(system_prompt)

        # ── 3. LLM 调用（流式）──
        thinking_mode = state.get("thinking_mode", False)
        on_reasoning_delta = state.get("on_reasoning_delta")
        use_streaming = thinking_mode and on_reasoning_delta is not None

        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_message(config, skeleton_summary)},
        ]

        llm_t0 = _time.time()
        reply_text = ""
        reasoning = ""
        token_usage = None

        try:
            async with _LLM_SEMAPHORE:
                if use_streaming:
                    async for chunk in llm.astream(messages):
                        if hasattr(chunk, "additional_kwargs"):
                            reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
                            if reasoning_delta:
                                reasoning += reasoning_delta
                                await on_reasoning_delta(config.component_type, reasoning_delta)
                        if hasattr(chunk, "content") and chunk.content:
                            reply_text += chunk.content
                else:
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
            logger.error(f"[{config.component_type}_gen] LLM 调用失败: {e}")
            return {
                output_key: [] if config.is_list else None,
                gen_diag_key: {
                    "label": config.label,
                    "rag_chars": rag_chars, "rag_ms": rag_ms,
                    "error": str(e),
                },
            }

        llm_ms = int((_time.time() - llm_t0) * 1000)
        llm_chars = len(reply_text)
        reasoning_chars = len(reasoning)

        logger.info(
            f"[{config.component_type}_gen] LLM 完成: {llm_chars} 字符, {llm_ms}ms"
            + (f", thinking={reasoning_chars}字符" if reasoning_chars else "")
        )

        # ── 4. 提取 JSON ──
        if config.is_list:
            fragments = extract_json_array(reply_text)
        else:
            obj = extract_json_object(reply_text)
            fragments = [obj] if obj else []

        if not fragments or (not config.is_list and fragments[0] is None):
            logger.warning(f"[{config.component_type}_gen] 未能提取 JSON")
            return {
                output_key: [] if config.is_list else None,
                gen_diag_key: {
                    "label": config.label,
                    "rag_chars": rag_chars, "rag_ms": rag_ms,
                    "prompt_chars": prompt_chars,
                    "llm_chars": llm_chars, "llm_ms": llm_ms,
                    "token_usage": token_usage,
                    "reasoning_chars": reasoning_chars,
                    "fragment_count": 0,
                    "error": "JSON 提取失败",
                },
            }

        # ── 5. 基本校验（类型 + 必填字段）──
        valid = _validate_fragments(fragments, config)
        total_ms = int((_time.time() - t0) * 1000)

        logger.info(f"[{config.component_type}_gen] 完成: {len(valid)} 个 {config.label}, {total_ms}ms")

        return {
            output_key: valid if config.is_list else (valid[0] if valid else None),
            gen_diag_key: {
                "label": config.label,
                "rag_chars": rag_chars, "rag_ms": rag_ms,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars, "llm_ms": llm_ms,
                "token_usage": token_usage,
                "reasoning_chars": reasoning_chars,
                "reasoning_preview": reasoning[:800] if reasoning else "",
                "fragment_count": len(valid),
                "total_ms": total_ms,
            },
        }

    generator.__name__ = f"{config.component_type}_gen"
    return generator


# ═══════════════════════════════════════════════════════════════
# 校验器工厂（工具调用，有诊断输出，无 LLM）
# ═══════════════════════════════════════════════════════════════

def create_component_validator(config: ComponentConfig):
    """创建组件校验节点（只做工具校验，不调 LLM）"""

    async def validator(state: GenerationState) -> dict:
        t0 = _time.time()
        output_key = config.output_key
        val_diag_key = f"{config.component_type}_val_diag"

        fragments = state.get(output_key)
        if config.is_list:
            fragments = fragments if isinstance(fragments, list) else []
        else:
            fragments = [fragments] if isinstance(fragments, dict) else []

        if not fragments:
            logger.info(f"[{config.component_type}_val] 无片段，跳过校验")
            return {
                val_diag_key: {
                    "label": config.label,
                    "fragment_count": 0,
                    "validation_applied": False,
                },
            }

        logger.info(f"[{config.component_type}_val] 校验 {len(fragments)} 个 {config.label}")

        skeleton_blueprint = state.get("skeleton_blueprint", {})
        validated, fixed = _validate_and_fix_with_tools(
            fragments,
            config.component_type,
            skeleton_blueprint,
            config.is_element,
        )

        total_ms = int((_time.time() - t0) * 1000)
        logger.info(
            f"[{config.component_type}_val] 完成: {len(validated)} 个, "
            + ("已修复" if fixed else "无需修复")
            + f", {total_ms}ms"
        )

        return {
            output_key: validated if config.is_list else (validated[0] if validated else None),
            val_diag_key: {
                "label": config.label,
                "fragment_count": len(validated),
                "validation_applied": fixed,
                "total_ms": total_ms,
            },
        }

    validator.__name__ = f"{config.component_type}_val"
    return validator


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _validate_fragments(fragments: list[dict], config: ComponentConfig) -> list[dict]:
    """基本校验：类型匹配 + 必填字段检查"""
    valid = []
    for frag in fragments:
        if not isinstance(frag, dict):
            continue
        if frag.get("type") != config.component_type:
            continue
        missing = [f for f in config.required_fields if not frag.get(f)]
        if missing:
            logger.warning(
                f"[{config.component_type}] 跳过 {frag.get('id', '?')}：缺少必填字段 {missing}"
            )
            continue
        valid.append(frag)
    return valid


def _build_user_message(config: ComponentConfig, skeleton_summary: str = "") -> str:
    """构建发给 LLM 的用户消息"""
    label = config.label
    if config.is_list:
        return (
            f"用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】中列出的"
            f"墙体、楼板、柱子信息，为每面墙/每个位置生成合适的 {label} 组件。\n\n"
            f"只输出 JSON 数组，不要其他文字。"
        )
    else:
        return (
            f"用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】中列出的"
            f"信息生成 {label} 构件。\n\n"
            f"只输出单个 JSON 对象，不要数组，不要其他文字。"
        )


def _validate_and_fix_with_tools(
    fragments: list[dict],
    component_type: str,
    skeleton_blueprint: dict,
    is_element: bool
) -> tuple[list[dict], bool]:
    """使用专用工具校验并修复组件"""
    if not fragments:
        return [], False

    try:
        from app.tools.component_tools import validate_component, fix_component
    except ImportError:
        logger.warning(f"[{component_type}] 组件工具未找到，跳过校验修复")
        return fragments, False

    temp_blueprint = {
        "meta": skeleton_blueprint.get("meta", {"version": "1.1", "type": "building"}),
        "geometry": {
            "elements": skeleton_blueprint.get("geometry", {}).get("elements", []).copy(),
            "components": skeleton_blueprint.get("geometry", {}).get("components", []).copy(),
        },
        "materials": skeleton_blueprint.get("materials", {}),
    }

    if is_element:
        temp_blueprint["geometry"]["elements"].extend(fragments)
    else:
        temp_blueprint["geometry"]["components"].extend(fragments)

    validation_result = validate_component(component_type, temp_blueprint)

    if "❌" in validation_result:
        logger.warning(f"[{component_type}_val] 检测到错误，自动修复中...")
        fix_result = fix_component(component_type, temp_blueprint)
        logger.info(f"[{component_type}_val] 修复结果:\n{fix_result}")

        if is_element:
            fixed_fragments = temp_blueprint["geometry"]["elements"][-len(fragments):]
        else:
            fixed_fragments = temp_blueprint["geometry"]["components"][-len(fragments):]

        return fixed_fragments, True

    return fragments, False
