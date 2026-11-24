"""图纸共享几何事实：轮廓、截面、标高、宿主坐标，不调用模型。"""

from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
from math import acos, ceil, cos, hypot, pi, sin

from shapely import affinity, set_precision
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.ops import unary_union
from shapely.validation import explain_validity


CHORD_ERROR = 0.00025  # 轮廓离散弦高上限，米；不能借此放宽设计尺寸约束。
GEOMETRY_EPSILON = 1e-7
TOPOLOGY_GRID = 1e-8  # 纳米级归一只消除运算噪声，不改变毫米级设计尺寸。


def has_spatial_geometry(design: dict) -> bool:
    return any(volume.get("geometry") for volume in design.get("volumes", []))


def issue(path: str, reason: str, **facts):
    from agent.utils.design.coordinates import DesignCoordinateConflict

    raise DesignCoordinateConflict(
        [{"code": "design_spatial_contract", "path": path, "reason": reason, **facts}]
    )


def index_by_id(values: list[dict], path: str) -> dict[str, dict]:
    result = {}
    for number, value in enumerate(values):
        identity = value.get("id")
        if not identity or identity in result:
            issue(f"{path}/{number}/id", "ID必须非空且唯一", actual=identity)
        result[identity] = value
    return result


def require(values: dict, identity: str, path: str):
    if identity not in values:
        issue(path, "引用目标未声明", expected="本次图纸中的稳定ID", actual=identity)
    return values[identity]


def elevation(reference: dict, levels: dict[str, dict], path: str = "/levels") -> float:
    level = require(levels, reference.get("level"), path)
    return level["elevation"] + reference.get("offset", 0)


def transform_points(points, origin=(0, 0), yaw=0, scale=(1, 1)) -> list[list[float]]:
    """局部缩放→绕+Y右手旋转→平移；二维点使用[X,Z]。"""
    c, s = cos(yaw), sin(yaw)
    result = []
    for x, z in points:
        x, z = x * scale[0], z * scale[1]
        result.append([origin[0] + c * x + s * z, origin[1] - s * x + c * z])
    return result


def _arc_steps(radius: float, angle: float) -> int:
    step = 2 * acos(max(-1, min(1, 1 - CHORD_ERROR / max(radius, CHORD_ERROR))))
    return max(2, min(8192, ceil(abs(angle) / max(step, 1e-5))))


def segment_points(segment: dict) -> list[list[float]]:
    kind = segment["type"]
    if kind == "line":
        return [list(segment["from"]), list(segment["to"])]
    if kind == "arc":
        angle = segment["sweep_angle"]
        if abs(angle) < GEOMETRY_EPSILON or abs(angle) > 2 * pi + GEOMETRY_EPSILON:
            issue(
                "/profiles/segments/sweep_angle",
                "圆弧扫角必须非零且不超过2π",
                actual=angle,
            )
        count = _arc_steps(segment["radius"], angle)
        result = []
        for index in range(count + 1):
            a = segment["start_angle"] + angle * index / count
            result.append(
                [
                    segment["center"][0] + segment["radius"] * cos(a),
                    segment["center"][1] - segment["radius"] * sin(a),
                ]
            )
        return result
    if kind != "cubic_bezier":
        issue("/profiles/segments/type", "不支持的曲线类型", actual=kind)
    output = [list(segment["points"][0])]

    def subdivide(points, depth=0):
        a, b, c, d = points
        chord = LineString([a, d]) if a != d else Point(a)
        error = max(chord.distance(Point(b)), chord.distance(Point(c)))
        if error <= CHORD_ERROR or depth >= 20:
            output.append(list(d))
            return
        ab = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
        bc = [(b[0] + c[0]) / 2, (b[1] + c[1]) / 2]
        cd = [(c[0] + d[0]) / 2, (c[1] + d[1]) / 2]
        abc = [(ab[0] + bc[0]) / 2, (ab[1] + bc[1]) / 2]
        bcd = [(bc[0] + cd[0]) / 2, (bc[1] + cd[1]) / 2]
        middle = [(abc[0] + bcd[0]) / 2, (abc[1] + bcd[1]) / 2]
        subdivide([a, ab, abc, middle], depth + 1)
        subdivide([middle, bcd, cd, d], depth + 1)

    subdivide(segment["points"])
    return output


def profile_edges(profile: dict) -> dict[str, list[list[float]]]:
    """稳定边名只来自设计；内部离散点数量变化不改变宿主身份。"""
    kind = profile["type"]
    if kind == "rectangle":
        x, z = profile["width"] / 2, profile["depth"] / 2
        return {
            "front": [[-x, -z], [x, -z]],
            "right": [[x, -z], [x, z]],
            "back": [[x, z], [-x, z]],
            "left": [[-x, z], [-x, -z]],
        }
    if kind in {"circle", "ellipse"}:
        rx = profile.get("radius", profile.get("radius_x"))
        rz = profile.get("radius", profile.get("radius_z"))
        count = 4 * ceil(max(32, _arc_steps(max(rx, rz), 2 * pi)) / 4)
        points = []
        for index in range(count + 1):
            angle = profile.get("seam_angle", 0) + 2 * pi * index / count
            points.append([rx * cos(angle), -rz * sin(angle)])
        points[-1] = points[0][:]
        return {"perimeter": points}
    if kind == "polygon":
        vertices = index_by_id(profile["vertices"], "/profiles/vertices")
        edges = {}
        for edge in profile["edges"]:
            if edge["id"] in edges:
                issue("/profiles/edges", "轮廓边ID重复", actual=edge["id"])
            edges[edge["id"]] = [
                require(vertices, edge["from"], "/profiles/edges/from")["point"],
                require(vertices, edge["to"], "/profiles/edges/to")["point"],
            ]
        return edges
    return {segment["id"]: segment_points(segment) for segment in profile["segments"]}


