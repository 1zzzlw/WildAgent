"""设计标记与落实记录；一个标记允许由多个 WILD 元素共同表达。"""
from copy import deepcopy

IMPLEMENTATION_STAGES = ("generate", "repair_1", "repair_2")


def body_floor_errors(entities, design):
    """按真实楼板轮廓和留洞核对主体，不再使用矩形包围盒替代实际占地。"""
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    from app.domain.design.spatial import resolve_geometry

    context = design.get("geometry_context") or resolve_geometry(design)
    expected = context.get("slabs", [])
    errors = []
    for entity in entities:
        if entity.get("type") != "floor":
            continue
        start = entity.get("from")
        thickness = entity.get("thickness")
        if not isinstance(start, list) or not isinstance(thickness, (int, float)):
            continue
        top = start[1] + thickness
        if entity.get("shape") == "polygon":
            outer = [[start[0]+x, start[2]+z] for x,z in entity["polygon"]]
            holes = []
            for ring in entity.get("holes", []):
                holes.append([[start[0]+x,start[2]+z] for x,z in ring])
            actual = Polygon(outer, holes)
        elif entity.get("shape", "rect") == "rect" and entity.get("to"):
            end = entity["to"]
            actual = box(min(start[0],end[0]),min(start[2],end[2]),
                         max(start[0],end[0]),max(start[2],end[2]))
        else:
            continue
        matching = [Polygon(slab["outer"],slab["holes"]) for slab in expected if abs(slab["top_y"]-top) <= 0.001]
        if not matching:
            errors.append(f"[{entity['id']}] 板顶Y={top:g}没有对应图纸楼板；不能把楼面改成墙顶或任意标高")
            continue
        allowed = unary_union(matching)
        outside = actual.difference(allowed.buffer(0.001)).area
        if outside > 0.001:
            errors.append(f"[{entity['id']}] 主体楼板超出图纸真实轮廓或覆盖显式挑空 {outside:.3f}㎡；"
                          "请按slabs/voids保留庭院和楼梯孔，不能铺满体量包围盒")
    return errors


