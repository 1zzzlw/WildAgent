"""建筑方案校验与归一化，不补造缺失的建筑设计。"""

from __future__ import annotations

from copy import deepcopy
from collections import Counter
import re
from typing import Any

from app.design.openings import opening_kind, opening_token, split_opening

from .profile import (
    _DETAIL_COMPONENT_QUOTAS,
    _FACES,
    _OPENING_TYPES,
    _SHAPE_ENUM,
    _default_detail_packages,
    _requested_balcony_access_count,
    _requested_balcony_width,
    _requested_dimension,
    _requested_floors,
    _requested_plan_dimensions,
    _requested_shape,
    coerce_shape_label,
    resolve_complexity_profile,
)


def _note(notes: list[str] | None, message: str) -> None:
    """把一条归一化记账写进调用方的诊断列表（``None`` = 这次调用不需要记账）。

    为什么用出参而不是返回值：`normalize_architecture_plan` 是链上复用最广的纯函数
    （6 处生产调用点），改返回类型会波及所有调用方；用 keyword-only 出参只影响关心
    记账的那一处 —— 保留字段来源与变化证据。
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
) -> list[dict[str, Any]]:
    modeled_floors = int(massing["modeled_floors"])
    if not isinstance(raw, list):
        raise ValueError("/volumes：必须提供建筑体量数组，不能使用默认体量代替设计")

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
        try:
            volumes.append(VolumeDecision.model_validate(item).model_dump(mode="json"))
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


def _normalize_structural_grid(raw: object) -> dict[str, Any]:
    from app.design.contracts import StructuralGridDecision

    return StructuralGridDecision.model_validate(raw).model_dump(mode="json")


def normalize_architecture_plan(
    raw: object,
    user_message: str = "",
    complexity_profile: dict[str, Any] | None = None,
    *,
    normalize_notes: list[str] | None = None,
    normalization_changes: list[dict] | None = None,
    input_source: str = "unknown",
) -> dict[str, Any]:
    """校验建筑方案并记录归一化变化，关键设计字段必须由调用方提供。

    ``normalize_notes`` 是可选出参：把归一化过程中"用户覆盖了模型""模型写了表外值"
    这类取舍保留为兼容文本。``normalization_changes`` 返回字段级来源和变更，
    由调用方写入既有诊断与设计 rule_trace，不参与后续几何计算。
    """
    if not isinstance(raw, dict):
        raise ValueError("建筑方案必须是完整 JSON 对象，不能使用默认建筑代替")
    source = raw
    complexity = deepcopy(complexity_profile or source.get("complexity") or resolve_complexity_profile())
    profile_id = str(source.get("profile") or "custom")
    requested_required = source.get("required_components")
    explicit_base = list(requested_required) if isinstance(requested_required, list) else None
    curtain_wall = bool(source.get("curtain_wall"))
    massing_raw = source.get("massing")
    if not isinstance(massing_raw, dict):
        raise ValueError("/massing：必须提供建筑总体设计，不能使用默认尺寸或楼层")
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
    model_shape = coerce_shape_label(massing_raw.get("shape"))
    resolved_shape = requested_shape or model_shape
    if requested_shape and model_shape and requested_shape != model_shape:
        # 覆盖必须记账：这条链上"谁把 U 形改成了矩形"以前是查不出来的
        # （正则无声、模型无声、兜底无声）。
        _note(
            normalize_notes,
            f"massing.shape：用户显式形状词 {requested_shape} 覆盖模型值 {model_shape}",
        )
    from app.design.contracts import MassingDecision

    massing = {**massing_raw, "shape": resolved_shape}
    for key, requested in (("width", requested_width), ("depth", requested_depth), ("floors", requested_floors)):
        if requested is not None:
            massing[key] = requested
    massing.setdefault("modeled_floors", massing.get("floors"))
    massing["representation_mode"] = (
        "full" if massing.get("modeled_floors") == massing.get("floors") else "schematic"
    )
    massing = MassingDecision.model_validate(massing).model_dump(mode="json", exclude_none=True)
    if massing["shape"] not in _SHAPE_ENUM:
        _note(normalize_notes, f"massing.shape：{massing['shape']!r} 不在形状枚举内，按仅标签语义保留")
    modeled_floors = int(massing["modeled_floors"])
    volumes = _normalize_volumes(source.get("volumes"), massing)
    structural_grid = _normalize_structural_grid(source.get("structural_grid"))
    raw_detail_packages = source.get("detail_packages")
    allowed_detail_packages = set(_DETAIL_COMPONENT_QUOTAS)
    # 用户点名的细部包是本次方案的硬需求：`_default_detail_packages` 只由显式关键词
    # 产生（不含默认套餐），所以"模型没写"就是"用户没要"，反过来"用户要了"就必须留下。
    # 模型可以补充，但**不能删除**——实测"生成一个别墅，里面要有家具"会被规划模型以
    # 「家具属于室内设计，不在建筑方案职责内」为由把 detail_packages 写成 `[]`，
    # 照单全收后配额与 required_components 一起消失，最终表现成"要了却一件都没生成"。
    requested_detail_packages = [
        str(item).lower() for item in _default_detail_packages(user_message, modeled_floors)
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
    detail_packages = detail_packages[:20]

    facade_source = source.get("facades") if isinstance(source.get("facades"), dict) else {}
    facades: dict[str, dict[str, Any]] = {}
    from app.design.contracts import FacadeDecision

    for face in _FACES:
        item = facade_source.get(face)
        required = ("bays", "ground_pattern", "upper_pattern")
        if not isinstance(item, dict) or any(key not in item for key in required):
            raise ValueError(f"/facades/{face}：必须提供 bays、ground_pattern 和 upper_pattern，不能使用默认门窗分格")
        if not all(isinstance(item[key], list) for key in ("ground_pattern", "upper_pattern")):
            raise ValueError(f"/facades/{face}：门窗分格必须是数组")
        bays = int(item["bays"])
        facades[face] = FacadeDecision.model_validate({
            **item,
            "ground_pattern": _normalize_pattern(item["ground_pattern"], bays, []),
            "upper_pattern": _normalize_pattern(item["upper_pattern"], bays, [], allowed_types=_OPENING_TYPES - {"door"}),
        }).model_dump(mode="json", exclude_none=True)

    roof_input = source.get("roof")
    # A single-item wrapper can be migrated without inventing a different roof.
    if isinstance(roof_input, list) and len(roof_input) == 1 and isinstance(roof_input[0], dict):
        roof_input = roof_input[0]
    from app.design.contracts import RoofDecision

    roof = RoofDecision.model_validate(roof_input).model_dump(mode="json", exclude_none=True)
    roof_type = roof["type"]
    opening_counts = _facade_opening_counts(facades, modeled_floors)
    if explicit_base is not None:
        base_components_effective = list(explicit_base)
    else:
        base_components_effective = [kind for kind, count in opening_counts.items() if count > 0]
        if str(roof_type).lower() not in {"none", "open"}:
            base_components_effective.append("roof")
    entrance_required = opening_counts["door"] > 0
    quotas: dict[str, dict[str, Any]] = {}
    unsupported_component_types: set[str] = set(source.get("unsupported_component_types") or [])
    raw_quotas = source.get("component_quota", {})
    if not isinstance(raw_quotas, dict):
        raise ValueError("component_quota 必须是对象；新图纸不输出配额，数量由程序从构件标记派生")
    for component_type, limits in raw_quotas.items():
        if not isinstance(limits, dict):
            raise ValueError(f"component_quota.{component_type} 必须是包含 min/max 的对象，实际 {limits!r}；"
                             "新图纸不输出配额，数量由程序从构件标记派生")
        component_type = str(component_type)
        # 开放集通道（用户决策 2026-09-29：删除构件白名单闸）：配额点名的任何类型
        # 都放行进入下游——已注册的走既有派生/模型通道，未注册的由 plan 条目用
        # 通用配置尝试（字段契约靠知识库检索），校验与修复环兜底。
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
    if str(roof["type"]).lower() in {"none", "open"} and explicit_base and "roof" in explicit_base:
        raise ValueError("屋顶设计明确为 none/open，却在 required_components 中要求 roof")
    roof_required = "roof" in base_components_effective and str(roof["type"]).lower() not in {"none", "open"}
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

    if "component_quota" not in source:
        instances = source.get("components") or []
        counts = Counter(item["type"] for item in instances if isinstance(item, dict) and item.get("type"))
        for component_type, count in counts.items():
            if component_type not in {"door", "window", "roof"}:
                if component_type == "balcony" and balcony_access_count:
                    continue
                quotas[component_type] = {"min": count, "max": count, "note": "由显式构件标记派生"}

    required = source.get("required_components")
    if not isinstance(required, list):
        required = [
            *base_components_effective,
            *(item["type"] for item in source.get("components") or []
              if isinstance(item, dict) and item.get("type")),
        ]
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
        rationale = []
    
    # §3.4: 保留构件实例清单
    components = source.get("components")
    if not isinstance(components, list):
        components = []
    
    result = {
        "schema_version": "1.0",
        "profile": profile_id,
        "concept": str(source.get("concept") or _concept_from_request(user_message))[:240],
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
        "design_rationale": [str(item) for item in rationale[:12]],
        "design_intent": deepcopy(source.get("design_intent")),
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
    result["design_rationale"] = [decision_summary(result), *rationale[:11]]
    if "design_constraints" in source:
        result["design_constraints"] = deepcopy(source["design_constraints"])
    if "complexity" in source:
        result["complexity"] = deepcopy(source["complexity"])
    return result
