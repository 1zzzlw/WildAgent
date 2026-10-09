"""建筑方案回退与归一化。"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from app.agent.knowledge.policy import term_is_requested
from app.design.openings import is_open_side, opening_kind, opening_token, split_opening

from .profile import (
    _DETAIL_COMPONENT_QUOTAS,
    _FACES,
    _OPENING_TYPES,
    _SUPPORTED_ROOF_TYPES,
    _clamp_number,
    _default_detail_packages,
    _fallback_volumes,
    _requested_balcony_access_count,
    _requested_balcony_width,
    _requested_dimension,
    _requested_floors,
    _requested_plan_dimensions,
    _requested_shape,
    coerce_shape_label,
    detect_architecture_profile,
    resolve_complexity_profile,
)


def _note(notes: list[str] | None, message: str) -> None:
    """把一条归一化记账写进调用方的诊断列表（``None`` = 这次调用不需要记账）。

    为什么用出参而不是返回值：`normalize_architecture_plan` 是链上复用最广的纯函数
    （6 处生产调用点），改返回类型会波及所有调用方；用 keyword-only 出参只影响关心
    记账的那一处 —— 与 `resolver.attach_material_plan(role_repairs=…)` 同一手法。
    """

    if notes is not None:
        notes.append(message)


def _concept_from_request(user_message: str) -> str:
    """从用户请求原文提炼方案名（concept 兜底）。

    用户说"生成一个四角亭子"，蓝图名就应该是"四角亭子"——不是风格词，
    更不是"比例清晰、入口有识别度"这种硬编码空话（旧兜底实测把每栋楼都
    命名成同一句话）。只剥请求动词与量词前缀，主体原样保留。
    """
    text = str(user_message or "").strip()
    text = re.sub(r"^(?:请|帮我|给我|麻烦|帮忙)?(?:生成|创建|设计|搭建|做|做个|做一|画|绘制|来|要|想要)", "", text)
    text = re.sub(r"^(?:一个|一座|一间|一栋|一幢|个|座)", "", text)
    text = text.strip("，。,. 、！!？?")
    return (text or "建筑方案")[:24]


def _fallback_plan(
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    base_override: list[str] | None = None,
) -> dict[str, Any]:
    profile = deepcopy(architecture_profile or detect_architecture_profile(user_message))
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
    is_european = any(term_is_requested(user_message, word) for word in ("欧式", "法式", "古典"))
    is_chinese = any(term_is_requested(user_message, word) for word in ("中式", "新中式", "庭院"))
    is_modern = any(term_is_requested(user_message, word) for word in ("现代", "极简"))
    roof_type = (
        "hip" if is_european else "chinese_curved" if is_chinese
        else "flat" if is_modern else profile["default_roof"]
    )
    # 入口强制语义（2026-09-29 修订）：档案默认要求主入口，但设计清单显式排除
    # door 时（如地下车站）不再强制——"要不要门"由设计说了算，档案只定默认。
    require_entrance = profile["require_front_entrance"] and (
        base_override is None or "door" in base_override
    )
    front_ground = (
        ["window", "empty", "door", "empty", "window"]
        if require_entrance else ["empty", "empty", "empty", "empty", "empty"]
    )
    base_components = (
        list(base_override) if base_override is not None else list(profile["base_components"])
    )
    # 开放集语义（用户决策 2026-09-29）：``base_override`` 来自设计清单显式给出的
    # ``required_components``（由调用方从 source 读出传入），是**权威**——它声明了
    # 这栋建筑需要哪些基础构件（如地下车站只要 light、无屋盖场景不要 roof），
    # 回退层不得再用档案默认值强行配额。
    curtain_wall = (
        term_is_requested(user_message, "玻璃幕墙")
        or term_is_requested(user_message, "玻璃幕")
    )
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
        if int(complexity.get("min_volumes", 1)) > 1 and "stepped" in profile["shapes"]
        else "rectangle"
    )
    volumes = _fallback_volumes(
        width, depth, modeled_floors, complexity, resolved_shape,
    )
    default_x_bays, default_z_bays = complexity["grid_bays"]
    structural_system = (
        "long_span" if profile["id"] in {"long_span_public", "industrial_long_span"}
        else "frame" if profile["id"] in {"ordinary_public", "high_rise"}
        else "wall_bearing"
    )
    return {
        "schema_version": "1.1",
        "profile": profile["id"],
        "concept": _concept_from_request(user_message),
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


def _normalize_pattern(
    value: object, bays: int, fallback: list[str], *, allowed_types: set[str] | None = None,
) -> list[str]:
    """把一面的 pattern 压成 ``bays`` 个**合法开口 token**。

     token 的解析一律走 `app.design.openings.split_opening`（§3.3）——**不在这里 `split(":")`**：
    契约层、本函数、立面编译、`resolver` 四处读同一串东西，分头解析必然分叉（且不报错）。

     非法形态**只丢形态、不丢开口**：``"window:casement"`` → ``"window"``，
    照常生成、形态由编译器派生。旧值 ``"window"`` 的行为一个字节不改。
    """

    raw = value if isinstance(value, list) else fallback
    allowed = _OPENING_TYPES if allowed_types is None else allowed_types
    pattern: list[str] = []
    for item in raw:
        kind, form = split_opening(item)
        if kind not in allowed:
            kind, form = "empty", None
        pattern.append(opening_token(kind, form))
    if len(pattern) < bays:
        pattern.extend(["empty"] * (bays - len(pattern)))
    return pattern[:bays]


def _facade_opening_counts(
    facades: dict[str, dict[str, Any]],
    modeled_floors: int,
) -> dict[str, int]:
    """统计归一化立面方案中会实际执行的门窗槽位。"""
    counts = {"door": 0, "window": 0}
    upper_repetitions = max(0, int(modeled_floors) - 1)
    for facade in facades.values():
        if not isinstance(facade, dict):
            continue
        layers = [facade.get("ground_pattern", [])]
        layers.extend([facade.get("upper_pattern", [])] * upper_repetitions)
        for pattern in layers:
            if not isinstance(pattern, list):
                continue
            for raw_opening in pattern:
                kind = opening_kind(raw_opening)
                if kind in counts:
                    counts[kind] += 1
    return counts


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

    from app.design.contracts import VolumeDecision
    from app.design.coordinates import DesignCoordinateConflict, volume_conflicts

    volumes = []
    if not 1 <= len(raw) <= 8:
        raise DesignCoordinateConflict([{"path": "/decisions/volumes", "value": raw,
            "conflict_path": "VolumeDecision", "reason": "体量数量必须为 1 到 8，不能丢弃显式条目"}])
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DesignCoordinateConflict([{"path": f"/decisions/volumes/{index}", "value": item,
                "conflict_path": "VolumeDecision", "reason": "体量必须是对象"}])
        # 只补缺省字段；显式坐标、尺寸和楼层绝不夹取或重解释。
        candidate = {"id": f"volume_{index+1}", "role": "primary", "x": 0, "z": 0,
                     "width": width, "depth": depth, "start_floor": 1,
                     "end_floor": modeled_floors, **item}
        try:
            volumes.append(VolumeDecision.model_validate(candidate).model_dump(mode="json"))
        except ValueError as exc:
            raise DesignCoordinateConflict([{"path": f"/decisions/volumes/{index}", "value": item,
                "conflict_path": "VolumeDecision", "reason": str(exc)}]) from exc
    conflicts = volume_conflicts(volumes, massing)
    if len({v["id"] for v in volumes}) != len(volumes):
        conflicts.append({"path": "/decisions/volumes", "value": raw,
                          "conflict_path": "volumes.id", "reason": "体量 ID 重复"})
    missing = [level for level in range(1, modeled_floors+1)
               if not any(v["start_floor"] <= level <= v["end_floor"] for v in volumes)]
    if missing:
        conflicts.append({"path": "/decisions/volumes", "value": raw,
                          "conflict_path": "/decisions/massing/modeled_floors",
                          "reason": f"楼层 {missing} 缺少体量，必须显式修订楼层覆盖"})
    if conflicts:
        raise DesignCoordinateConflict(conflicts)
    return volumes


def _repair_volume_floor_gaps(
    volumes: list[dict[str, Any]],
    modeled_floors: int,
) -> list[dict[str, Any]]:
    """补齐未被任何体量覆盖的楼层：把最近体量的 end_floor 扩展到该层。"""
    repaired = [dict(item) for item in volumes]
    for level in range(1, modeled_floors + 1):
        if any(volume["start_floor"] <= level <= volume["end_floor"] for volume in repaired):
            continue
        # 找 end_floor 距离该层最近、且未覆盖它的体量；优先主体积。
        def _distance(volume: dict[str, Any]) -> int:
            return min(abs(volume["end_floor"] - level), abs(volume["start_floor"] - level))

        candidates = [volume for volume in repaired if not (
            volume["start_floor"] <= level <= volume["end_floor"]
        )]
        if not candidates:
            continue
        candidates.sort(key=lambda volume: (0 if volume["role"] == "primary" else 1, _distance(volume)))
        candidates[0]["end_floor"] = max(candidates[0]["end_floor"], level)
    return repaired


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
        "x_bays": int(_clamp_number(source.get("x_bays"), 1, 32, fallback["x_bays"])),
        "z_bays": int(_clamp_number(source.get("z_bays"), 1, 32, fallback["z_bays"])),
    }


def normalize_architecture_plan(
    raw: object,
    user_message: str = "",
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    *,
    normalize_notes: list[str] | None = None,
    normalization_changes: list[dict] | None = None,
    input_source: str = "unknown",
) -> dict[str, Any]:
    """把模型方案压缩到稳定、有限的架构规划协议。

    ``normalize_notes`` 是可选出参：把归一化过程中"用户覆盖了模型""模型写了表外值"
    这类取舍保留为兼容文本。``normalization_changes`` 返回字段级来源和变更，
    由调用方写入既有诊断与设计 rule_trace，不参与后续几何计算。
    """
    # `source` 先取：plan 里可能已经带着上游（分类器）或上一轮判定的形制 id。
    source = raw if isinstance(raw, dict) else {}
    complexity = deepcopy(
        complexity_profile or resolve_complexity_profile(user_message)
    )
    #  profile 三级取值：显式传入 > **计划里已有的 id** > 重算（缺省 custom）。
    # 中间那一档是必需的：本函数在链上被多处**二次调用**（`compiler._compose`、
    # `build_deterministic_skeleton`、`probe_tool` 等），它们手里只有 plan、不会
    # 再传 `architecture_profile` —— 少了这一档就会把分类器判出的形制标签静默洗回
    # `custom`（实测 `compiler/compile.py:1234` 与 `skeleton.py:727` 两处正是如此）。
    # 只沿用 **id**：物理边界照旧由 `detect_architecture_profile` 给（恒为 custom 档）。
    carried_profile_id = source.get("profile")
    profile = deepcopy(
        architecture_profile
        or detect_architecture_profile(
            user_message,
            profile_id=carried_profile_id if isinstance(carried_profile_id, str) else None,
        )
    )
    # 开放集语义：设计清单显式给出的 required_components 是权威（见 _fallback_plan）。
    requested_required = source.get("required_components")
    explicit_base: list[str] | None = (
        [str(item) for item in requested_required if isinstance(item, str)]
        if isinstance(requested_required, list)
        else None
    )
    fallback = _fallback_plan(user_message, complexity, profile, base_override=explicit_base)
    curtain_wall = bool(source.get("curtain_wall", fallback.get("curtain_wall")))
    # 整面 open 明确表达无墙、无门；整面 empty 仍是实墙。
    facade_source_raw = (
        source.get("facades") if isinstance(source.get("facades"), dict) else {}
    )
    front_item_raw = (
        facade_source_raw.get("front")
        if isinstance(facade_source_raw.get("front"), dict)
        else {}
    )
    front_pattern_raw = front_item_raw.get("ground_pattern")
    model_declared_front_open = (
        isinstance(front_pattern_raw, list)
        and is_open_side(front_pattern_raw)
    )
    # 门窗/屋顶强制配额的判据同源：模型表态过的 required_components 优先于档案默认。
    if explicit_base is not None:
        base_components_effective = list(explicit_base)
    elif model_declared_front_open:
        # 开敞声明等效于"排除 door"：档案默认必备件里去掉 door，
        # 否则 required_components / 配额仍点名 door，交付层报"未落实"。
        base_components_effective = [
            item for item in profile["base_components"] if item != "door"
        ]
    else:
        base_components_effective = list(profile["base_components"])
    # 主入口强制语义：档案默认要求，但出现任一显式豁免时不强制——
    # ① 设计清单显式排除 door；② front 面被模型显式声明为全空开敞。
    entrance_required = (
        bool(profile["require_front_entrance"])
        and not model_declared_front_open
        and (explicit_base is None or "door" in explicit_base)
    )
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
    # 形状三级取值：**用户显式形状词 > 模型表态 > 确定性兜底**。
    #  中间这级不能被忽略：模型自选的形制名（pavilion / tower / 表外的自定义标签）
    # 才是设计的真实来源，正则只在"用户把形状词说出口"时才该压它一头。
    model_shape = coerce_shape_label(massing_raw.get("shape"))
    resolved_shape = requested_shape or model_shape or coerce_shape_label(
        fallback["massing"]["shape"]
    )
    if requested_shape and model_shape and requested_shape != model_shape:
        # 覆盖必须记账：这条链上"谁把 U 形改成了矩形"以前是查不出来的
        # （正则无声、模型无声、兜底无声）。
        _note(
            normalize_notes,
            f"massing.shape：用户显式形状词 {requested_shape} 覆盖模型值 {model_shape}",
        )
    massing = {
        "shape": resolved_shape,
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
            6.0,
            fallback["massing"]["floor_height"],
        ), 2),
        "symmetry": bool(massing_raw.get("symmetry", fallback["massing"]["symmetry"])),
    }
    if massing["shape"] not in profile["shapes"]:
        # 表外形状**不是错误，是"本档没有专门几何行为"**：按仅标签语义照原样保留
        # （与 `pavilion` / `tower` 这些形制名同类），并记账。
        # 2026-10-08 前这里是 `massing["shape"] = "rectangle"`：既抹掉模型的表达、
        # 又不留任何痕迹 —— KB `cone-roof-system.md` 教的 `massing.shape: "circle"`
        # 就是这样被静默吞掉的；而"允许列表"本身也违反项目宪法（枚举是词表不是闸）。
        _note(
            normalize_notes,
            f"massing.shape：{massing['shape']!r} 不在形状枚举内，按仅标签语义保留",
        )
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

    from pydantic import TypeAdapter
    from app.design.contracts import MassingDecision
    candidate_massing = deepcopy(massing)
    for key, field in MassingDecision.model_fields.items():
        if key not in massing_raw or key in {"shape", "representation_mode"}:
            continue
        try:
            candidate_massing[key] = TypeAdapter(field.rebuild_annotation()).validate_python(massing_raw[key])
        except ValueError:
            pass  # Keep the local fallback; preserve evidence for this field below.
    for key, requested in (("width", requested_width), ("depth", requested_depth), ("floors", requested_floors)):
        if requested is not None:
            try:
                candidate_massing[key] = TypeAdapter(MassingDecision.model_fields[key].rebuild_annotation()).validate_python(requested)
            except ValueError:
                candidate_massing[key] = massing[key]
    if requested_floors is not None and requested_floors != massing_raw.get("floors"):
        candidate_massing["modeled_floors"] = massing["modeled_floors"]
    candidate_massing["modeled_floors"] = min(candidate_massing["modeled_floors"], candidate_massing["floors"])
    candidate_massing["representation_mode"] = (
        "full" if candidate_massing["modeled_floors"] == candidate_massing["floors"] else "schematic")
    if candidate_massing.get("tiers") and sum(t.floors for t in candidate_massing["tiers"]) != candidate_massing["floors"]:
        candidate_massing.pop("tiers")
    massing = MassingDecision.model_validate(candidate_massing).model_dump(mode="json", exclude_none=True)
    modeled_floors = int(massing["modeled_floors"])
    volumes = _normalize_volumes(source.get("volumes"), massing, complexity)
    structural_grid = _normalize_structural_grid(
        source.get("structural_grid"), fallback["structural_grid"],
    )
    raw_detail_packages = source.get("detail_packages")
    allowed_detail_packages = set(_DETAIL_COMPONENT_QUOTAS)
    # 用户点名的细部包是本次方案的硬需求：`_default_detail_packages` 只由显式关键词
    # 产生（不含默认套餐），所以"模型没写"就是"用户没要"，反过来"用户要了"就必须留下。
    # 模型可以补充，但**不能删除**——实测"生成一个别墅，里面要有家具"会被规划模型以
    # 「家具属于室内设计，不在建筑方案职责内」为由把 detail_packages 写成 `[]`，
    # 照单全收后配额与 required_components 一起消失，最终表现成"要了却一件都没生成"。
    requested_detail_packages = [
        str(item).lower() for item in fallback["detail_packages"]
        if str(item).lower() in allowed_detail_packages
    ]
    if isinstance(raw_detail_packages, list):
        detail_packages = [
            str(item).lower() for item in raw_detail_packages if isinstance(item, str)
        ]
    else:
        detail_packages = []
    # 保留显式细部选择；数量边界沿用 DesignDocument 的 20 项。
    detail_packages = list(dict.fromkeys([
        *requested_detail_packages,
        *detail_packages,
    ]))
    if modeled_floors < 2:
        # 单层建筑没有垂直交通需求（KB《电梯》能力边界明确写"不要生成"）；
        # 这是需求侧的无效项，与模型是否写了它无关，所以在配额之前就剔除。
        detail_packages = [item for item in detail_packages if item != "elevator"]
    if not isinstance(raw_detail_packages, list) and len(detail_packages) < int(complexity["min_detail_packages"]):
        detail_packages = list(dict.fromkeys([
            *detail_packages,
            *fallback["detail_packages"],
        ]))
    detail_packages = detail_packages[:20]

    facade_source = source.get("facades") if isinstance(source.get("facades"), dict) else {}
    facades: dict[str, dict[str, Any]] = {}
    for face in _FACES:
        base = fallback["facades"][face]
        item = facade_source.get(face) if isinstance(facade_source.get(face), dict) else {}
        if curtain_wall and not item:
            # 该面缺少设计时才使用幕墙默认分格；显式 pattern 保留。
            bays = int(base["bays"])
            ground = _normalize_pattern(base["ground_pattern"], bays, base["ground_pattern"])
            upper = _normalize_pattern(base["upper_pattern"], bays, base["upper_pattern"], allowed_types=_OPENING_TYPES - {"door"})
            # entrance_bay 必须在 [1, bays] 范围内，即使是 fallback 值也要检查
            entrance_bay = min(int(base.get("entrance_bay", 1)), bays) if "entrance_bay" in base else None
        else:
            bays = int(_clamp_number(item.get("bays"), 1, 32, base["bays"]))
            ground = _normalize_pattern(item.get("ground_pattern"), bays, base["ground_pattern"])
            upper = _normalize_pattern(item.get("upper_pattern"), bays, base["upper_pattern"], allowed_types=_OPENING_TYPES - {"door"})
            # 显式入口索引可以位于任一立面；None 表示未指定。
            if "entrance_bay" in item and item["entrance_bay"] is None:
                entrance_bay = None
            elif "entrance_bay" in item or "entrance_bay" in base:
                entrance_bay = int(_clamp_number(item.get("entrance_bay"), 1, bays, base.get("entrance_bay", 1)))
            else:
                entrance_bay = None
        if (
            entrance_required
            and face == "front"
            and "ground_pattern" not in item
            and not any(opening_kind(token) == "door" for token in ground)
        ):
            if entrance_bay is None:
                entrance_bay = (bays + 1) // 2  # 默认放在中间
            # 系统补的主门不给形态：让编译器派生（`"door"` 而不是 `"door:swing"`），
            # 这样"没表态"和"表态成 swing"在诊断上仍然区分得开。
            ground[entrance_bay - 1] = "door"
        
        facade_data = {
            "bays": bays,
            "ground_pattern": ground,
            "upper_pattern": upper,
        }
        # 只有确实有entrance_bay的立面才加这个字段
        if entrance_bay is not None:
            facade_data["entrance_bay"] = entrance_bay
        facades[face] = facade_data

    roof_input = source.get("roof")
    # A single-item wrapper can be migrated without inventing a different roof.
    if isinstance(roof_input, list) and len(roof_input) == 1 and isinstance(roof_input[0], dict):
        roof_input = roof_input[0]
    roof_raw = roof_input if isinstance(roof_input, dict) else {}
    roof_type = str(roof_raw.get("type") or fallback["roof"]["type"]).lower()
    if roof_type not in _SUPPORTED_ROOF_TYPES:
        roof_type = fallback["roof"]["type"]
    roof = {
        "type": roof_type,
        "ridge_axis": "z" if str(roof_raw.get("ridge_axis", "x")).lower() == "z" else "x",
        "overhang": round(_clamp_number(roof_raw.get("overhang"), 0, 2, fallback["roof"]["overhang"]), 2),
    }

    from app.design.contracts import RoofDecision
    for key, field in RoofDecision.model_fields.items():
        if key in roof_raw:
            adapter = TypeAdapter(field.rebuild_annotation())
            try:
                value = adapter.validate_python(roof_raw[key])
            except ValueError:
                continue
            # P5-A：``volumes`` 校验出来是**模型对象序列**，直接塞进归一化方案会让下游
            # （facade / compile / json 导出）拿到非 JSON 类型。标量字段经同一个
            # ``dump_python`` 也是原值，所以对两者统一，不必按字段分支。
            roof[key] = adapter.dump_python(value, mode="json")

    quotas = {
        component_type: deepcopy(limits)
        for component_type, limits in fallback["component_quota"].items()
        if (
            component_type not in _DETAIL_COMPONENT_QUOTAS
            or component_type in detail_packages
            # 设计清单显式点名的类型（required_components → base_override）视为
            # 已获批准：地下车站的 light 等功能构件不得在这里被静默丢配额。
            or (explicit_base is not None and component_type in explicit_base)
        )
    }
    unsupported_component_types: set[str] = set()
    raw_quotas = source.get("component_quota") if isinstance(source.get("component_quota"), dict) else {}
    for component_type, limits in raw_quotas.items():
        if not isinstance(limits, dict):
            continue
        component_type = str(component_type)
        # 开放集通道（用户决策 2026-09-29：删除构件白名单闸）：配额点名的任何类型
        # 都放行进入下游——已注册的走既有派生/模型通道，未注册的由 plan 条目用
        # 通用配置尝试（字段契约靠知识库检索），校验与修复环兜底。
        # ``unsupported_component_types`` 保留为协议字段，从此恒空。
        if curtain_wall and component_type == "window":
            # 幕墙窗数量由立面槽位决定，模型配额不得覆盖密集窗格。
            continue
        normalized_limits = deepcopy(limits)
        # 配额上下限不再夹取到 32（用户决策 2026-09-29，删除上限白名单）：
        # 模型可以自由表达密集窗格、通高柱廊等大规模数量；上限只是参考值，
        # 下限才是设计要求。只使用 ComponentQuota 的协议边界及 max>=min 一致性。
        for bound in ("min", "max"):
            if bound in limits:
                try:
                    normalized_limits[bound] = min(10000, max(0, int(limits[bound])))
                except (TypeError, ValueError, OverflowError):
                    normalized_limits[bound] = int(quotas.get(component_type, {}).get(bound, 0))
        if isinstance(normalized_limits.get("min"), int) and isinstance(normalized_limits.get("max"), int):
            normalized_limits["max"] = max(normalized_limits["min"], normalized_limits["max"])
        quotas[component_type] = normalized_limits
    if massing["representation_mode"] == "full":
        opening_counts = _facade_opening_counts(facades, modeled_floors)
        for opening_type in ("door", "window"):
            if opening_type not in base_components_effective:
                continue
            if curtain_wall and opening_type == "window":
                # 幕墙窗数量由立面槽位决定，模型配额不得覆盖密集窗格；
                # 门仍按逐层 pattern 一一对应，否则门配额会与立面槽位数脱钩。
                continue
            planned_count = opening_counts[opening_type]
            quotas[opening_type] = {
                **quotas.get(opening_type, {}),
                "min": planned_count,
                "max": planned_count,
                "note": "由逐层立面 pattern 解析，槽位与组件一一对应",
            }
    if model_declared_front_open:
        # 开敞声明的第三处对齐：fallback 档案默认 door 配额（min=1）不得残留——
        # 841 行按 min>0 补派发会把它塞回 required_components。
        quotas["door"] = {
            **quotas.get("door", {}),
            "min": 0,
            "max": 0,
            "note": "front 面被模型声明为全空开敞，无门槽位",
        }
    roof_required = "roof" in base_components_effective
    quotas["roof"] = {
        **quotas.get("roof", {}),
        "min": 1 if roof_required else 0,
        "max": 1 if roof_required else 0,
        "type": roof_type,
    }
    for component_type in detail_packages:
        if component_type == "balcony" and modeled_floors < 2:
            continue
        if component_type in _DETAIL_COMPONENT_QUOTAS:
            quotas.setdefault(component_type, deepcopy(_DETAIL_COMPONENT_QUOTAS[component_type]))
    balcony_access_count = requested_balcony_access_count if modeled_floors >= 2 else 0
    balcony_width = requested_balcony_width
    if balcony_access_count:
        quotas["balcony"] = {
            **quotas.get("balcony", {}),
            "min": balcony_access_count,
            "max": balcony_access_count,
            "note": "两翼阳台均需与室内直接连通",
        }
        entrance_count = 1 if entrance_required else 0
        door_target = entrance_count + balcony_access_count
        quotas["door"] = {
            **quotas.get("door", {}),
            "min": max(door_target, int(quotas.get("door", {}).get("min", 0))),
            "max": max(door_target, int(quotas.get("door", {}).get("max", 0))),
            "note": "含主入口与阳台通室内入口",
        }

    required = source.get("required_components")
    if not isinstance(required, list):
        required = fallback["required_components"]
        # 开敞声明的第二条豁免（与 base_components_effective 同批）：模型没写
        # required_components 时整表取 fallback，档案默认表里带 door——不清掉
        # 它，交付层就会"点名 door 未落实"。
        if model_declared_front_open:
            required = [item for item in required if str(item).lower() != "door"]
    # 开放集通道（2026-09-29）：不再按注册表白名单过滤——模型点名的类型照常进入
    # required_components，未注册类型由 plan 条目用通用配置尝试。保留的过滤只有
    # 一条纪律：细部包类型必须已被 complexity 批准（与注册表无关）。
    required_components = [
        str(item).lower() for item in required
        if (
            str(item).lower() not in _DETAIL_COMPONENT_QUOTAS
            or str(item).lower() in detail_packages
        )
    ]
    for base_type in base_components_effective:
        if base_type in required_components:
            continue
        # 与上面同一纪律：未获 complexity 批准的细部包类型不得借道混回 required。
        if base_type in _DETAIL_COMPONENT_QUOTAS and base_type not in detail_packages:
            continue
        required_components.append(base_type)
    for component_type in detail_packages:
        if component_type not in required_components:
            required_components.append(component_type)
    # component_quota 是批准后的硬约束；若模型漏写 required_components，
    # 仍必须派发所有最低数量大于零的组件（开放集：不再按注册表过滤）。
    for component_type, limits in quotas.items():
        minimum = limits.get("min", 0) if isinstance(limits, dict) else 0
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and minimum > 0
            and component_type not in required_components
        ):
            required_components.append(component_type)
    required_components = [
        component_type for component_type in required_components
        if quotas.get(component_type, {}).get("max", 1) != 0
    ]

    circulation_source = source.get("circulation") if isinstance(source.get("circulation"), dict) else {}
    default_vertical_strategy = (
        "none" if modeled_floors <= 1
        # 核心筒化按**层数**（物理疏散需求）触发，与建筑类型无关——
        # 选档白名单删除后，高层规则的正确落点是楼层阈值而不是类型词表。
        else "core_and_stair" if modeled_floors >= 8
        else "stair"
    )
    vertical_strategy = str(
        circulation_source.get("vertical_strategy") or default_vertical_strategy
    ).lower()
    # 旧版允许单独选择 core，但当前核心筒只表达围合墙体，不能承担层间通行。
    # 将旧值收敛到“核心筒 + 楼梯”，避免多层方案在骨架阶段合法、交付阶段失败。
    if vertical_strategy == "core":
        vertical_strategy = "core_and_stair"
    if vertical_strategy not in {"none", "stair", "core_and_stair"}:
        vertical_strategy = default_vertical_strategy
    if modeled_floors > 1 and vertical_strategy == "none":
        vertical_strategy = default_vertical_strategy
    if modeled_floors > 1 and "elevator" in detail_packages:
        # 电梯必须有井道围合，而 `core_and_stair` 是唯一会生成 `wall_core_*` 骨架的策略
        # （`stair` 只放楼梯）。用户点了电梯却停留在 `stair` 时，轿厢没有井道可放，
        # 只能悬在建筑里；这里把策略升级到配套的核心筒，而不是让下游去猜。
        vertical_strategy = "core_and_stair"
    circulation = {"vertical_strategy": vertical_strategy}

    rationale = source.get("design_rationale")
    if not isinstance(rationale, list):
        rationale = fallback["design_rationale"]
    
    # §3.4: 保留构件实例清单
    components = source.get("components")
    if not isinstance(components, list):
        components = []
    
    result = {
        "schema_version": "1.1",
        "profile": profile["id"],
        "concept": str(source.get("concept") or fallback["concept"])[:240],
        "massing": massing,
        "volumes": volumes,
        "structural_grid": structural_grid,
        "circulation": circulation,
        "detail_packages": detail_packages,
        "facades": facades,
        "roof": roof,
        "component_quota": quotas,
        "components": components,
        "curtain_wall": curtain_wall,
        "balcony_access_count": balcony_access_count,
        "balcony_width": balcony_width,
        "required_components": list(dict.fromkeys(required_components)),
        "unsupported_component_types": sorted(unsupported_component_types),
        "design_rationale": [str(item)[:160] for item in rationale[:6]],
    }

    # §3.4 / P5-C：区域与构件材质绑定。**归一化不解释它**（角色闭集在材质方案那边，
    # 这里硬校验必然误拒），只做形状过滤后透传；认不出形状的条目丢掉即可 ——
    # 绑定写错由编译器记缺陷，不阻断。
    raw_regions = (source.get("materials") or {}).get("regions") if isinstance(source.get("materials"), dict) else None
    if not isinstance(raw_regions, list):
        raw_regions = source.get("material_regions") or []
    regions = [
        {
            "role": str(item["role"])[:60],
            **({"type": str(item["type"])[:60]} if item.get("type") else {}),
            **({"note": str(item["note"])[:200]} if item.get("note") else {}),
        }
        for item in raw_regions or []
        if isinstance(item, dict) and str(item.get("role") or "").strip()
    ][:20]
    if regions or "materials" in source or "material_regions" in source:
        result["materials"] = {"regions": regions}

    from app.design.normalization import plan_changes, decision_summary
    changes = plan_changes(source, result, source=input_source)
    if normalization_changes is not None:
        normalization_changes.extend(changes)
    semantic = any(c["semantic_change"] for c in changes)
    rationale = [text for text in result["design_rationale"] if not text.startswith("[决策事实]")]
    if semantic:
        rationale = [text if text.startswith("[待核对]") else "[待核对] " + text for text in rationale]
    result["design_rationale"] = [decision_summary(result), *rationale[:5]]
    if "design_constraints" in source:
        result["design_constraints"] = deepcopy(source["design_constraints"])
    if "complexity" in source:
        result["complexity"] = deepcopy(source["complexity"])
    return result
