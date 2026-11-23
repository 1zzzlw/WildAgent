"""把构造声明展开为既有 WILD 片段；所有产物仍经过 implementation 验收。"""

from copy import deepcopy
from math import hypot, isfinite

from app.domain.design.parametric import MAX_ITEMS
from app.domain.design.parametric import expand_parameters


def implementation_entities(geometry):
    if not isinstance(geometry, dict):
        raise ValueError("/geometry 必须是对象")
    if set(geometry) - {"elements", "components"}:
        raise ValueError(
            f"/geometry 未定义字段 {sorted(set(geometry)-{'elements', 'components'})}；实体写入 elements/components"
        )
    entities = []
    for bucket in ("elements", "components"):
        if not isinstance(geometry.get(bucket, []), list):
            raise ValueError(f"/geometry/{bucket} 必须是数组，没有构件时返回 []")
        for index, entity in enumerate(geometry.get(bucket, [])):
            path = f"/geometry/{bucket}/{index}"
            if not isinstance(entity, dict):
                raise ValueError(
                    f"{path}：实体须为对象，实际 {type(entity).__name__}；$repeat 每轮多实体请用 values:[...]，value 只返回单个实体"
                )
            if not isinstance(entity.get("id"), str) or not entity["id"]:
                raise ValueError(f"{path}/id：需要非空实体 ID")
            entities.append(entity)
    return entities


def _complete_native(row, marker, context):
    """单实体才有唯一的整体尺寸；不把整组尺寸强加给组合中的零件。"""
    geometry = row["geometry"]
    entities = []
    for current_key in ("elements", "components"):
        for current_entity in geometry.get(current_key, []):
            entities.append(current_entity)
    if len(entities) != 1:
        return []
    from app.domain.components.names import resolve_component_name

    entity = entities[0]
    kind = entity.get("type")
    family = resolve_component_name(marker["type"])["entity_type"]
    if kind != family and not (marker["type"] == kind == "primitive"):
        return []
    design, target = marker.get("design") or {}, marker.get("entity") or {}
    size, fields = design.get("size") or {}, {}
    if kind in {"door", "window"}:
        fields.update({key: size[key] for key in ("width", "height") if key in size})
        target = context.get("opening_hosts", {}).get(marker["id"]) or target
        width, height = entity.get("width", fields.get("width")), entity.get(
            "height", fields.get("height")
        )
        if (
            "from" not in target
            and marker.get("diagram_host")
            and all(
                type(v) in (int, float) and isfinite(v) and v > 0
                for v in (width, height)
            )
        ):
            from app.domain.design.relations import opening_target

            position = opening_target(marker, marker["diagram_host"], width, height)
            if position is not None:
                target = {**target, "from": position}
    elif kind in {"canopy", "balcony"}:
        from app.domain.design.relations import NATIVE_SIZE_FIELDS

        fields.update(
            {
                NATIVE_SIZE_FIELDS.get((kind, key), key): value
                for key, value in size.items()
                if key in {"width", "height", "depth"}
            }
        )
        target = context.get("canopy_mount_targets", {}).get(marker["id"]) or target
    elif kind == "furniture":
        from app.domain.design.relations import furniture_target

        fields.update(furniture_target(marker, entity))
    elif kind == "primitive" and entity.get("shape") == "box":
        # 设计 size 是世界外包框；旋转或缩放后的局部 dimensions 不能直接抄它。
        form = design.get("form") if isinstance(design.get("form"), dict) else {}
        if (
            entity.get("rotation", [0, 0, 0]) != [0, 0, 0]
            or entity.get("scale", [1, 1, 1]) != [1, 1, 1]
            or design.get("relation")
            or (design.get("placement") or {}).get("face")
            or any(form.get(k) for k in ("orientation", "rotation", "rotation_y"))
            or form.get("shape", "box") != "box"
        ):
            return []
        if all(key in size for key in ("width", "height", "depth")):
            fields["dimensions"] = [size[key] for key in ("width", "height", "depth")]
        if "position" in target:
            fields["position"] = target["position"]
    elif kind == "roof" and not size and isinstance(design.get("volume"), dict):
        roof_type = design.get("roof_type") or design.get("type")
        if (
            roof_type not in {"flat", "gable", "hip"}
            or entity.get("roofType", roof_type) != roof_type
        ):
            return []
        volume, overhang = design["volume"], design.get("overhang", 0)
        fields.update(
            roofType=roof_type,
            span=volume["width"] + 2 * overhang,
            depth=volume["depth"] + 2 * overhang,
        )
        if "position" in target:
            fields["position"] = target["position"]
        if "ridge_axis" in design:
            fields["ridgeAxis"] = design["ridge_axis"]
    if kind in {"door", "window", "canopy", "balcony"} and target.get("parentWall"):
        fields["parentWall"] = target["parentWall"]
        if (
            entity.get("parentWall", target["parentWall"]) == target["parentWall"]
            and "from" in target
        ):
            fields["from"] = target["from"]
    changes = []
    for key, value in fields.items():
        if (
            key == "dimensions"
            and isinstance(value, dict)
            and isinstance(entity.get(key), dict)
        ):
            for dimension, number in value.items():
                if dimension not in entity[key]:
                    entity[key][dimension] = number
                    changes.append(
                        {
                            "entity_id": entity.get("id"),
                            "field": f"dimensions/{dimension}",
                            "value": number,
                        }
                    )
        if key not in entity:
            entity[key] = deepcopy(value)
            changes.append(
                {"entity_id": entity.get("id"), "field": key, "value": deepcopy(value)}
            )
    return changes


