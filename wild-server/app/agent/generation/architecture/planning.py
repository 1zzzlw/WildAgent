"""建筑方案回退与归一化。"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from app.agent.generation.components import get_implemented_components
from app.agent.knowledge.policy import term_is_requested

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
    detect_architecture_profile,
    resolve_complexity_profile,
)
def _fallback_plan(
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
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
        if (
            profile["id"] == "high_rise"
            and any(word in user_message for word in ("综合体", "商业基座", "裙房", "基座"))
        )
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
            for opening_type in pattern:
                if opening_type in counts:
                    counts[opening_type] += 1
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
    # 相邻体量共享边合法。过去任一重叠即整份回退、丢弃 LLM 全部设计；现在改为
    # 逐项修复：按优先级保留主体积，把次级体积沿重叠方向推移出界，仍无法修复
    # 才整体回退。缺层时把最近体积的楼层区间扩展覆盖，避免方案被整份丢弃。
    volumes = _repair_volume_overlaps(volumes, width, depth)
    volumes = _repair_volume_floor_gaps(volumes, modeled_floors)
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


def _repair_volume_overlaps(
    volumes: list[dict[str, Any]],
    width: float,
    depth: float,
) -> list[dict[str, Any]]:
    """把同一楼层有正面积重叠的次级体量沿重叠方向推移出主体积。

    主体积（role=primary）优先级最高，不动它；次级体量按“重叠量最小的
    可推方向”移位。推移后允许与主体积共享边（重叠量收敛到 0）。
    """
    repaired = [dict(item) for item in volumes]
    for first_index, first in enumerate(repaired):
        if first["role"] != "primary":
            continue
        first_x1 = first["x"] + first["width"]
        first_z1 = first["z"] + first["depth"]
        for second_index, second in enumerate(repaired):
            if first_index == second_index or second["role"] == "primary":
                continue
            floors_overlap = (
                max(first["start_floor"], second["start_floor"])
                <= min(first["end_floor"], second["end_floor"])
            )
            if not floors_overlap:
                continue
            overlap_x = min(first_x1, second["x"] + second["width"]) - max(first["x"], second["x"])
            overlap_z = min(first_z1, second["z"] + second["depth"]) - max(first["z"], second["z"])
            if overlap_x <= 0.01 or overlap_z <= 0.01:
                continue
            # 两个可推方向：向右推 overlap_x，或向上推 overlap_z。选位移后
            # 仍能留在场地范围内的那一个；若都出界则保留原样由调用方整体回退。
            shift_right_ok = second["x"] + overlap_x + second["width"] <= width + 0.001
            shift_up_ok = second["z"] + overlap_z + second["depth"] <= depth + 0.001
            if shift_right_ok and shift_up_ok:
                # 优先选择位移较小的方向，避免次级体量被大幅移动。
                if overlap_x <= overlap_z:
                    second["x"] = round(second["x"] + overlap_x, 2)
                else:
                    second["z"] = round(second["z"] + overlap_z, 2)
            elif shift_right_ok:
                second["x"] = round(second["x"] + overlap_x, 2)
            elif shift_up_ok:
                second["z"] = round(second["z"] + overlap_z, 2)
    return repaired


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
        "x_bays": int(_clamp_number(source.get("x_bays"), 1, 12, fallback["x_bays"])),
        "z_bays": int(_clamp_number(source.get("z_bays"), 1, 12, fallback["z_bays"])),
    }


def normalize_architecture_plan(
    raw: object,
    user_message: str = "",
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把模型方案压缩到稳定、有限的架构规划协议。"""
    complexity = deepcopy(
        complexity_profile or resolve_complexity_profile(user_message)
    )
    profile = deepcopy(architecture_profile or detect_architecture_profile(user_message))
    fallback = _fallback_plan(user_message, complexity, profile)
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
    if complexity["level"] in {"minimal", "simple"}:
        # 简化模式只保留用户明确点名的细部。fallback 的细部列表在这两种
        # 模式下只包含显式关键词，可阻止模型自行添加凸窗等装饰硬配额。
        explicitly_requested = set(fallback["detail_packages"])
        detail_packages = [
            item for item in detail_packages
            if item in explicitly_requested
        ]
        detail_packages = list(dict.fromkeys([
            *detail_packages,
            *fallback["detail_packages"],
        ]))
    if (
        curtain_wall
        and profile["id"] == "high_rise"
        and not any(word in user_message for word in ("凸窗", "飘窗"))
        and "bay_window" in detail_packages
    ):
        # 连续高层幕墙与凸窗是相互冲突的立面系统。模型常为凑足“细部包”
        # 随手加入 bay_window；未被用户明确要求时改用入口/转折照明。
        detail_packages = [
            item for item in detail_packages if item != "bay_window"
        ]
        if "light" not in detail_packages:
            detail_packages.append("light")
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
            # entrance_bay 必须在 [1, bays] 范围内，即使是 fallback 值也要检查
            entrance_bay = min(int(base.get("entrance_bay", 1)), bays) if "entrance_bay" in base else None
        else:
            bays = int(_clamp_number(item.get("bays"), 1, 9, base["bays"]))
            ground = _normalize_pattern(item.get("ground_pattern"), bays, base["ground_pattern"])
            upper = _normalize_pattern(item.get("upper_pattern"), bays, base["upper_pattern"])
            # 只有base中有entrance_bay的立面（front）才处理entrance_bay
            if "entrance_bay" in base:
                entrance_bay = int(_clamp_number(item.get("entrance_bay"), 1, bays, base.get("entrance_bay", 1)))
            else:
                entrance_bay = None
        if profile["require_front_entrance"] and face == "front" and "door" not in ground:
            if entrance_bay is None:
                entrance_bay = (bays + 1) // 2  # 默认放在中间
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

    roof_raw = source.get("roof") if isinstance(source.get("roof"), dict) else {}
    roof_type = str(roof_raw.get("type") or fallback["roof"]["type"]).lower()
    if roof_type not in _SUPPORTED_ROOF_TYPES:
        roof_type = fallback["roof"]["type"]
    roof = {
        "type": roof_type,
        "ridge_axis": "z" if str(roof_raw.get("ridge_axis", "x")).lower() == "z" else "x",
        "overhang": round(_clamp_number(roof_raw.get("overhang"), 0, 2, fallback["roof"]["overhang"]), 2),
    }

    quotas = {
        component_type: deepcopy(limits)
        for component_type, limits in fallback["component_quota"].items()
        if (
            component_type not in _DETAIL_COMPONENT_QUOTAS
            or component_type in detail_packages
        )
    }
    allowed_components = {config.component_type for config in get_implemented_components()}
    unsupported_component_types = set()
    raw_quotas = source.get("component_quota") if isinstance(source.get("component_quota"), dict) else {}
    for component_type, limits in raw_quotas.items():
        if not isinstance(limits, dict):
            continue
        component_type = str(component_type)
        if component_type not in allowed_components:
            unsupported_component_types.add(component_type)
            continue
        if (
            component_type in _DETAIL_COMPONENT_QUOTAS
            and component_type not in detail_packages
            and (
                complexity["level"] in {"minimal", "simple"}
                or (
                    curtain_wall
                    and profile["id"] == "high_rise"
                    and component_type == "bay_window"
                )
            )
        ):
            # 简化模式只接受用户明确点名的细部；高层连续幕墙也不能被模型
            # 通过配额重新塞入未批准的凸窗。其余模式继续兼容“正配额补全
            # required_components”的既有协议。
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
        quotas[component_type] = normalized_limits
    if (
        complexity.get("level") != "minimal"
        and massing["representation_mode"] == "full"
    ):
        opening_counts = _facade_opening_counts(facades, modeled_floors)
        for opening_type in ("door", "window"):
            if opening_type not in profile["base_components"]:
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

    required = source.get("required_components")
    if not isinstance(required, list):
        required = fallback["required_components"]
    required_components = [
        str(item).lower() for item in required
        if (
            str(item).lower() in allowed_components
            and (
                str(item).lower() not in _DETAIL_COMPONENT_QUOTAS
                or str(item).lower() in detail_packages
            )
        )
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

    circulation_source = source.get("circulation") if isinstance(source.get("circulation"), dict) else {}
    default_vertical_strategy = (
        "none" if modeled_floors <= 1
        else "core_and_stair" if profile["id"] == "high_rise"
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
    circulation = {"vertical_strategy": vertical_strategy}

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
        "circulation": circulation,
        "detail_packages": detail_packages,
        "facades": facades,
        "roof": roof,
        "component_quota": quotas,
        "curtain_wall": curtain_wall,
        "balcony_access_count": balcony_access_count,
        "balcony_width": balcony_width,
        "required_components": list(dict.fromkeys(required_components)),
        "unsupported_component_types": sorted(unsupported_component_types),
        "design_rationale": [str(item)[:160] for item in rationale[:6]],
    }




