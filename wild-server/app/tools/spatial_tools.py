"""
Spatial Validation Tools —— 空间校验 + 自动修正工具

每个工具都是 @tool 装饰的纯函数：
  - 输入：完整的 Blueprint dict
  - 输出：人类可读的校验结果文本
  - 用途：
      1. 注册给 LangChain Agent（LLM 可选调用）
      2. 由 agent_service.run_validation_pipeline() 按固定顺序强制执行

校验流水线顺序（Structure → Schema → Reference → Geometry → Fix → Collision）：
  1. validate_blueprint_structure      — 顶层结构完整性、ID 唯一性
  2. validate_element_required_fields  — 各构件必填字段 + 枚举值合法性
  3. validate_reference_integrity      — 跨构件引用合法性（parentWall、templateId 等）
  4. validate_opening_coords           — 门窗沿墙距离格式检查
  5. validate_wall_junctions           — 墙体转角端点对齐检查
  6. validate_stair_alignment          — 楼梯端点高度对齐检查
  7. validate_roof_coverage            — 屋顶 span/depth 覆盖范围检查
  8. fix_opening_coords                — 自动修正疑似世界坐标的门窗 from[0]
     → 修正后重跑 validate_opening_coords（由流水线调度，非工具自身）
  9. validate_collision                — 构件碰撞/穿插/悬空/重叠检测

扩展方式：新增 def validate_xxx(bp: dict) -> str 并在 agent_service.PIPELINE 中注册。
"""
import math
from langchain.tools import tool


# 辅助函数 —— 不对外暴露，只在本模块内复用
def _get_elements(bp: dict) -> list[dict]:
    """安全获取 elements 列表"""
    if not isinstance(bp, dict):
        return []
    return bp.get("geometry", {}).get("elements", [])

def _get_by_id(bp: dict, eid: str) -> dict | None:
    """按 id 查找元素"""
    for el in _get_elements(bp):
        if el.get("id") == eid:
            return el
    return None

def _wall_length(wall: dict) -> float:
    """计算墙体在 XZ 平面上的长度（沿墙距离）"""
    f = wall.get("from", [0, 0, 0])
    t = wall.get("to", [0, 0, 0])
    dx = t[0] - f[0]
    dz = t[2] - f[2]
    return math.sqrt(dx * dx + dz * dz)

def _wall_direction_xz(wall: dict) -> tuple[float, float]:
    """返回墙体在 XZ 平面上的单位方向向量"""
    f = wall.get("from", [0, 0, 0])
    t = wall.get("to", [0, 0, 0])
    dx = t[0] - f[0]
    dz = t[2] - f[2]
    length = math.sqrt(dx * dx + dz * dz)
    if length < 1e-6:
        return (0.0, 0.0)
    return (dx / length, dz / length)


# 检测类 Tool —— 只查不改，返回问题列表

@tool
def validate_blueprint_structure(blueprint: dict) -> str:
    """
    检查 Blueprint 顶层结构是否完整。
    验证 meta、geometry、elements 等必需字段是否存在。

    参数 blueprint: 完整的 Blueprint dict
    """
    issues: list[str] = []

    if "meta" not in blueprint:
        issues.append("❌ 缺少顶层字段 'meta'")
    else:
        meta = blueprint["meta"]
        if "version" not in meta:
            issues.append("❌ meta.version 缺失（应为 '1.0'）")
        if "type" not in meta:
            issues.append("❌ meta.type 缺失（应为 'building' 或 'avatar'）")
        if "name" not in meta:
            issues.append("⚠️  meta.name 缺失（建议填写建筑名称）")

    if "geometry" not in blueprint:
        issues.append("❌ 缺少顶层字段 'geometry'")
    else:
        geo = blueprint["geometry"]
        if "elements" not in geo:
            issues.append("❌ geometry.elements 缺失")
        else:
            elements = geo["elements"]
            if not isinstance(elements, list):
                issues.append(f"❌ geometry.elements 应为数组，实际为 {type(elements).__name__}")
            elif len(elements) == 0:
                issues.append("⚠️  geometry.elements 为空，建筑没有任何构件")
            else:
                # 检查 ID 唯一性
                ids = [el.get("id", "") for el in elements]
                dupes = {eid for eid in ids if ids.count(eid) > 1}
                if dupes:
                    issues.append(f"❌ 重复的构件 ID: {dupes}")

                # 检查每个元素是否有 type
                for el in elements:
                    if "type" not in el:
                        issues.append(f"❌ 元素缺少 'type' 字段: id={el.get('id', '?')}")
                    if "id" not in el:
                        issues.append("❌ 元素缺少 'id' 字段")

    if not issues:
        elements_count = len(_get_elements(blueprint))
        types = set(el.get("type", "?") for el in _get_elements(blueprint))
        return f"✅ 结构完整（{elements_count} 个构件，类型: {types}）"
    return "\n".join(issues)


@tool
def validate_opening_coords(blueprint: dict) -> str:
    """
    检查所有 opening（门窗洞口）的 from 字段是否正确使用了沿墙距离格式。

    正确格式：from = [沿墙距离, 距墙底高度, 法向偏移]
      沿墙距离：从 parentWall.from 点开始，沿墙体方向的偏移量（米）
      距墙底高度：从墙底向上的高度（米）
      法向偏移：垂直于墙面的偏移，默认 0

    错误格式：from = [世界坐标X, 高度Y, 世界坐标Z]

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]

    if not openings:
        return "✅ 没有 opening 构件，跳过检查。"

    issues: list[str] = []
    for op in openings:
        oid = op.get("id", "?")
        parent_id = op.get("parentWall", "")
        from_vec = op.get("from", [0, 0, 0])

        if not parent_id:
            issues.append(f"❌ [{oid}] 缺少 parentWall 字段")
            continue

        parent = walls.get(parent_id)
        if not parent:
            issues.append(f"❌ [{oid}] parentWall='{parent_id}' 不存在于 elements 中")
            continue

        wl = _wall_length(parent)
        along_dist = from_vec[0]
        normal_offset = from_vec[2] if len(from_vec) > 2 else 0

        # 沿墙距离检查
        if along_dist < -0.3 or along_dist > wl + 0.3:
            issues.append(
                f"⚠️  [{oid}] from[0]={along_dist} 超出墙体长度 [0, {wl:.1f}]。"
                f"可能使用了世界坐标而非沿墙距离。"
                f"parentWall='{parent_id}' 从 {parent['from']} 到 {parent['to']}。"
            )

        # 法向偏移检查
        if abs(normal_offset) > 0.5:
            issues.append(
                f"⚠️  [{oid}] from[2]={normal_offset} 法向偏移偏大，"
                f"通常应为 0（门窗在墙面上）"
            )

    if not issues:
        return "✅ 所有 opening 的 from 字段格式正确。"
    return "\n".join(issues)


@tool
def validate_wall_junctions(blueprint: dict) -> str:
    """
    检查相邻墙体在转角处是否对齐（端点共享，无缝隙）。

    判断标准：两堵不同墙体的端点之间在 XZ 平面距离 < 0.15m 即为"已连接"。
    所有不满足此条件的端点视为"孤立端点"，可能造成墙体缝隙。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = [el for el in elements if el.get("type") == "wall"]

    if len(walls) < 2:
        return "✅ 少于 2 面墙，跳过连接检查。"

    # 收集所有端点：(wall_id, which, x, z)
    endpoints: list[dict] = []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to", [0, 0, 0])
        endpoints.append({
            "wall_id": w.get("id", "?"),
            "which": "from",
            "x": float(f[0]),
            "z": float(f[2]),
        })
        endpoints.append({
            "wall_id": w.get("id", "?"),
            "which": "to",
            "x": float(t[0]),
            "z": float(t[2]),
        })

    TOLERANCE = 0.15  # 15cm 容差
    isolated: list[str] = []
    for ep in endpoints:
        has_neighbor = False
        for other in endpoints:
            if other["wall_id"] == ep["wall_id"]:
                continue
            dist = math.sqrt((ep["x"] - other["x"])**2 + (ep["z"] - other["z"])**2)
            if dist < TOLERANCE:
                has_neighbor = True
                break
        if not has_neighbor:
            isolated.append(
                f"  - {ep['wall_id']}.{ep['which']} ({ep['x']:.2f}, {ep['z']:.2f})"
            )

    if not isolated:
        return "✅ 所有墙体端点都有相邻连接，墙体闭合良好。"
    return (
        f"⚠️  发现 {len(isolated)} 个孤立端点（可能造成缝隙）：\n"
        + "\n".join(isolated)
        + "\n\n建议：确保相邻墙体端点坐标精确一致。"
    )


