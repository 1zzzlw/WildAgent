"""骨架模型输出的解析与下游摘要构建。"""

def parse_design_brief(reply_text: str) -> dict | None:
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
        return brief

    return None


def parse_components_from_reply(reply_text: str) -> list[str]:
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


def build_skeleton_summary(blueprint: dict, design_brief: dict | None = None) -> str:
    """生成骨架摘要供后续节点使用（几何轮廓 + 设计清单）"""
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
            lines.append(f"\nRAG 能力与关系依据: {rag_ref}")

    # ── 门/窗定位基本规则 ──
    if walls:
        lines.append("\n【门/窗定位基本规则】：")
        lines.append(
            "  1. from[0] = 沿墙距离(m)；from[1] = 底部世界Y："
            "门窗均优先逐字使用程序解析槽位，不再按建筑类型套固定窗台高度"
        )
        lines.append("  2. 门窗宽高、边缘留量和相邻间距服从已批准槽位，并且必须完整落在父墙范围内")
        lines.append(
            "  3. from=[沿墙距离, 底部世界Y, 局部法向偏移]；from[2] 不是世界 X/Z。"
            "门窗通常必须为 0（即使背墙世界 z=6，仍写 from[2]=0）"
        )
        lines.append("  4. facade_plan 中 max_openings=0 的墙面不要放置任何开口")

    return "\n".join(lines)
