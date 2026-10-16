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


def stair_span_conflicts(design):
    """只核对显式数值能否落在已声明的楼面之间，不推断楼梯造型。"""
    from app.agent.knowledge.component_names import resolve_component_name

    levels = floor_elevations(design)
    highest_floor = levels[design["massing"]["floors"]]
    available_rise = highest_floor - levels[1]
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
            issues.append(f"/components/{index}/size/height：楼梯高 {height:g}m 超过首层至顶层楼面高差 "
                          f"{available_rise:g}m；核对连接楼层，屋面通行须显式写 form.roof_access")
        if all(isinstance(form.get(key), (int, float)) and not isinstance(form[key], bool)
               for key in ("flights", "rises", "riser_height")):
            total_rise = form["flights"] * form["rises"] * form["riser_height"]
            if total_rise > available_rise + 0.25:
                issues.append(f"/components/{index}/form：梯段数×每跑级数×踏步高={total_rise:g}m，"
                              f"超过首层至顶层楼面高差 {available_rise:g}m；修订楼梯连接或踏步参数")
            elif isinstance(height, (int, float)) and not isinstance(height, bool) and abs(total_rise-height) > 0.25:
                issues.append(f"/components/{index}/form：踏步总高差 {total_rise:g}m 与楼梯 size.height "
                              f"{height:g}m 不一致；修订踏步或楼梯高度")
    return issues


def design_relation_checks(design, markers, frames):
    """设计引用与明确楼层连接；资料不完整只列待审核，不代替设计。"""
    from app.agent.knowledge.component_names import resolve_component_name

    ids = {v["id"] for v in design["volumes"]} | {m["id"] for m in markers} | set(frames)
    errors, reviews, stairs = [], [], []
    for marker in markers:
        if marker["type"] == "building_body":
            continue
        component, path = marker["design"], marker["design_path"]
        for field, reference in (("host", marker.get("host")),
                                 ("relation/target", (component.get("relation") or {}).get("target"))):
            if reference and reference not in ids:
                errors.append({"code": "design_reference_missing", "path": f"{path}/{field}",
                               "marker_id": marker["id"], "expected": "图纸已声明的宿主或构件 ID",
                               "actual": reference, "reason": "引用目标未在本次图纸声明"})
        if resolve_component_name(marker["type"])["entity_type"] != "stair":
            continue
        targets, problems = floor_connection_targets(design, component)
        marker["floor_connections"] = targets
        errors.extend({**problem, "path": path + problem["path"], "marker_id": marker["id"]}
                      for problem in problems)
        stairs.append((marker, targets))
        if not targets:
            reviews.append({"marker_id": marker["id"], "path": path + "/floor_connections",
                            "reason": "楼梯连接楼层未结构化，须核对实际到达楼面；不据文字猜测连接"})
    if stairs and all(targets for _, targets in stairs) and design["massing"].get("representation_mode", "full") == "full":
        reached = {1}
        while True:
            expanded = reached | {t["to_floor"] for _, targets in stairs for t in targets if t["from_floor"] in reached}
            if expanded == reached:
                break
            reached = expanded
        missing = sorted(set(range(1, design["massing"]["floors"] + 1)) - reached)
        if missing:
            issue = {"code": "stair_floor_unreachable", "path": "/decisions/components",
                     "marker_id": "circulation", "marker_ids": [m["id"] for m, _ in stairs],
                     "expected": "各声明楼层可从首层到达", "actual": {"unreachable_floors": missing},
                     "reason": "明确楼梯连接漏连楼层"}
            (errors if design.get("circulation", {}).get("vertical_strategy") == "stair" else reviews).append(issue)
    return errors, reviews