@tool
def validate_roof_coverage(blueprint: dict) -> str:
    """
    检查屋顶 span/depth 是否合理覆盖了墙体范围。

    规则：
      - span 应接近墙体 X 方向跨度（允许 1m 出檐）
      - depth 应接近墙体 Z 方向跨度（允许 1m 出檐）
      - 过大或过小都会产生警告

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    roofs = [el for el in elements if el.get("type") == "roof"]
    walls = [el for el in elements if el.get("type") == "wall"]

    if not roofs:
        return "✅ 没有 roof 构件，跳过检查。"
    if not walls:
        return "⚠️  有屋顶但没有墙体，无法判断覆盖范围。请确认设计意图。"

    # 计算所有墙体的 XZ 包围盒
    all_x: list[float] = []
    all_z: list[float] = []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to", [0, 0, 0])
        all_x.extend([f[0], t[0]])
        all_z.extend([f[2], t[2]])

    wall_span = max(all_x) - min(all_x)  # X 方向跨度
    wall_depth = max(all_z) - min(all_z)  # Z 方向跨度

    issues: list[str] = []
    for r in roofs:
        rid = r.get("id", "?")
        span = r.get("span", 0)
        depth = r.get("depth", 0)

        # 合理范围：墙体范围 + 0~2m 出檐空间
        if span < wall_span * 0.5:
            issues.append(
                f"❌ [{rid}] span={span:.1f} 远小于墙体宽度={wall_span:.1f}，"
                f"屋顶完全无法覆盖墙体"
            )
        elif span < wall_span - 0.5:
            issues.append(
                f"⚠️  [{rid}] span={span:.1f} 略小于墙体宽度={wall_span:.1f}，"
                f"出檐不足"
            )
        elif span > wall_span + 4.0:
            issues.append(
                f"⚠️  [{rid}] span={span:.1f} 远大于墙体宽度={wall_span:.1f}，"
                f"屋顶悬空过多"
            )

        if depth < wall_depth * 0.5:
            issues.append(
                f"❌ [{rid}] depth={depth:.1f} 远小于墙体进深={wall_depth:.1f}，"
                f"屋顶完全无法覆盖墙体"
            )
        elif depth < wall_depth - 0.5:
            issues.append(
                f"⚠️  [{rid}] depth={depth:.1f} 略小于墙体进深={wall_depth:.1f}，"
                f"出檐不足"
            )
        elif depth > wall_depth + 4.0:
            issues.append(
                f"⚠️  [{rid}] depth={depth:.1f} 远大于墙体进深={wall_depth:.1f}，"
                f"屋顶悬空过多"
            )

    if not issues:
        return (
            f"✅ 屋顶尺寸合理。"
            f"（墙体宽度={wall_span:.1f}, 进深={wall_depth:.1f}）"
        )
    return "\n".join(issues)


@tool
def validate_stair_alignment(blueprint: dict) -> str:
    """
    检查楼梯 from/to 端点高度是否与地板或墙体高度对齐。

    规则：
      - from.y 应对齐下层地板顶面或地面（y=0）
      - to.y 应对齐上层地板顶面或墙体顶部高度
      - 允许 ±0.2m 容差

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    stairs = [el for el in elements if el.get("type") == "stair"]

    if not stairs:
        return "✅ 没有 stair 构件，跳过检查。"

    # 收集参考高度：地板顶面 + 墙体顶部 + 地面
    floors = [el for el in elements if el.get("type") == "floor"]
    walls = [el for el in elements if el.get("type") == "wall"]

    floor_heights: list[float] = []
    for f in floors:
        fy = f.get("from", [0, 0, 0])[1]
        if isinstance(fy, (int, float)):
            floor_heights.append(float(fy))

    wall_top_heights: list[float] = []
    for w in walls:
        ty = w.get("to", [0, 0, 0])[1]
        if isinstance(ty, (int, float)):
            wall_top_heights.append(float(ty))

    all_ref_heights = sorted(set([0.0] + floor_heights + wall_top_heights))

    issues: list[str] = []
    for s in stairs:
        sid = s.get("id", "?")
        f = s.get("from", [0, 0, 0])
        t = s.get("to", [0, 0, 0])

        fy = float(f[1]) if len(f) > 1 else 0.0
        ty = float(t[1]) if len(t) > 1 else 0.0

        # 检查 from.y
        from_diffs = [abs(fy - h) for h in all_ref_heights]
        if from_diffs and min(from_diffs) > 0.2:
            nearest = all_ref_heights[from_diffs.index(min(from_diffs))]
            issues.append(
                f"⚠️  [{sid}] from.y={fy:.2f} 不匹配任何参考高度。"
                f"最近: {nearest}（差 {abs(fy - nearest):.2f}m）"
            )

        # 检查 to.y
        to_diffs = [abs(ty - h) for h in all_ref_heights]
        if to_diffs and min(to_diffs) > 0.2:
            nearest = all_ref_heights[to_diffs.index(min(to_diffs))]
            issues.append(
                f"⚠️  [{sid}] to.y={ty:.2f} 不匹配任何参考高度。"
                f"最近: {nearest}（差 {abs(ty - nearest):.2f}m）"
            )

        # 检查 from.y < to.y（楼梯应该向上）
        if fy >= ty:
            issues.append(
                f"❌ [{sid}] from.y={fy:.2f} >= to.y={ty:.2f}，"
                f"楼梯应该向上攀升"
            )

    if not issues:
        ref_str = ", ".join(f"{h:.1f}m" for h in all_ref_heights)
        return f"✅ 楼梯端点与参考高度对齐。参考高度: [{ref_str}]"
    return "\n".join(issues)


# 修正类 Tool —— 自动计算并修改，返回修正结果

