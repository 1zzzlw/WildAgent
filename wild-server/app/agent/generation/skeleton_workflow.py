"""
Layer 0: 骨架生成节点

输入: user_message
输出: skeleton_blueprint, skeleton_summary, wall_bounding_box, skeleton_diag
"""
import time as _time
import json
from loguru import logger

from app.agent.state import GenerationState
from app.agent.generation.architecture import (
    build_deterministic_skeleton,
    evaluate_skeleton_complexity,
)
from app.agent.generation.material_plan import (
    apply_resolved_material_plan,
    material_role_specs,
)
from app.agent.generation.objects import build_object_skeleton, object_design_brief
from app.agent.generation.skeleton_output import (
    build_skeleton_summary,
    parse_components_from_reply,
    parse_design_brief,
)
from app.agent.prompts import (
    build_blueprint_recovery_messages,
    build_skeleton_prompt,
)
from app.llm.client import create_llm
from app.llm.invocation import (
    invoke_llm,
    merge_token_usage,
    stream_llm,
)
from app.agent.runtime import get_reasoning_callback
from app.spec.loader import SpecQuery
from app.agent.knowledge.policy import plan_knowledge_query
from app.tools.spatial_tools import (
    fix_element_dimensions,
    fix_material_references,
    validate_element_dimensions,
    validate_reference_integrity,
)
from app.utils.blueprint_parser import (
    extract_blueprint_from_text,
    normalize_blueprint_input,
    validate_blueprint_schema,
)

