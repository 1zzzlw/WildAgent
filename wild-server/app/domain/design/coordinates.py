"""体量起点坐标与总体尺寸控制；不把世界原点当场地边界。"""
import json
from math import hypot, isfinite


class DesignCoordinateConflict(ValueError):
    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__(json.dumps({"code": "design_coordinate_conflict", "conflicts": conflicts}, ensure_ascii=False))


def volume_conflicts(volumes: list[dict], massing: dict) -> list[dict]:
    """massing 宽深是总体包络控制上限；差值比较对整体平移不变。"""
    if not volumes:
        return []
    conflicts = []
    for axis, extent in (("x", "width"), ("z", "depth")):
        low = min(v[axis] for v in volumes)
        high = max(v[axis] + v[extent] for v in volumes)
        if high - low > massing[extent] + 0.001:
            conflicts.append({"path": "/decisions/volumes", "value": volumes,
                "conflict_path": "/decisions/massing/" + extent,
                "conflict_value": massing[extent], "actual_extent": high - low,
                "reason": "体量并集包围盒超出总体尺寸控制；必须显式修订，不能裁剪体量"})
    for index, v in enumerate(volumes):
        if v["end_floor"] > massing["modeled_floors"]:
            conflicts.append({"path": f"/decisions/volumes/{index}/end_floor", "value": v["end_floor"],
                "conflict_path": "/decisions/massing/modeled_floors",
                "conflict_value": massing["modeled_floors"], "reason": "体量楼层超出建模层数"})
    return conflicts



def representative_floor_indices(massing):
    count, floors = massing.modeled_floors, massing.floors
    if massing.representation_mode == "schematic" and count > 1:
        return [1 + round(i*(floors-1)/(count-1)) for i in range(count)]
    return list(range(1, count+1))


def floor_elevations(design):
    """同一图纸的楼面世界标高；显式 level 优先，未声明时沿用层高。"""
    if design.get("levels"):
        levels = {}
        roof = []
        for level in design["levels"]:
            levels[level["id"]] = level["elevation"]
            if level.get("index") is not None:
                levels[level["index"]] = level["elevation"]
            if level["kind"] == "roof":
                roof.append(level["elevation"])
        if roof:
            levels[design["massing"]["floors"]+1] = max(roof)
        return levels
    height, count = design["massing"]["floor_height"], design["massing"]["floors"]
    explicit = {}
    layouts = design.get("floor_layouts") or []
    if not isinstance(layouts, list):
        raise ValueError("/floor_layouts：逐层布局必须是对象数组")
    for index, layout in enumerate(layouts):
        if not isinstance(layout, dict):
            raise ValueError(f"/floor_layouts/{index}：每层布局必须是对象")
        for key in ("rooms", "walls"):
            if not isinstance(layout.get(key, []), list) or any(not isinstance(item, dict) for item in layout.get(key, [])):
                raise ValueError(f"/floor_layouts/{index}/{key}：必须是对象数组")
        if "floor" not in layout or layout.get("level") is None:
            continue
        floor, level = layout["floor"], layout["level"]
        if isinstance(floor, bool) or not isinstance(floor, int) or not 1 <= floor <= count:
            raise ValueError(f"/floor_layouts/{index}/floor：楼层必须是 1～{count} 的整数")
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not isfinite(level):
            raise ValueError(f"/floor_layouts/{index}/level：楼面世界标高必须是有限数字")
        if floor in explicit and explicit[floor] != level:
            raise ValueError(f"/floor_layouts/{index}/level：同一楼层声明了不同标高")
        explicit[floor] = level
    base = explicit.get(1, 0)
    levels = {i: explicit.get(i, base+(i-1)*height) for i in range(1, count+1)}
    levels[count+1] = levels[count]+height
    if any(levels[i+1] <= levels[i] for i in range(1, count)):
        raise ValueError("/floor_layouts：上层楼面标高必须高于下层；显式修订，不能覆盖已声明标高")
    return levels


