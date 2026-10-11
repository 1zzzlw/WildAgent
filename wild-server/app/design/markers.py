"""设计标记与落实记录；一个标记允许由多个 WILD 元素共同表达。"""
from copy import deepcopy

IMPLEMENTATION_STAGES = ("generate", "repair_1", "repair_2")


def body_floor_errors(entities, design):
    """主体矩形楼板不能把多体量的空缺填成整栋包围盒；只检查，不裁剪。"""
    from .contracts import MassingDecision
    from .coordinates import representative_floor_indices, rectangle_uncovered_area
    volumes = design.get("volumes") or []
    if not volumes or not design.get("massing"):
        return []
    massing = MassingDecision.model_validate(design["massing"])
    indices = representative_floor_indices(massing)
    margin = max((e.get("thickness", 0) / 2 for e in entities if e.get("type") == "wall"), default=0)
    errors = []
    for floor in entities:
        if floor.get("type") != "floor" or floor.get("shape", "rect") != "rect":
            continue
        a, b = floor["from"], floor["to"]
        top = a[1] + floor["thickness"]
        regions = [(v["x"]-margin, v["z"]-margin, v["x"]+v["width"]+margin, v["z"]+v["depth"]+margin)
                   for v in volumes if (indices[v["start_floor"]-1]-1)*massing.floor_height-0.25 <= top
                   <= indices[v["end_floor"]-1]*massing.floor_height+0.25]
        x0, x1 = sorted((a[0], b[0]))
        z0, z1 = sorted((a[2], b[2]))
        outside = rectangle_uncovered_area((x0, z0, x1, z1), regions)
        if outside > 0.001:
            errors.append(f"❌ [{floor['id']}] 主体楼板超出该标高体量并集 {outside:.3f}㎡；按体量分片保留庭院空缺，不能填满包围盒")
    return errors


def _explicit_opening_locations(d, explicit, indices):
    from app.agent.knowledge.component_names import resolve_component_name
    locations, covered = {}, {}
    for item in explicit:
        if resolve_component_name(item["type"])["entity_type"] not in {"door", "window"}:
            continue
        placement = item.get("placement") or {}
        position = placement.get("position")
        for volume in d.volumes:
            for face, facade in {**d.facades, **volume.facades}.items():
                # 墙方向与 project_drawing 的 from/to 一致。
                origin, axis, direction, length = {
                    "front": ([volume.x, 0, volume.z], 0, 1, volume.width),
                    "back": ([volume.x+volume.width, 0, volume.z+volume.depth], 0, -1, volume.width),
                    "right": ([volume.x+volume.width, 0, volume.z], 2, 1, volume.depth),
                    "left": ([volume.x, 0, volume.z+volume.depth], 2, -1, volume.depth),
                }[face]
                distance = abs(position[2-axis]-origin[2-axis]) if position else 0
                along = (position[axis]-origin[axis])*direction if position else 0
                for floor in range(volume.start_floor, volume.end_floor+1):
                    host = f"wall_{volume.id}_{face}_L{floor}"
                    direct = item["host"] == host
                    local = (item["host"] == volume.id and placement.get("face") == face
                             and placement.get("floor") == floor)
                    on_volume = (item["host"] == volume.id and position and distance <= 0.3
                        and 0 <= along <= length
                        and (indices[floor-1]-1)*d.massing.floor_height <= position[1] < indices[floor-1]*d.massing.floor_height)
                    if not direct and not on_volume and not local:
                        continue
                    locations[item["id"]] = host
                    bay = placement.get("bay", item.get("bay"))
                    width = (item.get("size") or {}).get("width")
                    if bay:
                        occupied = {bay}
                    elif position and width:
                        occupied = {b for b in range(1, facade.bays+1)
                                    if (b-1)*length/facade.bays < along+width/2-0.001
                                    and b*length/facade.bays > along-width/2+0.001}
                    elif width and "offset" in placement:
                        left = placement["offset"]
                        occupied = {b for b in range(1, facade.bays+1)
                                    if (b-1)*length/facade.bays < left+width-0.001
                                    and b*length/facade.bays > left+0.001}
                    else:
                        occupied = set()
                    covered.setdefault(host, set()).update(occupied)
    return locations, covered


