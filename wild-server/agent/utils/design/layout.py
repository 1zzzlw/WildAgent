"""设计平面的通行检查：共用真实轮廓与宿主坐标，不重新划矩形网格。"""

from collections import deque

from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import substring, unary_union

from agent.utils.components.names import resolve_component_name
from agent.utils.design.relations import opening_target
from agent.utils.design.spatial import (
    TOPOLOGY_GRID,
    host_path,
    polygons,
    resolve_geometry,
)


def _room_shape(room):
    pieces = room.get("polygons")
    if pieces:
        return unary_union(
            [Polygon(piece["outer"], piece.get("holes", [])) for piece in pieces]
        )
    bounds = room.get("bounds") or {}
    if all(key in bounds for key in ("x", "z", "width", "depth")):
        return box(
            bounds["x"],
            bounds["z"],
            bounds["x"] + bounds["width"],
            bounds["z"] + bounds["depth"],
        )
    return None


def floor_circulation_checks(design, markers, frames):
    """扣除实际墙体及留洞，使用真实门洞和楼梯连接检查各处可行走区域。"""
    facts = design.get("geometry_context") or resolve_geometry(design)
    errors, reviews = [], []
    graph, entrances, nodes = {}, set(), {}
    rooms = []
    level_by_id = {level["id"]: level for level in facts["levels"]}
    lowest = min((level["base_y"] for level in facts["levels"]), default=0)
    uncertain_floors = set()
    for level in facts["levels"]:
        index, y = level["index"], level["base_y"]
        pieces = [
            Polygon(slab["outer"], slab.get("holes", []))
            for slab in facts["slabs"]
            if abs(slab["top_y"] - y) < 0.001
        ]
        if not pieces:
            reviews.append(
                {
                    "marker_id": level["id"],
                    "path": "/decisions/slabs",
                    "reason": "此标高没有明确可行走楼板，不能把体量包围盒当作地面",
                }
            )
            continue
        region = set_precision(unary_union(pieces), TOPOLOGY_GRID)
        barriers, entries = [], []
        if abs(y - lowest) < 0.001:
            for boundary in facts.get("open_boundaries", []):
                if boundary["level"] == level["id"]:
                    path = LineString(boundary["path"])
                    entries.append(
                        substring(path, boundary["start"], boundary["end"]).buffer(0.02)
                    )
        for host in frames.values():
            if not host["from"][1] - 0.001 <= y < host["to"][1] - 0.001:
                continue
            path = LineString(host_path(host, y))
            spans = host.get("solid_intervals", [[0, path.length]])
            barrier = unary_union(
                [
                    substring(path, start, end).buffer(
                        host.get("thickness", 0.15) / 2, cap_style="flat"
                    )
                    for start, end in spans
                ]
            )
            for marker in markers:
                if marker.get("host") != host["id"]:
                    continue
                family = resolve_component_name(marker["type"])["entity_type"]
                if family != "door" and marker["type"] != "opening":
                    continue
                size = marker["design"].get("size") or {}
                width, height = size.get("width"), size.get("height")
                target = opening_target(marker, host, width or 0, height or 0)
                if target is None:
                    uncertain_floors.add(index)
                    continue
                if target[1] > y + 0.25 or (height and target[1] + height <= y):
                    continue
                if not width or not height:
                    uncertain_floors.add(index)
                    reviews.append(
                        {
                            "marker_id": marker["id"],
                            "path": marker.get("design_path", "/components"),
                            "reason": "通行开口尺寸尚未确定，当前只能检查可能连通",
                        }
                    )
                    cut = path
                else:
                    cut = substring(
                        path, max(0, target[0]), min(path.length, target[0] + width)
                    )
                barrier = barrier.difference(
                    cut.buffer(host.get("thickness", 0.15) + 0.01, cap_style="square")
                )
                if (
                    abs(y - lowest) < 0.001
                    and host.get("role") == "exterior"
                    and cut.distance(region.boundary) < 0.001
                ):
                    entries.append(cut.buffer(0.02))
            barriers.append(barrier)
        walkable = region.difference(unary_union(barriers)) if barriers else region
        current_nodes = []
        for number, shape in enumerate(
            polygons(set_precision(walkable, TOPOLOGY_GRID))
        ):
            if shape.area <= 1e-8:
                continue
            key = (index, number)
            graph[key], nodes[key] = set(), shape
            current_nodes.append(key)
            if any(shape.intersects(entry) for entry in entries):
                entrances.add(key)
        for layout_index, layout in enumerate(design.get("floor_layouts", [])):
            if layout.get("floor") != index:
                continue
            for number, room in enumerate(layout.get("rooms", [])):
                if room.get("void"):
                    continue
                shape = _room_shape(room)
                if shape is not None:
                    rooms.append(
                        (index, layout_index, number, room, shape, current_nodes)
                    )
    for marker in markers:
        if resolve_component_name(marker["type"])["entity_type"] != "stair":
            continue
        position = (marker.get("entity") or {}).get("position") or (
            marker["design"].get("placement") or {}
        ).get("position")
        size = marker["design"].get("size") or {}
        targets = marker.get("floor_connections") or []
        if (
            not position
            or not size.get("width")
            or not size.get("depth")
            or not targets
        ):
            reviews.append(
                {
                    "marker_id": marker["id"],
                    "path": marker.get("design_path", "/components"),
                    "reason": "楼梯占地或连接尚未确定，须复核上下口；不能凭文字证明实际可达",
                }
            )
            uncertain_floors.update(level["index"] for level in facts["levels"])
            continue
        footprint = box(
            position[0] - size["width"] / 2,
            position[2] - size["depth"] / 2,
            position[0] + size["width"] / 2,
            position[2] + size["depth"] / 2,
        )
        if marker.get("footprint_geometry"):
            shape = marker["footprint_geometry"]
            footprint = Polygon(shape["outer"], shape.get("holes", []))
        for number, target in enumerate(targets):
            floor_ids = []
            for key in ("from_floor", "to_floor"):
                value = target[key]
                floor_ids.append(
                    level_by_id[value]["index"] if value in level_by_id else value
                )
            portal = ("stair", marker["id"], number)
            graph[portal] = set()
            form = marker["design"].get("form") or {}
            for key, shape in nodes.items():
                if key[0] not in floor_ids:
                    continue
                anchor = form.get(
                    "lower_entry" if key[0] == floor_ids[0] else "upper_exit"
                )
                if anchor:
                    connected = shape.distance(Point(anchor[0], anchor[2])) <= 0.001
                else:
                    connected = shape.intersection(footprint.buffer(0.001)).area > 1e-8
                if connected:
                    graph[portal].add(key)
                    graph[key].add(portal)
    if not entrances:
        for level in facts["levels"]:
            reviews.append(
                {
                    "marker_id": f"floor_{level['index']}",
                    "path": "/decisions/floor_layouts",
                    "reason": "没有可确认的室外入口，房间可达性尚待复核",
                }
            )
        reviews.append(
            {
                "marker_id": "circulation",
                "path": "/decisions/components",
                "reason": "没有可确认的地面室外入口，尚不能判定整栋从室外可达",
            }
        )
        return errors, reviews
    reached, queue = set(entrances), deque(entrances)
    while queue:
        for neighbor in graph[queue.popleft()]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    for floor, layout_index, number, room, shape, keys in rooms:
        if floor in uncertain_floors:
            continue
        unreachable = [
            nodes[key].intersection(shape) for key in keys if key not in reached
        ]
        area = sum(piece.area for piece in unreachable)
        if area > 0.001:
            walls_path = (
                f"/decisions/floor_layouts/{layout_index}/walls"
                if not design.get("levels")
                else "/decisions/walls"
            )
            errors.append(
                {
                    "code": "room_unreachable",
                    "path": f"/decisions/floor_layouts/{layout_index}/rooms/{number}",
                    "related_paths": [walls_path, "/decisions/components"],
                    "marker_id": room.get("id", f"room_{number}"),
                    "expected": "房间实际可行走区域可经入口、门洞或已选楼梯到达",
                    "actual": {
                        "floor": floor,
                        "room_id": room.get("id"),
                        "unreachable_area": area,
                    },
                    "reason": "实际墙、通行开口和留洞形成封闭区域；请修订通路，不能自动删墙或补楼梯",
                }
            )
    return errors, reviews


