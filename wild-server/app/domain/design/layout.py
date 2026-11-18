"""设计平面的保守通行检查；未知几何列为待核对，不猜测户型。"""
from collections import deque
from math import hypot, isfinite

from app.domain.components.names import resolve_component_name
from app.domain.design.coordinates import floor_elevations
from app.domain.design.relations import opening_target


def _bounds(room):
    box = room.get("bounds") or {}
    if not isinstance(box, dict) or not all(
        type(box.get(key)) in (int, float) and isfinite(box[key])
        for key in ("x", "z", "width", "depth")
    ) or box["width"] <= 0 or box["depth"] <= 0:
        return None
    return (box["x"], box["z"], box["x"] + box["width"], box["z"] + box["depth"])


def floor_circulation_checks(design, markers, frames):
    """按墙端、房间边界和洞口分格，检查明确入口/楼梯可达的楼层区域。

    墙视作零厚度障碍，只证明拓扑连通，不代替通行净宽或建筑规范检查。
    斜墙不作为阻挡，未知洞口宽度放开整个宿主，楼梯落点使用完整占地；
    这些放宽只会增加可能路径，不会把尚未确定的形态误判为封闭房间。
    """
    errors, reviews = [], []
    levels = floor_elevations(design)
    graph, entry_nodes, floor_records, stair_routes = {}, set(), [], {}
    for layout_index, layout in enumerate(design.get("floor_layouts") or []):
        floor = layout.get("floor")
        if floor not in levels or floor > design["massing"]["floors"]:
            continue
        path = f"/decisions/floor_layouts/{layout_index}"
        rooms, voids = [], []
        for index, room in enumerate(layout.get("rooms") or []):
            box = _bounds(room)
            if box is not None:
                (voids if room.get("void") else rooms).append((index, room, box))
        if not rooms:
            continue
        regions = []
        for volume in design["volumes"]:
            if volume["start_floor"] <= floor <= volume["end_floor"]:
                regions.append((volume["x"], volume["z"], volume["x"] + volume["width"],
                                volume["z"] + volume["depth"]))
        barriers, passages, access, passage_boxes, stair_footprints = [], {}, [], [], {}
        uncertain = []
        for wall in layout.get("walls") or []:
            a, b = wall["from"], wall["to"]
            if abs(a[0] - b[0]) <= 0.001:
                barriers.append((wall["id"], 0, a[0], *sorted((a[1], b[1]))))
            elif abs(a[1] - b[1]) <= 0.001:
                barriers.append((wall["id"], 1, a[1], *sorted((a[0], b[0]))))
            else:
                uncertain.append(wall["id"])
        unknown_stair = False
        for marker in markers:
            family = resolve_component_name(marker["type"])["entity_type"]
            wall = frames.get(marker.get("host"))
            size = marker["design"].get("size") or {}
            if (family == "door" or marker["type"] == "opening") and wall and abs(wall["from"][1] - levels[floor]) <= 0.001:
                length = hypot(wall["to"][0] - wall["from"][0], wall["to"][2] - wall["from"][2])
                width = size.get("width")
                target = opening_target(marker, wall, width or length, size.get("height", 0))
                if target is None:
                    uncertain.append(marker["id"])
                    target, width = [0, levels[floor], 0], None
                elif (marker["design"].get("placement") or {}).get("position") and not size.get("height"):
                    target[1] = levels[floor]
                if target[1] > levels[floor] + 0.25 or (size.get("height") and target[1] + size["height"] <= levels[floor]):
                    continue
                if not width or not size.get("height"):
                    uncertain.append(marker["id"])
                low, high = (target[0], target[0] + width) if width else (0, length)
                a, b = wall["from"], wall["to"]
                start = (a[0] + (b[0] - a[0]) * low / length, a[2] + (b[2] - a[2]) * low / length)
                end = (a[0] + (b[0] - a[0]) * high / length, a[2] + (b[2] - a[2]) * high / length)
                box = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
                passage_boxes.append(box)
                if wall.get("facing"):
                    access.append(box)
                else:
                    axis = 1 if abs(a[0] - b[0]) <= 0.001 else 0
                    passages.setdefault(wall["id"], []).append((box[axis], box[axis + 2]))
            if family != "stair":
                continue
            connections = marker.get("floor_connections") or []
            if connections and not any(floor in (c["from_floor"], c["to_floor"]) for c in connections):
                continue
            position = (marker["design"].get("placement") or {}).get("position")
            if not connections or not position or not size.get("width") or not size.get("depth"):
                unknown_stair = True
                continue
            for index, connection in enumerate(connections):
                if floor not in (connection["from_floor"], connection["to_floor"]):
                    continue
                identifier = (marker["id"], index)
                stair_footprints[identifier] = (position[0] - size["width"] / 2, position[2] - size["depth"] / 2,
                                               position[0] + size["width"] / 2, position[2] + size["depth"] / 2)
                stair_routes[identifier] = {connection["from_floor"], connection["to_floor"]}
        for wall in frames.values():
            if not wall.get("facing") or abs(wall["from"][1] - levels[floor]) > 0.001:
                continue
            a, b = wall["from"], wall["to"]
            length = hypot(b[0] - a[0], b[2] - a[2])
            for low, high in wall.get("open_intervals", []):
                p = (a[0] + (b[0] - a[0]) * low / length, a[2] + (b[2] - a[2]) * low / length)
                q = (a[0] + (b[0] - a[0]) * high / length, a[2] + (b[2] - a[2]) * high / length)
                access.append((min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1])))
        review = {"marker_id": f"floor_{floor}", "path": path,
                  "reason": "楼层通行仅检查已知范围；未确定的入口、楼梯落点、斜墙或洞口尺寸需在实现后复核",
                  "actual": {"uncertain_geometry": uncertain, "unknown_stair": unknown_stair}}
        if uncertain or unknown_stair or not (access or stair_footprints):
            reviews.append(review)
        if unknown_stair or not (access or stair_footprints):
            continue
        boxes = regions + [box for _, _, box in rooms + voids] + access + passage_boxes + list(stair_footprints.values())
        xs, zs = set(), set()
        for x0, z0, x1, z1 in boxes:
            xs.update((x0, x1))
            zs.update((z0, z1))
        for wall in layout.get("walls") or []:
            for point in (wall["from"], wall["to"]):
                xs.add(point[0])
                zs.add(point[1])
        xs, zs = sorted(xs), sorted(zs)
        if len(xs) * len(zs) > 100000:
            reviews.append({**review, "reason": "平面分格过多，通行检查尚未完成，须复核实际动线"})
            continue
        cells = {}
        for i in range(len(xs) - 1):
            for j in range(len(zs) - 1):
                x, z = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
                if xs[i + 1] - xs[i] <= 0.001 or zs[j + 1] - zs[j] <= 0.001:
                    continue
                if not any(x0 < x < x1 and z0 < z < z1 for x0, z0, x1, z1 in regions):
                    continue
                if any(x0 < x < x1 and z0 < z < z1 for _, _, (x0, z0, x1, z1) in voids):
                    continue
                cells[i, j] = (x, z)
                node = (floor, i, j)
                graph[node] = set()
                for x0, z0, x1, z1 in access:
                    hit_x = xs[i] <= x0 <= xs[i + 1] if x0 == x1 else xs[i] < x1 and xs[i + 1] > x0
                    hit_z = zs[j] <= z0 <= zs[j + 1] if z0 == z1 else zs[j] < z1 and zs[j + 1] > z0
                    if hit_x and hit_z:
                        # 体量之间的共用立面不是室外入口。
                        sides = ((x0 - 0.0001, z), (x0 + 0.0001, z)) if x0 == x1 else ((x, z0 - 0.0001), (x, z0 + 0.0001))
                        inside = [any(left < px < right and front < pz < back for left, front, right, back in regions)
                                  for px, pz in sides]
                        if inside[0] != inside[1]:
                            entry_nodes.add(node)
                for identifier, (x0, z0, x1, z1) in stair_footprints.items():
                    if xs[i] < x1 and xs[i + 1] > x0 and zs[j] < z1 and zs[j + 1] > z0:
                        portal = ("stair", identifier)
                        graph[node].add(portal)
                        graph.setdefault(portal, set()).add(node)
        for i, j in cells:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (i + di, j + dj)
                if neighbor not in cells:
                    continue
                axis = 0 if di else 1
                plane = xs[max(i, i + di)] if di else zs[max(j, j + dj)]
                along = cells[i, j][1 - axis]
                blocked = False
                for identifier, wall_axis, wall_plane, low, high in barriers:
                    if wall_axis == axis and abs(wall_plane - plane) <= 0.001 and low < along < high:
                        if not any(start < along < end for start, end in passages.get(identifier, [])):
                            blocked = True
                            break
                if not blocked:
                    graph[floor, i, j].add((floor, *neighbor))
        floor_records.append((floor, path, rooms, cells, [wall[0] for wall in barriers]))
    analyzed_floors = {record[0] for record in floor_records}
    for identifier, route in stair_routes.items():
        portal = ("stair", identifier)
        if portal in graph and route - analyzed_floors:
            # 未提供平面的连接层可能另有入口；不能据缺失平面断言下层不可达。
            entry_nodes.add(portal)
            reviews.append({"marker_id": identifier[0], "path": "/decisions/floor_layouts",
                            "actual": {"unreviewed_floors": sorted(route - analyzed_floors, key=str)},
                            "reason": "楼梯连接涉及未完成通行分析的楼层，当前只证明可能连通，仍需补齐平面或复核实际动线"})
    if not entry_nodes:
        if floor_records:
            reviews.append({"marker_id": "circulation", "path": "/decisions/components",
                            "reason": "图纸尚未声明可解析的室外入口，不能确定房间从室外可达；须补齐入口或复核实际动线"})
        return errors, reviews
    reached = set(entry_nodes)
    queue = deque(entry_nodes)
    while queue:
        for neighbor in graph[queue.popleft()]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    for floor, path, rooms, cells, partition_ids in floor_records:
        for index, room, (x0, z0, x1, z1) in rooms:
            unreachable = [cell for cell, (x, z) in cells.items()
                           if x0 < x < x1 and z0 < z < z1 and (floor, *cell) not in reached]
            if unreachable:
                errors.append({"code": "room_unreachable", "path": f"{path}/rooms/{index}",
                               "marker_id": room.get("id", f"room_{index}"),
                               "expected": "房间全部已知楼面区域可通过入口、通行开口或楼梯到达",
                               "actual": {"floor": floor, "room_id": room.get("id"), "bounds": room["bounds"],
                                          "unreachable_regions": len(unreachable), "partition_ids": partition_ids},
                               "related_paths": [path + "/walls", "/decisions/components"],
                               "reason": "房间被已声明内墙隔断，门窗、墙端缺口与楼梯占地均已纳入检查；"
                                         "显式修订通行开口、墙段或空间布局，不能靠另一个房间有门判定本房间可达"})
    return errors, reviews


