"""
组件专用校验/修复工具

每种组件有对应的校验和修复函数：
- validate_<component>: 校验该组件
- fix_<component>: 修复该组件

策略：在节点生成后立即调用，确保对齐
"""
from loguru import logger
from app.tools.spatial_tools import MAX_OPENING_NORMAL_OFFSET


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
    
    # 计算建筑包围盒
    walls = [e for e in elements if e.get("type") == "wall"]
    if not walls:
        return "⚠️ 没有墙体，无法校验屋顶"
    
    min_x = min_z = float('inf')
    max_x = max_z = float('-inf')
    
    for wall in walls:
        frm = wall.get("from", [0, 0, 0])
        to = wall.get("to", [0, 0, 0])
        min_x = min(min_x, frm[0], to[0])
        max_x = max(max_x, frm[0], to[0])
        min_z = min(min_z, frm[2], to[2])
        max_z = max(max_z, frm[2], to[2])
    
    building_width = max_x - min_x
    building_depth = max_z - min_z
    
    issues = []
    for roof in roofs:
        roof_id = roof.get("id", "?")
        roof_span = roof.get("span", 0)
        roof_depth = roof.get("depth", 0)
        
        if roof_span < building_width * 0.9:
            issues.append(f"❌ [{roof_id}] span {roof_span:.2f}m < 建筑宽度 {building_width:.2f}m")
        
        if roof_depth < building_depth * 0.9:
            issues.append(f"❌ [{roof_id}] depth {roof_depth:.2f}m < 建筑深度 {building_depth:.2f}m")
    
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
    
    # 计算建筑包围盒
    min_x = min_z = float('inf')
    max_x = max_z = float('-inf')
    max_y = 0
    
    for wall in walls:
        frm = wall.get("from", [0, 0, 0])
        to = wall.get("to", [0, 0, 0])
        min_x = min(min_x, frm[0], to[0])
        max_x = max(max_x, frm[0], to[0])
        min_z = min(min_z, frm[2], to[2])
        max_z = max(max_z, frm[2], to[2])
        max_y = max(max_y, frm[1], to[1])
    
    building_width = max_x - min_x
    building_depth = max_z - min_z
    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2
    
    fixes = []
    for roof in roofs:
        roof_id = roof.get("id", "?")
        
        # 扩大 10% 确保覆盖
        roof["span"] = building_width * 1.1
        roof["depth"] = building_depth * 1.1
        
        # 设置中心位置
        if not roof.get("position"):
            roof["position"] = [center_x, max_y, center_z]
        
        fixes.append(f"🔧 [{roof_id}] 调整为 {roof['span']:.2f}×{roof['depth']:.2f}m, 中心=[{center_x:.2f}, {max_y:.2f}, {center_z:.2f}]")
    
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
    for canopy in canopies:
        canopy_id = canopy.get("id", "?")
        parent_wall = canopy.get("parentWall")
        depth = canopy.get("depth", 0)
        thickness = canopy.get("thickness", 0)
        
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{canopy_id}] parentWall '{parent_wall}' 不存在")
        
        if depth <= 0:
            issues.append(f"❌ [{canopy_id}] depth {depth} 必须大于 0")
        
        if thickness <= 0:
            issues.append(f"❌ [{canopy_id}] thickness {thickness} 必须大于 0")
    
    if not issues:
        return f"✅ 雨棚校验通过 ({len(canopies)} 个雨棚)"
    
    return "\n".join(issues)


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
    """校验阳台配置"""
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
        
        if not parent_wall or parent_wall not in walls:
            issues.append(f"❌ [{balcony_id}] parentWall '{parent_wall}' 不存在")
        
        if slab_thickness <= 0:
            issues.append(f"❌ [{balcony_id}] slabThickness {slab_thickness} 必须大于 0")
    
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
    
    fixes = []
    for balcony in balconies:
        balcony_id = balcony.get("id", "?")
        parent_wall = balcony.get("parentWall")
        
        if not parent_wall or parent_wall not in walls:
            new_wall = list(walls.keys())[0]
            balcony["parentWall"] = new_wall
            fixes.append(f"🔧 [{balcony_id}] parentWall 修正为 {new_wall}")
        
        if balcony.get("slabThickness", 0) <= 0:
            balcony["slabThickness"] = 0.15
            fixes.append(f"🔧 [{balcony_id}] slabThickness 设置为 0.15m")
    
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
    """校验檐口配置"""
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
        
        if len(profile) < 3:
            issues.append(f"❌ [{cornice_id}] profile 至少需要 3 个点，当前: {len(profile)}")
    
    if not issues:
        return f"✅ 檐口校验通过 ({len(cornices)} 个檐口)"
    
    return "\n".join(issues)


def fix_cornice_placement(blueprint: dict) -> str:
    """修复檐口配置"""
    components = blueprint.get("geometry", {}).get("components", [])
    cornices = [c for c in components if c.get("type") == "cornice"]
    
    if not cornices:
        return "⚠️ 没有檐口"
    
    fixes = []
    for cornice in cornices:
        cornice_id = cornice.get("id", "?")
        
        if len(cornice.get("path", [])) < 2:
            cornice["path"] = [[0, 0, 0], [5, 0, 0]]
            fixes.append(f"🔧 [{cornice_id}] 添加默认 path")
        
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