def expand_implementation(row, marker, context):
    facts = {**context, "marker": marker}
    result, evidence = expand_parameters(row, facts=facts)
    for misplaced in ("entities", "elements", "components", "lightBody"):
        if misplaced in result:
            raise ValueError(
                f"/{misplaced} 不是实现项字段；实体放入 /geometry/elements 或 /geometry/components，灯体放在 light.body"
            )
    geometry = (
        result.setdefault("geometry", {})
        if result.get("walls") or result.get("slabs")
        else result.get("geometry")
    )
    format_changes = []
    if isinstance(geometry, dict):
        for bucket in ("elements", "components"):
            if geometry.get(bucket) == {}:
                geometry[bucket] = []
                format_changes.append(
                    {"path": f"/geometry/{bucket}", "before": {}, "after": []}
                )
    implementation_entities(geometry)
    from app.domain.components.capability import capability_surface

    capabilities = capability_surface()
    for bucket in ("elements", "components"):
        for entity in list(geometry.get(bucket, [])):
            target = (capabilities.get(entity.get("type")) or {}).get("target")
            if target in {"elements", "components"} and target != bucket:
                geometry[bucket].remove(entity)
                geometry.setdefault(target, []).append(entity)
                format_changes.append(
                    {"entity_id": entity["id"], "before": bucket, "after": target}
                )
    completed = _complete_native(result, marker, context)
    from app.domain.design.relations import place_roof_surface

    placement_changes = place_roof_surface(result, marker)
    if completed or format_changes or placement_changes:
        from app.domain.validation.diagnostics import blueprint_fingerprint

        evidence.update(
            construction_version="construction/2",
            completed_fields=completed,
            format_changes=format_changes,
            placement_changes=placement_changes,
            input_hash=blueprint_fingerprint(row),
            output_hash=blueprint_fingerprint(result),
        )
    walls, slabs = result.pop("walls", []), result.pop("slabs", [])
    if not isinstance(walls, list) or not isinstance(slabs, list):
        raise ValueError("/walls、/slabs 必须为数组")
    if not walls and not slabs:
        return result, evidence
    if marker["type"] != "building_body":
        raise ValueError(
            "walls/slabs 只用于主体的图纸宿主和楼面，其他构件使用 geometry"
        )
    elements = geometry.setdefault("elements", [])
    geometry.setdefault("components", [])
    hosts = {host["id"]: host for host in context["diagram_hosts"]}
    used = {e.get("id") for e in elements if isinstance(e, dict)}
    constructed = []

    def check(spec, fields, path):
        if not isinstance(spec, dict) or set(spec) != fields:
            raise ValueError(f"{path}：需要且仅接受 {sorted(fields)}")
        thickness = spec["thickness"]
        if (
            type(thickness) not in (int, float)
            or not isfinite(thickness)
            or thickness <= 0
        ):
            raise ValueError(f"{path}/thickness：必须为有限正数")
        if not isinstance(spec["material"], str) or not spec["material"]:
            raise ValueError(f"{path}/material：必须引用明确材质")

    def append(entity, path):
        if (
            not isinstance(entity["id"], str)
            or not entity["id"]
            or entity["id"] in used
        ):
            raise ValueError(f"{path}：构造实体 ID 缺失或重复 {entity['id']}")
        if len(elements) >= MAX_ITEMS:
            raise ValueError(f"{path}：构造展开超过 {MAX_ITEMS} 个实体")
        used.add(entity["id"])
        elements.append(entity)
        constructed.append({"path": path, "entity_id": entity["id"]})

    for index, spec in enumerate(walls):
        path = f"/walls/{index}"
        check(spec, {"host", "thickness", "material"}, path)
        host = hosts.get(spec["host"])
        if not host or host.get("type") != "wall" or host.get("open"):
            raise ValueError(f"{path}/host：不是当前图纸的封闭墙宿主 {spec['host']}")
        if "thickness" in host and abs(host["thickness"] - spec["thickness"]) > 1e-6:
            raise ValueError(f"{path}/thickness：必须保留图纸墙厚 {host['thickness']}")
        a, b = host["from"], host["to"]
        # 显式构造不能被简写入口悄悄改成默认直墙。
        for component in marker["design"].get("body_components", []):
            if (
                component.get("id") == spec["host"]
                or component.get("host") == spec["host"]
            ):
                size = component.get("size") or {}
                actual = {
                    "width": hypot(b[0] - a[0], b[2] - a[2]),
                    "height": b[1] - a[1],
                    "depth": spec["thickness"],
                }
                if any(
                    abs(size[key] - actual[key]) > 0.001
                    for key in actual
                    if key in size
                ):
                    raise ValueError(
                        f"{path}：墙尺寸与显式构件 {component['id']} 不一致"
                    )
                form = component.get("form") or {}
                if any(key in form for key in ("curve", "rotation", "rotation_y")):
                    raise ValueError(
                        f"{path}：显式曲线/旋转墙请在 geometry 中按图纸实现"
                    )
        append(
            {
                "id": spec["host"],
                "type": "wall",
                "from": deepcopy(a),
                "to": deepcopy(b),
                "thickness": spec["thickness"],
                "material": spec["material"],
            },
            path,
        )

    from app.domain.geometry.geometry import subtract_rectangles

    levels = {level["index"]: level for level in context["levels"]}
    placed = []
    for index, spec in enumerate(slabs):
        path = f"/slabs/{index}"
        check(spec, {"id", "volume", "floor", "thickness", "material"}, path)
        level = levels.get(spec["floor"])
        if (
            type(spec["floor"]) is not int
            or not level
            or spec["volume"] not in level["volume_ids"]
        ):
            raise ValueError(f"{path}：体量在指定楼层不存在")
        bounds = context["volume_geometry"][spec["volume"]]["bounds"]
        cuts = [void["bounds"] for void in level["voids"]]
        for other_y, other_bounds, other_spec in placed:
            if abs(other_y - level["base_y"]) > 0.001:
                continue
            overlap = max(bounds[0], other_bounds[0]) < min(
                bounds[2], other_bounds[2]
            ) and max(bounds[1], other_bounds[1]) < min(bounds[3], other_bounds[3])
            if overlap and any(
                spec[key] != other_spec[key] for key in ("thickness", "material")
            ):
                raise ValueError(f"{path}：重叠楼面材料或厚度不同，须明确修订范围")
            if spec["volume"] == other_spec["volume"]:
                raise ValueError(f"{path}：同一体量楼层重复声明楼板")
            cuts.append(other_bounds)
        rectangles = subtract_rectangles(bounds, cuts)
        y = level["base_y"] - spec["thickness"]
        for part, (x0, z0, x1, z1) in enumerate(rectangles):
            append(
                {
                    "id": spec["id"] if part == 0 else f"{spec['id']}_part_{part}",
                    "type": "floor",
                    "from": [x0, y, z0],
                    "to": [x1, y, z1],
                    "thickness": spec["thickness"],
                    "material": spec["material"],
                },
                path,
            )
        placed.append((level["base_y"], bounds, spec))
    from app.domain.validation.diagnostics import blueprint_fingerprint

    evidence.update(
        construction_version="construction/2",
        constructed=constructed,
        input_hash=blueprint_fingerprint(row),
        output_hash=blueprint_fingerprint(result),
    )
    return result, evidence