def component_markers(document, geometry=None):
    """统一从已解析的墙、板和构件生成任务标记；历史立面只在输入转换中展开一次。"""
    from math import hypot
    from shapely.geometry import LineString, Point
    from app.domain.components.names import resolve_component_name
    from app.domain.design.spatial import elevation, execution_view, host_point, issue, resolve_geometry

    original = document.decisions.model_dump(mode="json")
    facts = geometry or resolve_geometry(original)
    source = facts["source"]
    hosts = {host["id"]:host for host in facts["hosts"]}
    levels = {level["id"]:level for level in source["levels"]}
    material_plan = document.decisions.materials.resolved_plan
    material_ids = {role.role:role.materialId for role in material_plan.roles} if material_plan else {}
    body_design = execution_view(original, facts)
    body_design["delegated_components"] = source.get("components", [])
    rows = [{"id":"building_body","type":"building_body","host":"","depends_on":[],
             "design":body_design,"entity":{},"geometry":deepcopy(facts["body_geometry"])}]
    roles = {host["id"]:host.get("material_role") for host in facts["hosts"]}
    roles.update({slab["id"]:slab.get("material_role") for slab in facts["slabs"]})
    rows[0]["construction_materials"] = material_ids
    rows[0]["geometry_material_roles"] = roles
    explicit = list(source.get("components", []))
    for roof in source.get("roofs", []):
        shape = roof["geometry"]
        explicit.append({"id":roof["id"],"type":"roof","host":roof["host"],"size":{},
                         "form":deepcopy(shape),"material_role":roof.get("material_role"),
                         "support":roof["support"],"roof_geometry":shape,"placement":{}})
    explicit.extend(source.get("_automatic_openings", []))
    identities = {component["id"] for component in explicit}
    for index,item in enumerate(explicit):
        design = deepcopy(item)
        form = design.setdefault("form", {})
        form.update(design.get("parameters") or {})
        if design.get("system"):
            system = source["systems"][design["system"]]
            if system.get("construction"):
                form["construction"] = deepcopy(system["construction"])
        host_id = design.get("host") or ""
        placement = design.get("placement") or {}
        size = design.setdefault("size", {})
        family = resolve_component_name(design["type"])["entity_type"] or design["type"]
        entity = {}
        host = hosts.get(host_id)
        position = placement.get("position")
        if position:
            position = list(position)
            if placement.get("anchor") in {"base_center","footprint_center_at_base","bottom_center"}:
                position[1] += size.get("height",0)/2
            entity["position"] = position
        if host:
            if position and family in {"door","window","opening","bay_window"}:
                path = LineString(host["path"])
                center = path.project(Point(position[0],position[2]))
                start = center-size.get("width",0)/2
                bottom = position[1]-size.get("height",0)/2
                reference = host_point(host,center,bottom)
                tangent_end = host_point(host,min(host["length"],center+0.001),bottom)
                dx,dz = tangent_end[0]-reference[0],tangent_end[2]-reference[2]
                length = hypot(dx,dz) or 1
                normal = -(position[0]-reference[0])*dz/length+(position[2]-reference[2])*dx/length
                entity["from"] = [start,bottom,normal]
            elif not position:
                bottom = (elevation(placement["elevation"],levels) if placement.get("elevation")
                          else host["from"][1]+placement.get("sill_height",0))
                start = placement.get("offset",0)
                normal = placement.get("normal_offset",0)
                if not item.get("_automatic") and placement.get("mode") == "wall":
                    if placement.get("anchor") in {"center","opening_center_bottom"}:
                        start -= size.get("width",0)/2
                    if placement.get("anchor") == "center":
                        bottom -= size.get("height",0)/2
                if item.get("_automatic"):
                    entity.update(centerAlong=start,bottomY=bottom)
                else:
                    entity["from"] = [start,bottom,normal]
                entity["position_hint"] = host_point(host,start,bottom,normal)
            entity["parentWall"] = host_id
        elif family in {"door","window","opening","bay_window"}:
            issue(f"/components/{index}/host","门窗宿主没有解析成墙面",actual=host_id)
        dependencies = {"building_body"}
        if host_id in identities:
            dependencies.add(host_id)
        relation_target = (design.get("relation") or {}).get("target")
        if relation_target in identities:
            dependencies.add(relation_target)
        marker = {"id":design["id"],"type":resolve_component_name(design["type"])["kind"],"host":host_id,
                  "depends_on":sorted(dependencies),"design_path":f"/decisions/components/{index}",
                  "design":design,"entity":entity,"construction_materials":material_ids}
        if host:
            marker["diagram_host"] = host
            native_curve = host.get("curve") or {}
            if (host["varying_section"] or host["curved"] and native_curve.get("type") != "arc") and family in {"door","window","opening","bay_window"}:
                marker["capability_gaps"] = [{"entity":design["id"],"field":"host",
                    "code":"varying_wall_opening","expected":"放样墙面上的真实洞口和框扇",
                    "actual":"当前WILD门窗宿主仍要求wall；保留设计，需对应曲面开洞能力"}]
        if placement.get("mode") in {"anchor","surface"}:
            marker.setdefault("capability_gaps", []).append({"entity":design["id"],"field":"placement",
                "code":"placement_not_implemented","expected":placement["mode"],
                "actual":"当前构件执行入口尚未解析此定位方式，保留设计但不猜测安装位置"})
        if placement.get("mode") == "world" and placement.get("anchor") not in {"center","base_center","bottom_center","footprint_center_at_base"}:
            marker.setdefault("capability_gaps", []).append({"entity":design["id"],"field":"placement.anchor",
                "code":"anchor_not_implemented","expected":placement.get("anchor"),
                "actual":"此世界锚点尚无确定的中心转换规则，不能默认当作center"})
        if placement.get("mounting") == "tangent_plane" and host and host["curved"]:
            marker.setdefault("capability_gaps", []).append({"entity":design["id"],"field":"placement.mounting",
                "code":"mounting_not_implemented","expected":"tangent_plane",
                "actual":"现有圆弧门窗沿墙展开，尚未实现独立切平面安装"})
        role = design.get("material_role")
        if role in material_ids:
            marker["material_id"] = material_ids[role]
        if family == "stair":
            from app.domain.design.coordinates import floor_connection_targets
            targets,problems = floor_connection_targets(original,design)
            if problems:
                issue(f"/components/{index}/floor_connections","楼梯连接无效",actual=problems)
            marker["floor_connections"] = targets
            if targets and design.get("footprint"):
                from app.domain.design.spatial import profile_polygon
                profiles = {profile["id"]:profile for profile in source["profiles"]}
                x0,z0,x1,z1 = profile_polygon(design["footprint"],profiles).bounds
                size.setdefault("width",x1-x0)
                size.setdefault("depth",z1-z0)
                size.setdefault("height",max(t["to_y"] for t in targets)-min(t["from_y"] for t in targets))
                if position and placement.get("anchor") == "footprint_center_at_base":
                    entity["position"][1] = placement["position"][1]+size["height"]/2
                if position:
                    from shapely import affinity
                    from app.domain.design.spatial import polygon_data

                    footprint = profile_polygon(design["footprint"],profiles)
                    footprint = affinity.rotate(footprint,-placement.get("rotation",[0,0,0])[1],origin=(0,0),use_radians=True)
                    footprint = affinity.translate(footprint,position[0],position[2])
                    marker["footprint_geometry"] = polygon_data(footprint)
        if family == "roof" and host_id in facts["volumes"]:
            volume = facts["volumes"][host_id]
            x0,z0,x1,z1 = volume["bounds"]
            support = elevation(design["support"],levels) if design.get("support") else volume["roof_support_y"]
            shape = design.get("roof_geometry") or original.get("roof") or {}
            overhang = shape.get("overhang",0)
            design["volume"] = {"id":host_id,"x":x0,"z":z0,"width":x1-x0,"depth":z1-z0}
            design["roof_type"] = shape.get("type") or form.get("roof_type") or original.get("roof",{}).get("type")
            design["overhang"] = overhang
            entity.setdefault("position",[x0+(x1-x0)/2,support,z0+(z1-z0)/2])
            from app.domain.design.spatial import resolve_region, section_at, section_polygon, polygon_data

            section = section_at(volume["sections"],support)
            outline = shape.get("outline") or {}
            if outline.get("type") in {"profile_region","volume_union_section"}:
                resolved = resolve_region(outline,levels,
                    {profile["id"]:profile for profile in source["profiles"]},
                    {volume["id"]:volume for volume in source["volumes"]},
                    {identity:volume["sections"] for identity,volume in facts["volumes"].items()})
                if resolved.geom_type != "Polygon":
                    issue(f"/roofs/{design['id']}/geometry/outline","多片离散屋面须分别声明独立屋面ID")
                marker["resolved_outline"] = polygon_data(resolved)
            elif section is not None:
                marker["resolved_outline"] = polygon_data(section_polygon(section))
            else:
                issue(f"/roofs/{design['id']}/support","屋面支承标高处没有可用宿主截面")
        rows.append(marker)
    for relation in source.get("relations", []):
        subject = next((row for row in rows if row["id"] == relation["subject"]),None)
        if subject and relation["type"] == "supported_by":
            subject["design"].setdefault("support_targets",[]).extend(relation.get("targets",[]))
    if len({row["id"] for row in rows}) != len(rows):
        issue("/components/id","构件标记ID重复；building_body为保留ID")
    rows[0]["design"]["opening_layout"] = [
        {"id":row["id"],"type":row["type"],"host":row["host"],"entity":row["entity"],"size":row["design"].get("size",{})}
        for row in rows[1:] if resolve_component_name(row["type"])["entity_type"] in {"door","window"}
    ]
    return rows