def floor_connection_targets(design, component):
    """明确楼层引用的唯一标高来源；未声明连接时不猜测。"""
    levels = floor_elevations(design)
    count = design["massing"]["floors"]
    targets, issues = [], []
    for index, connection in enumerate(component.get("floor_connections") or []):
        if connection.get("from_level"):
            lower,upper = connection["from_level"],connection["to_level"]
            if lower not in levels or upper not in levels or levels[upper] <= levels[lower]:
                issues.append({"code":"floor_connection_reference","path":f"/floor_connections/{index}",
                               "actual":connection,"reason":"连接标高不存在或终点不高于起点"})
                continue
            targets.append({**connection,"from_floor":lower,"to_floor":upper,"from_y":levels[lower],
                            "to_y":levels[upper],"rise":levels[upper]-levels[lower]})
            continue
        lower, upper = connection["from_floor"], connection["to_floor"]
        destination = count + 1 if upper == "roof" else upper
        if lower > count or destination > count + (upper == "roof") or destination <= lower:
            issues.append({"code": "floor_connection_reference", "path": f"/floor_connections/{index}",
                           "expected": f"1～{count} 层的递增连接或显式 roof", "actual": connection,
                           "reason": "连接楼层不存在或上层不高于下层"})
            continue
        targets.append({**connection, "from_y": levels[lower], "to_y": levels[destination],
                        "rise": levels[destination] - levels[lower]})
    return targets, issues


def design_geometry_context(design):
    """所有节点共用已解析的轮廓、标高和宿主；禁止各自从宽深重算建筑。"""
    if design.get("geometry_context"):
        return design["geometry_context"]
    from app.domain.design.spatial import resolve_geometry

    result = resolve_geometry(design)
    return {key:value for key,value in result.items() if key not in {"source","body_geometry"}}


def stair_span_conflicts(design):
    """只核对显式数值能否落在已声明的楼面之间，不推断楼梯造型。"""
    from app.domain.components.names import resolve_component_name

    levels = floor_elevations(design)
    numeric_levels = [value for key,value in levels.items() if isinstance(key,int) and key <= design["massing"]["floors"]]
    highest_floor = max(numeric_levels)
    available_rise = highest_floor - min(numeric_levels)
    issues = []
    for index, component in enumerate(design.get("components") or []):
        if resolve_component_name(component.get("type", ""))["entity_type"] != "stair":
            continue
        form = component.get("form") if isinstance(component.get("form"), dict) else {}
        targets, _ = floor_connection_targets(design, component)
        if targets:
            available_rise = max(t["to_y"] for t in targets) - min(t["from_y"] for t in targets)
        elif form.get("roof_access") is True or design["massing"]["floors"] < 2:
            continue
        else:
            available_rise = highest_floor - levels[1]
        size = component.get("size") if isinstance(component.get("size"), dict) else {}
        height = size.get("height")
        if isinstance(height, (int, float)) and not isinstance(height, bool) and height > available_rise + 0.25:
            issues.append(f"/components/{index}/size/height：楼梯高 {height:g}m 超过连接楼面高差 "
                          f"{available_rise:g}m；核对连接楼层，屋面通行须显式写 form.roof_access")
        elif targets and isinstance(height, (int, float)) and not isinstance(height, bool) and height < available_rise - 0.25:
            issues.append(f"/components/{index}/size/height：楼梯 {component.get('id', index)} 高 {height:g}m，"
                          f"不足以覆盖 /components/{index}/floor_connections 声明的楼面高差 {available_rise:g}m；"
                          f"实际连接标高为 {[(t['from_y'], t['to_y']) for t in targets]}。"
                          "显式修订楼梯尺寸、梯段或连接设计，不交给执行节点拉伸楼梯")
        if all(isinstance(form.get(key), (int, float)) and not isinstance(form[key], bool)
               for key in ("flights", "rises", "riser_height")):
            total_rise = form["flights"] * form["rises"] * form["riser_height"]
            if total_rise > available_rise + 0.25:
                issues.append(f"/components/{index}/form：梯段数×每跑级数×踏步高={total_rise:g}m，"
                              f"超过首层至顶层楼面高差 {available_rise:g}m；修订楼梯连接或踏步参数")
            elif targets and total_rise < available_rise - 0.25:
                issues.append(f"/components/{index}/form：踏步总高差 {total_rise:g}m 小于明确连接楼面高差 "
                              f"{available_rise:g}m；核对 /components/{index}/floor_connections 与踏步参数")
            elif isinstance(height, (int, float)) and not isinstance(height, bool) and abs(total_rise-height) > 0.25:
                issues.append(f"/components/{index}/form：踏步总高差 {total_rise:g}m 与楼梯 size.height "
                              f"{height:g}m 不一致；修订踏步或楼梯高度")
    return issues