@tool
def validate_element_required_fields(blueprint: dict) -> str:
    """
    检查每个构件是否包含其类型所需的必填字段。
    这是渲染前的最后一道防线——缺少必填字段会导致 wild-core 重建崩溃。

    各构件类型的必填字段：
      wall:    from, to, thickness
      floor:   from, to, thickness
      column:  base, height, bottomRadius, topRadius, style
      beam:    from, to, crossSection, width, height
      roof:    roofType, span, depth, height, thickness
      opening: parentWall, from, width, height, style
      stair:   from, to, width
      furniture: subtype, position, dimensions { width, depth, height }

    参数 blueprint: 完整的 Blueprint dict
    """
    REQUIRED = {
        "wall":      ["from", "to", "thickness"],
        "floor":     ["from", "to", "thickness"],
        "column":    ["base", "height", "bottomRadius", "topRadius", "style"],
        "beam":      ["from", "to", "crossSection", "width", "height"],
        "roof":      ["roofType", "span", "depth", "height", "thickness"],
        "opening":   ["parentWall", "from", "width", "height", "style"],
        "stair":     ["from", "to", "width"],
        "furniture": ["subtype", "position", "dimensions"],
        "dense_brick": ["resolution", "origin", "data"],
        "body":      ["height", "build", "headShape", "armLength", "legLength", "cloakLength", "hoodUp"],
    }

    # 合法枚举值
    VALID_FURNITURE_SUBTYPES = {"table", "chair", "bookshelf", "bed", "lamp", "tile"}
    VALID_ROOF_TYPES = {"gable", "hip", "dome", "flat", "chinese_curved", "chinese_pagoda"}
    VALID_COLUMN_STYLES = {"doric", "ionic", "corinthian", "modern", "chinese_wooden"}
    VALID_OPENING_STYLES = {"rectangular", "arched", "gothic", "circular"}

    # 蓝图顶层只允许这些 key
    VALID_ROOT_KEYS = {"meta", "geometry", "materials", "behaviors", "editor"}
    # geometry 内部只允许这些 key
    VALID_GEOMETRY_KEYS = {"elements", "templates", "instances", "placements"}

    issues: list[str] = []

    # === 检查根级别多余的 key ===
    extra_root = set(blueprint.keys()) - VALID_ROOT_KEYS
    if extra_root:
        issues.append(f"❌ 蓝图根级别出现非法字段: {extra_root}。只允许: {VALID_ROOT_KEYS}")

    # === 检查 geometry 内部多余的 key ===
    geo = blueprint.get("geometry", {})
    if isinstance(geo, dict):
        extra_geo = set(geo.keys()) - VALID_GEOMETRY_KEYS
        if extra_geo:
            issues.append(f"❌ geometry 内部出现非法字段: {extra_geo}。只允许: {VALID_GEOMETRY_KEYS}")

    elements = _get_elements(blueprint)
    if not elements:
        if not issues:
            return "✅ 没有构件，跳过必填字段检查。"
        return "\n".join(issues)

    for el in elements:
        etype = el.get("type", "")
        eid = el.get("id", "?")
        required = REQUIRED.get(etype, [])
        if not required:
            issues.append(f"❌ [{eid}] 未知构件类型 '{etype}'")
            continue
        for field in required:
            if field not in el or el[field] is None:
                issues.append(f"❌ [{eid}] (type={etype}) 缺少必填字段 '{field}'")

        # furniture 特殊检查
        if etype == "furniture":
            # subtype 合法性
            subtype = el.get("subtype", "")
            if subtype and subtype not in VALID_FURNITURE_SUBTYPES:
                issues.append(
                    f"❌ [{eid}] furniture subtype='{subtype}' 无效。"
                    f"合法值: {VALID_FURNITURE_SUBTYPES}"
                )
            # dimensions 结构化检查
            if "dimensions" in el:
                dims = el["dimensions"]
                if isinstance(dims, dict):
                    for dfield in ["width", "depth", "height"]:
                        if dfield not in dims or dims[dfield] is None:
                            issues.append(
                                f"❌ [{eid}] (type=furniture) dimensions 缺少 '{dfield}'"
                            )
                else:
                    issues.append(
                        f"❌ [{eid}] (type=furniture) dimensions 必须是对象，实际为 {type(dims).__name__}"
                    )

    if not issues:
        types_found = set(el.get("type", "?") for el in elements)
        return f"✅ 所有 {len(elements)} 个构件的必填字段完整（类型: {types_found}）"
    return "\n".join(issues)

