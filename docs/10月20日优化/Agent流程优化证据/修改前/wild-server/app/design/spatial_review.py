"""实际产物的有限空间使用复核；不移动实体，不冒充网格碰撞或规范验收。"""
from math import cos, sin, hypot, isfinite


EPS = 0.001


def _vector(value, size):
    return (isinstance(value, (list, tuple)) and len(value) == size
            and all(type(v) in (int, float) and isfinite(v) for v in value))


def _strip(start, end, width):
    dx, dz = end[0]-start[0], end[1]-start[1]
    length = hypot(dx, dz)
    if length <= EPS:
        return None
    nx, nz = -dz/length*width/2, dx/length*width/2
    return [[start[0]+nx, start[1]+nz], [end[0]+nx, end[1]+nz],
            [end[0]-nx, end[1]-nz], [start[0]-nx, start[1]-nz]]


def _frame(entity):
    """只解析可精确映射的直墙、矩形板、平顶和仅绕 Y 旋转的 box/家具。"""
    if any(key.startswith("parent") for key in entity) or entity.get("curve"):
        return None
    if entity.get("scale", [1, 1, 1]) != [1, 1, 1]:
        return None
    kind = entity.get("type")
    a, b = entity.get("from"), entity.get("to")
    if kind in {"wall", "floor"} and _vector(a, 3) and _vector(b, 3):
        thickness = entity.get("thickness")
        if type(thickness) not in (int, float) or not isfinite(thickness) or thickness <= 0:
            return None
        if kind == "wall":
            polygon = _strip([a[0], a[2]], [b[0], b[2]], thickness)
            return (polygon, min(a[1], b[1]), max(a[1], b[1])) if polygon else None
        if entity.get("shape", "rect") != "rect" or abs(a[1]-b[1]) > EPS:
            return None
        return ([[a[0], a[2]], [b[0], a[2]], [b[0], b[2]], [a[0], b[2]]], a[1], a[1]+thickness)
    position = entity.get("position")
    dimensions = entity.get("dimensions")
    if kind == "furniture" and isinstance(dimensions, dict):
        dimensions = [dimensions.get(k) for k in ("width", "height", "depth")]
    elif kind == "roof" and entity.get("roofType") == "flat":
        dimensions = [entity.get("span"), entity.get("thickness"), entity.get("depth")]
    elif kind != "primitive" or entity.get("shape") != "box":
        return None
    rotation = entity.get("rotation", [0, 0, 0])
    if (not _vector(position, 3) or not _vector(dimensions, 3) or min(dimensions) <= 0
            or not _vector(rotation, 3) or abs(rotation[0]) > EPS or abs(rotation[2]) > EPS):
        return None
    width, height, depth = dimensions
    angle = rotation[1]
    polygon = [[position[0]+x*cos(angle)+z*sin(angle), position[2]-x*sin(angle)+z*cos(angle)]
               for x, z in ((-width/2, -depth/2), (width/2, -depth/2), (width/2, depth/2), (-width/2, depth/2))]
    bottom = position[1] if kind in {"furniture", "roof"} else position[1]-height/2
    return polygon, bottom, bottom+height


def entity_bounds(entity):
    """世界包围框只供上下文筛选和已支持形态的尺寸核对。"""
    frame = _frame(entity)
    if frame is None:
        return None
    polygon, bottom, top = frame
    return {"min": [min(p[0] for p in polygon), bottom, min(p[1] for p in polygon)],
            "max": [max(p[0] for p in polygon), top, max(p[1] for p in polygon)]}


def _overlap(first, second):
    """凸多边形分离轴；仅接触不算侵入。"""
    for polygon in (first, second):
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            nx, nz = -(b[1]-a[1]), b[0]-a[0]
            length = hypot(nx, nz)
            if length <= EPS:
                continue
            x = [p[0]*nx/length+p[1]*nz/length for p in first]
            y = [p[0]*nx/length+p[1]*nz/length for p in second]
            if min(max(x), max(y))-max(min(x), min(y)) <= EPS:
                return False
    return True


