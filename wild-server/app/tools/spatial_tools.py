"""
Spatial Validation Tools —— 空间校验 + 自动修正工具

每个工具都是 @tool 装饰的纯函数：
  - 输入：完整的 Blueprint dict（或 Blueprint JSON 字符串）
  - 输出：人类可读的校验结果文本
  - 用途：注册给 LangChain Agent，LLM 在生成蓝图后自动调用

模块化设计：
  - 辅助函数：_get_elements、_get_by_id、_wall_length 等
  - 检测类 Tool：validate_* 系列（只查不改）
  - 修正类 Tool：fix_* 系列（自动计算并修改）

扩展方式：新增一个 def validate_xxx(bp: dict) -> str 函数并注册即可。
"""
import math
from langchain.tools import tool


# ============================================================
# 辅助函数 —— 不对外暴露，只在本模块内复用
# ============================================================

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


# ============================================================
# 检测类 Tool —— 只查不改，返回问题列表
# ============================================================

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


# ============================================================
# 修正类 Tool —— 自动计算并修改，返回修正结果
# ============================================================

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