def join_edges(edges: dict, path: str) -> list[list[float]]:
    result = []
    for points in edges.values():
        if (
            result
            and hypot(result[-1][0] - points[0][0], result[-1][1] - points[0][1])
            > GEOMETRY_EPSILON
        ):
            issue(path, "轮廓相邻边必须首尾衔接", expected=result[-1], actual=points[0])
        result.extend(points if not result else points[1:])
    if (
        not result
        or hypot(result[0][0] - result[-1][0], result[0][1] - result[-1][1])
        > GEOMETRY_EPSILON
    ):
        issue(path, "轮廓必须闭合")
    return result[:-1]


def profile_polygon(identity: str, profiles: dict, seen=()) -> Polygon:
    profile = require(profiles, identity, "/profiles")
    if identity in seen:
        issue("/profiles/holes", "轮廓孔洞存在循环引用", actual=[*seen, identity])
    outer = join_edges(profile_edges(profile), f"/profiles/{identity}")
    holes = []
    hole_polygons = []
    outer_polygon = Polygon(outer)
    for hole_id in profile.get("holes", []):
        hole = profile_polygon(hole_id, profiles, (*seen, identity))
        if hole.interiors:
            issue(f"/profiles/{identity}/holes", "孔洞不能再嵌套孔洞")
        if not outer_polygon.contains(hole) or outer_polygon.boundary.intersects(hole):
            issue(
                f"/profiles/{identity}/holes",
                "孔洞必须严格位于外轮廓内部",
                actual=hole_id,
            )
        if any(hole.intersects(prior) for prior in hole_polygons):
            issue(f"/profiles/{identity}/holes", "孔洞不能相交、相切或嵌套")
        hole_polygons.append(hole)
        holes.append(list(hole.exterior.coords))
    result = Polygon(outer, holes)
    if not result.is_valid or result.area <= GEOMETRY_EPSILON:
        issue(f"/profiles/{identity}", "轮廓无效：" + explain_validity(result))
    return result


def _section_edges(section: dict, volume: dict, profiles: dict) -> dict:
    profile = require(profiles, section["profile"], "/volumes/geometry/profile")
    placement = volume["placement"]
    result = {}
    for key, points in profile_edges(profile).items():
        local = transform_points(
            points,
            section.get("offset_xz", (0, 0)),
            section.get("yaw", 0),
            section.get("scale", (1, 1)),
        )
        result[key] = transform_points(
            local, placement["origin_xz"], placement.get("yaw", 0)
        )
    return result


def volume_sections(volume: dict, levels: dict, profiles: dict) -> list[dict]:
    geometry = volume["geometry"]
    if geometry["type"] == "extrusion":
        values = [
            {"at": geometry["bottom"], "profile": geometry["profile"]},
            {"at": geometry["top"], "profile": geometry["profile"]},
        ]
    elif geometry["type"] == "section_loft":
        values = geometry["sections"]
    else:
        return []
    result = []
    topology = None
    previous = None
    for number, section in enumerate(values):
        y = elevation(
            section["at"], levels, f"/volumes/{volume['id']}/geometry/sections/{number}"
        )
        if previous is not None and y <= previous:
            issue(f"/volumes/{volume['id']}/geometry", "截面标高必须严格递增", actual=y)
        previous = y
        edges = _section_edges(section, volume, profiles)
        profile = profiles[section["profile"]]
        signature = (tuple(edges), tuple(profile.get("holes", [])))
        if topology is not None and signature != topology:
            issue(
                f"/volumes/{volume['id']}/geometry",
                "相邻截面边名及孔洞拓扑不一致，不能猜测匹配关系",
            )
        topology = signature
        holes = []
        for hole_id in profile.get("holes", []):
            hole = profile_polygon(hole_id, profiles)
            points = transform_points(
                list(hole.exterior.coords)[:-1],
                section.get("offset_xz", (0, 0)),
                section.get("yaw", 0),
                section.get("scale", (1, 1)),
            )
            holes.append(
                transform_points(
                    points,
                    volume["placement"]["origin_xz"],
                    volume["placement"].get("yaw", 0),
                )
            )
        result.append({"y": y, "edges": edges, "holes": holes})
    return result


def _resample(points, count):
    line = LineString(points)
    return [
        list(line.interpolate(index / count, normalized=True).coords[0])
        for index in range(count + 1)
    ]


