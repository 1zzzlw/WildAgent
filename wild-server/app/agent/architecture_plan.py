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

_COMPLEXITY_PROFILES: dict[str, dict[str, Any]] = {
    "simple": {
        "min_volumes": 1,
        "min_detail_packages": 0,
        "target_structural_elements": 6,
        "grid_bays": (1, 1),
    },
    "standard": {
        "min_volumes": 1,
        "min_detail_packages": 0,
        "target_structural_elements": 10,
        "grid_bays": (2, 2),
    },
    "detailed": {
        "min_volumes": 2,
        "min_detail_packages": 3,
        "target_structural_elements": 18,
        "grid_bays": (3, 2),
    },
}

_DETAIL_COMPONENT_QUOTAS: dict[str, dict[str, Any]] = {
    "canopy": {"min": 1, "max": 2, "note": "强化主入口进深与阴影层次"},
    "balcony": {"min": 1, "max": 2, "note": "结合二层退台或主立面设置"},
    "bay_window": {"min": 1, "max": 2, "note": "用于重点开间的立面凸出层次"},
    "cornice": {"min": 1, "max": 4, "note": "用于檐口或水平分层线脚"},
    "railing": {"min": 1, "max": 4, "note": "仅用于阳台、露台或高差边界"},
    "ramp": {"min": 1, "max": 1, "note": "公共入口无障碍连接"},
    "light": {"min": 2, "max": 8, "note": "强调入口、檐下和体量转折"},
    "chimney": {"min": 1, "max": 1, "note": "仅用于风格与功能确需的屋面重点"},
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


def resolve_complexity_profile(
    user_message: str,
    precision_mode: bool = False,
) -> dict[str, Any]:
    """把用户表达与运行模式解析为可验证的复杂度目标。"""
    message = user_message.lower()
    simple_words = (
        "简单", "简易", "基础款", "低复杂度", "方盒子", "单一体量",
        "minimal massing", "simple massing",
    )
    detailed_words = (
        "复杂", "高细节", "丰富", "有层次", "层次感", "多体量", "组合体量",
        "退台", "错落", "豪华", "精致", "标志性", "complex", "detailed",
    )
    if any(word in message for word in simple_words):
        level = "simple"
        reason = "用户明确要求简化体量"
    elif precision_mode or any(word in message for word in detailed_words):
        level = "detailed"
        reason = "精密模式默认高复杂度" if precision_mode else "用户明确要求高细节"
    else:
        level = "standard"
        reason = "快速模式默认标准复杂度"

    result = deepcopy(_COMPLEXITY_PROFILES[level])
    result.update({"level": level, "reason": reason})
    result["grid_bays"] = list(result["grid_bays"])
    return result


def _default_detail_packages(
    profile_id: str,
    user_message: str,
    modeled_floors: int,
    complexity: dict[str, Any],
) -> list[str]:
    explicit_keywords = {
        "canopy": ("雨棚", "门廊"),
        "balcony": ("阳台", "露台"),
        "bay_window": ("凸窗", "飘窗"),
        "cornice": ("檐口", "线脚", "飞檐"),
        "railing": ("栏杆", "护栏"),
        "ramp": ("坡道", "无障碍"),
        "light": ("灯光", "灯具", "照明"),
        "chimney": ("烟囱",),
    }
    explicit = [
        component_type
        for component_type, keywords in explicit_keywords.items()
        if any(keyword in user_message for keyword in keywords)
    ]
    if complexity["level"] == "simple":
        return explicit

    is_european = any(word in user_message for word in ("欧式", "法式", "古典"))
    is_chinese = any(word in user_message for word in ("中式", "新中式", "庭院"))
    defaults = {
        "residential_lowrise": (
            ["canopy", "cornice", "railing"] if is_chinese
            else ["balcony", "canopy", "cornice"] if is_european
            else ["balcony", "canopy", "bay_window"]
        ),
        "ordinary_public": ["canopy", "ramp", "light"],
        "long_span_public": ["canopy", "ramp", "light"],
        "high_rise": ["canopy", "balcony", "light"],
        "underground_transport": ["ramp", "light", "railing"],
        "garden_structure": ["cornice", "railing", "light"],
        "religious_landmark": ["cornice", "canopy", "railing"],
    }.get(profile_id, ["canopy", "light", "cornice"])
    if modeled_floors < 2:
        defaults = [item for item in defaults if item != "balcony"]
        if "bay_window" not in defaults and profile_id == "residential_lowrise":
            defaults.append("bay_window")

    target = int(complexity["min_detail_packages"])
    merged = list(dict.fromkeys([*explicit, *defaults]))
    return merged[:max(target, len(explicit))]


def _fallback_volumes(
    width: float,
    depth: float,
    modeled_floors: int,
    complexity: dict[str, Any],
) -> list[dict[str, Any]]:
    if complexity["level"] != "detailed":
        return [{
            "id": "main", "role": "primary", "x": 0.0, "z": 0.0,
            "width": round(width, 2), "depth": round(depth, 2),
            "start_floor": 1, "end_floor": modeled_floors,
        }]
    if modeled_floors >= 2:
        return [
            {
                "id": "base", "role": "primary", "x": 0.0, "z": 0.0,
                "width": round(width, 2), "depth": round(depth, 2),
                "start_floor": 1, "end_floor": 1,
            },
            {
                "id": "upper_setback", "role": "secondary",
                "x": round(width * 0.08, 2), "z": round(depth * 0.06, 2),
                "width": round(width * 0.82, 2), "depth": round(depth * 0.78, 2),
                "start_floor": 2, "end_floor": modeled_floors,
            },
        ]
    return [
        {
            "id": "main_wing", "role": "primary", "x": 0.0, "z": 0.0,
            "width": round(width * 0.68, 2), "depth": round(depth, 2),
            "start_floor": 1, "end_floor": 1,
        },
        {
            "id": "side_wing", "role": "secondary",
            "x": round(width * 0.68, 2), "z": round(depth * 0.15, 2),
            "width": round(width * 0.32, 2), "depth": round(depth * 0.70, 2),
            "start_floor": 1, "end_floor": 1,
        },
    ]


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


def _fallback_plan(
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = detect_architecture_profile(user_message)
    complexity = deepcopy(
        complexity_profile or resolve_complexity_profile(user_message)
    )
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
    detail_packages = _default_detail_packages(
        profile["id"], user_message, modeled_floors, complexity,
    )
    for component_type in detail_packages:
        limits = deepcopy(_DETAIL_COMPONENT_QUOTAS[component_type])
        if component_type == "balcony" and modeled_floors < 2:
            continue
        component_quota.setdefault(component_type, limits)
        if component_type not in base_components:
            base_components.append(component_type)
    volumes = _fallback_volumes(width, depth, modeled_floors, complexity)
    default_x_bays, default_z_bays = complexity["grid_bays"]
    structural_system = (
        "long_span" if profile["id"] == "long_span_public"
        else "frame" if profile["id"] in {"ordinary_public", "high_rise"}
        else "hybrid" if complexity["level"] == "detailed"
        else "wall_bearing"
    )
    return {
        "schema_version": "1.1",
        "profile": profile["id"],
        "concept": f"{style}、比例清晰、入口有识别度",
        "massing": {
            "shape": (
                "stepped"
                if complexity["level"] == "detailed" and "stepped" in profile["shapes"]
                else "rectangle"
            ),
            "width": round(width, 2),
            "depth": round(depth, 2),
            "floors": floors,
            "modeled_floors": modeled_floors,
            "representation_mode": "schematic" if modeled_floors < floors else "full",
            "floor_height": default_floor_height,
            "symmetry": is_european,
        },
        "complexity": complexity,
        "volumes": volumes,
        "structural_grid": {
            "system": structural_system,
            "x_bays": default_x_bays,
            "z_bays": default_z_bays,
        },
        "detail_packages": detail_packages,
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
        "design_rationale": [
            "入口位于主立面视觉中心",
            "上下层门窗沿轴线对齐",
            "体量转折与细部构件共同形成真实进深和阴影层次",
        ],
    }


def _normalize_pattern(value: object, bays: int, fallback: list[str]) -> list[str]:
    raw = value if isinstance(value, list) else fallback
    pattern = [str(item).lower() if str(item).lower() in _OPENING_TYPES else "empty" for item in raw]
    if len(pattern) < bays:
        pattern.extend(["empty"] * (bays - len(pattern)))
    return pattern[:bays]


def _normalize_volumes(
    raw: object,
    massing: dict[str, Any],
    complexity: dict[str, Any],
) -> list[dict[str, Any]]:
    width = float(massing["width"])
    depth = float(massing["depth"])
    modeled_floors = int(massing["modeled_floors"])
    fallback = _fallback_volumes(width, depth, modeled_floors, complexity)
    if not isinstance(raw, list):
        return fallback

    volumes: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:4]):
        if not isinstance(item, dict):
            continue
        x = _clamp_number(item.get("x"), 0, max(0, width - 1), 0)
        z = _clamp_number(item.get("z"), 0, max(0, depth - 1), 0)
        item_width = _clamp_number(item.get("width"), 1, width - x, width - x)
        item_depth = _clamp_number(item.get("depth"), 1, depth - z, depth - z)
        start_floor = int(_clamp_number(item.get("start_floor"), 1, modeled_floors, 1))
        end_floor = int(_clamp_number(
            item.get("end_floor"), start_floor, modeled_floors, modeled_floors,
        ))
        raw_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(item.get("id") or f"volume_{index + 1}"))
        volumes.append({
            "id": raw_id[:48] or f"volume_{index + 1}",
            "role": "secondary" if str(item.get("role")).lower() == "secondary" else "primary",
            "x": round(x, 2),
            "z": round(z, 2),
            "width": round(item_width, 2),
            "depth": round(item_depth, 2),
            "start_floor": start_floor,
            "end_floor": end_floor,
        })
    if len(volumes) < int(complexity["min_volumes"]):
        return fallback
    return volumes


