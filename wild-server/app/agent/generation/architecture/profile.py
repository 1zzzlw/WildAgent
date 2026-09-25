"""从用户需求识别建筑类型、尺寸和复杂度配置。"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from app.agent.knowledge.policy import term_is_requested


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
    # 家具无宿主，是唯一"可以单独成一栋场景"的构件类。放在这里只表示
    # **它进入了建筑细部包的合法词表**，不等于默认生成：`_default_detail_packages`
    # 只在用户点名时返回它，`planning.py` 又会把不在 detail_packages 里的细部配额丢掉。
    # 两者合起来 = "点名才生成"，与 KB《家具参数契约》的适用条件一致。
    "furniture": {"min": 2, "max": 12, "note": "按空间功能摆放桌椅、柜体与床；不做室内隔墙与房间划分"},
    # 电梯是唯一带运行时交互的垂直交通构件（点击呼梯按钮 → 轿厢在楼层间升降）。
    # 井道围合不由它自己生成，必须与骨架 `core_and_stair` 的 `wall_core_*` 配套 ⇒
    # `planning.py` 在点名电梯时会把 `vertical_strategy` 强制升到 `core_and_stair`；
    # 单层建筑没有垂直交通需求（KB《电梯》能力边界），点名也会在配额之前被剔除。
    "elevator": {"min": 1, "max": 2, "note": "与核心筒井道配套；单层建筑不生成"},
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
    "industrial_long_span": {
        "label": "工业与农业大跨建筑",
        "width_range": (8.0, 300.0),
        "depth_range": (8.0, 500.0),
        "floor_range": (1, 12),
        "default_massing": (60.0, 40.0, 1, 6.0),
        "max_explicit_floors": 4,
        "shapes": {"rectangle", "linear", "stepped"},
        "base_components": ["door", "window", "roof"],
        "require_front_entrance": True,
        "default_roof": "gable",
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
    if any(word in user_message for word in (
        "庭院", "中庭", "合院", "围合院落", "回字形", "回形",
    )):
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


## 模糊限定词：用户写"宽约17米"和写"宽17米"表达的是同一个尺寸约束，
## 不能因为多了一个"约"就整条落回默认值。验收侧（planning/requirements.py）
## 已经按"含约则放宽容差"处理，两侧必须认出同一句话，否则会出现
## "验收要求 17×23、实际生成 12×9"的跨模块自相矛盾。
_DIMENSION_QUALIFIERS = r"(?:约|大约|大概|为|是|在)?\s*"


def _requested_dimension(user_message: str, labels: tuple[str, ...]) -> float | None:
    number = r"(\d+(?:\.\d+)?)"
    for label in labels:
        for pattern in (
            fr"{label}\s*{_DIMENSION_QUALIFIERS}{number}\s*(?:米|m)?",
            fr"{number}\s*(?:米|m)?\s*{label}",
        ):
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
    elif any(word in message for word in detailed_words):
        level = "detailed"
        reason = "用户明确要求高细节"
    else:
        level = "standard"
        reason = "未指定体量复杂度；精密模式只提高实现与验证质量"

    result = deepcopy(_COMPLEXITY_PROFILES[level])
    result["min_detail_packages"] = 0
    if not any(term_is_requested(message, word) for word in ("多体量", "组合体量", "退台", "错落", "主次体量")):
        result["min_volumes"] = 1
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
        # 家具的点名词：与 COMPONENT_REGISTRY["furniture"].need_keywords 保持同一套语义，
        # 避免"生成侧能派发、计划侧却不认账"的口径分叉。
        "furniture": (
            "家具", "桌子", "餐桌", "书桌", "茶几", "椅子", "沙发", "床",
            "书柜", "书架", "衣柜", "床头柜", "电视柜",
        ),
        # 电梯的点名词：同样与 COMPONENT_REGISTRY["elevator"].need_keywords 对齐。
        # 此前两处词表都没有 elevator，用户点名电梯时规划阶段不会有任何配额。
        "elevator": ("电梯", "升降梯", "垂直交通", "观光梯", "载货梯"),
    }
    explicit = [
        component_type
        for component_type, keywords in explicit_keywords.items()
        if any(term_is_requested(user_message, keyword) for keyword in keywords)
    ]
    if modeled_floors < 2:
        # 单层建筑没有垂直交通需求（KB《电梯》能力边界），点名也不派发。
        explicit = [item for item in explicit if item != "elevator"]
    # 回退仅补用户点名的功能；类型和风格不能触发固定构件套餐。
    return explicit



def _fallback_volumes(
    width: float,
    depth: float,
    modeled_floors: int,
    complexity: dict[str, Any],
    shape: str | None = None,
) -> list[dict[str, Any]]:
    def volume(
        volume_id: str,
        role: str,
        x: float,
        z: float,
        volume_width: float,
        volume_depth: float,
        start_floor: int = 1,
        end_floor: int | None = None,
    ) -> dict[str, Any]:
        return {
            "id": volume_id,
            "role": role,
            "x": round(x, 2),
            "z": round(z, 2),
            "width": round(volume_width, 2),
            "depth": round(volume_depth, 2),
            "start_floor": start_floor,
            "end_floor": modeled_floors if end_floor is None else end_floor,
        }

    if shape == "l_shape":
        wing_width = max(1.5, width * 0.42)
        return [
            volume("left_wing", "primary", 0.0, 0.0, wing_width, depth),
            volume(
                "front_wing", "secondary", wing_width, 0.0,
                width - wing_width, max(1.5, depth * 0.42),
            ),
        ]

    if shape == "courtyard":
        side_width = max(1.2, width * 0.22)
        end_depth = max(1.2, depth * 0.22)
        inner_width = width - side_width * 2
        inner_depth = depth - end_depth * 2
        if inner_width >= 1.0 and inner_depth >= 1.0:
            return [
                volume("courtyard_front", "primary", 0.0, 0.0, width, end_depth),
                volume(
                    "courtyard_back", "primary", 0.0, depth - end_depth,
                    width, end_depth,
                ),
                volume(
                    "courtyard_left", "secondary", 0.0, end_depth,
                    side_width, inner_depth,
                ),
                volume(
                    "courtyard_right", "secondary", width - side_width, end_depth,
                    side_width, inner_depth,
                ),
            ]

    if shape == "stepped" and modeled_floors >= 2:
        podium_floors = max(1, min(2, round(modeled_floors * 0.2)))
        tower_width = width * 0.72
        tower_depth = depth * 0.72
        return [
            volume(
                "base", "primary", 0.0, 0.0, width, depth,
                end_floor=podium_floors,
            ),
            volume(
                "upper_setback", "secondary",
                (width - tower_width) / 2,
                (depth - tower_depth) / 2,
                tower_width,
                tower_depth,
                start_floor=podium_floors + 1,
            ),
        ]

    if shape == "u_shape" and modeled_floors == 1:
        wing_width = min(width * 0.4, max(1.5, width * 0.28))
        back_depth = min(depth * 0.45, max(1.5, depth * 0.32))
        center_width = width - wing_width * 2
        if center_width >= 1.0:
            return [
                volume("left_wing", "primary", 0.0, 0.0, wing_width, depth),
                volume(
                    "right_wing", "primary", width - wing_width, 0.0,
                    wing_width, depth,
                ),
                volume(
                    "back_link", "secondary", wing_width, depth - back_depth,
                    center_width, back_depth,
                ),
            ]

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
    if int(complexity.get("min_volumes", 1)) <= 1:
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


#: **各档位的类型词**（按声明顺序取第一个命中 = 选档顺序）。
#: 这份表同时是 `is_architecture_request` 的闭集来源（见 `_ARCHITECTURE_TYPE_WORDS`），
#: 所以新增一个建筑类型词只需要加在这里一处，"选档"和"是不是建筑"会同时看见它。
_PROFILE_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "underground_transport": ("地铁", "地下车站", "站台层", "地下站", "隧道"),
    "high_rise": ("超高层", "高层", "摩天", "高层写字楼", "高层办公", "塔楼"),
    "long_span_public": (
        "体育场", "体育馆", "游泳馆", "航站楼", "高铁站", "火车站",
        "客运站", "港口客运", "剧院", "音乐厅", "会展", "大会堂",
    ),
    "industrial_long_span": (
        "工厂", "厂房", "仓库", "车间", "物流中心", "配送中心", "机库",
        "温室", "畜舍", "粮仓", "农业建筑",
    ),
    "garden_structure": ("园林", "水榭", "凉亭", "亭子", "游廊", "景观廊"),
    "religious_landmark": ("佛寺", "寺庙", "道观", "清真寺", "教堂", "礼拜殿"),
    "ordinary_public": (
        "办公", "写字楼", "学校", "幼儿园", "教学楼", "实验室", "博物馆",
        "图书馆", "医院", "商业", "商场", "超市", "酒店", "法院", "养老院",
    ),
    # 低层居住建筑是"说了要建筑、但没说清是哪一类"的档位，所以它同时承担
    # 三类词：明确的住宅类型词、房子的口语说法、以及英文常见写法。
    "residential_lowrise": (
        "别墅", "住宅", "民居", "民房", "公寓", "洋房", "排屋", "联排", "独栋",
        "自建房", "私宅", "木屋", "小屋", "房子", "房屋", "民居建筑",
        "house", "villa", "cottage", "cabin", "building",
    ),
}

#: 跨档位的**通用建筑名词**：它们能确定"这是建筑"，但不足以选档（选档仍走
#: `_PROFILE_TYPE_WORDS` 的缺省档位）。放在这里而不是塞进某个档位，是因为
#: "楼/屋/房/馆/站"单独出现时无法判断建筑类型，硬归某一档会给出错的规划边界。
#:
#: ⚠️ 这里只收**单字名词**（"楼""馆""站"这类）。多字的建筑词一律进
#: `_PROFILE_TYPE_WORDS`，否则"是不是建筑"与"是哪一档"会给出互相矛盾的答案。
_GENERIC_ARCHITECTURE_WORDS: tuple[str, ...] = (
    "建筑", "构筑物", "场地", "写字楼", "办公楼", "大厦", "商厦",
    "楼", "屋", "房", "塔", "阁", "苑", "站", "厂",
)

#: 🔴 **建筑类型词的闭集**（`_PROFILE_TYPE_WORDS` 全部类型词 ∪ 通用建筑名词）。
#:
#: 判据为什么建在闭集这一侧：建筑类型是**有限闭集**（平台能生成的就是上面这些），
#: 所以"没命中任何建筑类型词"可以安全地推出"用户要的不是建筑"；而物件名是
#: **开放集**（桌子、小人、机器人、花瓶、路灯、雕塑……永远列不全），**不能**反过来
#: 用"命中了某个物件名词"来判定目标类型。
#:
#: `routing.detect_target_kind` 就踩过这个坑：它拿一张家具名词表判"是不是物件"，
#: 没命中就兜底成建筑 —— 于是"生成一个小人"被送去盖房子。改用本闭集之后，
#: "生成一个人/花瓶/路灯/机器人"都会正确落到物件链，不需要为任何一个名字写规则。
_ARCHITECTURE_TYPE_WORDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        word
        for words in _PROFILE_TYPE_WORDS.values()
        for word in words
    )
) + _GENERIC_ARCHITECTURE_WORDS


def is_architecture_request(user_message: str) -> bool:
    """这次请求命中的是不是**建筑类型闭集**；命中任一建筑类型词即为建筑。

    这是目标判定（``target_kind``）唯一的规则判据，语义是"是不是建筑"，
    **不是**"是不是某个已知物件"。降级路径（模型没给 target_kind 或模型不可用）
    与关键词预检都走这里，避免同一句话在两处得出不同结论。
    """

    message = str(user_message or "").lower()
    if not message:
        return False
    return any(word in message for word in _ARCHITECTURE_TYPE_WORDS)


def match_architecture_profile_id(user_message: str) -> str | None:
    """按**建筑类型词**判定命中了清单里的哪一档；一档都不命中时返回 ``None``。

    "命中与否"本身就是一份可用判据，不只是选档的中间值：
    ``is_architecture_request`` 就是它的闭集版本（见 `_ARCHITECTURE_TYPE_WORDS`）。
    """

    message = user_message.lower()
    requested_floors = _requested_floors(user_message)
    if any(word in message for word in _PROFILE_TYPE_WORDS["underground_transport"]):
        return "underground_transport"
    if (
        any(word in message for word in _PROFILE_TYPE_WORDS["high_rise"])
        or (requested_floors is not None and requested_floors >= 20)
    ):
        return "high_rise"
    if any(word in message for word in _PROFILE_TYPE_WORDS["long_span_public"]):
        return "long_span_public"
    if any(word in message for word in _PROFILE_TYPE_WORDS["industrial_long_span"]):
        return "industrial_long_span"
    if any(word in message for word in _PROFILE_TYPE_WORDS["garden_structure"]):
        return "garden_structure"
    if any(word in message for word in _PROFILE_TYPE_WORDS["religious_landmark"]):
        return "religious_landmark"
    if any(word in message for word in _PROFILE_TYPE_WORDS["ordinary_public"]):
        return "ordinary_public"
    if any(word in message for word in _PROFILE_TYPE_WORDS["residential_lowrise"]):
        return "residential_lowrise"
    return None


def detect_architecture_profile(
    user_message: str,
    fallback_profile_id: str | None = None,
) -> dict[str, Any]:
    """按功能和规模选择确定性规划边界，避免所有建筑退化成低层住宅。"""

    profile_id = match_architecture_profile_id(user_message) or (
        fallback_profile_id
        if fallback_profile_id in _ARCHITECTURE_PROFILES
        else "residential_lowrise"
    )
    profile = deepcopy(_ARCHITECTURE_PROFILES[profile_id])
    profile["id"] = profile_id
    return profile
