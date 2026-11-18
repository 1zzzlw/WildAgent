"""把历史矩形字段展开为同一空间协议；不改变文档版本或原稿坐标。"""

from copy import deepcopy

from app.domain.design.openings import is_open_side
from app.domain.design.spatial import has_spatial_geometry


def spatial_input(design: dict) -> dict:
    """仅运行时转换历史输入；新图纸直接使用其声明，禁止用矩形补齐未知形态。"""
    if has_spatial_geometry(design):
        return deepcopy(design)
    from app.domain.design.coordinates import (
        floor_elevations,
        representative_floor_indices,
    )
    from app.domain.design.contracts import MassingDecision

    data = deepcopy(design)
    massing = MassingDecision.model_validate(data["massing"])
    indices = representative_floor_indices(massing)
    heights = floor_elevations(data)
    data["levels"] = []
    for slot, index in enumerate(indices, 1):
        data["levels"].append(
            {
                "id": f"L{slot}",
                "kind": "storey",
                "index": slot,
                "elevation": heights[index],
            }
        )
    data["levels"].append(
        {"id": "RF", "kind": "roof", "elevation": heights[indices[-1] + 1]}
    )
    data["profiles"], data["walls"], data["slabs"], data["voids"], data["roofs"] = (
        [],
        [],
        [],
        [],
        [],
    )
    data["systems"] = {
        "legacy_exterior_wall": {
            "kind": "wall",
            "thickness": 0.24,
            "material_role": "facade_primary",
        },
        "legacy_slab": {"kind": "slab", "thickness": 0.2, "material_role": "floor"},
    }
    components = data.get("components", [])
    for component in components:
        placement = component.get("placement") or {}
        if placement.get("position"):
            placement.setdefault("mode", "world")
            placement.setdefault("anchor", "center")
        elif component.get("host"):
            placement.setdefault("mode", "wall")
            placement.setdefault(
                "anchor",
                "opening_start_bottom"
                if component["type"] in {"door", "window"}
                else "center",
            )
        component["placement"] = placement
    declared = deepcopy(data["volumes"])
    data["volumes"] = []
    for volume in declared:
        identity = volume["id"]
        profile_id = f"profile_{identity}"
        data["profiles"].append(
            {
                "id": profile_id,
                "type": "rectangle",
                "width": volume["width"],
                "depth": volume["depth"],
                "holes": [],
            }
        )
        top_id = (
            f"L{volume['end_floor'] + 1}"
            if volume["end_floor"] < len(indices)
            else "RF"
        )
        data["volumes"].append(
            {
                "id": identity,
                "role": volume.get("role", "primary"),
                "placement": {
                    "origin_xz": [
                        volume["x"] + volume["width"] / 2,
                        volume["z"] + volume["depth"] / 2,
                    ],
                    "yaw": 0,
                },
                "geometry": {
                    "type": "extrusion",
                    "profile": profile_id,
                    "bottom": {"level": f"L{volume['start_floor']}", "offset": 0},
                    "top": {"level": top_id, "offset": 0},
                },
            }
        )
        for slot in range(volume["start_floor"], volume["end_floor"] + 1):
            level_id = f"L{slot}"
            upper = f"L{slot + 1}" if slot < len(indices) else "RF"
            for face, facade in {
                **data.get("facades", {}),
                **volume.get("facades", {}),
            }.items():
                pattern = (
                    facade["ground_pattern"] if slot == 1 else facade["upper_pattern"]
                )
                from app.domain.design.spatial import profile_edges, transform_points

                outline = profile_edges(
                    {
                        "type": "rectangle",
                        "width": volume["width"],
                        "depth": volume["depth"],
                    }
                )[face]
                path = transform_points(
                    outline,
                    [
                        volume["x"] + volume["width"] / 2,
                        volume["z"] + volume["depth"] / 2,
                    ],
                )
                length = (
                    volume["width"] if face in {"front", "back"} else volume["depth"]
                )
                solid_intervals = []
                for bay, token in enumerate(pattern):
                    start, end = (
                        bay * length / facade["bays"],
                        (bay + 1) * length / facade["bays"],
                    )
                    if is_open_side([token]):
                        data.setdefault("_open_boundaries", []).append(
                            {
                                "path": path,
                                "start": start,
                                "end": end,
                                "level": level_id,
                            }
                        )
                    elif solid_intervals and abs(solid_intervals[-1][1] - start) < 1e-8:
                        solid_intervals[-1][1] = end
                    else:
                        solid_intervals.append([start, end])
                if is_open_side(pattern):
                    continue
                wall_id = f"wall_{identity}_{face}_L{slot}"
                data["walls"].append(
                    {
                        "id": wall_id,
                        "role": "exterior",
                        "system": "legacy_exterior_wall",
                        "_solid_intervals": solid_intervals,
                        "geometry": {
                            "type": "volume_boundary",
                            "volume": identity,
                            "edge": face,
                            "bottom": {"level": level_id, "offset": 0},
                            "top": {"level": upper, "offset": -0.2},
                        },
                    }
                )
                _expand_facade(
                    data,
                    components,
                    declared,
                    volume,
                    face,
                    facade,
                    pattern,
                    slot,
                    wall_id,
                )
    for layout_index, layout in enumerate(data.get("floor_layouts", [])):
        slot = indices.index(layout["floor"]) + 1
        level_id = f"L{slot}"
        upper = f"L{slot + 1}" if slot < len(indices) else "RF"
        for wall in layout.get("walls", []):
            system_id = f"system_{wall['id']}"
            data["systems"][system_id] = {
                "kind": "wall",
                "thickness": wall["thickness"],
                "material_role": "facade_primary",
            }
            data["walls"].append(
                {
                    "id": wall["id"],
                    "role": "interior",
                    "system": system_id,
                    "geometry": {
                        "type": "path",
                        "frame": "world",
                        "segments": [
                            {
                                "id": "path",
                                "type": "line",
                                "from": wall["from"],
                                "to": wall["to"],
                            }
                        ],
                        "bottom": {"level": level_id, "offset": 0},
                        "top": {"level": upper, "offset": -0.2},
                    },
                }
            )
        for room in layout.get("rooms", []):
            if room.get("void") is not True:
                continue
            bounds = room["bounds"]
            profile_id = f"profile_void_{layout_index}_{room['id']}"
            data["profiles"].append(
                {
                    "id": profile_id,
                    "type": "rectangle",
                    "width": bounds["width"],
                    "depth": bounds["depth"],
                    "holes": [],
                }
            )
            data["voids"].append(
                {
                    "id": f"void_{layout_index}_{room['id']}",
                    "purpose": "opening",
                    "level": level_id,
                    "region": {
                        "type": "profile_region",
                        "profile": profile_id,
                        "frame": "world",
                        "origin_xz": [
                            bounds["x"] + bounds["width"] / 2,
                            bounds["z"] + bounds["depth"] / 2,
                        ],
                        "yaw": 0,
                    },
                }
            )
    for slot in range(1, len(indices) + 1):
        volume_ids = [
            v["id"] for v in declared if v["start_floor"] <= slot <= v["end_floor"]
        ]
        data["slabs"].append(
            {
                "id": f"slab_L{slot}",
                "system": "legacy_slab",
                "top": {"level": f"L{slot}", "offset": 0},
                "region": {
                    "type": "volume_union_section",
                    "volumes": volume_ids,
                    "level": f"L{slot}",
                },
                "holes": [
                    void["id"] for void in data["voids"] if void["level"] == f"L{slot}"
                ],
            }
        )
    for component in components:
        host = component.get("host")
        placement = component.get("placement") or {}
        from app.domain.components.names import resolve_component_name

        if (
            host
            and any(v["id"] == host for v in declared)
            and resolve_component_name(component["type"])["entity_type"]
            in {"door", "window"}
        ):
            if placement.get("face") and placement.get("floor"):
                component["host"] = (
                    f"wall_{host}_{placement['face']}_L{placement['floor']}"
                )
    roof = data.get("roof") or {"type": "none"}
    for volume in declared:
        if any(
            c["type"] == "roof" and c.get("host") == volume["id"] for c in components
        ):
            continue
        override = next(
            (
                item
                for item in roof.get("volumes", [])
                if item["volume"] == volume["id"]
            ),
            {},
        )
        kind = override.get("type") or roof["type"]
        if kind in {"none", "open"}:
            continue
        support_id = (
            f"L{volume['end_floor'] + 1}"
            if volume["end_floor"] < len(indices)
            else "RF"
        )
        data["roofs"].append(
            {
                "id": f"roof_{volume['id']}",
                "host": volume["id"],
                "support": {"level": support_id, "offset": 0},
                "geometry": {
                    "type": kind,
                    "outline": {"type": "host_section", "level": support_id},
                    "overhang": override.get("overhang", roof.get("overhang", 0)),
                    "ridge_axis": roof.get("ridge_axis", "x"),
                },
                "material_role": "roof",
            }
        )
    data["components"] = components
    data["_legacy_source"] = deepcopy(design)
    return data


