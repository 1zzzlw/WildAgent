"""
组件专用校验/修复工具

每种组件有对应的校验和修复函数：
- validate_<component>: 校验该组件
- fix_<component>: 修复该组件

策略：在节点生成后立即调用，确保对齐
"""
from loguru import logger
from app.tools.spatial_tools import (
    MAX_OPENING_NORMAL_OFFSET,
    fix_element_elevations,
    fix_primitive_elevations,
    get_roof_support_bounds,
    validate_element_required_fields,
)


def validate_door_placement(blueprint: dict) -> str:
    """校验门的位置是否正确
    
    检查：
    1. parentWall 是否存在
    2. from 位置是否在墙体范围内
    3. 门宽度是否超出墙体
    4. 门是否与其他开口重叠
    """
    issues = []
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    # 构建墙体索引
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    
    # 获取所有门
    doors = [c for c in components if c.get("type") == "door"]
    
    for door in doors:
        door_id = door.get("id", "?")
        parent_wall = door.get("parentWall")
        door_from = door.get("from", [0, 0, 0])
        door_width = door.get("width", 0)
        
        # 检查 1: parentWall 是否存在
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{door_id}] parentWall '{parent_wall}' 不存在")
            continue
        
        if (
            not isinstance(door_from, list)
            or len(door_from) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in door_from)
        ):
            issues.append(f"❌ [{door_id}] from 必须是 3 个数值组成的局部坐标")
            continue

        wall = walls[parent_wall]
        wall_from = wall.get("from", [0, 0, 0])
        wall_to = wall.get("to", [0, 0, 0])
        
        # 计算墙长度
        wall_length = ((wall_to[0] - wall_from[0])**2 + (wall_to[2] - wall_from[2])**2)**0.5
        
        # 检查 2: from[0] 是否在墙体范围内
        door_pos = door_from[0] if isinstance(door_from, list) else door_from
        if door_pos < 0 or door_pos > wall_length:
            issues.append(f"❌ [{door_id}] from位置 {door_pos:.2f}m 超出墙长 {wall_length:.2f}m")
        
        # 检查 3: 门是否超出墙体末端
        if door_pos + door_width > wall_length:
            issues.append(f"❌ [{door_id}] 门末端 {door_pos + door_width:.2f}m 超出墙长 {wall_length:.2f}m")
        if abs(float(door_from[2])) > MAX_OPENING_NORMAL_OFFSET:
            issues.append(
                f"❌ [{door_id}] from[2]={door_from[2]} 是过大的法向偏移；"
                "不能填写父墙世界坐标，门应贴合父墙且通常为 0"
            )
    
    if not issues:
        return f"✅ 门位置校验通过 ({len(doors)} 个门)"
    
    return "\n".join(issues)


def fix_door_placement(blueprint: dict) -> str:
    """修复门的位置错误
    
    修复策略：
    1. parentWall 不存在 → 找最近的墙
    2. from 位置超出 → 调整到墙体中心
    3. 宽度超出 → 缩小宽度或移动位置
    """
    fixes = []
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    if not walls:
        return "⚠️ 没有墙体，无法修复门"
    
    doors = [c for c in components if c.get("type") == "door"]
    
    for door in doors:
        door_id = door.get("id", "?")
        parent_wall = door.get("parentWall")
        door_from = door.get("from", [0, 0, 0])
        door_width = door.get("width", 1.0)
        
        # 修复 1: parentWall 不存在 → 使用第一面墙
        if not parent_wall or parent_wall not in walls:
            new_wall = list(walls.keys())[0]
            door["parentWall"] = new_wall
            fixes.append(f"🔧 [{door_id}] parentWall 修正为 {new_wall}")
            parent_wall = new_wall
        
        wall = walls[parent_wall]
        wall_from = wall.get("from", [0, 0, 0])
        wall_to = wall.get("to", [0, 0, 0])
        wall_length = ((wall_to[0] - wall_from[0])**2 + (wall_to[2] - wall_from[2])**2)**0.5

        if (
            not isinstance(door_from, list)
            or len(door_from) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in door_from)
        ):
            door_from = [(wall_length - door_width) / 2, min(wall_from[1], wall_to[1]), 0.0]
            door["from"] = door_from
            fixes.append(f"🔧 [{door_id}] from 重建为局部门窗坐标 {door_from}")

        if abs(float(door_from[2])) > MAX_OPENING_NORMAL_OFFSET:
            dx = wall_to[0] - wall_from[0]
            dz = wall_to[2] - wall_from[2]
            dir_x = dx / wall_length if wall_length else 0.0
            dir_z = dz / wall_length if wall_length else 0.0
            projected = (
                (float(door_from[0]) - float(wall_from[0])) * dir_x
                + (float(door_from[2]) - float(wall_from[2])) * dir_z
            )
            old_offset = door_from[2]
            if -0.3 <= projected <= wall_length + 0.3:
                door_from[0] = round(max(0.0, min(projected, wall_length)), 2)
            door_from[2] = 0.0
            door["from"] = door_from
            fixes.append(f"🔧 [{door_id}] from[2] {old_offset} → 0，重新投影到父墙")
        
        # 修复 2: 位置超出或宽度超出
        door_pos = door_from[0] if isinstance(door_from, list) else door_from
        
        # 确保门在墙体范围内，留 0.3m 边距
        margin = 0.3
        max_pos = max(0, wall_length - door_width - margin)
        
        if door_pos < margin or door_pos + door_width > wall_length - margin:
            # 移到墙体中心
            new_pos = (wall_length - door_width) / 2
            new_pos = max(margin, min(new_pos, max_pos))
            
            if isinstance(door_from, list):
                door["from"] = [new_pos, door_from[1], door_from[2]]
            else:
                door["from"] = new_pos
            
            fixes.append(f"🔧 [{door_id}] 位置调整为 {new_pos:.2f}m (墙长 {wall_length:.2f}m)")
    
    if not fixes:
        return f"✅ 门位置无需修复 ({len(doors)} 个门)"
    
    return "\n".join(fixes)


def validate_window_placement(blueprint: dict) -> str:
    """校验窗的位置是否正确"""
    issues = []
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    windows = [c for c in components if c.get("type") == "window"]
    
    for window in windows:
        window_id = window.get("id", "?")
        parent_wall = window.get("parentWall")
        window_from = window.get("from", [0, 0, 0])
        window_width = window.get("width", 0)
        
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{window_id}] parentWall '{parent_wall}' 不存在")
            continue
        
        if (
            not isinstance(window_from, list)
            or len(window_from) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in window_from)
        ):
            issues.append(f"❌ [{window_id}] from 必须是 3 个数值组成的局部坐标")
            continue

        wall = walls[parent_wall]
        wall_from = wall.get("from", [0, 0, 0])
        wall_to = wall.get("to", [0, 0, 0])
        wall_length = ((wall_to[0] - wall_from[0])**2 + (wall_to[2] - wall_from[2])**2)**0.5
        
        window_pos = window_from[0] if isinstance(window_from, list) else window_from
        
        if window_pos < 0 or window_pos > wall_length:
            issues.append(f"❌ [{window_id}] from位置 {window_pos:.2f}m 超出墙长 {wall_length:.2f}m")
        
        if window_pos + window_width > wall_length:
            issues.append(f"❌ [{window_id}] 窗末端 {window_pos + window_width:.2f}m 超出墙长 {wall_length:.2f}m")
        if abs(float(window_from[2])) > MAX_OPENING_NORMAL_OFFSET:
            issues.append(
                f"❌ [{window_id}] from[2]={window_from[2]} 是过大的法向偏移；"
                "不能填写父墙世界坐标，窗应贴合父墙且通常为 0"
            )
    
    if not issues:
        return f"✅ 窗位置校验通过 ({len(windows)} 个窗)"
    
    return "\n".join(issues)


