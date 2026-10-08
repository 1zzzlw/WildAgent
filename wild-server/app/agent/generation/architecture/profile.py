"""从用户需求识别建筑类型、尺寸和复杂度配置。"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from app.agent.knowledge.policy import term_is_requested
from app.design.openings import OPENING_KINDS


_FACES = ("front", "back", "left", "right")
#: 开口类型闭集。🔴 **从 `app.design.openings` 派生**，不在这里再写一遍——
#: 同一个闭集两处写着，迟早一处加了另一处没加（`MEMORY.md`：单一事实源）。
_OPENING_TYPES = frozenset(OPENING_KINDS)
_SUPPORTED_ROOF_TYPES = {
    "flat", "gable", "hip", "dome", "chinese_curved", "chinese_pagoda",
}

# 复杂度目标固定为单一标准档（2026-09-30 用户决策：前端粒度选择已下线，
# "一面墙/复杂/精致"等词表分档一并删除）。字段名保留，下游
# （normalize/设计分块/收敛环/试算/提示词）的 complexity_profile 契约不动。
_COMPLEXITY_PROFILES: dict[str, dict[str, Any]] = {
    "standard": {
        "min_volumes": 1,
        "min_detail_packages": 0,
        "target_structural_elements": 10,
        "grid_bays": (2, 2),
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
    # 柱是引擎原生元素（注册表 2026-09-29 起可派发）。与家具同族："点名才生成"——
    # 门廊柱/围廊柱/景观柱按设计点名进入配额，普通建筑不会被默认塞柱子。
    "column": {"min": 0, "max": 48, "note": "门廊柱、围廊柱或景观柱；数量与柱网由设计点名"},
}


# 🔴 档案表只剩一个成员：``custom``（用户决策 2026-09-29：删除类型关键词→档案的
# 选档白名单）。它**只提供物理安全边界，不做设计锚定**：
#   - shapes / base_components 给全集（我们不再替模型决定它能是什么形状、能用什么构件）；
#   - default_massing / default_roof 只是模型完全没表态时的最后兜底，
#     且 prompts/planning.py 本来就把这两个字段排除在提示词之外，不会先入为主；
#   - 设计意图（类型、风格、规模、结构体系）由模型 + 知识库决定。
# 此前的 8 档关键词选档（住宅/公建/厂房…）会把"欧式古典柱廊殿宇"这类提示词
# 锚成 12×9 两层住宅体量再被 shapes 钳死——是"所有建筑长一个样"的上游根因。
#
# 2026-10-08 补充：``id`` 现在会带上**分类器模型自选**的形制标签（villa / pavilion /
# tower …），但**上表所有物理边界照旧来自 custom**——标签只用来分流检索与观测，
# 不用来收窄能力。改这里之前先读 `detect_architecture_profile` 的 docstring。
#: 体量形状枚举 —— **唯一事实源**（`_ARCHITECTURE_PROFILES` 的 ``shapes`` 由它派生）。
#:
#: 值是"这个成员在下游有没有**专门的几何行为**"，不是"能不能用"：
#:
#: - ``"volumes"``：`_fallback_volumes` 里有专属分支（模型没给 volumes 时按它派生体量）；
#: - ``"plain"``：没有特殊形态，落到通用体量派生（"一栋普通矩形楼"）；
#: - ``"label"``：**只有标签语义** —— 它的体量构成是设计决策（塔的收分、亭的居中、
#:   巴西利卡的主从各不相同），只能由模型给的 ``volumes`` 表达，兜底只给一组通用体量。
#:   `circle` 也属这一类：圆形平面的几何由屋顶类型派生（KB `cone-roof-system.md`），
#:   本字段只负责表态。
#:
#: 🔴 **枚举是提示词词表，不是输出闸**（项目宪法：禁止给"模型能做什么"设允许列表）。
#: 模型的 shape 越界时**不拦截、不静默改写**，按"仅标签语义"照原样保留并记账
#: —— 这与 2026-09-29「未知构件类型走 `generic_component_config`」是同一条口径。
#:
#: 🔴 **这张表是"枚举↔行为↔KB"的对账点**：加成员只改这里；
#: `tests/components/test_shape_enum.py` 钉住三条 —— 每个成员必须归类、
#: 标了 ``volumes`` 的必须真有分支、KB 里教的 `massing.shape` 取值必须是表内成员
#: （`circle` 就是这么发现 KB 与枚举不一致的）。
_SHAPE_ENUM: dict[str, str] = {
    "rectangle": "plain",
    "l_shape": "volumes",
    "u_shape": "volumes",
    "stepped": "volumes",
    "courtyard": "volumes",
    "circle": "label",
    "linear": "label",
    "radial": "label",
    "bowl": "label",
    "terminal": "label",
    "tower": "label",
    "twin_tower": "label",
    "pavilion": "label",
    "basilica": "label",
    "centralized": "label",
    "underground": "label",
}

#: 形状标签的字符上限。**与 `app.design.contracts.MassingDecision.shape` 的
#: ``max_length`` 同值**（守卫测试比对两者，不是靠注释提醒）：
#: 越界会让契约校验直接硬失败，而"模型的形状词太长"绝不该掐掉整轮生成。
_SHAPE_LABEL_MAX = 40


def coerce_shape_label(value: object) -> str:
    """把作者写的形状标签清成契约能收的形式（去空白、小写、截到上限）。

    **不做成员校验** —— 枚举不是闸，表外名字照样保留（见 `_SHAPE_ENUM`）。
    只做两件契约要求的事：非空、不超长。
    """

    text = str(value or "").strip().lower()
    return text[:_SHAPE_LABEL_MAX]


_ARCHITECTURE_PROFILES: dict[str, dict[str, Any]] = {
    "custom": {
        # 不带 label："自定义建筑"这类档位标签
        # 一旦进提示词就会被模型当成设计主题写进 concept（实测"生成一个四角亭子"
        # 产出 concept"自定义建筑、比例清晰、入口有识别度"的四层别墅）。
        # 档案只提供物理边界，类型/风格/形态完全由用户请求 + 知识库决定。
        "id": "custom",
        "width_range": (4.0, 300.0),
        "depth_range": (4.0, 300.0),
        "floor_range": (1, 200),
        "default_massing": (12.0, 9.0, 2, 3.2),
        "max_explicit_floors": 12,
        # 形状词表由 `_SHAPE_ENUM` 派生（一处定义）：它进提示词告诉模型"有哪些可用"。
        # 越界值不在这里拦 —— 见 `_SHAPE_ENUM` 的注释。
        "shapes": set(_SHAPE_ENUM),
        "base_components": ["door", "window", "roof"],
        # 档案默认要求主入口；设计清单显式排除 door 时（地下车站等）由
        # planning 的 entrance_required 语义放宽——见 _fallback_plan / normalize。
        "require_front_entrance": True,
        "default_roof": "gable",
    },
}


def _clamp_number(value: object, low: float, high: float, default: float) -> float:
    """返回值**恒在 [low, high] 内**——包括走 default 分支的时候。

    🔴 default 也必须夹取（2026-09-30 四角凉亭线上事故）：`entrance_bay` 的调用点
    ``_clamp_number(item.get("entrance_bay"), 1, bays, base["entrance_bay"])`` 里
    ``high=bays`` 是动态值——模型写 ``bays: 0``（夹成 1）而档案 default=3 时，
    不夹 default 就会把 ``ground[3-1]`` 打进长度 1 的列表，
    抛 ``IndexError: list assignment index out of range`` 掐掉整轮生成。
    对 default 本来就在界内的既有调用点，这里是零行为变化。
    """
    if isinstance(value, bool):
        return max(low, min(high, default))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return max(low, min(high, default))
    if not math.isfinite(number):
        return max(low, min(high, default))
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
    """提取用户**明确说出的形状词**，优先于模型方案中的旧值。

    它唯一的不可替代作用：**用户显式表态 > 模型推断**（"把体量改成 U 形"必须生效，
    不能让模型的自选把它顶掉）。所以词表必须只收**显式形状词**。

    🔴 2026-10-08 实测（真实语料对照实验，见
    `.workbuddy/diag/audit_requested_shape_hitrate.py`）：

    - 「**在庭院里**设计一个四角凉亭…」→ 旧实现正则给 `courtyard`；
    - 「生成一个四角凉亭」→ 正则不命中，模型自己写 `pavilion`（与 KB
      `pavilion-garden-structure.md` 一致）。

    两例的 `volumes` 完全相同（单体 4×4 `pavilion_main`），唯一差别就是"在庭院里"
    四个字 —— 也就是说旧实现**用场地词压掉了模型的正确答案**。因此删掉：

    - ``庭院``／``中庭``：**场地/室内空间**词，不是建筑自身平面形态；亭台常"在庭院里"，
      它一命中就把亭子判成围合式四合院（`_fallback_volumes` 的 courtyard 分支真会
      生成四块体量）。
    - ``退台``：**工艺/部位**词。模型看到原文自己会选 `stepped`（语料 3 例全对），
      正则去猜它只是与模型抢方向盘。

    已知不精确（**有意不拦**）：它不看形状词修饰的是谁 ——「屋顶应该也是 L 形状的」
    里那四个字仍是形状词，照样会命中（语料 1 例）。判"这个词在说屋顶还是说体量"需要
    句法级判断，正则做不到；而为此收窄（要求"平面/体量/整体"作限定词）会漏掉
    "二层为U形"这类**真**表态 —— 漏判（用户明说了却没被尊重）比误判更贵。
    """

    if re.search(r"(?:^|[^a-z])u\s*(?:形|型)", user_message, re.I):
        return "u_shape"
    if re.search(r"(?:^|[^a-z])l\s*(?:形|型)", user_message, re.I):
        return "l_shape"
    # `回字形/回形` 是平面形态；`合院` 是围合式形制（"生成一个四合院"实测就该是它）。
    # 🔴 `合院` 必须带负向断言：`围合院落` 里也含"合院"两个连续字（`围合`+`院落` 的
    # 跨词切分），裸子串匹配会把"围合院落式住宅"误判成 courtyard——这正是本轮要消除的
    # 那类"看起来像形状表态"的误命中，写测试时当场撞上。
    if re.search(r"回字形|回形|(?<!围)合院", user_message):
        return "courtyard"
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
) -> dict[str, Any]:
    """返回固定的标准复杂度目标。

    2026-09-30 用户决策：前端粒度选择已下线，复杂度固定为标准档。
    保留函数与返回结构是为了不破坏下游契约；多体量意图仍按用户原文
    点名（"多体量/退台"等）放开 min_volumes。
    """
    result = deepcopy(_COMPLEXITY_PROFILES["standard"])
    result["min_detail_packages"] = 0
    if not any(term_is_requested(user_message, word) for word in ("多体量", "组合体量", "退台", "错落", "主次体量")):
        result["min_volumes"] = 1
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
        # 柱的点名词：围廊/门廊/景观柱按点名进入配额（引擎原生元素，2026-09-29 起可派发）。
        "column": ("柱廊", "廊柱", "罗马柱", "柱子", "石柱"),
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


#: 🔴 **建筑类型词闭集**——"这句话是不是在要建筑"的路由判据，**唯一身份**。
#:
#:
#: 判据为什么建在闭集这一侧：建筑是**有限闭集**，所以"没命中任何建筑类型词"
#: 可以安全地推出"用户要的不是建筑"；而物件名是**开放集**（桌子、小人、机器人、
#: 花瓶、路灯、雕塑……永远列不全），**不能**反过来用"命中了某个物件名词"来判定
#: 目标类型。
#:
#: 目标判定（:mod:`.target_kind`）早期就踩过这个坑：它拿一张家具名词表判"是不是物件"，
#: 没命中就兜底成建筑 —— 于是"生成一个小人"被送去盖房子。改用本闭集之后，
#: "生成一个人/花瓶/路灯/机器人"都会正确落到物件链，不需要为任何一个名字写规则。
_ARCHITECTURE_TYPE_KEYWORDS: tuple[str, ...] = (
    # 交通
    "地铁", "地下车站", "站台层", "地下站", "隧道",
    # 高层
    "超高层", "高层", "摩天", "塔楼",
    # 大跨公共
    "体育场", "体育馆", "游泳馆", "航站楼", "高铁站", "火车站",
    "客运站", "剧院", "音乐厅", "会展", "大会堂",
    # 工农业
    "工厂", "厂房", "仓库", "车间", "物流中心", "机库",
    "温室", "粮仓",
    # 园林
    "园林", "水榭", "凉亭", "亭子", "游廊",
    # 宗教
    "佛寺", "寺庙", "道观", "清真寺", "教堂", "礼拜殿",
    # 公共
    "办公", "写字楼", "学校", "幼儿园", "教学楼", "博物馆",
    "图书馆", "医院", "商场", "超市", "酒店", "法院", "养老院",
    # 居住（含口语与英文）
    "别墅", "住宅", "民居", "民房", "公寓", "洋房", "排屋", "联排", "独栋",
    "自建房", "木屋", "小屋", "房子", "房屋",
    "house", "villa", "cottage", "cabin",
)

#: 跨类型的**通用建筑名词**：能确定"这是建筑"，但不携带任何类型语义。
_GENERIC_ARCHITECTURE_WORDS: tuple[str, ...] = (
    "建筑", "构筑物", "场地", "大厦", "商厦",
    "楼", "屋", "房", "塔", "阁", "苑", "站", "厂",
)

#: 路由闭集 = 类型词 ∪ 通用建筑名词（``is_architecture_request`` 唯一判据）。
_ARCHITECTURE_TYPE_WORDS: tuple[str, ...] = tuple(
    dict.fromkeys(_ARCHITECTURE_TYPE_KEYWORDS)
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


def detect_architecture_profile(
    user_message: str = "",
    fallback_profile_id: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """返回本次生成使用的规划档案。

    ``profile_id`` 是**分类器**（Layer -1，``intent/workflow.py``）给出的形制标签：
    它由模型在**同一个意图分类调用**里自行判断，本函数只把它落成档案 id。
    """

    del user_message, fallback_profile_id

    profile = deepcopy(_ARCHITECTURE_PROFILES["custom"])
    # 只做长度/空白清洗，不做枚举校验：认不出的标签原样保留，缺失才退 custom。
    label = str(profile_id or "").strip().lower()[:40]
    profile["id"] = label or "custom"
    return profile
