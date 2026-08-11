"""
通用组件节点工厂 —— gen（LLM生成）+ val（工具校验）两段式

用法:
    from .base_component_node import create_component_generator, create_component_validator
    from app.agent.component_registry import COMPONENT_REGISTRY

    door_gen = create_component_generator(COMPONENT_REGISTRY["door"])
    door_val = create_component_validator(COMPONENT_REGISTRY["door"])
"""
import asyncio
import json
import time as _time
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.prompts import build_component_prompt
from app.agent.model_client import create_llm
from app.agent.runtime_context import get_reasoning_callback
from app.agent.component_registry import ComponentConfig
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_array, extract_json_object

# 全局 LLM 并发信号量
_LLM_SEMAPHORE = asyncio.Semaphore(3)


def _component_state_update(
    config: ComponentConfig,
    value,
    diag_key: str,
    diag: dict,
) -> dict:
    """同时写入通用 State 与旧字段，便于渐进迁移现有调用方。"""
    return {
        config.output_key: value,
        diag_key: diag,
        "component_fragments": {config.component_type: value},
        "component_diagnostics": {diag_key: diag},
    }


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
        output_key = config.output_key
        gen_diag_key = f"{config.component_type}_gen_diag"

        logger.info(f"[{config.component_type}_gen] 开始生成 {config.label}")

        # ── 1. RAG 检索 ──
        rag_t0 = _time.time()
        queries = [
            SpecQuery(user_message, {"entity_type": config.entity_type}),
            SpecQuery(
                f"{user_message}\n{config.label}构件参数与位置规则：{config.component_type} 的推荐数量、位置、尺寸",
                {"doc_type": "component"},
            ),
        ]
        for extra_query in config.rag_extra_queries:
            queries.append(SpecQuery(extra_query, {"doc_type": "component"}))

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
            {"role": "user", "content": _build_user_message(config, skeleton_summary, design_brief)},
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
                                await on_reasoning_delta(f"{config.component_type}_gen", reasoning_delta)
                        if hasattr(chunk, "content") and chunk.content:
                            reply_text += chunk.content
                        # 捕获流式 usage（最终 chunk 带 usage 字段）
                        if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                            usage = chunk.response_metadata.get("usage")
                            if usage:
                                token_usage = {
                                    "input": usage.get("prompt_tokens", 0),
                                    "output": usage.get("completion_tokens", 0),
                                    "total": usage.get("total_tokens", 0),
                                }
                        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                            token_usage = {
                                "input": chunk.usage_metadata.get("input_tokens", 0),
                                "output": chunk.usage_metadata.get("output_tokens", 0),
                                "total": chunk.usage_metadata.get("total_tokens", 0),
                            }
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
            empty_value = [] if config.is_list else None
            diag = {
                    "label": config.label,
                    "rag_chars": rag_chars, "rag_ms": rag_ms, "rag_hits": rag_hits,
                    "rag_error": rag_error,
                    "error": str(e),
                }
            return _component_state_update(config, empty_value, gen_diag_key, diag)

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
                    "error": "JSON 提取失败",
                }
            return _component_state_update(config, empty_value, gen_diag_key, diag)

        # ── 5. 基本校验（类型 + 必填字段）──
        valid = _validate_fragments(fragments, config)
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
        return _component_state_update(config, value, gen_diag_key, diag)

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
            return _component_state_update(config, value, val_diag_key, diag)

        logger.info(f"[{config.component_type}_val] 校验 {len(fragments)} 个 {config.label}")

        skeleton_blueprint = state.get("skeleton_blueprint", {})
        validated, fixed, validation_passed = _validate_and_fix_with_tools(
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
        return _component_state_update(config, value, val_diag_key, diag)

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
        missing = [
            field
            for field in config.required_fields
            if _is_missing_required_value(frag, field)
        ]
        if missing:
            logger.warning(
                f"[{config.component_type}] 跳过 {frag.get('id', '?')}：缺少必填字段 {missing}"
            )
            continue
        valid.append(frag)
    return valid


def _is_missing_required_value(fragment: dict, field: str) -> bool:
    """必填字段允许合法的 ``False`` 和 ``0``，只拒绝真正缺失或空值。"""
    if field not in fragment or fragment[field] is None:
        return True
    value = fragment[field]
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return not value
    return False


def _validation_has_error(result) -> bool:
    """兼容现有文本工具与后续结构化校验结果。"""
    if isinstance(result, dict):
        if result.get("has_error") or result.get("status") == "error":
            return True
        if result.get("error_count", 0):
            return True
        errors = result.get("errors")
        if isinstance(errors, (list, tuple, dict, set)) and errors:
            return True
    if getattr(result, "has_error", False):
        return True
    return "❌" in str(result)


def _build_user_message(config: ComponentConfig, skeleton_summary: str = "", design_brief: dict | None = None) -> str:
    """构建发给 LLM 的用户消息"""
    label = config.label
    # 从设计清单提取当前组件的配额约束
    quota_note = ""
    if design_brief:
        quota = design_brief.get("component_quota", {}).get(config.component_type, {})
        if quota:
            min_n = quota.get("min", "?")
            max_n = quota.get("max", "?")
            note = quota.get("note", "")
            quota_note = f"，精确数量范围: {min_n}~{max_n} 个 ({note})"

    if config.is_list:
        return (
            f"用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】和【立面开口方案 / 构件配额】"
            f"生成**合适数量**的 {label} 组件{quota_note}。\n\n"
            f"重要：请仔细阅读 facade_plan（立面开口方案），严格按照每面墙的 max_openings 和 intent 生成。"
            f"max_openings=0 的墙必须留空。\n\n"
            f"只输出 JSON 数组，不要其他文字。"
        )
    else:
        return (
            f"用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】"
            f"生成 {label} 构件。\n\n"
            f"只输出单个 JSON 对象，不要数组，不要其他文字。"
        )


def _validate_and_fix_with_tools(
    fragments: list[dict],
    component_type: str,
    skeleton_blueprint: dict,
    is_element: bool
) -> tuple[list[dict], bool, bool]:
    """使用专用工具校验并修复组件"""
    if not fragments:
        return [], False, True

    try:
        from app.tools.component_tools import validate_component, fix_component
    except ImportError:
        logger.warning(f"[{component_type}] 组件工具未找到，跳过校验修复")
        return fragments, False, False

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

    if _validation_has_error(validation_result):
        logger.warning(f"[{component_type}_val] 检测到错误，自动修复中...")
        fix_result = fix_component(component_type, temp_blueprint)
        logger.info(f"[{component_type}_val] 修复结果:\n{fix_result}")

        if is_element:
            fixed_fragments = temp_blueprint["geometry"]["elements"][-len(fragments):]
        else:
            fixed_fragments = temp_blueprint["geometry"]["components"][-len(fragments):]

        recheck_result = validate_component(component_type, temp_blueprint)
        recheck_text = str(recheck_result)
        if _validation_has_error(recheck_result):
            logger.warning(
                f"[{component_type}] 工具修复后复检仍未通过: {recheck_text}"
            )
        return fixed_fragments, True, not _validation_has_error(recheck_result)

    return fragments, False, True