@tool
def fix_opening_coords(blueprint: dict) -> str:
    """
    自动检测并修正 opening 的坐标问题。
    如果 from[0] 疑似世界坐标（值超出墙体长度范围），则尝试换算为沿墙距离。

    原理：
      - 对于主要沿 X 方向的墙（|dx| > |dz|）：沿墙距离 = from[0] - wall.from[0]
      - 对于主要沿 Z 方向的墙（|dz| > |dx|）：沿墙距离 = from[2] - wall.from[2]

    注意：此工具会直接修改传入的 Blueprint dict。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]

    if not openings:
        return "✅ 没有 opening 需要修正。"

    fixes: list[str] = []
    for op in openings:
        oid = op.get("id", "?")
        parent_id = op.get("parentWall", "")
        from_vec = op.get("from", [0, 0, 0])

        parent = walls.get(parent_id)
        if not parent:
            continue

        wl = _wall_length(parent)
        along_dist = float(from_vec[0])

        # 判断是否可能在合理范围外
        if -0.3 <= along_dist <= wl + 0.3:
            continue  # 已经在合理范围

        # 尝试换算
        wf = parent.get("from", [0, 0, 0])
        dx, dz = _wall_direction_xz(parent)

        # 计算当前 from_vec 在墙起点基础上的偏移
        world_x = float(from_vec[0])
        world_z = float(from_vec[2]) if len(from_vec) > 2 else 0.0

        if abs(dx) > abs(dz):
            # 墙体主要沿 X 方向
            new_along = (world_x - wf[0]) if dx > 0 else (wf[0] - world_x)
        else:
            # 墙体主要沿 Z 方向
            new_along = (world_z - wf[2]) if dz > 0 else (wf[2] - world_z)

        new_along = max(0.1, min(abs(new_along), wl - 0.1))

        old_val = from_vec[0]
        op["from"][0] = round(new_along, 2)

        fixes.append(
            f"🔧 [{oid}]: from[0] {old_val} → {new_along:.2f}（沿墙距离）\n"
            f"   parentWall='{parent_id}' 墙长={wl:.1f} 方向={'X' if abs(dx) > abs(dz) else 'Z'}"
        )

    if not fixes:
        return "✅ 所有 opening 坐标已在合理范围，无需修正。"
    return "已自动修正以下 opening 坐标：\n" + "\n".join(fixes)


# ============================================================
# 引用完整性校验 —— Step 3 in pipeline
# ============================================================

@tool
def validate_reference_integrity(blueprint: dict) -> str:
    """
    校验构件之间的引用关系是否合法。

    检查项：
      1. opening.parentWall 必须存在且 type == 'wall'
      2. geometry.instances[*].templateId 必须存在于 geometry.templates
      3. behaviors.physics.constraints[*].target 必须是已存在的构件 id
      4. 不允许循环引用（template 引用自身）

    参数 blueprint: 完整的 Blueprint dict
    """
    issues: list[str] = []
    elements = _get_elements(blueprint)
    element_ids = {el.get("id") for el in elements if el.get("id")}
    wall_ids = {el.get("id") for el in elements if el.get("type") == "wall"}

    # --- 1. opening.parentWall 校验 ---
    for el in elements:
        if el.get("type") != "opening":
            continue
        eid = el.get("id", "?")
        parent = el.get("parentWall", "")
        if not parent:
            issues.append(f"❌ [{eid}] opening 缺少 parentWall 字段")
        elif parent not in element_ids:
            issues.append(f"❌ [{eid}] parentWall='{parent}' 引用的构件不存在")
        elif parent not in wall_ids:
            issues.append(
                f"❌ [{eid}] parentWall='{parent}' 引用的构件不是 wall 类型"
            )

    # --- 2. instances.templateId 校验 ---
    geo = blueprint.get("geometry", {})
    templates = geo.get("templates", {}) or {}
    instances = geo.get("instances", []) or []
    for inst in instances:
        iid = inst.get("id", "?")
        tid = inst.get("templateId", "")
        if not tid:
            issues.append(f"❌ [instance:{iid}] 缺少 templateId 字段")
        elif tid not in templates:
            issues.append(
                f"❌ [instance:{iid}] templateId='{tid}' 在 geometry.templates 中不存在"
            )

    # --- 3. behaviors.physics.constraints.target 校验 ---
    physics = blueprint.get("behaviors", {}).get("physics", {})
    for c in physics.get("constraints", []):
        target = c.get("target", "")
        if target and target not in element_ids:
            issues.append(
                f"❌ [behavior.constraint] target='{target}' 引用的构件不存在"
            )

    # --- 4. template 自引用检测 ---
    for tname, tdef in templates.items():
        sub_elements = tdef.get("elements", []) if isinstance(tdef, dict) else []
        for sub in sub_elements:
            ref = sub.get("templateId", "")
            if ref == tname:
                issues.append(
                    f"❌ [template:{tname}] 存在自引用（templateId 指向自身），会导致无限递归"
                )

    if not issues:
        return (
            f"✅ 引用完整性通过。"
            f"（{len(elements)} 个构件，{len(templates)} 个模板，{len(instances)} 个实例）"
        )
    return "\n".join(issues)


# ============================================================
# 碰撞 / 空间冲突检测 —— Step 9 in pipeline
# ============================================================

def _aabb(el: dict) -> tuple[float, float, float, float, float, float] | None:
    """
    计算元素的轴对齐包围盒 (minX, maxX, minY, maxY, minZ, maxZ)。
    只处理有明确坐标的构件，无法计算的返回 None。
    Y 轴：wall/floor/beam 用 from[1]/to[1]，column 用 base[1] ~ base[1]+height。
    """
    t = el.get("type", "")

    if t in ("wall", "floor", "beam"):
        f = el.get("from", [])
        to = el.get("to", [])
        if len(f) < 3 or len(to) < 3:
            return None
        thickness = el.get("thickness", el.get("width", 0.2))
        # 对于 wall/beam，XZ 方向有厚度，需向两侧各扩半个厚度
        half_t = thickness / 2.0
        min_x = min(f[0], to[0]) - half_t
        max_x = max(f[0], to[0]) + half_t
        min_y = min(f[1], to[1])
        max_y = max(f[1], to[1])
        min_z = min(f[2], to[2]) - half_t
        max_z = max(f[2], to[2]) + half_t
        return (min_x, max_x, min_y, max_y, min_z, max_z)

    if t == "column":
        base = el.get("base", [])
        height = el.get("height", 0)
        r = max(el.get("bottomRadius", 0.1), el.get("topRadius", 0.1))
        if len(base) < 3:
            return None
        return (
            base[0] - r, base[0] + r,
            base[1], base[1] + height,
            base[2] - r, base[2] + r,
        )

    if t == "stair":
        f = el.get("from", [])
        to = el.get("to", [])
        w = el.get("width", 1.0) / 2.0
        if len(f) < 3 or len(to) < 3:
            return None
        return (
            min(f[0], to[0]) - w, max(f[0], to[0]) + w,
            min(f[1], to[1]), max(f[1], to[1]),
            min(f[2], to[2]) - w, max(f[2], to[2]) + w,
        )

    if t == "furniture":
        pos = el.get("position", [])
        dims = el.get("dimensions", {})
        if len(pos) < 3 or not isinstance(dims, dict):
            return None
        hw = dims.get("width", 0.5) / 2.0
        hd = dims.get("depth", 0.5) / 2.0
        h = dims.get("height", 0.5)
        return (
            pos[0] - hw, pos[0] + hw,
            pos[1], pos[1] + h,
            pos[2] - hd, pos[2] + hd,
        )

    return None


def _aabb_overlap(
    a: tuple[float, float, float, float, float, float],
    b: tuple[float, float, float, float, float, float],
    margin: float = 0.05,
) -> bool:
    """判断两个 AABB 是否重叠（margin 为最小穿插深度阈值，避免贴面误报）"""
    return (
        a[0] < b[1] - margin and a[1] > b[0] + margin and  # X
        a[2] < b[3] - margin and a[3] > b[2] + margin and  # Y
        a[4] < b[5] - margin and a[5] > b[4] + margin      # Z
    )


@tool
def validate_collision(blueprint: dict) -> str:
    """
    检测构件之间是否存在碰撞、穿插、悬空或不合理重叠。

    检查项：
      1. 同类型构件之间不应有实质性重叠（如两根柱子、两段楼梯）
      2. opening 不应与其他 opening 重叠（同一面墙上）
      3. column / furniture / stair 不应穿插进 wall 内部（允许贴靠）
      4. column / stair / furniture 底部 Y 不应悬空
         （base[1] 或 from[1] 应 >= 最近楼板顶面，容差 0.3m）

    说明：
      - 使用轴对齐包围盒（AABB）近似，不做精确几何求交
      - opening 本身嵌入墙体是合法的，不参与碰撞检测
      - wall 之间的端点相交是正常建筑连接，不报告

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    issues: list[str] = []

    # 按 type 分组
    by_type: dict[str, list[dict]] = {}
    for el in elements:
        t = el.get("type", "")
        by_type.setdefault(t, []).append(el)

    # --- 1. 同类型非 wall 构件之间重叠检测 ---
    CHECK_SELF_COLLISION = ("column", "stair", "furniture", "beam", "floor")
    for t in CHECK_SELF_COLLISION:
        group = by_type.get(t, [])
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                ba = _aabb(a)
                bb = _aabb(b)
                if ba and bb and _aabb_overlap(ba, bb):
                    issues.append(
                        f"⚠️  [{a.get('id','?')}] 与 [{b.get('id','?')}]"
                        f"（均为 {t}）存在重叠/穿插，请检查坐标"
                    )

    # --- 2. 同一面墙上的 opening 重叠检测 ---
    openings = by_type.get("opening", [])
    # 按 parentWall 分组
    wall_openings: dict[str, list[dict]] = {}
    for op in openings:
        pw = op.get("parentWall", "")
        wall_openings.setdefault(pw, []).append(op)

    for wall_id, ops in wall_openings.items():
        for i in range(len(ops)):
            for j in range(i + 1, len(ops)):
                a, b = ops[i], ops[j]
                a_from = a.get("from", [0, 0, 0])
                b_from = b.get("from", [0, 0, 0])
                a_w = a.get("width", 1.0)
                b_w = b.get("width", 1.0)
                a_h = a.get("height", 1.0)
                b_h = b.get("height", 1.0)

                # 沿墙方向区间重叠 + 高度区间重叠
                a_along_min = a_from[0]
                a_along_max = a_from[0] + a_w
                b_along_min = b_from[0]
                b_along_max = b_from[0] + b_w

                a_y_min = a_from[1]
                a_y_max = a_from[1] + a_h
                b_y_min = b_from[1]
                b_y_max = b_from[1] + b_h

                along_overlap = a_along_min < b_along_max and a_along_max > b_along_min
                y_overlap = a_y_min < b_y_max and a_y_max > b_y_min

                if along_overlap and y_overlap:
                    issues.append(
                        f"❌ [{a.get('id','?')}] 与 [{b.get('id','?')}]"
                        f" 在墙 '{wall_id}' 上发生开口重叠，"
                        f"沿墙区间 [{a_along_min:.2f},{a_along_max:.2f}] ∩ [{b_along_min:.2f},{b_along_max:.2f}]"
                    )

    # --- 3. column / stair / furniture 不应穿插入 wall 内部 ---
    # 允许贴靠（margin 收紧到 0.15m，避免合理贴墙被误报）
    walls = by_type.get("wall", [])
    INTRUDE_TYPES = ("column", "stair", "furniture")
    for t in INTRUDE_TYPES:
        for el in by_type.get(t, []):
            el_bb = _aabb(el)
            if not el_bb:
                continue
            for wall in walls:
                w_bb = _aabb(wall)
                if not w_bb:
                    continue
                if _aabb_overlap(el_bb, w_bb, margin=0.15):
                    issues.append(
                        f"⚠️  [{el.get('id','?')}]（{t}）与墙 [{wall.get('id','?')}] "
                        f"存在穿插，请确认是否为贴墙摆放（可忽略）或实际穿墙（需修正）"
                    )

    # --- 4. 悬空检测：column / stair / furniture 底部 Y 应不低于地板 ---
    floors = by_type.get("floor", [])
    floor_top_ys: list[float] = []
    for f in floors:
        fy = f.get("from", [0, 0, 0])[1]
        if isinstance(fy, (int, float)):
            floor_top_ys.append(float(fy))
    floor_top_ys = sorted(set([0.0] + floor_top_ys))

    FLOATING_TYPES = {
        "column": lambda el: el.get("base", [0, 0, 0])[1],
        "stair":  lambda el: el.get("from", [0, 0, 0])[1],
        "furniture": lambda el: el.get("position", [0, 0, 0])[1],
    }
    for t, get_bottom_y in FLOATING_TYPES.items():
        for el in by_type.get(t, []):
            bottom_y = float(get_bottom_y(el))
            # 找最近的楼板高度
            nearest_floor = min(floor_top_ys, key=lambda fy: abs(fy - bottom_y))
            gap = bottom_y - nearest_floor
            if gap > 0.3:
                issues.append(
                    f"⚠️  [{el.get('id','?')}]（{t}）底部 Y={bottom_y:.2f}，"
                    f"距最近楼板 Y={nearest_floor:.2f} 相差 {gap:.2f}m，可能悬空"
                )
            elif gap < -0.1:
                issues.append(
                    f"⚠️  [{el.get('id','?')}]（{t}）底部 Y={bottom_y:.2f}，"
                    f"低于最近楼板 Y={nearest_floor:.2f}，可能穿入地板"
                )

    if not issues:
        checked = sum(len(by_type.get(t, [])) for t in (*CHECK_SELF_COLLISION, "opening"))
        return f"✅ 碰撞检测通过，共检查 {checked} 个构件，未发现空间冲突。"
    return f"发现 {len(issues)} 处空间冲突：\n" + "\n".join(issues)