def design_relation_checks(design, markers, frames):
    """用已解析宿主核对引用和重复墙；不再重新构造四向矩形围护。"""
    from shapely.geometry import LineString
    from app.domain.components.names import resolve_component_name
    from app.domain.design.spatial import host_path

    ids = {v["id"] for v in design["volumes"]} | {m["id"] for m in markers} | set(frames)
    errors, reviews = [], []
    walls = list(frames.values())
    for index, wall in enumerate(walls):
        for other in walls[index+1:]:
            lower = max(wall["from"][1], other["from"][1])
            upper = min(wall["to"][1], other["to"][1])
            if upper-lower <= 0.001:
                continue
            path = LineString(host_path(wall, lower))
            overlap = path.intersection(LineString(host_path(other, lower))).length
            if overlap > 0.001:
                errors.append({"code": "floor_wall_facade_conflict", "path": wall["design_path"],
                               "actual": {"wall_id": wall["id"], "facade_id": other["id"], "overlap": overlap},
                               "reason": "同一墙路径被重复声明；保留一个实体来源并修订相关引用"})
    for marker in markers:
        if marker["type"] == "building_body":
            continue
        component, path = marker["design"], marker["design_path"]
        for field, reference in (("host", marker.get("host")),
                                 ("relation/target", (component.get("relation") or {}).get("target"))):
            if reference and reference not in ids:
                errors.append({"code": "design_reference_missing", "path": f"{path}/{field}",
                               "marker_id": marker["id"], "actual": reference, "reason": "引用目标未在图纸声明"})
        family = resolve_component_name(marker["type"])["entity_type"]
        placement = component.get("placement") or {}
        if (not marker.get("host") and not (component.get("relation") or {}).get("target")
                and not placement.get("position")
                and (placement.get("face") or placement.get("floor")
                     or any(placement.get(key) for key in ("offset", "sill_height", "normal_offset")))):
            errors.append({"code": "design_placement_reference_missing", "path": path+"/placement",
                           "marker_id": marker["id"], "reason": "局部定位缺少host或relation.target参考对象"})
        if family in {"door", "window"} and marker.get("host") not in frames:
            errors.append({"code": "design_opening_host_missing", "path": path+"/host",
                           "marker_id": marker["id"], "actual": marker.get("host"),
                           "reason": "门窗必须引用可解析的逻辑墙宿主，不能由执行节点猜测"})
        if family == "stair":
            targets, problems = floor_connection_targets(design, component)
            marker["floor_connections"] = targets
            errors.extend({**problem, "path": path+problem["path"], "marker_id": marker["id"]} for problem in problems)
            if not targets:
                reviews.append({"marker_id": marker["id"], "path": path+"/floor_connections",
                                "reason": "楼梯缺少明确楼层连接，尚不能确认上下口可达"})
    return errors, reviews


def floor_layout_conflicts(design):
    """检查墙路径是否穿过房间内部，支持真实多边形与曲线墙。"""
    from shapely.geometry import LineString
    from app.domain.design.layout import _room_shape

    issues = []
    for layout_index, layout in enumerate(design.get("floor_layouts") or []):
        for wall_index, wall in enumerate(layout.get("walls") or []):
            points = wall.get("path") or [wall.get("from"), wall.get("to")]
            if any(point is None for point in points):
                continue
            if any(item.get("host") == wall.get("id") for item in design.get("components") or []):
                continue
            path = LineString(points)
            for room_index, room in enumerate(layout.get("rooms") or []):
                if room.get("void"):
                    continue
                shape = _room_shape(room)
                if shape is None:
                    continue
                crossing = path.intersection(shape.buffer(-0.001))
                if crossing.length > 0.001:
                    issues.append(f"/floor_layouts/{layout_index}/walls/{wall_index}：墙 {wall.get('id')} "
                                  f"穿过 rooms/{room_index} 房间内部；联合修订墙与房间边界")
    return issues




