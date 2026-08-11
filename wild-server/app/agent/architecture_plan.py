"""建筑方案归一化、候选评分与确定性立面槽位解析。"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


_FACES = ("front", "back", "left", "right")
_OPENING_TYPES = {"door", "window", "empty"}
_SUPPORTED_ROOF_TYPES = {
    "flat", "gable", "hip", "dome", "chinese_curved", "chinese_pagoda",
}


_ARCHITECTURE_PROFILES: dict[str, dict[str, Any]] = {
    "residential_lowrise": {
        "label": "低层居住建筑",
        "width_range": (4.0, 60.0),
        "depth_range": (4.0, 60.0),
        "floor_range": (1, 8),
        "default_massing": (12.0, 9.0, 2, 3.2),
        "max_explicit_floors": 6,
        "shapes": {"rectangle", "l_shape", "stepped", "courtyard"},
        "base_components": ["door", "window", "roof"],
        "require_front_entrance": True,
        "default_roof": "gable",
    },
    "ordinary_public": {
        "label": "普通公共建筑",
        "width_range": (6.0, 160.0),
        "depth_range": (6.0, 160.0),
        "floor_range": (1, 30),
        "default_massing": (30.0, 22.0, 4, 3.9),
        "max_explicit_floors": 8,
        "shapes": {"rectangle", "l_shape", "stepped", "courtyard", "linear"},
        "base_components": ["door", "window", "roof"],
        "require_front_entrance": True,
        "default_roof": "flat",
    },
    "long_span_public": {
        "label": "大跨公共建筑",
        "width_range": (12.0, 300.0),
        "depth_range": (12.0, 300.0),
        "floor_range": (1, 12),
        "default_massing": (80.0, 55.0, 2, 6.0),
        "max_explicit_floors": 4,
        "shapes": {"rectangle", "linear", "radial", "bowl", "terminal"},
        "base_components": ["door", "roof"],
        "require_front_entrance": True,
        "default_roof": "gable",
    },
    "high_rise": {
        "label": "高层与超高层建筑",
        "width_range": (12.0, 120.0),
        "depth_range": (12.0, 120.0),
        "floor_range": (6, 200),
        "default_massing": (42.0, 36.0, 30, 4.0),
        "max_explicit_floors": 10,
        "shapes": {"rectangle", "stepped", "tower", "twin_tower"},
        "base_components": ["door", "window", "roof"],
        "require_front_entrance": True,
        "default_roof": "flat",
    },
    "underground_transport": {
        "label": "地下交通建筑",
        "width_range": (6.0, 300.0),
        "depth_range": (12.0, 500.0),
        "floor_range": (1, 8),
        "default_massing": (24.0, 120.0, 2, 5.0),
        "max_explicit_floors": 4,
        "shapes": {"rectangle", "linear", "underground"},
        "base_components": ["light"],
        "require_front_entrance": False,
        "default_roof": "flat",
    },
    "garden_structure": {
        "label": "园林与景观建筑",
        "width_range": (3.0, 80.0),
        "depth_range": (3.0, 80.0),
        "floor_range": (1, 5),
        "default_massing": (12.0, 8.0, 1, 3.6),
        "max_explicit_floors": 5,
        "shapes": {"rectangle", "l_shape", "courtyard", "linear", "pavilion"},
        "base_components": ["roof", "railing"],
        "require_front_entrance": False,
        "default_roof": "chinese_curved",
    },
    "religious_landmark": {
        "label": "宗教与纪念性建筑",
        "width_range": (6.0, 120.0),
        "depth_range": (6.0, 160.0),
        "floor_range": (1, 12),
        "default_massing": (24.0, 36.0, 2, 5.0),
        "max_explicit_floors": 6,
        "shapes": {"rectangle", "courtyard", "linear", "basilica", "centralized"},
        "base_components": ["door", "window", "roof"],
        "require_front_entrance": True,
        "default_roof": "chinese_curved",
    },
}


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
    match = re.search(r"(?<!\d)(\d{1,3})\s*层", user_message)
    if match:
        return max(1, int(match.group(1)))
    if "单层" in user_message:
        return 1
    chinese_match = re.search(r"([零一二两三四五六七八九十百]+)\s*层", user_message)
    if not chinese_match:
        return None
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    total = 0
    current = 0
    for char in chinese_match.group(1):
        if char in digits:
            current = digits[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
    return max(1, total + current)


def _requested_dimension(user_message: str, labels: tuple[str, ...]) -> float | None:
    number = r"(\d+(?:\.\d+)?)"
    for label in labels:
        before = re.search(fr"{label}\s*{number}\s*(?:米|m)?", user_message, re.I)
        if before:
            return float(before.group(1))
        after = re.search(fr"{number}\s*(?:米|m)?\s*{label}", user_message, re.I)
        if after:
            return float(after.group(1))
    return None


def detect_architecture_profile(user_message: str) -> dict[str, Any]:
    """按功能和规模选择确定性规划边界，避免所有建筑退化成低层住宅。"""
    message = user_message.lower()
    requested_floors = _requested_floors(user_message)
    if any(word in message for word in ("地铁", "地下车站", "站台层", "地下站", "隧道")):
        profile_id = "underground_transport"
    elif (
        any(word in message for word in ("超高层", "摩天", "高层写字楼", "高层办公", "塔楼"))
        or (requested_floors is not None and requested_floors >= 20)
    ):
        profile_id = "high_rise"
    elif any(word in message for word in (
        "体育场", "体育馆", "游泳馆", "航站楼", "高铁站", "火车站",
        "客运站", "港口客运", "剧院", "音乐厅", "会展", "大会堂",
    )):
        profile_id = "long_span_public"
    elif any(word in message for word in ("园林", "水榭", "凉亭", "亭子", "游廊", "景观廊")):
        profile_id = "garden_structure"
    elif any(word in message for word in ("佛寺", "寺庙", "道观", "清真寺", "教堂", "礼拜殿")):
        profile_id = "religious_landmark"
    elif any(word in message for word in (
        "办公", "写字楼", "学校", "幼儿园", "教学楼", "实验室", "博物馆",
        "图书馆", "医院", "商业", "商场", "超市", "酒店", "法院", "养老院",
    )):
        profile_id = "ordinary_public"
    else:
        profile_id = "residential_lowrise"

    profile = deepcopy(_ARCHITECTURE_PROFILES[profile_id])
    profile["id"] = profile_id
    return profile


def _fallback_plan(user_message: str) -> dict[str, Any]:
    profile = detect_architecture_profile(user_message)
    default_width, default_depth, default_floors, default_floor_height = profile["default_massing"]
    requested_width = _requested_dimension(user_message, (r"宽(?:度)?",))
    requested_depth = _requested_dimension(user_message, (r"深(?:度)?", r"长(?:度)?"))
    width = _clamp_number(
        requested_width,
        profile["width_range"][0],
        profile["width_range"][1],
        default_width,
    )
    depth = _clamp_number(
        requested_depth,
        profile["depth_range"][0],
        profile["depth_range"][1],
        default_depth,
    )
    requested_floors = _requested_floors(user_message)
    floors = int(_clamp_number(
        requested_floors,
        profile["floor_range"][0],
        profile["floor_range"][1],
        default_floors,
    ))
    modeled_floors = min(floors, profile["max_explicit_floors"])
    is_european = any(word in user_message for word in ("欧式", "法式", "古典"))
    is_chinese = any(word in user_message for word in ("中式", "新中式", "庭院"))
    is_modern = any(word in user_message for word in ("现代", "极简"))
    style = (
        "欧式" if is_european else "中式" if is_chinese else "现代" if is_modern
        else profile["label"]
    )
    roof_type = (
        "hip" if is_european else "chinese_curved" if is_chinese
        else "flat" if is_modern else profile["default_roof"]
    )
    require_entrance = profile["require_front_entrance"]
    front_ground = (
        ["window", "empty", "door", "empty", "window"]
        if require_entrance else ["empty", "empty", "empty", "empty", "empty"]
    )
    base_components = list(profile["base_components"])
    component_quota: dict[str, dict[str, Any]] = {}
    if "door" in base_components:
        component_quota["door"] = {"min": 1, "max": 4, "note": "主入口及必要辅助入口"}
    else:
        component_quota["door"] = {"min": 0, "max": 8, "note": "仅在功能确有入口时生成"}
    if "window" in base_components:
        component_quota["window"] = {
            "min": min(12, 4 + max(0, modeled_floors - 1) * 2),
            "max": 32,
            "note": "按立面轴线对齐",
        }
    else:
        component_quota["window"] = {"min": 0, "max": 24, "note": "按建筑功能选用"}
    component_quota["roof"] = {
        "min": 1 if "roof" in base_components else 0,
        "max": 1 if "roof" in base_components else 0,
        "type": roof_type,
        "note": "覆盖主体体量" if "roof" in base_components else "地下或无屋盖场景不生成",
    }
    if "railing" in base_components:
        component_quota["railing"] = {"min": 0, "max": 4, "note": "仅用于有高差边界"}
    if "light" in base_components:
        component_quota["light"] = {"min": 4, "max": 16, "note": "地下公共空间基础照明"}
    return {
        "schema_version": "1.0",
        "profile": profile["id"],
        "concept": f"{style}、比例清晰、入口有识别度",
        "massing": {
            "shape": "rectangle",
            "width": round(width, 2),
            "depth": round(depth, 2),
            "floors": floors,
            "modeled_floors": modeled_floors,
            "representation_mode": "schematic" if modeled_floors < floors else "full",
            "floor_height": default_floor_height,
            "symmetry": is_european,
        },
        "facades": {
            "front": {
                "bays": 5,
                "entrance_bay": 3,
                "ground_pattern": front_ground,
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
        "component_quota": component_quota,
        "required_components": base_components,
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
    profile = detect_architecture_profile(user_message)
    source = raw if isinstance(raw, dict) else {}
    massing_raw = source.get("massing") if isinstance(source.get("massing"), dict) else {}
    requested_floors = _requested_floors(user_message)
    requested_width = _requested_dimension(user_message, (r"宽(?:度)?",))
    requested_depth = _requested_dimension(user_message, (r"深(?:度)?", r"长(?:度)?"))
    floors = int(_clamp_number(
        requested_floors if requested_floors is not None else massing_raw.get("floors"),
        profile["floor_range"][0],
        profile["floor_range"][1],
        fallback["massing"]["floors"],
    ))
    modeled_floors = int(_clamp_number(
        massing_raw.get("modeled_floors"),
        1,
        min(floors, profile["max_explicit_floors"]),
        min(floors, profile["max_explicit_floors"]),
    ))
    massing = {
        "shape": str(massing_raw.get("shape") or fallback["massing"]["shape"]).lower(),
        "width": round(_clamp_number(
            requested_width if requested_width is not None else massing_raw.get("width"),
            profile["width_range"][0],
            profile["width_range"][1],
            fallback["massing"]["width"],
        ), 2),
        "depth": round(_clamp_number(
            requested_depth if requested_depth is not None else massing_raw.get("depth"),
            profile["depth_range"][0],
            profile["depth_range"][1],
            fallback["massing"]["depth"],
        ), 2),
        "floors": floors,
        "modeled_floors": modeled_floors,
        "representation_mode": "schematic" if modeled_floors < floors else "full",
        "floor_height": round(_clamp_number(
            massing_raw.get("floor_height"),
            2.4,
            12.0 if profile["id"] == "long_span_public" else 6.0,
            fallback["massing"]["floor_height"],
        ), 2),
        "symmetry": bool(massing_raw.get("symmetry", fallback["massing"]["symmetry"])),
    }
    if massing["shape"] not in profile["shapes"]:
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
        if profile["require_front_entrance"] and face == "front" and "door" not in ground:
            ground[entrance_bay - 1] = "door"
        facades[face] = {
            "bays": bays,
            "entrance_bay": entrance_bay,
            "ground_pattern": ground,
            "upper_pattern": upper,
        }

    roof_raw = source.get("roof") if isinstance(source.get("roof"), dict) else {}
    roof_type = str(roof_raw.get("type") or fallback["roof"]["type"]).lower()
    if roof_type not in _SUPPORTED_ROOF_TYPES:
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
    roof_required = "roof" in profile["base_components"]
    quotas["roof"] = {
        **quotas.get("roof", {}),
        "min": 1 if roof_required else 0,
        "max": 1 if roof_required else 0,
        "type": roof_type,
    }

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
    for base_type in profile["base_components"]:
        if base_type not in required_components:
            required_components.append(base_type)
    required_components = [
        component_type for component_type in required_components
        if quotas.get(component_type, {}).get("max", 1) != 0
    ]

    rationale = source.get("design_rationale")
    if not isinstance(rationale, list):
        rationale = fallback["design_rationale"]
    return {
        "schema_version": "1.0",
        "profile": profile["id"],
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
    profile = detect_architecture_profile(user_message)
    massing = plan["massing"]
    facades = plan["facades"]
    score += 10 if plan.get("concept") else 0
    score += 12 if (
        profile["width_range"][0] <= massing["width"] <= profile["width_range"][1]
        and profile["depth_range"][0] <= massing["depth"] <= profile["depth_range"][1]
    ) else 0
    requested = _requested_floors(user_message)
    score += 16 if requested is None or requested == massing["floors"] else -16
    front_ground = facades["front"]["ground_pattern"]
    if profile["require_front_entrance"]:
        score += 15 if "door" in front_ground else -30
    if "window" in profile["base_components"]:
        score += 8 if any(item == "window" for item in front_ground) else 0
    requested_width = _requested_dimension(user_message, (r"宽(?:度)?",))
    requested_depth = _requested_dimension(user_message, (r"深(?:度)?", r"长(?:度)?"))
    if requested_width is not None:
        score += 6 if abs(massing["width"] - requested_width) <= 0.1 else -6
    if requested_depth is not None:
        score += 6 if abs(massing["depth"] - requested_depth) <= 0.1 else -6
    score += 8 if plan.get("required_components") else 0
    score += min(12, len(plan.get("design_rationale", [])) * 3)
    if any(word in user_message for word in ("欧式", "法式", "对称")):
        score += 12 if massing["symmetry"] else -8
        score += 8 if plan["roof"]["type"] in {"hip", "gable"} else -6
    if any(word in user_message for word in ("现代", "极简")):
        score += 8 if plan["roof"]["type"] == "flat" else 0
    if profile["id"] == "high_rise":
        score += 10 if massing["representation_mode"] == "schematic" or massing["floors"] <= 10 else 0
    if profile["id"] == "underground_transport":
        score += 10 if "roof" not in plan.get("required_components", []) else -10
    return score


def select_architecture_plan(raw: object, user_message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """归一化候选并以确定性评分选出一个方案。"""
    profile = detect_architecture_profile(user_message)
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
            "profile": candidate.get("profile", profile["id"]),
            "roof": deepcopy(candidate.get("roof", {})),
            "front_bays": candidate.get("facades", {}).get("front", {}).get("bays"),
            "rationale": list(candidate.get("design_rationale", [])),
        }
        for index, candidate in enumerate(candidates)
    ]
    return candidates[selected_index], {
        "profile": profile["id"],
        "profile_label": profile["label"],
        "candidate_count": len(candidates),
        "candidate_scores": scores,
        "candidate_summaries": candidate_summaries,
        "selected_index": selected_index,
        "used_fallback": not bool(raw),
    }


def build_deterministic_skeleton(plan: dict[str, Any], user_message: str = "") -> dict[str, Any]:
    """在骨架模型不可用时生成可校验的矩形概念骨架。

    该回退只保证结构闭合和后续组件有稳定父对象，不尝试替代复杂建筑设计。
    超过显式建模层数的方案使用完整总高度的示意外壳，避免一次生成数百层元素。
    """
    normalized = normalize_architecture_plan(plan, user_message)
    massing = normalized["massing"]
    width = float(massing["width"])
    depth = float(massing["depth"])
    floors = int(massing["floors"])
    modeled_floors = int(massing["modeled_floors"])
    floor_height = float(massing["floor_height"])
    schematic = massing["representation_mode"] == "schematic"
    total_height = floors * floor_height

    elements: list[dict[str, Any]] = []
    if schematic:
        level_ranges = [(1, 0.0, total_height)]
        floor_levels = [("floor_ground", 0.0), ("floor_top", total_height)]
    else:
        level_ranges = [
            (level + 1, level * floor_height, (level + 1) * floor_height)
            for level in range(modeled_floors)
        ]
        floor_levels = [
            (f"floor_{level + 1}", level * floor_height)
            for level in range(modeled_floors)
        ]

    for floor_id, elevation in floor_levels:
        elements.append({
            "type": "floor",
            "id": floor_id,
            "from": [0.0, elevation, 0.0],
            "to": [width, elevation, depth],
            "thickness": 0.2,
            "material": "concrete",
        })

    for level, base_y, top_y in level_ranges:
        suffix = str(level) if not schematic else "shell"
        elements.extend([
            {
                "type": "wall", "id": f"wall_front_{suffix}",
                "from": [0.0, base_y, 0.0], "to": [width, top_y, 0.0],
                "thickness": 0.24, "material": "wall_finish",
            },
            {
                "type": "wall", "id": f"wall_right_{suffix}",
                "from": [width, base_y, 0.0], "to": [width, top_y, depth],
                "thickness": 0.24, "material": "wall_finish",
            },
            {
                "type": "wall", "id": f"wall_back_{suffix}",
                "from": [width, base_y, depth], "to": [0.0, top_y, depth],
                "thickness": 0.24, "material": "wall_finish",
            },
            {
                "type": "wall", "id": f"wall_left_{suffix}",
                "from": [0.0, base_y, depth], "to": [0.0, top_y, 0.0],
                "thickness": 0.24, "material": "wall_finish",
            },
        ])

    if not schematic and modeled_floors > 1:
        stair_x = max(1.0, min(width - 1.0, width * 0.2))
        stair_z0 = max(0.8, min(depth - 2.0, depth * 0.2))
        stair_z1 = max(stair_z0 + 1.0, min(depth - 0.8, depth * 0.65))
        for level in range(modeled_floors - 1):
            base_y = level * floor_height
            elements.append({
                "type": "stair",
                "id": f"stair_{level + 1}_{level + 2}",
                "from": [stair_x, base_y, stair_z0],
                "to": [stair_x, base_y + floor_height, stair_z1],
                "width": min(1.8, max(1.0, width * 0.08)),
                "material": "concrete",
            })

    if schematic or normalized["profile"] in {"long_span_public", "high_rise"}:
        radius = min(0.6, max(0.2, min(width, depth) * 0.012))
        for index, (x, z) in enumerate((
            (0.5, 0.5), (width - 0.5, 0.5),
            (width - 0.5, depth - 0.5), (0.5, depth - 0.5),
        ), start=1):
            elements.append({
                "type": "column",
                "id": f"column_corner_{index}",
                "base": [x, 0.0, z],
                "height": total_height,
                "bottomRadius": radius,
                "topRadius": radius,
                "style": "modern",
                "material": "concrete",
            })

    return {
        "meta": {
            "version": "1.1",
            "type": "building",
            "name": str(normalized.get("concept") or "确定性回退建筑")[:80],
        },
        "geometry": {"elements": elements, "components": []},
        "materials": {
            "concrete": {
                "baseColor": [0.72, 0.72, 0.72], "roughness": 0.65,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "wall_finish": {
                "baseColor": [0.86, 0.84, 0.80], "roughness": 0.72,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "wood": {
                "baseColor": [0.42, 0.24, 0.12], "roughness": 0.68,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "metal": {
                "baseColor": [0.16, 0.17, 0.18], "roughness": 0.34,
                "metallic": 0.7, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "glass": {
                "baseColor": [0.52, 0.70, 0.82], "roughness": 0.12,
                "metallic": 0.0, "albedo": 1.0, "opacity": 0.35,
                "lightingCondition": "D65_noon",
            },
            "roof": {
                "baseColor": [0.30, 0.31, 0.33], "roughness": 0.75,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
        },
        "behaviors": {},
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