async def skeleton_generator(state: GenerationState) -> dict:
    """把已批准方案确定性编译为骨架，并输出后续计划所需设计清单。"""
    t0 = _time.time()
    user_message = state["user_message"]
    thinking_mode = state.get("thinking_mode", False)
    on_reasoning_delta = get_reasoning_callback()
    architecture_plan = state.get("architecture_plan")
    material_plan = state.get("material_plan")
    deterministic_primary = isinstance(architecture_plan, dict) and bool(architecture_plan)
    # 物件场景走"空几何骨架"：没有墙、楼板、层高，也就没有"复杂度达标"这件事。
    # 判据与方案层、材质层共用同一个 `is_object_plan`，不在这里另判一次。
    from app.design.resolver import is_object_plan

    object_scene = is_object_plan(architecture_plan)
    role_specs = material_role_specs(architecture_plan)

    logger.info(f"[skeleton] 开始生成骨架，用户消息: {user_message[:100]}, 思考模式: {thinking_mode}")

    if deterministic_primary and on_reasoning_delta is not None:
        await on_reasoning_delta(
            "skeleton:progress",
            "已收到批准的物件方案，正在建立物件场景骨架……\n"
            if object_scene
            else "已收到批准的结构化方案，正在确定性编译墙、楼板、柱梁与楼梯……\n",
        )

    # ── 1. 仅兼容无结构化方案的旧入口；正常生成链不再二次检索和重新设计 ──
    rag_t0 = _time.time()
    rag_error = None
    spec_text = ""
    rag_hits = []
    if not deterministic_primary:
        from app.services.agent_service import agent_service

        selected_query = plan_knowledge_query(user_message, architecture_plan)
        queries = [
            SpecQuery("墙、楼板、楼梯与屋顶的已实现组装关系", {"doc_type": "recipe", "entity_name": "supported_assembly_relations"}),
            SpecQuery(selected_query, {"doc_type": "recipe", "knowledge_role": "relation"}),
            SpecQuery("墙体 楼板 柱子 梁", {"doc_type": "component", "entity_type": "structural_component"}),
            SpecQuery("墙体标高与宿主范围", {"doc_type": "component", "entity_type": "wall"}),
        ]
        try:
            spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
        except Exception as exc:
            rag_error = str(exc)
            logger.warning(f"[skeleton] RAG 检索失败，继续使用方案约束: {exc}")
        rag_hits = [] if rag_error else [
            {
                "source": hit.metadata.get("source", "?"),
                "heading": hit.metadata.get("heading", "?"),
                "doc_type": hit.metadata.get("doc_type", "?"),
                "entity_type": hit.metadata.get("entity_type", "?"),
            }
            for hit in getattr(agent_service.spec_loader, "last_results", [])
        ]
    else:
        logger.info("[skeleton] 使用已批准方案的确定性编译路径，跳过 RAG 与骨架 LLM")
    if rag_error:
        spec_text = ""
    rag_ms = int((_time.time() - rag_t0) * 1000)
    rag_chars = len(spec_text)
    logger.info(
        f"[skeleton] RAG 完成（能力与关系知识）: {rag_chars} 字符, {rag_ms}ms, "
        f"hits={json.dumps(rag_hits, ensure_ascii=False, default=str)}"
    )

    # ── 2. 构建 Prompt ──
    system_prompt = (
        "" if deterministic_primary
        else build_skeleton_prompt(spec_text, architecture_plan, material_plan)
    )
    prompt_chars = len(system_prompt)

    # ── 3. 正常链确定性编译；只有旧入口没有 architecture_plan 时才走模型兼容路径 ──
    llm_t0 = _time.time()
    reply_text = ""
    reasoning = ""
    token_usage = None
    finish_reason = None
    blueprint = None
    if deterministic_primary:
        blueprint = (
            build_object_skeleton(architecture_plan, user_message)
            if object_scene
            else build_deterministic_skeleton(architecture_plan, user_message)
        )
    deterministic_fallback_reason = None
    complexity_diag = None
    use_streaming = thinking_mode and on_reasoning_delta is not None

    if not deterministic_primary:
        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        try:
            if use_streaming:
                llm_result = await stream_llm(
                    llm,
                    messages,
                    on_reasoning_delta=lambda delta: on_reasoning_delta("skeleton", delta),
                )
            else:
                llm_result = await invoke_llm(llm, messages)
            reply_text = llm_result.content
            reasoning = llm_result.reasoning
            token_usage = llm_result.token_usage
            finish_reason = llm_result.finish_reason
        except Exception as e:
            logger.error(f"[skeleton] LLM 调用失败: {e}")
            return {
                "error": f"骨架生成失败: {str(e)}",
                "status": "failed",
                "skeleton_diag": {
                    "rag_chars": rag_chars,
                    "rag_ms": rag_ms,
                    "error": str(e),
                },
            }

    llm_ms = 0 if deterministic_primary else int((_time.time() - llm_t0) * 1000)
    llm_chars = len(reply_text)
    reasoning_chars = len(reasoning)
    
    if not deterministic_primary:
        logger.info(
            f"[skeleton] LLM 回复: {llm_chars} 字符, {llm_ms}ms"
            + (f", thinking={reasoning_chars}字符" if reasoning_chars else "")
            + (f", tokens={token_usage['total']}" if token_usage else "")
            + (f", finish_reason={finish_reason}" if finish_reason else "")
        )

    # ── 4. 从 LLM 回复中提取组件建议 + DESIGN_BRIEF + Blueprint JSON ──
    suggested_components = (
        list(architecture_plan.get("required_components", []))
        if isinstance(architecture_plan, dict)
        else parse_components_from_reply(reply_text)
    )
    design_brief = None if architecture_plan else parse_design_brief(reply_text)
    if blueprint is None:
        blueprint = extract_blueprint_from_text(reply_text)

    # 部分 OpenAI-compatible 模型在流式思考模式下会把最终结构化输出放进
    # reasoning_content，而 content 为空。只在正常 content 提取失败时回退，
    # 避免“界面看得到 JSON、服务端却判定 Blueprint 缺失”。
    used_reasoning_fallback = False
    if not blueprint and reasoning:
        blueprint = extract_blueprint_from_text(reasoning)
        if blueprint:
            used_reasoning_fallback = True
            suggested_components = (
                suggested_components or parse_components_from_reply(reasoning)
            )
            if not architecture_plan:
                design_brief = design_brief or parse_design_brief(reasoning)
            logger.warning("[skeleton] 最终 Blueprint 来自 reasoning_content 兼容回退")

    # Qwen/GLM 等混合思考模型偶尔会正确输出 DESIGN_BRIEF，却漏掉、截断或包装
    # Blueprint。先由确定性解析器处理常见包装；仍失败时只补做一次非思考调用，
    # 要求返回单一 JSON 对象，避免整条 LangGraph 在昂贵的首轮调用后直接短路。
    recovery_diag = None
    if not blueprint:
        has_meta_marker = '"meta"' in reply_text
        has_geometry_marker = '"geometry"' in reply_text
        logger.warning(
            "[skeleton] Blueprint 首次提取失败: "
            f"meta_marker={has_meta_marker}, "
            f"geometry_marker={has_geometry_marker}, "
            f"code_fence={'```' in reply_text}, finish_reason={finish_reason}"
        )
        if on_reasoning_delta is not None:
            await on_reasoning_delta(
                "skeleton",
                "\nBlueprint 结构化输出缺失或格式无效，正在进行一次定向格式恢复...\n",
            )
        blueprint, recovery_diag = await _recover_blueprint_json(
            system_prompt=system_prompt,
            user_message=user_message,
            failed_reply=reply_text,
            design_brief=design_brief,
        )
        token_usage = merge_token_usage(
            token_usage,
            recovery_diag.get("token_usage"),
        )
        if blueprint:
            logger.warning(
                "[skeleton] Blueprint 定向格式恢复成功: "
                f"{recovery_diag.get('llm_chars', 0)} 字符, "
                f"{recovery_diag.get('llm_ms', 0)}ms"
            )

    if not blueprint:
        if isinstance(architecture_plan, dict):
            logger.error("[skeleton] 模型格式恢复失败，使用确定性骨架回退")
            blueprint = build_deterministic_skeleton(architecture_plan, user_message)
            deterministic_fallback_reason = "模型未返回有效 Blueprint，格式恢复仍未成功"
        else:
            logger.error("[skeleton] 未能提取 Blueprint JSON，定向格式恢复也未成功")
            return {
                "error": "骨架生成失败：模型未返回有效的 Blueprint JSON，自动格式恢复仍未成功",
                "status": "failed",
                "skeleton_diag": {
                    "rag_chars": rag_chars,
                    "rag_ms": rag_ms,
                    "prompt_chars": prompt_chars,
                    "llm_chars": llm_chars,
                    "llm_ms": llm_ms,
                    "token_usage": token_usage,
                    "finish_reason": finish_reason,
                    "recovery": recovery_diag,
                    "error": "JSON 提取失败",
                },
            }

    # ── 5. 归一化和 Schema 校验 ──
    blueprint = normalize_blueprint_input(blueprint)
    schema_issues = validate_blueprint_schema(blueprint, allow_empty_geometry=object_scene)
    if not schema_issues:
        blueprint = apply_resolved_material_plan(blueprint, material_plan, role_specs=role_specs)
    floor_coordinates = {
        element.get("id", "?"): {
            "from": element.get("from"),
            "to": element.get("to"),
        }
        for element in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(element, dict) and element.get("type") == "floor"
    }
    if floor_coordinates:
        logger.info(
            "[skeleton] 楼板坐标规范化结果: "
            + json.dumps(floor_coordinates, ensure_ascii=False, default=str)
        )
    schema_issues = validate_blueprint_schema(blueprint, allow_empty_geometry=object_scene)

    if (
        schema_issues
        and isinstance(architecture_plan, dict)
        and not deterministic_primary
        and not deterministic_fallback_reason
    ):
        logger.warning("[skeleton] 模型骨架 Schema 无效，切换到确定性骨架回退")
        blueprint = apply_resolved_material_plan(
            normalize_blueprint_input(
                build_deterministic_skeleton(architecture_plan, user_message)
            ),
            material_plan,
            role_specs=role_specs,
        )
        deterministic_fallback_reason = "模型骨架未通过 Schema 预检"
        schema_issues = validate_blueprint_schema(blueprint, allow_empty_geometry=object_scene)

    # 复杂度评估只对建筑有意义：它衡量的是体量覆盖、逐层墙标高、竖向交通与
    # 结构构件数量。物件场景的 elements 本来就是空的（家具由 generate 条目后写入），
    # 拿建筑口径去评它必然"不达标"，会把一张合法的桌子判成失败。
    if not schema_issues and isinstance(architecture_plan, dict) and not object_scene:
        complexity_diag = evaluate_skeleton_complexity(blueprint, architecture_plan)
        if (
            not complexity_diag["meets_target"]
            and not deterministic_primary
            and not deterministic_fallback_reason
        ):
            logger.warning(
                "[skeleton] 模型骨架未满足结构与方案约束，切换到确定性骨架: "
                f"{json.dumps(complexity_diag, ensure_ascii=False, default=str)}"
            )
            if on_reasoning_delta is not None:
                await on_reasoning_delta(
                    "skeleton",
                    "\n模型骨架存在无效结构或未满足方案约束，正在依据已批准方案重建骨架...\n",
                )
            blueprint = apply_resolved_material_plan(
                normalize_blueprint_input(
                    build_deterministic_skeleton(architecture_plan, user_message)
                ),
                material_plan,
                role_specs=role_specs,
            )
            deterministic_fallback_reason = "模型骨架未满足结构与方案约束"
            schema_issues = validate_blueprint_schema(blueprint, allow_empty_geometry=object_scene)
            complexity_diag = evaluate_skeleton_complexity(blueprint, architecture_plan)

    if complexity_diag and not complexity_diag["meets_target"]:
        return {
            "error": "确定性骨架仍未满足结构与方案约束，停止派发组件",
            "status": "failed",
            "skeleton_diag": {"complexity": complexity_diag, "deterministic_fallback_reason": deterministic_fallback_reason},
        }

    if schema_issues:
        logger.warning(f"[skeleton] Schema 校验失败: {schema_issues[:3]}")
        return {
            "error": f"骨架结构预检未通过: {'; '.join(schema_issues[:3])}",
            "status": "failed",
            "skeleton_diag": {
                "rag_chars": rag_chars,
                "rag_ms": rag_ms,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars,
                "llm_ms": llm_ms,
                "token_usage": token_usage,
                "schema_issues": schema_issues[:5],
            },
        }

    floor_coordinates = {
        element.get("id", "?"): {
            "from": element.get("from"),
            "to": element.get("to"),
        }
        for element in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(element, dict) and element.get("type") == "floor"
    }

    # 模型偶尔把 wall.to[1] 写成与 from[1] 相同，导致墙高为 0。组件节点若继续
    # 使用这种骨架，门窗无论重试多少次都不可能落入父墙。派发组件前先确定性补全。
    dimension_fix_fn = getattr(fix_element_dimensions, "func", fix_element_dimensions)
    dimension_validate_fn = getattr(
        validate_element_dimensions,
        "func",
        validate_element_dimensions,
    )
    dimension_fix_output = dimension_fix_fn(blueprint)
    dimension_validation = dimension_validate_fn(blueprint)
    if "❌" in dimension_validation:
        logger.warning(f"[skeleton] 几何尺寸预检失败: {dimension_validation}")
        return {
            "error": f"骨架几何预检未通过: {dimension_validation}",
            "status": "failed",
            "skeleton_diag": {
                "rag_chars": rag_chars,
                "rag_ms": rag_ms,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars,
                "llm_ms": llm_ms,
                "token_usage": token_usage,
                "rag_hits": rag_hits,
                "floor_coordinates": floor_coordinates,
                "dimension_fix": dimension_fix_output,
                "dimension_validation": dimension_validation,
            },
        }

    material_fix_fn = getattr(fix_material_references, "func", fix_material_references)
    reference_validate_fn = getattr(
        validate_reference_integrity,
        "func",
        validate_reference_integrity,
    )
    material_fix_output = material_fix_fn(blueprint)
    reference_validation = reference_validate_fn(blueprint)
    if "❌" in reference_validation:
        logger.warning(f"[skeleton] 引用预检失败: {reference_validation}")
        return {
            "error": f"骨架引用预检未通过: {reference_validation}",
            "status": "failed",
            "skeleton_diag": {
                "rag_chars": rag_chars,
                "rag_ms": rag_ms,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars,
                "llm_ms": llm_ms,
                "token_usage": token_usage,
                "material_fix": material_fix_output,
                "reference_validation": reference_validation,
            },
        }

    # ── 6. 工具调用：计算墙体包围盒 ──
    bbox_result = {}
    spatial_invariants = {}
    try:
        from app.tools.spatial_tools import compute_wall_bounding_box
        from app.agent.generation.spatial_invariants import build_spatial_invariants

        bbox_result = compute_wall_bounding_box(blueprint)
        spatial_invariants = build_spatial_invariants(blueprint, bbox_result)
        logger.info("[skeleton] 墙体包围盒计算完成")
    except Exception as e:
        logger.error(f"[skeleton] 包围盒计算失败: {e}")

    # ── 6.5 把抽象轴网解析为真实 wall id 和精确局部门窗槽位 ──
    # 物件场景没有立面轴网，也就没有槽位可解析：设计清单直接由方案里的
    # component_quota 生成（家具的数量靠 quota 表达，不靠槽位）。
    if object_scene:
        design_brief = object_design_brief(architecture_plan)
        logger.info(
            f"[skeleton] 物件设计清单: {json.dumps(design_brief.get('component_quota', {}), ensure_ascii=False, default=str)}"
        )
    elif isinstance(architecture_plan, dict):
        from app.agent.generation.architecture import resolve_facade_layout

        design_brief = resolve_facade_layout(blueprint, architecture_plan)
        logger.info(
            f"[skeleton] 立面槽位解析完成: {len(design_brief.get('opening_slots', []))} 个槽位"
        )

    # ── 7. 生成骨架摘要（几何轮廓 + 确定性开口方案）──
    summary = build_skeleton_summary(blueprint, design_brief)
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    total_ms = int((_time.time() - t0) * 1000)

    logger.info(f"[skeleton] 骨架生成完成: {len(elements)} 个构件, 建议组件: {suggested_components}, {total_ms}ms")
    if design_brief:
        quota = design_brief.get("component_quota", {})
        logger.info(f"[skeleton] 设计清单: {json.dumps(quota, ensure_ascii=False, default=str)}")
    if deterministic_primary and on_reasoning_delta is not None:
        await on_reasoning_delta(
            "skeleton:progress",
            (
                "物件场景骨架已建立"
                f"（待生成构件：{json.dumps((design_brief or {}).get('component_quota', {}), ensure_ascii=False, default=str)}）；"
                "下一节点将直接展开执行计划。\n"
                if object_scene
                else f"骨架编译完成：{len(elements)} 个结构元素、"
                     f"{len((design_brief or {}).get('opening_slots', []))} 个组件槽位；"
                     "下一节点将直接展开执行计划。\n"
            ),
        )

    return {
        "skeleton_blueprint": blueprint,
        "skeleton_summary": summary,
        "wall_bounding_box": bbox_result,
        "spatial_invariants": spatial_invariants,
        "suggested_components": suggested_components,
        "design_brief": design_brief,
        "skeleton_diag": {
            "source": "deterministic" if deterministic_primary else "llm",
            "rag_chars": rag_chars,
            "rag_ms": rag_ms,
            "rag_hits": rag_hits,
            "rag_error": rag_error,
            "prompt_chars": prompt_chars,
            "llm_chars": llm_chars,
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "finish_reason": finish_reason,
            "recovery": recovery_diag,
            "reasoning_chars": reasoning_chars,
            "reasoning_preview": reasoning[:800] if reasoning else "",
            "reasoning_fallback": used_reasoning_fallback,
            "deterministic_fallback": bool(deterministic_fallback_reason),
            "deterministic_fallback_reason": deterministic_fallback_reason,
            "complexity": complexity_diag,
            "element_count": len(elements),
            "opening_slot_count": len((design_brief or {}).get("opening_slots", [])),
            "floor_coordinates": floor_coordinates,
            "dimension_fix": dimension_fix_output,
            "material_fix": material_fix_output,
            "total_ms": total_ms,
        },
    }


