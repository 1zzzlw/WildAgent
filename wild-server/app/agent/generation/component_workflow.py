"""
通用组件节点工厂 —— gen（LLM生成）+ val（工具校验）两段式

图入口由 ``nodes/base_component_node.py`` 转发到本模块；本模块只组织组件生成与复检用例。

    door_gen = create_component_generator(COMPONENT_REGISTRY["door"])
    door_val = create_component_validator(COMPONENT_REGISTRY["door"])
"""
import asyncio
import json
import time as _time
from loguru import logger

from app.agent.state import GenerationState
from app.agent.generation.component_processing import (
    component_state_update,
    validate_and_fix_with_tools,
    validate_fragments,
)
from app.agent.prompts import (
    build_component_prompt,
    build_component_recovery_messages,
    build_component_user_message,
)
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, stream_llm
from app.llm.errors import classify_model_error
from app.agent.runtime import get_reasoning_callback
from app.agent.generation.components import ComponentConfig
from app.spec.loader import SpecQuery
from app.agent.knowledge.policy import plan_knowledge_query
from app.utils.json_extractor import extract_json_array, extract_json_object

# 全局 LLM 并发信号量
_LLM_SEMAPHORE = asyncio.Semaphore(3)


async def _recover_component_json(
    config: ComponentConfig,
    system_prompt: str,
    user_message: str,
    failed_reply: str,
) -> tuple[str, int]:
    """用一次非思考调用把无效的组件回复恢复为单一 JSON 数组/对象。

    返回 (恢复文本, 耗时毫秒)；调用失败返回原失败回复，让调用方走既有空分片路径。
    """
    recovery_t0 = _time.time()
    try:
        recovery_llm = create_llm(enable_thinking=False, streaming=False)
        result = await invoke_llm(
            recovery_llm,
            build_component_recovery_messages(
                config=config,
                system_prompt=system_prompt,
                user_message=user_message,
                failed_reply=failed_reply,
            ),
        )
        return result.content, int((_time.time() - recovery_t0) * 1000)
    except Exception as exc:
        logger.warning(f"[{config.component_type}_gen] 定向格式恢复调用失败: {exc}")
        return failed_reply, int((_time.time() - recovery_t0) * 1000)


# 生成器工厂（LLM 调用，有思考内容）