def opening_partition_conflicts(markers, frames):
    """核对实际宿主方向；内墙不能接到门窗洞口内部。"""
    errors = []
    partitions = [wall for wall in frames.values()
                  if wall.get("design_path", "").startswith("/decisions/floor_layouts/")]
    for marker in markers:
        if resolve_component_name(marker["type"])["entity_type"] not in {"door", "window"}:
            continue
        wall = marker.get("diagram_host")
        if not wall:
            continue
        size = marker["design"].get("size") or {}
        width, height = size.get("width"), size.get("height")
        target = opening_target(marker, wall, width or 0, height or 0)
        if target is None:
            continue
        a, b = wall["from"], wall["to"]
        length = hypot(b[0] - a[0], b[2] - a[2])
        ux, uz = (b[0] - a[0]) / length, (b[2] - a[2]) / length
        for partition in partitions:
            if partition["id"] == wall["id"]:
                continue
            p, q = partition["from"], partition["to"]
            if min(b[1], q[1]) - max(a[1], p[1]) <= 0.001:
                continue
            if height and (target[1] + height <= p[1] or target[1] >= q[1]):
                continue
            np = -(p[0] - a[0]) * uz + (p[2] - a[2]) * ux
            nq = -(q[0] - a[0]) * uz + (q[2] - a[2]) * ux
            if abs(np - nq) <= 0.001 or min(np, nq) > 0.001 or max(np, nq) < -0.001:
                continue
            ratio = np / (np - nq)
            along = (p[0] + ratio * (q[0] - p[0]) - a[0]) * ux + (p[2] + ratio * (q[2] - p[2]) - a[2]) * uz
            if width:
                inside = target[0] + 0.001 < along < target[0] + width - 0.001
            else:
                centered = marker["entity"].get("position") or "centerAlong" in marker["entity"]
                inside = bool(centered) and abs(along - target[0]) <= 0.001
            if inside:
                errors.append({"code": "opening_partition_conflict", "path": marker["design_path"],
                               "marker_id": marker["id"], "expected": "内墙与洞口边界交接，不能接入洞口内部",
                               "actual": {"host": wall["id"], "partition": partition["id"], "intersection_along": along,
                                          "opening_along": [target[0], target[0] + width] if width else "中心与内墙交点重合，宽度待实现"},
                               "related_paths": [partition["design_path"]],
                               "reason": "内墙接入门窗洞口内部；联合修订门窗位置/分格或内墙位置，保留未受影响的设计"})
    return errors