# ============================================================
# P0：开口越界检查 —— 顶点爆炸根源
# ============================================================

@tool
def validate_opening_fit(blueprint: dict) -> str:
    """
    检查每个 opening 是否完全在 parentWall 的尺寸范围内。

    规则：
      - 沿墙方向：from[0] >= 0 且 from[0] + width <= 墙长
      - 高度方向：from[1] >= 墙底Y 且 from[1] + height <= 墙顶Y

    超出墙体范围的 opening 会导致 wild-core 切孔算法产生异常几何（顶点数爆炸）。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]

    if not openings:
        return "✅ 没有 opening 构件，跳过检查。"

    issues: list[str] = []
    for op in openings:
        oid = op.get("id", "?")
        parent_id = op.get("parentWall", "")
        from_vec = op.get("from", [0, 0, 0])
        width = op.get("width", 0)
        height = op.get("height", 0)

        parent = walls.get(parent_id)
        if not parent:
            continue  # 已由 validate_reference_integrity 覆盖

        wl = _wall_length(parent)
        wall_bottom_y = min(parent.get("from", [0, 0, 0])[1],
                            parent.get("to",   [0, 0, 0])[1])
        wall_top_y    = max(parent.get("from", [0, 0, 0])[1],
                            parent.get("to",   [0, 0, 0])[1])
        wall_height   = wall_top_y - wall_bottom_y

        along = float(from_vec[0])
        base_y = float(from_vec[1]) if len(from_vec) > 1 else wall_bottom_y

        # 沿墙方向越界
        if along < -0.05:
            issues.append(
                f"❌ [{oid}] 沿墙起点 {along:.2f} < 0，开口超出墙体左端"
            )
        if along + width > wl + 0.05:
            issues.append(
                f"❌ [{oid}] 沿墙终点 {along + width:.2f} > 墙长 {wl:.2f}，开口超出墙体右端"
            )

        # 高度方向越界（相对世界坐标）
        rel_bottom = base_y - wall_bottom_y
        rel_top    = rel_bottom + height
        if rel_bottom < -0.05:
            issues.append(
                f"❌ [{oid}] 开口底部 Y={base_y:.2f} 低于墙底 Y={wall_bottom_y:.2f}"
            )
        if rel_top > wall_height + 0.05:
            issues.append(
                f"❌ [{oid}] 开口顶部 Y={base_y + height:.2f} 超出墙顶 Y={wall_top_y:.2f}"
            )

        # 尺寸为零或负值
        if width <= 0:
            issues.append(f"❌ [{oid}] width={width} 无效，必须 > 0")
        if height <= 0:
            issues.append(f"❌ [{oid}] height={height} 无效，必须 > 0")

    if not issues:
        return f"✅ 所有 {len(openings)} 个 opening 均在 parentWall 范围内。"
    return "\n".join(issues)


# ============================================================
# P1：构件尺寸合理性检查
# ============================================================

@tool
def validate_element_dimensions(blueprint: dict) -> str:
    """
    检查各构件尺寸是否在合理范围内。

    规则（单位：米）：
      wall:    长度 0.1~500，高度 0.1~50，厚度 0.01~5
      floor:   单边 0.1~500，厚度 0.01~5
      column:  高度 0.1~50，半径 0.01~5
      beam:    长度 0.1~200，宽/高截面 0.01~5
      roof:    span/depth 0.5~500，高度 0.1~100
      opening: 宽 0.1~20，高 0.1~20
      stair:   高差 0.1~50，水平距离 0.1~100

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    issues: list[str] = []

    for el in elements:
        t   = el.get("type", "")
        eid = el.get("id", "?")

        if t == "wall":
            length = _wall_length(el)
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            h = abs(to[1] - f[1])
            th = el.get("thickness", 0)
            if not (0.1 <= length <= 500):
                issues.append(f"⚠️  [{eid}] wall 长度={length:.1f}m，建议在 0.1~500m")
            if h > 0 and not (0.1 <= h <= 50):
                issues.append(f"⚠️  [{eid}] wall 高度={h:.1f}m，建议在 0.1~50m")
            if th > 0 and not (0.01 <= th <= 5):
                issues.append(f"⚠️  [{eid}] wall thickness={th}m，建议在 0.01~5m")

        elif t == "floor":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            sx = abs(to[0] - f[0])
            sz = abs(to[2] - f[2])
            th = el.get("thickness", 0)
            for dim, val in [("X跨度", sx), ("Z跨度", sz)]:
                if val > 0 and not (0.1 <= val <= 500):
                    issues.append(f"⚠️  [{eid}] floor {dim}={val:.1f}m，建议在 0.1~500m")
            if th > 0 and not (0.01 <= th <= 5):
                issues.append(f"⚠️  [{eid}] floor thickness={th}m，建议在 0.01~5m")

        elif t == "column":
            h  = el.get("height", 0)
            br = el.get("bottomRadius", 0)
            tr = el.get("topRadius", 0)
            if h > 0 and not (0.1 <= h <= 50):
                issues.append(f"⚠️  [{eid}] column height={h}m，建议在 0.1~50m")
            for rname, rv in [("bottomRadius", br), ("topRadius", tr)]:
                if rv > 0 and not (0.01 <= rv <= 5):
                    issues.append(f"⚠️  [{eid}] column {rname}={rv}m，建议在 0.01~5m")

        elif t == "beam":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            dx = to[0]-f[0]; dy = to[1]-f[1]; dz = to[2]-f[2]
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            w = el.get("width", 0)
            h = el.get("height", 0)
            if length > 0 and not (0.1 <= length <= 200):
                issues.append(
                    f"❌ [{eid}] beam 长度={length:.1f}m，超出合理范围 0.1~200m，"
                    f"可能坐标错误"
                )
            for fname, fv in [("width", w), ("height", h)]:
                if fv > 0 and not (0.01 <= fv <= 5):
                    issues.append(f"⚠️  [{eid}] beam {fname}={fv}m，建议在 0.01~5m")

        elif t == "roof":
            span  = el.get("span", 0)
            depth = el.get("depth", 0)
            rh    = el.get("height", 0)
            for fname, fv, lo, hi in [
                ("span",  span,  0.5, 500),
                ("depth", depth, 0.5, 500),
                ("height",rh,    0.1, 100),
            ]:
                if fv > 0 and not (lo <= fv <= hi):
                    issues.append(f"⚠️  [{eid}] roof {fname}={fv}m，建议在 {lo}~{hi}m")

        elif t == "opening":
            w = el.get("width", 0)
            h = el.get("height", 0)
            for fname, fv in [("width", w), ("height", h)]:
                if fv > 0 and not (0.1 <= fv <= 20):
                    issues.append(f"⚠️  [{eid}] opening {fname}={fv}m，建议在 0.1~20m")

        elif t == "stair":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            dh = abs(to[1] - f[1])
            dx = to[0]-f[0]; dz = to[2]-f[2]
            horiz = math.sqrt(dx*dx + dz*dz)
            if dh > 0 and not (0.1 <= dh <= 50):
                issues.append(f"⚠️  [{eid}] stair 高差={dh:.1f}m，建议在 0.1~50m")
            if horiz > 0 and not (0.1 <= horiz <= 100):
                issues.append(f"⚠️  [{eid}] stair 水平距离={horiz:.1f}m，建议在 0.1~100m")

    if not issues:
        return f"✅ 所有 {len(elements)} 个构件尺寸合理。"
    return "\n".join(issues)