def section_at(sections: list[dict], y: float) -> dict | None:
    if (
        not sections
        or y < sections[0]["y"] - GEOMETRY_EPSILON
        or y > sections[-1]["y"] + GEOMETRY_EPSILON
    ):
        return None
    for section in sections:
        if abs(section["y"] - y) <= GEOMETRY_EPSILON:
            return deepcopy(section)
    slot = max(
        0,
        min(
            len(sections) - 2,
            bisect_right([section["y"] for section in sections], y) - 1,
        ),
    )
    lower, upper = sections[slot], sections[slot + 1]
    ratio = (y - lower["y"]) / (upper["y"] - lower["y"])
    edges = {}
    for key, low in lower["edges"].items():
        high = upper["edges"][key]
        count = max(len(low), len(high)) - 1
        if len(low) != len(high):
            low, high = _resample(low, count), _resample(high, count)
        edges[key] = [
            [a[0] + ratio * (b[0] - a[0]), a[1] + ratio * (b[1] - a[1])]
            for a, b in zip(low, high)
        ]
    holes = []
    for low, high in zip(lower["holes"], upper["holes"]):
        count = max(len(low), len(high))
        low = _resample([*low, low[0]], count)[:-1]
        high = _resample([*high, high[0]], count)[:-1]
        holes.append(
            [
                [a[0] + ratio * (b[0] - a[0]), a[1] + ratio * (b[1] - a[1])]
                for a, b in zip(low, high)
            ]
        )
    return {"y": y, "edges": edges, "holes": holes}


def section_polygon(section: dict) -> Polygon:
    polygon = Polygon(
        join_edges(section["edges"], "/volumes/geometry/sections"), section["holes"]
    )
    if not polygon.is_valid or polygon.area <= GEOMETRY_EPSILON:
        issue(
            "/volumes/geometry/sections",
            "体量插值截面无效：" + explain_validity(polygon),
        )
    return polygon