def fix_window_placement(blueprint: dict) -> str:
    """修复窗的位置错误"""
    fixes = []
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    if not walls:
        return "⚠️ 没有墙体，无法修复窗"
    
    windows = [c for c in components if c.get("type") == "window"]
    
    for window in windows:
        window_id = window.get("id", "?")
        parent_wall = window.get("parentWall")
        window_from = window.get("from", [0, 0, 0])
        window_width = window.get("width", 1.2)
        
        if not parent_wall or parent_wall not in walls:
            new_wall = list(walls.keys())[0]
            window["parentWall"] = new_wall
            fixes.append(f"🔧 [{window_id}] parentWall 修正为 {new_wall}")
            parent_wall = new_wall
        
        wall = walls[parent_wall]
        wall_from = wall.get("from", [0, 0, 0])
        wall_to = wall.get("to", [0, 0, 0])
        wall_length = ((wall_to[0] - wall_from[0])**2 + (wall_to[2] - wall_from[2])**2)**0.5

        if (
            not isinstance(window_from, list)
            or len(window_from) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in window_from)
        ):
            window_from = [(wall_length - window_width) / 2, min(wall_from[1], wall_to[1]) + 0.9, 0.0]
            window["from"] = window_from
            fixes.append(f"🔧 [{window_id}] from 重建为局部门窗坐标 {window_from}")

        if abs(float(window_from[2])) > MAX_OPENING_NORMAL_OFFSET:
            dx = wall_to[0] - wall_from[0]
            dz = wall_to[2] - wall_from[2]
            dir_x = dx / wall_length if wall_length else 0.0
            dir_z = dz / wall_length if wall_length else 0.0
            projected = (
                (float(window_from[0]) - float(wall_from[0])) * dir_x
                + (float(window_from[2]) - float(wall_from[2])) * dir_z
            )
            old_offset = window_from[2]
            if -0.3 <= projected <= wall_length + 0.3:
                window_from[0] = round(max(0.0, min(projected, wall_length)), 2)
            window_from[2] = 0.0
            window["from"] = window_from
            fixes.append(f"🔧 [{window_id}] from[2] {old_offset} → 0，重新投影到父墙")
        
        window_pos = window_from[0] if isinstance(window_from, list) else window_from
        margin = 0.3
        max_pos = max(0, wall_length - window_width - margin)
        
        if window_pos < margin or window_pos + window_width > wall_length - margin:
            # 窗口在墙上均匀分布
            new_pos = (wall_length - window_width) / 2
            new_pos = max(margin, min(new_pos, max_pos))
            
            if isinstance(window_from, list):
                window["from"] = [new_pos, window_from[1], window_from[2]]
            else:
                window["from"] = new_pos
            
            fixes.append(f"🔧 [{window_id}] 位置调整为 {new_pos:.2f}m (墙长 {wall_length:.2f}m)")
    
    if not fixes:
        return f"✅ 窗位置无需修复 ({len(windows)} 个窗)"
    
    return "\n".join(fixes)


def validate_roof_coverage(blueprint: dict) -> str:
    """校验屋顶是否覆盖建筑"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    roofs = [e for e in elements if e.get("type") == "roof"]
    
    if not roofs:
        return "⚠️ 没有屋顶"
    
    walls = [e for e in elements if e.get("type") == "wall"]
    if not walls:
        return "⚠️ 没有墙体，无法校验屋顶"
    
    issues = []
    for roof in roofs:
        roof_id = roof.get("id", "?")
        roof_span = roof.get("span", 0)
        roof_depth = roof.get("depth", 0)
        bounds = get_roof_support_bounds(walls, roof)
        building_width = bounds["span"]
        building_depth = bounds["depth"]
        
        if roof_span < building_width * 0.9:
            issues.append(f"❌ [{roof_id}] span {roof_span:.2f}m < 建筑宽度 {building_width:.2f}m")
        
        if roof_depth < building_depth * 0.9:
            issues.append(f"❌ [{roof_id}] depth {roof_depth:.2f}m < 建筑深度 {building_depth:.2f}m")
        if roof_span > building_width + 4.0 or roof_depth > building_depth + 4.0:
            issues.append(
                f"❌ [{roof_id}] 屋顶 {roof_span:.2f}×{roof_depth:.2f}m "
                f"远大于顶层承托墙 {building_width:.2f}×{building_depth:.2f}m"
            )
    
    if not issues:
        return f"✅ 屋顶覆盖校验通过 ({len(roofs)} 个屋顶)"
    
    return "\n".join(issues)


def fix_roof_coverage(blueprint: dict) -> str:
    """修复屋顶覆盖问题"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    roofs = [e for e in elements if e.get("type") == "roof"]
    
    if not roofs:
        return "⚠️ 没有屋顶"
    
    walls = [e for e in elements if e.get("type") == "wall"]
    if not walls:
        return "⚠️ 没有墙体"
    
    fixes = []
    for roof in roofs:
        roof_id = roof.get("id", "?")
        bounds = get_roof_support_bounds(walls, roof)
        roof["span"] = round(bounds["span"] + 1.2, 2)
        roof["depth"] = round(bounds["depth"] + 1.2, 2)
        roof["position"] = [
            round(bounds["center_x"], 2),
            round(bounds["support_y"], 2),
            round(bounds["center_z"], 2),
        ]
        fixes.append(
            f"🔧 [{roof_id}] 调整为 {roof['span']:.2f}×{roof['depth']:.2f}m, "
            f"中心={roof['position']}"
        )
    
    return "\n".join(fixes)


def validate_railing_placement(blueprint: dict) -> str:
    """校验栏杆路径和高度"""
    components = blueprint.get("geometry", {}).get("components", [])
    railings = [c for c in components if c.get("type") == "railing"]
    
    if not railings:
        return "⚠️ 没有栏杆"
    
    issues = []
    for railing in railings:
        rail_id = railing.get("id", "?")
        path = railing.get("path", [])
        height = railing.get("height", 1.0)
        
        if len(path) < 2:
            issues.append(f"❌ [{rail_id}] path 至少需要 2 个点，当前: {len(path)}")
        
        if height < 0.8 or height > 1.2:
            issues.append(f"❌ [{rail_id}] height {height:.2f}m 超出常规范围 0.8~1.2m")
    
    if not issues:
        return f"✅ 栏杆校验通过 ({len(railings)} 个栏杆)"
    
    return "\n".join(issues)