def component_markers(document):
    from .coordinates import representative_floor_indices, exterior_facade_intervals
    from app.agent.knowledge.component_names import resolve_component_name
    d = document.decisions
    indices = representative_floor_indices(d.massing)
    explicit = [i.model_dump(mode="json", exclude_none=True) for i in d.components]
    body_components = [i for i in explicit if resolve_component_name(i["type"])["kind"] == "building_body"]
    body_ids = {i["id"] for i in body_components}
    locations, covered = _explicit_opening_locations(d, explicit, indices)
    delegated = [i for i in explicit if resolve_component_name(i["type"])["entity_type"] in {"stair", "floor", "column", "beam"}]
    rows = [{"id": "building_body", "type": "building_body", "host": "", "depends_on": [],
             "design": {k: v for k, v in d.model_dump(mode="json").items()
                        if k not in {"components", "roof", "component_quota", "required_components"}},
             "entity": {}}]
    rows[0]["design"]["delegated_components"] = delegated
    rows[0]["design"]["body_components"] = body_components
    explicit_openings = {}
    wall_floors = {}
    for item in explicit:
        family = resolve_component_name(item["type"])["entity_type"]
        placement = item.get("placement") or {}
        has_extent = (item.get("size") or {}).get("width") and "offset" in placement
        if family in {"door", "window"} and not placement.get("position") and not has_extent:
            explicit_openings.setdefault((family, locations.get(item["id"], item["host"])), []).append(item)
    for v in d.volumes:
        for face, facade in {**d.facades, **v.facades}.items():
            for floor in range(v.start_floor, v.end_floor+1):
                host = f"wall_{v.id}_{face}_L{floor}"
                wall_floors[host] = floor
                pattern = facade.ground_pattern if floor == 1 else facade.upper_pattern
                for bay, token in enumerate(pattern, 1):
                    kind, _, form = token.partition(":")
                    if kind in {"empty", "open", "none", "no_opening", "无开口", "留白"}:
                        continue
                    name = resolve_component_name(kind)
                    family = name["entity_type"]
                    if family == "wall":
                        continue
                    length = v.width if face in {"front", "back"} else v.depth
                    center = (bay-0.5)*length/facade.bays
                    exposed = exterior_facade_intervals(v, face, floor, d.volumes)
                    if not any(left <= center <= right for left, right in exposed):
                        continue
                    if family in {"door", "window"} and bay in covered.get(host, set()):
                        continue
                    candidates = explicit_openings.get((family, host), [])
                    matching = next((i for i in candidates if (i.get("placement") or {}).get("bay", i.get("bay")) == bay), None)
                    matching = matching or next((i for i in candidates if not (i.get("placement") or {}).get("bay", i.get("bay"))), None)
                    if matching:
                        candidates.remove(matching)
                        continue
                    rows.append({"id": f"{kind}_{v.id}_{face}_L{floor}_{bay}", "type": name["kind"],
                                 "host": host, "depends_on": ["building_body"], "design_path": f"/decisions/facades/{face}",
                                 "design": {"type": kind, "host": host, "floor": floor, "bay": bay,
                                            "bays": facade.bays, "semantic_floor": indices[floor-1], "form": form, "facade": facade.model_dump(mode="json")},
                                 "entity": {"parentWall": host,
                                     "centerAlong": center,
                                     "bottomY": (indices[floor-1]-1)*d.massing.floor_height + (1 if family == "window" else 0)}})
        if not any(resolve_component_name(i["type"])["entity_type"] == "roof" and i["host"] == v.id for i in explicit):
            roof = d.roof.model_dump(mode="json")
            override = next((i.model_dump(mode="json", exclude_none=True) for i in d.roof.volumes if i.volume == v.id), {})
            if override.get("type", roof["type"]) in {"none", "open"}:
                continue
            rows.append({"id": f"roof_{v.id}", "type": "roof", "host": v.id,
                         "depends_on": ["building_body"], "design_path": "/decisions/roof", "design": {**roof, **override, "volume": v.model_dump(mode="json")},
                         "entity": {"position": [v.x+v.width/2, indices[v.end_floor-1]*d.massing.floor_height, v.z+v.depth/2]}})
    explicit_ids = {i["id"] for i in explicit}
    for index, item in enumerate(explicit):
        if item["id"] in body_ids:
            continue
        dependencies = {"building_body"}
        if item["host"] in explicit_ids:
            dependencies.add(item["host"])
        target = (item.get("relation") or {}).get("target")
        if target in explicit_ids:
            dependencies.add(target)
        placement = item.get("placement") or {}
        position = placement.get("position")
        host = locations.get(item["id"], item["host"])
        elevation = (indices[wall_floors.get(host, 1)-1]-1)*d.massing.floor_height
        local = [placement.get("offset", 0), elevation + placement.get("sill_height", 0), placement.get("normal_offset", 0)]
        entity = {"parentWall": host, **({"position": position} if position else {"from": local})}
        design = item
        volume = next((v for v in d.volumes if v.id == host), None)
        if resolve_component_name(item["type"])["entity_type"] == "roof" and volume:
            roof = d.roof.model_dump(mode="json")
            override = next((r.model_dump(mode="json", exclude_none=True) for r in d.roof.volumes if r.volume == host), {})
            roof_type = item.get("roof_type") or (item["type"] if item["type"] != "roof" else override.get("type", roof["type"]))
            design = {**roof, **override, **item, "roof_type": roof_type, "volume": volume.model_dump(mode="json")}
            entity = {"position": position or [volume.x+volume.width/2,
                      indices[volume.end_floor-1]*d.massing.floor_height, volume.z+volume.depth/2]}
        rows.append({"id": item["id"], "type": item["type"], "host": host,
                     "depends_on": sorted(dependencies-body_ids), "design_path": f"/decisions/components/{index}", "design": design,
                     "entity": entity})
    rows[0]["design"]["opening_layout"] = [
        {"id": m["id"], "type": m["type"], "host": m["host"], "entity": m["entity"],
         "size": m["design"].get("size", {})}
        for m in rows[1:] if resolve_component_name(m["type"])["entity_type"] in {"door", "window"}]
    ids = [m["id"] for m in rows]
    for marker in rows:
        dependencies = set(marker["depends_on"])
        target = (marker["design"].get("relation") or {}).get("target")
        for reference in (marker["host"], target):
            if reference in ids and reference != marker["id"]:
                dependencies.add(reference)
        marker["depends_on"] = sorted(dependencies)
    if len(set(ids)) != len(ids):
        raise ValueError("设计标记 ID 重复；building_body 与自动立面标记 ID 为保留名称")
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
    return {key: value for diag in (state.get("component_diagnostics") or {}).values()
            for key, value in (diag.get("implementations") or {}).items()}


