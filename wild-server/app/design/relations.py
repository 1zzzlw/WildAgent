"""有限的柱—雨棚几何支撑判据；编译、计划对账和履约共用，不证明荷载安全。"""
from math import cos, hypot, isfinite, sin

TOLERANCE = 0.001  # 米，与批准实体比较相同，1mm。


def entity_index(blueprint: dict) -> dict:
    geometry = blueprint.get("geometry") or {}
    return {e["id"]: e for bucket in ("elements", "components")
            for e in geometry.get(bucket, []) if isinstance(e, dict) and e.get("id")}


def roof_design_errors(blueprint: dict, entities: list[dict], marker: dict) -> list[str]:
    """核对矩形体量屋面的投影并集；封檐条不能替代整片屋面。"""
    volume = marker.get("design", {}).get("volume")
    from app.agent.knowledge.component_names import resolve_component_name
    if resolve_component_name(marker["type"])["entity_type"] != "roof" or not isinstance(volume, dict):
        return []
    from .coordinates import rectangle_uncovered_area
    from app.tools.spatial_tools import _roof_footprint_entries
    walls = [e for e in entity_index(blueprint).values() if e.get("type") == "wall"]
    elevation = marker["entity"]["position"][1]
    regions = [(x0, z0, x1, z1) for x0, x1, z0, z1, y, _ in _roof_footprint_entries(entities, walls)
               if y >= elevation-TOLERANCE]
    for entity in entities:
        if entity.get("type") == "floor" and entity.get("shape", "rect") == "rect":
            a, b = entity["from"], entity["to"]
            if a[1]+entity["thickness"] >= elevation-TOLERANCE:
                regions.append((min(a[0], b[0]), min(a[2], b[2]), max(a[0], b[0]), max(a[2], b[2])))
        elif entity.get("type") == "primitive" and entity.get("shape") == "box":
            rx, ry, rz = entity.get("rotation", [0, 0, 0])
            # 单轴倾斜的 box 上表面仍投影为矩形，不用整个包围盒冒充屋面。
            if ry or (rx and rz) or cos(rx)*cos(rz) <= 0:
                continue
            w, h, d = [v*s for v, s in zip(entity["dimensions"], entity.get("scale", [1, 1, 1]))]
            if min(w, h, d) <= 0:
                continue
            x, y, z = entity.get("position", [0, 0, 0])
            x -= h/2*sin(rz)
            z += h/2*sin(rx)
            lowest = y+h/2*cos(rx)*cos(rz)-abs(d/2*sin(rx))-abs(w/2*sin(rz))
            if lowest >= elevation-TOLERANCE:
                regions.append((x-w/2*cos(rz), z-d/2*cos(rx), x+w/2*cos(rz), z+d/2*cos(rx)))
    overhang = marker["design"].get("overhang", 0)
    target = (volume["x"]-overhang, volume["z"]-overhang,
              volume["x"]+volume["width"]+overhang, volume["z"]+volume["depth"]+overhang)
    missing = rectangle_uncovered_area(target, [(a-TOLERANCE, b-TOLERANCE, c+TOLERANCE, d+TOLERANCE)
                                               for a, b, c, d in regions])
    return ([f"❌ [{entities[0]['id']}] 图纸标记 {marker['id']}：屋面未覆盖负责体量及出檐，"
             f"缺少 {missing:.3f}㎡；生成连续屋面，不能只返回封檐条；当前可核对 roof、矩形 floor 和单轴倾斜 box"]
            if missing > TOLERANCE else [])