def marker_results(state):
    results = {}
    for fragments in (state.get("component_fragments") or {}).values():
        for entity in fragments if isinstance(fragments, list) else []:
            if entity["id"] in results:
                raise ValueError(f"重复构件结果：{entity['id']}")
            results[entity["id"]] = entity
    return results


def implementation_records(state):
    result = {}
    for diag in (state.get("component_diagnostics") or {}).values():
        for key, value in (diag.get("implementations") or {}).items():
            result[key] = value
    return result


def merge_marker_resources(blueprint, diag):
    for key in ("materials", "assets"):
        for name, definition in (diag.get(key) or {}).items():
            if name in blueprint[key] and blueprint[key][name] != definition:
                raise ValueError(f"/{key}/{name} 的片段定义冲突；不能按合并顺序覆盖材质或资产")
            blueprint[key].setdefault(name, deepcopy(definition))


def implementation_complete(record):
    return bool(record and record.get("status") in {"implemented", "abandoned"})


def assemble_marker_results(document, state):
    from app.domain.design.resolver import _stable_hash
    from app.domain.design.compilation import RESOLVER_VERSION
    reviewed = state.get("resolved_design") or {}
    if reviewed.get("design_hash") != _stable_hash(document) or reviewed.get("resolver_version") != RESOLVER_VERSION:
        raise ValueError("落实记录与审核图纸版本不一致")
    blueprint = deepcopy(state["skeleton_blueprint"])
    entities = marker_results(state)
    records = implementation_records(state)
    expected = {m["id"] for m in component_markers(document)}
    if set(records) - expected:
        raise ValueError("落实记录含有未设计标记")
    owned = set()
    for record in records.values():
        if not record.get("status") == "implemented":
            continue
        for entity_id in record["entity_ids"]:
            owned.add(entity_id)
    if owned != set(entities):
        raise ValueError("落实记录与实际构件集合不一致")
    for diag in (state.get("component_diagnostics") or {}).values():
        for bucket in ("elements", "components"):
            blueprint["geometry"][bucket].extend(deepcopy(entities[i]) for i in diag.get(bucket, []) if i in entities)
        merge_marker_resources(blueprint, diag)
    missing = sorted(i for i in expected if not implementation_complete(records.get(i)))
    return blueprint, missing
