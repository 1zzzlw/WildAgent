"""轴对齐直梯的楼板通道：用已有矩形 floor 表达差集，不发明洞口字段。

范围：矩形楼板、轴对齐直梯及纯平移模板实例；不改圆板、斜梯和旋转实例。
楼梯投影从下端到上端留空，上端之外的楼板作为平台保留。容差为 1mm。
"""

from copy import deepcopy


EPS = 0.001


def _members(blueprint):
    geometry = blueprint.get("geometry") or {}
    for element in geometry.get("elements", []):
        yield element, None
    templates = geometry.get("templates") or {}
    for instance in geometry.get("instances", []):
        template = templates.get(instance.get("ref"), {})
        if template.get("type") not in {"floor", "stair"}:
            continue
        if instance.get("rotation", [0, 0, 0]) != [0, 0, 0] or instance.get("scale", [1, 1, 1]) != [1, 1, 1]:
            continue
        element = deepcopy(template)
        element.update(instance.get("overrides") or {})
        element["id"] = instance["id"]
        offset = instance.get("position", [0, 0, 0])
        for key in ("from", "to"):
            if isinstance(element.get(key), list) and len(element[key]) == 3:
                element[key] = [value + shift for value, shift in zip(element[key], offset)]
        yield element, instance


def _opening(stair):
    start, end = stair.get("from"), stair.get("to")
    if not isinstance(start, list) or not isinstance(end, list) or len(start) != 3 or len(end) != 3:
        return None
    half = float(stair.get("width") or 0) / 2
    if end[1] <= start[1] + EPS or half <= 0:
        return None
    if abs(end[0] - start[0]) <= EPS and abs(end[2] - start[2]) > EPS:
        return start[0] - half, min(start[2], end[2]), start[0] + half, max(start[2], end[2])
    if abs(end[2] - start[2]) <= EPS and abs(end[0] - start[0]) > EPS:
        return min(start[0], end[0]), start[2] - half, max(start[0], end[0]), start[2] + half
    return None


def _blocked_regions(blueprint):
    members = list(_members(blueprint))
    stairs = [(s, _opening(s)) for s, _ in members if s.get("type") == "stair"]
    for floor, instance in members:
        if floor.get("type") != "floor" or floor.get("shape", "rect") != "rect":
            continue
        start, end = floor.get("from"), floor.get("to")
        if not isinstance(start, list) or not isinstance(end, list) or len(start) != 3 or len(end) != 3:
            continue
        bounds = min(start[0], end[0]), min(start[2], end[2]), max(start[0], end[0]), max(start[2], end[2])
        cuts = []
        for stair, opening in stairs:
            if opening is None:
                continue
            # 底层不挖；端点允许与楼板底面或顶面相接，沿途楼板均不得封住梯段。
            y = start[1]
            if y <= stair["from"][1] + 0.25 or y > stair["to"][1] + 0.25:
                continue
            x0, z0 = max(bounds[0], opening[0]), max(bounds[1], opening[1])
            x1, z1 = min(bounds[2], opening[2]), min(bounds[3], opening[3])
            if x1 - x0 > EPS and z1 - z0 > EPS:
                cuts.append((stair["id"], (x0, z0, x1, z1)))
        if cuts:
            yield floor, instance, bounds, cuts


def stair_opening_issues(blueprint: dict) -> list[str]:
    return [
        f"❌ [{floor['id']}, {stair_id}] 楼板遮挡楼梯通道，缺少楼梯开口"
        for floor, _, _, cuts in _blocked_regions(blueprint)
        for stair_id, _ in cuts
    ]


def cut_stair_openings(blueprint: dict) -> list[str]:
    """原位拆分遮挡楼板，保留材质/厚度和原 ID；重复执行不再改变几何。"""
    blocked = list(_blocked_regions(blueprint))
    geometry = blueprint.get("geometry") or {}
    used_ids = {element.get("id") for element, _ in _members(blueprint)}
    changed = []
    for floor, instance, bounds, cuts in blocked:
        rectangles = [bounds]
        for _, (cx0, cz0, cx1, cz1) in cuts:
            remaining = []
            for x0, z0, x1, z1 in rectangles:
                a, b, c, d = max(x0, cx0), max(z0, cz0), min(x1, cx1), min(z1, cz1)
                if c - a <= EPS or d - b <= EPS:
                    remaining.append((x0, z0, x1, z1))
                    continue
                remaining.extend(r for r in (
                    (x0, z0, a, z1), (c, z0, x1, z1),
                    (a, z0, c, b), (a, d, c, z1),
                ) if r[2] - r[0] > EPS and r[3] - r[1] > EPS)
            rectangles = remaining
        pieces = []
        for index, (x0, z0, x1, z1) in enumerate(rectangles):
            piece = deepcopy(floor)
            if index:
                suffix = index
                while f"{floor['id']}_opening_{suffix}" in used_ids:
                    suffix += 1
                piece["id"] = f"{floor['id']}_opening_{suffix}"
                used_ids.add(piece["id"])
            piece["from"] = [x0, floor["from"][1], z0]
            piece["to"] = [x1, floor["from"][1], z1]
            pieces.append(piece)
        if instance is not None:
            geometry["instances"].remove(instance)
            geometry.setdefault("elements", []).extend(pieces)
        else:
            index = geometry["elements"].index(floor)
            geometry["elements"][index:index + 1] = pieces
        changed.append(str(floor["id"]))
    return changed