def opening_coordinate_errors(markers):
    """核对门窗越界及同一墙面洞口重叠，不改写设计坐标。"""
    from app.domain.components.names import resolve_component_name
    errors, openings = [], []
    for marker in markers:
        wall = marker.get("diagram_host")
        design, spec = marker["design"], marker["entity"]
        if (wall and wall.get("open")
                and resolve_component_name(marker["type"])["entity_type"] in {"door", "window"}):
            errors.append(f"{marker.get('design_path', '/decisions/components')}/host：{marker['id']} 引用了 {wall['id']}，"
                          "但该体量此面此层的有效 facades 是 open（无墙）；"
                          "封闭空间需在对应 volume.facades 覆盖此面的布局，或显式修订门窗宿主；"
                          "不能只在文字中声明围护，未覆盖的面仍继承共享 facades")
            continue
        if (not wall or not design.get("placement") or not spec.get("from")
                or resolve_component_name(marker["type"])["entity_type"] not in {"door", "window"}):
            continue
        a, b = wall["from"], wall["to"]
        length = wall.get("length") or hypot(b[0]-a[0], b[2]-a[2])
        along, y, _ = spec["from"]
        size = design.get("size") or {}
        width, height = size.get("width", 0), size.get("height", 0)
        world = bool(design["placement"].get("position"))
        problems = []
        for low, high in wall.get("open_intervals", []):
            if min(along + width, high) - max(along, low) > 0.001:
                problems.append(f"洞口沿墙范围 [{along:g}, {along+width:g}]m 与 facades 中 open（无墙）区段 "
                                f"[{low:g}, {high:g}]m 重叠；关联 {wall.get('design_path', '/decisions/volumes')} "
                                "与 /decisions/facades，显式修订围护布局或宿主，不能把无墙区段当作门窗宿主")
        if along < -0.001 or along+width > length+0.001:
            message = f"沿墙范围 [{along:g}, {along+width:g}]m，宿主允许 [0, {length:g}]m，窗宽={width:g}m；"
            if width > length:
                message += ("当前宽度没有可用沿墙位置" if world else "当前宽度没有可用 offset") + "，须显式修订宽度或宿主"
            elif world:
                message += (f"position 沿宿主 from→to 的中心距离={along+width/2:g}m，"
                            f"保留宽度时中心距离的可用范围 [{width/2:g}, {length-width/2:g}]")
            else:
                message += f"offset={along:g} 是沿墙局部距离，保留宽度时 offset 的可用范围 [0, {length-width:g}]"
            problems.append(message)
        if y < a[1]-0.001 or y+height > b[1]+0.001:
            message = f"竖向范围 [{y:g}, {y+height:g}]m，宿主允许 [{a[1]:g}, {b[1]:g}]m，墙高={b[1]-a[1]:g}m；"
            if world:
                message += f"position[1] 是世界中心 Y，窗高={height:g}m；"
                if height <= b[1]-a[1]:
                    message += f"保留窗高时 position[1] 的可用范围 [{a[1]+height/2:g}, {b[1]-height/2:g}]"
                else:
                    message += "当前窗高没有可用中心位置，须显式修订窗高或宿主"
            else:
                message += f"sill_height={y-a[1]:g}m 是相对本层墙底的高度，窗高={height:g}m；"
                if height <= b[1]-a[1]:
                    message += f"保留窗高时 sill_height 的可用范围 [0, {b[1]-a[1]-height:g}]"
                else:
                    message += "当前窗高没有可用 sill_height，须显式修订窗高或宿主"
            message += "；"
            if a[1] <= y < b[1]:
                message += f"保留窗底时 height 的可用范围 (0, {b[1]-y:g}]"
            else:
                message += "窗底已超出可安装范围，需修订位置或宿主，不能只改窗高"
            problems.append(message)
        if problems:
            errors.append(f"{marker['design_path']}/placement：{marker['id']} 的门窗范围超出宿主 {wall['id']}；"
                          + "；".join(problems) + "；只修对应方向的位置或明确调整尺寸/宿主，保留未受影响的设计")
        if width <= 0 or height <= 0 or length <= 0.001 or wall.get("curve"):
            continue
        ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
        start = (a[0]+ux*along, a[2]+uz*along)
        for other, origin, direction, other_width, bottom, other_height in openings:
            if abs(ux*direction[1]-uz*direction[0]) > 0.000001:
                continue
            dx, dz = origin[0]-start[0], origin[1]-start[1]
            if abs(-dx*uz+dz*ux) > 0.001:
                continue
            shift = dx*ux+dz*uz
            end = shift+other_width*(ux*direction[0]+uz*direction[1])
            overlap = min(width, max(shift, end))-max(0, min(shift, end))
            if overlap <= 0.001 or min(y+height, bottom+other_height)-max(y, bottom) <= 0.001:
                continue
            errors.append(f"{marker['design_path']}/placement：{marker['id']} 与 "
                          f"{other['design_path']} 的 {other['id']} 在同一物理墙面上的洞口重叠；"
                          f"沿墙重叠 {overlap:g}m，当前洞口范围 [{along:g}, {along+width:g}]m、"
                          f"Y=[{y:g}, {y+height:g}]m。显式修订位置、尺寸或组合分格，"
                          "不能同时声明覆盖彼此的完整门窗，也不能让执行节点自行移动已批准洞口")
        openings.append((marker, start, (ux, uz), width, y, height))
    return errors




