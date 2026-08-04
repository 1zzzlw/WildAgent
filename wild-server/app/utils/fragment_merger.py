"""
分片合并工具：将骨架 + 多个组件分片合并为完整 Blueprint
新增：空间冲突解决器 —— 检测并修正重叠的门/窗位置
"""
from copy import deepcopy
from loguru import logger


def merge_fragments(skeleton: dict, fragments: list[dict]) -> dict:
    """
    将骨架 Blueprint + 多个组件分片合并为完整 Blueprint

    Args:
        skeleton: Layer 0 生成的骨架 Blueprint
        fragments: Layer 1 各节点生成的组件分片列表

    Returns:
        合并后的完整 Blueprint（含空间冲突修正）
    """
    blueprint = deepcopy(skeleton)
    elements = blueprint.setdefault("geometry", {}).setdefault("elements", [])
    components = blueprint["geometry"].setdefault("components", [])

    # 收集已有的 ID，用于冲突检测
    used_ids = {el.get("id") for el in elements if el.get("id")}

    for fragment in fragments:
        if not fragment:
            continue

        # 如果分片是列表，直接追加到 components
        if isinstance(fragment, list):
            for item in fragment:
                _insert_item(item, components, elements, used_ids)

        # 如果分片是单个对象（如 roof）
        elif isinstance(fragment, dict):
            _insert_item(fragment, components, elements, used_ids)

    blueprint["geometry"]["elements"] = elements
    blueprint["geometry"]["components"] = components

    # ── 空间冲突解决：修正重叠的门/窗 ──
    _resolve_openings_on_walls(components, elements)

    return blueprint


def _insert_item(item: dict, components: list, elements: list, used_ids: set):
    """插入一个元素或组件，处理 ID 冲突"""
    item_type = item.get("type", "")
    item_id = item.get("id")
    if not item_id:
        return

    # ID 冲突检测：自动加后缀
    if item_id in used_ids:
        original_id = item_id
        suffix = 1
        while f"{original_id}_{suffix}" in used_ids:
            suffix += 1
        item_id = f"{original_id}_{suffix}"
        item["id"] = item_id

    used_ids.add(item_id)

    # roof 写入 elements，其他写入 components
    if item_type == "roof":
        elements.append(item)
    else:
        components.append(item)


def _resolve_openings_on_walls(components: list[dict], elements: list[dict]):
    """检测并修正同一面墙上重叠的门/窗/凸窗

    策略：
    1. 按 parentWall 分组
    2. 每组内按 from[0] 排序
    3. 检测重叠：from[0]_i + width_i + min_gap > from[0]_(i+1)
    4. 重叠时：重新均匀分布所有开口，保持最小间距 0.3m
    """
    # 获取所有墙的信息
    wall_map = {}
    for el in elements:
        if el.get("type") == "wall":
            wid = el.get("id")
            if wid:
                frm = el.get("from", [0, 0, 0])
                to = el.get("to", [0, 0, 0])
                length = ((to[0] - frm[0]) ** 2 + (to[2] - frm[2]) ** 2) ** 0.5
                wall_map[wid] = {"from": frm, "to": to, "length": length}

    if not wall_map:
        return

    # 收集所有有 parentWall 的开口类组件
    opening_types = {"door", "window", "bay_window"}
    wall_openings: dict[str, list[dict]] = {}  # wall_id → [opening, ...]

    for comp in components:
        parent_wall = comp.get("parentWall", "")
        if comp.get("type") in opening_types and parent_wall in wall_map:
            wall_openings.setdefault(parent_wall, []).append(comp)

    fix_count = 0
    for wall_id, openings in wall_openings.items():
        if len(openings) < 2:
            continue

        wall = wall_map[wall_id]
        wall_length = wall["length"]

        # 按沿墙位置排序
        openings.sort(key=lambda o: o.get("from", [0, 0, 0])[0])

        # 检查是否重叠
        min_gap = 0.3  # 最小间距 30cm
        has_overlap = False
        for i in range(len(openings) - 1):
            a = openings[i]
            b = openings[i + 1]
            a_from = a.get("from", [0, 0, 0])[0]
            a_width = a.get("width", 1.0)
            b_from = b.get("from", [0, 0, 0])[0]

            if a_from + a_width + min_gap > b_from:
                has_overlap = True
                break

        if not has_overlap:
            continue

        # ── 重新均匀分布 ──
        logger.info(f"[merge] 检测到 {wall_id} 上有 {len(openings)} 个开口重叠，重新分配位置")

        total_width = sum(o.get("width", 1.0) for o in openings)
        total_gap = wall_length - total_width

        if total_gap < min_gap * (len(openings) + 1):
            # 墙太短，缩小开口宽度
            logger.warning(f"[merge] {wall_id} 墙长 {wall_length:.1f}m 不足以容纳 {len(openings)} 个开口（需 {total_width + min_gap*(len(openings)+1):.1f}m）")
            gap = min_gap
        else:
            gap = total_gap / (len(openings) + 1)

        # 均匀分布：第一个开口从 gap 位置开始
        current_pos = gap
        for opening in openings:
            width = opening.get("width", 1.0)
            fr = list(opening.get("from", [0, 0, 0]))

            # 确保不超出墙体
            if current_pos + width > wall_length:
                current_pos = max(0, wall_length - width)
                logger.warning(f"[merge] {opening.get('id')} 超出 {wall_id} 边界，修正到 {current_pos:.2f}")

            fr[0] = round(current_pos, 2)
            opening["from"] = fr
            current_pos += width + gap
            fix_count += 1

    if fix_count > 0:
        logger.info(f"[merge] 空间冲突解决完成：修正了 {fix_count} 个开口位置")
