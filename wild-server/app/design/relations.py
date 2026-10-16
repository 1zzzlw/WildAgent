"""有限的柱—雨棚几何支撑判据；编译、计划对账和履约共用，不证明荷载安全。"""
from math import cos, hypot, isfinite, sin, tan

TOLERANCE = 0.001  # 米，与批准实体比较相同，1mm。
NATIVE_SIZE_FIELDS = {("balcony", "height"): "slabThickness", ("canopy", "height"): "thickness"}


def entity_index(blueprint: dict) -> dict:
    geometry = blueprint.get("geometry") or {}
    return {e["id"]: e for bucket in ("elements", "components")
            for e in geometry.get(bucket, []) if isinstance(e, dict) and e.get("id")}


def delegated_geometry_errors(entities: list[dict], marker: dict, markers) -> list[str]:
    """平屋面与另派女儿墙的有限归属检查，不把屋面以下支承误作女儿墙。"""
    from app.agent.knowledge.component_names import resolve_component_name
    if resolve_component_name(marker["type"])["entity_type"] != "roof":
        return []
    design = marker.get("design") or {}
    roof_type = str(design.get("roof_type") or design.get("type") or "").casefold()
    if "flat" not in roof_type and "平屋" not in roof_type and "平顶" not in roof_type:
        return []
    delegated = [m for m in markers if m["id"] != marker["id"] and marker.get("host")
                 and m.get("host") == marker["host"]
                 and resolve_component_name(m["type"])["kind"] == "parapet"]
    position = (marker.get("entity") or {}).get("position")
    if not delegated or not isinstance(position, list) or len(position) != 3:
        return []
    outside = [e["id"] for e in entities if e.get("type") == "wall"
               and all(isinstance(e.get(k), list) and len(e[k]) == 3
                       and type(e[k][1]) in (int, float) for k in ("from", "to"))
               and min(e["from"][1], e["to"][1]) >= position[1]-TOLERANCE
               and max(e["from"][1], e["to"][1]) > position[1]+TOLERANCE]
    return ([f"屋顶 {marker['id']} 越界实现屋面以上围墙 {outside}；"
             f"该宿主女儿墙已委派给 {[m['id'] for m in delegated]}，本任务只实现屋面与支承"] if outside else [])


def stair_design_errors(blueprint: dict, entities: list[dict], marker: dict) -> list[str]:
    """逐标记检查明确楼面连接；平台承托仍由共享空间校验检查。"""
    targets = marker.get("floor_connections") or []
    flights = [e for e in entities if e.get("type") == "stair"
               and all(isinstance(e.get(k), list) and len(e[k]) == 3
                       and all(type(n) in (int, float) and isfinite(n) for n in e[k]) for k in ("from", "to"))]
    if not targets or not flights:
        return []
    errors = []
    for target in targets:
        reached = [target["from_y"]]
        while True:
            additions = [e["to"][1] for e in flights
                         if any(abs(e["from"][1]-y) <= TOLERANCE for y in reached)
                         and not any(abs(e["to"][1]-y) <= TOLERANCE for y in reached)]
            if not additions:
                break
            reached.extend(additions)
        if not any(abs(target["to_y"]-y) <= TOLERANCE for y in reached):
            errors.append(f"❌ [{', '.join(e['id'] for e in flights)}] 图纸标记 {marker['id']} "
                          f"未连接楼面 {target['from_floor']}→{target['to_floor']}；"
                          f"期望 Y={target['from_y']:g}→{target['to_y']:g}，实际可达标高={reached}")
    low, high = min(t["from_y"] for t in targets), max(t["to_y"] for t in targets)
    extra = [e["id"] for e in flights if e["from"][1] < low-TOLERANCE or e["to"][1] > high+TOLERANCE]
    if extra:
        errors.append(f"❌ [{', '.join(extra)}] 图纸标记 {marker['id']} 的梯段超出明确连接标高 "
                      f"[{low:g}, {high:g}]；墙顶不自动成为到达楼面")
    return errors