# ============================================================
# 查询类 Tool —— 不修改 Blueprint，只返回场景信息供 LLM 参考
# ============================================================

@tool
def get_wall_bounding_box(blueprint: dict) -> str:
    """
    查询所有墙体的 XZ 平面包围盒信息。

    返回墙体覆盖范围（宽度/进深）、中心点坐标、墙高范围，
    用于在生成 roof / floor 等覆盖类构件前获取正确的目标尺寸。

    重要：生成 roof 前必须先调用此工具！roof 的 span/depth 必须 >= 墙体包围盒。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = [el for el in elements if el.get("type") == "wall"]

    if not walls:
        return "⚠️  场景中没有墙体，无法计算包围盒。"

    all_x, all_z = [], []
    all_y_min, all_y_max = [], []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to", [0, 0, 0])
        all_x.extend([f[0], t[0]])
        all_z.extend([f[2], t[2]])
        all_y_min.append(min(f[1], t[1]))
        all_y_max.append(max(f[1], t[1]))

    min_x, max_x = min(all_x), max(all_x)
    min_z, max_z = min(all_z), max(all_z)
    span = max_x - min_x
    depth = max_z - min_z
    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2
    min_y = min(all_y_min)
    max_y = max(all_y_max)

    EAVE = 1.0  # 建议出檐

    return (
        f"📐 墙体 XZ 包围盒信息：\n"
        f"  - X 方向（宽度/面阔）：{span:.1f}m（从 {min_x:.1f} 到 {max_x:.1f}，中心={center_x:.1f}）\n"
        f"  - Z 方向（进深）：{depth:.1f}m（从 {min_z:.1f} 到 {max_z:.1f}，中心={center_z:.1f}）\n"
        f"  - Y 方向（高度）范围：{min_y:.1f}m ~ {max_y:.1f}m（最大墙高={max_y:.1f}m）\n"
        f"  - 墙体数量：{len(walls)} 面\n"
        f"\n"
        f"💡 屋顶生成建议：\n"
        f"  - roof.span 应设为 {span + EAVE * 2:.1f}m（墙体宽度 + {EAVE * 2:.1f}m 出檐）\n"
        f"  - roof.depth 应设为 {depth + EAVE * 2:.1f}m（墙体进深 + {EAVE * 2:.1f}m 出檐）\n"
        f"  - roof.position = [{center_x:.1f}, {max_y:.1f}, {center_z:.1f}]（墙顶中心）\n"
        f"  - 如果是多屋顶设计，请根据各自的覆盖范围分别设置"
    )


# ============================================================
# P0：屋顶自动修正
# ============================================================

@tool
def fix_roof_coverage(blueprint: dict) -> str:
    """
    自动修正屋顶的 span/depth/position，使其合理覆盖墙体包围盒。

    修正逻辑：
      1. 计算所有 wall 的 XZ 包围盒（minX/maxX/minZ/maxZ）
      2. span  = wall X 跨度 + 出檐（默认 1.0m 每侧）
      3. depth = wall Z 跨度 + 出檐（默认 1.0m 每侧）
      4. position.x = wall X 中心
      5. position.z = wall Z 中心
      6. position.y 保持不变（由 LLM 生成，通常是墙顶高度）

    仅修正 span/depth 明显不匹配的屋顶（差值 > 2m）。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls  = [el for el in elements if el.get("type") == "wall"]
    roofs  = [el for el in elements if el.get("type") == "roof"]

    if not roofs:
        return "✅ 没有 roof 构件，跳过修正。"
    if not walls:
        return "⚠️  没有 wall 构件，无法计算屋顶目标尺寸。"

    # 计算墙体 XZ 包围盒
    all_x, all_z = [], []
    for w in walls:
        f, t = w.get("from", [0,0,0]), w.get("to", [0,0,0])
        all_x += [f[0], t[0]]
        all_z += [f[2], t[2]]

    min_x, max_x = min(all_x), max(all_x)
    min_z, max_z = min(all_z), max(all_z)
    wall_span  = max_x - min_x
    wall_depth = max_z - min_z
    center_x   = (min_x + max_x) / 2
    center_z   = (min_z + max_z) / 2

    EAVE = 1.0   # 出檐 1m
    target_span  = round(wall_span  + EAVE * 2, 2)
    target_depth = round(wall_depth + EAVE * 2, 2)

    fixes: list[str] = []
    for r in roofs:
        rid   = r.get("id", "?")
        span  = r.get("span",  0)
        depth = r.get("depth", 0)
        pos   = r.get("position", [center_x, 0, center_z])

        changed: list[str] = []

        # span 差值 > 2m 才修正
        if abs(span - target_span) > 2.0:
            r["span"] = target_span
            changed.append(f"span {span} → {target_span}")

        # depth 差值 > 2m 才修正
        if abs(depth - target_depth) > 2.0:
            r["depth"] = target_depth
            changed.append(f"depth {depth} → {target_depth}")

        # position.x / position.z 修正到墙体中心（偏差 > 5m 才动）
        if isinstance(pos, list) and len(pos) >= 3:
            if abs(pos[0] - center_x) > 5.0:
                changed.append(f"position.x {pos[0]} → {center_x:.2f}")
                pos[0] = round(center_x, 2)
            if abs(pos[2] - center_z) > 5.0:
                changed.append(f"position.z {pos[2]} → {center_z:.2f}")
                pos[2] = round(center_z, 2)
            r["position"] = pos

        if changed:
            fixes.append(f"🔧 [{rid}]: " + ", ".join(changed))

    if not fixes:
        return (
            f"✅ 所有屋顶尺寸已合理（墙体跨度 {wall_span:.1f}×{wall_depth:.1f}m，"
            f"目标 {target_span:.1f}×{target_depth:.1f}m），无需修正。"
        )
    return (
        f"已自动修正屋顶覆盖范围（墙体 {wall_span:.1f}×{wall_depth:.1f}m，"
        f"目标 {target_span:.1f}×{target_depth:.1f}m）：\n"
        + "\n".join(fixes)
    )