def implementation_complete(record):
    return bool(record and record.get("status") in {"implemented", "abandoned"})


def assemble_marker_results(document, state):
    from .resolver import _stable_hash
    from .compilation import RESOLVER_VERSION
    reviewed = state.get("resolved_design") or {}
    if reviewed.get("design_hash") != _stable_hash(document) or reviewed.get("resolver_version") != RESOLVER_VERSION:
        raise ValueError("落实记录与审核图纸版本不一致")
    blueprint = deepcopy(state["skeleton_blueprint"])
    entities = marker_results(state)
    records = implementation_records(state)
    expected = {m["id"] for m in component_markers(document)}
    if set(records) - expected:
        raise ValueError("落实记录含有未设计标记")
    owned = {entity_id for r in records.values() if r.get("status") == "implemented" for entity_id in r["entity_ids"]}
    if owned != set(entities):
        raise ValueError("落实记录与实际构件集合不一致")
    for diag in (state.get("component_diagnostics") or {}).values():
        for bucket in ("elements", "components"):
            blueprint["geometry"][bucket].extend(deepcopy(entities[i]) for i in diag.get(bucket, []) if i in entities)
        blueprint["materials"].update(diag.get("materials") or {})
        blueprint["assets"].update(diag.get("assets") or {})
    missing = sorted(i for i in expected if not implementation_complete(records.get(i)))
    return blueprint, missing