def floor_layout_conflicts(design):
    """Reject a partition that cuts across a declared rectangular room."""
    issues = []
    for floor_index, layout in enumerate(design.get("floor_layouts") or []):
        for wall_index, wall in enumerate(layout.get("walls") or []):
            a, b = wall.get("from"), wall.get("to")
            if not (isinstance(a, list) and isinstance(b, list) and len(a) == len(b) == 2
                    and all(type(n) in (int, float) and isfinite(n) for n in a+b)):
                continue  # Field validation reports malformed walls separately.
            if any(item.get("host") == wall.get("id") for item in design.get("components") or []):
                continue  # A designed opening or attached detail needs human review.
            for room_index, room in enumerate(layout.get("rooms") or []):
                box = room.get("bounds") or {}
                if not isinstance(box, dict):
                    continue
                if not all(type(box.get(key)) in (int, float) and isfinite(box[key])
                           for key in ("x", "z", "width", "depth")):
                    continue
                x0, z0 = box["x"], box["z"]
                x1, z1 = x0+box["width"], z0+box["depth"]
                vertical = (abs(a[0]-b[0]) <= 0.001 and x0+0.001 < a[0] < x1-0.001
                            and min(a[1], b[1]) <= z0+0.001 and max(a[1], b[1]) >= z1-0.001)
                horizontal = (abs(a[1]-b[1]) <= 0.001 and z0+0.001 < a[1] < z1-0.001
                              and min(a[0], b[0]) <= x0+0.001 and max(a[0], b[0]) >= x1-0.001)
                if vertical or horizontal:
                    origin, extent, lower, upper, cut = (("x", "width", x0, x1, a[0]) if vertical else
                                                         ("z", "depth", z0, z1, a[1]))
                    neighbors = []
                    for other in layout.get("rooms") or []:
                        bounds = other.get("bounds") or {}
                        if other is room or other.get("void") or not isinstance(bounds, dict) or not all(
                                type(bounds.get(k)) in (int, float) and isfinite(bounds[k])
                                for k in ("x", "z", "width", "depth")):
                            continue
                        left, right = max(x0, bounds["x"]), min(x1, bounds["x"]+bounds["width"])
                        front, back = max(z0, bounds["z"]), min(z1, bounds["z"]+bounds["depth"])
                        if right-left > 0.001 and back-front > 0.001:
                            neighbors.append(f"{other.get('id', '?')}（{other.get('name', '未命名')}）"
                                             f"：X=[{left:g}, {right:g}]，Z=[{front:g}, {back:g}]")
                    issues.append(f"/floor_layouts/{floor_index}/rooms/{room_index}："
                                  f"内墙 {wall.get('id', wall_index)}（from={a}, to={b}）贯穿"
                                  f"第 {layout.get('floor', '?')} 层房间 {room.get('id', room_index)}"
                                  f"（{room.get('name', '未命名')}）范围，世界 X=[{x0:g}, {x1:g}]，Z=[{z0:g}, {z1:g}]；"
                                  f"墙段位于 {'X' if vertical else 'Z'}={a[0] if vertical else a[1]:g}，"
                                  "在房间内部跨越整个范围。保留墙时，房间 bounds 应在墙的一侧；"
                                  f"例如保留较大坐标边界时可写 bounds.{origin}={cut:g}、bounds.{extent}={upper-cut:g}；"
                                  f"保留较小坐标边界时可写 bounds.{origin}={lower:g}、bounds.{extent}={cut-lower:g}。"
                                  "仅把墙端缩短到房间另一边界仍然是贯穿。"
                                  + ("该房间还与以下房间范围重叠，须一并核对：" + "；".join(neighbors) + "。" if neighbors else "") +
                                  "保留房间时，修订墙段到房间边界或明确设计通行开口。"
                                  f"核对 /floor_layouts/{floor_index}/walls/{wall_index} 与该房间 bounds，"
                                  "不能原样返回冲突数据")
    return issues


def rectangle_uncovered_area(bounds, regions):
    """矩形减去矩形并集的面积；重复、重叠覆盖不能抵消其他位置的空缺。"""
    x0, z0, x1, z1 = bounds
    xs = sorted({x0, x1, *(max(x0, min(x1, x)) for r in regions for x in (r[0], r[2]))})
    covered = 0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((max(z0, r[1]), min(z1, r[3])) for r in regions
                           if r[0] <= left and r[2] >= right and r[1] < z1 and r[3] > z0)
        end, length = z0, 0
        for low, high in intervals:
            length += max(0, high-max(end, low))
            end = max(end, high)
        covered += (right-left)*length
    return max(0, (x1-x0)*(z1-z0)-covered)


def opening_coordinate_errors(markers):
    """核对门窗范围，按实际越界方向反馈；不猜测或改写设计坐标。"""
    from app.agent.knowledge.component_names import resolve_component_name
    errors = []
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
        length = hypot(b[0]-a[0], b[2]-a[2])
        along, y, _ = spec["from"]
        size = design.get("size") or {}
        width, height = size.get("width", 0), size.get("height", 0)
        world = bool(design["placement"].get("position"))
        problems = []
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
    return errors


def exterior_facade_intervals(volume, face, floor, volumes):
    """自动立面使用的外露墙段；同向共面区域只分配给一个体量。"""
    axis = "x" if face in {"front", "back"} else "z"
    extent = "width" if axis == "x" else "depth"
    normal, normal_extent = ("z", "depth") if axis == "x" else ("x", "width")
    positive = face in {"right", "back"}
    plane = getattr(volume, normal) + (getattr(volume, normal_extent) if positive else 0)
    origin, length = getattr(volume, axis), getattr(volume, extent)
    segments = [(0.0, length)]
    for other in volumes:
        if other.id == volume.id or not other.start_floor <= floor <= other.end_floor:
            continue
        low, high = getattr(other, normal), getattr(other, normal)+getattr(other, normal_extent)
        inside = low <= plane+0.001 and high > plane+0.001 if positive else low < plane-0.001 and high >= plane-0.001
        shared = plane == (high if positive else low)
        owner = (-getattr(other, extent), other.id) < (-length, volume.id)
        if not inside and not (shared and owner):
            continue
        start = max(0.0, getattr(other, axis)-origin)
        end = min(length, getattr(other, axis)+getattr(other, extent)-origin)
        if face in {"back", "left"}:
            start, end = length-end, length-start
        if end <= start:
            continue
        segments = [(a, b) for left, right in segments for a, b in
                    ((left, min(right, start)), (max(left, end), right)) if b-a > 0.001]
    return segments


def component_dimension_conflicts(design):
    """显式方向和相对标高不能与构件自身的世界尺寸、中心矛盾。"""
    from app.agent.knowledge.component_names import resolve_component_name

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
    from app.agent.knowledge.component_names import resolve_component_name
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
