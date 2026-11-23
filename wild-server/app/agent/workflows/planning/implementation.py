"""按图纸编写 WILD，检索与校验失败只影响当前标记。"""

from copy import deepcopy
import json
import re
from xml.etree import ElementTree

from app.agent.prompts.implementation import build_marker_implementation_prompt
from app.agent.prompts.implementation import build_marker_output_protocol
from app.domain.design.markers import BUILDING_BODY_ENTITY_TYPES
from app.domain.design.markers import IMPLEMENTATION_STAGES
from app.domain.design.markers import ImplementationValidationError
from app.domain.design.markers import implementation_records
from app.domain.design.markers import marker_results
from app.domain.design.markers import merge_marker_resources
from app.domain.design.relations import NATIVE_SIZE_FIELDS as _SIZE_FIELDS
from app.agent.workflows.planning.construction import expand_implementation
from app.agent.workflows.planning.construction import implementation_entities
from app.domain.design.construction_systems import VERSION as SYSTEM_VERSION
from app.domain.design.construction_systems import construction_spec
from app.domain.design.construction_systems import construct_system
from app.domain.validation.issues import validation_issues_from_results
from app.domain.validation.issues import wild_schema_issues
from app.domain.validation.issues import issue_fingerprints
from app.domain.validation.issues import repair_feedback


def implementation_blueprint(state):
    blueprint = deepcopy(state["skeleton_blueprint"])
    for diag in (state.get("component_diagnostics") or {}).values():
        merge_marker_resources(blueprint, diag)
        for bucket in ("elements", "components"):
            ids = set(diag.get(bucket) or [])
            blueprint["geometry"][bucket].extend(
                deepcopy(e) for e in marker_results(state).values() if e["id"] in ids
            )
    return blueprint


def _material_definition(value):
    return {"opacity": 1, **value} if isinstance(value, dict) else value