def fix_railing_placement(blueprint: dict) -> str:
    """修复栏杆配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    railings = [c for c in components if c.get("type") == "railing"]
    
    if not railings:
        return "⚠️ 没有栏杆"
    
    fixes = []
    for railing in railings:
        rail_id = railing.get("id", "?")
        path = railing.get("path", [])
        
        if len(path) < 2:
            # 生成默认 2 点路径
            railing["path"] = [[0, 0, 0], [3, 0, 0]]
            fixes.append(f"🔧 [{rail_id}] 添加默认路径")
        
        height = railing.get("height", 1.0)
        if height < 0.8:
            railing["height"] = 0.9
            fixes.append(f"🔧 [{rail_id}] height 调整为 0.9m")
        elif height > 1.2:
            railing["height"] = 1.1
            fixes.append(f"🔧 [{rail_id}] height 调整为 1.1m")
    
    if not fixes:
        return f"✅ 栏杆无需修复 ({len(railings)} 个栏杆)"
    
    return "\n".join(fixes)


def validate_canopy_placement(blueprint: dict) -> str:
    """校验雨棚配置"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    canopies = [c for c in components if c.get("type") == "canopy"]
    
    if not canopies:
        return "⚠️ 没有雨棚"
    
    issues = []
    warnings = []
    for canopy in canopies:
        canopy_id = canopy.get("id", "?")
        parent_wall = canopy.get("parentWall")
        depth = canopy.get("depth", 0)
        thickness = canopy.get("thickness", 0)
        
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{canopy_id}] parentWall '{parent_wall}' 不存在")
            continue
        
        if depth <= 0:
            issues.append(f"❌ [{canopy_id}] depth {depth} 必须大于 0")
        
        if thickness <= 0:
            issues.append(f"❌ [{canopy_id}] thickness {thickness} 必须大于 0")

        # 雨棚必须遮蔽真实的门/窗/入口。悬在无任何洞口的实墙高处，
        # 视觉上就是一块“悬空片”（实测生成缺陷），这里按宿主墙上开洞对齐判定。
        mount_y = canopy.get("from", [0, 0, 0])[1]
        start_x = canopy.get("from", [0, 0, 0])[0]
        end_x = start_x + canopy.get("width", 0)
        covered = []
        for component in components:
            if component.get("type") not in {"door", "window", "bay_window"}:
                continue
            if component.get("parentWall") != parent_wall:
                continue
            comp_x = component.get("from", [0, 0, 0])[0]
            comp_top = component.get("from", [0, 0, 0])[1] + component.get("height", 0)
            if comp_x < end_x and comp_x + component.get("width", 0) > start_x and comp_top <= mount_y + 0.6:
                covered.append(str(component.get("id", "?")))
        if not covered:
            warnings.append(
                f"⚠️ [{canopy_id}] 下方没有门/窗可遮蔽（挂高 {mount_y:.2f}m、"
                f"沿墙 {start_x:.2f}~{end_x:.2f}m），疑似悬空装饰片："
                "请移到入口门上方，或删除该雨棚"
            )
    
    if not issues:
        if warnings:
            return "\n".join(warnings)
        return f"✅ 雨棚校验通过 ({len(canopies)} 个雨棚)"
    
    return "\n".join([*issues, *warnings])


def fix_canopy_placement(blueprint: dict) -> str:
    """修复雨棚配置"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    if not walls:
        return "⚠️ 没有墙体，无法修复雨棚"
    
    canopies = [c for c in components if c.get("type") == "canopy"]
    
    fixes = []
    for canopy in canopies:
        canopy_id = canopy.get("id", "?")
        parent_wall = canopy.get("parentWall")
        
        if not parent_wall or parent_wall not in walls:
            new_wall = list(walls.keys())[0]
            canopy["parentWall"] = new_wall
            fixes.append(f"🔧 [{canopy_id}] parentWall 修正为 {new_wall}")
        
        if canopy.get("depth", 0) <= 0:
            canopy["depth"] = 1.5
            fixes.append(f"🔧 [{canopy_id}] depth 设置为 1.5m")
        
        if canopy.get("thickness", 0) <= 0:
            canopy["thickness"] = 0.15
            fixes.append(f"🔧 [{canopy_id}] thickness 设置为 0.15m")
    
    if not fixes:
        return f"✅ 雨棚无需修复 ({len(canopies)} 个雨棚)"
    
    return "\n".join(fixes)


def validate_balcony_placement(blueprint: dict) -> str:
    """校验阳台父墙、尺寸与标高；地面标高的“阳台”属于无效构件。"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    balconies = [c for c in components if c.get("type") == "balcony"]
    
    if not balconies:
        return "⚠️ 没有阳台"
    
    issues = []
    for balcony in balconies:
        balcony_id = balcony.get("id", "?")
        parent_wall = balcony.get("parentWall")
        slab_thickness = balcony.get("slabThickness", 0)
        balcony_from = balcony.get("from", [])
        
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{balcony_id}] parentWall '{parent_wall}' 不存在")
            continue
        if slab_thickness <= 0:
            issues.append(f"❌ [{balcony_id}] slabThickness {slab_thickness} 必须大于 0")
        if not isinstance(balcony_from, list) or len(balcony_from) != 3:
            issues.append(f"❌ [{balcony_id}] from 必须是 [沿墙距离, 世界Y, 法向偏移]")
            continue
        wall = walls[parent_wall]
        wall_from = wall.get("from", [0, 0, 0])
        wall_to = wall.get("to", [0, 0, 0])
        wall_bottom = min(float(wall_from[1]), float(wall_to[1]))
        wall_top = max(float(wall_from[1]), float(wall_to[1]))
        if wall_top - wall_bottom < 0.5:
            wall_top = wall_bottom + float(wall.get("height", 0))
        balcony_y = float(balcony_from[1])
        if balcony_y < 1.8:
            issues.append(f"❌ [{balcony_id}] 阳台标高 Y={balcony_y:.2f}m 位于地面层")
        if balcony_y < wall_bottom - 0.25 or balcony_y > wall_top + 0.25:
            issues.append(
                f"❌ [{balcony_id}] 阳台标高 Y={balcony_y:.2f}m "
                f"超出父墙竖向范围 {wall_bottom:.2f}~{wall_top:.2f}m"
            )
        wall_length = (
            (float(wall_to[0]) - float(wall_from[0])) ** 2
            + (float(wall_to[2]) - float(wall_from[2])) ** 2
        ) ** 0.5
        width = float(balcony.get("width", 0))
        if float(balcony_from[0]) < 0 or float(balcony_from[0]) + width > wall_length:
            issues.append(f"❌ [{balcony_id}] 阳台沿墙范围超出父墙长度 {wall_length:.2f}m")
    
    if not issues:
        return f"✅ 阳台校验通过 ({len(balconies)} 个阳台)"
    
    return "\n".join(issues)