def opening_partition_conflicts(markers, frames):
    """用真实墙路径核对内墙接入洞口，支持斜墙和曲线，避免按世界X/Z猜测。"""
    errors = []
    for marker in markers:
        if resolve_component_name(marker["type"])["entity_type"] not in {
            "door",
            "window",
        }:
            continue
        host = marker.get("diagram_host")
        size = marker["design"].get("size") or {}
        if not host:
            continue
        width, height = size.get("width", 0), size.get("height", 0)
        target = opening_target(marker, host, width, height)
        if target is None:
            continue
        path = LineString(
            host.get("path")
            or [[host["from"][0], host["from"][2]], [host["to"][0], host["to"][2]]]
        )
        for partition in frames.values():
            if partition["id"] == host["id"] or partition.get("role") != "interior":
                continue
            if (
                target[1] + height <= partition["from"][1]
                or target[1] >= partition["to"][1]
            ):
                continue
            points = partition.get("path") or [
                [partition["from"][0], partition["from"][2]],
                [partition["to"][0], partition["to"][2]],
            ]
            intersection = path.intersection(LineString(points))
            if intersection.is_empty:
                continue
            contacts = (
                [intersection]
                if isinstance(intersection, Point)
                else list(getattr(intersection, "geoms", []))
            )
            for contact in contacts:
                if not isinstance(contact, Point):
                    continue
                along = path.project(contact)
                centered = (
                    "centerAlong" in (marker.get("entity") or {})
                    and not width
                    and abs(along - target[0]) <= 0.001
                )
                if centered or target[0] + 0.001 < along < target[0] + width - 0.001:
                    errors.append(
                        {
                            "code": "opening_partition_conflict",
                            "path": marker.get("design_path", "/components"),
                            "marker_id": marker["id"],
                            "actual": {
                                "host": host["id"],
                                "partition": partition["id"],
                                "intersection_along": along,
                            },
                            "expected": "内墙在洞口边界交接",
                            "reason": "内墙接入门窗洞口内部，须联合修订实际墙路径或开口位置",
                        }
                    )
    return errors