def _wall_segments(wall, openings, bottom, top):
    a, b = wall["from"], wall["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    intervals = [(0, length)]
    for opening in openings:
        origin = opening.get("from")
        if (opening.get("parentWall") != wall["id"] or opening.get("type") not in {"door", "opening"}
                or not _vector(origin, 3) or abs(origin[2]) > EPS
                or origin[1] > bottom+EPS or origin[1]+opening.get("height", 0) < top-EPS):
            continue
        left, right = origin[0], origin[0]+opening.get("width", 0)
        intervals = [(x, y) for low, high in intervals
                     for x, y in ((low, min(high, left)), (max(low, right), high)) if y-x > EPS]
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    return [_strip([a[0]+ux*low, a[2]+uz*low], [a[0]+ux*high, a[2]+uz*high], wall["thickness"])
            for low, high in intervals]


def review_spatial_use(blueprint, design):
    """核对显式净空路径和家具/洞口关系；未知形态列待复核，不自动判过。"""
    from .coordinates import floor_elevations

    geometry = blueprint.get("geometry") or {}
    entities = [e for bucket in ("elements", "components") for e in geometry.get(bucket, []) if isinstance(e, dict)]
    by_id = {e.get("id"): e for e in entities}
    frames = {e.get("id"): _frame(e) for e in entities}
    blockers = [e for e in entities if e.get("type") in {"wall", "furniture", "primitive", "column", "beam"}]
    openings = [e for e in entities if e.get("type") in {"door", "window", "opening"}
                and all(type(e.get(k)) in (int, float) and isfinite(e[k]) and e[k] > 0 for k in ("width", "height"))]
    errors, observations, checks = [], [], []
    unverified = [e.get("id") for e in blockers if frames[e.get("id")] is None]
    levels = floor_elevations(design)
    for index, path in enumerate((design.get("circulation") or {}).get("paths") or []):
        target = f"/decisions/circulation/paths/{index}"
        bottom, top = levels[path["floor"]], levels[path["floor"]]+path["height"]
        paths = [_strip(a, b, path["width"]) for a, b in zip(path["points"], path["points"][1:])]
        blocked = []
        for entity in blockers:
            frame = frames[entity.get("id")]
            if frame is None or min(frame[2], top)-max(frame[1], bottom) <= EPS:
                continue
            polygons = _wall_segments(entity, openings, bottom, top) if entity["type"] == "wall" else [frame[0]]
            if any(_overlap(route, polygon) for route in paths for polygon in polygons):
                blocked.append(entity["id"])
        check = {"code": "circulation_clearance", "design_path": target, "path_id": path["id"],
                 "expected": {"floor": path["floor"], "width": path["width"], "height": path["height"]},
                 "actual": {"blocking_entity_ids": blocked}, "entity_ids": blocked,
                 "status": "blocked" if blocked else ("needs_review" if unverified else "checked")}
        checks.append(check)
        if blocked:
            errors.append({**check, "message": f"通行路径 {path['id']} 的设计净空 "
                           f"{path['width']:g}×{path['height']:g}m 被 {blocked} 占用；"
                           "核对实际实体与门洞，不能删除或缩窄已批准路径绕过问题"})

    furniture = [e for e in entities if e.get("type") == "furniture" and frames.get(e.get("id"))]
    for opening in openings:
        wall = by_id.get(opening.get("parentWall"))
        origin = opening.get("from")
        if not wall or not frames.get(wall.get("id")) or not _vector(origin, 3):
            continue
        a, b = wall["from"], wall["to"]
        length = hypot(b[0]-a[0], b[2]-a[2])
        ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
        for item in furniture:
            polygon, low, high = frames[item["id"]]
            if min(high, origin[1]+opening.get("height", 0))-max(low, origin[1]) <= EPS:
                continue
            along = [(p[0]-a[0])*ux+(p[1]-a[2])*uz for p in polygon]
            normal = [-(p[0]-a[0])*uz+(p[1]-a[2])*ux-origin[2] for p in polygon]
            if min(max(along), origin[0]+opening.get("width", 0))-max(min(along), origin[0]) <= EPS:
                continue
            # 0.5m 仅用于找出可能挡光的近窗家具，不是净距规范或硬门禁。
            band = 0.5 if opening["type"] == "window" else wall["thickness"]/2
            if min(max(normal), band)-max(min(normal), -band) <= EPS:
                continue
            issue = {"code": "furniture_opening", "entity_ids": [item["id"], opening["id"], wall["id"]],
                     "design_path": "/decisions/components", "actual": {"along": [min(along), max(along)],
                     "height": [low, high], "normal": [min(normal), max(normal)]},
                     "message": f"家具 {item['id']} 与 {opening['type']} {opening['id']} 的沿墙及高度范围重叠"}
            if opening["type"] == "window":
                observations.append({**issue, "message": issue["message"]+"，可能遮挡玻璃；结合用途复核，不自动移动"})
            else:
                errors.append({**issue, "message": issue["message"]+"，且侵入实际门洞通行面"})
    return {"version": "spatial-use/1", "errors": errors, "observations": observations,
            "checks": checks, "unverified_entity_ids": unverified,
            "scope": "explicit_path_clearance_and_furniture_openings; no_mesh_or_code_certification"}
