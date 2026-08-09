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
from app.tools.spatial_tools import get_wall_bounding_box
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
    logger.info(f"[skeleton] RAG 完成（建筑类型知识）: {rag_chars} 字符, {rag_ms}ms")

    # ── 2. 构建 Prompt ──
    system_prompt = build_skeleton_prompt(spec_text)
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
    )

    # ── 4. 从 LLM 回复中提取组件建议 + DESIGN_BRIEF + Blueprint JSON ──
    suggested_components = _parse_components_from_reply(reply_text)
    design_brief = _parse_design_brief(reply_text)
    blueprint = extract_blueprint_from_text(reply_text)

    if not blueprint:
        logger.error("[skeleton] 未能提取 Blueprint JSON")
        return {
            "error": "骨架生成失败：LLM 未返回有效的 Blueprint JSON",
            "status": "failed",
            "skeleton_diag": {
                "rag_chars": rag_chars,
                "rag_ms": rag_ms,
                "prompt_chars": prompt_chars,
                "llm_chars": llm_chars,
                "llm_ms": llm_ms,
                "token_usage": token_usage,
                "error": "JSON 提取失败",
            },
        }

    # ── 5. 归一化和 Schema 校验 ──
    blueprint = normalize_blueprint_input(blueprint)
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

    # ── 6. 工具调用：计算墙体包围盒 ──
    bbox_result = {}
    try:
        bbox_fn = getattr(get_wall_bounding_box, "func", get_wall_bounding_box)
        bbox_result_str = bbox_fn(blueprint)
        logger.info("[skeleton] 墙体包围盒计算完成")
    except Exception as e:
        logger.error(f"[skeleton] 包围盒计算失败: {e}")

    # ── 7. 生成骨架摘要（仅几何轮廓，不含机械开口方案）──
    summary = _build_skeleton_summary(blueprint, design_brief)
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    total_ms = int((_time.time() - t0) * 1000)

    logger.info(f"[skeleton] 骨架生成完成: {len(elements)} 个构件, 建议组件: {suggested_components}, {total_ms}ms")
    if design_brief:
        quota = design_brief.get("component_quota", {})
        logger.info(f"[skeleton] 设计清单: {_json.dumps(quota, ensure_ascii=False, default=str)}")

    return {
        "skeleton_blueprint": blueprint,
        "skeleton_summary": summary,
        "wall_bounding_box": bbox_result,
        "suggested_components": suggested_components,
        "design_brief": design_brief,
        "skeleton_diag": {
            "rag_chars": rag_chars,
            "rag_ms": rag_ms,
            "prompt_chars": prompt_chars,
            "llm_chars": llm_chars,
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "reasoning_chars": reasoning_chars,
            "reasoning_preview": reasoning[:800] if reasoning else "",
            "element_count": len(elements),
            "total_ms": total_ms,
        },
    }


def _parse_design_brief(reply_text: str) -> dict | None:
    """从 LLM 回复中解析 DESIGN_BRIEF: JSON 段"""
    import re
    import json as _json

    m = re.search(r'DESIGN_BRIEF:\s*(\{[\s\S]*?\})\s*(?:$|\n\n)', reply_text)
    if not m:
        logger.warning("[skeleton] 未找到 DESIGN_BRIEF: 标记，骨架不会传递设计约束")
        return None

    try:
        brief = _json.loads(m.group(1))
        logger.info(f"[skeleton] 解析 DESIGN_BRIEF 成功: facade_plan={len(brief.get('facade_plan', {}))}面墙, "
                     f"component_quota={list(brief.get('component_quota', {}).keys())}")
        return brief
    except _json.JSONDecodeError as e:
        logger.warning(f"[skeleton] DESIGN_BRIEF JSON 解析失败: {e}")
        return None


def _parse_components_from_reply(reply_text: str) -> list[str]:
    """从 LLM 回复中解析 `_components: door, window, roof` 行"""
    import re
    valid_types = {"door", "window", "roof", "railing", "canopy",
                   "balcony", "light", "ramp", "bay_window", "cornice", "chimney", "stair"}

    m = re.search(r'_components:\s*(.+)', reply_text)
    if not m:
        return []

    raw = m.group(1).strip()
    components = []
    for token in re.split(r'[,，\s]+', raw):
        token = token.strip().lower()
        if token in valid_types and token not in components:
            components.append(token)

    return components


def _build_skeleton_summary(blueprint: dict, design_brief: dict | None = None) -> str:
    """生成骨架摘要供后续节点使用（几何轮廓 + 设计清单）"""
    import json as _json
    elements = blueprint.get("geometry", {}).get("elements", [])
    walls = [e for e in elements if e.get("type") == "wall"]
    floors = [e for e in elements if e.get("type") == "floor"]
    columns = [e for e in elements if e.get("type") == "column"]
    stairs = [e for e in elements if e.get("type") == "stair"]

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
        lines.append("  1. from[0] = 沿墙距离(m)，from[1] = 离地高度(门=0, 窗=0.9~1.1)")
        lines.append("  2. 门宽 0.9~1.2m，高 2.0~2.4m；窗宽 1.0~2.0m，高 1.2~1.8m")
        lines.append("  3. 开口边缘距墙角 ≥0.3m，相邻开口间距 ≥0.5m")
        lines.append("  4. from 第3个坐标(z或x)必须与 parentWall 的平面坐标一致（如背墙z=6则from[2]=6）")
        lines.append("  5. facade_plan 中 max_openings=0 的墙面不要放置任何开口")

    return "\n".join(lines)