def fix_balcony_placement(blueprint: dict) -> str:
    """修复阳台配置"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    if not walls:
        return "⚠️ 没有墙体，无法修复阳台"
    
    balconies = [c for c in components if c.get("type") == "balcony"]
    
    def wall_metrics(wall: dict) -> tuple[float, float, float]:
        start = wall.get("from", [0, 0, 0])
        end = wall.get("to", [0, 0, 0])
        length = (
            (float(end[0]) - float(start[0])) ** 2
            + (float(end[2]) - float(start[2])) ** 2
        ) ** 0.5
        bottom = min(float(start[1]), float(end[1]))
        top = max(float(start[1]), float(end[1]))
        if top - bottom < 0.5:
            top = bottom + float(wall.get("height", 0))
        return length, bottom, top

    fixes = []
    wall_usage: dict[str, int] = {}
    for balcony in balconies:
        parent = str(balcony.get("parentWall") or "")
        wall_usage[parent] = wall_usage.get(parent, 0) + 1
    for balcony in balconies:
        balcony_id = balcony.get("id", "?")
        parent_wall = balcony.get("parentWall")
        invalid_parent = not parent_wall or parent_wall not in walls
        if invalid_parent:
            new_wall = list(walls.keys())[0]
            balcony["parentWall"] = new_wall
            fixes.append(f"🔧 [{balcony_id}] parentWall 修正为 {new_wall}")
        
        if balcony.get("slabThickness", 0) <= 0:
            balcony["slabThickness"] = 0.15
            fixes.append(f"🔧 [{balcony_id}] slabThickness 设置为 0.15m")

        balcony_from = balcony.get("from")
        current_wall = walls.get(str(balcony.get("parentWall") or ""))
        invalid_elevation = (
            invalid_parent
            or not isinstance(balcony_from, list)
            or len(balcony_from) != 3
            or float(balcony_from[1]) < 1.8
        )
        invalid_horizontal = False
        if current_wall and not invalid_elevation:
            current_length, wall_bottom, wall_top = wall_metrics(current_wall)
            invalid_elevation = not (
                wall_bottom - 0.25 <= float(balcony_from[1]) <= wall_top + 0.25
            )
            invalid_horizontal = (
                float(balcony_from[0]) < 0
                or float(balcony_from[0]) + float(balcony.get("width", 0)) > current_length
            )
        if not invalid_elevation and not invalid_horizontal:
            continue

        width = max(0.8, float(balcony.get("width", 2.4)))
        candidates = []
        for wall_id, wall in walls.items():
            wall_length, wall_bottom, wall_top = wall_metrics(wall)
            if wall_length + 0.01 >= width and wall_top >= 1.8:
                anchor_y = wall_bottom if wall_bottom >= 1.8 else wall_top
                candidates.append((
                    0 if wall_bottom >= 1.8 else 1,
                    0 if "front" in wall_id.lower() else 1,
                    wall_usage.get(wall_id, 0),
                    -wall_length,
                    wall_id,
                    wall_length,
                    anchor_y,
                ))
        if not candidates:
            continue
        _, _, _, _, target_id, target_length, anchor_y = min(candidates)
        old_parent = balcony.get("parentWall")
        old_y = balcony_from[1] if isinstance(balcony_from, list) and len(balcony_from) == 3 else "?"
        along = (
            float(balcony_from[0])
            if isinstance(balcony_from, list) and len(balcony_from) == 3
            else (target_length - width) / 2
        )
        available = max(0.0, target_length - width)
        clearance = min(0.3, available / 2)
        along = round(max(clearance, min(along, available - clearance)), 2)
        balcony["parentWall"] = target_id
        balcony["from"] = [along, round(anchor_y, 2), 0.0]
        wall_usage[target_id] = wall_usage.get(target_id, 0) + 1
        fixes.append(
            f"🔧 [{balcony_id}] 从地面/越界位置 {old_parent}@Y={old_y} "
            f"迁移到 {target_id}@Y={anchor_y:.2f}"
        )
    
    if not fixes:
        return f"✅ 阳台无需修复 ({len(balconies)} 个阳台)"
    
    return "\n".join(fixes)


def validate_light_placement(blueprint: dict) -> str:
    """校验灯具配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    lights = [c for c in components if c.get("type") == "light"]
    
    if not lights:
        return "⚠️ 没有灯具"
    
    issues = []
    for light in lights:
        light_id = light.get("id", "?")
        position = light.get("position", [])
        initially_on = light.get("initiallyOn")

        if not position or len(position) != 3:
            issues.append(f"❌ [{light_id}] position 必须是 [x,y,z] 坐标")
        else:
            try:
                coords = [float(value) for value in position]
            except (TypeError, ValueError):
                issues.append(f"❌ [{light_id}] position 坐标必须是有限数值")
                coords = []
            if coords:
                if not all(abs(value) <= 1e6 for value in coords):
                    issues.append(f"❌ [{light_id}] position 坐标超出合理范围")
                if coords[1] < -0.1:
                    issues.append(f"❌ [{light_id}] position[1]（高度）为负，灯具埋入地下")

        if initially_on is None:
            issues.append(f"❌ [{light_id}] initiallyOn 必填")
    
    if not issues:
        return f"✅ 灯具校验通过 ({len(lights)} 个灯具)"
    
    return "\n".join(issues)