def create_component_generator(config: ComponentConfig):
    """创建组件生成节点（只做 LLM 生成，不做工具校验）"""

    async def generator(state: GenerationState) -> dict:
        from app.services.agent_service import agent_service

        t0 = _time.time()
        user_message = state["user_message"]
        skeleton_summary = state.get("skeleton_summary", "")
        spatial_invariants = state.get("spatial_invariants", {})
        if spatial_invariants:
            skeleton_summary = (
                f"{skeleton_summary}\n\n【确定性空间不变量（必须遵守，不得自行改写）】\n"
                f"{json.dumps(spatial_invariants, ensure_ascii=False, default=str)}"
            )
        design_brief = state.get("design_brief")  # ← 骨架设计清单
        gen_diag_key = f"{config.component_type}_gen_diag"

        logger.info(f"[{config.component_type}_gen] 开始生成 {config.label}")

        # ── 1. RAG 检索 ──
        rag_t0 = _time.time()
        selected_query = plan_knowledge_query(user_message, state.get("architecture_plan"))
        queries = [
            SpecQuery(selected_query, {"doc_type": "component", "entity_type": config.entity_type}),
            SpecQuery(
                f"{user_message}\n{config.label}构件参数与位置规则：{config.component_type} 的宿主、局部坐标、字段与边界",
                {"doc_type": "component", "entity_type": config.entity_type},
            ),
        ]
        for extra_query in config.rag_extra_queries:
            queries.append(SpecQuery(extra_query, {"doc_type": "component", "entity_type": config.entity_type}))

        rag_error = None
        try:
            spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
        except Exception as exc:
            spec_text = ""
            rag_error = str(exc)
            logger.warning(
                f"[{config.component_type}_gen] RAG 检索失败，继续使用骨架约束: {exc}"
            )
        rag_ms = int((_time.time() - rag_t0) * 1000)
        rag_chars = len(spec_text)
        rag_hits = [] if rag_error else [
            {
                "source": hit.metadata.get("source", "?"),
                "heading": hit.metadata.get("heading", "?"),
                "doc_type": hit.metadata.get("doc_type", "?"),
                "entity_type": hit.metadata.get("entity_type", "?"),
            }
            for hit in getattr(agent_service.spec_loader, "last_results", [])
        ]

        # ── 2. 构建 Prompt ──
        system_prompt = build_component_prompt(
            spec_text=spec_text,
            component_type=config.component_type,
            skeleton_summary=skeleton_summary,
            extra_rules=config.extra_rules,
            design_brief=design_brief,
        )
        prompt_chars = len(system_prompt)

        # ── 3. LLM 调用（流式）──
        thinking_mode = state.get("thinking_mode", False)
        on_reasoning_delta = get_reasoning_callback()
        use_streaming = thinking_mode and on_reasoning_delta is not None

        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_component_user_message(config, design_brief)},
        ]

        llm_t0 = _time.time()
        reply_text = ""
        reasoning = ""
        token_usage = None

        try:
            async with _LLM_SEMAPHORE:
                if use_streaming:
                    llm_result = await stream_llm(
                        llm,
                        messages,
                        on_reasoning_delta=lambda delta: on_reasoning_delta(
                            f"{config.component_type}_gen", delta
                        ),
                    )
                else:
                    llm_result = await invoke_llm(llm, messages)
                reply_text = llm_result.content
                reasoning = llm_result.reasoning
                token_usage = llm_result.token_usage

        except Exception as e:
            logger.error(f"[{config.component_type}_gen] LLM 调用失败: {e}")
            model_error = classify_model_error(e)
            empty_value = [] if config.is_list else None
            diag = {
                    "label": config.label,
                    "rag_chars": rag_chars, "rag_ms": rag_ms, "rag_hits": rag_hits,
                    "rag_error": rag_error,
                    "error": model_error["user_message"],
                    "model_error": model_error,
                }
            return component_state_update(config, empty_value, gen_diag_key, diag)

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
            # 解析失败不立即判定为组件缺失：做一次非思考定向格式恢复，避免
            # 偶发格式抖动把整类组件静默丢弃（skeleton 节点已有同类恢复模式）。
            recovery_text, recovery_ms = await _recover_component_json(
                config,
                system_prompt,
                user_message,
                reply_text,
            )
            if config.is_list:
                fragments = extract_json_array(recovery_text)
            else:
                recovered_obj = extract_json_object(recovery_text)
                fragments = [recovered_obj] if recovered_obj is not None else []
            if not fragments or (not config.is_list and fragments[0] is None):
                logger.warning(f"[{config.component_type}_gen] 未能提取 JSON")
                empty_value = [] if config.is_list else None
                diag = {
                        "label": config.label,
                        "rag_chars": rag_chars, "rag_ms": rag_ms, "rag_hits": rag_hits,
                        "rag_error": rag_error,
                        "prompt_chars": prompt_chars,
                        "llm_chars": llm_chars, "llm_ms": llm_ms,
                        "token_usage": token_usage,
                        "reasoning_chars": reasoning_chars,
                        "fragment_count": 0,
                        "recovery_ms": recovery_ms,
                        "error": "JSON 提取失败",
                        # 显式标记格式故障：不是服务故障（不设 terminal，merge 不会
                        # 误判为模型服务中断），但 merge 可据此诊断，避免“静默消失”。
                        "json_parse_failed": True,
                        "model_error": {
                            "category": "json_parse",
                            "terminal_current_run": False,
                            "retryable": True,
                            "user_message": f"{config.label} 结构化输出解析失败",
                        },
                    }
                return component_state_update(config, empty_value, gen_diag_key, diag)

        # ── 5. 基本校验（类型 + 必填字段）──
        valid = validate_fragments(fragments, config)
        total_ms = int((_time.time() - t0) * 1000)

        logger.info(f"[{config.component_type}_gen] 完成: {len(valid)} 个 {config.label}, {total_ms}ms")

        value = valid if config.is_list else (valid[0] if valid else None)
        diag = {
                "label": config.label,
                "rag_chars": rag_chars, "rag_ms": rag_ms, "rag_hits": rag_hits,
                "rag_error": rag_error,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars, "llm_ms": llm_ms,
                "token_usage": token_usage,
                "reasoning_chars": reasoning_chars,
                "reasoning_preview": reasoning[:800] if reasoning else "",
                "fragment_count": len(valid),
                "total_ms": total_ms,
            }
        return component_state_update(config, value, gen_diag_key, diag)

    generator.__name__ = f"{config.component_type}_gen"
    return generator


# 校验器工厂（工具调用，有诊断输出，无 LLM）

def create_component_validator(config: ComponentConfig):
    """创建组件校验节点（只做工具校验，不调 LLM）"""

    async def validator(state: GenerationState) -> dict:
        t0 = _time.time()
        output_key = config.output_key
        val_diag_key = f"{config.component_type}_val_diag"

        fragments = state.get("component_fragments", {}).get(
            config.component_type,
            state.get(output_key),
        )
        if config.is_list:
            fragments = fragments if isinstance(fragments, list) else []
        else:
            fragments = [fragments] if isinstance(fragments, dict) else []

        if not fragments:
            logger.info(f"[{config.component_type}_val] 无片段，跳过校验")
            diag = {
                    "label": config.label,
                    "fragment_count": 0,
                    "validation_applied": False,
                    "validation_passed": True,
                }
            value = [] if config.is_list else None
            return component_state_update(config, value, val_diag_key, diag)

        logger.info(f"[{config.component_type}_val] 校验 {len(fragments)} 个 {config.label}")

        skeleton_blueprint = state.get("skeleton_blueprint", {})
        validated, fixed, validation_passed = validate_and_fix_with_tools(
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

        # 专用工具复检仍失败时，禁止把原始错误分片继续送入 merge。后续设计
        # 配额校验会把缺失构件交给回调重试，避免无效几何流到前端编译器。
        deliverable = validated if validation_passed else []
        value = deliverable if config.is_list else (deliverable[0] if deliverable else None)
        diag = {
                "label": config.label,
                "fragment_count": len(deliverable),
                "rejected_fragment_count": 0 if validation_passed else len(validated),
                "validation_applied": fixed,
                "validation_passed": validation_passed,
                "total_ms": total_ms,
            }
        return component_state_update(config, value, val_diag_key, diag)

    validator.__name__ = f"{config.component_type}_val"
    return validator