def _opening_frame(blueprint, entities, marker):
    from app.agent.knowledge.component_names import resolve_component_name
    spec = marker.get("entity") or {}
    family = resolve_component_name(marker["type"])["entity_type"]
    index = entity_index(blueprint)
    diagram = marker.get("diagram_host") or index.get(spec.get("parentWall"))
    if family not in {"door", "window"} or not diagram or diagram.get("type") != "wall" or diagram.get("curve"):
        return None
    openings = [e for e in entities if e.get("type") == family]
    openings = openings or [e for e in entities if e.get("type") == "opening"]
    if not openings:
        return None
    a, b = diagram["from"], diagram["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    if length <= TOLERANCE:
        raise ValueError("示意宿主长度无效")
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    alongs, heights, normals = [], [], []
    for opening in openings:
        wall = index.get(opening.get("parentWall"))
        if not wall or wall.get("curve"):
            raise ValueError("无法核对真实直墙宿主")
        p, q = wall["from"], wall["to"]
        wall_length = hypot(q[0]-p[0], q[2]-p[2])
        if wall_length <= TOLERANCE:
            raise ValueError("真实宿主长度无效")
        vx, vz = (q[0]-p[0])/wall_length, (q[2]-p[2])/wall_length
        if abs(ux*vz-uz*vx) > TOLERANCE:
            raise ValueError("实际洞口宿主与设计墙方向不一致")
        start, bottom, normal = opening["from"]
        for distance in (start, start+opening["width"]):
            x, z = p[0]+vx*distance-vz*normal-a[0], p[2]+vz*distance+vx*normal-a[2]
            alongs.append(x*ux+z*uz)
            normals.append(-x*uz+z*ux)
        heights.extend((bottom, bottom+opening["height"]))
    return index, diagram, openings, (ux, uz), (min(alongs), max(alongs), min(heights), max(heights)), normals


def opening_target(marker, diagram, width, height):
    """把图纸中心、洞口起点和开间中心统一成沿示意墙的左下角。"""
    spec = marker.get("entity") or {}
    a, b = diagram["from"], diagram["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    if spec.get("position"):
        x, y, z = spec["position"]
        return [(x-a[0])*ux+(z-a[2])*uz-width/2, y-height/2, -(x-a[0])*uz+(z-a[2])*ux]
    if spec.get("from") and marker["design"].get("placement"):
        return list(spec["from"])
    if "centerAlong" in spec:
        return [spec["centerAlong"]-width/2, spec["bottomY"], 0]
    return None


def body_host_errors(blueprint, markers):
    """主体交接前核对门窗安装范围；未给尺寸的标记先核对定位点。"""
    from app.agent.knowledge.component_names import resolve_component_name
    from app.tools.spatial_tools import MAX_OPENING_NORMAL_OFFSET
    index, errors = entity_index(blueprint), []
    for marker in markers:
        family = resolve_component_name(marker["type"])["entity_type"]
        host_id = marker.get("entity", {}).get("parentWall")
        diagram = marker.get("diagram_host")
        if family not in {"door", "window"} or not host_id or not diagram or diagram.get("curve"):
            continue
        prefix = f"主体宿主 {host_id} 无法承接图纸标记 {marker['id']}："
        wall = index.get(host_id)
        if not wall or wall.get("type") != "wall":
            errors.append(prefix + "缺少真实墙；沿用 diagram_hosts 的宿主ID和安装范围")
            continue
        size = marker.get("design", {}).get("size") or {}
        width, height = size.get("width", 0), size.get("height", 0)
        probe = {"id": marker["id"], "type": family, "parentWall": host_id,
                 "from": [0, 0, 0], "width": width, "height": height}
        try:
            placed, _ = place_opening_group(blueprint, {"geometry": {"components": [probe]}}, marker)
            if opening_target(marker, diagram, width, height) is None:
                continue
            start, bottom, normal = placed["geometry"]["components"][0]["from"]
            a, b = wall["from"], wall["to"]
            length = hypot(b[0]-a[0], b[2]-a[2])
            if abs(normal) > MAX_OPENING_NORMAL_OFFSET:
                errors.append(prefix + "实际墙面偏离图纸安装面；保持宿主所在墙面，不能让门窗漂浮在墙外")
            if (start < -TOLERANCE or start+width > length+TOLERANCE
                    or bottom < min(a[1], b[1])-TOLERANCE or bottom+height > max(a[1], b[1])+TOLERANCE):
                errors.append(prefix + "墙段未覆盖安装位置；不要把原宿主ID留给一小段墙，门窗会由原生洞口裁墙")
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(prefix + str(exc))
    return errors


def place_opening_group(blueprint, row, marker):
    """编译门窗组的安装平移，保留形态、尺寸和组内分格。"""
    from copy import deepcopy
    row = deepcopy(row)
    geometry = row.get("geometry")
    if not isinstance(geometry, dict) or any(not isinstance(geometry.get(k, []), list) for k in ("elements", "components")):
        return row, []
    entities = [*geometry.get("elements", []), *geometry.get("components", [])]
    frame = _opening_frame(blueprint, entities, marker)
    if not frame:
        return row, []
    index, diagram, openings, (ux, uz), (left, right, bottom, top), normals = frame
    target = opening_target(marker, diagram, right-left, top-bottom)
    if target is None:
        return row, []
    # 不消除组内法向错位；它仍应由同一门窗验收报告。
    da, dy, dn = target[0]-left, target[1]-bottom, target[2]-normals[0]
    if max(abs(da), abs(dy), abs(dn)) <= TOLERANCE:
        return row, []
    dx, dz = ux*da-uz*dn, uz*da+ux*dn
    changes = []
    for entity in entities:
        if entity in openings:
            wall = index[entity["parentWall"]]
            p, q = wall["from"], wall["to"]
            length = hypot(q[0]-p[0], q[2]-p[2])
            vx, vz = (q[0]-p[0])/length, (q[2]-p[2])/length
            field, delta = "from", [dx*vx+dz*vz, dy, -dx*vz+dz*vx]
        elif entity.get("type") == "primitive" and isinstance(entity.get("position"), list):
            field, delta = "position", [dx, dy, dz]
        else:
            continue
        before = list(entity[field])
        entity[field] = [v+d for v, d in zip(before, delta)]
        changes.append({"rule": "compiler.opening_placement", "entity_id": entity["id"],
                        "field": field, "before": before, "after": entity[field]})
    return row, changes


def opening_design_errors(blueprint: dict, entities: list[dict], marker: dict) -> list[str]:
    """核对有定位的门窗安装：真实洞口、宿主平面和整个窗组的设计范围。"""
    from app.agent.knowledge.component_names import resolve_component_name
    spec = marker.get("entity") or {}
    family = resolve_component_name(marker["type"])["entity_type"]
    if family not in {"door", "window"} or not spec.get("parentWall"):
        return []
    index = entity_index(blueprint)
    diagram = marker.get("diagram_host") or index.get(spec["parentWall"])
    if diagram and diagram.get("type") != "wall":
        return []
    prefix = f"❌ [{entities[0]['id']}] 图纸标记 {marker['id']}："
    if any(e.get("type") == "wall" for e in entities):
        return [prefix + "门窗任务不能补墙封堵主体；使用真实宿主或反馈主体缺口"]
    openings = [e for e in entities if e.get("type") == family]
    openings = openings or [e for e in entities if e.get("type") == "opening"]
    if not openings:
        return [prefix + "门窗必须落实真实洞口；primitive 玻璃和框条不会在墙上开洞"]
    if not diagram or diagram.get("curve"):
        return []
    try:
        _, _, _, _, (left, right, bottom, top), normals = _opening_frame(blueprint, entities, marker)
    except ValueError as exc:
        return [prefix + str(exc)]
    design, errors = marker["design"], []
    if family == "window":
        for opening in openings:
            if opening.get("type") != "window":
                continue
            wall = index[opening["parentWall"]]
            p, q = wall["from"], wall["to"]
            length = hypot(q[0]-p[0], q[2]-p[2])
            vx, vz = (q[0]-p[0])/length, (q[2]-p[2])/length
            if min(abs(vx), abs(vz)) > TOLERANCE:
                continue
            for panel in entities:
                if (panel.get("type") != "primitive" or panel.get("shape") != "box"
                        or any(panel.get("rotation", [0, 0, 0]))):
                    continue
                material = blueprint.get("materials", {}).get(panel.get("material"), {})
                if material.get("transmission", 0) > 0 or material.get("opacity", 1) < 1 or material.get("materialClass") == "glass":
                    continue
                x, y, z = panel.get("position", [0, 0, 0])
                w, h, d = [v*s for v, s in zip(panel["dimensions"], panel.get("scale", [1, 1, 1]))]
                along, normal = (x-p[0])*vx+(z-p[2])*vz, -(x-p[0])*vz+(z-p[2])*vx
                half = (abs(vx)*w+abs(vz)*d)/2
                start, bottom, offset = opening["from"]
                if (abs(normal-offset) <= wall["thickness"]/2+opening.get("frameDepth", 0.1)+TOLERANCE
                        and along-half <= start+TOLERANCE and along+half >= start+opening["width"]-TOLERANCE
                        and y-h/2 <= bottom+TOLERANCE and y+h/2 >= bottom+opening["height"]-TOLERANCE):
                    errors.append(f"❌ [{panel['id']}] 图纸标记 {marker['id']}：实心板遮满窗洞 {opening['id']}；窗框用四边框或条状构件，保留玻璃净空")
    size = design.get("size") or {}
    for field, actual in (("width", right-left), ("height", top-bottom)):
        if field in size and abs(actual-size[field]) > TOLERANCE:
            errors.append(prefix + f"门窗组 {field} 应为 {size[field]}，实际 {actual:.3f}，按整个洞口组核对")
    expected = opening_target(marker, diagram, right-left, top-bottom)
    if expected is None:
        return errors
    actual = (left, bottom, max(normals, key=lambda n: abs(n-expected[2])))
    for field, wanted, value in zip(("沿墙位置", "标高", "法向位置"), expected, actual):
        if abs(wanted-value) > TOLERANCE:
            errors.append(prefix + f"{field} 应为 {wanted:.3f}m，实际 {value:.3f}m；按图纸修订，不能移动实例绕过冲突")
    return errors


def wall_attached_point(blueprint: dict, component: dict, along: float, y: float, depth: float) -> list:
    """墙局部位置 → 墙外世界位置，与 core attachedToWall 的法线及外表面一致。"""
    entities = entity_index(blueprint)
    wall = entities.get(component.get("parentWall"))
    if not wall or wall.get("type") != "wall" or wall.get("curve"):
        raise ValueError("需要真实直墙宿主；曲墙附属位置尚不支持")
    a, b = wall["from"], wall["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    if length <= TOLERANCE:
        raise ValueError("宿主墙长度无效")
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    nx, nz = -uz, ux
    points = [p for e in entities.values() if e.get("type") == "wall" for p in (e["from"], e["to"])]
    cx = (min(p[0] for p in points)+max(p[0] for p in points))/2
    cz = (min(p[2] for p in points)+max(p[2] for p in points))/2
    offset = component["from"][2]
    midpoint = component["from"][0]+component["width"]/2
    dot = (a[0]+ux*midpoint-cx)*nx+(a[2]+uz*midpoint-cz)*nz
    sign = 1 if dot > 1e-6 else -1
    offset += sign*(wall["thickness"]/2+depth)
    point = [a[0]+ux*along+nx*offset, y, a[2]+uz*along+nz*offset]
    if not all(isfinite(v) for v in point):
        raise ValueError("关系坐标不是有限数")
    return point


def canopy_support_point(blueprint: dict, relation: dict) -> tuple[list, float]:
    """沿墙比例、出挑比例 → 世界柱顶；与 core canopy 的墙外表面及板底一致。"""
    entities = entity_index(blueprint)
    canopy = entities.get(relation.get("target"))
    if not canopy or canopy.get("type") != "canopy":
        raise ValueError("支撑目标不存在或不是 canopy")
    along = canopy["from"][0]+canopy["width"]*relation["along_ratio"]
    top = canopy["from"][1]-canopy["thickness"]/2
    point = wall_attached_point(blueprint, canopy, along, top, canopy["depth"]*relation["depth_ratio"])
    wall = entities[canopy["parentWall"]]
    bottom = min(wall["from"][1], wall["to"][1])
    if top <= bottom:
        raise ValueError("雨棚板底不高于宿主底标高")
    return point, bottom


def evaluate_support(blueprint: dict, entity_id: str, relation: dict) -> dict:
    entities = entity_index(blueprint)
    column = entities.get(entity_id)
    base = {"entity_id": entity_id, "target": relation.get("target"), "tolerance_m": TOLERANCE}
    if relation.get("kind") != "supports":
        return {**base, "status": "unsupported", "reason": "当前只支持柱—雨棚的 supports 几何关系"}
    target = entities.get(relation.get("target")) or {}
    wall = entities.get(target.get("parentWall")) or {}
    if wall.get("curve"):
        return {**base, "status": "unsupported", "reason": "曲墙雨棚支撑暂无几何判据，需要设计复核"}
    geometry = blueprint.get("geometry") or {}
    all_entities = [*geometry.get("elements", []), *geometry.get("components", [])]
    if any(sum(e.get("id") == key for e in all_entities) != 1
           for key in (entity_id, relation.get("target"), target.get("parentWall"))):
        return {**base, "status": "open", "reason": "柱、雨棚或墙引用缺失/重复，无法唯一解析"}
    if not column or column.get("type") != "column":
        return {**base, "status": "open", "reason": "对应柱实体缺失或类型错误"}
    try:
        point, bottom = canopy_support_point(blueprint, relation)
        start = column["base"]
        height = column["height"]
        if isinstance(height, bool) or not isinstance(height, (int, float)) or not isfinite(height) or height <= 0:
            raise ValueError("柱高必须是正有限数")
        end = [start[0], start[1]+height, start[2]]
        values = start+end
        if len(start) != 3 or len(end) != 3 or not all(isinstance(v, (float, int)) and not isinstance(v, bool) and isfinite(v) for v in values):
            raise ValueError("柱端点无效")
        valid = (abs(start[0]-point[0]) <= TOLERANCE and abs(start[2]-point[2]) <= TOLERANCE
                 and abs(end[0]-point[0]) <= TOLERANCE and abs(end[2]-point[2]) <= TOLERANCE
                 and abs(min(start[1], end[1])-bottom) <= TOLERANCE
                 and abs(max(start[1], end[1])-point[1]) <= TOLERANCE)
        return {**base, "status": "satisfied" if valid else "open", "expected_top": point,
                "actual_from": start, "actual_to": end, "reason": "核对局部支撑位置、柱底与雨棚板底；仅证明几何关系"}
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {**base, "status": "open", "reason": str(exc)}