# ============================================================
# P1：墙体端点自动对齐
# ============================================================

@tool
def fix_wall_junctions(blueprint: dict) -> str:
    """
    自动对齐孤立的墙体端点，消除墙体转角缝隙。

    修正逻辑：
      对每个孤立端点，找距离最近的其他墙体端点；
      若距离在 (TOLERANCE, MAX_SNAP] 范围内，则把孤立端点坐标对齐到目标端点。
      - TOLERANCE = 0.15m（已在容差内的不处理）
      - MAX_SNAP   = 1.5m（超过此距离不自动对齐，避免误操作）

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = [el for el in elements if el.get("type") == "wall"]

    if len(walls) < 2:
        return "✅ 少于 2 面墙，跳过端点对齐。"

    TOLERANCE = 0.15
    MAX_SNAP  = 1.5

    # 收集所有端点
    endpoints: list[dict] = []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to",   [0, 0, 0])
        endpoints.append({"wall": w, "which": "from", "x": float(f[0]), "z": float(f[2])})
        endpoints.append({"wall": w, "which": "to",   "x": float(t[0]), "z": float(t[2])})

    fixes: list[str] = []

    for ep in endpoints:
        # 检查是否已有邻居
        has_neighbor = any(
            other["wall"] is not ep["wall"] and
            math.sqrt((ep["x"]-other["x"])**2 + (ep["z"]-other["z"])**2) < TOLERANCE
            for other in endpoints
        )
        if has_neighbor:
            continue

        # 找最近的其他墙端点
        candidates = [
            (math.sqrt((ep["x"]-o["x"])**2 + (ep["z"]-o["z"])**2), o)
            for o in endpoints
            if o["wall"] is not ep["wall"]
        ]
        if not candidates:
            continue
        dist, nearest = min(candidates, key=lambda x: x[0])

        if TOLERANCE < dist <= MAX_SNAP:
            wall  = ep["wall"]
            which = ep["which"]
            old_x, old_z = ep["x"], ep["z"]
            new_x, new_z = nearest["x"], nearest["z"]

            # 修改 blueprint dict
            coord = wall[which]  # list [x, y, z]
            coord[0] = new_x
            coord[2] = new_z

            fixes.append(
                f"🔧 [{wall.get('id','?')}.{which}]: "
                f"({old_x:.2f}, {old_z:.2f}) → ({new_x:.2f}, {new_z:.2f})  "
                f"dist={dist:.3f}m"
            )

    if not fixes:
        return "✅ 所有墙体端点已对齐，无需修正。"
    return "已自动对齐以下墙体端点：\n" + "\n".join(fixes)


# ============================================================
# P1：开口越界自动修正（继 validate_opening_fit）
# ============================================================

@tool
def fix_opening_fit(blueprint: dict) -> str:
    """
    自动修正超出 parentWall 范围的 opening。

    修正策略：
      - 沿墙方向越界：将 from[0] 钳位到 [0, 墙长 - width]，width 超出墙长时等比例缩小
      - 高度方向越界：将 from[1] 钳位到 [墙底Y, 墙顶Y - height]，height 超出墙高时等比例缩小

    仅对严重越界（超出 0.5m）的 opening 进行修正，轻微偏差保留原样。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]

    if not openings:
        return "✅ 没有 opening 构件，跳过修正。"

    THRESHOLD = 0.5  # 只修正超出 0.5m 的情况，避免过度干扰用户设计意图

    fixes: list[str] = []
    for op in openings:
        oid = op.get("id", "?")
        parent_id = op.get("parentWall", "")
        parent = walls.get(parent_id)
        if not parent:
            continue

        wl = _wall_length(parent)
        f, t = parent.get("from", [0, 0, 0]), parent.get("to", [0, 0, 0])
        wall_bottom_y = min(f[1], t[1])
        wall_top_y    = max(f[1], t[1])
        wall_height   = wall_top_y - wall_bottom_y

        along = op.get("from", [0, 0, 0])[0]
        base_y = op.get("from", [0, 0, 0])[1] if len(op["from"]) > 1 else wall_bottom_y
        width  = op.get("width", 1.0)
        height = op.get("height", 1.0)

        changed: list[str] = []

        # 1. 沿墙方向修正
        left_margin  = max(0.0, 0.0 - along)
        right_margin = max(0.0, (along + width) - wl)

        if left_margin > THRESHOLD:
            # 左端越界 → 向右移动，保持 width
            new_along = 0.1  # 留 0.1m 余量
            op["from"][0] = new_along
            changed.append(f"沿墙距离 {along:.2f} → {new_along:.2f}（左端越界 {left_margin:.2f}m）")
        elif right_margin > THRESHOLD:
            # 右端越界 → 向左移动，若 width 超过墙长则等比例缩小
            max_width = wl - 0.1
            if width > max_width:
                op["width"] = max_width
                changed.append(f"宽度 {width:.2f} → {max_width:.2f}（超出墙体 {right_margin:.2f}m）")
            # 移动起点
            new_along = max(0.1, wl - op["width"] - 0.1)
            op["from"][0] = new_along
            changed.append(f"沿墙距离 {along:.2f} → {new_along:.2f}（右端越界）")

        # 2. 高度方向修正
        bottom_margin = max(0.0, wall_bottom_y - base_y)
        top_margin    = max(0.0, (base_y + height) - wall_top_y)

        if bottom_margin > THRESHOLD:
            # 底部低于墙底 → 上移到墙底 + 余量
            new_base_y = wall_bottom_y + 0.1
            op["from"][1] = new_base_y
            changed.append(f"底部Y {base_y:.2f} → {new_base_y:.2f}（低于墙底 {bottom_margin:.2f}m）")
        elif top_margin > THRESHOLD:
            # 顶部高于墙顶 → 等比例缩小或下移
            max_height = wall_height - 0.1
            if height > max_height:
                op["height"] = max_height
                changed.append(f"高度 {height:.2f} → {max_height:.2f}（超出墙体 {top_margin:.2f}m）")
            # 下移到底部
            new_base_y = wall_top_y - op["height"] - 0.1
            op["from"][1] = new_base_y
            changed.append(f"底部Y {base_y:.2f} → {new_base_y:.2f}（超出墙顶）")

        # 3. 防止尺寸为零或负值
        if op.get("width", 1.0) <= 0.01:
            op["width"] = 0.1
            changed.append(f"宽度修正为 0.1m（原值为 {width}）")
        if op.get("height", 1.0) <= 0.01:
            op["height"] = 0.1
            changed.append(f"高度修正为 0.1m（原值为 {height}）")

        if changed:
            fixes.append(f"🔧 [{oid}]: " + "; ".join(changed))

    if not fixes:
        return "✅ 所有 opening 均在 parentWall 合理范围内，无需修正。"
    return "已自动修正以下 opening 越界问题：\n" + "\n".join(fixes)