def component_dimension_conflicts(design):
    """显式方向和相对标高不能与构件自身的世界尺寸、中心矛盾。"""
    from app.domain.components.names import resolve_component_name

    errors = []
    volumes = {v["id"]: v for v in design.get("volumes") or []}
    for index, component in enumerate(design.get("components") or []):
        family = resolve_component_name(component.get("type", ""))["entity_type"]
        size = component.get("size") or {}
        form = component.get("form") if isinstance(component.get("form"), dict) else {}
        path = f"/components/{index}"
        direction = str(form.get("span_direction") or "").strip().lower()
        if family == "beam" and direction in {"x", "z"} and all(k in size for k in ("width", "depth")):
            span, cross = ("width", "depth") if direction == "x" else ("depth", "width")
            if size[span] < size[cross]-0.001:
                errors.append(f"{path}/size：span_direction={direction}，但 {span}={size[span]:g} "
                              f"小于 {cross}={size[cross]:g}；size.width/height/depth 是整体世界 X/Y/Z 尺度，"
                              "方向不会旋转这套尺寸。请修订方向或对应尺寸，不能让实现节点同时满足相反约束")
        position = (component.get("placement") or {}).get("position")
        rise = form.get("ridge_height_from_wall_top")
        volume = volumes.get(component.get("host"))
        if (family != "roof" or not volume or not position or "height" not in size
                or type(rise) not in (int, float) or not isfinite(rise)):
            continue
        top = floor_elevations(design)[volume["end_floor"]+1]
        expected = top+rise-size["height"]/2
        if abs(position[1]-expected) > 0.001:
            errors.append(f"{path}/placement/position：屋面整体中心Y={position[1]:g}，但宿主墙顶={top:g}、"
                          f"form.ridge_height_from_wall_top={rise:g}、size.height={size['height']:g} "
                          f"推导中心Y={expected:g}（墙顶+屋脊高差-屋面高度/2）；"
                          "请显式修订位置或相对高差，不能把屋脊标高当成整体中心")
    return errors


def roof_span_conflicts(markers):
    """显式整片屋面的设计包围框必须覆盖其负责体量及出檐。"""
    from app.domain.components.names import resolve_component_name
    errors = []
    for marker in markers:
        design = marker.get("design") or {}
        volume = design.get("volume")
        position = (design.get("placement") or {}).get("position")
        size = design.get("size") or {}
        if (resolve_component_name(marker["type"])["entity_type"] != "roof"
                or not volume or not position):
            continue
        overhang = design.get("overhang", 0)
        path = marker.get("design_path", "/decisions/components").removeprefix("/decisions")
        for key, axis, origin in (("width", 0, "x"), ("depth", 2, "z")):
            if key not in size:
                continue
            lower = volume[origin]-overhang
            upper = volume[origin]+volume[key]+overhang
            required = 2*max(position[axis]-lower, upper-position[axis])
            if size[key] < required-0.001:
                errors.append(f"{path}/size/{key}：整片屋面需覆盖体量和出檐，"
                              f"世界 {'XZ'[axis//2]} 范围 [{lower:g}, {upper:g}]，"
                              f"当前中心 {position[axis]:g}，{key} 至少为 {required:g}，实际 {size[key]:g}；"
                              "修订 /components 的覆盖尺寸或 /volumes、/roof 中相互矛盾的设计数值，不能带着矛盾进入实现")
    return errors