async def _recover_blueprint_json(
    *,
    system_prompt: str,
    user_message: str,
    failed_reply: str,
    design_brief: dict | None,
) -> tuple[dict | None, dict]:
    """用一次非思考调用把缺失或无效的骨架回复恢复为单一 Blueprint JSON。"""
    recovery_t0 = _time.time()
    recovery_llm = create_llm(enable_thinking=False, streaming=False)
    try:
        llm_result = await invoke_llm(
            recovery_llm,
            build_blueprint_recovery_messages(
                system_prompt=system_prompt,
                user_message=user_message,
                failed_reply=failed_reply,
                design_brief=design_brief,
            ),
        )
        recovery_text = llm_result.content
        diag = {
            "attempted": True,
            "success": False,
            "llm_chars": len(recovery_text),
            "llm_ms": int((_time.time() - recovery_t0) * 1000),
            "token_usage": llm_result.token_usage,
            "finish_reason": llm_result.finish_reason,
        }
        blueprint = extract_blueprint_from_text(recovery_text)
        diag["success"] = blueprint is not None
        return blueprint, diag
    except Exception as exc:
        logger.error(f"[skeleton] Blueprint 定向格式恢复调用失败: {exc}")
        return None, {
            "attempted": True,
            "success": False,
            "llm_ms": int((_time.time() - recovery_t0) * 1000),
            "error": str(exc),
        }