def fix_light_placement(blueprint: dict) -> str:
    """修复灯具配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    lights = [c for c in components if c.get("type") == "light"]
    
    if not lights:
        return "⚠️ 没有灯具"
    
    fixes = []
    for light in lights:
        light_id = light.get("id", "?")
        
        if not light.get("position") or len(light.get("position", [])) != 3:
            light["position"] = [0, 3, 0]
            fixes.append(f"🔧 [{light_id}] position 设置为 [0, 3, 0]")
        
        if light.get("initiallyOn") is None:
            light["initiallyOn"] = True
            fixes.append(f"🔧 [{light_id}] initiallyOn 设置为 true")
    
    if not fixes:
        return f"✅ 灯具无需修复 ({len(lights)} 个灯具)"
    
    return "\n".join(fixes)


def _resolve_core_shaft(blueprint: dict) -> dict | None:
    """从骨架的 `wall_core_*` 推导电梯井的可用停靠位、层高与层数。

    `wall_core_*` 是骨架 `core_and_stair` 生成的核心筒：四壁加一道中间分隔墙。
    双联井时分隔墙把井道切成左右两格，**轿厢只能落在其中一格**里 —— 把位置夹到
    整个井道的几何中心会让轿厢骑在分隔墙上，看起来"电梯装不进去"。

    返回 ``{"bays": [(x0, x1, z0, z1), …], "floor_height": float|None,
    "floor_count": int|None}``；骨架没有核心筒时返回 ``None``（此时电梯没有
    井道可依托，属能力缺失，只标记不阻断）。
    """

    geometry = blueprint.get("geometry") or {}
    elements = geometry.get("elements") or []
    walls = [
        element for element in elements
        if isinstance(element, dict)
        and element.get("type") == "wall"
        and str(element.get("id") or "").startswith("wall_core_")
    ]
    if not walls:
        return None

    wall_thickness = 0.2
    xs: list[float] = []
    zs: list[float] = []
    base_levels: set[float] = set()
    top_levels: set[float] = set()
    partition_axis: float | None = None
    partition_axis_z: float | None = None
    for wall in walls:
        frm, to = wall.get("from"), wall.get("to")
        if not isinstance(frm, list) or not isinstance(to, list):
            continue
        try:
            fx, fy, fz = float(frm[0]), float(frm[1]), float(frm[2])
            tx, ty, tz = float(to[0]), float(to[1]), float(to[2])
        except (TypeError, ValueError):
            continue
        xs.extend((fx, tx))
        zs.extend((fz, tz))
        base_levels.add(round(fy, 3))
        top_levels.add(round(ty, 3))
        if "partition" not in str(wall.get("id") or ""):
            continue
        # 分隔墙垂直于候梯面：井道沿 z 排布时它立在某个 x 上（跨 z），
        # 沿 x 排布时它卧在某个 z 上（跨 x）。两个朝向都要认，否则长轴沿 x 的
        # 双联井会被当成"一整格"，轿厢骑在分隔墙上。
        if abs(tx - fx) < 1e-6:
            partition_axis = fx
        elif abs(tz - fz) < 1e-6:
            partition_axis_z = fz
    if not xs or not zs:
        return None

    shaft_x0, shaft_x1 = min(xs) + wall_thickness, max(xs) - wall_thickness
    shaft_z0, shaft_z1 = min(zs) + wall_thickness, max(zs) - wall_thickness
    if shaft_x1 - shaft_x0 <= 0.2 or shaft_z1 - shaft_z0 <= 0.2:
        return None

    gap = wall_thickness / 2
    bays: list[tuple[float, float, float, float]]
    if partition_axis is not None and shaft_x0 < partition_axis < shaft_x1:
        spans = [
            (shaft_x0, partition_axis - gap),
            (partition_axis + gap, shaft_x1),
        ]
        bays = [
            (x0, x1, shaft_z0, shaft_z1)
            for x0, x1 in spans
            if x1 - x0 > 0.2
        ]
    elif partition_axis_z is not None and shaft_z0 < partition_axis_z < shaft_z1:
        spans = [
            (shaft_z0, partition_axis_z - gap),
            (partition_axis_z + gap, shaft_z1),
        ]
        bays = [
            (shaft_x0, shaft_x1, z0, z1)
            for z0, z1 in spans
            if z1 - z0 > 0.2
        ]
    else:
        bays = [(shaft_x0, shaft_x1, shaft_z0, shaft_z1)]
    if not bays:
        return None

    ordered_levels = sorted(base_levels)
    floor_count = len(ordered_levels) or None
    floor_height = None
    if len(ordered_levels) >= 2:
        floor_height = round(
            (ordered_levels[-1] - ordered_levels[0]) / (len(ordered_levels) - 1), 3,
        )
    elif ordered_levels and top_levels:
        floor_height = round(max(top_levels) - ordered_levels[0], 3)
    return {"bays": bays, "floor_height": floor_height, "floor_count": floor_count}


def _cab_fits_bay(
    position: object,
    width: float,
    depth: float,
    bays: list[tuple[float, float, float, float]],
    *,
    tolerance: float,
) -> bool:
    """轿厢占地是否完整落在**某一格**井道净空内。"""

    if not isinstance(position, list) or len(position) != 3:
        return False
    try:
        cx, cz = float(position[0]), float(position[2])
    except (TypeError, ValueError):
        return False
    half_x, half_z = float(width) / 2, float(depth) / 2
    return any(
        cx - half_x >= x0 - tolerance and cx + half_x <= x1 + tolerance
        and cz - half_z >= z0 - tolerance and cz + half_z <= z1 + tolerance
        for x0, x1, z0, z1 in bays
    )


def validate_elevator_placement(blueprint: dict) -> str:
    """校验电梯组件：尺寸、层数与初始楼层（详细字段校验见 spatial_tools 的元素级必填表）"""
    components = blueprint.get("geometry", {}).get("components", [])
    elevators = [c for c in components if c.get("type") == "elevator"]

    if not elevators:
        return "⚠️ 没有电梯"

    shaft = _resolve_core_shaft(blueprint)
    issues = []
    shaft_warning_added = False
    for elevator in elevators:
        elevator_id = elevator.get("id", "?")
        floor_height = elevator.get("floorHeight")
        floor_count = elevator.get("floorCount")

        if not isinstance(floor_height, (int, float)) or isinstance(floor_height, bool) or floor_height <= 0:
            issues.append(f"❌ [{elevator_id}] floorHeight 必须是正数（与建筑层高一致）")
        if not isinstance(floor_count, int) or isinstance(floor_count, bool) or floor_count < 1:
            issues.append(f"❌ [{elevator_id}] floorCount 必须是 ≥1 的整数（井道跨越层数）")

        dims = elevator.get("dimensions") or {}
        width = dims.get("width", 0)
        depth = dims.get("depth", 0)
        if isinstance(floor_height, (int, float)) and not isinstance(floor_height, bool):
            cab_height = dims.get("height", 0)
            if isinstance(cab_height, (int, float)) and not isinstance(cab_height, bool) and cab_height >= floor_height:
                issues.append(
                    f"❌ [{elevator_id}] dimensions.height({cab_height}) 必须小于 floorHeight({floor_height})，否则轿厢无法在本层停靠"
                )
        if isinstance(width, (int, float)) and not isinstance(width, bool) and width > 2.6:
            issues.append(f"⚠️ [{elevator_id}] dimensions.width({width}) 超过常见轿厢上限（住宅梯约 1.6m）")
        if isinstance(depth, (int, float)) and not isinstance(depth, bool) and depth > 2.6:
            issues.append(f"⚠️ [{elevator_id}] dimensions.depth({depth}) 超过常见轿厢上限（住宅梯约 1.8m）")

        initial_floor = elevator.get("initialFloor")
        if initial_floor is not None and isinstance(floor_count, int) and not isinstance(floor_count, bool):
            if not isinstance(initial_floor, int) or isinstance(initial_floor, bool) or not (0 <= initial_floor < floor_count):
                issues.append(f"❌ [{elevator_id}] initialFloor 必须落在 [0, floorCount) 内")

        # 井道对齐：轿厢是"装在井里"的设备，停靠位由骨架决定，不是模型的自由创作。
        if shaft is None:
            if not shaft_warning_added:
                issues.append(
                    "⚠️ 骨架没有 wall_core_* 井道围合，无法核对轿厢停靠位置"
                    "（电梯应与 core_and_stair 核心筒配套）"
                )
                shaft_warning_added = True
        elif (
            isinstance(width, (int, float)) and not isinstance(width, bool) and width > 0
            and isinstance(depth, (int, float)) and not isinstance(depth, bool) and depth > 0
            and not _cab_fits_bay(
                elevator.get("position"), width, depth, shaft["bays"], tolerance=0.02,
            )
        ):
            bay = shaft["bays"][0]
            issues.append(
                f"❌ [{elevator_id}] 轿厢占地不在 wall_core_* 井道净空内"
                f"（可用井格 x∈[{bay[0]:.2f}, {bay[1]:.2f}]，z∈[{bay[2]:.2f}, {bay[3]:.2f}]）"
                "，可由骨架确定性对齐"
            )

    if not issues:
        return f"✅ 电梯校验通过 ({len(elevators)} 台电梯)"

    return "\n".join(issues)


def fix_elevator_placement(blueprint: dict) -> str:
    """修复电梯配置：补默认尺寸/层高，收敛非法 initialFloor"""
    components = blueprint.get("geometry", {}).get("components", [])
    elevators = [c for c in components if c.get("type") == "elevator"]

    if not elevators:
        return "⚠️ 没有电梯"

    shaft = _resolve_core_shaft(blueprint)
    fixes = []
    for elevator in elevators:
        elevator_id = elevator.get("id", "?")

        dims = elevator.get("dimensions")
        if not isinstance(dims, dict) or not isinstance(dims.get("width"), (int, float)):
            elevator["dimensions"] = {"width": 1.4, "depth": 1.6, "height": 2.2}
            fixes.append(f"🔧 [{elevator_id}] dimensions 设置为 {{width: 1.4, depth: 1.6, height: 2.2}}")

        floor_height = elevator.get("floorHeight")
        if not isinstance(floor_height, (int, float)) or isinstance(floor_height, bool) or floor_height <= 0:
            elevator["floorHeight"] = 3.3
            fixes.append(f"🔧 [{elevator_id}] floorHeight 设置为 3.3（默认层高）")

        floor_count = elevator.get("floorCount")
        if not isinstance(floor_count, int) or isinstance(floor_count, bool) or floor_count < 1:
            elevator["floorCount"] = 1
            fixes.append(f"🔧 [{elevator_id}] floorCount 设置为 1")

        cab_height = (elevator.get("dimensions") or {}).get("height")
        if (
            isinstance(cab_height, (int, float)) and not isinstance(cab_height, bool)
            and isinstance(elevator.get("floorHeight"), (int, float))
            and cab_height >= elevator["floorHeight"]
        ):
            elevator["dimensions"]["height"] = elevator["floorHeight"] - 0.15
            fixes.append(f"🔧 [{elevator_id}] dimensions.height 压缩至 floorHeight-0.15，保证轿厢可停靠")

        # ── 井道确定性对齐 ──
        # 骨架井道与电梯组件是两条独立生成的路径，模型无从知道 wall_core_* 的真实
        # 坐标。所以停靠位不靠模型算，而是从骨架反推：取最近的一格井，把轿厢居中
        # 放进去，尺寸夹到该格净空以内，层高与层数一并与骨架对齐。
        if shaft is not None:
            if shaft.get("floor_height") and elevator.get("floorHeight") != shaft["floor_height"]:
                elevator["floorHeight"] = shaft["floor_height"]
                fixes.append(
                    f"🔧 [{elevator_id}] floorHeight 对齐骨架层高 {shaft['floor_height']}"
                )
            if shaft.get("floor_count") and elevator.get("floorCount") != shaft["floor_count"]:
                elevator["floorCount"] = shaft["floor_count"]
                fixes.append(
                    f"🔧 [{elevator_id}] floorCount 对齐井道层数 {shaft['floor_count']}"
                )

            position = elevator.get("position")
            if not isinstance(position, list) or len(position) != 3:
                position = [0.0, 0.0, 0.0]
                fixes.append(f"🔧 [{elevator_id}] position 缺失，按井道重建")
            coords = [
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else 0.0
                for value in position
            ]
            bay = min(
                shaft["bays"],
                key=lambda item: abs(coords[0] - (item[0] + item[1]) / 2),
            )
            bx0, bx1, bz0, bz1 = bay
            available_x = max(0.6, (bx1 - bx0) - 0.1)
            available_z = max(0.6, (bz1 - bz0) - 0.1)

            dims_now = elevator.get("dimensions")
            if not isinstance(dims_now, dict):
                dims_now = {"width": 1.4, "depth": 1.6, "height": 2.2}
                elevator["dimensions"] = dims_now
            cab_width = dims_now.get("width")
            cab_width = (
                float(cab_width)
                if isinstance(cab_width, (int, float)) and not isinstance(cab_width, bool) and cab_width > 0
                else 1.4
            )
            cab_depth = dims_now.get("depth")
            cab_depth = (
                float(cab_depth)
                if isinstance(cab_depth, (int, float)) and not isinstance(cab_depth, bool) and cab_depth > 0
                else 1.6
            )
            if cab_width > available_x:
                fixes.append(
                    f"🔧 [{elevator_id}] dimensions.width {cab_width} → {available_x:.2f}（井道净空）"
                )
                cab_width = available_x
            if cab_depth > available_z:
                fixes.append(
                    f"🔧 [{elevator_id}] dimensions.depth {cab_depth} → {available_z:.2f}（井道净空）"
                )
                cab_depth = available_z
            dims_now["width"] = round(cab_width, 3)
            dims_now["depth"] = round(cab_depth, 3)

            target_x = round((bx0 + bx1) / 2, 3)
            target_z = round((bz0 + bz1) / 2, 3)
            target_y = coords[1]
            step = elevator.get("floorHeight")
            floor_total = elevator.get("floorCount")
            if (
                isinstance(step, (int, float)) and not isinstance(step, bool) and step > 0
                and isinstance(floor_total, int) and not isinstance(floor_total, bool)
                and floor_total >= 1
            ):
                index = min(max(round(coords[1] / step), 0), floor_total - 1)
                target_y = round(index * step, 3)
            if (
                round(coords[0], 3) != target_x
                or round(coords[2], 3) != target_z
                or round(coords[1], 3) != target_y
            ):
                elevator["position"] = [target_x, target_y, target_z]
                fixes.append(
                    f"🔧 [{elevator_id}] 轿厢对齐到井格中心 [{target_x}, {target_y}, {target_z}]"
                )

        # initialFloor 的合法性必须在**层数对齐之后**判定：上面可能刚把 floorCount
        # 从模型给的层数收敛到井道真实层数，用旧层数校验会漏掉越界的初始楼层
        # （实测 floorCount 5→2 后 initialFloor=4 仍然留着）。
        initial_floor = elevator.get("initialFloor")
        if initial_floor is not None:
            floor_count_now = elevator.get("floorCount")
            if (
                not isinstance(initial_floor, int)
                or isinstance(initial_floor, bool)
                or not isinstance(floor_count_now, int)
                or isinstance(floor_count_now, bool)
                or not (0 <= initial_floor < floor_count_now)
            ):
                elevator["initialFloor"] = 0
                fixes.append(f"🔧 [{elevator_id}] initialFloor 收敛为 0")

    if not fixes:
        return f"✅ 电梯无需修复 ({len(elevators)} 台电梯)"

    return "\n".join(fixes)


def validate_ramp_placement(blueprint: dict) -> str:
    """校验坡道配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    ramps = [c for c in components if c.get("type") == "ramp"]
    
    if not ramps:
        return "⚠️ 没有坡道"
    
    issues = []
    for ramp in ramps:
        ramp_id = ramp.get("id", "?")
        frm = ramp.get("from", [])
        to = ramp.get("to", [])
        width = ramp.get("width", 0)
        
        if not frm or len(frm) != 3:
            issues.append(f"❌ [{ramp_id}] from 必须是 [x,y,z]")
        
        if not to or len(to) != 3:
            issues.append(f"❌ [{ramp_id}] to 必须是 [x,y,z]")
        
        if frm and to and len(frm) == 3 and len(to) == 3:
            if abs(frm[1] - to[1]) < 0.1:
                issues.append(f"❌ [{ramp_id}] from/to 高度差过小 ({abs(frm[1] - to[1]):.2f}m)")
        
        if width <= 0:
            issues.append(f"❌ [{ramp_id}] width {width} 必须大于 0")
    
    if not issues:
        return f"✅ 坡道校验通过 ({len(ramps)} 个坡道)"
    
    return "\n".join(issues)