def _normalize_structural_grid(
    raw: object,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    allowed_systems = {"wall_bearing", "frame", "hybrid", "long_span", "shell"}
    system = str(source.get("system") or fallback["system"]).lower()
    if system not in allowed_systems:
        system = fallback["system"]
    return {
        "system": system,
        "x_bays": int(_clamp_number(source.get("x_bays"), 1, 12, fallback["x_bays"])),
        "z_bays": int(_clamp_number(source.get("z_bays"), 1, 12, fallback["z_bays"])),
    }


def normalize_architecture_plan(
    raw: object,
    user_message: str = "",
    complexity_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把模型方案压缩到稳定、有限的架构规划协议。"""
    complexity = deepcopy(
        complexity_profile or resolve_complexity_profile(user_message)
    )
    fallback = _fallback_plan(user_message, complexity)
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

    volumes = _normalize_volumes(source.get("volumes"), massing, complexity)
    structural_grid = _normalize_structural_grid(
        source.get("structural_grid"), fallback["structural_grid"],
    )
    raw_detail_packages = source.get("detail_packages")
    allowed_detail_packages = set(_DETAIL_COMPONENT_QUOTAS)
    if isinstance(raw_detail_packages, list):
        detail_packages = [
            str(item).lower() for item in raw_detail_packages
            if str(item).lower() in allowed_detail_packages
        ]
    else:
        detail_packages = list(fallback["detail_packages"])
    if len(detail_packages) < int(complexity["min_detail_packages"]):
        detail_packages = list(dict.fromkeys([
            *detail_packages,
            *fallback["detail_packages"],
        ]))
    detail_packages = detail_packages[:6]

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
    for component_type in detail_packages:
        if component_type == "balcony" and modeled_floors < 2:
            continue
        quotas.setdefault(
            component_type,
            deepcopy(_DETAIL_COMPONENT_QUOTAS[component_type]),
        )

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
    for component_type in detail_packages:
        if component_type not in required_components:
            required_components.append(component_type)
    required_components = [
        component_type for component_type in required_components
        if quotas.get(component_type, {}).get("max", 1) != 0
    ]

    rationale = source.get("design_rationale")
    if not isinstance(rationale, list):
        rationale = fallback["design_rationale"]
    return {
        "schema_version": "1.1",
        "profile": profile["id"],
        "concept": str(source.get("concept") or fallback["concept"])[:240],
        "massing": massing,
        "complexity": complexity,
        "volumes": volumes,
        "structural_grid": structural_grid,
        "detail_packages": detail_packages,
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
    complexity = plan.get("complexity", {})
    if complexity.get("level") == "detailed":
        volume_count = len(plan.get("volumes", []))
        detail_count = len(plan.get("detail_packages", []))
        score += 14 if volume_count >= int(complexity.get("min_volumes", 2)) else -24
        score += 12 if detail_count >= int(complexity.get("min_detail_packages", 3)) else -18
        score += 8 if massing["shape"] != "rectangle" or volume_count > 1 else -12
        grid = plan.get("structural_grid", {})
        score += 6 if int(grid.get("x_bays", 1)) >= 2 and int(grid.get("z_bays", 1)) >= 2 else -6
    return score


def select_architecture_plan(
    raw: object,
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """归一化候选并以确定性评分选出一个方案。"""
    profile = detect_architecture_profile(user_message)
    source = raw if isinstance(raw, dict) else {}
    candidates_raw = source.get("candidates") if isinstance(source.get("candidates"), list) else [source]
    candidates = [
        normalize_architecture_plan(item, user_message, complexity_profile)
        for item in candidates_raw[:4]
    ]
    if not candidates:
        candidates = [normalize_architecture_plan({}, user_message, complexity_profile)]
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
            "complexity": deepcopy(candidate.get("complexity", {})),
            "volume_count": len(candidate.get("volumes", [])),
            "detail_packages": list(candidate.get("detail_packages", [])),
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


def _resolve_floor_plate_plan(
    volumes: list[dict[str, Any]],
    modeled_floors: int,
    floor_height: float,
) -> list[dict[str, Any]]:
    """生成各楼层标高的非重复楼板覆盖。

    退台交接层必须由下层体量的完整顶板封闭；上层较小体量的底板若已被
    该顶板包含，则不能再生成一块共面楼板。
    """
    plates: list[dict[str, Any]] = []
    tolerance = 0.01

    def bounds(volume: dict[str, Any]) -> tuple[float, float, float, float]:
        x0 = float(volume["x"])
        z0 = float(volume["z"])
        return (
            x0,
            z0,
            x0 + float(volume["width"]),
            z0 + float(volume["depth"]),
        )

    def contains(
        outer: tuple[float, float, float, float],
        inner: tuple[float, float, float, float],
    ) -> bool:
        return (
            outer[0] <= inner[0] + tolerance
            and outer[1] <= inner[1] + tolerance
            and outer[2] >= inner[2] - tolerance
            and outer[3] >= inner[3] - tolerance
        )

    for level in range(1, modeled_floors + 1):
        current = [
            volume for volume in volumes
            if int(volume["start_floor"]) <= level <= int(volume["end_floor"])
        ]
        supporting = [] if level == 1 else [
            volume for volume in volumes
            if int(volume["start_floor"]) <= level - 1 <= int(volume["end_floor"])
        ]
        candidates = [*supporting, *current]
        if not candidates:
            continue

        ranked = sorted(
            candidates,
            key=lambda volume: (
                -(float(volume["width"]) * float(volume["depth"])),
                str(volume["id"]),
            ),
        )
        selected: list[tuple[dict[str, Any], tuple[float, float, float, float]]] = []
        for volume in ranked:
            footprint = bounds(volume)
            if any(contains(existing, footprint) for _, existing in selected):
                continue
            selected.append((volume, footprint))

        for volume, footprint in selected:
            plates.append({
                "level": level,
                "elevation": round((level - 1) * floor_height, 3),
                "volume_id": str(volume["id"]),
                "bounds": footprint,
            })
    return plates


def evaluate_skeleton_complexity(
    blueprint: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """评估骨架是否兑现方案中的结构数量和体量层次目标。"""
    elements = [
        item for item in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(item, dict)
    ]
    counts: dict[str, int] = {}
    floor_footprints: set[tuple[float, ...]] = set()
    floor_layouts: set[tuple[float, ...]] = set()
    wall_groups: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for element in elements:
        element_type = str(element.get("type") or "unknown")
        counts[element_type] = counts.get(element_type, 0) + 1
        if element_type == "floor":
            start = element.get("from")
            end = element.get("to")
            if isinstance(start, list) and isinstance(end, list) and len(start) == 3 and len(end) == 3:
                floor_footprints.add(tuple(round(float(value), 2) for value in (
                    start[0], start[2], end[0], end[2],
                )))
                floor_layouts.add(tuple(round(float(value), 2) for value in (
                    start[1], start[0], start[2], end[0], end[2],
                )))
        elif element_type == "wall":
            start = element.get("from")
            end = element.get("to")
            if isinstance(start, list) and isinstance(end, list) and len(start) == 3 and len(end) == 3:
                vertical_range = tuple(sorted((round(float(start[1]), 2), round(float(end[1]), 2))))
                wall_groups.setdefault(vertical_range, []).append(element)

    volume_footprints: set[tuple[float, ...]] = set()
    for walls in wall_groups.values():
        pending = set(range(len(walls)))
        while pending:
            component = {pending.pop()}
            changed = True
            while changed:
                changed = False
                component_points = [
                    (float(walls[index][field][0]), float(walls[index][field][2]))
                    for index in component for field in ("from", "to")
                ]
                for index in list(pending):
                    wall_points = [
                        (float(walls[index][field][0]), float(walls[index][field][2]))
                        for field in ("from", "to")
                    ]
                    if any(
                        math.hypot(first[0] - second[0], first[1] - second[1]) <= 0.05
                        for first in component_points for second in wall_points
                    ):
                        pending.remove(index)
                        component.add(index)
                        changed = True
            connected_walls = [walls[index] for index in component]
            xs = [
                float(point) for wall in connected_walls
                for point in (wall["from"][0], wall["to"][0])
            ]
            zs = [
                float(point) for wall in connected_walls
                for point in (wall["from"][2], wall["to"][2])
            ]
            volume_footprints.add(tuple(round(value, 2) for value in (
                min(xs), min(zs), max(xs), max(zs),
            )))

    complexity = plan.get("complexity", {}) if isinstance(plan, dict) else {}
    level = str(complexity.get("level") or "standard")
    structural_count = sum(
        counts.get(item, 0) for item in ("wall", "floor", "column", "beam", "stair")
    )
    volume_target = min(
        int(complexity.get("min_volumes", 1)),
        max(1, len(plan.get("volumes", []))),
    )
    target = int(complexity.get("target_structural_elements", 6))
    massing = plan.get("massing", {})
    floor_height = float(massing.get("floor_height", 3.2))
    plan_volumes = [
        volume for volume in plan.get("volumes", [])
        if isinstance(volume, dict)
    ]
    modeled_floors = int(massing.get("modeled_floors", massing.get("floors", 1)))
    expected_floor_layouts = {
        tuple(round(value, 2) for value in (
            plate["elevation"], *plate["bounds"],
        ))
        for plate in _resolve_floor_plate_plan(plan_volumes, modeled_floors, floor_height)
    }
    checks = {
        "structural_element_target": structural_count >= target,
        "volume_footprint_target": len(volume_footprints) >= volume_target,
        "volume_plan_conformance": (
            not expected_floor_layouts or floor_layouts == expected_floor_layouts
        ),
        "structural_type_diversity": len([value for value in counts.values() if value]) >= 3,
    }
    return {
        "level": level,
        "meets_target": (
            checks["volume_plan_conformance"]
            and (level != "detailed" or all(checks.values()))
        ),
        "checks": checks,
        "structural_element_count": structural_count,
        "target_structural_elements": target,
        "floor_footprint_count": len(floor_footprints),
        "volume_footprint_count": len(volume_footprints),
        "floor_layout_count": len(floor_layouts),
        "expected_floor_layout_count": len(expected_floor_layouts),
        "target_volume_footprints": volume_target,
        "element_type_counts": counts,
    }


def build_deterministic_skeleton(plan: dict[str, Any], user_message: str = "") -> dict[str, Any]:
    """在骨架模型不可用或复杂度不足时生成可校验的体量化概念骨架。

    full 模式按方案 volumes 落实组合体量；schematic 模式仍使用完整总高度外壳，
    避免一次生成数百层元素。
    """
    normalized = normalize_architecture_plan(
        plan,
        user_message,
        plan.get("complexity") if isinstance(plan, dict) else None,
    )
    massing = normalized["massing"]
    width = float(massing["width"])
    depth = float(massing["depth"])
    floors = int(massing["floors"])
    modeled_floors = int(massing["modeled_floors"])
    floor_height = float(massing["floor_height"])
    schematic = massing["representation_mode"] == "schematic"
    total_height = floors * floor_height
    volumes = normalized.get("volumes") or _fallback_volumes(
        width, depth, modeled_floors, normalized["complexity"],
    )

    elements: list[dict[str, Any]] = []
    if schematic:
        level_ranges = [(1, 0.0, total_height)]
        for floor_id, elevation in (("floor_ground", 0.0), ("floor_top", total_height)):
            elements.append({
                "type": "floor", "id": floor_id,
                "from": [0.0, elevation, 0.0],
                "to": [width, elevation, depth],
                "thickness": 0.2, "material": "concrete",
            })
        for level, base_y, top_y in level_ranges:
            elements.extend([
                {
                    "type": "wall", "id": "wall_front_shell",
                    "from": [0.0, base_y, 0.0], "to": [width, top_y, 0.0],
                    "thickness": 0.24, "material": "wall_finish",
                },
                {
                    "type": "wall", "id": "wall_right_shell",
                    "from": [width, base_y, 0.0], "to": [width, top_y, depth],
                    "thickness": 0.24, "material": "wall_finish",
                },
                {
                    "type": "wall", "id": "wall_back_shell",
                    "from": [width, base_y, depth], "to": [0.0, top_y, depth],
                    "thickness": 0.24, "material": "wall_finish",
                },
                {
                    "type": "wall", "id": "wall_left_shell",
                    "from": [0.0, base_y, depth], "to": [0.0, top_y, 0.0],
                    "thickness": 0.24, "material": "wall_finish",
                },
            ])
    else:
        detailed = normalized["complexity"]["level"] == "detailed"
        floor_plates = _resolve_floor_plate_plan(volumes, modeled_floors, floor_height)
        for level in range(1, modeled_floors + 1):
            active_volumes = [
                volume for volume in volumes
                if int(volume["start_floor"]) <= level <= int(volume["end_floor"])
            ] or [
                {
                    "id": "main", "x": 0.0, "z": 0.0,
                    "width": width, "depth": depth,
                }
            ]
            base_y = (level - 1) * floor_height
            top_y = level * floor_height
            for plate in (item for item in floor_plates if item["level"] == level):
                x0, z0, x1, z1 = plate["bounds"]
                elements.append({
                    "type": "floor",
                    "id": f"floor_{level}_{plate['volume_id']}",
                    "from": [x0, plate["elevation"], z0],
                    "to": [x1, plate["elevation"], z1],
                    "thickness": 0.2,
                    "material": "concrete",
                })
            for volume_index, volume in enumerate(active_volumes):
                volume_id = str(volume["id"])
                x0 = float(volume["x"])
                z0 = float(volume["z"])
                x1 = x0 + float(volume["width"])
                z1 = z0 + float(volume["depth"])
                suffix = f"{level}_{volume_id}" if detailed or len(active_volumes) > 1 else str(level)
                elements.extend([
                    {
                        "type": "wall", "id": f"wall_front_{suffix}",
                        "from": [x0, base_y, z0], "to": [x1, top_y, z0],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                    {
                        "type": "wall", "id": f"wall_right_{suffix}",
                        "from": [x1, base_y, z0], "to": [x1, top_y, z1],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                    {
                        "type": "wall", "id": f"wall_back_{suffix}",
                        "from": [x1, base_y, z1], "to": [x0, top_y, z1],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                    {
                        "type": "wall", "id": f"wall_left_{suffix}",
                        "from": [x0, base_y, z1], "to": [x0, top_y, z0],
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

    if normalized["complexity"]["level"] == "detailed" and not schematic:
        radius = min(0.35, max(0.16, min(width, depth) * 0.015))
        for volume in volumes:
            x0 = float(volume["x"])
            z0 = float(volume["z"])
            x1 = x0 + float(volume["width"])
            z1 = z0 + float(volume["depth"])
            inset = min(0.35, float(volume["width"]) * 0.08, float(volume["depth"]) * 0.08)
            base_y = (int(volume["start_floor"]) - 1) * floor_height
            volume_height = (int(volume["end_floor"]) - int(volume["start_floor"]) + 1) * floor_height
            if int(volume["start_floor"]) > 1:
                base_y += 0.2
                volume_height = max(0.5, volume_height - 0.2)
            volume_id = str(volume["id"])
            corners = (
                (x0 + inset, z0 + inset), (x1 - inset, z0 + inset),
                (x1 - inset, z1 - inset), (x0 + inset, z1 - inset),
            )
            for index, (x, z) in enumerate(corners, start=1):
                elements.append({
                    "type": "column", "id": f"column_{volume_id}_{index}",
                    "base": [x, base_y, z], "height": volume_height,
                    "bottomRadius": radius, "topRadius": radius,
                    "style": "modern", "material": "concrete",
                })
            beam_y = base_y + volume_height
            elements.append({
                "type": "beam", "id": f"beam_main_{volume_id}",
                "from": [x0 + inset, beam_y, (z0 + z1) / 2],
                "to": [x1 - inset, beam_y, (z0 + z1) / 2],
                "crossSection": "rect", "width": 0.18, "height": 0.28,
                "material": "concrete",
            })
    elif schematic or normalized["profile"] in {"long_span_public", "high_rise"}:
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

    min_y = min(wall["base_y"] for wall in walls)
    level_bounds: dict[float, dict[str, float]] = {}
    for wall in walls:
        level_key = round(float(wall["base_y"]), 3)
        bounds = level_bounds.setdefault(level_key, {
            "min_x": wall["x"], "max_x": wall["x"],
            "min_z": wall["z"], "max_z": wall["z"],
        })
        bounds["min_x"] = min(bounds["min_x"], wall["x"])
        bounds["max_x"] = max(bounds["max_x"], wall["x"])
        bounds["min_z"] = min(bounds["min_z"], wall["z"])
        bounds["max_z"] = max(bounds["max_z"], wall["z"])

    facade_plan: dict[str, dict[str, Any]] = {}
    slots: list[dict[str, Any]] = []
    for wall in sorted(walls, key=lambda item: (item["base_y"], str(item["id"]))):
        bounds = level_bounds[round(float(wall["base_y"]), 3)]
        span = max(
            bounds["max_x"] - bounds["min_x"],
            bounds["max_z"] - bounds["min_z"],
            1.0,
        )
        boundary_tolerance = max(0.35, span * 0.04)
        if wall["axis"] == "x":
            distances = {
                "front": abs(wall["z"] - bounds["min_z"]),
                "back": abs(wall["z"] - bounds["max_z"]),
            }
        else:
            distances = {
                "left": abs(wall["x"] - bounds["min_x"]),
                "right": abs(wall["x"] - bounds["max_x"]),
            }
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
    """把模型门窗吸附到槽位，并补足设计下限；凸窗优先占用普通窗槽位。"""
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
    non_openings = [
        item for item in components
        if item.get("type") not in {"door", "window", "bay_window"}
    ]
    result_openings: list[dict[str, Any]] = []
    stats = {"snapped": 0, "synthesized": 0, "pruned": 0}
    quotas = design_brief.get("component_quota", {})
    all_slots = design_brief["opening_slots"]

    # 凸窗本质上也是父墙洞口。先让它占用最近的普通窗槽位，后续普通窗只能
    # 使用剩余槽位，从源头避免独立节点生成的凸窗和门窗在合并后重复切洞。
    window_slots = [
        slot for slot in all_slots
        if isinstance(slot, dict) and slot.get("type") == "window"
    ]
    used_window_slots: set[str] = set()
    bay_windows = [deepcopy(item) for item in components if item.get("type") == "bay_window"]
    for bay_window in bay_windows:
        available = [slot for slot in window_slots if slot["id"] not in used_window_slots]
        if not available:
            stats["pruned"] += 1
            continue
        original_from = bay_window.get("from", [0, 0, 0])
        original_center = (
            float(original_from[0]) + float(bay_window.get("width", 0)) / 2
            if isinstance(original_from, list) and original_from else 0.0
        )
        original_y = (
            float(original_from[1])
            if isinstance(original_from, list) and len(original_from) > 1 else 0.0
        )

        def bay_slot_rank(slot: dict[str, Any]) -> tuple[int, float, float, str]:
            slot_from = slot.get("from", [0, 0, 0])
            return (
                0 if slot.get("wall_id") == bay_window.get("parentWall") else 1,
                abs(float(slot_from[1]) - original_y),
                abs(float(slot_from[0]) + float(slot.get("width", 0)) / 2 - original_center),
                str(slot.get("id", "")),
            )

        slot = min(available, key=bay_slot_rank)
        used_window_slots.add(slot["id"])
        bay_window["parentWall"] = slot["wall_id"]
        bay_window["from"] = deepcopy(slot["from"])
        bay_window["width"] = slot["width"]
        bay_window["height"] = slot["height"]
        result_openings.append(bay_window)
        stats["snapped"] += 1

    for opening_type in ("door", "window"):
        items = [deepcopy(item) for item in components if item.get("type") == opening_type]
        slots = [
            slot for slot in all_slots
            if isinstance(slot, dict)
            and slot.get("type") == opening_type
            and (opening_type != "window" or slot["id"] not in used_window_slots)
        ]
        limits = quotas.get(opening_type, {}) if isinstance(quotas.get(opening_type), dict) else {}
        bay_count = (
            sum(1 for item in result_openings if item.get("type") == "bay_window")
            if opening_type == "window" else 0
        )
        maximum = min(len(slots), max(0, int(limits.get("max", len(slots))) - bay_count))
        minimum = min(maximum, max(0, int(limits.get("min", 0)) - bay_count))
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