def _expand_facade(
    data, components, volumes, volume, face, facade, pattern, floor, wall_id
):
    """历史pattern仅在此展开一次；明确实例覆盖所在开间，内部接合面不加外窗。"""
    from app.domain.components.names import resolve_component_name

    length = volume["width"] if face in {"front", "back"} else volume["depth"]
    for bay, token in enumerate(pattern, 1):
        kind, _, form = token.partition(":")
        if kind in {"empty", "open", "none", "no_opening", "无开口", "留白"}:
            continue
        center = (bay - 0.5) * length / facade["bays"]
        intervals = _exterior_facade_intervals(volume, face, floor, volumes)
        if not any(a <= center <= b for a, b in intervals):
            continue
        family = resolve_component_name(kind)["entity_type"]
        covered = False
        for component in components:
            placement = component.get("placement") or {}
            matching = component.get("host") == wall_id or (
                component.get("host") == volume["id"]
                and placement.get("face") == face
                and placement.get("floor") == floor
            )
            if (
                not matching
                or resolve_component_name(component["type"])["entity_type"] != family
            ):
                continue
            width = (component.get("size") or {}).get("width")
            if (
                width
                and "offset" in placement
                and placement["offset"] <= center <= placement["offset"] + width
            ):
                covered = True
            elif not placement.get("position") and "offset" not in placement:
                covered = True
        if covered:
            continue
        data.setdefault("_automatic_openings", []).append(
            {
                "id": f"{kind}_{volume['id']}_{face}_L{floor}_{bay}",
                "type": kind,
                "host": wall_id,
                "placement": {
                    "mode": "wall",
                    "anchor": "opening_center_bottom",
                    "offset": center,
                    "sill_height": 1 if family == "window" else 0,
                },
                "size": {},
                "form": {"description": form},
                "_automatic": True,
            }
        )