def fix_ramp_placement(blueprint: dict) -> str:
    """修复坡道配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    ramps = [c for c in components if c.get("type") == "ramp"]
    
    if not ramps:
        return "⚠️ 没有坡道"
    
    fixes = []
    for ramp in ramps:
        ramp_id = ramp.get("id", "?")
        
        if not ramp.get("from") or len(ramp.get("from", [])) != 3:
            ramp["from"] = [0, 0, 0]
            fixes.append(f"🔧 [{ramp_id}] from 设置为 [0, 0, 0]")
        
        if not ramp.get("to") or len(ramp.get("to", [])) != 3:
            ramp["to"] = [3, 0.5, 0]
            fixes.append(f"🔧 [{ramp_id}] to 设置为 [3, 0.5, 0]")
        
        if ramp.get("width", 0) <= 0:
            ramp["width"] = 1.5
            fixes.append(f"🔧 [{ramp_id}] width 设置为 1.5m")
        
        if not ramp.get("thickness"):
            ramp["thickness"] = 0.15
            fixes.append(f"🔧 [{ramp_id}] thickness 设置为 0.15m")
    
    if not fixes:
        return f"✅ 坡道无需修复 ({len(ramps)} 个坡道)"
    
    return "\n".join(fixes)


def validate_bay_window_placement(blueprint: dict) -> str:
    """校验凸窗配置"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    bay_windows = [c for c in components if c.get("type") == "bay_window"]
    
    if not bay_windows:
        return "⚠️ 没有凸窗"
    
    issues = []
    for bay_window in bay_windows:
        bw_id = bay_window.get("id", "?")
        parent_wall = bay_window.get("parentWall")
        projection_depth = bay_window.get("projectionDepth", 0)
        
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{bw_id}] parentWall '{parent_wall}' 不存在")
        
        if projection_depth <= 0:
            issues.append(f"❌ [{bw_id}] projectionDepth {projection_depth} 必须大于 0")
    
    if not issues:
        return f"✅ 凸窗校验通过 ({len(bay_windows)} 个凸窗)"
    
    return "\n".join(issues)