def _bind_materials(base, row, marker, material_roles=None):
    """相同定义复用；局部同名材质按内容分配 ID，并发合并不互相改色。"""
    from hashlib import sha256

    row = deepcopy(row)
    definitions = row.get("materials", {})
    if not isinstance(definitions, dict):
        raise ValueError("materials 必须是对象")
    existing, bindings, adopted = base["materials"], {}, {}
    for name, value in definitions.items():
        definition = _material_definition(value)
        if name in existing and definition == _material_definition(existing[name]):
            adopted[name] = deepcopy(existing[name])
            continue
        payload = json.dumps(
            definition, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
        suffix = "__" + sha256(payload.encode()).hexdigest()[:12]
        if marker["type"] == "building_body" and name not in existing:
            target = name
        elif name.endswith(suffix):
            target = name
        else:
            target = name + suffix
        bindings[name] = target
        adopted[target] = value

    # 已批准角色到实际材质 ID 的唯一映射，不让模型重新猜 ID；显式定义/现有 ID 优先。
    for role, target in (material_roles or {}).items():
        if role not in definitions and role not in existing and target in existing:
            bindings[role] = target
    used_bindings = {}

    def bind(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if (key == "material" or key.endswith("Material")) and isinstance(
                    child, str
                ):
                    value[key] = bindings.get(child, child)
                    if value[key] != child:
                        used_bindings[child] = value[key]
                else:
                    bind(child)
        elif isinstance(value, list):
            for child in value:
                bind(child)

    bind(row.get("geometry"))
    row["materials"] = adopted
    return row, used_bindings


def web_reference_query(item, markers):
    from app.domain.components.names import resolve_component_name

    name = resolve_component_name(item.kind)
    label = name["label"].replace("_", " ")
    family = (
        resolve_component_name(name["entity_type"])["label"]
        if name["entity_type"]
        else ""
    )
    descriptions = list(
        dict.fromkeys(
            str(m["design"].get("description") or "").strip() for m in markers.values()
        )
    )
    terms = list(dict.fromkeys(t for t in [label, family, *descriptions] if t))
    return (
        '"'
        + label.replace('"', "")
        + '" '
        + " ".join(terms[1:])[:180]
        + " 建筑 构造 详图 installation detail drawing"
    )


def relevant_web_reference(hit, query):
    quoted = re.match(r'^"([^"]+)"', query.strip())
    subject = (quoted.group(1) if quoted else query.strip().split(" ", 1)[0]).casefold()
    text = " ".join(hit.get(key, "") for key in ("title", "description")).casefold()

    def contains(term):
        return (
            term in text
            if re.search(r"[\u4e00-\u9fff]", term)
            else bool(re.search(r"\b" + re.escape(term) + r"\b", text))
        )

    terms = set(re.findall(r"[\u4e00-\u9fff]+|[a-z]{3,}", query.casefold()))
    return bool(
        subject
        and contains(subject)
        and any(contains(t) for t in terms if t not in subject)
    )


async def search_web_impl(query):
    """搜索构件形态说明，保留来源 URL；结果仅作为参考资料。"""
    import httpx

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(
            "https://www.bing.com/search", params={"q": query, "format": "rss"}
        )
        response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    hits = [
        {
            "title": i.findtext("title", ""),
            "url": i.findtext("link", ""),
            "description": i.findtext("description", ""),
        }
        for i in root.findall("./channel/item")
    ]
    return [hit for hit in hits if relevant_web_reference(hit, query)][:4]


def implementation_issues(blueprint):
    from app.domain.components.capability import load_engine_schema
    from app.domain.blueprint.parser import validate_blueprint_schema
    from app.agent.tools.spatial import validate_element_dimensions
    from app.agent.tools.spatial import validate_element_required_fields
    from app.agent.tools.spatial import validate_reference_integrity
    from app.agent.tools.spatial import validate_opening_coords
    from app.agent.tools.spatial import validate_opening_fit
    from app.agent.tools.spatial import validate_model_quality
    from app.domain.validation.components import validate_balcony_placement
    from app.domain.validation.components import validate_canopy_placement

    schema = load_engine_schema()
    results = []

    def add(name, messages, *, issues=None):
        if messages:
            results.append(
                {
                    "name": name,
                    "has_error": True,
                    "output": "\n".join(messages),
                    "issues": issues,
                }
            )

    add("validate_blueprint_schema", validate_blueprint_schema(blueprint))
    try:
        json.dumps(blueprint, allow_nan=False)
    except (ValueError, TypeError) as exc:
        add("validate_wild_json", [f"WILD 必须是标准 JSON：{exc}"])
    schema_issues = wild_schema_issues(blueprint, schema)
    add(
        "validate_wild_schema",
        [issue["message"] for issue in schema_issues],
        issues=schema_issues,
    )
    for validator in (
        validate_element_dimensions,
        validate_element_required_fields,
        validate_reference_integrity,
        validate_opening_coords,
        validate_opening_fit,
        validate_model_quality,
        validate_balcony_placement,
        validate_canopy_placement,
    ):
        function = getattr(validator, "func", validator)
        output = function(deepcopy(blueprint))
        add(
            function.__name__,
            [line for line in str(output).splitlines() if "❌" in line],
        )
    return validation_issues_from_results(results, blueprint)


def _accept_group(base, row, marker, *, check_size=True):
    from app.domain.validation.diagnostics import blueprint_fingerprint

    geometry = row.get("geometry")
    entities = implementation_entities(geometry)
    if not entities:
        message = "没有生成有效实体；请尝试原生构件或 primitive 组合"
        if marker["type"] == "building_body" and not entities:
            message += (
                "；开敞仅表示不建墙，未另派 floor 任务的楼面仍由主体实现。"
                "台基任务不等于 floor 任务；按 floor_layouts.level/levels.base_y 写实际 floor，"
                "from/to 的 Y 为楼面顶减板厚，X/Z 按体量起点与宽深。不能返回空逻辑容器"
            )
        raise ValueError(message)
    if (
        marker["type"] == "building_body"
        and any(
            layout.get("rooms")
            for layout in marker["design"].get("floor_layouts") or []
        )
        and any(e.get("type") == "column" for e in entities)
    ):
        raise ValueError(
            "建筑主体返回了图纸未标注的独立柱；柱位应先在 architecture.components 标注，交由对应 plan 实现"
        )
    ids = [e["id"] for e in entities]
    existing = set()
    for geometry_bucket in ("elements", "components"):
        for entity in base["geometry"][geometry_bucket]:
            existing.add(entity["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("当前片段的实体 ID 重复；每个实体只返回一次")
    if existing.intersection(ids):
        raise ValueError(
            "不能覆盖已采用实体："
            + ", ".join(sorted(existing.intersection(ids))[:8])
            + "；保留原实体，只修订失败片段，不能改名后重复新建"
        )
    candidate = deepcopy(base)
    for key in ("materials", "assets"):
        added = row.get(key, {})
        if not isinstance(added, dict):
            raise ValueError(f"{key} 必须是对象")
        for name, value in added.items():
            prior = candidate[key].get(name)
            equal = (
                (_material_definition(prior) == _material_definition(value))
                if key == "materials"
                else prior == value
            )
            if name in candidate[key] and not equal:
                raise ValueError(
                    f"/{key}/{name} 不能覆盖已经采用的定义；使用独立 ID 并更新当前片段引用"
                )
            candidate[key].setdefault(name, value)
    for bucket in ("elements", "components"):
        candidate["geometry"][bucket].extend(geometry.get(bucket, []))
    baseline = issue_fingerprints(implementation_issues(base))
    issues = [
        issue
        for issue in implementation_issues(candidate)
        if not issue_fingerprints([issue]) <= baseline
    ]
    errors = [issue["message"] for issue in issues]

    def add_errors(name, messages):
        if messages:
            errors.extend(messages)
            issues.extend(
                validation_issues_from_results(
                    [{"name": name, "has_error": True, "output": "\n".join(messages)}],
                    candidate,
                )
            )

    if marker["type"] == "building_body" and not errors:
        from app.domain.design.markers import body_floor_errors

        walls = [e for e in base["geometry"]["elements"] if e.get("type") == "wall"]
        add_errors(
            "design_body_footprint",
            body_floor_errors([*entities, *walls], marker["design"]),
        )
    stair_ids = {e["id"] for e in entities if e.get("type") == "stair"}
    if stair_ids and not errors:
        from app.domain.geometry.stair_openings import cut_stair_openings
        from app.domain.validation.spatial import collect_stair_placement_issues

        preview = deepcopy(candidate)
        cut_stair_openings(preview)
        add_errors(
            "validate_stair_alignment",
            [
                str(issue["message"])
                for issue in collect_stair_placement_issues(preview)
                if stair_ids.intersection(issue["entity_ids"])
            ],
        )
        route = _stair_route_target(base, marker)
        if route and len(stair_ids) == 2:
            first, second = sorted(
                (e for e in entities if e.get("type") == "stair"),
                key=lambda e: e["from"][1],
            )
            axis = route["direction_axis"]
            if (first["to"][axis] - first["from"][axis]) * route["direction_sign"] <= 0:
                add_errors(
                    "design_stair_connection",
                    [
                        f"楼梯 {first['id']} 第一跑方向与图纸相反；应沿 "
                        f"{'+' if route['direction_sign'] > 0 else '-'}{'X' if axis == 0 else 'Z'} 上行，"
                        f"参考 stair_route_targets.{marker['id']} 的梯段与平台坐标"
                    ],
                )
            if (second["to"][axis] - second["from"][axis]) * route[
                "direction_sign"
            ] >= 0:
                add_errors(
                    "design_stair_connection",
                    [
                        f"楼梯 {second['id']} 第二跑没有按图纸折返；参考 "
                        f"stair_route_targets.{marker['id']} 的梯段与平台坐标"
                    ],
                )
    if check_size and not errors:
        from app.domain.design.relations import opening_design_errors
        from app.domain.design.relations import roof_design_errors
        from app.domain.design.relations import railing_design_errors
        from app.domain.design.relations import stair_design_errors
        from app.domain.design.relations import component_geometry_review
        from app.domain.design.relations import canopy_design_errors

        add_errors(
            "design_opening_placement",
            opening_design_errors(candidate, entities, marker),
        )
        add_errors(
            "design_roof_surface", roof_design_errors(candidate, entities, marker)
        )
        add_errors(
            "design_railing_placement",
            railing_design_errors(candidate, entities, marker),
        )
        add_errors(
            "design_stair_connection", stair_design_errors(candidate, entities, marker)
        )
        add_errors(
            "design_canopy_placement", canopy_design_errors(candidate, entities, marker)
        )
        review = component_geometry_review(candidate, entities, marker)
        add_errors("design_component_geometry", review["errors"])
    else:
        review = {
            "status": "needs_review",
            "checked": [],
            "unverified": ["当前为片段验收"],
            "errors": [],
        }
    if errors:
        raise ImplementationValidationError(issues)
    record = {
        "status": "implemented",
        "entity_ids": [e["id"] for e in entities],
        "entity_fingerprint": blueprint_fingerprint(entities),
        "explanation": str(row.get("explanation") or ""),
        "verification": (
            "needs_review"
            if review["status"] == "needs_review"
            else "geometry_validated"
        ),
        "geometry_review": review,
    }
    return candidate, entities, record


def _accept_fragment(
    base,
    row,
    marker,
    retained_geometry=None,
    *,
    dependent_markers=(),
    diagram_hosts=None,
):
    from app.domain.validation.diagnostics import blueprint_fingerprint

    row = deepcopy(row)
    geometry = row.get("geometry")
    repeated = []
    if (
        isinstance(geometry, dict)
        and not set(geometry) - {"elements", "components"}
        and all(
            isinstance(geometry.get(k, []), list) for k in ("elements", "components")
        )
    ):
        for bucket in ("elements", "components"):
            retained = {e["id"]: e for e in (retained_geometry or {}).get(bucket, [])}
            fresh = []
            for entity in geometry.get(bucket, []):
                if (
                    isinstance(entity, dict)
                    and entity.get("id") in retained
                    and blueprint_fingerprint(entity)
                    == blueprint_fingerprint(retained[entity["id"]])
                ):
                    repeated.append(entity["id"])
                else:
                    fresh.append(entity)
            row["geometry"][bucket] = fresh
    row["repeated_entity_ids"] = repeated
    if len(repeated) != len(set(repeated)):
        return (
            base,
            None,
            {"row": row, "error": "当前片段的实体 ID 重复；每个实体只返回一次"},
            None,
        )
    recheck_retained = bool(
        repeated and not any(row["geometry"].get(k) for k in ("elements", "components"))
    )
    validation_base = base
    if recheck_retained:
        retained_ids = set()
        for geometry_bucket in ("elements", "components"):
            for current_entity in retained_geometry.get(geometry_bucket, []):
                retained_ids.add(current_entity["id"])
        if set(repeated) != retained_ids:
            return (
                base,
                None,
                {"row": row, "error": "本轮仅重复部分已通过实体，尚未提供完整修订结果"},
                None,
            )
    validation_row = deepcopy(row)
    valid_geometry = (
        isinstance(geometry, dict)
        and not set(geometry) - {"elements", "components"}
        and all(
            isinstance(geometry.get(k, []), list) for k in ("elements", "components")
        )
    )
    if retained_geometry and valid_geometry:
        retained_ids = set()
        for geometry_bucket in ("elements", "components"):
            for current_entity in retained_geometry.get(geometry_bucket, []):
                retained_ids.add(current_entity["id"])
        for bucket in ("elements", "components"):
            for entity in row["geometry"].get(bucket, []):
                if isinstance(entity, dict) and entity.get("id") in retained_ids:
                    return (
                        base,
                        None,
                        {"row": row, "error": "不能覆盖已采用实体；只修订失败片段"},
                        None,
                    )
        validation_base = deepcopy(base)
        for bucket in ("elements", "components"):
            validation_base["geometry"][bucket] = [
                e for e in base["geometry"][bucket] if e["id"] not in retained_ids
            ]
            validation_row["geometry"][bucket] = deepcopy(
                retained_geometry.get(bucket, [])
            ) + row["geometry"].get(bucket, [])
    from app.domain.design.relations import delegated_geometry_errors

    if valid_geometry:
        submitted_entities = []
        for bucket in ("elements", "components"):
            for entity in validation_row["geometry"].get(bucket, []):
                if isinstance(entity, dict):
                    submitted_entities.append(entity)
        ownership_errors = delegated_geometry_errors(
            submitted_entities, marker, dependent_markers
        )
        if ownership_errors:
            return base, None, {"row": row, "error": "；".join(ownership_errors)}, None
    from app.domain.components.names import resolve_component_name

    family = resolve_component_name(marker["type"])["entity_type"]
    if (
        (marker["type"] == "building_body" or family == "wall")
        and isinstance(geometry, dict)
        and all(
            isinstance(geometry.get(k, []), list) for k in ("elements", "components")
        )
    ):
        from app.domain.design.relations import body_host_errors

        preview = deepcopy(validation_base)
        preview["geometry"]["elements"].extend(
            e
            for e in validation_row["geometry"].get("elements", [])
            if isinstance(e, dict)
        )
        if marker["type"] == "building_body":
            delegated_walls = {
                m["id"]
                for m in dependent_markers
                if m["id"] != marker["id"]
                and resolve_component_name(m["type"])["entity_type"] == "wall"
            }
            handoff_markers = [
                m
                for m in dependent_markers
                if (m.get("entity") or {}).get("parentWall") not in delegated_walls
            ]
        else:
            handoff_markers = [
                m
                for m in dependent_markers
                if (m.get("entity") or {}).get("parentWall") == marker["id"]
            ]
        errors = body_host_errors(preview, handoff_markers, diagram_hosts=diagram_hosts)
        if errors:
            if marker["type"] == "building_body":
                from app.domain.design.markers import body_floor_errors

                errors = (
                    body_floor_errors(preview["geometry"]["elements"], marker["design"])
                    + errors
                )
            try:
                _accept_group(validation_base, validation_row, marker)
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(str(exc))
            issues = validation_issues_from_results(
                [
                    {
                        "name": "design_host_geometry",
                        "has_error": True,
                        "output": "\n".join(errors),
                    }
                ],
                preview,
            )
            return (
                base,
                None,
                {"row": row, "error": "；".join(errors[:12]), "issues": issues},
                None,
            )
    try:
        candidate, entities, record = _accept_group(
            validation_base, validation_row, marker
        )
        if recheck_retained:
            row["geometry"] = {"elements": [], "components": []}
        return candidate, row, None, record
    except (ValueError, TypeError, KeyError) as exc:
        error = str(exc)
        issues = getattr(exc, "issues", [])
    if recheck_retained:
        return base, None, {"row": row, "error": error, "issues": issues}, None
    if construction_spec(marker.get("design") or {}) is not None:
        return base, None, {"row": row, "error": error, "issues": issues}, None
    family = resolve_component_name(marker["type"])["entity_type"]
    if (
        family in {"roof", "stair", "canopy"}
        or (family == "railing" and marker.get("host"))
        or (marker.get("entity", {}).get("parentWall") and family in {"door", "window"})
    ):
        return base, None, {"row": row, "error": error, "issues": issues}, None
    geometry = row.get("geometry")
    if (
        not isinstance(geometry, dict)
        or set(geometry) - {"elements", "components"}
        or any(
            not isinstance(geometry.get(k, []), list)
            for k in ("elements", "components")
        )
    ):
        return base, None, {"row": row, "error": error, "issues": issues}, None
    from app.domain.design.relations import component_geometry_review

    preview = deepcopy(base)
    group = []
    for geometry_bucket in ("elements", "components"):
        for current_entity in validation_row["geometry"].get(geometry_bucket, []):
            group.append(current_entity)
    if not isinstance(row.get("materials", {}), dict) or any(
        not isinstance(e, dict) for e in group
    ):
        return base, None, {"row": row, "error": error, "issues": issues}, None
    preview["materials"].update(row.get("materials") or {})
    if component_geometry_review(preview, group, marker)["errors"]:
        return base, None, {"row": row, "error": error, "issues": issues}, None
    remaining = []
    for geometry_bucket in ("elements", "components"):
        for current_entity in geometry.get(geometry_bucket, []):
            remaining.append((geometry_bucket, current_entity))
    accepted = {**row, "geometry": {"elements": [], "components": []}}
    single = len(group) == 1
    record = None
    while remaining:
        failed = []
        errors = []
        part_issues = []
        for bucket, entity in remaining:
            part = {
                **row,
                "geometry": {"elements": [], "components": [], bucket: [entity]},
            }
            try:
                base, _, record = _accept_group(base, part, marker, check_size=single)
                accepted["geometry"][bucket].append(entity)
            except (ValueError, TypeError, KeyError) as exc:
                failed.append((bucket, entity))
                errors.append(str(exc))
                part_issues.extend(getattr(exc, "issues", []))
        if errors:
            error = "；".join(dict.fromkeys(errors))
            issues = part_issues or issues
        if len(failed) == len(remaining):
            break
        remaining = failed
    if remaining or not record:
        rejected_geometry = {"elements": [], "components": []}
        for bucket, entity in remaining:
            if bucket in rejected_geometry:
                rejected_geometry[bucket].append(entity)
        rejected = {**row, "geometry": rejected_geometry}
        return (
            base,
            accepted if any(accepted["geometry"].values()) else None,
            {"row": rejected, "error": error, "issues": issues},
            None,
        )
    return base, accepted, None, record


def _stair_route_target(base, marker):
    """由明确的折返方向、占地与楼面计算路线；缺省踏步参数不阻断定位。"""
    from math import isfinite

    design = marker.get("design") or {}
    form, size = design.get("form") or {}, design.get("size") or {}
    if (
        not isinstance(form, dict)
        or form.get("flights") != 2
        or not re.search(
            r"(?<![A-Za-z])U(?![A-Za-z])|回形|回型|折返|平行双跑",
            str(form.get("shape") or "") + str(form.get("description") or ""),
            re.I,
        )
    ):
        return None
    direction = str(form.get("span_direction") or "").strip().lower()
    if direction and direction not in {"+x", "-x", "+z", "-z"}:
        return None
    if not direction:
        match = re.search(
            r"第一跑[^。；]*?沿\s*([+-])\s*([XZ])",
            str(form.get("description") or ""),
            re.I,
        )
        direction = match[1] + match[2].lower() if match else ""
    position = (design.get("placement") or {}).get("position")
    connections = marker.get("floor_connections") or []
    values = [
        size.get("width"),
        size.get("depth"),
        form.get("flight_width"),
        form.get("landing_depth"),
    ]
    if (
        not direction
        or not isinstance(position, list)
        or len(position) != 3
        or len(connections) != 1
        or not all(type(v) in (int, float) and isfinite(v) and v > 0 for v in values)
        or not all(type(v) in (int, float) and isfinite(v) for v in position)
    ):
        return None
    axis = 0 if direction[1] == "x" else 2
    cross_axis = 2 if axis == 0 else 0
    sign = 1 if direction[0] == "+" else -1
    length, cross = (
        size["width" if axis == 0 else "depth"],
        size["depth" if axis == 0 else "width"],
    )
    lower, upper = connections[0]["from_y"], connections[0]["to_y"]
    middle = (lower + upper) / 2
    rises, tread, riser = (
        form.get("rises"),
        form.get("tread_depth"),
        form.get("riser_height"),
    )
    if rises is not None and (type(rises) is not int or rises < 1):
        return None
    if riser is not None:
        if type(riser) not in (int, float) or not isfinite(riser) or riser <= 0:
            return None
        if rises is None:
            count = (middle - lower) / riser
            if abs(count - round(count)) > 0.000001 or count < 1:
                return None
            rises = round(count)
        elif abs(rises * riser - (middle - lower)) > 0.01:
            return None
    if tread is not None and (
        type(tread) not in (int, float)
        or not isfinite(tread)
        or tread <= 0
        or rises is None
    ):
        return None
    run = rises * tread if tread is not None else length - form["landing_depth"]
    if (
        run <= 0
        or run + form["landing_depth"] > length + 0.01
        or 2 * form["flight_width"] > cross + 0.01
    ):
        return None
    near = position[axis] - sign * length / 2
    turn = near + sign * run
    far = turn + sign * form["landing_depth"]
    cross_offset = (cross - form["flight_width"]) / 2
    first_cross, second_cross = (
        position[cross_axis] - cross_offset,
        position[cross_axis] + cross_offset,
    )

    def point(cross_value, y, along):
        result = list(position)
        result[axis], result[cross_axis], result[1] = (
            round(along, 6),
            round(cross_value, 6),
            round(y, 6),
        )
        return result

    first_from, first_to = (
        point(first_cross, lower, near),
        point(first_cross, middle, turn),
    )
    second_from, second_to = (
        point(second_cross, middle, turn),
        point(second_cross, upper, near),
    )
    from app.domain.validation.spatial import _floor_regions_by_level
    from app.domain.geometry.geometry import point_in_regions

    levels = _floor_regions_by_level(base["geometry"]["elements"])
    for endpoint, y in ((first_from, lower), (second_to, upper)):
        regions = []
        for level, group in levels:
            if abs(level - y) <= 0.01:
                regions.extend(group)
        if not regions:
            return None
        for factor in (-1, 0, 1):
            offset_x = factor * form["flight_width"] / 2 if cross_axis == 0 else 0
            offset_z = factor * form["flight_width"] / 2 if cross_axis == 2 else 0
            sample = (endpoint[0] + offset_x, endpoint[2] + offset_z)
            if not point_in_regions(sample, regions):
                return None
    bounds = [
        position[0] - size["width"] / 2,
        position[2] - size["depth"] / 2,
        position[0] + size["width"] / 2,
        position[2] + size["depth"] / 2,
    ]
    bounds[0 if axis == 0 else 1] = min(turn, far)
    bounds[2 if axis == 0 else 3] = max(turn, far)
    flight = {
        "width": form["flight_width"],
        "rise": round(middle - lower, 6),
        "run": round(run, 6),
    }
    if rises is not None:
        flight.update(
            stepCount=rises, stepHeight=(middle - lower) / rises, stepDepth=run / rises
        )
    return {
        "first_flight": {**flight, "from": first_from, "to": first_to},
        "second_flight": {**flight, "from": second_from, "to": second_to},
        "landing": {"bounds": [round(v, 6) for v in bounds], "top_y": round(middle, 6)},
        "direction_axis": axis,
        "direction_sign": sign,
    }


def _item_context(state, markers, base, reference_entity_ids=()):
    from app.domain.components.names import component_reference_prompt

    drawing = state["design_document"]["decisions"]
    from app.domain.design.coordinates import design_geometry_context

    from app.domain.design.spatial import execution_view

    object_scene = drawing.get("kind") == "object"
    geometry = (state.get("resolved_design") or {}).get("geometry_context")
    if object_scene:
        geometry = {"levels": [], "volumes": {}}
        spatial_view = drawing
    else:
        geometry = geometry or design_geometry_context(drawing)
        spatial_view = execution_view(drawing, geometry)
    body = any(m["type"] == "building_body" for m in markers.values())
    from app.domain.components.names import resolve_component_name

    circulation = any(
        resolve_component_name(m["type"])["entity_type"] == "stair"
        for m in markers.values()
    )
    needed = {m.get("host", "") for m in markers.values()} | set(reference_entity_ids)
    from app.domain.design.relations import opening_cell_limits

    opening_hosts = _opening_host_context(state, markers, base, needed)
    records = implementation_records(state)
    for marker in markers.values():
        needed.update(
            v
            for k, v in marker.get("entity", {}).items()
            if k.startswith("parent") and isinstance(v, str)
        )
        for dependency in marker.get("depends_on", []):
            if dependency != "building_body":
                needed.update((records.get(dependency) or {}).get("entity_ids", []))
    entities = []
    for geometry_bucket in ("elements", "components"):
        for current_entity in base["geometry"][geometry_bucket]:
            entities.append(current_entity)
    if any((m.get("host") or "").startswith("wall_") for m in markers.values()):
        structural_ids = set((records.get("building_body") or {}).get("entity_ids", []))
        needed.update(
            e["id"]
            for e in entities
            if e["id"] in structural_ids
            and e.get("type") in {"beam", "column", "primitive"}
        )
    body_hosts = {
        e["id"]
        for e in state.get("drawing_hosts", [])
        if e.get("type") == "wall" and not e.get("open")
    }
    volumes = [
        v
        for v in spatial_view.get("volumes", [])
        if circulation or any(m.get("host") == v["id"] for m in markers.values())
    ]
    for entity in entities:
        if (
            object_scene
            or body
            or (circulation and entity.get("type") == "wall")
            or any(entity["id"].startswith(f"wall_{host}_") for host in needed if host)
        ):
            needed.add(entity["id"])
        if entity.get("type") in {"floor", "stair"} and all(
            isinstance(entity.get(k), list) for k in ("from", "to")
        ):
            if any(
                min(entity["from"][0], entity["to"][0]) < v["x"] + v["width"]
                and max(entity["from"][0], entity["to"][0]) > v["x"]
                and min(entity["from"][2], entity["to"][2]) < v["z"] + v["depth"]
                and max(entity["from"][2], entity["to"][2]) > v["z"]
                for v in volumes
            ):
                needed.add(entity["id"])
    _expand_context_dependencies(entities, needed)
    existing_geometry = {}
    for bucket in ("elements", "components"):
        existing_geometry[bucket] = []
        for entity in base["geometry"][bucket]:
            if entity["id"] in needed:
                existing_geometry[bucket].append(entity)
    context = {
        "component_references": component_reference_prompt(
            {m["type"] for m in markers.values()}
        ),
        "levels": geometry["levels"],
        "volume_geometry": geometry["volumes"],
        "markers": list(markers.values()),
        "drawing": {
            key: drawing.get(key)
            for key in ("concept", "design_intent", "massing", "materials", "coordinate_system",
                        "levels", "profiles", "systems", "walls", "slabs", "voids", "roofs", "relations", "floor_layouts")
        },
        "diagram_hosts": [
            e
            for e in state.get("drawing_hosts", [])
            if e["id"] in (body_hosts if body else needed)
        ],
        "existing_blueprint": {**base, "geometry": existing_geometry},
    }
    context["opening_hosts"] = opening_hosts
    context["material_roles"] = {
        role["role"]: role["materialId"]
        for role in ((drawing.get("materials") or {}).get("resolved_plan") or {}).get(
            "roles", []
        )
    }
    context["opening_cell_limits"] = {
        m["id"]: limits
        for m in markers.values()
        if (limits := opening_cell_limits(m)) is not None
    }
    from app.domain.design.relations import canopy_mount_target

    context["canopy_mount_targets"] = {
        m["id"]: target
        for m in markers.values()
        if (target := canopy_mount_target(base, m)) is not None
    }
    context["native_size_targets"] = {}
    for marker in markers.values():
        size_targets = {}
        for field, value in (marker["design"].get("size") or {}).items():
            entity_type = resolve_component_name(marker["type"])["entity_type"]
            native_field = _SIZE_FIELDS.get((entity_type, field), field)
            size_targets[native_field] = value
        context["native_size_targets"][marker["id"]] = size_targets
    context["stair_route_targets"] = {
        m["id"]: route
        for m in markers.values()
        if (route := _stair_route_target(base, m)) is not None
    }
    context["attachment_geometry"] = _attachment_context(base, markers, records)
    context["drawing"]["volumes"] = [
        v
        for v in drawing.get("volumes", [])
        if body
        or circulation
        or any(
            m.get("host") == v["id"]
            or (m.get("host") or "").startswith(f"wall_{v['id']}_")
            for m in markers.values()
        )
    ]
    if circulation:
        context["drawing"]["circulation"] = drawing.get("circulation")
        levels = context["levels"]
        context["available_floor_connections"] = [
            {
                "from_floor": lower["index"],
                "to_floor": upper["index"],
                "from_y": lower["base_y"],
                "to_y": upper["base_y"],
            }
            for lower, upper in zip(levels, levels[1:])
        ]
    if any(
        resolve_component_name(m["type"])["entity_type"] == "roof"
        for m in markers.values()
    ):
        context["drawing"]["roof"] = deepcopy(drawing.get("roof"))
    all_markers = (state.get("resolved_design") or {}).get("component_markers", [])
    current_hosts = {marker.get("host") for marker in markers.values()}
    context["delegated_markers"] = []
    context["other_task_markers"] = []
    for marker in all_markers:
        if marker["id"] in markers:
            continue
        if marker.get("host") and marker.get("host") in current_hosts:
            context["delegated_markers"].append(
                {field: marker.get(field) for field in ("id", "type", "host", "design")}
            )
        context["other_task_markers"].append(
            {field: marker.get(field) for field in ("id", "type", "host")}
        )
    context["assembly_bounds"] = _marker_assembly_bounds(markers)
    if object_scene:
        context["drawing"]["objects"] = drawing.get("objects", [])
        context["drawing"]["ground_y"] = 0
    if body:
        context["drawing"] = deepcopy(
            next(m["design"] for m in markers.values() if m["type"] == "building_body")
        )
        context["markers"] = []
        for marker in markers.values():
            context["markers"].append(
                {key: value for key, value in marker.items() if key != "design"}
            )
        context["delegated_markers"] = []
        for marker in all_markers:
            if marker["id"] not in markers:
                context["delegated_markers"].append(
                    {field: marker[field] for field in ("id", "type", "host")}
                )
    return context


def failure_context_fingerprint(state, marker, base=None, owned_ids=()):
    """失败去重绑定图纸及本标记实际依赖，宿主变化后允许重新验收。"""
    from app.domain.validation.diagnostics import blueprint_fingerprint

    context = _item_context(
        state, {marker["id"]: marker}, base or implementation_blueprint(state)
    )
    geometry = context["existing_blueprint"]["geometry"]
    owned = set(owned_ids) | set(
        (implementation_records(state).get(marker["id"]) or {}).get("entity_ids", [])
    )
    reference_geometry = {}
    for bucket, entities in geometry.items():
        reference_entities = [
            entity for entity in entities if entity["id"] not in owned
        ]
        reference_geometry[bucket] = sorted(
            reference_entities, key=lambda entity: entity["id"]
        )
    return blueprint_fingerprint(
        {
            "design_hash": (state.get("resolved_design") or {}).get("design_hash"),
            "geometry": reference_geometry,
            **{
                key: context.get(key)
                for key in (
                    "levels",
                    "diagram_hosts",
                    "opening_hosts",
                    "attachment_geometry",
                )
            },
        }
    )


def _failed_candidate(row, retained_geometry, error, context_fingerprint):
    from app.domain.validation.diagnostics import blueprint_fingerprint

    geometry = row.get("geometry") if isinstance(row, dict) else None
    if not isinstance(geometry, dict) or any(
        not isinstance(geometry.get(k, []), list) for k in ("elements", "components")
    ):
        return None
    entities = []
    for geometry_bucket in ("elements", "components"):
        for entity in geometry.get(geometry_bucket, []):
            entities.append(entity)
    for geometry_bucket in ("elements", "components"):
        for entity in (retained_geometry or {}).get(geometry_bucket, []):
            if entity not in entities:
                entities.append(entity)
    if not entities or any(not isinstance(e, dict) for e in entities):
        return None
    # 实体改名或说明文字变化不能伪装成新的几何；外部宿主引用保持原值。
    labels = {}
    for entity in entities:
        if not isinstance(entity.get("id"), str):
            continue
        geometry_fields = {}
        for key, value in entity.items():
            if key != "id" and not key.startswith("parent"):
                geometry_fields[key] = value
        labels[entity.get("id")] = blueprint_fingerprint(geometry_fields)

    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items() if k != "id"}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        return labels.get(value, value) if isinstance(value, str) else value

    normalized = sorted(
        json.dumps(normalize(e), sort_keys=True, ensure_ascii=False) for e in entities
    )
    for entity_id in sorted(labels, key=len, reverse=True):
        error = re.sub(
            r"(?<![\w.-])" + re.escape(entity_id) + r"(?![\w.-])",
            labels[entity_id],
            error,
        )
    issues = sorted(set(filter(None, (part.strip() for part in error.split("；")))))
    return {
        "candidate_fingerprint": blueprint_fingerprint(
            {
                "entities": normalized,
                "materials": row.get("materials") or {},
                "assets": row.get("assets") or {},
            }
        ),
        "context_fingerprint": context_fingerprint,
        "issues_fingerprint": blueprint_fingerprint(issues),
        "issues": issues,
    }


async def run_marker_generate(state, item):
    """按审核版本执行图纸标记，单次任务的可变状态由执行器管理。"""
    resolved = state.get("resolved_design") or {}
    if item.params["design_hash"] != resolved.get("design_hash"):
        return {}, "failed", [], "任务与审核图纸版本不一致", []
    return await _MarkerGeneration(state, item).run()


class _MarkerGeneration:
    """保存单次任务跨阶段共享的候选、落实记录及失败证据。"""

    async def run(self):
        """依次执行确定性构造、参考检索、模型实现和结果汇总。"""
        from app.agent.runtime import get_reasoning_callback
        from app.domain.components.capability import load_engine_schema

        schema = load_engine_schema()
        self.schema = schema
        if schema is None:
            return (
                {"status": "failed", "error": "WILD Schema 不可用"},
                "aborted",
                [],
                "WILD Schema 不可用",
                self.trace,
            )
        self.callback = get_reasoning_callback()
        self._construct_systems()
        if self.pending.keys() - self.system_ids and not self.references:
            await self._load_references()
        self._prepare_jobs()
        await self._run_jobs()
        return self._finish()

    def __init__(self, state, item):
        """准备本轮实现使用的图纸、已有产物和诊断记录。"""
        self.state = state
        self.item = item
        self.resolved = self.state.get("resolved_design") or {}
        self.markers = {m["id"]: m for m in self.resolved.get("component_markers", [])}
        self.target_ids = (
            self.item.params.get("retry_marker_ids") or self.item.target["marker_ids"]
        )
        self.pending = {i: deepcopy(self.markers[i]) for i in self.target_ids}
        prior_records = implementation_records(self.state)
        for marker in self.pending.values():
            parent = prior_records.get(marker.get("host"))
            if parent:
                marker["host_entity_ids"] = list(parent.get("entity_ids", []))
        old = (self.state.get("component_diagnostics") or {}).get(self.item.id) or {}
        self.trace = deepcopy(old.get("trace") or [])
        self.previous_trace_size = len(self.trace)
        self.references = old.get("references") or ""
        self.failures = {
            i: "\n".join(
                filter(
                    None,
                    (
                        (old.get("failures") or {}).get(i, ""),
                        self.item.params.get("assembly_feedback", ""),
                    ),
                )
            )
            for i in self.pending
        }
        self.failed_rows = deepcopy(old.get("failed_implementations") or {})
        self.failure_evidence = deepcopy(old.get("failure_evidence") or {})
        self.parts = deepcopy(old.get("partial_implementations") or {})
        self.base = implementation_blueprint(self.state)
        for part in self.parts.values():
            merge_marker_resources(self.base, part)
            for bucket in ("elements", "components"):
                self.base["geometry"][bucket].extend(
                    deepcopy(part.get("geometry", {}).get(bucket, []))
                )
        self.fragments = list(
            (self.state.get("component_fragments") or {}).get(self.item.id) or []
        )
        self.records = dict(old.get("implementations") or {})
        if not self.item.params.get("assembly_feedback"):
            self.pending = {
                i: m
                for i, m in self.pending.items()
                if self.records.get(i, {}).get("status") != "implemented"
            }
        self.buckets = {
            key: list(old.get(key) or []) for key in ("elements", "components")
        }
        self.materials, self.assets = (
            dict(old.get("materials") or {}),
            dict(old.get("assets") or {}),
        )

    def _record_failure(self, marker_id, row, raw_issues=()):
        """把失败候选与图纸期望转换为可定位的修订证据。"""
        preview = deepcopy(self.base)
        geometry = row.get("geometry") if isinstance(row, dict) else None
        ids = []
        if isinstance(geometry, dict):
            for bucket in ("elements", "components"):
                values = geometry.get(bucket)
                if isinstance(values, list):
                    preview["geometry"][bucket].extend(
                        deepcopy(e) for e in values if isinstance(e, dict)
                    )
                    ids.extend(
                        e["id"]
                        for e in values
                        if isinstance(e, dict) and isinstance(e.get("id"), str)
                    )
        raw_issues = deepcopy(raw_issues) or validation_issues_from_results(
            [
                {
                    "name": "implementation",
                    "has_error": True,
                    "output": self.failures[marker_id],
                }
            ],
            preview,
        )
        for issue in raw_issues:
            issue["marker_id"] = marker_id
            if not issue.get("entity_ids") and not issue.get("entity_id"):
                issue["entity_ids"] = ids
        evidence = repair_feedback(
            raw_issues,
            preview,
            markers=[self.markers[marker_id]],
            design_hash=self.resolved.get("design_hash", ""),
            source="implementation",
        )
        self.failure_evidence[marker_id] = evidence
        return evidence

    def _construct_systems(self):
        """按已批准构造执行确定性实现，保留设计冲突证据。"""
        self.system_ids = {
            i
            for i, m in self.pending.items()
            if construction_spec(m["design"]) is not None or m.get("geometry") is not None or m.get("capability_gaps")
        }
        from graphlib import TopologicalSorter

        dependencies = {marker_id: set(self.pending[marker_id].get("depends_on", [])) & self.system_ids
                        for marker_id in sorted(self.system_ids)}
        for marker_id in TopologicalSorter(dependencies).static_order():
            marker = self.pending[marker_id]
            attempt = {
                "tool": "construct_system",
                "stage": "construction",
                "model_calls": 0,
                "version": SYSTEM_VERSION,
                "marker_ids": [marker_id],
                "source": deepcopy(marker["design"]),
                "errors": {},
            }
            self.trace.append(attempt)
            try:
                if marker.get("capability_gaps"):
                    raise ValueError(json.dumps(marker["capability_gaps"], ensure_ascii=False))
                row = construct_system(marker, self.base)
                attempt["output"] = deepcopy(row)
                candidate, accepted, rejected, record = _accept_fragment(
                    self.base,
                    row,
                    marker,
                    dependent_markers=self.markers.values(),
                    diagram_hosts=self.state.get("drawing_hosts", []),
                )
                if rejected:
                    raise ValueError(rejected["error"])
                entities = []
                for current_values in accepted["geometry"].values():
                    for current_entity in current_values:
                        entities.append(current_entity)
                self.base = candidate
                self.records[marker_id] = record
                self.fragments.extend(entities)
                for key in self.buckets:
                    self.buckets[key].extend(e["id"] for e in row["geometry"][key])
                self.pending.pop(marker_id)
                self.failures.pop(marker_id, None)
                self.failure_evidence.pop(marker_id, None)
            except (ValueError, TypeError, KeyError) as exc:
                self.failures[marker_id] = (
                    "已批准构造无法落实，须修订设计参数或宿主：" + str(exc)
                )
                attempt["errors"][marker_id] = self.failures[marker_id]
                attempt["stop_reason"] = "construction_design_conflict"
                attempt["failure_evidence"] = {
                    marker_id: self._record_failure(
                        marker_id,
                        None,
                        [
                            {
                                "validator": "design_construction_conflict",
                                "message": self.failures[marker_id],
                                "recommended_repair_level": "design_revision",
                            }
                        ],
                    )
                }

    async def _load_references(self):
        """为缺少构造资料的标记加载知识库及网络参考。"""
        from app.domain.components.capability import capability_surface
        from app.agent.workflows.planning.knowledge_tool import search_knowledge_result

        if self.callback:
            await self.callback(
                "execute:progress", f"{self.item.label}：先查询知识库。\n"
            )
        descriptions = []
        for pending_marker in self.pending.values():
            pending_design = pending_marker["design"]
            pending_form = pending_design.get("form")
            form_description = (
                pending_form.get("description")
                if isinstance(pending_form, dict)
                else pending_form
            )
            for value in (pending_design.get("description"), form_description):
                descriptions.append(str(value or "").strip())
        descriptions = list(dict.fromkeys(descriptions))
        from app.domain.components.names import resolve_component_name

        component_types = list(
            dict.fromkeys(
                resolve_component_name(m["type"])["kind"] for m in self.pending.values()
            )
        )
        query = " ".join(
            [
                self.item.kind,
                self.item.label,
                *component_types,
                *descriptions,
                "构造 形态 JSON 示例",
            ]
        )
        if self.item.kind == "roof":
            roof_forms = list(
                dict.fromkeys(
                    str(m["design"].get("roof_type") or m["design"].get("type") or "")
                    for m in self.pending.values()
                )
            )
            query = " ".join(roof_forms) + " " + query
        if self.item.kind == "building_body":
            from app.domain.knowledge.policy import plan_knowledge_query

            query = plan_knowledge_query(
                query, self.state["design_document"]["decisions"]
            )
        query = query[:1000]
        variants = (
            {
                m["design"].get("roof_type", m["design"].get("type"))
                for m in self.pending.values()
            }
            if self.item.kind == "roof"
            else set()
        )
        known_variants = [
            v
            for v in sorted(variants - {None})
            if resolve_component_name(v)["entity_type"] == "roof"
            and resolve_component_name(v)["kind"] != "roof"
        ]
        if len(variants) == 1:
            variant = next(iter(variants))
        elif len(known_variants) == 1:
            variant = known_variants[0]
        else:
            variant = None
        lookup_kind = (
            variant
            if variant and resolve_component_name(variant)["entity_type"]
            else self.item.kind
        )
        import asyncio

        knowledge = await asyncio.to_thread(
            search_knowledge_result, query, kind=lookup_kind
        )
        self.references = knowledge["text"]
        native = capability_surface()
        supplied_shape = True
        for pending_marker in self.pending.values():
            pending_design = pending_marker.get("design", {})
            if any(pending_design.get(key) for key in ("geometry", "path", "profile")):
                continue
            pending_form = pending_design.get("form")
            if isinstance(pending_form, dict) and any(
                pending_form.get(key) for key in ("shape", "path", "profile", "points")
            ):
                continue
            supplied_shape = False
            break
        needs_web = (
            not knowledge["has_shape_reference"]
            and not supplied_shape
            and any(
                resolve_component_name(m["type"])["entity_type"] not in native
                and m["type"] != "building_body"
                for m in self.pending.values()
            )
        )
        self.trace.append(
            {
                "tool": "search_knowledge",
                "query": query,
                "result": self.references,
                "ok": not knowledge.get("error_type")
                and not self.references.startswith("❌"),
                "error_type": knowledge.get("error_type"),
                "has_shape_reference": knowledge["has_shape_reference"],
                "injected_chunk_ids": knowledge.get("chunk_ids", []),
                "web_required": needs_web,
                "web_reason": (
                    "缺少当前构件的形态资料"
                    if needs_web
                    else "已有构件参考、原生形态或图纸几何信息"
                ),
            }
        )
        if needs_web:
            query = web_reference_query(self.item, self.pending)
            if self.callback:
                await self.callback(
                    "execute:progress", f"{self.item.label}：缺少形态参考，查询网络。\n"
                )
            try:
                hits = await search_web_impl(query)
                self.trace.append(
                    {
                        "tool": "web_search",
                        "query": query,
                        "sources": hits,
                        "ok": bool(hits),
                    }
                )
                self.references += "\n网络形态参考：\n" + json.dumps(
                    hits, ensure_ascii=False
                )
                if not hits and self.callback:
                    await self.callback(
                        "execute:progress",
                        f"{self.item.label}：网络没有相关资料，依据图纸和模型知识继续实现。\n",
                    )
            except Exception as exc:
                self.trace.append(
                    {
                        "tool": "web_search",
                        "query": query,
                        "ok": False,
                        "error": str(exc),
                    }
                )

    def _prepare_jobs(self):
        """沿用历史拆分边界，建立本轮可执行的修订队列。"""
        self.completed_stages = {}
        for pending_marker_id in self.pending:
            marker_stages = set()
            for trace_entry in self.trace:
                if pending_marker_id in trace_entry.get(
                    "marker_ids", []
                ) and not trace_entry.get("split_marker_ids"):
                    marker_stages.add(trace_entry.get("stage"))
            self.completed_stages[pending_marker_id] = marker_stages
        stages = (
            ("assembly_revision",)
            if self.item.params.get("assembly_feedback")
            else IMPLEMENTATION_STAGES
        )
        self.model_error = None
        self.stopped = set()
        from collections import deque

        batches = [list(self.pending)]
        for attempt in self.trace:
            for half in attempt.get("split_marker_ids", []):
                split_batches = []
                for batch in batches:
                    inside_half = []
                    outside_half = []
                    for pending_marker_id in batch:
                        if pending_marker_id in half:
                            inside_half.append(pending_marker_id)
                        else:
                            outside_half.append(pending_marker_id)
                    if inside_half:
                        split_batches.append(inside_half)
                    if outside_half:
                        split_batches.append(outside_half)
                batches = split_batches
        self.jobs = deque()
        for stage in stages:
            for batch in batches:
                self.jobs.append((stage, batch))
        self.call_limit = len(self.item.target["marker_ids"]) * (
            len(IMPLEMENTATION_STAGES) + 1
        )

    def _build_batch(self, eligible):
        """组装当前批次的协议、反馈和只读设计上下文。"""
        protocol = build_marker_output_protocol(
            self.schema,
            eligible,
            self.references,
            {i: self.failed_rows[i] for i in eligible if i in self.failed_rows},
        )
        from app.domain.components.names import resolve_component_name

        families = {
            resolve_component_name(m["type"])["entity_type"] or m["type"]
            for m in eligible.values()
        }
        prompt = build_marker_implementation_prompt(families, protocol)
        context = _item_context(
            self.state,
            eligible,
            self.base,
            self.item.params.get("reference_entity_ids", []),
        )
        accepted_entity_ids = {}
        for accepted_marker_id in eligible:
            marker_entity_ids = []
            for bucket in ("elements", "components"):
                for entity in (
                    self.parts.get(accepted_marker_id, {})
                    .get("geometry", {})
                    .get(bucket, [])
                ):
                    marker_entity_ids.append(entity["id"])
            accepted_entity_ids[accepted_marker_id] = marker_entity_ids
        context.update(
            validation_feedback={i: self.failures[i] for i in eligible},
            reference_data=self.references,
            failure_evidence={
                i: self.failure_evidence[i]
                for i in eligible
                if i in self.failure_evidence
            },
            failed_implementations={
                i: self.failed_rows[i] for i in eligible if i in self.failed_rows
            },
            accepted_entity_ids=accepted_entity_ids,
        )
        for bucket, entities in context["existing_blueprint"]["geometry"].items():
            for entity_id in eligible:
                for current_entity in (
                    self.parts.get(entity_id, {}).get("geometry", {}).get(bucket, [])
                ):
                    if current_entity not in entities:
                        entities.append(current_entity)
        return prompt, context

    async def _invoke_batch(self, stage, eligible, prompt, context):
        """执行一次模型调用；服务故障保留原有终止结果。"""
        from app.domain.validation.diagnostics import blueprint_fingerprint
        from app.agent.runtime import create_llm
        from app.infrastructure.llm.invocation import invoke_llm

        try:
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ]
            from app.infrastructure.observability.trace import llm_trace_scope
            from app.agent.workflows.planning.expand import _batch_load

            chunk_ids = next(
                (
                    t.get("injected_chunk_ids", [])
                    for t in reversed(self.trace)
                    if t.get("tool") == "search_knowledge"
                ),
                [],
            )
            with llm_trace_scope(
                item_id=self.item.id,
                stage=stage,
                design_hash=self.resolved.get("design_hash"),
                candidate_fingerprint=blueprint_fingerprint(self.base),
                marker_ids=list(eligible),
                batch_load=_batch_load(list(eligible.values())),
                injected_chunk_ids=chunk_ids,
            ):
                reply = await invoke_llm(
                    create_llm(enable_thinking=False, streaming=False), messages
                )
        except Exception as exc:
            from app.infrastructure.llm.errors import model_failure_result

            self.model_error = model_failure_result(exc)
            return None
        return reply

    async def _split_batch(self, stage, eligible, attempt):
        """截断时拆分无相互依赖的标记，并保留后续阶段的边界。"""
        from collections import deque

        ids = list(eligible)
        middle = len(ids) // 2
        halves = [ids[:middle], ids[middle:]]
        attempt["split_marker_ids"] = halves
        attempt["errors"] = {
            i: "模型输出达到长度上限；拆分当前批次，不原批重复修订" for i in ids
        }
        # 后续修订沿用拆分边界，不再把失败标记拼回同一个超长请求。
        following = []
        for next_stage, next_ids in self.jobs:
            selected = set(ids).intersection(next_ids)
            if selected:
                for half in halves:
                    if selected.intersection(half):
                        selected_ids = [
                            marker_id for marker_id in half if marker_id in selected
                        ]
                        following.append((next_stage, selected_ids))
                other = [i for i in next_ids if i not in selected]
                if other:
                    following.append((next_stage, other))
            else:
                following.append((next_stage, next_ids))
        self.jobs = deque([(stage, half) for half in halves] + following)
        if self.callback:
            await self.callback(
                "execute:progress",
                f"{self.item.label}：输出达到长度上限，拆为 {len(halves[0])} 和 {len(halves[1])} 个标记继续实现。\n",
            )

    def _read_batch(self, reply, attempt, eligible):
        """解析模型输出，拒绝重复、越界或不完整的标记列表。"""
        from app.domain.blueprint.json_extractor import extract_json_object

        try:
            payload = extract_json_object(
                reply.content or "",
                required_key="implementations",
                raise_on_error=True,
                outer_only=True,
            )
        except ValueError as exc:
            payload = {}
            feedback = (
                "模型输出达到长度上限；保留全部设计要求，精简重复字段和说明，返回完整 JSON"
                if attempt["finish_reason"] in {"length", "max_tokens"}
                else str(exc)
                + "；只返回完整 JSON，算式写成 parameters 模式的字符串表达式"
            )
            self.failures.update({i: feedback for i in eligible})
        rows = payload.get("implementations")
        if not payload:
            pass
        elif not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            self.failures.update({i: "implementations 必须是数组" for i in eligible})
        elif (
            any(not isinstance(r.get("id"), str) for r in rows)
            or len({r["id"] for r in rows}) != len(rows)
            or any(r["id"] not in eligible for r in rows)
        ):
            self.failures.update(
                {i: "返回了重复或不属于当前任务的标记" for i in eligible}
            )
        else:
            returned = {r["id"]: r for r in rows}
            return returned
        return None

    def _retain_body_geometry(self, marker_id, row, marker, attempt):
        """将主体之外的构件归还各自任务，保留原始输出诊断。"""
        from app.domain.components.names import resolve_component_name

        if marker["type"] == "building_body" and isinstance(row.get("geometry"), dict):
            geometry = row["geometry"]
            if all(
                isinstance(geometry.get(k, []), list)
                for k in ("elements", "components")
            ):
                delegated_ids = {i for i in self.markers if i != marker_id}
                delegated_stair = any(
                    resolve_component_name(self.markers[i]["type"])["entity_type"]
                    == "stair"
                    for i in delegated_ids
                )
                has_room_plan = any(
                    layout.get("rooms")
                    for layout in marker["design"].get("floor_layouts") or []
                )

                def belongs_to_body(entity):
                    return (
                        entity.get("type") in BUILDING_BODY_ENTITY_TYPES
                        and not (has_room_plan and entity.get("type") == "column")
                        and not (delegated_stair and entity.get("type") == "stair")
                        and not any(
                            entity.get("id") == i
                            or str(entity.get("id", "")).startswith(i + "_")
                            for i in delegated_ids
                        )
                    )

                outside = []
                for geometry_bucket in ("elements", "components"):
                    for current_entity in geometry.get(geometry_bucket, []):
                        if not (
                            isinstance(current_entity, dict)
                            and (
                                geometry_bucket != "elements"
                                or not belongs_to_body(current_entity)
                            )
                        ):
                            continue
                        outside.append(current_entity.get("id"))
                attempt["outside_item_entity_ids"] = outside
                geometry["elements"] = [
                    e
                    for e in geometry.get("elements", [])
                    if not isinstance(e, dict) or belongs_to_body(e)
                ]
                geometry["components"] = []

    def _adopt_fragment(
        self, marker_id, accepted, rejected, record, placement_changes, attempt
    ):
        """累积已通过片段，拒绝错误稿，并更新落实记录和资源。"""
        from app.domain.validation.diagnostics import blueprint_fingerprint

        accumulated = self.parts.setdefault(
            marker_id,
            {
                "geometry": {"elements": [], "components": []},
                "materials": {},
                "assets": {},
            },
        )
        if accepted:
            if accepted.get("repeated_entity_ids"):
                attempt.setdefault("repeated_entity_ids", {})[marker_id] = accepted[
                    "repeated_entity_ids"
                ]
            for bucket in ("elements", "components"):
                accumulated["geometry"][bucket].extend(
                    accepted["geometry"].get(bucket, [])
                )
            for key in ("materials", "assets"):
                accumulated[key].update(accepted.get(key) or {})
        if rejected:
            failed_geometry = rejected["row"].get("geometry")
            repeated = rejected["row"].get("repeated_entity_ids")
            if repeated:
                attempt.setdefault("repeated_entity_ids", {})[marker_id] = repeated
            if (
                repeated
                and isinstance(failed_geometry, dict)
                and not any(failed_geometry.values())
                and self.failures.get(marker_id)
            ):
                raise ValueError(self.failures[marker_id])
            if marker_id not in self.failed_rows or (
                isinstance(failed_geometry, dict)
                and any(failed_geometry.get(k) for k in ("elements", "components"))
            ):
                self.failed_rows[marker_id] = rejected["row"]
            raise ValueError(rejected["error"])
        entities = []
        for geometry_bucket in ("elements", "components"):
            for current_entity in accumulated["geometry"][geometry_bucket]:
                entities.append(current_entity)
        record.update(
            entity_ids=[e["id"] for e in entities],
            entity_fingerprint=blueprint_fingerprint(entities),
        )
        assembly_changes = list(placement_changes)
        for trace_entry in self.trace:
            assembly_changes.extend(
                trace_entry.get("shared_wall_changes", {}).get(marker_id, [])
            )
        if assembly_changes:
            record["assembly_changes"] = assembly_changes
        adopted_bindings = {}
        for entry in self.trace:
            for current_key, current_value in (
                entry.get("material_bindings", {}).get(marker_id, {}).items()
            ):
                if not (
                    current_value in accumulated["materials"]
                    or current_value in self.base["materials"]
                ):
                    continue
                adopted_bindings[current_key] = current_value
        if adopted_bindings:
            record["material_bindings"] = adopted_bindings
        self.fragments.extend(entities)
        self.records[marker_id] = record
        for key in self.buckets:
            self.buckets[key].extend(e["id"] for e in accumulated["geometry"][key])
        self.materials.update(accumulated["materials"])
        self.assets.update(accumulated["assets"])
        self.pending.pop(marker_id)
        self.failures.pop(marker_id, None)
        self.failure_evidence.pop(marker_id, None)

    async def _record_rejection(
        self, marker_id, marker, submitted, rejected, attempt, exc
    ):
        """记录本次失败并识别几何与问题都未变化的重复候选。"""
        self.failures[marker_id] = str(exc)
        if isinstance(submitted, dict) and (
            rejected is None
            or any(k in submitted for k in ("parameters", "walls", "slabs"))
        ):
            self.failed_rows[marker_id] = submitted
        attempt.setdefault("issues", {})[marker_id] = getattr(exc, "issues", []) or (
            rejected or {}
        ).get("issues", [])
        owned = []
        for geometry_bucket in ("elements", "components"):
            for current_entity in (
                self.parts.get(marker_id, {})
                .get("geometry", {})
                .get(geometry_bucket, [])
            ):
                owned.append(current_entity["id"])
        failed_candidate = (
            _failed_candidate(
                submitted,
                self.parts.get(marker_id, {}).get("geometry"),
                str(exc),
                failure_context_fingerprint(self.state, marker, self.base, owned),
            )
            if submitted
            else None
        )
        if failed_candidate:
            attempt.setdefault("failed_candidates", {})[marker_id] = failed_candidate
            previous = next(
                (
                    t.get("failed_candidates", {}).get(marker_id)
                    for t in reversed(self.trace[:-1])
                    if marker_id in t.get("marker_ids", [])
                ),
                None,
            )
            if failed_candidate == previous:
                self.stopped.add(marker_id)
                attempt.setdefault("stop_reasons", {})[
                    marker_id
                ] = "repeated_failed_candidate"
                if self.callback:
                    await self.callback(
                        "execute:progress",
                        f"{self.item.label}：{marker_id} 连续返回相同失败几何且问题未减少，停止重复修订。\n",
                    )

    async def _adopt_implementation(
        self, marker_id, marker, returned, context, attempt
    ):
        """在副本上展开、定位并校验单个标记，只保留通过的结果。"""
        submitted = None
        rejected = None
        try:
            if marker_id not in returned:
                raise ValueError("缺少该标记的实现")
            row = deepcopy(returned[marker_id])
            submitted = deepcopy(row)
            row, construction = expand_implementation(row, marker, context)
            if construction:
                attempt.setdefault("construction", {})[marker_id] = {
                    "source": submitted,
                    **construction,
                }
            self._retain_body_geometry(marker_id, row, marker, attempt)
            from app.domain.design.relations import coalesce_body_walls
            from app.domain.design.relations import place_opening_group

            if marker["type"] == "building_body":
                row, wall_changes = coalesce_body_walls(
                    self.base,
                    row,
                    self.markers.values(),
                    diagram_hosts=self.state.get("drawing_hosts", []),
                )
                if wall_changes:
                    attempt.setdefault("shared_wall_changes", {})[
                        marker_id
                    ] = wall_changes
            row, placement_changes = place_opening_group(self.base, row, marker)
            if placement_changes:
                attempt.setdefault("placement_changes", {})[
                    marker_id
                ] = placement_changes
            row, bindings = _bind_materials(
                self.base, row, marker, context["material_roles"]
            )
            submitted = deepcopy(row)
            if bindings:
                attempt.setdefault("material_bindings", {})[marker_id] = bindings
            retained = {}
            for geometry_bucket in ("elements", "components"):
                for current_entity in (
                    self.parts.get(marker_id, {})
                    .get("geometry", {})
                    .get(geometry_bucket, [])
                ):
                    retained[current_entity["id"]] = current_entity
            geometry = row.get("geometry")
            returned_entities = []
            if isinstance(geometry, dict) and all(
                isinstance(geometry.get(bucket, []), list)
                for bucket in ("elements", "components")
            ):
                for bucket in ("elements", "components"):
                    returned_entities.extend(geometry.get(bucket, []))
            failed_geometry = self.failed_rows.get(marker_id, {}).get("geometry") or {}
            failed_elements = failed_geometry.get("elements") or []
            if (
                marker["type"] == "building_body"
                and returned_entities
                and all(
                    isinstance(e, dict) and retained.get(e.get("id")) == e
                    for e in returned_entities
                )
                and any(e.get("type") == "floor" for e in failed_elements)
                and not any(e.get("type") == "floor" for e in retained.values())
            ):
                attempt.setdefault("repeated_entity_ids", {})[marker_id] = [
                    e["id"] for e in returned_entities
                ]
                raise ValueError(self.failures[marker_id])
            self.base, accepted, rejected, record = _accept_fragment(
                self.base,
                row,
                marker,
                self.parts.get(marker_id, {}).get("geometry"),
                dependent_markers=self.markers.values(),
                diagram_hosts=self.state.get("drawing_hosts", []),
            )
            self._adopt_fragment(
                marker_id, accepted, rejected, record, placement_changes, attempt
            )
        except (ValueError, TypeError, KeyError) as exc:
            await self._record_rejection(
                marker_id, marker, submitted, rejected, attempt, exc
            )

    async def _run_jobs(self):
        """按已有预算执行各阶段，逐批接受结果并回传修订证据。"""
        while self.jobs:
            stage, batch_ids = self.jobs.popleft()
            if not self.pending:
                break
            eligible = {
                i: self.pending[i]
                for i in batch_ids
                if i in self.pending
                and i not in self.stopped
                and i not in self.system_ids
                and stage not in self.completed_stages[i]
            }
            if not eligible:
                continue
            if sum(t.get("model_calls", 0) for t in self.trace) >= self.call_limit:
                self.failures.update(
                    {
                        i: "当前任务模型调用预算已耗尽，仍未完成实现"
                        for i in self.pending
                    }
                )
                self.trace.append(
                    {
                        "tool": "implementation_budget_exhausted",
                        "model_calls": 0,
                        "marker_ids": list(self.pending),
                        "limit": self.call_limit,
                    }
                )
                break
            if self.callback:
                stage_label = (
                    "结合图纸和参考实现" if stage == "generate" else "只修订失败片段"
                )
                await self.callback(
                    "execute:progress",
                    f"{self.item.label}：{stage_label}，待落实 {len(eligible)} 个标记。\n",
                )
            prompt, context = self._build_batch(eligible)
            reply = await self._invoke_batch(stage, eligible, prompt, context)
            if reply is None:
                break
            attempt = {
                "tool": "generate_wild",
                "stage": stage,
                "model_calls": 1,
                "call_id": getattr(reply, "call_id", None),
                "enable_thinking": False,
                "token_usage": reply.token_usage,
                "finish_reason": getattr(reply, "finish_reason", None),
                "output": reply.content,
                "marker_ids": list(eligible),
                "errors": {},
                "feedback_used": deepcopy(context["failure_evidence"]),
            }
            self.trace.append(attempt)
            if (
                attempt["finish_reason"] in {"length", "max_tokens"}
                and len(eligible) > 1
                and (
                    not any(
                        (
                            set(m.get("depends_on") or []).intersection(eligible)
                            for m in eligible.values()
                        )
                    )
                )
            ):
                await self._split_batch(stage, eligible, attempt)
                continue
            returned = self._read_batch(reply, attempt, eligible)
            if returned is not None:
                for marker_id, marker in eligible.items():
                    await self._adopt_implementation(
                        marker_id, marker, returned, context, attempt
                    )
            attempt["errors"] = dict(self.failures)
            attempt["failure_evidence"] = {
                i: self._record_failure(
                    i, self.failed_rows.get(i), attempt.get("issues", {}).get(i, [])
                )
                for i in eligible
                if i in self.failures
            }

    def _finish(self):
        """汇总本轮新增调用及完整诊断，保留主体失败的终止语义。"""
        for marker_id in self.pending if not self.model_error else []:
            self.records[marker_id] = {
                "status": "abandoned",
                "entity_ids": [],
                "reason": self.failures[marker_id],
                "attempted_stages": [t["stage"] for t in self.trace if "stage" in t],
            }
            if marker_id in self.stopped:
                self.records[marker_id]["stop_reason"] = "repeated_failed_candidate"
                self.records[marker_id]["marker_id"] = marker_id
            if marker_id in self.system_ids:
                self.records[marker_id]["stop_reason"] = "construction_design_conflict"
        for marker_id in self.target_ids:
            if marker_id not in self.records:
                continue
            record = self.records[marker_id]
            record["attempts"] = [
                t
                for t in self.trace
                if "stage" not in t or marker_id in t.get("marker_ids", [])
            ]
            record["attempted_stages"] = [
                t["stage"] for t in record["attempts"] if "stage" in t
            ]
        new_calls = sum(
            t.get("model_calls", 0) for t in self.trace[self.previous_trace_size :]
        )
        # 执行器只统计本次新增调用，诊断记录保留之前的完整尝试。
        event_trace = [{**t, "model_calls": 0} for t in self.trace]
        event_trace.append({"tool": "implementation_result", "model_calls": new_calls})
        diag = {
            "implementations": self.records,
            "trace": self.trace,
            "references": self.references,
            "partial_implementations": {
                i: self.parts[i] for i in self.pending if i in self.parts
            },
            "failed_implementations": {
                i: self.failed_rows[i] for i in self.pending if i in self.failed_rows
            },
            "failures": self.failures,
            "failure_evidence": {
                i: self.failure_evidence[i]
                for i in self.pending
                if i in self.failure_evidence
            },
            "materials": self.materials,
            "assets": self.assets,
            **self.buckets,
        }
        summary = {
            "implemented": sum(
                r.get("status") == "implemented" for r in self.records.values()
            ),
            "abandoned": sum(
                r.get("status") == "abandoned" for r in self.records.values()
            ),
            "total": len(self.item.target["marker_ids"]),
            "design_complete": all(
                (self.records.get(i) or {}).get("status") == "implemented"
                for i in self.item.target["marker_ids"]
            ),
        }
        diag["implementation_summary"] = summary
        updates = {
            "component_fragments": {self.item.id: self.fragments},
            "component_diagnostics": {self.item.id: diag},
        }
        if self.model_error:
            return (
                {**updates, **self.model_error},
                "aborted",
                [e["id"] for e in self.fragments],
                self.model_error.get("error", "模型调用失败"),
                event_trace,
            )
        if "building_body" in self.pending:
            error = (
                "建筑主体未能实现，停止附属构件生成：" + self.failures["building_body"]
            )
            return (
                {**updates, "status": "failed", "error": error},
                "aborted",
                [],
                error,
                event_trace,
            )
        return (
            updates,
            ("succeeded" if summary["design_complete"] else "failed"),
            [e["id"] for e in self.fragments],
            f"落实 {summary['implemented']}，舍弃 {summary['abandoned']}",
            event_trace,
        )


def _opening_host_context(state, markers, base, needed):
    """计算门窗实际宿主引用，并把所依赖的墙加入只读上下文。"""
    from app.domain.design.relations import opening_host
    from app.domain.design.relations import place_opening_group
    from app.domain.components.names import resolve_component_name

    opening_hosts = {}
    for marker in markers.values():
        family = resolve_component_name(marker["type"])["entity_type"]
        wall = (
            opening_host(base, marker, diagram_hosts=state.get("drawing_hosts", []))
            if family in {"door", "window"}
            else None
        )
        size = marker["design"].get("size") or {}
        if (
            wall
            and all(size.get(k) for k in ("width", "height"))
            and (
                wall["id"] != marker.get("entity", {}).get("parentWall")
                or (
                    family in {"door", "window"}
                    and marker["design"].get("host")
                    != marker.get("entity", {}).get("parentWall")
                )
            )
        ):
            probe = {
                "id": marker["id"],
                "type": family,
                "parentWall": wall["id"],
                "from": [0, 0, 0],
                **size,
            }
            placed, _ = place_opening_group(
                base, {"geometry": {"components": [probe]}}, marker
            )
            placed_components = (placed.get("geometry") or {}).get("components") or []
            if placed_components and all(
                key in placed_components[0] for key in ("parentWall", "from")
            ):
                opening_hosts[marker["id"]] = {
                    key: placed_components[0][key] for key in ("parentWall", "from")
                }
            needed.add(wall["id"])
    return opening_hosts


def _expand_context_dependencies(entities, needed):
    """沿实体父级关系展开当前任务需要引用的实体集合。"""
    while True:
        previous = set(needed)
        for entity in entities:
            parents = {
                v
                for k, v in entity.items()
                if k.startswith("parent") and isinstance(v, str)
            }
            if entity["id"] in needed:
                needed.update(parents)
            elif parents & needed:
                needed.add(entity["id"])
        if needed == previous:
            break


def _attachment_context(base, markers, records):
    """按实际阳台几何计算栏杆依附关系。"""
    from app.domain.design.relations import balcony_geometry
    from app.domain.components.names import resolve_component_name

    context = {}
    footprints = (
        balcony_geometry(base)
        if any(
            resolve_component_name(m["type"])["entity_type"] == "railing"
            for m in markers.values()
        )
        else {}
    )
    context["attachment_geometry"] = {}
    for marker in markers.values():
        if resolve_component_name(marker["type"])["entity_type"] != "railing":
            continue
        parents = (records.get(marker.get("host")) or {}).get("entity_ids", [])
        if len([i for i in parents if i in footprints]) == 1:
            parent_id = next(i for i in parents if i in footprints)
            context["attachment_geometry"][marker["id"]] = {
                "host_entity_id": parent_id,
                **footprints[parent_id],
            }
    return context["attachment_geometry"]


def _marker_assembly_bounds(markers):
    """从图纸中心与显式尺寸计算整组构造的世界边界。"""
    context = {}
    context["assembly_bounds"] = {}
    for marker_id, marker in markers.items():
        design = marker.get("design") or {}
        position = (design.get("placement") or {}).get("position")
        size = design.get("size") or {}
        if position and all(size.get(k) for k in ("width", "height", "depth")):
            extent = [size[k] for k in ("width", "height", "depth")]
            context["assembly_bounds"][marker_id] = {
                "min": [p - s / 2 for p, s in zip(position, extent)],
                "max": [p + s / 2 for p, s in zip(position, extent)],
            }
    return context["assembly_bounds"]
