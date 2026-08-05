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
    """生成建筑骨架（walls + floors + columns + beams）"""
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
    # 如果需要思考且有回调，使用流式；否则非流式
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
            # 流式调用：逐 chunk 收集 content 和 reasoning_content
            async for chunk in llm.astream(messages):
                # 提取思考内容
                if hasattr(chunk, "additional_kwargs"):
                    reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
                    if reasoning_delta:
                        reasoning += reasoning_delta
                        # 实时推送给前端
                        await on_reasoning_delta("skeleton", reasoning_delta)
                
                # 收集正文内容
                if hasattr(chunk, "content") and chunk.content:
                    reply_text += chunk.content
            
            logger.info(f"[skeleton] LLM 流式完成: {len(reply_text)} 字符")
        else:
            # 非流式调用
            response = await llm.ainvoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)
            
            # 提取模型思考内容（多个来源都尝试）
            if hasattr(response, "additional_kwargs"):
                reasoning = response.additional_kwargs.get("reasoning_content", "") or ""
            if not reasoning and hasattr(response, "response_metadata"):
                reasoning = response.response_metadata.get("reasoning_content", "") or ""
            
            # 提取 token 用量
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

    # ── 4. 从 LLM 回复中提取组件建议 + Blueprint JSON ──
    suggested_components = _parse_components_from_reply(reply_text)
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

    # ── 7. 生成骨架摘要 ──
    summary = _build_skeleton_summary(blueprint)
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    total_ms = int((_time.time() - t0) * 1000)

    logger.info(f"[skeleton] 骨架生成完成: {len(elements)} 个构件, 建议组件: {suggested_components}, {total_ms}ms")

    return {
        "skeleton_blueprint": blueprint,
        "skeleton_summary": summary,
        "wall_bounding_box": bbox_result,
        "suggested_components": suggested_components,  # ← 新增：建议的组件列表
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


def _parse_components_from_reply(reply_text: str) -> list[str]:
    """从 LLM 回复中解析 `_components: door, window, roof` 行

    AI 自由判断用户需求需要哪些组件。未匹配到 _components: 时用关键词 fallback。
    """
    import re
    # 支持所有可用组件类型
    valid_types = {"door", "window", "roof", "railing", "canopy",
                   "balcony", "light", "ramp", "bay_window", "cornice", "chimney"}

    m = re.search(r'_components:\s*(.+)', reply_text)
    if not m:
        # AI 没输出 _components: 标签 → 关键词 fallback
        # 这个 fallback 与 graph.py 的 _keyword_fallback 呼应，
        # 但这里返回的是 skeleton 的 suggested_components，影响 graph 派发
        return []  # 返回空列表，让 graph.py 的 _dispatch_components 做关键词 fallback

    raw = m.group(1).strip()
    components = []
    for token in re.split(r'[,，\s]+', raw):
        token = token.strip().lower()
        if token in valid_types and token not in components:
            components.append(token)

    # AI 的选择就是最终结果，不再强制补全
    if not components:
        return []

    return components


def _build_skeleton_summary(blueprint: dict) -> str:
    """生成骨架摘要供后续节点使用（包含墙体详细信息用于门窗定位）"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    walls = [e for e in elements if e.get("type") == "wall"]
    floors = [e for e in elements if e.get("type") == "floor"]
    columns = [e for e in elements if e.get("type") == "column"]

    lines = [f"当前场景包含 {len(elements)} 个结构元素："]
    
    # 墙体详细信息（供门窗节点使用）
    lines.append("\n【墙体详情】用于门窗定位：")
    for wall in walls:
        wid = wall.get("id", "?")
        frm = wall.get("from", [0, 0, 0])
        to = wall.get("to", [0, 0, 0])
        length = ((to[0] - frm[0])**2 + (to[2] - frm[2])**2)**0.5
        height = wall.get("height", to[1] - frm[1])
        thickness = wall.get("thickness", 0.3)
        
        # 计算墙体方向
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

    # ── 门/窗定位指引 ──
    if walls:
        lines.append("\n【门/窗定位规则 — 请严格遵守】：")
        lines.append("  1. 门的 from[0] = 沿墙距离(米)，from[1] = 底部离地高度(门=0, 窗=0.9~1.1)")
        lines.append("  2. 门通常放在墙的中间或偏移 1/3 处，宽度 0.9~1.2m，高度 2.0~2.4m")
        lines.append("  3. 窗通常均匀分布，宽度 1.0~2.0m，高度 1.2~1.8m，间距 ≥0.5m")
        lines.append("  4. 同一面墙上的门+窗总数不宜超过 墙长/1.5 个")
        lines.append("  5. 门和窗之间的间距不少于 0.5m，避免重叠")
        lines.append("  6. 开口边缘距墙角 ≥0.3m（留出结构余量）")

        # 计算每面墙的建议开口数量和位置
        lines.append("\n【每面墙的建议开口方案】：")
        for wall in walls:
            wid = wall.get("id", "?")
            frm = wall.get("from", [0, 0, 0])
            to = wall.get("to", [0, 0, 0])
            length = ((to[0] - frm[0])**2 + (to[2] - frm[2])**2)**0.5

            # 估算该墙可容纳的开口数
            max_openings = max(1, int(length / 1.8))
            suggested_count = min(max_openings, 3)  # 每面墙最多建议3个开口

            if suggested_count <= 1:
                pos = round(length / 2, 1)
                lines.append(f"  - [{wid}] 长{length:.1f}m, 建议 1 个开口，位置约 from[0]={pos}m（居中）")
            else:
                gap = length / (suggested_count + 1)
                positions = [round(gap * (i + 1), 1) for i in range(suggested_count)]
                pos_str = ", ".join(f"{p}m" for p in positions)
                lines.append(f"  - [{wid}] 长{length:.1f}m, 建议 {suggested_count} 个开口，位置约 from[0]={pos_str}")

    return "\n".join(lines)
