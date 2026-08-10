"""建筑方案归一化、候选评分与确定性立面槽位解析。"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


_FACES = ("front", "back", "left", "right")
_OPENING_TYPES = {"door", "window", "empty"}


def _clamp_number(value: object, low: float, high: float, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(low, min(high, number))


def _requested_floors(user_message: str) -> int | None:
    match = re.search(r"([1-5])\s*层", user_message)
    if match:
        return int(match.group(1))
    mapping = {"一层": 1, "单层": 1, "二层": 2, "两层": 2, "三层": 3}
    return next((value for word, value in mapping.items() if word in user_message), None)


def _fallback_plan(user_message: str) -> dict[str, Any]:
    floors = _requested_floors(user_message) or 2
    is_european = any(word in user_message for word in ("欧式", "法式", "古典"))
    is_chinese = any(word in user_message for word in ("中式", "新中式", "庭院"))
    is_modern = any(word in user_message for word in ("现代", "极简"))
    style = "欧式" if is_european else "中式" if is_chinese else "现代" if is_modern else "当代住宅"
    roof_type = "hip" if is_european or is_chinese else "flat" if is_modern else "gable"
    return {
        "schema_version": "1.0",
        "concept": f"{style}、比例清晰、入口有识别度",
        "massing": {
            "shape": "rectangle",
            "width": 12.0,
            "depth": 9.0,
            "floors": floors,
            "floor_height": 3.2,
            "symmetry": is_european,
        },
        "facades": {
            "front": {
                "bays": 5,
                "entrance_bay": 3,
                "ground_pattern": ["window", "empty", "door", "empty", "window"],
                "upper_pattern": ["window", "empty", "window", "empty", "window"],
            },
            "back": {
                "bays": 4,
                "ground_pattern": ["window", "empty", "empty", "window"],
                "upper_pattern": ["window", "empty", "empty", "window"],
            },
            "left": {
                "bays": 3,
                "ground_pattern": ["empty", "window", "empty"],
                "upper_pattern": ["empty", "window", "empty"],
            },
            "right": {
                "bays": 3,
                "ground_pattern": ["empty", "window", "empty"],
                "upper_pattern": ["empty", "window", "empty"],
            },
        },
        "roof": {"type": roof_type, "ridge_axis": "x", "overhang": 0.55},
        "component_quota": {
            "door": {"min": 1, "max": 2, "note": "主入口，必要时增加后门"},
            "window": {"min": min(14, 6 + max(0, floors - 1) * 4), "max": 14, "note": "按立面轴线对齐"},
            "roof": {"min": 1, "max": 1, "type": roof_type, "note": "覆盖主体体量"},
        },
        "required_components": ["door", "window", "roof"],
        "design_rationale": ["入口位于主立面视觉中心", "上下层门窗沿轴线对齐"],
    }


def _normalize_pattern(value: object, bays: int, fallback: list[str]) -> list[str]:
    raw = value if isinstance(value, list) else fallback
    pattern = [str(item).lower() if str(item).lower() in _OPENING_TYPES else "empty" for item in raw]
    if len(pattern) < bays:
        pattern.extend(["empty"] * (bays - len(pattern)))
    return pattern[:bays]


def normalize_architecture_plan(raw: object, user_message: str = "") -> dict[str, Any]:
    """把模型方案压缩到稳定、有限的架构规划协议。"""
    fallback = _fallback_plan(user_message)
    source = raw if isinstance(raw, dict) else {}
    massing_raw = source.get("massing") if isinstance(source.get("massing"), dict) else {}
    requested_floors = _requested_floors(user_message)
    floors = int(_clamp_number(
        requested_floors if requested_floors is not None else massing_raw.get("floors"),
        1,
        5,
        fallback["massing"]["floors"],
    ))
    massing = {
        "shape": str(massing_raw.get("shape") or fallback["massing"]["shape"]).lower(),
        "width": round(_clamp_number(massing_raw.get("width"), 4, 40, fallback["massing"]["width"]), 2),
        "depth": round(_clamp_number(massing_raw.get("depth"), 4, 40, fallback["massing"]["depth"]), 2),
        "floors": floors,
        "floor_height": round(_clamp_number(massing_raw.get("floor_height"), 2.4, 5, 3.2), 2),
        "symmetry": bool(massing_raw.get("symmetry", fallback["massing"]["symmetry"])),
    }
    if massing["shape"] not in {"rectangle", "l_shape", "stepped", "courtyard"}:
        massing["shape"] = "rectangle"

    facade_source = source.get("facades") if isinstance(source.get("facades"), dict) else {}
    facades: dict[str, dict[str, Any]] = {}
    for face in _FACES:
        base = fallback["facades"][face]
        item = facade_source.get(face) if isinstance(facade_source.get(face), dict) else {}
        bays = int(_clamp_number(item.get("bays"), 1, 9, base["bays"]))
        ground = _normalize_pattern(item.get("ground_pattern"), bays, base["ground_pattern"])
        upper = _normalize_pattern(item.get("upper_pattern"), bays, base["upper_pattern"])
        entrance_bay = int(_clamp_number(item.get("entrance_bay"), 1, bays, base.get("entrance_bay", 1)))
        if face == "front" and "door" not in ground:
            ground[entrance_bay - 1] = "door"
        facades[face] = {
            "bays": bays,
            "entrance_bay": entrance_bay,
            "ground_pattern": ground,
            "upper_pattern": upper,
        }

    roof_raw = source.get("roof") if isinstance(source.get("roof"), dict) else {}
    roof_type = str(roof_raw.get("type") or fallback["roof"]["type"]).lower()
    if roof_type not in {"flat", "gable", "hip", "shed", "mansard", "pyramid"}:
        roof_type = fallback["roof"]["type"]
    roof = {
        "type": roof_type,
        "ridge_axis": "z" if str(roof_raw.get("ridge_axis", "x")).lower() == "z" else "x",
        "overhang": round(_clamp_number(roof_raw.get("overhang"), 0, 2, fallback["roof"]["overhang"]), 2),
    }

    quotas = deepcopy(fallback["component_quota"])
    raw_quotas = source.get("component_quota") if isinstance(source.get("component_quota"), dict) else {}
    for component_type, limits in raw_quotas.items():
        if not isinstance(limits, dict):
            continue
        normalized_limits = deepcopy(limits)
        if "min" in limits:
            normalized_limits["min"] = int(_clamp_number(limits.get("min"), 0, 32, 0))
        if "max" in limits:
            normalized_limits["max"] = int(_clamp_number(limits.get("max"), 0, 32, 32))
        if isinstance(normalized_limits.get("min"), int) and isinstance(normalized_limits.get("max"), int):
            normalized_limits["max"] = max(normalized_limits["min"], normalized_limits["max"])
        quotas[str(component_type)] = normalized_limits
    quotas["roof"] = {**quotas.get("roof", {}), "min": 1, "max": 1, "type": roof_type}

    allowed_components = {
        "door", "window", "roof", "railing", "canopy", "balcony", "light",
        "ramp", "bay_window", "cornice", "chimney",
    }
    required = source.get("required_components")
    if not isinstance(required, list):
        required = fallback["required_components"]
    required_components = [
        str(item).lower() for item in required
        if str(item).lower() in allowed_components
    ]
    for base_type in ("door", "window", "roof"):
        if base_type not in required_components:
            required_components.append(base_type)

    rationale = source.get("design_rationale")
    if not isinstance(rationale, list):
        rationale = fallback["design_rationale"]
    return {
        "schema_version": "1.0",
        "concept": str(source.get("concept") or fallback["concept"])[:240],
        "massing": massing,
        "facades": facades,
        "roof": roof,
        "component_quota": quotas,
        "required_components": list(dict.fromkeys(required_components)),
        "design_rationale": [str(item)[:160] for item in rationale[:6]],
    }


def score_architecture_plan(plan: dict[str, Any], user_message: str) -> int:
    """用可解释规则选择同一模型给出的候选方案。"""
    score = 0
    massing = plan["massing"]
    facades = plan["facades"]
    score += 10 if plan.get("concept") else 0
    score += 12 if 6 <= massing["width"] <= 24 and 6 <= massing["depth"] <= 24 else 0
    requested = _requested_floors(user_message)
    score += 16 if requested is None or requested == massing["floors"] else -16
    front_ground = facades["front"]["ground_pattern"]
    score += 15 if "door" in front_ground else -30
    score += 8 if any(item == "window" for item in front_ground) else 0
    score += 8 if plan.get("required_components") else 0
    score += min(12, len(plan.get("design_rationale", [])) * 3)
    if any(word in user_message for word in ("欧式", "法式", "对称")):
        score += 12 if massing["symmetry"] else -8
        score += 8 if plan["roof"]["type"] in {"hip", "mansard", "gable"} else -6
    if any(word in user_message for word in ("现代", "极简")):
        score += 8 if plan["roof"]["type"] in {"flat", "shed"} else 0
    return score


def select_architecture_plan(raw: object, user_message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """归一化候选并以确定性评分选出一个方案。"""
    source = raw if isinstance(raw, dict) else {}
    candidates_raw = source.get("candidates") if isinstance(source.get("candidates"), list) else [source]
    candidates = [normalize_architecture_plan(item, user_message) for item in candidates_raw[:4]]
    if not candidates:
        candidates = [normalize_architecture_plan({}, user_message)]
    scores = [score_architecture_plan(item, user_message) for item in candidates]
    selected_index = max(range(len(candidates)), key=lambda index: scores[index])
    candidate_summaries = [
        {
            "index": index,
            "score": scores[index],
            "concept": candidate.get("concept", ""),
            "massing": deepcopy(candidate.get("massing", {})),
            "roof": deepcopy(candidate.get("roof", {})),
            "front_bays": candidate.get("facades", {}).get("front", {}).get("bays"),
            "rationale": list(candidate.get("design_rationale", [])),
        }
        for index, candidate in enumerate(candidates)
    ]
    return candidates[selected_index], {
        "candidate_count": len(candidates),
        "candidate_scores": scores,
        "candidate_summaries": candidate_summaries,
        "selected_index": selected_index,
        "used_fallback": not bool(raw),
    }


def _wall_descriptor(wall: dict[str, Any]) -> dict[str, Any] | None:
    start = wall.get("from")
    end = wall.get("to")
    if not isinstance(start, list) or not isinstance(end, list) or len(start) != 3 or len(end) != 3:
        return None
    try:
        values = [float(value) for value in (*start, *end)]
    except (TypeError, ValueError):
        return None
    x1, y1, z1, x2, y2, z2 = values
    length = math.hypot(x2 - x1, z2 - z1)
    height = abs(y2 - y1)
    if length < 0.5 or height < 0.5:
        return None
    return {
        "id": wall.get("id"), "x": (x1 + x2) / 2, "z": (z1 + z2) / 2,
        "base_y": min(y1, y2), "height": height, "length": length,
        "axis": "x" if abs(x2 - x1) >= abs(z2 - z1) else "z",
    }


def resolve_facade_layout(blueprint: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """把抽象立面轴网解析成真实 wall id 与精确门窗局部坐标。"""
    walls = []
    for element in blueprint.get("geometry", {}).get("elements", []):
        if isinstance(element, dict) and element.get("type") == "wall":
            descriptor = _wall_descriptor(element)
            if descriptor:
                walls.append(descriptor)
    if not walls:
        return {"facade_plan": {}, "component_quota": deepcopy(plan.get("component_quota", {})), "opening_slots": []}

    min_x = min(wall["x"] for wall in walls)
    max_x = max(wall["x"] for wall in walls)
    min_z = min(wall["z"] for wall in walls)
    max_z = max(wall["z"] for wall in walls)
    min_y = min(wall["base_y"] for wall in walls)
    span = max(max_x - min_x, max_z - min_z, 1.0)
    boundary_tolerance = max(0.35, span * 0.04)

    facade_plan: dict[str, dict[str, Any]] = {}
    slots: list[dict[str, Any]] = []
    for wall in sorted(walls, key=lambda item: (item["base_y"], str(item["id"]))):
        if wall["axis"] == "x":
            distances = {"front": abs(wall["z"] - min_z), "back": abs(wall["z"] - max_z)}
        else:
            distances = {"left": abs(wall["x"] - min_x), "right": abs(wall["x"] - max_x)}
        facing = min(distances, key=distances.get)
        external = distances[facing] <= boundary_tolerance
        facade = plan.get("facades", {}).get(facing, {})
        bays = max(1, int(facade.get("bays", 1)))
        is_ground = abs(wall["base_y"] - min_y) < 0.25
        pattern_key = "ground_pattern" if is_ground else "upper_pattern"
        pattern = facade.get(pattern_key, []) if external else []
        bay_width = wall["length"] / bays
        wall_slots: list[dict[str, Any]] = []
        for bay_index, opening_type in enumerate(pattern[:bays]):
            if opening_type not in {"door", "window"}:
                continue
            if opening_type == "door" and not is_ground:
                continue
            width_factor = 0.52 if opening_type == "door" else 0.62
            width_limit = 1.25 if opening_type == "door" else 2.2
            width_floor = 0.85 if opening_type == "door" else 0.75
            width = max(width_floor, min(width_limit, bay_width * width_factor))
            width = min(width, max(0.5, bay_width - 0.35))
            center = bay_width * (bay_index + 0.5)
            left = max(0.18, min(wall["length"] - width - 0.18, center - width / 2))
            bottom = wall["base_y"] if opening_type == "door" else wall["base_y"] + min(1.0, wall["height"] * 0.3)
            height = min(2.35 if opening_type == "door" else 1.55, wall["height"] - (bottom - wall["base_y"]) - 0.25)
            slot = {
                "id": f"{wall['id']}:{opening_type}:{bay_index + 1}",
                "type": opening_type,
                "wall_id": wall["id"],
                "facing": facing,
                "bay": bay_index + 1,
                "from": [round(left, 3), round(bottom, 3), 0.0],
                "width": round(width, 3),
                "height": round(max(0.8, height), 3),
            }
            wall_slots.append(slot)
            slots.append(slot)
        facade_plan[str(wall["id"])] = {
            "facing": facing if external else "internal",
            "intent": "按建筑方案轴网布置门窗" if external else "内部/退台墙，不自动开口",
            "max_openings": len(wall_slots),
            "is_main_facade": external and facing == "front",
            "slots": wall_slots,
        }

    slots.sort(key=lambda slot: (
        {"front": 0, "back": 1, "left": 2, "right": 3}.get(slot["facing"], 4),
        slot["bay"],
        slot["from"][1],
    ))

    quotas = deepcopy(plan.get("component_quota", {}))
    for opening_type in ("door", "window"):
        available = sum(1 for slot in slots if slot["type"] == opening_type)
        limits = quotas.setdefault(opening_type, {})
        maximum = limits.get("max")
        limits["max"] = available if not isinstance(maximum, (int, float)) else min(int(maximum), available)
        minimum = limits.get("min", 0)
        limits["min"] = min(int(minimum) if isinstance(minimum, (int, float)) else 0, limits["max"])

    return {
        "facade_plan": facade_plan,
        "component_quota": quotas,
        "opening_slots": slots,
        "rag_reference": "建筑方案节点已确定体量、立面轴网、屋顶类型；门窗坐标由程序解析。",
    }


def conform_openings_to_slots(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
    materials: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """把模型门窗吸附到槽位，并补足设计下限；其他组件原样保留。"""
    if not isinstance(design_brief, dict) or not isinstance(design_brief.get("opening_slots"), list):
        return components, {"snapped": 0, "synthesized": 0, "pruned": 0}
    material_names = list((materials or {}).keys())
    default_material = material_names[0] if material_names else "default"
    glass_material = next(
        (name for name, value in (materials or {}).items() if "glass" in name.lower() or (isinstance(value, dict) and value.get("opacity", 1) < 0.99)),
        default_material,
    )
    frame_material = next(
        (name for name in material_names if any(word in name.lower() for word in ("frame", "wood", "metal"))),
        default_material,
    )
    non_openings = [item for item in components if item.get("type") not in {"door", "window"}]
    result_openings: list[dict[str, Any]] = []
    stats = {"snapped": 0, "synthesized": 0, "pruned": 0}
    quotas = design_brief.get("component_quota", {})
    all_slots = design_brief["opening_slots"]

    for opening_type in ("door", "window"):
        items = [deepcopy(item) for item in components if item.get("type") == opening_type]
        slots = [slot for slot in all_slots if isinstance(slot, dict) and slot.get("type") == opening_type]
        limits = quotas.get(opening_type, {}) if isinstance(quotas.get(opening_type), dict) else {}
        maximum = min(len(slots), int(limits.get("max", len(slots))))
        minimum = min(maximum, int(limits.get("min", 0)))
        if len(items) > maximum:
            stats["pruned"] += len(items) - maximum
            items = items[:maximum]
        used_slots: set[str] = set()
        ordered_items: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for item in items:
            preferred = next((slot for slot in slots if slot["id"] not in used_slots and slot["wall_id"] == item.get("parentWall")), None)
            slot = preferred or next((slot for slot in slots if slot["id"] not in used_slots), None)
            if not slot:
                break
            used_slots.add(slot["id"])
            ordered_items.append((item, slot))
        while len(ordered_items) < minimum:
            slot = next((candidate for candidate in slots if candidate["id"] not in used_slots), None)
            if not slot:
                break
            used_slots.add(slot["id"])
            index = len(ordered_items) + 1
            if opening_type == "door":
                item = {
                    "id": f"door_planned_{index:02d}", "type": "door",
                    "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90},
                    "frameMaterial": frame_material, "leafMaterial": frame_material,
                }
            else:
                item = {
                    "id": f"window_planned_{index:02d}", "type": "window",
                    "verticalMullions": 1, "horizontalMullions": 0,
                    "frameMaterial": frame_material, "glassMaterial": glass_material,
                }
            ordered_items.append((item, slot))
            stats["synthesized"] += 1
        for item, slot in ordered_items:
            item["parentWall"] = slot["wall_id"]
            item["from"] = deepcopy(slot["from"])
            item["width"] = slot["width"]
            item["height"] = slot["height"]
            result_openings.append(item)
            stats["snapped"] += 1
    return [*non_openings, *result_openings], stats
