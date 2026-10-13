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