def fix_bay_window_placement(blueprint: dict) -> str:
    """修复凸窗配置"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    
    walls = {w["id"]: w for w in elements if w.get("type") == "wall"}
    if not walls:
        return "⚠️ 没有墙体，无法修复凸窗"
    
    bay_windows = [c for c in components if c.get("type") == "bay_window"]
    
    fixes = []
    for bay_window in bay_windows:
        bw_id = bay_window.get("id", "?")
        parent_wall = bay_window.get("parentWall")
        
        if not parent_wall or parent_wall not in walls:
            new_wall = list(walls.keys())[0]
            bay_window["parentWall"] = new_wall
            fixes.append(f"🔧 [{bw_id}] parentWall 修正为 {new_wall}")
        
        if bay_window.get("projectionDepth", 0) <= 0:
            bay_window["projectionDepth"] = 0.8
            fixes.append(f"🔧 [{bw_id}] projectionDepth 设置为 0.8m")
    
    if not fixes:
        return f"✅ 凸窗无需修复 ({len(bay_windows)} 个凸窗)"
    
    return "\n".join(fixes)


def validate_cornice_placement(blueprint: dict) -> str:
    """校验檐口配置：path/profile 存在性 + 几何合理性。

    除“至少 N 个点”外，还检查 path 每段长度、profile 是否退化（共线），
    避免产出“合法但错误”的零长度/退化截面。
    """
    components = blueprint.get("geometry", {}).get("components", [])
    cornices = [c for c in components if c.get("type") == "cornice"]

    if not cornices:
        return "⚠️ 没有檐口"

    issues = []
    for cornice in cornices:
        cornice_id = cornice.get("id", "?")
        path = cornice.get("path", [])
        profile = cornice.get("profile", [])

        if len(path) < 2:
            issues.append(f"❌ [{cornice_id}] path 至少需要 2 个点，当前: {len(path)}")
        else:
            total_length = 0.0
            for index in range(len(path) - 1):
                p1, p2 = path[index], path[index + 1]
                if (
                    not isinstance(p1, (list, tuple)) or len(p1) < 3
                    or not isinstance(p2, (list, tuple)) or len(p2) < 3
                ):
                    continue
                seg_length = (
                    (float(p2[0]) - float(p1[0])) ** 2
                    + (float(p2[1]) - float(p1[1])) ** 2
                    + (float(p2[2]) - float(p1[2])) ** 2
                ) ** 0.5
                total_length += seg_length
            if total_length < 0.05:
                issues.append(
                    f"❌ [{cornice_id}] path 总长度过短 ({total_length:.2f}m)，"
                    f"檐口无法形成可见轮廓"
                )

        if len(profile) < 3:
            issues.append(f"❌ [{cornice_id}] profile 至少需要 3 个点，当前: {len(profile)}")
        elif _profile_is_degenerate(profile):
            issues.append(f"❌ [{cornice_id}] profile 退化为直线，无法形成飞檐截面")

    if not issues:
        return f"✅ 檐口校验通过 ({len(cornices)} 个檐口)"

    return "\n".join(issues)


def _profile_is_degenerate(profile: list) -> bool:
    """判断 2D 截面是否退化（所有点共线、面积为零）。"""
    try:
        points = [(float(p[0]), float(p[1])) for p in profile if isinstance(p, (list, tuple)) and len(p) >= 2]
    except (TypeError, ValueError):
        return True
    if len(points) < 3:
        return True
    area = 0.0
    for index in range(len(points)):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) < 1e-6


def fix_cornice_placement(blueprint: dict) -> str:
    """修复檐口配置：按宿主屋顶范围推导保守默认 path，不再写死任意坐标。"""
    components = blueprint.get("geometry", {}).get("components", [])
    cornices = [c for c in components if c.get("type") == "cornice"]

    if not cornices:
        return "⚠️ 没有檐口"

    roofs = [
        element for element in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(element, dict) and element.get("type") == "roof"
    ]

    def _default_path_for(cornice: dict) -> list:
        # 优先用宿主屋顶的 span/depth 推导；无宿主则退回紧凑默认。
        parent_roof = cornice.get("parentRoof")
        for roof in roofs:
            if parent_roof and str(roof.get("id") or "") != str(parent_roof):
                continue
            try:
                span = float(roof.get("span") or 0.0)
                depth = float(roof.get("depth") or 0.0)
                position = roof.get("position")
                if span > 0.5 and depth > 0.5 and isinstance(position, list) and len(position) >= 3:
                    half_x = span / 2.0
                    return [
                        [round(float(position[0]) - half_x, 3), round(float(position[1]) or 0.0, 3), round(float(position[2]) - depth / 2.0, 3)],
                        [round(float(position[0]) + half_x, 3), round(float(position[1]) or 0.0, 3), round(float(position[2]) - depth / 2.0, 3)],
                    ]
            except (TypeError, ValueError):
                continue
        return [[0, 0, 0], [5, 0, 0]]

    fixes = []
    for cornice in cornices:
        cornice_id = cornice.get("id", "?")

        if len(cornice.get("path", [])) < 2:
            cornice["path"] = _default_path_for(cornice)
            fixes.append(f"🔧 [{cornice_id}] 按宿主屋顶范围设置 path")

        if len(cornice.get("profile", [])) < 3:
            # 简单的飞檐截面
            cornice["profile"] = [[0, 0], [0.3, 0], [0.3, 0.2], [0, 0.2]]
            fixes.append(f"🔧 [{cornice_id}] 添加默认 profile")

    if not fixes:
        return f"✅ 檐口无需修复 ({len(cornices)} 个檐口)"

    return "\n".join(fixes)


def validate_chimney_placement(blueprint: dict) -> str:
    """校验烟囱配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    chimneys = [c for c in components if c.get("type") == "chimney"]
    
    if not chimneys:
        return "⚠️ 没有烟囱"
    
    issues = []
    for chimney in chimneys:
        chimney_id = chimney.get("id", "?")
        position = chimney.get("position", [])
        width = chimney.get("width", 0)
        depth = chimney.get("depth", 0)
        height = chimney.get("height", 0)
        
        if not position or len(position) != 3:
            issues.append(f"❌ [{chimney_id}] position 必须是 [x,y,z]")
        
        if width <= 0:
            issues.append(f"❌ [{chimney_id}] width {width} 必须大于 0")
        
        if depth <= 0:
            issues.append(f"❌ [{chimney_id}] depth {depth} 必须大于 0")
        
        if height <= 0:
            issues.append(f"❌ [{chimney_id}] height {height} 必须大于 0")
    
    if not issues:
        return f"✅ 烟囱校验通过 ({len(chimneys)} 个烟囱)"
    
    return "\n".join(issues)