def component_geometry_review(blueprint: dict, entities: list[dict], marker: dict) -> dict:
    """精确核对可映射的组合尺寸；旋转/曲面/未知形式列待审核。"""
    from app.agent.knowledge.component_names import resolve_component_name

    design = marker.get("design") or {}
    size, placement = design.get("size") or {}, design.get("placement") or {}
    form = design.get("form") if isinstance(design.get("form"), dict) else {"description": design.get("form")}
    family = resolve_component_name(marker["type"])["entity_type"]
    checked, unverified, errors = [], [], []
    if (len(entities) > 1 or family in {"", "primitive"}) and size and family not in {"door", "window", "roof", "railing", "stair"}:
        boxes = (bool(entities) and not placement.get("face") and not design.get("relation")
                 and not any(form.get(k) for k in ("orientation", "rotation", "rotation_y"))
                 and all(e.get("type") == "primitive" and e.get("shape") == "box"
                         and e.get("rotation", [0, 0, 0]) == [0, 0, 0]
                         and e.get("scale", [1, 1, 1]) == [1, 1, 1]
                         and not any(k.startswith("parent") for k in e)
                         and all(isinstance(e.get(k), list) and len(e[k]) == 3
                                 and all(type(n) in (int, float) and isfinite(n) for n in e[k])
                                 for k in ("position", "dimensions")) for e in entities))
        if boxes:
            bounds = [(min(e["position"][axis]-e["dimensions"][axis]/2 for e in entities),
                       max(e["position"][axis]+e["dimensions"][axis]/2 for e in entities)) for axis in range(3)]
            for key, axis in (("width", 0), ("height", 1), ("depth", 2)):
                if key in size:
                    actual = bounds[axis][1]-bounds[axis][0]
                    checked.append("size."+key)
                    if abs(actual-size[key]) > TOLERANCE:
                        position = placement.get("position")
                        target = (f"；世界 {'XYZ'[axis]} 范围应为 "
                                  f"[{position[axis]-size[key]/2:g}, {position[axis]+size[key]/2:g}]，"
                                  f"实际 [{bounds[axis][0]:g}, {bounds[axis][1]:g}]；"
                                  "零件中心±该轴尺寸/2是外边界，端部杆件厚度也要计入") if position else ""
                        if position:
                            for sign, edge in ((-1, 0), (1, 1)):
                                expected = position[axis]+sign*size[key]/2
                                if abs(bounds[axis][edge]-expected) <= TOLERANCE:
                                    continue
                                boundary = min(entities, key=lambda e: (
                                    abs(e["position"][axis]+sign*e["dimensions"][axis]/2-bounds[axis][edge]),
                                    e["dimensions"][axis]))
                                if boundary["dimensions"][axis] > size[key]+TOLERANCE:
                                    target += f"；[{boundary['id']}].dimensions[{axis}] 超过整组上限 {size[key]:g}，只平移不能解决"
                                else:
                                    target += (f"；若保持零件尺寸，[{boundary['id']}].position[{axis}] "
                                               f"应为 {expected-sign*boundary['dimensions'][axis]/2:g}，"
                                               f"当前 {boundary['position'][axis]:g}；其他越界零件也须回核")
                        errors.append(f"图纸标记 {marker['id']} 的组合设计尺寸 {key}={size[key]:g}，实际 {actual:g}；不能只验证单个零件" + target)
            position = placement.get("position")
            if isinstance(position, list) and len(position) == 3:
                checked.append("placement.position")
                actual = [(a+b)/2 for a, b in bounds]
                if any(abs(a-b) > TOLERANCE for a, b in zip(actual, position)):
                    errors.append(f"图纸标记 {marker['id']} 的组合中心期望 {position}，实际 {actual}")
        else:
            unverified.append("组合整体尺寸与定位需要复核，当前形态不能按未旋转 box 尺度验收")
        if set(size) - {"width", "height", "depth"}:
            unverified.append("组合的其他尺寸参数暂无实体映射")
    elif len(entities) == 1 and family == "beam" and entities[0].get("type") == "beam":
        beam = entities[0]
        a, b = beam.get("from"), beam.get("to")
        valid = (all(isinstance(p, list) and len(p) == 3 and all(type(v) in (int, float) and isfinite(v) for v in p)
                     for p in (a, b)) and not beam.get("curve") and beam.get("crossSection") in {"rect", "i-beam"}
                 and all(type(beam.get(k)) in (int, float) and isfinite(beam[k]) and beam[k] > 0
                         for k in ("width", "height")))
        if valid and abs(a[1]-b[1]) <= TOLERANCE and hypot(b[0]-a[0], b[2]-a[2]) > TOLERANCE:
            dx, dz = abs(b[0]-a[0]), abs(b[2]-a[2])
            length = hypot(dx, dz)
            actual = {"width": dx+beam["width"]*dz/length, "height": beam["height"],
                      "depth": dz+beam["width"]*dx/length}
            for key, value in size.items():
                if key in actual:
                    checked.append("size."+key)
                    if abs(actual[key]-value) > TOLERANCE:
                        errors.append(f"图纸标记 {marker['id']} 的整体 {key}={value:g}，实际 {actual[key]:g}；"
                                      "梁跨度由 from/to 决定，原生 width 是垂直于梁轴的截面宽，不能用跨度替代")
            center = [(p+q)/2 for p, q in zip(a, b)]
            if isinstance(placement.get("position"), list) and any(
                    abs(p-q) > TOLERANCE for p, q in zip(center, placement["position"])):
                errors.append(f"图纸标记 {marker['id']} 的梁中心期望 {placement['position']}，实际 {center}")
        else:
            unverified.append("曲线、倾斜或圆截面梁的整体尺寸需要复核")
    elif len(entities) == 1 and family and entities[0].get("type") == family:
        for key, value in size.items():
            field = NATIVE_SIZE_FIELDS.get((family, key), key)
            (checked if field in entities[0] else unverified).append(
                "size."+key if field in entities[0] else "size."+key+" 未建立原生字段映射")
            if field in entities[0] and (type(entities[0][field]) not in (int, float)
                                         or abs(entities[0][field]-value) > TOLERANCE):
                geometry = blueprint.get("geometry") or {}
                bucket = next((k for k in ("elements", "components") if entities[0] in geometry.get(k, [])), "elements")
                index = geometry.get(bucket, []).index(entities[0]) if entities[0] in geometry.get(bucket, []) else 0
                errors.append(f"设计尺寸 {key}={value}，实际 {field}={entities[0][field]}；"
                              f"/geometry/{bucket}/{index}/{field} 应写 {field}={value}，安装标高另写 from/position")
    if any(form.values()) and family not in {"door", "window", "roof", "railing", "stair"}:
        unverified.append("造型与构造描述需要渲染复核")
    if family == "stair" and not marker.get("floor_connections"):
        unverified.append("楼梯未声明具体楼面连接")
    material_id = marker.get("material_id")
    if design.get("material_role"):
        materials = blueprint.get("materials") or {}
        expected = materials.get(material_id)
        if not isinstance(expected, dict):
            unverified.append("设计材质角色尚未解析为实际材质")
        else:
            from app.agent.generation.material.plan import material_region_field

            definition = {"opacity": 1, **expected}
            references = [e.get(material_region_field(design["material_role"], e.get("type", "")))
                          for e in entities]
            if not any({"opacity": 1, **materials[reference]} == definition
                       for reference in references if isinstance(reference, str)
                       and isinstance(materials.get(reference), dict)):
                errors.append(f"图纸标记 {marker['id']} 未引用设计材质角色 {design['material_role']}")
            else:
                checked.append("material_role 引用")
    return {"status": "needs_review" if unverified else "checked", "checked": checked,
            "unverified": unverified, "errors": errors}