# ============================================================
# P1：楼梯端点高度自动对齐
# ============================================================

@tool
def fix_stair_alignment(blueprint: dict) -> str:
    """
    自动修正楼梯端点高度，使其对齐到最近的地板或墙体高度。

    修正逻辑：
      - 收集所有可用参考高度（地板顶面Y、墙体顶部Y、地面Y=0）
      - 将 stair.from.y 对齐到最近的参考高度（容差 0.2m 内才修正）
      - 将 stair.to.y 对齐到下一个更高的参考高度
      - 确保 from.y < to.y（楼梯向上）

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    stairs = [el for el in elements if el.get("type") == "stair"]
    if not stairs:
        return "✅ 没有 stair 构件，跳过修正。"

    # 收集参考高度
    ref_ys: list[float] = [0.0]
    for el in elements:
        if el.get("type") == "floor":
            fy = el.get("from", [0, 0, 0])[1]
            if isinstance(fy, (int, float)):
                ref_ys.append(float(fy))
        elif el.get("type") == "wall":
            ty = el.get("to", [0, 0, 0])[1]
            if isinstance(ty, (int, float)):
                ref_ys.append(float(ty))
    ref_ys = sorted(set(ref_ys))

    TOL = 0.2  # 2cm 容差，小于此值时视为已对齐

    fixes: list[str] = []
    for s in stairs:
        sid = s.get("id", "?")
        f = s.get("from", [0, 0, 0])
        t = s.get("to",   [0, 0, 0])
        fy = float(f[1]) if len(f) > 1 else 0.0
        ty = float(t[1]) if len(t) > 1 else 0.0

        changed: list[str] = []

        # 对齐 from.y
        if ref_ys:
            best_ref = min(ref_ys, key=lambda h: abs(h - fy))
            if abs(fy - best_ref) > TOL:
                f[1] = best_ref
                changed.append(f"from.y {fy:.2f} → {best_ref:.2f}")

        # 对齐 to.y（找比当前 from.y 更高的最近参考高度）
        from_y = f[1]
        higher_refs = [h for h in ref_ys if h > from_y]
        if higher_refs:
            best_to = min(higher_refs, key=lambda h: abs(h - ty))
            if abs(ty - best_to) > TOL:
                t[1] = best_to
                changed.append(f"to.y {ty:.2f} → {best_to:.2f}")
        else:
            # 没有更高参考，设为 from.y + 0.3m（标准踏步高度）
            new_to_y = from_y + 0.3
            if abs(ty - new_to_y) > TOL:
                t[1] = new_to_y
                changed.append(f"to.y {ty:.2f} → {new_to_y:.2f}（默认踏步高度）")

        # 检查 from.y < to.y，若不成立则交换
        if f[1] >= t[1]:
            f[1], t[1] = t[1], f[1]
            changed.append("from/to Y 互换（确保楼梯向上）")

        if changed:
            fixes.append(f"🔧 [{sid}]: " + ", ".join(changed))

    if not fixes:
        return "✅ 所有 stair 端点高度已合理对齐，无需修正。"
    return "已自动修正以下 stair 高度对齐：\n" + "\n".join(fixes)


# ============================================================
# P1：构件尺寸自动修正（继 validate_element_dimensions）
# ============================================================

@tool
def fix_element_dimensions(blueprint: dict) -> str:
    """
    自动修正严重异常的构件尺寸。

    修正策略：
      - 超出上限 2 倍以上的尺寸才修正（防止过度干预合理设计）
      - 按合理范围上限的 0.9 倍收缩
      - 保留组件比例（如 wall 的厚度与高度比例）

    参数 blueprint: 完整的 Blueprint dict
    """
    RULES = {
        "wall":      {"length": (0.1, 500), "height": (0.1, 50),  "thickness": (0.01, 5)},
        "floor":     {"span":   (0.1, 500), "thickness": (0.01, 5)},
        "column":    {"height": (0.1, 50),  "radius": (0.01, 5)},
        "beam":      {"length": (0.1, 200), "width": (0.01, 5),   "height": (0.01, 5)},
        "roof":      {"span":   (0.5, 500), "depth": (0.5, 500),  "height": (0.1, 100)},
        "opening":   {"width":  (0.1, 20),  "height": (0.1, 20)},
        "stair":     {"rise":   (0.1, 50),  "run": (0.1, 100)},
    }

    elements = _get_elements(blueprint)
    fixes: list[str] = []

    for el in elements:
        t = el.get("type", "")
        eid = el.get("id", "?")
        if t not in RULES:
            continue

        changed: list[str] = []

        # wall 特殊处理
        if t == "wall":
            length = _wall_length(el)
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            height = abs(to[1] - f[1])
            thickness = el.get("thickness", 0)

            lo, hi = RULES[t]["length"]
            if length > hi * 2:  # 超过上限 2 倍才修
                # 保持墙体方向，等比缩短到 hi * 0.9
                scale = hi * 0.9 / length
                el["to"][0] = f[0] + (to[0] - f[0]) * scale
                el["to"][2] = f[2] + (to[2] - f[2]) * scale
                changed.append(f"长度 {length:.1f} → {length*scale:.1f}m")

            lo, hi = RULES[t]["height"]
            if height > hi * 2:
                # 降低高度，保持厚度比例
                new_height = hi * 0.9
                scale = new_height / height
                el["to"][1] = f[1] + (to[1] - f[1]) * scale
                changed.append(f"高度 {height:.1f} → {new_height:.1f}m")

            lo, hi = RULES[t]["thickness"]
            if thickness > hi * 2:
                el["thickness"] = hi * 0.9
                changed.append(f"厚度 {thickness:.1f} → {el['thickness']:.1f}m")

        # beam 特殊处理（长度）
        elif t == "beam":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            dx, dy, dz = to[0]-f[0], to[1]-f[1], to[2]-f[2]
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            lo, hi = RULES[t]["length"]
            if length > hi * 2:
                scale = hi * 0.9 / length
                el["to"][0] = f[0] + dx * scale
                el["to"][1] = f[1] + dy * scale
                el["to"][2] = f[2] + dz * scale
                changed.append(f"长度 {length:.1f} → {length*scale:.1f}m")

        # 屋顶修正（已在 fix_roof_coverage 中处理，这里只兜底极端值）
        elif t == "roof":
            for field, (lo, hi) in [("span", RULES[t]["span"]),
                                     ("depth", RULES[t]["depth"]),
                                     ("height", RULES[t]["height"])]:
                if field in el:
                    val = el[field]
                    if val > hi * 3:  # 极端异常才修
                        el[field] = hi * 0.9
                        changed.append(f"{field} {val:.1f} → {el[field]:.1f}m")

        if changed:
            fixes.append(f"🔧 [{eid}]: " + "; ".join(changed))

    if not fixes:
        return "✅ 所有构件尺寸在合理范围内，无需修正。"
    return "已自动修正以下构件尺寸异常：\n" + "\n".join(fixes)