def fix_chimney_placement(blueprint: dict) -> str:
    """修复烟囱配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    chimneys = [c for c in components if c.get("type") == "chimney"]
    
    if not chimneys:
        return "⚠️ 没有烟囱"
    
    fixes = []
    for chimney in chimneys:
        chimney_id = chimney.get("id", "?")
        
        if not chimney.get("position") or len(chimney.get("position", [])) != 3:
            chimney["position"] = [0, 0, 0]
            fixes.append(f"🔧 [{chimney_id}] position 设置为 [0, 0, 0]")
        
        if chimney.get("width", 0) <= 0:
            chimney["width"] = 0.8
            fixes.append(f"🔧 [{chimney_id}] width 设置为 0.8m")
        
        if chimney.get("depth", 0) <= 0:
            chimney["depth"] = 0.8
            fixes.append(f"🔧 [{chimney_id}] depth 设置为 0.8m")
        
        if chimney.get("height", 0) <= 0:
            chimney["height"] = 3.0
            fixes.append(f"🔧 [{chimney_id}] height 设置为 3.0m")
    
    if not fixes:
        return f"✅ 烟囱无需修复 ({len(chimneys)} 个烟囱)"
    
    return "\n".join(fixes)


# ── 组件工具映射表 ──
COMPONENT_TOOLS = {
    "door": {
        "validate": validate_door_placement,
        "fix": fix_door_placement,
    },
    "window": {
        "validate": validate_window_placement,
        "fix": fix_window_placement,
    },
    "roof": {
        "validate": validate_roof_coverage,
        "fix": fix_roof_coverage,
    },
    "railing": {
        "validate": validate_railing_placement,
        "fix": fix_railing_placement,
    },
    "canopy": {
        "validate": validate_canopy_placement,
        "fix": fix_canopy_placement,
    },
    "balcony": {
        "validate": validate_balcony_placement,
        "fix": fix_balcony_placement,
    },
    "light": {
        "validate": validate_light_placement,
        "fix": fix_light_placement,
    },
    "elevator": {
        "validate": validate_elevator_placement,
        "fix": fix_elevator_placement,
    },
    "ramp": {
        "validate": validate_ramp_placement,
        "fix": fix_ramp_placement,
    },
    "bay_window": {
        "validate": validate_bay_window_placement,
        "fix": fix_bay_window_placement,
    },
    "cornice": {
        "validate": validate_cornice_placement,
        "fix": fix_cornice_placement,
    },
    "chimney": {
        "validate": validate_chimney_placement,
        "fix": fix_chimney_placement,
    },
    # furniture 是 elements 原生类型（见 KB《家具参数契约》），复用的是
    # 结构元素通用校验与"底部 Y 对齐行走面"修复——它不是组合构件，
    # 没有门窗户那样的宿主/槽位关系可查。
    "furniture": {
        # `furniture` 是唯一直接复用 spatial_tools 的元素级构件，而那两个名字是
        # `@tool` 装饰过的 `StructuredTool`；本表其余 11 项都是普通函数。
        # `validate_component()` / `fix_component()` 的契约是"取出函数直接调用"
        # （`tools["validate"](blueprint)`），传 StructuredTool 会抛
        # `'StructuredTool' object is not callable` —— 家具条目每次都被判失败，
        # 而它不影响任何建筑构件，所以一直没暴露。
        # 这里取回底层函数保持全表同形；不变量由
        # `tests/agent/test_component_tools_registry.py` 逐项断言。
        "validate": getattr(validate_element_required_fields, "func", validate_element_required_fields),
        "fix": getattr(fix_element_elevations, "func", fix_element_elevations),
    },
    # primitive / body 也是 elements 原生类型，复用结构元素通用校验；
    # 但**修复不能复用** fix_element_elevations：那个函数按"底面中心锚点"
    # 逐件贴楼板，而 primitive/body 的 position 是形体中心锚点，
    # 逐件贴地会把零件压进地面 —— 所以用整组刚性平移的 fix_primitive_elevations。
    "primitive": {
        "validate": getattr(validate_element_required_fields, "func", validate_element_required_fields),
        "fix": getattr(fix_primitive_elevations, "func", fix_primitive_elevations),
    },
    "body": {
        "validate": getattr(validate_element_required_fields, "func", validate_element_required_fields),
        "fix": getattr(fix_primitive_elevations, "func", fix_primitive_elevations),
    },
}


def validate_component(component_type: str, blueprint: dict) -> str:
    """通用组件校验入口"""
    tools = COMPONENT_TOOLS.get(component_type)
    if not tools or "validate" not in tools:
        return f"⚠️ 组件 {component_type} 没有校验工具"
    
    return tools["validate"](blueprint)


def fix_component(component_type: str, blueprint: dict) -> str:
    """通用组件修复入口"""
    tools = COMPONENT_TOOLS.get(component_type)
    if not tools or "fix" not in tools:
        return f"⚠️ 组件 {component_type} 没有修复工具"
    
    return tools["fix"](blueprint)