def coalesce_body_walls(blueprint, row, markers, *, diagram_hosts=None):
    """同构造直墙的重叠段只实现一次；保留外露段及被引用的宿主。"""
    from copy import deepcopy
    from collections import Counter
    from app.agent.knowledge.component_names import resolve_component_name
    from app.tools.spatial_tools import _is_finite_vector3, _is_positive_number, _wall_vertical_range

    row = deepcopy(row)
    geometry = row.get("geometry")
    if (not isinstance(geometry, dict) or set(geometry) - {"elements", "components"}
            or any(not isinstance(geometry.get(k, []), list) for k in ("elements", "components"))):
        return row, []
    existing = list(entity_index(blueprint).values())
    incoming = [e for k in ("elements", "components") for e in geometry.get(k, []) if isinstance(e, dict)]
    changes = []
    interior = {h["id"]: h for h in diagram_hosts or []
                if str(h.get("design_path", "")).startswith("/decisions/floor_layouts/")}
    for entity in incoming:
        host = interior.get(entity.get("id"))
        a, b = entity.get("from"), entity.get("to")
        if (not host or entity.get("type") != "wall" or entity.get("curve") or "height" in entity
                or not _is_finite_vector3(a) or not _is_finite_vector3(b) or abs(a[1]-b[1]) > 1e-9):
            continue
        planar = (a[::2], b[::2])
        expected = (host["from"][::2], host["to"][::2])
        if planar != expected and planar != expected[::-1]:
            continue
        before = {"from": list(a), "to": list(b)}
        a[1], b[1] = host["from"][1], host["to"][1]
        changes.append({"rule": "compiler.interior_wall_levels", "entity_id": entity["id"],
                        "design_path": host["design_path"], "before": before,
                        "after": {"from": list(a), "to": list(b)}})

    def strings(value):
        if isinstance(value, str):
            return {value}
        values = value.values() if isinstance(value, dict) else value if isinstance(value, (list, tuple)) else []
        return set().union(*(strings(v) for v in values))

    markers = deepcopy(list(markers))
    marker_index = {m.get("id"): m for m in markers}
    for marker in markers:
        if marker.get("type") != "building_body":
            continue
        layout = (marker.get("design") or {}).get("opening_layout", [])
        for entry in layout:
            full = marker_index.get(entry.get("id"))
            if not full or entry != {"id": full.get("id"), "type": full.get("type"), "host": full.get("host"),
                                     "entity": full.get("entity"), "size": (full.get("design") or {}).get("size", {})}:
                break
        else:
            # 摘要不是另一份宿主依赖；完整标记仍逐个核对安装范围。
            marker.get("design", {}).pop("opening_layout", None)
    referenced, entity_references = strings(markers), set()
    for entity in [*existing, *incoming]:
        entity_references.update(strings({k: v for k, v in entity.items() if k != "id"}))
    referenced.update(entity_references)

    def wall_bounds(entity):
        a, b = entity.get("from"), entity.get("to")
        if (entity.get("type") != "wall" or entity.get("curve") or not entity.get("id")
                or not _is_finite_vector3(a) or not _is_finite_vector3(b)
                or not _is_positive_number(entity.get("thickness"))
                or ("height" in entity and not _is_positive_number(entity["height"]))):
            return None
        axis = 0 if abs(a[2]-b[2]) < 1e-9 else 2 if abs(a[0]-b[0]) < 1e-9 else None
        low, high = _wall_vertical_range(entity)
        if axis is None or abs(a[axis]-b[axis]) < 1e-9 or high-low < 1e-9:
            return None
        properties = {k: v for k, v in entity.items() if k not in {"id", "from", "to", "height"}}
        return axis, a[2-axis], min(a[axis], b[axis]), max(a[axis], b[axis]), low, high, properties

    def keeps_host_frame(entity, bounds, segments):
        if entity["id"] in entity_references:
            return False
        if not segments:
            preview = {"geometry": {"elements": [e for e, _ in kept]}}
            attached = [m for m in markers if entity["id"] in strings(m)]
            return bool(attached) and all(
                m.get("id") != entity["id"] and m.get("entity", {}).get("parentWall") == entity["id"]
                and opening_host(preview, m, diagram_hosts=diagram_hosts) is not None for m in attached)
        if len(segments) != 1:
            return False
        axis = bounds[0]
        left, right = segments[0]
        start = right if entity["from"][axis] > entity["to"][axis] else left
        shift = (start-entity["from"][axis]) * (1 if entity["to"][axis] > entity["from"][axis] else -1)
        for marker in markers:
            if entity["id"] not in strings(marker):
                continue
            spec, design = marker.get("entity") or {}, marker.get("design") or {}
            if (marker.get("id") == entity["id"] or spec.get("parentWall") != entity["id"]
                    or not marker.get("diagram_host")):
                return False
            diagram = marker["diagram_host"]
            if (diagram["from"][::2] != entity["from"][::2]
                    or (diagram["to"][axis]-diagram["from"][axis]) * (entity["to"][axis]-start) <= 0):
                return False
            if shift and resolve_component_name(marker["type"])["entity_type"] not in {"door", "window"}:
                return False
            width = (design.get("size") or {}).get("width")
            if not width and design.get("bay") and design.get("bays"):
                width = (bounds[3]-bounds[2])/design["bays"]
            if not width:
                return False
            target = opening_target(marker, diagram, width, 0)
            if target is None or target[0]-shift < -TOLERANCE or target[0]-shift+width > right-left+TOLERANCE:
                return False
        return True

    kept = [(e, wall_bounds(e)) for e in existing if wall_bounds(e)]
    counts = Counter(e.get("id") for e in incoming if isinstance(e.get("id"), str))
    existing_ids = {e["id"] for e in existing}
    walls = [(e, wall_bounds(e)) for e in geometry.get("elements", [])
             if isinstance(e, dict) and isinstance(e.get("id"), str) and counts[e["id"]] == 1
             and e["id"] not in existing_ids and wall_bounds(e)]
    walls.sort(key=lambda pair: (-(pair[1][3]-pair[1][2])*(pair[1][5]-pair[1][4]), pair[0]["id"] not in referenced))
    replacements = {}
    reserved_ids = existing_ids | set(counts) | referenced
    for entity, bounds in walls:
        segments, owners = [(bounds[2], bounds[3])], []
        for other, limits in kept:
            if (bounds[:2] != limits[:2] or bounds[6] != limits[6]
                    or limits[4] > bounds[4] or limits[5] < bounds[5]):
                continue
            if bounds[4:6] != limits[4:6] and not (limits[2] <= bounds[2] and limits[3] >= bounds[3]):
                continue
            remaining = []
            for left, right in segments:
                if max(left, limits[2]) >= min(right, limits[3]):
                    remaining.append((left, right))
                    continue
                if left < limits[2]:
                    remaining.append((left, limits[2]))
                if right > limits[3]:
                    remaining.append((limits[3], right))
            if remaining != segments:
                owners.append(other["id"])
            segments = remaining
        if not owners or (entity["id"] in referenced and not keeps_host_frame(entity, bounds, segments)):
            kept.append((entity, bounds))
            continue
        axis = bounds[0]
        reverse = entity["from"][axis] > entity["to"][axis]
        pieces = []
        for index, (left, right) in enumerate(reversed(segments) if reverse else segments):
            piece = deepcopy(entity)
            piece["from"][axis], piece["to"][axis] = (right, left) if reverse else (left, right)
            if index:
                piece["id"] = f"{entity['id']}__shared_{index+1}"
                while piece["id"] in reserved_ids:
                    piece["id"] += "_auto"
            reserved_ids.add(piece["id"])
            pieces.append(piece)
            kept.append((piece, wall_bounds(piece)))
        replacements[entity["id"]] = pieces
        changes.append({"rule": "compiler.shared_wall", "entity_id": entity["id"],
                        "retained_entity_id": owners[0], "retained_entity_ids": owners,
                        "before": entity, "after": pieces[0] if len(pieces) == 1 else pieces or None,
                        "semantic_change": False})
    geometry["elements"] = [part for e in geometry.get("elements", [])
                            for part in (replacements.get(e.get("id"), [e]) if isinstance(e, dict) else [e])]
    return row, changes


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
    design = marker["design"]
    position = (design.get("placement") or {}).get("position")
    height = (design.get("size") or {}).get("height")
    if position and type(height) in (int, float) and height > 0:
        # 显式构件按整体中心定位；自动屋面标记才直接使用墙顶标高。
        elevation = position[1] - height / 2
    native_roofs = {e["id"]: e for e in entities if e.get("type") == "roof"}
    regions, projected, below = [], [], []
    for x0, x1, z0, z1, y, entity_id in _roof_footprint_entries(entities, walls):
        roof = native_roofs[entity_id]
        surface_y = y + roof["thickness"] if roof.get("roofType") == "flat" else y
        projected.append((x0, z0, x1, z1))
        if surface_y >= elevation-TOLERANCE:
            regions.append((x0, z0, x1, z1))
        else:
            below.append(f"[{entity_id}] 原生屋面支承标高 {surface_y:.3f}m 低于图纸要求 {elevation:.3f}m；"
                         "图纸 placement.position 是整体中心，size.height 为整体高度；"
                         "核对图纸中心、相对墙顶高差与实际支承，不能只修改覆盖宽深")
    for entity in entities:
        if entity.get("type") == "floor" and entity.get("shape", "rect") == "rect":
            a, b = entity["from"], entity["to"]
            if a[1]+entity["thickness"] >= elevation-TOLERANCE:
                regions.append((min(a[0], b[0]), min(a[2], b[2]), max(a[0], b[0]), max(a[2], b[2])))
                projected.append(regions[-1])
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
            bounds = (x-w/2*cos(rz), z-d/2*cos(rx), x+w/2*cos(rz), z+d/2*cos(rx))
            a, b, c, e = bounds
            a, b = max(a, volume["x"]), max(b, volume["z"])
            c, e = min(c, volume["x"]+volume["width"]), min(e, volume["z"]+volume["depth"])
            # 外挑屋檐允许继续降坡；标高校验只针对体量内的承托区域。
            lowest = (y+h/2*cos(rx)*cos(rz)+min((a-x)*tan(rz), (c-x)*tan(rz))
                      -max((b-z)*tan(rx), (e-z)*tan(rx))) if a <= c and b <= e else (
                          y+h/2*cos(rx)*cos(rz)-abs(d/2*sin(rx))-abs(w/2*sin(rz)))
            projected.append(bounds)
            if lowest >= elevation-TOLERANCE:
                regions.append(bounds)
            else:
                below.append(f"[{entity['id']}] 体量内屋面最低标高 {lowest:.3f}m 低于承托标高 {elevation:.3f}m；"
                             f"/position/1 当前 {y:.3f}，保持尺寸和坡角时中心Y至少为 {y+elevation-lowest:.3f}m；"
                             "同时落实斜屋面与墙顶的封闭支承，不能只抬高屋面留下缝隙")
    overhang = marker["design"].get("overhang", 0)
    target = (volume["x"]-overhang, volume["z"]-overhang,
              volume["x"]+volume["width"]+overhang, volume["z"]+volume["depth"]+overhang)
    missing = rectangle_uncovered_area(target, [(a-TOLERANCE, b-TOLERANCE, c+TOLERANCE, d+TOLERANCE)
                                               for a, b, c, d in regions])
    if missing > TOLERANCE and below:
        projected_missing = rectangle_uncovered_area(target, [(a-TOLERANCE, b-TOLERANCE, c+TOLERANCE, d+TOLERANCE)
                                                              for a, b, c, d in projected])
        coverage = ("平面投影已覆盖体量及出檐" if projected_missing <= TOLERANCE else
                    f"平面投影还缺少 {projected_missing:.3f}㎡，核对倾斜后上表面的 X/Z 中心与投影宽深")
        return [f"❌ [{entities[0]['id']}] 图纸标记 {marker['id']}：{coverage}；" + "；".join(below)]
    return ([f"❌ [{entities[0]['id']}] 图纸标记 {marker['id']}：屋面未覆盖负责体量及出檐，"
             f"缺少 {missing:.3f}㎡；目标 X/Z 范围 {target}，已有上表面投影 {regions[:6]}；"
             "核对倾斜后的投影尺寸及中心，保持连续屋面，不能只返回封檐条；当前可核对 roof、矩形 floor 和单轴倾斜 box"]
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


def balcony_geometry(blueprint):
    from app.agent.generation.assembly.merge import balcony_footprint
    from app.tools.spatial_tools import _is_finite_vector3
    index = entity_index(blueprint)
    points = [p for w in index.values() if w.get("type") == "wall"
              for p in (w.get("from"), w.get("to")) if _is_finite_vector3(p)]
    if not points:
        return {}
    center = ((min(p[0] for p in points)+max(p[0] for p in points))/2,
              (min(p[2] for p in points)+max(p[2] for p in points))/2)
    result = {}
    for entity in index.values():
        wall = index.get(entity.get("parentWall"))
        if entity.get("type") != "balcony" or not wall or wall.get("curve"):
            continue
        footprint = balcony_footprint(entity, wall, center)
        if footprint:
            result[entity["id"]] = footprint
    return result


def railing_design_errors(blueprint, entities, marker):
    from app.agent.knowledge.component_names import resolve_component_name
    if resolve_component_name(marker["type"])["entity_type"] != "railing":
        return []
    footprints = balcony_geometry(blueprint)
    parents = [i for i in marker.get("host_entity_ids", [marker.get("host")]) if i in footprints]
    if len(parents) != 1:
        return []
    parent_id = parents[0]
    footprint = footprints[parent_id]
    index = entity_index(blueprint)
    x0, x1, z0, z1 = footprint["bounds"]
    errors = []
    for railing in entities:
        if railing.get("type") != "railing":
            continue
        path = railing["path"]
        floor = index.get(railing.get("parentFloor"))
        if floor and floor.get("type") == "floor":
            a, b = floor["from"], floor.get("to", floor["from"])
            origin = a if floor.get("shape") == "circle" else [min(a[0], b[0]), a[1], min(a[2], b[2])]
            path = [[p[0]+origin[0], p[1]+origin[1]+floor["thickness"], p[2]+origin[2]] for p in path]
        if any(not (x0-TOLERANCE <= x <= x1+TOLERANCE and z0-TOLERANCE <= z <= z1+TOLERANCE
                    and abs(y-footprint["top_y"]) <= TOLERANCE) for x, y, z in path):
            errors.append(f"❌ [{railing['id']}] 图纸标记 {marker['id']}：栏杆路径未落在实际阳台 {parent_id} 的板顶范围；"
                          f"世界边缘 path={footprint['path']}，核对室外方向、标高和 parentFloor 坐标语义")
    return errors


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


def opening_cell_limits(marker):
    """自动立面标记的开间范围；显式实例仍按其批准尺寸和位置验收。"""
    spec, design = marker.get("entity") or {}, marker.get("design") or {}
    diagram = marker.get("diagram_host") or {}
    bays = design.get("bays")
    if ("centerAlong" not in spec or type(bays) is not int or bays < 1
            or diagram.get("curve") or not all(isinstance(diagram.get(k), list)
            and len(diagram[k]) == 3 for k in ("from", "to"))):
        return None
    a, b = diagram["from"], diagram["to"]
    width = hypot(b[0]-a[0], b[2]-a[2])/bays
    center, bottom = spec["centerAlong"], spec["bottomY"]
    return {"along_min": center-width/2, "along_max": center+width/2,
            "bottom_y": bottom, "max_width": width, "max_height": max(a[1], b[1])-bottom}


def opening_host(blueprint, marker, *, diagram_hosts=None):
    """缺少示意墙时，查找唯一完整覆盖其安装框的真实直墙。"""
    from app.agent.knowledge.component_names import resolve_component_name
    from app.tools.spatial_tools import _is_finite_vector3, _is_positive_number, _wall_vertical_range
    index = entity_index(blueprint)
    host = index.get(marker.get("entity", {}).get("parentWall"))
    if host is not None:
        return host if host.get("type") == "wall" else None
    diagram, size = marker.get("diagram_host") or {}, marker.get("design", {}).get("size") or {}
    if (resolve_component_name(marker.get("type", ""))["entity_type"] not in {"door", "window"}
            or diagram.get("curve") or not all(_is_finite_vector3(diagram.get(k)) for k in ("from", "to"))
            or not all(_is_positive_number(size.get(k)) for k in ("width", "height"))):
        return None
    a, b = diagram["from"], diagram["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    if length <= TOLERANCE or opening_target(marker, diagram, size["width"], size["height"]) is None:
        return None
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    allowed = {w["id"] for w in diagram_hosts} if diagram_hosts is not None else None
    candidates = []
    for wall in index.values():
        if (wall.get("type") != "wall" or wall.get("curve")
                or (allowed is not None and wall["id"] not in allowed)
                or not all(_is_finite_vector3(wall.get(k)) for k in ("from", "to"))
                or not _is_positive_number(wall.get("thickness"))):
            continue
        p, q = wall["from"], wall["to"]
        along = [(v[0]-a[0])*ux+(v[2]-a[2])*uz for v in (p, q)]
        normal = [-(v[0]-a[0])*uz+(v[2]-a[2])*ux for v in (p, q)]
        low, high = _wall_vertical_range(wall)
        if (max(map(abs, normal)) <= TOLERANCE and min(along) <= TOLERANCE
                and max(along) >= length-TOLERANCE
                and low <= min(a[1], b[1])+TOLERANCE and high >= max(a[1], b[1])-TOLERANCE):
            candidates.append(wall)
    return candidates[0] if len(candidates) == 1 else None


def body_host_errors(blueprint, markers, *, diagram_hosts=None):
    """主体交接前核对开敞面与门窗宿主；不把示意定位框当实体墙。"""
    from app.agent.knowledge.component_names import resolve_component_name
    from app.tools.spatial_tools import MAX_OPENING_NORMAL_OFFSET, _is_finite_vector3, _wall_vertical_range
    from .openings import is_open_side
    from .coordinates import floor_elevations, representative_floor_indices, rectangle_uncovered_area
    from .contracts import MassingDecision
    errors = []
    for marker in markers:
        if marker["type"] == "building_body" and marker.get("design", {}).get("massing"):
            design = marker["design"]
            elevations = floor_elevations(design)
            indices = representative_floor_indices(MassingDecision.model_validate(design["massing"]))
            walls = [w for w in entity_index(blueprint).values() if w.get("type") == "wall" and not w.get("curve")
                     and all(_is_finite_vector3(w.get(k)) for k in ("from", "to"))]
            open_faces, closed_faces = [], []
            for volume in design.get("volumes", []):
                x, z, w, d = (volume[k] for k in ("x", "z", "width", "depth"))
                frames = {"front": (2, z, 0, x, x+w), "back": (2, z+d, 0, x, x+w),
                          "left": (0, x, 2, z, z+d), "right": (0, x+w, 2, z, z+d)}
                for floor in range(volume["start_floor"], volume["end_floor"]+1):
                    for face, facade in {**design.get("facades", {}), **volume.get("facades", {})}.items():
                        pattern = facade["ground_pattern"] if floor == 1 else facade["upper_pattern"]
                        normal, plane, axis, left, right = frames[face]
                        bottom, top = elevations[indices[floor-1]], elevations[indices[floor-1]+1]
                        target = open_faces if is_open_side(pattern) else closed_faces
                        target.append((volume["id"], face, floor, normal, plane, axis, left, right, bottom, top))
            for volume_id, face, floor, normal, plane, axis, left, right, bottom, top in open_faces:
                shared = [(a, y0, b, y1) for owner, _, _, n, p, _, a, b, y0, y1 in closed_faces
                          if owner != volume_id and n == normal and abs(p-plane) <= TOLERANCE]
                if rectangle_uncovered_area((left, bottom, right, top), shared) <= TOLERANCE:
                    continue  # 开敞体量不重复建墙，也不撤销另一体量明确设计的共用围护。
                for wall in walls:
                    a, b = wall["from"], wall["to"]
                    low, high = _wall_vertical_range(wall)
                    if (max(abs(a[normal]-plane), abs(b[normal]-plane)) <= TOLERANCE
                            and min(a[axis], b[axis]) <= left+TOLERANCE and max(a[axis], b[axis]) >= right-TOLERANCE
                            and low <= bottom+TOLERANCE and high >= top-TOLERANCE):
                        errors.append(f"❌ [{wall['id']}] 体量 {volume_id} 的 {face} L{floor} 明确开敞，却生成整面实体墙；"
                                      "该界面未被其他体量已声明的实墙围护完整覆盖；按 open 保留无墙空间，定位参考不能编成薄 wall")
        family = resolve_component_name(marker["type"])["entity_type"]
        host_id = marker.get("entity", {}).get("parentWall")
        diagram = marker.get("diagram_host")
        if family not in {"door", "window"} or not host_id or not diagram or diagram.get("curve"):
            continue
        prefix = f"主体宿主 {host_id} 无法承接图纸标记 {marker['id']}："
        wall = opening_host(blueprint, marker, diagram_hosts=diagram_hosts)
        if not wall or wall.get("type") != "wall":
            errors.append(prefix + "缺少真实墙或唯一完整共用墙；保持 diagram_hosts 的安装范围")
            continue
        size = marker.get("design", {}).get("size") or {}
        width, height = size.get("width", 0), size.get("height", 0)
        probe = {"id": marker["id"], "type": family, "parentWall": wall["id"],
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
            if start < -TOLERANCE or start+width > length+TOLERANCE:
                errors.append(prefix + "墙段未覆盖安装位置；不要把原宿主ID留给一小段墙，门窗会由原生洞口裁墙")
            if bottom < min(a[1], b[1])-TOLERANCE or bottom+height > max(a[1], b[1])+TOLERANCE:
                errors.append(prefix + f"门窗竖向标高 [{bottom:g}, {bottom+height:g}] 超出墙高 "
                              f"[{min(a[1], b[1]):g}, {max(a[1], b[1]):g}]；按 diagram_hosts 修订墙底、墙顶 Y，不能改门窗位置掩盖缺失墙高")
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
    changes = []
    host_id = marker.get("entity", {}).get("parentWall")
    host_ids = [host_id]
    declared_host = marker.get("design", {}).get("host")
    if marker.get("diagram_host") and declared_host and declared_host not in entity_index(blueprint):
        host_ids.append(declared_host)
    wall = opening_host(blueprint, marker)
    if wall and any(e.get("parentWall") in host_ids and e.get("parentWall") != wall["id"] for e in entities):
        a, b = marker["diagram_host"]["from"], marker["diagram_host"]["to"]
        p, q = wall["from"], wall["to"]
        length = hypot(q[0]-p[0], q[2]-p[2])
        vx, vz = (q[0]-p[0])/length, (q[2]-p[2])/length
        direction = 1 if (b[0]-a[0])*vx+(b[2]-a[2])*vz > 0 else -1
        for entity in entities:
            if (entity.get("type") not in {"door", "window", "opening"}
                    or entity.get("parentWall") not in host_ids or entity.get("parentWall") == wall["id"]):
                continue
            start, y, normal = entity["from"]
            before = {"parentWall": entity["parentWall"], "from": list(entity["from"])}
            entity["parentWall"] = wall["id"]
            entity["from"] = [(a[0]-p[0])*vx+(a[2]-p[2])*vz+direction*start
                              -(entity["width"] if direction < 0 else 0), y,
                              -(a[0]-p[0])*vz+(a[2]-p[2])*vx+direction*normal]
            changes.append({"rule": "compiler.opening_host", "entity_id": entity["id"], "before": before,
                            "after": {"parentWall": entity["parentWall"], "from": list(entity["from"])}})
    frame = _opening_frame(blueprint, entities, marker)
    if not frame:
        return row, changes
    index, diagram, openings, (ux, uz), (left, right, bottom, top), normals = frame
    target = opening_target(marker, diagram, right-left, top-bottom)
    if target is None:
        return row, changes
    # 不消除组内法向错位；它仍应由同一门窗验收报告。
    da, dy, dn = target[0]-left, target[1]-bottom, target[2]-normals[0]
    if max(abs(da), abs(dy), abs(dn)) <= TOLERANCE:
        return row, changes
    dx, dz = ux*da-uz*dn, uz*da+ux*dn
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
    limits = opening_cell_limits(marker)
    if limits and (left < limits["along_min"]-TOLERANCE or right > limits["along_max"]+TOLERANCE):
        errors.append(prefix + f"整组洞口占用相邻开间；本开间沿墙范围 "
                      f"[{limits['along_min']:g}, {limits['along_max']:g}]，实际 [{left:g}, {right:g}]；"
                      f"整组宽度不得超过 {limits['max_width']:g}m，保持图纸中心不变")
    if limits and top > limits["bottom_y"]+limits["max_height"]+TOLERANCE:
        errors.append(prefix + f"整组洞口超过本层开间顶部；高度不得超过 {limits['max_height']:g}m，保持图纸底标高不变")
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


def canopy_mount_target(blueprint, marker):
    """将已批准的板中心换算成 Core 的附墙起点，供提示与验收共用。"""
    from app.agent.knowledge.component_names import resolve_component_name
    if resolve_component_name(marker["type"])["entity_type"] != "canopy":
        return None
    spec, size = marker.get("entity") or {}, marker.get("design", {}).get("size") or {}
    wall = entity_index(blueprint).get(spec.get("parentWall"))
    position = spec.get("position")
    if (not wall or wall.get("type") != "wall" or wall.get("curve")
            or not isinstance(position, list) or len(position) != 3
            or not all(type(size.get(k)) in (int, float) and size[k] > 0 for k in ("width", "depth"))):
        return None
    a, b = wall["from"], wall["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    if length <= TOLERANCE:
        return None
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    along = (position[0]-a[0])*ux+(position[2]-a[2])*uz-size["width"]/2
    probe = {"parentWall": wall["id"], "width": size["width"], "from": [along, position[1], 0]}
    center = wall_attached_point(blueprint, probe, along+size["width"]/2, position[1], size["depth"]/2)
    normal = -(position[0]-center[0])*uz+(position[2]-center[2])*ux
    return {"parentWall": wall["id"], "from": [along, position[1], normal]}


def canopy_design_errors(blueprint, entities, marker):
    from app.agent.knowledge.component_names import resolve_component_name
    if resolve_component_name(marker["type"])["entity_type"] != "canopy":
        return []
    canopies = [e for e in entities if e.get("type") == "canopy"]
    if len(canopies) != 1:
        return []  # 自定义组合保留现有几何审核，不猜测其安装框。
    canopy = canopies[0]
    target = canopy_mount_target(blueprint, marker)
    errors = []
    if target and (canopy.get("parentWall") != target["parentWall"]
                   or any(abs(a-b) > TOLERANCE for a, b in zip(canopy["from"], target["from"]))):
        errors.append(f"❌ [{canopy['id']}] 图纸雨棚板中心必须保持 {marker['entity']['position']}；"
                      f"附墙安装应为 parentWall={target['parentWall']}，from={target['from']}，"
                      "from[0] 为板左端沿墙距离，from[2] 为安装偏移，不能直接填写板中心法向距离")
    for field, value in (marker.get("design", {}).get("size") or {}).items():
        actual_field = NATIVE_SIZE_FIELDS.get(("canopy", field), field)
        if actual_field in canopy and abs(canopy[actual_field]-value) > TOLERANCE:
            errors.append(f"❌ [{canopy['id']}] 图纸雨棚 {actual_field} 应为 {value}，实际 {canopy[actual_field]}；不能改变尺寸绕过宿主边界")
    return errors


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