def _exterior_facade_intervals(volume, face, floor, volumes):
    """自动立面使用的外露墙段；同向共面区域只分配给一个体量。"""
    from types import SimpleNamespace

    volume = SimpleNamespace(**volume) if isinstance(volume, dict) else volume
    volumes = [
        SimpleNamespace(**item) if isinstance(item, dict) else item for item in volumes
    ]
    axis = "x" if face in {"front", "back"} else "z"
    extent = "width" if axis == "x" else "depth"
    normal, normal_extent = ("z", "depth") if axis == "x" else ("x", "width")
    positive = face in {"right", "back"}
    plane = getattr(volume, normal) + (
        getattr(volume, normal_extent) if positive else 0
    )
    origin, length = getattr(volume, axis), getattr(volume, extent)
    segments = [(0.0, length)]
    for other in volumes:
        if other.id == volume.id or not other.start_floor <= floor <= other.end_floor:
            continue
        low, high = (
            getattr(other, normal),
            getattr(other, normal) + getattr(other, normal_extent),
        )
        inside = (
            low <= plane + 0.001 and high > plane + 0.001
            if positive
            else low < plane - 0.001 and high >= plane - 0.001
        )
        shared = plane == (high if positive else low)
        owner = (-getattr(other, extent), other.id) < (-length, volume.id)
        if not inside and not (shared and owner):
            continue
        start = max(0.0, getattr(other, axis) - origin)
        end = min(length, getattr(other, axis) + getattr(other, extent) - origin)
        if face in {"back", "left"}:
            start, end = length - end, length - start
        if end <= start:
            continue
        updated_segments = []
        for left, right in segments:
            for segment_start, segment_end in (
                (left, min(right, start)),
                (max(left, end), right),
            ):
                if segment_end - segment_start > 0.001:
                    updated_segments.append((segment_start, segment_end))
        segments = updated_segments
    return segments