def polygons(geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [] if geometry.is_empty else [geometry]
    result = []
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        for item in geometry.geoms:
            result.extend(polygons(item))
    return result


def polygon_data(polygon: Polygon) -> dict:
    return {
        "outer": [list(point) for point in polygon.exterior.coords[:-1]],
        "holes": [
            [list(point) for point in ring.coords[:-1]] for ring in polygon.interiors
        ],
    }


def resolve_region(
    region: dict, levels: dict, profiles: dict, volumes: dict, sections: dict
):
    if region["type"] == "volume_union_section":
        y = require(levels, region["level"], "/region/level")["elevation"]
        shapes = []
        for identity in region["volumes"]:
            require(volumes, identity, "/region/volumes")
            section = section_at(sections.get(identity, []), y)
            if section is None:
                issue(
                    "/region/volumes",
                    "体量在指定标高没有可用截面",
                    actual={"volume": identity, "level": region["level"]},
                )
            shapes.append(section_polygon(section))
        return unary_union([set_precision(shape, TOPOLOGY_GRID) for shape in shapes])
    shape = profile_polygon(region["profile"], profiles)
    shape = affinity.rotate(
        shape, -region.get("yaw", 0), origin=(0, 0), use_radians=True
    )
    shape = affinity.translate(shape, *region.get("origin_xz", (0, 0)))
    if region.get("frame", "world") != "world":
        volume = require(volumes, region["frame"], "/region/frame")
        placement = volume["placement"]
        shape = affinity.rotate(
            shape, -placement.get("yaw", 0), origin=(0, 0), use_radians=True
        )
        shape = affinity.translate(shape, *placement["origin_xz"])
    return shape


def validate_spatial_design(design: dict) -> None:
    """只核对可计算事实；高级形态留给能力反馈，不用矩形默认值伪装通过。"""
    levels = index_by_id(design.get("levels", []), "/levels")
    profiles = index_by_id(design.get("profiles", []), "/profiles")
    volumes = index_by_id(design.get("volumes", []), "/volumes")
    walls = index_by_id(design.get("walls", []), "/walls")
    slabs = index_by_id(design.get("slabs", []), "/slabs")
    voids = index_by_id(design.get("voids", []), "/voids")
    components = index_by_id(design.get("components", []), "/components")
    roofs = index_by_id(design.get("roofs", []), "/roofs")
    relations = index_by_id(design.get("relations", []), "/relations")
    all_ids = set()
    for records in (
        levels,
        profiles,
        volumes,
        walls,
        slabs,
        voids,
        components,
        roofs,
        relations,
    ):
        overlap = all_ids.intersection(records)
        if overlap:
            issue("/decisions", "不同实体的稳定ID不得重复", actual=sorted(overlap))
        all_ids.update(records)
    storeys = [level for level in levels.values() if level["kind"] == "storey"]
    if len(storeys) != design["massing"]["modeled_floors"]:
        issue(
            "/levels",
            "主楼面数量必须与modeled_floors一致",
            expected=design["massing"]["modeled_floors"],
            actual=len(storeys),
        )
    indices = [level.get("index") for level in storeys]
    if sorted(index for index in indices if index is not None) != list(
        range(1, len(storeys) + 1)
    ):
        issue("/levels", "主楼层index必须从1开始连续且唯一")
    ordered = sorted(storeys, key=lambda level: level["index"])
    if any(b["elevation"] <= a["elevation"] for a, b in zip(ordered, ordered[1:])):
        issue("/levels", "主楼层标高必须按index递增")
    for identity in profiles:
        profile_polygon(identity, profiles)
    sections = {}
    shapes = []
    for identity, volume in volumes.items():
        if not volume.get("geometry"):
            issue(f"/volumes/{identity}", "新图纸中每个体量必须使用明确geometry")
        values = volume_sections(volume, levels, profiles)
        sections[identity] = values
        for section in values:
            shapes.append(section_polygon(section))
        for a, b in zip(values, values[1:]):
            for fraction in (0.25, 0.5, 0.75):
                section_polygon(
                    section_at(values, a["y"] + (b["y"] - a["y"]) * fraction)
                )
    if shapes:
        x0, z0, x1, z1 = unary_union(shapes).bounds
        for name, actual in (("width", x1 - x0), ("depth", z1 - z0)):
            if actual > design["massing"][name] + 0.001:
                issue(
                    "/massing/" + name,
                    "真实截面包络超出总体尺寸控制",
                    expected=design["massing"][name],
                    actual=actual,
                )
    systems = design.get("systems", {})
    for layout_index, layout in enumerate(design.get("floor_layouts", [])):
        require(levels, layout["level"], f"/floor_layouts/{layout_index}/level")
        for room in layout.get("rooms", []):
            if room["id"] in all_ids:
                issue(
                    f"/floor_layouts/{layout_index}/rooms",
                    "房间ID与已有实体重复",
                    actual=room["id"],
                )
            all_ids.add(room["id"])
            if not room.get("region"):
                issue(
                    f"/floor_layouts/{layout_index}/rooms/{room['id']}/region",
                    "新图纸必须明确房间真实区域，不能以bounds代替",
                )
            resolve_region(room["region"], levels, profiles, volumes, sections)
    for identity, wall in walls.items():
        system = require(systems, wall["system"], f"/walls/{identity}/system")
        if system["kind"] != "wall":
            issue(f"/walls/{identity}/system", "墙必须引用wall系统")
        geometry = wall["geometry"]
        bottom = elevation(geometry["bottom"], levels)
        top = elevation(geometry["top"], levels)
        if top <= bottom:
            issue(f"/walls/{identity}/geometry", "墙顶必须高于墙底")
        if geometry["type"] == "volume_boundary":
            require(volumes, geometry["volume"], f"/walls/{identity}/geometry/volume")
            for y in (bottom, top):
                section = section_at(sections.get(geometry["volume"], []), y)
                if section is None or geometry["edge"] not in section["edges"]:
                    issue(
                        f"/walls/{identity}/geometry/edge",
                        "墙边界在指定高度不存在",
                        actual=geometry["edge"],
                    )
        else:
            if geometry.get("frame", "world") != "world":
                require(volumes, geometry["frame"], f"/walls/{identity}/geometry/frame")
            last = None
            for segment in geometry["segments"]:
                points = segment_points(segment)
                if (
                    last is not None
                    and hypot(last[0] - points[0][0], last[1] - points[0][1])
                    > GEOMETRY_EPSILON
                ):
                    issue(
                        f"/walls/{identity}/geometry/segments", "墙路径相邻段必须衔接"
                    )
                if LineString(points).length <= GEOMETRY_EPSILON:
                    issue(f"/walls/{identity}/geometry/segments", "墙路径不能退化")
                last = points[-1]
    for identity, item in voids.items():
        require(levels, item["level"], f"/voids/{identity}/level")
        resolve_region(item["region"], levels, profiles, volumes, sections)
    for identity, slab in slabs.items():
        system = require(systems, slab["system"], f"/slabs/{identity}/system")
        if system["kind"] != "slab":
            issue(f"/slabs/{identity}/system", "楼板必须引用slab系统")
        elevation(slab["top"], levels)
        region = resolve_region(slab["region"], levels, profiles, volumes, sections)
        for hole in slab.get("holes", []):
            void = require(voids, hole, f"/slabs/{identity}/holes")
            if (
                abs(elevation(slab["top"], levels) - levels[void["level"]]["elevation"])
                > 0.001
            ):
                issue(f"/slabs/{identity}/holes", "留洞与板顶不在同一标高", actual=hole)
            hole_shape = resolve_region(
                void["region"], levels, profiles, volumes, sections
            )
            if not region.covers(hole_shape):
                issue(f"/slabs/{identity}/holes", "留洞超出实际楼板范围", actual=hole)
    for identity, component in components.items():
        if component.get("system"):
            system = require(
                systems, component["system"], f"/components/{identity}/system"
            )
            if system["kind"] != component["type"]:
                issue(f"/components/{identity}/system", "构造系统类型与构件类型不符")
        host = component.get("host")
        placement = component.get("placement") or {}
        if host and host not in all_ids:
            issue(f"/components/{identity}/host", "宿主未声明", actual=host)
        if (
            component["type"] in {"door", "window", "opening", "bay_window"}
            and host not in walls
        ):
            issue(f"/components/{identity}/host", "门窗必须引用逻辑墙ID", actual=host)
        if placement.get("mode") in {"wall", "anchor", "surface"} and not host:
            issue(f"/components/{identity}/host", "宿主定位必须明确host")
        if placement.get("mode") == "wall" and host not in walls:
            issue(f"/components/{identity}/placement", "wall定位必须引用墙")
        if component.get("footprint"):
            require(
                profiles, component["footprint"], f"/components/{identity}/footprint"
            )
        if component.get("opening"):
            require(voids, component["opening"], f"/components/{identity}/opening")
        if component.get("access"):
            require(profiles, component["access"], f"/components/{identity}/access")
        if host == identity:
            issue(f"/components/{identity}/host", "构件不能依附自身")
        for connection in component.get("floor_connections", []):
            if not connection.get("from_level") or not connection.get("to_level"):
                issue(
                    f"/components/{identity}/floor_connections",
                    "新空间图纸使用from_level/to_level引用明确标高",
                )
            if connection.get("from_level"):
                a = require(
                    levels,
                    connection["from_level"],
                    f"/components/{identity}/floor_connections",
                )
                b = require(
                    levels,
                    connection["to_level"],
                    f"/components/{identity}/floor_connections",
                )
                if a["elevation"] >= b["elevation"]:
                    issue(
                        f"/components/{identity}/floor_connections",
                        "连接终点必须高于起点",
                    )
    for identity, roof in roofs.items():
        require(volumes, roof["host"], f"/roofs/{identity}/host")
        elevation(roof["support"], levels)
        if not roof["geometry"].get("type"):
            issue(f"/roofs/{identity}/geometry/type", "屋面必须明确几何类型")
    for relation in design.get("relations", []):
        require(
            {key: True for key in all_ids}, relation["subject"], "/relations/subject"
        )
        for target in [
            *relation.get("targets", []),
            *([relation["target"]] if relation.get("target") else []),
        ]:
            require({key: True for key in all_ids}, target, "/relations/targets")
    from graphlib import CycleError, TopologicalSorter

    dependencies = {}
    for identity, component in components.items():
        targets = [
            component.get("host"),
            (component.get("relation") or {}).get("target"),
        ]
        dependencies[identity] = [target for target in targets if target in components]
    try:
        tuple(TopologicalSorter(dependencies).static_order())
    except CycleError as exc:
        issue(
            "/components/host",
            "构件依附存在循环，无法按宿主先后顺序实现",
            actual=exc.args[1],
        )
    circulation = design.get("circulation") or {}
    for number, connection in enumerate(circulation.get("required_connections", [])):
        for field in ("from", "to", "via"):
            if connection.get(field):
                require(
                    {key: True for key in all_ids},
                    connection[field],
                    f"/circulation/required_connections/{number}/{field}",
                )
    for number, path in enumerate(circulation.get("clearance_paths", [])):
        require(levels, path["level"], f"/circulation/clearance_paths/{number}/level")
        if LineString(path["points"]).length <= GEOMETRY_EPSILON:
            issue(
                f"/circulation/clearance_paths/{number}/points",
                "净空路径不能退化为一个点",
            )


def host_path(host: dict, y: float) -> list[list[float]]:
    """在指定标高取得宿主路径，供定位、平面预览和通行检查共用。"""
    path = host["path"]
    sections = host.get("sections", [])
    if sections:
        lower = sections[0]
        upper = sections[-1]
        for a, b in zip(sections, sections[1:]):
            if a["y"] - GEOMETRY_EPSILON <= y <= b["y"] + GEOMETRY_EPSILON:
                lower, upper = a, b
                break
        t = (y - lower["y"]) / (upper["y"] - lower["y"])
        count = max(len(lower["path"]), len(upper["path"])) - 1
        low, high = _resample(lower["path"], count), _resample(upper["path"], count)
        path = [
            [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
            for a, b in zip(low, high)
        ]

    return path


def host_point(
    host: dict, along: float, y: float, normal_offset: float = 0
) -> list[float]:
    """逻辑宿主局部参数→世界点；曲线距离始终由同一基线弧长解释。"""
    baseline = LineString(host["path"])
    if baseline.length <= GEOMETRY_EPSILON:
        issue("/walls/geometry", "宿主路径长度为0", actual=host["id"])
    ratio = along / baseline.length
    if ratio < -GEOMETRY_EPSILON or ratio > 1 + GEOMETRY_EPSILON:
        issue(
            "/components/placement/offset",
            "沿墙位置超出宿主范围",
            expected=[0, baseline.length],
            actual=along,
        )
    path = host_path(host, y)
    line = LineString(path)
    distance = max(0, min(1, ratio)) * line.length
    point = line.interpolate(distance)
    delta = min(0.001, line.length / 1000)
    a, b = (
        line.interpolate(max(0, distance - delta)),
        line.interpolate(min(line.length, distance + delta)),
    )
    length = hypot(b.x - a.x, b.y - a.y)
    if length <= GEOMETRY_EPSILON:
        issue("/walls/geometry", "宿主切线退化", actual=host["id"])
    nx, nz = -(b.y - a.y) / length, (b.x - a.x) / length
    return [point.x + nx * normal_offset, y, point.y + nz * normal_offset]


def _native_curve(design, volume, geometry, bottom):
    """仅对能无损映射的路径返回现有Core曲线；其余保留真实放样面。"""
    shape = volume["geometry"]
    if shape["type"] != "extrusion":
        return None
    profile = next(
        item for item in design["profiles"] if item["id"] == shape["profile"]
    )
    placement = volume["placement"]
    if profile["type"] == "circle":
        return {
            "type": "arc",
            "center": [placement["origin_xz"][0], bottom, placement["origin_xz"][1]],
            "sweep": -360,
            "segments": max(32, _arc_steps(profile["radius"], 2 * pi)),
        }
    if profile["type"] == "ellipse" and abs(placement.get("yaw", 0)) < GEOMETRY_EPSILON:
        return {
            "type": "ellipse",
            "center": [placement["origin_xz"][0], bottom, placement["origin_xz"][1]],
            "radiusX": profile["radius_x"],
            "radiusZ": profile["radius_z"],
            "startAngle": -profile.get("seam_angle", 0) * 180 / pi,
            "sweep": -360,
            "segments": max(
                32, _arc_steps(max(profile["radius_x"], profile["radius_z"]), 2 * pi)
            ),
        }
    if profile["type"] == "curve_loop":
        segment = next(
            item for item in profile["segments"] if item["id"] == geometry["edge"]
        )
        if segment["type"] == "arc":
            center = transform_points(
                [segment["center"]], placement["origin_xz"], placement.get("yaw", 0)
            )[0]
            return {
                "type": "arc",
                "center": [center[0], bottom, center[1]],
                "sweep": -segment["sweep_angle"] * 180 / pi,
                "segments": _arc_steps(segment["radius"], segment["sweep_angle"]),
            }
    return None


def resolve_geometry(design: dict) -> dict:
    """所有设计使用同一解析入口；兼容输入先展开，事实只在这里计算一次。"""
    from agent.utils.design.spatial_input import spatial_input

    data = spatial_input(design)
    levels = index_by_id(data["levels"], "/levels")
    profiles = index_by_id(data["profiles"], "/profiles")
    volumes = index_by_id(data["volumes"], "/volumes")
    sections = {}
    gaps, hosts, body = [], [], []
    volume_facts = {}
    for identity, volume in volumes.items():
        values = volume_sections(volume, levels, profiles)
        sections[identity] = values
        if not values:
            gaps.append(
                {
                    "entity": identity,
                    "field": "geometry",
                    "code": "capability_not_implemented",
                    "expected": volume["geometry"]["type"],
                    "actual": "缺少该高级形态的可用空间解析器",
                }
            )
            continue
        shapes = [section_polygon(section) for section in values]
        x0, z0, x1, z1 = unary_union(shapes).bounds
        volume_facts[identity] = {
            "bounds": [x0, z0, x1, z1],
            "center_xz": [(x0 + x1) / 2, (z0 + z1) / 2],
            "base_y": values[0]["y"],
            "roof_support_y": values[-1]["y"],
            "sections": [
                {"y": section["y"], "edges": section["edges"], **polygon_data(shape)}
                for section, shape in zip(values, shapes)
            ],
        }
    for wall_number, wall in enumerate(data.get("walls", [])):
        geometry = wall["geometry"]
        system = require(
            data["systems"], wall["system"], f"/walls/{wall_number}/system"
        )
        bottom, top = (
            elevation(geometry["bottom"], levels),
            elevation(geometry["top"], levels),
        )
        curve = None
        wall_sections = []
        if geometry["type"] == "volume_boundary":
            volume = require(volumes, geometry["volume"], "/walls/volume")
            heights = [bottom, top]
            heights.extend(
                item["y"]
                for item in sections.get(volume["id"], [])
                if bottom < item["y"] < top
            )
            for y in sorted(set(heights)):
                section = section_at(sections.get(volume["id"], []), y)
                if section is None:
                    issue("/walls/geometry", "墙面超出实际体量截面", actual=wall["id"])
                path = require(
                    section["edges"], geometry["edge"], "/walls/geometry/edge"
                )
                wall_sections.append({"y": y, "path": path})
            curve = _native_curve(data, volume, geometry, bottom)
        else:
            path = []
            for segment in geometry["segments"]:
                points = segment_points(segment)
                path.extend(points if not path else points[1:])
            if geometry.get("frame", "world") != "world":
                placement = volumes[geometry["frame"]]["placement"]
                path = transform_points(
                    path, placement["origin_xz"], placement.get("yaw", 0)
                )
            wall_sections = [{"y": bottom, "path": path}, {"y": top, "path": path}]
            if (
                len(geometry["segments"]) == 1
                and geometry["segments"][0]["type"] == "arc"
                and geometry.get("frame", "world") == "world"
            ):
                segment = geometry["segments"][0]
                curve = {
                    "type": "arc",
                    "center": [segment["center"][0], bottom, segment["center"][1]],
                    "sweep": -segment["sweep_angle"] * 180 / pi,
                    "segments": len(path) - 1,
                }
        path = wall_sections[0]["path"]
        constant = all(item["path"] == path for item in wall_sections)
        line = LineString(path)
        straight = (
            line.length > GEOMETRY_EPSILON
            and abs(
                line.length - hypot(path[-1][0] - path[0][0], path[-1][1] - path[0][1])
            )
            < GEOMETRY_EPSILON
        )
        host = {
            "id": wall["id"],
            "type": "wall",
            "path": path,
            "sections": wall_sections,
            "from": [path[0][0], bottom, path[0][1]],
            "to": [path[-1][0], top, path[-1][1]],
            "thickness": system["thickness"],
            "length": line.length,
            "role": wall["role"],
            "design_path": f"/decisions/walls/{wall_number}",
            "material_role": system.get("material_role"),
            "curved": not straight,
            "varying_section": not constant,
        }
        if curve:
            host["curve"] = curve
        if wall.get("_solid_intervals") is not None:
            host["solid_intervals"] = wall["_solid_intervals"]
            cursor, open_intervals = 0, []
            for start, end in host["solid_intervals"]:
                if start > cursor:
                    open_intervals.append([cursor, start])
                cursor = end
            if cursor < line.length:
                open_intervals.append([cursor, line.length])
            host["open_intervals"] = open_intervals
        hosts.append(host)
        if constant and (straight or curve):
            native = {
                key: host[key] for key in ("id", "type", "from", "to", "thickness")
            }
            if curve:
                native["curve"] = curve
            intervals = host.get("solid_intervals", [[0, line.length]])
            for number, (start, end) in enumerate(intervals):
                piece = deepcopy(native)
                if (
                    len(intervals) != 1
                    or abs(start) > GEOMETRY_EPSILON
                    or abs(end - line.length) > GEOMETRY_EPSILON
                ):
                    piece["id"] = f"{wall['id']}__part_{number}"
                    a, b = line.interpolate(start), line.interpolate(end)
                    piece["from"], piece["to"] = [a.x, bottom, a.y], [b.x, top, b.y]
                body.append(piece)
        else:
            shell_sections = []
            for section in wall_sections:
                shell = LineString(section["path"]).buffer(
                    system["thickness"] / 2, cap_style="flat", join_style="mitre"
                )
                items = polygons(shell)
                if len(items) != 1:
                    issue(
                        "/walls/geometry",
                        "墙路径生成了不连续或自交的厚度区域",
                        actual=wall["id"],
                    )
                shell_sections.append(
                    {"height": section["y"], "profile": polygon_data(items[0])}
                )
            count = max(len(section["profile"]["outer"]) for section in shell_sections)
            for section in shell_sections:
                ring = section["profile"]["outer"]
                section["profile"]["outer"] = _resample([*ring, ring[0]], count)[:-1]
            hole_counts = {
                len(section["profile"]["holes"]) for section in shell_sections
            }
            if len(hole_counts) != 1:
                issue(
                    "/walls/geometry",
                    "墙厚区域的孔洞拓扑在截面间发生改变，不能猜测网格对应关系",
                    actual=wall["id"],
                )
            for hole_index in range(next(iter(hole_counts))):
                count = max(
                    len(section["profile"]["holes"][hole_index])
                    for section in shell_sections
                )
                for section in shell_sections:
                    ring = section["profile"]["holes"][hole_index]
                    section["profile"]["holes"][hole_index] = _resample(
                        [*ring, ring[0]], count
                    )[:-1]
            body.append(
                {
                    "id": wall["id"],
                    "type": "solid",
                    "kind": "loft",
                    "sections": shell_sections,
                    "segmentsPerSpan": 1,
                }
            )
    void_shapes = {}
    for item in data.get("voids", []):
        void_shapes[item["id"]] = resolve_region(
            item["region"], levels, profiles, volumes, sections
        )
    slab_facts = []
    for slab in data.get("slabs", []):
        shape = resolve_region(slab["region"], levels, profiles, volumes, sections)
        for hole in slab.get("holes", []):
            shape = shape.difference(require(void_shapes, hole, "/slabs/holes"))
        system = data["systems"][slab["system"]]
        top = elevation(slab["top"], levels)
        for number, polygon in enumerate(polygons(shape)):
            identity = slab["id"] if number == 0 else f"{slab['id']}__part_{number}"
            bounds = polygon.bounds
            piece = {
                "type": "floor",
                "id": identity,
                "from": [0, top - system["thickness"], 0],
                "thickness": system["thickness"],
                "shape": "polygon",
                "polygon": polygon_data(polygon)["outer"],
            }
            if polygon.interiors:
                piece["holes"] = polygon_data(polygon)["holes"]
            body.append(piece)
            slab_facts.append(
                {
                    "id": identity,
                    "source_id": slab["id"],
                    "top_y": top,
                    "bottom_y": top - system["thickness"],
                    "bounds": list(bounds),
                    **polygon_data(polygon),
                    "material_role": system.get("material_role"),
                }
            )
    level_facts = []
    ordered = sorted(levels.values(), key=lambda level: level["elevation"])
    main_indices = {
        item["id"]: item.get("index") for item in ordered if item["kind"] == "storey"
    }
    for number, level in enumerate(ordered):
        if level["kind"] == "roof":
            continue
        top = (
            ordered[number + 1]["elevation"]
            if number + 1 < len(ordered)
            else level["elevation"] + data["massing"]["floor_height"]
        )
        voids = []
        for void in data.get("voids", []):
            if void["level"] != level["id"]:
                continue
            for polygon in polygons(void_shapes[void["id"]]):
                voids.append(
                    {
                        "id": void["id"],
                        "bounds": list(polygon.bounds),
                        **polygon_data(polygon),
                    }
                )
        active = []
        for identity, values in sections.items():
            if (
                values
                and values[0]["y"] - GEOMETRY_EPSILON
                <= level["elevation"]
                < values[-1]["y"] - GEOMETRY_EPSILON
            ):
                active.append(identity)
        level_facts.append(
            {
                "id": level["id"],
                "index": level.get("index") or len(main_indices) + number + 1,
                "kind": level["kind"],
                "base_y": level["elevation"],
                "top_y": top,
                "height": top - level["elevation"],
                "volume_ids": active,
                "voids": voids,
            }
        )
    all_shapes = []
    for facts in volume_facts.values():
        all_shapes.extend(
            Polygon(section["outer"], section["holes"]) for section in facts["sections"]
        )
    if all_shapes:
        x0, z0, x1, z1 = unary_union(all_shapes).bounds
        bottom = min(item["base_y"] for item in volume_facts.values())
        top = max(item["roof_support_y"] for item in volume_facts.values())
        bounds = {"width": x1 - x0, "depth": z1 - z0, "height": top - bottom}
    else:
        bounds = {"width": 0, "depth": 0, "height": 0}
    return {
        "levels": level_facts,
        "volumes": volume_facts,
        "hosts": hosts,
        "slabs": slab_facts,
        "body_geometry": {"elements": body, "components": []},
        "capability_gaps": gaps,
        "bounds": bounds,
        "source": data,
        "open_boundaries": data.get("_open_boundaries", []),
    }


def execution_view(design: dict, geometry: dict | None = None) -> dict:
    """给既有执行/验收工具提供派生数值；真实轮廓仍在geometry_context，不反写图纸。"""
    facts = geometry or resolve_geometry(design)
    from agent.utils.design.spatial_input import spatial_input

    source = facts.get("source") or spatial_input(design)
    result = deepcopy(source.get("_legacy_source", design))
    result["geometry_context"] = {
        key: value
        for key, value in facts.items()
        if key not in {"source", "body_geometry"}
    }
    result["volumes"] = []
    for identity, volume in facts["volumes"].items():
        x0, z0, x1, z1 = volume["bounds"]
        active = [
            level["index"]
            for level in facts["levels"]
            if identity in level["volume_ids"]
        ]
        result["volumes"].append(
            {
                "id": identity,
                "x": x0,
                "z": z0,
                "width": x1 - x0,
                "depth": z1 - z0,
                "start_floor": min(active) if active else 1,
                "end_floor": max(active) if active else 1,
                "sections": volume["sections"],
            }
        )
    if source.get("_legacy_source"):
        return result
    levels = {item["id"]: item for item in facts["levels"]}
    level_index = index_by_id(source["levels"], "/levels")
    profiles = index_by_id(source["profiles"], "/profiles")
    volumes = index_by_id(source["volumes"], "/volumes")
    sections = {
        identity: volume_sections(volume, level_index, profiles)
        for identity, volume in volumes.items()
    }
    layouts = []
    for layout in source.get("floor_layouts", []):
        level = require(levels, layout.get("level"), "/floor_layouts/level")
        rooms = []
        for room in layout.get("rooms", []):
            region = resolve_region(
                room["region"], level_index, profiles, volumes, sections
            )
            x0, z0, x1, z1 = region.bounds
            rooms.append(
                {
                    **room,
                    "bounds": {"x": x0, "z": z0, "width": x1 - x0, "depth": z1 - z0},
                    "polygons": [polygon_data(piece) for piece in polygons(region)],
                }
            )
        partitions = []
        for host in facts["hosts"]:
            if (
                host["role"] == "interior"
                and abs(host["from"][1] - level["base_y"]) < 0.001
            ):
                partitions.append(
                    {
                        "id": host["id"],
                        "from": host["path"][0],
                        "to": host["path"][-1],
                        "thickness": host["thickness"],
                        "path": host["path"],
                    }
                )
        layouts.append(
            {
                "floor": level["index"],
                "level": level["base_y"],
                "rooms": rooms,
                "walls": partitions,
            }
        )
    result["floor_layouts"] = layouts
    result.setdefault("facades", {})
    result.setdefault("roof", {"type": "none", "overhang": 0, "volumes": []})
    return result
