"""建筑方案归一化、候选评分与确定性立面槽位解析。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import re
from typing import Any

from app.agent.facade_recipe import load_curtain_wall_parameters


_FACES = ("front", "back", "left", "right")
_OPENING_TYPES = {"door", "window", "empty"}
_SUPPORTED_ROOF_TYPES = {
    "flat", "gable", "hip", "dome", "chinese_curved", "chinese_pagoda",
}

_COMPLEXITY_PROFILES: dict[str, dict[str, Any]] = {
    "minimal": {
        "min_volumes": 1,
        "min_detail_packages": 0,
        "target_structural_elements": 1,
        "grid_bays": (1, 1),
    },
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
        "shapes": {"rectangle", "l_shape", "u_shape", "stepped", "courtyard"},
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
        "shapes": {"rectangle", "l_shape", "u_shape", "stepped", "courtyard", "linear"},
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
    candidates = [
        max(1, int(match.group(1)))
        for match in re.finditer(r"(?<!\d)(\d{1,3})\s*层", user_message)
    ]
    if "单层" in user_message:
        candidates.append(1)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    for chinese_match in re.finditer(r"([零一二两三四五六七八九十百]+)\s*层", user_message):
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
        candidates.append(max(1, total + current))
    return max(candidates) if candidates else None


def _requested_shape(user_message: str) -> str | None:
    """提取用户明确指定的平面/体量形状，优先于模型方案中的旧值。"""
    if re.search(r"(?:^|[^a-z])u\s*(?:形|型)", user_message, re.I):
        return "u_shape"
    if re.search(r"(?:^|[^a-z])l\s*(?:形|型)", user_message, re.I):
        return "l_shape"
    if any(word in user_message for word in ("庭院", "合院", "围合院落")):
        return "courtyard"
    if "退台" in user_message:
        return "stepped"
    if any(word in user_message for word in ("矩形", "方盒子")):
        return "rectangle"
    return None


def _requested_balcony_access_count(user_message: str) -> int:
    """识别明确要求阳台与室内直接连通的入口数量。"""
    if "阳台" not in user_message or not any(
        phrase in user_message
        for phrase in ("直接通向室内", "直接通室内", "后面没有墙体", "后面没有墙")
    ):
        return 0
    if "两端分别" in user_message or re.search(r"(?:两个|2\s*个).*阳台", user_message):
        return 2
    match = re.search(r"(\d+)\s*个[^，。；]*阳台", user_message)
    return max(1, min(4, int(match.group(1)))) if match else 1


def _requested_dimension(user_message: str, labels: tuple[str, ...]) -> float | None:
    number = r"(\d+(?:\.\d+)?)"
    for label in labels:
        for pattern in (fr"{label}\s*{number}\s*(?:米|m)?", fr"{number}\s*(?:米|m)?\s*{label}"):
            for match in re.finditer(pattern, user_message, re.I):
                clause_start = max(
                    user_message.rfind(mark, 0, match.start())
                    for mark in ("，", "。", "；", ";")
                ) + 1
                following = [
                    position for mark in ("，", "。", "；", ";")
                    if (position := user_message.find(mark, match.end())) >= 0
                ]
                clause_end = min(following) if following else len(user_message)
                context = user_message[clause_start:clause_end]
                if any(word in context for word in (
                    "阳台", "门", "窗", "栏杆", "雨棚", "楼梯", "走廊", "开间", "柱", "梁",
                )):
                    continue
                return float(match.group(1))
    return None


def _requested_plan_dimensions(user_message: str) -> tuple[float, float] | None:
    """识别明确描述建筑平面或标准层的 ``宽×深`` 组合尺寸。"""
    number = r"(\d+(?:\.\d+)?)"
    pattern = re.compile(fr"{number}\s*[×xX*]\s*{number}\s*(?:米|m)?", re.I)
    plan_terms = ("标准层", "平面", "占地", "建筑尺寸", "楼体尺寸", "塔楼尺寸")
    excluded_terms = ("阳台", "门", "窗", "雨棚", "楼梯", "走廊", "开间", "柱", "梁", "房间")
    for match in pattern.finditer(user_message):
        local_context = user_message[max(0, match.start() - 18):match.end() + 8]
        if not any(term in local_context for term in plan_terms):
            continue
        prefix = local_context[:local_context.find(match.group(0))]
        if any(term in prefix for term in excluded_terms):
            continue
        return float(match.group(1)), float(match.group(2))
    return None


def _requested_balcony_width(user_message: str) -> float | None:
    patterns = (
        r"宽\s*(\d+(?:\.\d+)?)\s*(?:米|m)?[^，。；]{0,16}阳台",
        r"阳台[^，。；]{0,16}?宽\s*(\d+(?:\.\d+)?)\s*(?:米|m)?",
    )
    for pattern in patterns:
        match = re.search(pattern, user_message, re.I)
        if match:
            return max(0.8, min(6.0, float(match.group(1))))
    return None


def resolve_complexity_profile(
    user_message: str,
    precision_mode: bool = False,
) -> dict[str, Any]:
    """把用户表达与运行模式解析为可验证的复杂度目标。"""
    message = user_message.lower()
    minimal_words = (
        "一面墙", "一堵墙", "单面墙", "一面幕墙", "单面幕墙", "只要一面",
        "只要一堵", "单个构件", "单个元素", "一面玻璃", "一块楼板", "一根柱",
        "一根梁", "一堵",
    )
    simple_words = (
        "简单", "简易", "基础款", "低复杂度", "方盒子", "单一体量",
        "minimal massing", "simple massing",
    )
    detailed_words = (
        "复杂", "高细节", "丰富", "有层次", "层次感", "多体量", "组合体量",
        "退台", "错落", "豪华", "精致", "标志性", "complex", "detailed",
    )
    if any(word in message for word in minimal_words):
        level = "minimal"
        reason = "用户明确要求极简结构"
    elif any(word in message for word in simple_words):
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
    if complexity["level"] in ("simple", "minimal"):
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
    shape: str | None = None,
) -> list[dict[str, Any]]:
    if shape == "u_shape" and modeled_floors >= 2:
        wing_width = min(width * 0.4, max(1.5, width * 0.28))
        back_depth = min(depth * 0.45, max(1.5, depth * 0.32))
        center_width = width - wing_width * 2
        if center_width >= 1.0:
            return [
                {
                    "id": "base", "role": "primary", "x": 0.0, "z": 0.0,
                    "width": round(width, 2), "depth": round(depth, 2),
                    "start_floor": 1, "end_floor": 1,
                },
                {
                    "id": "upper_left_wing", "role": "secondary", "x": 0.0, "z": 0.0,
                    "width": round(wing_width, 2), "depth": round(depth, 2),
                    "start_floor": 2, "end_floor": modeled_floors,
                },
                {
                    "id": "upper_right_wing", "role": "secondary",
                    "x": round(width - wing_width, 2), "z": 0.0,
                    "width": round(wing_width, 2), "depth": round(depth, 2),
                    "start_floor": 2, "end_floor": modeled_floors,
                },
                {
                    "id": "upper_back_link", "role": "secondary",
                    "x": round(wing_width, 2), "z": round(depth - back_depth, 2),
                    "width": round(center_width, 2), "depth": round(back_depth, 2),
                    "start_floor": 2, "end_floor": modeled_floors,
                },
            ]
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
        any(word in message for word in ("超高层", "高层", "摩天", "高层写字楼", "高层办公", "塔楼"))
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
    requested_plan_dimensions = _requested_plan_dimensions(user_message)
    requested_width = _requested_dimension(user_message, (r"宽(?:度)?",))
    requested_depth = _requested_dimension(user_message, (r"深(?:度)?", r"长(?:度)?"))
    if requested_plan_dimensions:
        requested_width = requested_width or requested_plan_dimensions[0]
        requested_depth = requested_depth or requested_plan_dimensions[1]
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
    curtain_wall = "玻璃幕墙" in user_message or "玻璃幕" in user_message
    component_quota: dict[str, dict[str, Any]] = {}
    if "door" in base_components:
        component_quota["door"] = {"min": 1, "max": 4, "note": "主入口及必要辅助入口"}
    else:
        component_quota["door"] = {"min": 0, "max": 8, "note": "仅在功能确有入口时生成"}
    if "window" in base_components:
        if profile["id"] == "high_rise":
            repeated_window_count = min(160, max(16, floors * 4))
            component_quota["window"] = {
                "min": repeated_window_count,
                "max": repeated_window_count,
                "note": "按标准层标高与立面轴线均匀重复",
            }
        else:
            component_quota["window"] = {
                "min": min(12, 4 + max(0, modeled_floors - 1) * 2),
                "max": 32,
                "note": "按立面轴线对齐",
            }
    else:
        component_quota["window"] = {"min": 0, "max": 24, "note": "按建筑功能选用"}
    if curtain_wall:
        component_quota["window"] = {
            "min": 1,
            "max": 480,
            "note": "水平模数化幕墙网格窗，实际数量由立面槽位决定",
        }
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
    balcony_access_count = (
        _requested_balcony_access_count(user_message) if modeled_floors >= 2 else 0
    )
    balcony_width = _requested_balcony_width(user_message)
    if balcony_access_count:
        component_quota["balcony"] = {
            **component_quota.get("balcony", {}),
            "min": balcony_access_count,
            "max": balcony_access_count,
            "note": "两翼阳台均需与室内直接连通",
        }
        entrance_count = 1 if require_entrance else 0
        component_quota["door"] = {
            **component_quota.get("door", {}),
            "min": entrance_count + balcony_access_count,
            "max": max(
                entrance_count + balcony_access_count,
                int(component_quota.get("door", {}).get("max", 0)),
            ),
            "note": "含主入口与阳台通室内入口",
        }
    requested_shape = _requested_shape(user_message)
    resolved_shape = (
        requested_shape
        if requested_shape in profile["shapes"]
        else "stepped"
        if complexity["level"] == "detailed" and "stepped" in profile["shapes"]
        else "rectangle"
    )
    volumes = _fallback_volumes(
        width, depth, modeled_floors, complexity, resolved_shape,
    )
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
            "shape": resolved_shape,
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
        "facades": (
            {
                "front": {
                    "bays": 6,
                    "entrance_bay": 3,
                    "ground_pattern": ["window", "window", "door", "window", "window", "window"],
                    "upper_pattern": ["window"] * 6,
                },
                "back": {
                    "bays": 5,
                    "ground_pattern": ["window"] * 5,
                    "upper_pattern": ["window"] * 5,
                },
                "left": {
                    "bays": 4,
                    "ground_pattern": ["window"] * 4,
                    "upper_pattern": ["window"] * 4,
                },
                "right": {
                    "bays": 4,
                    "ground_pattern": ["window"] * 4,
                    "upper_pattern": ["window"] * 4,
                },
            }
            if curtain_wall
            else {
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
            }
        ),
        "roof": {"type": roof_type, "ridge_axis": "x", "overhang": 0.55},
        "component_quota": component_quota,
        "curtain_wall": curtain_wall,
        "balcony_access_count": balcony_access_count,
        "balcony_width": balcony_width,
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
    fallback = _fallback_volumes(
        width, depth, modeled_floors, complexity, str(massing.get("shape") or ""),
    )
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
    if len({volume["id"] for volume in volumes}) != len(volumes):
        return fallback

    # 同一楼层的正面积重叠会让每个矩形体量各自生成一套墙柱，造成重影。
    # 相邻体量共享边合法；缺少任一显式楼层的体量则说明旧方案与用户层数冲突。
    for first_index, first in enumerate(volumes):
        first_x1 = first["x"] + first["width"]
        first_z1 = first["z"] + first["depth"]
        for second in volumes[first_index + 1:]:
            floors_overlap = (
                max(first["start_floor"], second["start_floor"])
                <= min(first["end_floor"], second["end_floor"])
            )
            if not floors_overlap:
                continue
            overlap_x = min(first_x1, second["x"] + second["width"]) - max(first["x"], second["x"])
            overlap_z = min(first_z1, second["z"] + second["depth"]) - max(first["z"], second["z"])
            if overlap_x > 0.01 and overlap_z > 0.01:
                return fallback
    if any(
        not any(volume["start_floor"] <= level <= volume["end_floor"] for volume in volumes)
        for level in range(1, modeled_floors + 1)
    ):
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
    curtain_wall = bool(fallback.get("curtain_wall"))
    massing_raw = source.get("massing") if isinstance(source.get("massing"), dict) else {}
    requested_floors = _requested_floors(user_message)
    requested_shape = _requested_shape(user_message)
    requested_balcony_width = _requested_balcony_width(user_message)
    requested_balcony_access_count = _requested_balcony_access_count(user_message)
    requested_plan_dimensions = _requested_plan_dimensions(user_message)
    requested_width = _requested_dimension(user_message, (r"宽(?:度)?",))
    requested_depth = _requested_dimension(user_message, (r"深(?:度)?", r"长(?:度)?"))
    if requested_plan_dimensions:
        requested_width = requested_width or requested_plan_dimensions[0]
        requested_depth = requested_depth or requested_plan_dimensions[1]
    floors = int(_clamp_number(
        requested_floors if requested_floors is not None else massing_raw.get("floors"),
        profile["floor_range"][0],
        profile["floor_range"][1],
        fallback["massing"]["floors"],
    ))
    modeled_floors = int(_clamp_number(
        min(floors, profile["max_explicit_floors"])
        if requested_floors is not None
        else massing_raw.get("modeled_floors"),
        1,
        min(floors, profile["max_explicit_floors"]),
        min(floors, profile["max_explicit_floors"]),
    ))
    massing = {
        "shape": str(
            requested_shape or massing_raw.get("shape") or fallback["massing"]["shape"]
        ).lower(),
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
    if (
        massing["shape"] == "u_shape"
        and requested_balcony_width is not None
        and requested_balcony_access_count >= 2
    ):
        minimum_u_width = requested_balcony_width * 2 + max(2.0, requested_balcony_width)
        target_u_width = minimum_u_width
        if requested_width is None and massing["width"] <= minimum_u_width + 0.01:
            target_u_width = max(target_u_width, float(fallback["massing"]["width"]))
        massing["width"] = round(max(massing["width"], target_u_width), 2)

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
        if curtain_wall:
            # 幕墙立面轴网必须密铺；模型输出不得用稀疏「窗/空」模式覆盖默认窗格。
            bays = int(base["bays"])
            ground = _normalize_pattern(base["ground_pattern"], bays, base["ground_pattern"])
            upper = _normalize_pattern(base["upper_pattern"], bays, base["upper_pattern"])
            entrance_bay = int(base.get("entrance_bay", 1))
        else:
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
        if curtain_wall and component_type == "window":
            # 幕墙窗数量由立面槽位决定，模型配额不得覆盖密集窗格。
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
    balcony_access_count = requested_balcony_access_count if modeled_floors >= 2 else 0
    balcony_width = requested_balcony_width
    if balcony_access_count:
        quotas["balcony"] = {
            **quotas.get("balcony", {}),
            "min": balcony_access_count,
            "max": balcony_access_count,
            "note": "两翼阳台均需与室内直接连通",
        }
        entrance_count = 1 if profile["require_front_entrance"] else 0
        door_target = entrance_count + balcony_access_count
        quotas["door"] = {
            **quotas.get("door", {}),
            "min": max(door_target, int(quotas.get("door", {}).get("min", 0))),
            "max": max(door_target, int(quotas.get("door", {}).get("max", 0))),
            "note": "含主入口与阳台通室内入口",
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
    for component_type in detail_packages:
        if component_type not in required_components:
            required_components.append(component_type)
    # component_quota 是批准后的硬约束；若模型漏写 required_components，
    # 仍必须派发所有最低数量大于零的已实现组件。
    for component_type, limits in quotas.items():
        minimum = limits.get("min", 0) if isinstance(limits, dict) else 0
        if (
            component_type in allowed_components
            and isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and minimum > 0
            and component_type not in required_components
        ):
            required_components.append(component_type)
    required_components = [
        component_type for component_type in required_components
        if quotas.get(component_type, {}).get("max", 1) != 0
    ]
    if complexity.get("level") == "minimal":
        required_components = []

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
        "curtain_wall": curtain_wall,
        "balcony_access_count": balcony_access_count,
        "balcony_width": balcony_width,
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
    requested_plan_dimensions = _requested_plan_dimensions(user_message)
    if requested_plan_dimensions:
        requested_width = requested_width or requested_plan_dimensions[0]
        requested_depth = requested_depth or requested_plan_dimensions[1]
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


def _resolve_union_wall_segments(
    volumes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把同层正交矩形体量编译成联合外轮廓，去掉共享边和被覆盖的内部边。"""
    rectangles = [
        (
            float(volume["x"]),
            float(volume["z"]),
            float(volume["x"]) + float(volume["width"]),
            float(volume["z"]) + float(volume["depth"]),
        )
        for volume in volumes
    ]
    xs = sorted({value for rectangle in rectangles for value in (rectangle[0], rectangle[2])})
    zs = sorted({value for rectangle in rectangles for value in (rectangle[1], rectangle[3])})
    occupied: set[tuple[int, int]] = set()
    for x_index in range(len(xs) - 1):
        for z_index in range(len(zs) - 1):
            center_x = (xs[x_index] + xs[x_index + 1]) / 2
            center_z = (zs[z_index] + zs[z_index + 1]) / 2
            if any(
                x0 < center_x < x1 and z0 < center_z < z1
                for x0, z0, x1, z1 in rectangles
            ):
                occupied.add((x_index, z_index))

    raw_segments: list[tuple[str, float, float, float]] = []
    for x_index, z_index in occupied:
        x0, x1 = xs[x_index], xs[x_index + 1]
        z0, z1 = zs[z_index], zs[z_index + 1]
        if (x_index, z_index - 1) not in occupied:
            raw_segments.append(("front", z0, x0, x1))
        if (x_index, z_index + 1) not in occupied:
            raw_segments.append(("back", z1, x0, x1))
        if (x_index - 1, z_index) not in occupied:
            raw_segments.append(("left", x0, z0, z1))
        if (x_index + 1, z_index) not in occupied:
            raw_segments.append(("right", x1, z0, z1))

    merged: list[tuple[str, float, float, float]] = []
    for side in ("front", "right", "back", "left"):
        constants = sorted({segment[1] for segment in raw_segments if segment[0] == side})
        for constant in constants:
            intervals = sorted(
                (segment[2], segment[3])
                for segment in raw_segments
                if segment[0] == side and abs(segment[1] - constant) <= 1e-6
            )
            if not intervals:
                continue
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start <= end + 1e-6:
                    end = max(end, next_end)
                else:
                    merged.append((side, constant, start, end))
                    start, end = next_start, next_end
            merged.append((side, constant, start, end))

    segments: list[dict[str, Any]] = []
    for side, constant, start, end in merged:
        if side == "front":
            start_point, end_point = (start, constant), (end, constant)
        elif side == "back":
            start_point, end_point = (end, constant), (start, constant)
        elif side == "left":
            start_point, end_point = (constant, end), (constant, start)
        else:
            start_point, end_point = (constant, start), (constant, end)
        segments.append({"side": side, "from": start_point, "to": end_point})
    return segments


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
    wall_base_levels: set[float] = set()
    wall_keys: set[tuple[Any, ...]] = set()
    duplicate_wall_count = 0
    columns: list[tuple[float, float, float, float, float]] = []
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
                wall_base_levels.add(vertical_range[0])
                horizontal_endpoints = tuple(sorted((
                    (round(float(start[0]), 2), round(float(start[2]), 2)),
                    (round(float(end[0]), 2), round(float(end[2]), 2)),
                )))
                wall_key = (horizontal_endpoints, vertical_range)
                if wall_key in wall_keys:
                    duplicate_wall_count += 1
                else:
                    wall_keys.add(wall_key)
        elif element_type == "column":
            base = element.get("base")
            if isinstance(base, list) and len(base) == 3:
                try:
                    height = float(element.get("height", 0))
                    radius = max(
                        float(element.get("bottomRadius", 0)),
                        float(element.get("topRadius", 0)),
                        float(element.get("radius", 0)),
                        float(element.get("width", 0)) / 2,
                        float(element.get("depth", 0)) / 2,
                        0.01,
                    )
                    columns.append((
                        float(base[0]), float(base[1]), float(base[2]), height, radius,
                    ))
                except (TypeError, ValueError):
                    pass

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

    # 联合外轮廓会把相接矩形编译成一个连通墙组；凹多边形仍代表多个体量层次，
    # 不能再依赖旧的“重复矩形墙圈数量”来证明复杂度。
    articulated_levels = sum(1 for walls in wall_groups.values() if len(walls) > 4)
    resolved_volume_footprint_count = max(
        len(volume_footprints),
        1 + articulated_levels if volume_footprints else 0,
    )
    overlapping_column_count = 0
    for index, first in enumerate(columns):
        for second in columns[index + 1:]:
            vertical_overlap = min(first[1] + first[3], second[1] + second[3]) - max(first[1], second[1])
            horizontal_distance = math.hypot(first[0] - second[0], first[2] - second[2])
            if vertical_overlap > 0.05 and horizontal_distance < first[4] + second[4] - 0.02:
                overlapping_column_count += 1

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
    schematic = str(massing.get("representation_mode") or "full") == "schematic"
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
    expected_wall_base_levels = {
        round(level * floor_height, 2) for level in range(modeled_floors)
    }
    checks = {
        "structural_element_target": structural_count >= target,
        "volume_footprint_target": resolved_volume_footprint_count >= volume_target,
        "volume_plan_conformance": (
            True if schematic
            else (not expected_floor_layouts or floor_layouts == expected_floor_layouts)
        ),
        "structural_type_diversity": len([value for value in counts.values() if value]) >= 3,
        "storey_wall_levels": (
            True if schematic
            else expected_wall_base_levels.issubset(wall_base_levels)
        ),
        "vertical_circulation": modeled_floors <= 1 or counts.get("stair", 0) > 0,
        "duplicate_wall_free": duplicate_wall_count == 0,
        "overlapping_column_free": overlapping_column_count == 0,
    }
    realization_checks = (
        checks["volume_plan_conformance"],
        checks["storey_wall_levels"],
        checks["vertical_circulation"],
        checks["duplicate_wall_free"],
        checks["overlapping_column_free"],
    )
    return {
        "level": level,
        "meets_target": (
            level == "minimal"
            or (
                all(realization_checks)
                and (level != "detailed" or all(checks.values()))
            )
        ),
        "checks": checks,
        "structural_element_count": structural_count,
        "target_structural_elements": target,
        "floor_footprint_count": len(floor_footprints),
        "volume_footprint_count": resolved_volume_footprint_count,
        "floor_layout_count": len(floor_layouts),
        "expected_floor_layout_count": len(expected_floor_layouts),
        "target_volume_footprints": volume_target,
        "duplicate_wall_count": duplicate_wall_count,
        "overlapping_column_count": overlapping_column_count,
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
    templates: dict[str, dict[str, Any]] = {}
    instances: list[dict[str, Any]] = []
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

        if floors > 1:
            templates["standard_floor_plate"] = {
                "type": "floor", "id": "standard_floor_plate",
                "from": [0.0, 0.0, 0.0], "to": [width, 0.0, depth],
                "thickness": 0.2, "material": "concrete",
            }
            instances.extend({
                "id": f"floor_standard_{level}",
                "ref": "standard_floor_plate",
                "position": [0.0, round(level * floor_height, 3), 0.0],
            } for level in range(1, floors))

            stair_x = max(1.0, min(width - 1.0, width * 0.2))
            stair_z0 = max(0.8, min(depth - 2.0, depth * 0.2))
            stair_z1 = max(stair_z0 + 1.0, min(depth - 0.8, depth * 0.65))
            templates["standard_storey_stair"] = {
                "type": "stair", "id": "standard_storey_stair",
                "from": [stair_x, 0.0, stair_z0],
                "to": [stair_x, floor_height, stair_z1],
                "width": min(1.8, max(1.0, width * 0.08)),
                "material": "concrete",
            }
            instances.extend({
                "id": f"stair_standard_{level}_{level + 1}",
                "ref": "standard_storey_stair",
                "position": [0.0, round((level - 1) * floor_height, 3), 0.0],
            } for level in range(1, floors))

        if normalized["profile"] == "high_rise":
            core_width = min(width - 2.0, max(4.0, width * 0.24))
            core_depth = min(depth - 2.0, max(4.0, depth * 0.28))
            x0 = (width - core_width) / 2
            x1 = x0 + core_width
            z0 = (depth - core_depth) / 2
            z1 = z0 + core_depth
            core_thickness = 0.2
            elements.extend([
                {
                    "type": "wall", "id": "wall_core_front",
                    "from": [x0, 0.0, z0], "to": [x1, total_height, z0],
                    "thickness": core_thickness, "material": "concrete",
                },
                {
                    "type": "wall", "id": "wall_core_right",
                    "from": [x1, 0.0, z0], "to": [x1, total_height, z1],
                    "thickness": core_thickness, "material": "concrete",
                },
                {
                    "type": "wall", "id": "wall_core_back",
                    "from": [x1, 0.0, z1], "to": [x0, total_height, z1],
                    "thickness": core_thickness, "material": "concrete",
                },
                {
                    "type": "wall", "id": "wall_core_left",
                    "from": [x0, 0.0, z1], "to": [x0, total_height, z0],
                    "thickness": core_thickness, "material": "concrete",
                },
                {
                    "type": "wall", "id": "wall_core_partition",
                    "from": [(x0 + x1) / 2, 0.0, z0],
                    "to": [(x0 + x1) / 2, total_height, z1],
                    "thickness": core_thickness, "material": "concrete",
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
            if len(active_volumes) > 1:
                side_counts: dict[str, int] = {}
                for segment in _resolve_union_wall_segments(active_volumes):
                    side = str(segment["side"])
                    side_counts[side] = side_counts.get(side, 0) + 1
                    start_x, start_z = segment["from"]
                    end_x, end_z = segment["to"]
                    elements.append({
                        "type": "wall",
                        "id": f"wall_{side}_{level}_{side_counts[side]}",
                        "from": [start_x, base_y, start_z],
                        "to": [end_x, top_y, end_z],
                        "thickness": 0.24,
                        "material": "wall_finish",
                    })
                continue

            for volume in active_volumes:
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
        column_keys: set[tuple[float, float, float, float]] = set()
        for volume in volumes:
            x0 = float(volume["x"])
            z0 = float(volume["z"])
            x1 = x0 + float(volume["width"])
            z1 = z0 + float(volume["depth"])
            beam_inset = min(0.35, float(volume["width"]) * 0.08, float(volume["depth"]) * 0.08)
            column_inset = min(
                max(radius + 0.04, 0.18),
                float(volume["width"]) * 0.2,
                float(volume["depth"]) * 0.2,
            )
            base_y = (int(volume["start_floor"]) - 1) * floor_height
            volume_height = (int(volume["end_floor"]) - int(volume["start_floor"]) + 1) * floor_height
            if int(volume["start_floor"]) > 1:
                base_y += 0.2
                volume_height = max(0.5, volume_height - 0.2)
            volume_id = str(volume["id"])
            corners = (
                (x0 + column_inset, z0 + column_inset),
                (x1 - column_inset, z0 + column_inset),
                (x1 - column_inset, z1 - column_inset),
                (x0 + column_inset, z1 - column_inset),
            )
            for index, (x, z) in enumerate(corners, start=1):
                column_key = (
                    round(x, 3), round(z, 3), round(base_y, 3),
                    round(base_y + volume_height, 3),
                )
                if column_key in column_keys:
                    continue
                column_keys.add(column_key)
                elements.append({
                    "type": "column", "id": f"column_{volume_id}_{index}",
                    "base": [x, base_y, z], "height": volume_height,
                    "bottomRadius": radius, "topRadius": radius,
                    "style": "modern", "material": "concrete",
                })
            beam_y = base_y + volume_height
            elements.append({
                "type": "beam", "id": f"beam_main_{volume_id}",
                "from": [x0 + beam_inset, beam_y, (z0 + z1) / 2],
                "to": [x1 - beam_inset, beam_y, (z0 + z1) / 2],
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
        "geometry": {
            "elements": elements,
            "components": [],
            **({"templates": templates, "instances": instances} if templates else {}),
        },
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


def _expand_schematic_facade_storeys(
    walls: list[dict[str, Any]],
    realization: dict[str, Any],
) -> list[dict[str, Any]]:
    """把连续高墙映射为逐层立面区间，宿主仍保持同一真实 wall。"""
    if realization.get("representation_mode") != "schematic":
        return walls
    floors = max(1, int(realization.get("floors") or realization.get("modeled_floors") or 1))
    floor_height = max(0.1, float(realization.get("floor_height") or 3.2))
    expected_height = floors * floor_height
    expanded: list[dict[str, Any]] = []
    for wall in walls:
        if wall["height"] < expected_height - max(0.1, floor_height * 0.05):
            expanded.append(wall)
            continue
        for level in range(floors):
            expanded.append({
                **wall,
                "base_y": round(wall["base_y"] + level * floor_height, 3),
                "height": min(floor_height, wall["height"] - level * floor_height),
                "story_index": level + 1,
            })
    return expanded


def _opening_slots_overlap(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    horizontal_clearance: float = 0.0,
) -> bool:
    """判断同一父墙上的两个门窗槽位是否在墙面矩形中相交。"""
    if first.get("wall_id") != second.get("wall_id"):
        return False
    try:
        first_from = first["from"]
        second_from = second["from"]
        first_left = float(first_from[0])
        first_bottom = float(first_from[1])
        second_left = float(second_from[0])
        second_bottom = float(second_from[1])
        first_width = float(first["width"])
        first_height = float(first["height"])
        second_width = float(second["width"])
        second_height = float(second["height"])
    except (KeyError, TypeError, ValueError, IndexError):
        return True
    if min(first_width, first_height, second_width, second_height) <= 0:
        return True
    vertical_overlap = (
        first_bottom < second_bottom + second_height
        and second_bottom < first_bottom + first_height
    )
    horizontal_overlap = (
        first_left < second_left + second_width + horizontal_clearance
        and second_left < first_left + first_width + horizontal_clearance
    )
    return vertical_overlap and horizontal_overlap


def _stable_unit_interval(value: str) -> float:
    """把稳定标识映射到 [0, 1]，为未指定参数提供可复现的小幅变化。"""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _default_entrance_dimensions(slot_id: str, wall_height: float) -> tuple[float, float]:
    width = 0.9 + _stable_unit_interval(f"{slot_id}:width") * 0.25
    height = 2.1 + _stable_unit_interval(f"{slot_id}:height") * 0.25
    return round(width, 3), round(min(height, wall_height - 0.25), 3)


def _evenly_spaced_opening_slots(
    slots: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """在配额小于候选槽位时保留覆盖完整标高范围的规则采样。"""
    if limit <= 0:
        return []
    if len(slots) <= limit:
        return slots
    ordered = sorted(slots, key=lambda slot: (
        float(slot.get("from", [0.0, 0.0, 0.0])[1]),
        {"front": 0, "back": 1, "left": 2, "right": 3}.get(slot.get("facing"), 4),
        int(slot.get("bay") or 0),
        str(slot.get("id") or ""),
    ))
    if limit == 1:
        return [ordered[len(ordered) // 2]]
    last = len(ordered) - 1
    return [ordered[round(index * last / (limit - 1))] for index in range(limit)]


def _planned_roof_slots(plan: dict[str, Any], realization: dict[str, Any]) -> list[dict[str, Any]]:
    """为 U 形顶层生成互不重叠的平屋顶分段，避免整块屋面填平凹口。"""
    roof = plan.get("roof") if isinstance(plan.get("roof"), dict) else {}
    if realization.get("shape") != "u_shape" or roof.get("type") != "flat":
        return []
    modeled_floors = int(realization.get("modeled_floors") or 1)
    floor_height = float(realization.get("floor_height") or 3.2)
    volumes = [
        volume for volume in realization.get("volumes", [])
        if isinstance(volume, dict)
        and int(volume.get("start_floor", 1)) <= modeled_floors <= int(volume.get("end_floor", 1))
    ]
    if len(volumes) < 2:
        return []

    rectangles = [
        (
            float(volume["x"]),
            float(volume["z"]),
            float(volume["x"]) + float(volume["width"]),
            float(volume["z"]) + float(volume["depth"]),
        )
        for volume in volumes
    ]
    overhang = max(0.15, min(0.8, float(roof.get("overhang") or 0.35)))

    def has_adjacent(rectangle: tuple[float, float, float, float], edge: str) -> bool:
        x0, z0, x1, z1 = rectangle
        for other in rectangles:
            if other == rectangle:
                continue
            ox0, oz0, ox1, oz1 = other
            if edge == "left" and abs(ox1 - x0) <= 1e-6 and min(z1, oz1) - max(z0, oz0) > 1e-6:
                return True
            if edge == "right" and abs(ox0 - x1) <= 1e-6 and min(z1, oz1) - max(z0, oz0) > 1e-6:
                return True
            if edge == "front" and abs(oz1 - z0) <= 1e-6 and min(x1, ox1) - max(x0, ox0) > 1e-6:
                return True
            if edge == "back" and abs(oz0 - z1) <= 1e-6 and min(x1, ox1) - max(x0, ox0) > 1e-6:
                return True
        return False

    slots: list[dict[str, Any]] = []
    for index, (volume, rectangle) in enumerate(zip(volumes, rectangles), start=1):
        x0, z0, x1, z1 = rectangle
        roof_x0 = x0 if has_adjacent(rectangle, "left") else x0 - overhang
        roof_x1 = x1 if has_adjacent(rectangle, "right") else x1 + overhang
        roof_z0 = z0 if has_adjacent(rectangle, "front") else z0 - overhang
        roof_z1 = z1 if has_adjacent(rectangle, "back") else z1 + overhang
        slots.append({
            "id": f"roof:{volume.get('id') or index}",
            "position": [
                round((roof_x0 + roof_x1) / 2, 3),
                round(modeled_floors * floor_height, 3),
                round((roof_z0 + roof_z1) / 2, 3),
            ],
            "span": round(roof_x1 - roof_x0, 3),
            "depth": round(roof_z1 - roof_z0, 3),
        })
    return slots


def _planned_terrace_railing_slots(
    blueprint: dict[str, Any],
    opening_slots: list[dict[str, Any]],
    realization: dict[str, Any],
) -> list[dict[str, Any]]:
    """为 U 形二层退台的临空前缘补一条连续安全栏杆。"""
    if realization.get("shape") != "u_shape":
        return []
    access_slots = [slot for slot in opening_slots if slot.get("role") == "balcony_access"]
    if len(access_slots) < 2:
        return []
    walls = {
        element.get("id"): element
        for element in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(element, dict) and element.get("type") == "wall"
    }
    ranges: list[tuple[float, float, float, float]] = []
    for slot in access_slots:
        wall = walls.get(slot.get("wall_id"))
        start = wall.get("from") if isinstance(wall, dict) else None
        end = wall.get("to") if isinstance(wall, dict) else None
        if not isinstance(start, list) or not isinstance(end, list) or len(start) != 3 or len(end) != 3:
            continue
        if abs(float(start[2]) - float(end[2])) > 1e-6:
            continue
        ranges.append((
            min(float(start[0]), float(end[0])),
            max(float(start[0]), float(end[0])),
            float(start[2]),
            float(slot.get("from", [0, 0, 0])[1]),
        ))
    ranges.sort()
    if len(ranges) < 2:
        return []
    left, right = ranges[0], ranges[-1]
    if abs(left[2] - right[2]) > 0.05 or right[0] - left[1] < 0.8:
        return []
    slab_thickness = 0.2
    for floor in blueprint.get("geometry", {}).get("elements", []):
        start = floor.get("from") if isinstance(floor, dict) and floor.get("type") == "floor" else None
        if isinstance(start, list) and len(start) == 3 and abs(float(start[1]) - left[3]) <= 0.05:
            slab_thickness = max(slab_thickness, float(floor.get("thickness") or 0.0))
    y = round(left[3] + slab_thickness, 3)
    return [{
        "id": "railing:upper_terrace_front",
        "path": [[round(left[1], 3), y, round(left[2], 3)], [round(right[0], 3), y, round(right[2], 3)]],
        "height": 1.1,
    }]


def _derived_balcony_slots(
    opening_slots: list[dict[str, Any]],
    walls: list[dict[str, Any]],
    *,
    count: int,
    minimum_y: float,
    requested_width: float | None,
) -> list[dict[str, Any]]:
    """从上层立面开口推导阳台槽位，使悬挑板与入口轴线对齐。"""
    if count <= 0:
        return []
    wall_by_id = {str(wall["id"]): wall for wall in walls}
    candidates: list[tuple[tuple[int, float, str], dict[str, Any]]] = []
    for opening in opening_slots:
        wall = wall_by_id.get(str(opening.get("wall_id") or ""))
        if (
            opening.get("type") != "window"
            or opening.get("role")
            or not wall
            or float(wall["base_y"]) <= minimum_y + 0.25
        ):
            continue
        wall_length = float(wall["length"])
        opening_width = float(opening["width"])
        target_width = (
            float(requested_width)
            if isinstance(requested_width, (int, float)) and not isinstance(requested_width, bool)
            else max(2.4, min(3.2, opening_width + 1.2))
        )
        width = min(wall_length, max(opening_width, target_width))
        center = float(opening["from"][0]) + opening_width / 2
        edge_clearance = min(0.18, max(0.0, (wall_length - width) / 2))
        left = max(
            edge_clearance,
            min(wall_length - width - edge_clearance, center - width / 2),
        )
        # 夹到墙边时无法保持轴线对齐的候选不自动采用。
        if abs(left + width / 2 - center) > 0.05:
            continue
        facing = str(opening.get("facing") or "")
        rank = (
            {"front": 0, "back": 1, "left": 2, "right": 3}.get(facing, 4),
            abs(center - wall_length / 2),
            str(opening.get("id") or ""),
        )
        candidates.append((rank, {
            "id": str(opening["id"]).replace(":window:", ":balcony:"),
            "wall_id": opening["wall_id"],
            "from": [round(left, 3), round(float(wall["base_y"]), 3), 0.0],
            "width": round(width, 3),
            "opening_slot_id": opening["id"],
        }))

    ordered = [candidate for _, candidate in sorted(candidates, key=lambda item: item[0])]
    selected: list[dict[str, Any]] = []
    used_walls: set[str] = set()
    for candidate in ordered:
        wall_id = str(candidate["wall_id"])
        if wall_id in used_walls:
            continue
        selected.append(candidate)
        used_walls.add(wall_id)
        if len(selected) >= count:
            return selected
    for candidate in ordered:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= count:
            break
    return selected


def _curtain_wall_mullions(span: float, *, pane: float | None = None) -> int:
    """玻璃幕墙窗格密铺：按知识库配方的分格模数计算竖向/横向梃数量（上限 32）。

    方案 A（``wall + window``）中，窗编译器会按 ``verticalMullions`` 与
    ``horizontalMullions`` 生成框、竖梃、横梃和玻璃。这里把每个窗切到配方
    ``pane_module`` 见方的窗格，从而避免「整片纯玻璃墙」的观感。分格模数随
    知识库 `glass-curtain-wall-assembly.md` 的确定性参数变化，不在代码里写死。
    """
    if pane is None:
        pane = load_curtain_wall_parameters().pane_module
    if not isinstance(span, (int, float)) or isinstance(span, bool) or span <= 0:
        return 0
    panes = max(1, int(round(float(span) / pane)))
    return min(32, max(0, panes - 1))


def resolve_facade_layout(blueprint: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """把抽象立面轴网解析成真实 wall id 与精确门窗局部坐标。"""
    massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
    curtain_wall = bool(plan.get("curtain_wall"))
    curtain_params = load_curtain_wall_parameters() if curtain_wall else None
    realization = {
        "floors": int(massing.get("floors") or massing.get("modeled_floors") or 1),
        "modeled_floors": int(massing.get("modeled_floors") or massing.get("floors") or 1),
        "floor_height": float(massing.get("floor_height") or 3.2),
        "representation_mode": str(massing.get("representation_mode") or "full"),
        "shape": str(massing.get("shape") or "rectangle"),
        "volumes": deepcopy(plan.get("volumes") or []),
    }
    walls = []
    for element in blueprint.get("geometry", {}).get("elements", []):
        if isinstance(element, dict) and element.get("type") == "wall":
            descriptor = _wall_descriptor(element)
            if descriptor:
                walls.append(descriptor)
    walls = _expand_schematic_facade_storeys(walls, realization)
    if not walls:
        roof_slots = _planned_roof_slots(plan, realization)
        quotas = deepcopy(plan.get("component_quota", {}))
        if roof_slots:
            quotas["roof"] = {**quotas.get("roof", {}), "min": len(roof_slots), "max": len(roof_slots)}
        return {
            "facade_plan": {},
            "component_quota": quotas,
            "opening_slots": [],
            "balcony_slots": [],
            "roof_slots": roof_slots,
            "railing_slots": [],
            "realization": realization,
        }

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
    meta = blueprint.get("meta", {}) if isinstance(blueprint.get("meta"), dict) else {}
    variation_scope = str(
        meta.get("seed")
        or meta.get("name")
        or plan.get("concept")
        or "default-building"
    )
    balcony_access_remaining = max(0, int(plan.get("balcony_access_count") or 0))
    balcony_width = plan.get("balcony_width")
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
        is_balcony_access_wall = (
            balcony_access_remaining > 0
            and not is_ground
            and external
            and facing == "front"
            and wall["axis"] == "x"
            and wall["length"] >= 1.0
        )
        if is_balcony_access_wall:
            requested_access_width = (
                float(balcony_width)
                if isinstance(balcony_width, (int, float)) and not isinstance(balcony_width, bool)
                else wall["length"] - 0.2
            )
            access_width = max(0.8, min(wall["length"], requested_access_width))
            wall_slots.append({
                "id": f"{wall['id']}:floor_{wall.get('story_index', 1)}:door:balcony_access",
                "type": "door",
                "role": "balcony_access",
                "wall_id": wall["id"],
                "facing": facing,
                "bay": 1,
                "from": [round((wall["length"] - access_width) / 2, 3), round(wall["base_y"], 3), 0.0],
                "width": round(access_width, 3),
                "height": round(max(0.8, min(2.6, wall["height"] - 0.25)), 3),
            })
            slots.extend(wall_slots)
            balcony_access_remaining -= 1
        for bay_index, opening_type in enumerate(pattern[:bays]):
            if is_balcony_access_wall:
                break
            if opening_type not in {"door", "window"}:
                continue
            if opening_type == "door" and not is_ground:
                continue
            if opening_type == "door":
                slot_id = (
                    f"{wall['id']}:floor_{wall.get('story_index', 1)}:"
                    f"{opening_type}:{bay_index + 1}"
                )
                target_width, target_height = _default_entrance_dimensions(
                    f"{variation_scope}:{slot_id}",
                    wall["height"],
                )
                # 门可以跨越立面轴网，不能因为单个 bay 偏窄而失去基本通行宽度。
                available_width = min(wall["length"], max(0.5, wall["length"] - 0.36))
                if wall["length"] >= 0.9:
                    available_width = max(0.9, available_width)
                width = min(target_width, available_width)
            elif curtain_wall:
                # 幕墙窗带贴合开间，只留配方设定的细窄竖梃缝；不再用固定上限卡宽。
                width = max(curtain_params.min_window_width, bay_width - curtain_params.mullion_gap)
            else:
                width = max(0.75, min(2.2, bay_width * 0.62))
                width = min(width, max(0.5, bay_width - 0.35))
            center = bay_width * (bay_index + 0.5)
            edge_clearance = min(0.18, max(0.0, (wall["length"] - width) / 2))
            left = max(
                edge_clearance,
                min(wall["length"] - width - edge_clearance, center - width / 2),
            )
            if opening_type == "door":
                bottom = wall["base_y"]
                height_cap = target_height
            elif curtain_wall:
                # 幕墙窗台压薄、窗带加高，缩小层间不透明缝。
                bottom = wall["base_y"] + min(
                    curtain_params.sill_height,
                    wall["height"] * curtain_params.sill_ratio,
                )
                height_cap = wall["height"] - (bottom - wall["base_y"]) - curtain_params.top_clearance
            else:
                bottom = wall["base_y"] + min(1.0, wall["height"] * 0.3)
                height_cap = 1.55
            height = min(
                height_cap,
                wall["height"] - (bottom - wall["base_y"]) - 0.25,
            )
            slot = {
                "id": (
                    f"{wall['id']}:floor_{wall.get('story_index', 1)}:"
                    f"{opening_type}:{bay_index + 1}"
                ),
                "type": opening_type,
                "wall_id": wall["id"],
                "facing": facing,
                "bay": bay_index + 1,
                "from": [round(left, 3), round(bottom, 3), 0.0],
                "width": round(width, 3),
                "height": round(max(0.8, height), 3),
            }
            if curtain_wall and opening_type == "window":
                slot["vertical_mullions"] = _curtain_wall_mullions(width)
                slot["horizontal_mullions"] = _curtain_wall_mullions(height)
            if any(
                _opening_slots_overlap(
                    slot,
                    existing,
                    horizontal_clearance=0.1,
                )
                for existing in wall_slots
            ):
                continue
            wall_slots.append(slot)
            slots.append(slot)
        wall_plan = facade_plan.setdefault(str(wall["id"]), {
            "facing": facing if external else "internal",
            "intent": (
                "阳台后方设置通室内入口"
                if is_balcony_access_wall
                else "按建筑方案轴网布置门窗"
                if external
                else "内部/退台墙，不自动开口"
            ),
            "max_openings": 0,
            "is_main_facade": False,
            "slots": [],
        })
        wall_plan["max_openings"] += len(wall_slots)
        wall_plan["is_main_facade"] = (
            wall_plan["is_main_facade"] or (external and facing == "front")
        )
        wall_plan["slots"].extend(wall_slots)

    slots.sort(key=lambda slot: (
        {"front": 0, "back": 1, "left": 2, "right": 3}.get(slot["facing"], 4),
        slot["bay"],
        slot["from"][1],
    ))

    quotas = deepcopy(plan.get("component_quota", {}))
    for opening_type in ("door", "window"):
        available = sum(1 for slot in slots if slot["type"] == opening_type)
        limits = quotas.setdefault(opening_type, {})
        if curtain_wall and opening_type == "window":
            # 幕墙全立面密铺：每个窗槽位都必须有窗。这里忽略模型/回退配额上限，
            # 直接按实际立面槽位数量补齐，否则按少量配额沿全高抽样会变成
            # 「每几层才一个窗」的错乱散布。
            limits["max"] = available
            limits["min"] = available
            continue
        maximum = limits.get("max")
        limits["max"] = available if not isinstance(maximum, (int, float)) else min(int(maximum), available)
        minimum = limits.get("min", 0)
        limits["min"] = min(int(minimum) if isinstance(minimum, (int, float)) else 0, limits["max"])

    balcony_slots = [
        {
            "id": str(slot["id"]).replace(":door:", ":balcony:"),
            "wall_id": slot["wall_id"],
            "from": deepcopy(slot["from"]),
            "width": slot["width"],
        }
        for slot in slots
        if slot.get("role") == "balcony_access"
    ]
    balcony_limits = quotas.get("balcony", {})
    balcony_minimum = (
        int(balcony_limits.get("min", 0))
        if isinstance(balcony_limits, dict)
        and isinstance(balcony_limits.get("min", 0), (int, float))
        else 0
    )
    if len(balcony_slots) < balcony_minimum:
        balcony_slots.extend(_derived_balcony_slots(
            slots,
            walls,
            count=balcony_minimum - len(balcony_slots),
            minimum_y=min_y,
            requested_width=(
                float(balcony_width)
                if isinstance(balcony_width, (int, float)) and not isinstance(balcony_width, bool)
                else None
            ),
        ))
    roof_slots = _planned_roof_slots(plan, realization)
    if roof_slots:
        quotas["roof"] = {
            **quotas.get("roof", {}),
            "min": len(roof_slots),
            "max": len(roof_slots),
            "note": "U 形顶层按体量分段覆盖，不跨越退台凹口",
        }
    railing_slots = _planned_terrace_railing_slots(blueprint, slots, realization)

    return {
        "facade_plan": facade_plan,
        "component_quota": quotas,
        "opening_slots": slots,
        "balcony_slots": balcony_slots,
        "roof_slots": roof_slots,
        "railing_slots": railing_slots,
        "realization": realization,
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
    fallback_frame_material = next(
        (name for name in material_names if "wood" in name.lower()),
        default_material,
    )
    frame_material = next(
        (name for name in material_names if any(word in name.lower() for word in ("frame", "metal"))),
        fallback_frame_material,
    )
    leaf_material = next(
        (name for name in material_names if any(word in name.lower() for word in ("wood", "door", "accent"))),
        frame_material,
    )
    non_openings = [
        item for item in components
        if item.get("type") not in {"door", "window", "bay_window"}
    ]
    result_openings: list[dict[str, Any]] = []
    stats = {"snapped": 0, "synthesized": 0, "pruned": 0}
    quotas = design_brief.get("component_quota", {})
    all_slots: list[dict[str, Any]] = []
    for raw_slot in design_brief["opening_slots"]:
        if (
            not isinstance(raw_slot, dict)
            or raw_slot.get("type") not in {"door", "window"}
            or not raw_slot.get("id")
            or not raw_slot.get("wall_id")
        ):
            continue
        slot = deepcopy(raw_slot)
        if any(_opening_slots_overlap(slot, existing) for existing in all_slots):
            continue
        all_slots.append(slot)

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
        slots = _evenly_spaced_opening_slots(slots, maximum)
        maximum = len(slots)
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
                is_balcony_access = slot.get("role") == "balcony_access"
                item = {
                    "id": (
                        f"door_balcony_access_{index:02d}"
                        if is_balcony_access else f"door_planned_{index:02d}"
                    ),
                    "type": "door",
                    "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90},
                    "frameMaterial": frame_material, "leafMaterial": leaf_material,
                }
            else:
                item = {
                    "id": f"window_planned_{index:02d}", "type": "window",
                    "verticalMullions": int(slot.get("vertical_mullions", 1)),
                    "horizontalMullions": int(slot.get("horizontal_mullions", 0)),
                    "frameMaterial": frame_material, "glassMaterial": glass_material,
                }
            ordered_items.append((item, slot))
            stats["synthesized"] += 1
        for item, slot in ordered_items:
            if slot.get("role"):
                item["role"] = slot["role"]
            item["parentWall"] = slot["wall_id"]
            item["from"] = deepcopy(slot["from"])
            item["width"] = slot["width"]
            item["height"] = slot["height"]
            if opening_type == "window" and "vertical_mullions" in slot:
                # 幕墙窗格：统一到骨架解析出的分格模数，覆盖模型任意梃数，保证整面密铺。
                item["verticalMullions"] = int(slot["vertical_mullions"])
                item["horizontalMullions"] = int(slot.get("horizontal_mullions", 0))
                item["frameMaterial"] = frame_material
                item["glassMaterial"] = glass_material
            if opening_type == "door":
                variant = _stable_unit_interval(f"{item.get('id', slot['id'])}:frame")
                item.setdefault("frameWidth", round(0.065 + variant * 0.025, 3))
                item.setdefault("frameMaterial", frame_material)
                item.setdefault("leafMaterial", leaf_material)
                item.setdefault("interaction", {
                    "mode": "swing",
                    "hingeSide": "left" if variant < 0.5 else "right",
                    "openAngle": 90,
                })
            result_openings.append(item)
            stats["snapped"] += 1
    return [*non_openings, *result_openings], stats


def conform_balconies_to_slots(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """把阳台与阳台门槽位一一绑定，修正挂错墙和宽度漂移。"""
    slots = design_brief.get("balcony_slots") if isinstance(design_brief, dict) else None
    if not isinstance(slots, list) or not slots:
        return components, {"snapped": 0, "synthesized": 0, "pruned": 0}
    sources = [deepcopy(item) for item in components if item.get("type") == "balcony"]
    non_balconies = [item for item in components if item.get("type") != "balcony"]
    stats = {
        "snapped": min(len(sources), len(slots)),
        "synthesized": max(0, len(slots) - len(sources)),
        "pruned": max(0, len(sources) - len(slots)),
    }
    balconies: list[dict[str, Any]] = []
    for index, slot in enumerate(slots, start=1):
        item = sources[index - 1] if index <= len(sources) else {
            "type": "balcony",
            "id": f"balcony_planned_{index:02d}",
            "depth": 1.5,
            "slabThickness": 0.18,
            "railingHeight": 1.1,
            "postSpacing": 0.9,
        }
        item["parentWall"] = slot["wall_id"]
        item["from"] = deepcopy(slot["from"])
        item["width"] = slot["width"]
        item["depth"] = round(max(0.8, min(2.5, float(item.get("depth") or 1.5))), 3)
        item["slabThickness"] = round(max(0.12, float(item.get("slabThickness") or 0.18)), 3)
        item["railingHeight"] = round(max(0.9, float(item.get("railingHeight") or 1.1)), 3)
        balconies.append(item)
    return [*non_balconies, *balconies], stats


def conform_roofs_to_slots(
    elements: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """用一个模型屋顶作为风格模板，按已批准的 U 形体量拆成多个无重叠屋面。"""
    slots = design_brief.get("roof_slots") if isinstance(design_brief, dict) else None
    if not isinstance(slots, list) or not slots:
        return elements, {"split": 0, "synthesized": 0}
    roofs = [deepcopy(item) for item in elements if item.get("type") == "roof"]
    non_roofs = [item for item in elements if item.get("type") != "roof"]
    template = roofs[0] if roofs else {
        "type": "roof", "roofType": "flat", "height": 0,
        "thickness": 0.25, "material": "default",
    }
    planned: list[dict[str, Any]] = []
    for index, slot in enumerate(slots, start=1):
        item = deepcopy(template)
        item["id"] = f"roof_planned_{index:02d}"
        item["position"] = deepcopy(slot["position"])
        item["span"] = slot["span"]
        item["depth"] = slot["depth"]
        planned.append(item)
    return [*non_roofs, *planned], {
        "split": max(0, len(planned) - len(roofs)),
        "synthesized": 1 if not roofs else 0,
    }


def conform_railings_to_slots(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """补齐方案要求的退台临空栏杆，并优先替换无明确位置的超额栏杆。"""
    slots = design_brief.get("railing_slots") if isinstance(design_brief, dict) else None
    if not isinstance(slots, list) or not slots:
        return components, {"synthesized": 0, "replaced": 0}
    result = list(components)
    maximum = int(design_brief.get("component_quota", {}).get("railing", {}).get("max", 4))
    stats = {"synthesized": 0, "replaced": 0}
    for index, slot in enumerate(slots, start=1):
        if any(item.get("type") == "railing" and item.get("path") == slot.get("path") for item in result):
            continue
        railing_indices = [i for i, item in enumerate(result) if item.get("type") == "railing"]
        if maximum >= 0 and len(railing_indices) >= maximum and railing_indices:
            result.pop(railing_indices[-1])
            stats["replaced"] += 1
        result.append({
            "type": "railing",
            "id": f"railing_planned_{index:02d}",
            "path": deepcopy(slot["path"]),
            "height": float(slot.get("height") or 1.1),
            "postSpacing": 1.0,
            "railCount": 2,
        })
        stats["synthesized"] += 1
    return result, stats
