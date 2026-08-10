"""
Layer 0: 骨架生成节点

输入: user_message
输出: skeleton_blueprint, skeleton_summary, wall_bounding_box, skeleton_diag
"""
import time as _time
import json
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.prompts import build_skeleton_prompt
from app.agent.model_client import create_llm
from app.spec.loader import SpecQuery
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

from app.services.agent_service import agent_service


async def skeleton_generator(state: GenerationState) -> dict:
    """生成建筑骨架（walls + floors + columns + beams + stair）并输出设计清单"""
    t0 = _time.time()
    user_message = state["user_message"]
    thinking_mode = state.get("thinking_mode", False)
    on_reasoning_delta = state.get("on_reasoning_delta")
    architecture_plan = state.get("architecture_plan")

    logger.info(f"[skeleton] 开始生成骨架，用户消息: {user_message[:100]}, 思考模式: {thinking_mode}")

    # ── 1. RAG 检索（专注建筑类型知识）──
    rag_t0 = _time.time()

    queries = [
        # 主查询：建筑类型特征（如"欧式别墅"、"中式庭院"）
        SpecQuery(user_message, {"doc_type": "building_type"}),
        # 补充：建筑配方和结构组件通用规范
        SpecQuery(user_message, {"doc_type": "recipe"}),
        SpecQuery("墙体 楼板 柱子 梁", {"entity_type": "structural_component"}),
    ]

    spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
    rag_ms = int((_time.time() - rag_t0) * 1000)
    rag_chars = len(spec_text)
    rag_hits = [
        {
            "source": hit.metadata.get("source", "?"),
            "heading": hit.metadata.get("heading", "?"),
            "doc_type": hit.metadata.get("doc_type", "?"),
            "entity_type": hit.metadata.get("entity_type", "?"),
        }
        for hit in getattr(agent_service.spec_loader, "last_results", [])
    ]
    logger.info(
        f"[skeleton] RAG 完成（建筑类型知识）: {rag_chars} 字符, {rag_ms}ms, "
        f"hits={json.dumps(rag_hits, ensure_ascii=False, default=str)}"
    )

    # ── 2. 构建 Prompt ──
    system_prompt = build_skeleton_prompt(spec_text, architecture_plan)
    prompt_chars = len(system_prompt)

    # ── 3. LLM 调用（流式或非流式）──
    use_streaming = thinking_mode and on_reasoning_delta is not None
    llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    llm_t0 = _time.time()
    reply_text = ""
    reasoning = ""
    token_usage = None
    finish_reason = None
    
    try:
        if use_streaming:
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "additional_kwargs"):
                    reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
                    if reasoning_delta:
                        reasoning += reasoning_delta
                        await on_reasoning_delta("skeleton", reasoning_delta)
                if hasattr(chunk, "content") and chunk.content:
                    reply_text += chunk.content
                if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                    finish_reason = (
                        chunk.response_metadata.get("finish_reason")
                        or chunk.response_metadata.get("stop_reason")
                        or finish_reason
                    )
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
            
            logger.info(f"[skeleton] LLM 流式完成: {len(reply_text)} 字符")
        else:
            response = await llm.ainvoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)
            if hasattr(response, "additional_kwargs"):
                reasoning = response.additional_kwargs.get("reasoning_content", "") or ""
            if not reasoning and hasattr(response, "response_metadata"):
                reasoning = response.response_metadata.get("reasoning_content", "") or ""
            if hasattr(response, "response_metadata"):
                finish_reason = (
                    response.response_metadata.get("finish_reason")
                    or response.response_metadata.get("stop_reason")
                )
                usage = response.response_metadata.get("token_usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("prompt_tokens", 0),
                        "output": usage.get("completion_tokens", 0),
                        "total": usage.get("total_tokens", 0),
                    }
    
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

    llm_ms = int((_time.time() - llm_t0) * 1000)
    llm_chars = len(reply_text)
    reasoning_chars = len(reasoning)
    
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
        else _parse_components_from_reply(reply_text)
    )
    design_brief = None if architecture_plan else _parse_design_brief(reply_text)
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
                suggested_components or _parse_components_from_reply(reasoning)
            )
            if not architecture_plan:
                design_brief = design_brief or _parse_design_brief(reasoning)
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
        token_usage = _merge_token_usage(
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
    schema_issues = validate_blueprint_schema(blueprint)

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
        from app.agent.spatial_invariants import build_spatial_invariants

        bbox_result = compute_wall_bounding_box(blueprint)
        spatial_invariants = build_spatial_invariants(blueprint, bbox_result)
        logger.info("[skeleton] 墙体包围盒计算完成")
    except Exception as e:
        logger.error(f"[skeleton] 包围盒计算失败: {e}")

    # ── 6.5 把抽象轴网解析为真实 wall id 和精确局部门窗槽位 ──
    if isinstance(architecture_plan, dict):
        from app.agent.architecture_plan import resolve_facade_layout

        design_brief = resolve_facade_layout(blueprint, architecture_plan)
        logger.info(
            f"[skeleton] 立面槽位解析完成: {len(design_brief.get('opening_slots', []))} 个槽位"
        )

    # ── 7. 生成骨架摘要（几何轮廓 + 确定性开口方案）──
    summary = _build_skeleton_summary(blueprint, design_brief)
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    total_ms = int((_time.time() - t0) * 1000)

    logger.info(f"[skeleton] 骨架生成完成: {len(elements)} 个构件, 建议组件: {suggested_components}, {total_ms}ms")
    if design_brief:
        quota = design_brief.get("component_quota", {})
        logger.info(f"[skeleton] 设计清单: {json.dumps(quota, ensure_ascii=False, default=str)}")

    return {
        "skeleton_blueprint": blueprint,
        "skeleton_summary": summary,
        "wall_bounding_box": bbox_result,
        "spatial_invariants": spatial_invariants,
        "suggested_components": suggested_components,
        "design_brief": design_brief,
        "skeleton_diag": {
            "rag_chars": rag_chars,
            "rag_ms": rag_ms,
            "rag_hits": rag_hits,
            "prompt_chars": prompt_chars,
            "llm_chars": llm_chars,
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "finish_reason": finish_reason,
            "recovery": recovery_diag,
            "reasoning_chars": reasoning_chars,
            "reasoning_preview": reasoning[:800] if reasoning else "",
            "reasoning_fallback": used_reasoning_fallback,
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
    brief_text = json.dumps(design_brief or {}, ensure_ascii=False)
    # Blueprint 在原提示词中位于 DESIGN_BRIEF 之前，保留失败回复的前部最有机会
    # 包含可修复的几何；限制长度避免把一次恢复再次膨胀为长上下文任务。
    failed_excerpt = failed_reply[:12000]
    recovery_instruction = """

# Blueprint 格式恢复（覆盖前面的输出格式要求）

这是一次失败恢复，不要重新解释设计过程。你只能输出一个严格合法的 JSON 对象：
- 顶层必须直接包含 meta、geometry、materials；
- geometry.elements 必须包含完整建筑骨架；
- geometry.components 必须是空数组；
- 不要输出 `_components`、DESIGN_BRIEF、Markdown 围栏、注释或额外文本；
- 如果上一轮 Blueprint 缺失或 JSON 不完整，根据原始需求和设计清单补全。
"""
    recovery_user = f"""原始用户需求：
{user_message}

已解析设计清单：
{brief_text}

上一轮无效输出（仅供修复，不要照抄其额外说明）：
{failed_excerpt}
"""

    try:
        response = await recovery_llm.ainvoke(
            [
                {"role": "system", "content": system_prompt + recovery_instruction},
                {"role": "user", "content": recovery_user},
            ]
        )
        recovery_text = response.content if hasattr(response, "content") else str(response)
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
        token_usage = None
        if usage:
            token_usage = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
        diag = {
            "attempted": True,
            "success": False,
            "llm_chars": len(recovery_text),
            "llm_ms": int((_time.time() - recovery_t0) * 1000),
            "token_usage": token_usage,
            "finish_reason": metadata.get("finish_reason") or metadata.get("stop_reason"),
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


def _merge_token_usage(primary: dict | None, recovery: dict | None) -> dict | None:
    """合并首次生成和格式恢复的 token 统计。"""
    if not primary and not recovery:
        return None
    primary = primary or {}
    recovery = recovery or {}
    return {
        key: primary.get(key, 0) + recovery.get(key, 0)
        for key in ("input", "output", "total")
    }


def _parse_design_brief(reply_text: str) -> dict | None:
    """从 LLM 回复中解析 DESIGN_BRIEF: JSON 段"""
    import re
    import json as _json

    decoder = _json.JSONDecoder()
    for marker in re.finditer(r'DESIGN_BRIEF:\s*', reply_text):
        tail = reply_text[marker.end():].lstrip()
        if not tail.startswith("{"):
            continue
        try:
            brief, _ = decoder.raw_decode(tail)
        except _json.JSONDecodeError:
            continue
        if not isinstance(brief, dict):
            continue
        if "facade_plan" not in brief and "component_quota" not in brief:
            continue
        logger.info(f"[skeleton] 解析 DESIGN_BRIEF 成功: facade_plan={len(brief.get('facade_plan', {}))}面墙, "
                    f"component_quota={list(brief.get('component_quota', {}).keys())}")
        return brief

    logger.warning("[skeleton] 未找到可解析的 DESIGN_BRIEF，骨架不会传递设计约束")
    return None


def _parse_components_from_reply(reply_text: str) -> list[str]:
    """从 LLM 回复中解析 `_components: door, window, roof` 行"""
    import re
    valid_types = {"door", "window", "roof", "railing", "canopy",
                   "balcony", "light", "ramp", "bay_window", "cornice", "chimney", "stair"}

    for match in re.finditer(r'_components:\s*(.+)', reply_text):
        raw = match.group(1).strip()
        first_token = re.split(r'[,，\s]+', raw, maxsplit=1)[0].strip().lower()
        # 只接受标记后直接跟组件 ID 的正式行；跳过“_components: 格式要求”
        # 或“_components: 列表（...）”等思考过程中的提及。
        if first_token not in valid_types:
            continue
        components = []
        for token in re.split(r'[,，\s]+', raw):
            token = token.strip().lower()
            if token in valid_types and token not in components:
                components.append(token)
        if components:
            return components
    return []


def _build_skeleton_summary(blueprint: dict, design_brief: dict | None = None) -> str:
    """生成骨架摘要供后续节点使用（几何轮廓 + 设计清单）"""
    import json as _json
    elements = blueprint.get("geometry", {}).get("elements", [])
    walls = [e for e in elements if e.get("type") == "wall"]
    floors = [e for e in elements if e.get("type") == "floor"]
    columns = [e for e in elements if e.get("type") == "column"]
    stairs = [e for e in elements if e.get("type") == "stair"]
    materials = blueprint.get("materials", {})

    lines = [f"当前场景包含 {len(elements)} 个结构元素："]
    
    # 墙体详细信息
    lines.append("\n【墙体详情】用于门窗定位：")
    for wall in walls:
        wid = wall.get("id", "?")
        frm = wall.get("from", [0, 0, 0])
        to = wall.get("to", [0, 0, 0])
        length = ((to[0] - frm[0])**2 + (to[2] - frm[2])**2)**0.5
        height = wall.get("height", to[1] - frm[1])
        thickness = wall.get("thickness", 0.3)
        
        dx = to[0] - frm[0]
        dz = to[2] - frm[2]
        if abs(dx) > abs(dz):
            direction = "东西向" if dx > 0 else "西东向"
        else:
            direction = "南北向" if dz > 0 else "北南向"
        
        lines.append(
            f"  - [{wid}] {direction}墙: from=[{frm[0]:.2f}, {frm[1]:.2f}, {frm[2]:.2f}] "
            f"to=[{to[0]:.2f}, {to[1]:.2f}, {to[2]:.2f}], "
            f"长度={length:.2f}m, 高度={height:.2f}m, 厚度={thickness:.2f}m"
        )

    # 楼板信息
    if floors:
        lines.append("\n【楼板】：")
        for floor in floors:
            fid = floor.get("id", "?")
            frm = floor.get("from", [0, 0, 0])
            to = floor.get("to", [0, 0, 0])
            if to:
                width = abs(to[0] - frm[0])
                depth = abs(to[2] - frm[2])
                lines.append(f"  - [{fid}] {width:.2f}×{depth:.2f}m, 标高={frm[1]:.2f}m")

    # 柱子信息
    if columns:
        lines.append(f"\n【柱子】：{len(columns)} 个")
        for col in columns[:4]:
            cid = col.get("id", "?")
            base = col.get("base", [0, 0, 0])
            height = col.get("height", 3.0)
            lines.append(f"  - [{cid}] 位置=[{base[0]:.2f}, {base[2]:.2f}], 高度={height:.2f}m")

    # 楼梯信息
    if stairs:
        lines.append(f"\n【楼梯】：{len(stairs)} 个")
        for s in stairs:
            sid = s.get("id", "?")
            frm = s.get("from", [0, 0, 0])
            to = s.get("to", [0, 0, 0])
            width = s.get("width", 1.0)
            lines.append(f"  - [{sid}] from={frm} to={to}, width={width:.2f}m")

    if materials:
        material_names = ", ".join(sorted(materials))
        lines.append(
            f"\n【可用材质 ID】：{material_names}\n"
            "组件的 material/frameMaterial/leafMaterial/glassMaterial 只能引用以上 ID。"
        )

    # ── 设计清单（来自 DESIGN_BRIEF）──
    if design_brief:
        lines.append("\n【设计清单 — 来自骨架设计规划】：")
        
        quota = design_brief.get("component_quota", {})
        if quota:
            lines.append("\n构件配额（必须遵守）：")
            for comp_type, q in quota.items():
                min_n = q.get("min", "?")
                max_n = q.get("max", "?")
                note = q.get("note", "")
                roof_type = q.get("type", "")
                if roof_type:
                    note = f"类型={roof_type}, " + note
                lines.append(f"  - {comp_type}: {min_n}~{max_n} 个 ({note})")

        fplan = design_brief.get("facade_plan", {})
        if fplan:
            lines.append("\n立面开口方案（严格遵照）：")
            for wall_id, plan in fplan.items():
                facing = plan.get("facing", "?")
                intent = plan.get("intent", "")
                max_o = plan.get("max_openings", "")
                is_main = "主立面" if plan.get("is_main_facade") else "非主立面"
                lines.append(f"  - [{wall_id}] ({facing}, {is_main}): {intent}, 最多 {max_o} 个开口")

        rag_ref = design_brief.get("rag_reference", "")
        if rag_ref:
            lines.append(f"\nRAG 参考模板: {rag_ref}")

    # ── 门/窗定位基本规则 ──
    if walls:
        lines.append("\n【门/窗定位基本规则】：")
        lines.append(
            "  1. from[0] = 沿墙距离(m)；from[1] = 底部世界Y："
            "门=父墙底Y，窗=父墙底Y+0.9~1.1m"
        )
        lines.append("  2. 门宽 0.9~1.2m，高 2.0~2.4m；窗宽 1.0~2.0m，高 1.2~1.8m")
        lines.append("  3. 开口边缘距墙角 ≥0.3m，相邻开口间距 ≥0.5m")
        lines.append(
            "  4. from=[沿墙距离, 底部世界Y, 局部法向偏移]；from[2] 不是世界 X/Z。"
            "门窗通常必须为 0（即使背墙世界 z=6，仍写 from[2]=0）"
        )
        lines.append("  5. facade_plan 中 max_openings=0 的墙面不要放置任何开口")

    return "\n".join(lines)
