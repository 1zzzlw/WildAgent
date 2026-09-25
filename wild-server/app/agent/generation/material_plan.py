"""材质计划的受控归一化与 Blueprint 应用逻辑。"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from app.agent.generation.materials import infer_brick_preset, resolve_brick_preset
ROLE_SPECS: dict[str, dict[str, Any]] = {
    "facade_primary": {
        "materialId": "wall_finish", "baseColor": [0.84, 0.82, 0.78],
        "roughness": 0.72, "metallic": 0.0,
    },
    "structure": {
        "materialId": "concrete", "baseColor": [0.66, 0.67, 0.68],
        "roughness": 0.76, "metallic": 0.0,
    },
    "floor": {
        "materialId": "floor_finish", "baseColor": [0.52, 0.51, 0.49],
        "roughness": 0.78, "metallic": 0.0,
    },
    "frame": {
        "materialId": "metal", "baseColor": [0.12, 0.13, 0.14],
        "roughness": 0.3, "metallic": 0.8,
    },
    "door": {
        "materialId": "wood", "baseColor": [0.38, 0.22, 0.12],
        "roughness": 0.62, "metallic": 0.0,
    },
    "glass": {
        "materialId": "glass", "baseColor": [0.72, 0.88, 0.96],
        "roughness": 0.08, "metallic": 0.0,
    },
    "roof": {
        "materialId": "roof", "baseColor": [0.27, 0.28, 0.3],
        "roughness": 0.76, "metallic": 0.0,
    },
    "ground": {
        "materialId": "ground", "baseColor": [0.34, 0.38, 0.33],
        "roughness": 0.9, "metallic": 0.0,
    },
    "accent": {
        "materialId": "accent", "baseColor": [0.42, 0.2, 0.09],
        "roughness": 0.5, "metallic": 0.0,
    },
}

ELEMENT_ROLE = {
    "wall": "facade_primary",
    "floor": "floor",
    "stair": "floor",
    "column": "structure",
    "beam": "structure",
    "roof": "roof",
}

#: 物件场景的受控材质角色。**materialId 与
#: `generation/objects/skeleton.py::OBJECT_MATERIALS` 的键逐字一致**——
#: 家具的 `material` 字段引用的是材质名，两边对不上就会出现"引用了一个不存在的材质"。
#:
#: 刻意不含 facade_primary / structure / floor / frame / door / roof / ground：
#: 一张桌子没有外墙与屋顶，为它"补齐"这些角色只会往蓝图里塞一堆用不上的材质，
#: 并让设计审核图纸出现不存在的构件语义。
OBJECT_ROLE_SPECS: dict[str, dict[str, Any]] = {
    "wood": {
        "materialId": "wood", "baseColor": [0.42, 0.26, 0.14],
        "roughness": 0.62, "metallic": 0.0,
    },
    "metal": {
        "materialId": "metal", "baseColor": [0.16, 0.17, 0.18],
        "roughness": 0.32, "metallic": 0.8,
    },
    "glass": {
        "materialId": "glass", "baseColor": [0.72, 0.88, 0.96],
        "roughness": 0.08, "metallic": 0.0,
    },
    "stone": {
        "materialId": "stone", "baseColor": [0.62, 0.60, 0.57],
        "roughness": 0.78, "metallic": 0.0,
    },
    "fabric": {
        "materialId": "fabric", "baseColor": [0.46, 0.44, 0.42],
        "roughness": 0.92, "metallic": 0.0,
    },
    "accent": {
        "materialId": "accent", "baseColor": [0.42, 0.20, 0.09],
        "roughness": 0.50, "metallic": 0.0,
    },
}

#: 角色名里"这一档必须是金属"的集合。`role == "frame"` 是建筑侧的对应写法，
#: 物件侧没有 frame 角色，用 `metal`——两处必须同时生效，否则金属会被
#: 0.15 的通用上限压成塑料。
_METALLIC_ROLES = frozenset({"frame", "metal"})


def material_role_specs(architecture_plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """按方案是物件还是建筑选择受控角色表。

    判定复用 `design.resolver.is_object_plan`：只有一处判据，
    不会出现"这里当物件、那里当建筑"的分叉。
    """

    from app.design.resolver import is_object_plan

    return OBJECT_ROLE_SPECS if is_object_plan(architecture_plan) else ROLE_SPECS

# 骨架生成器会先用这些受控材质 ID 标记构件的“用途”：例如玻璃幕墙壳体
# 是 glass、龙骨是 metal、核心筒是 concrete。材质规划只能替换该用途对应的
# 具体材质参数，不能再仅凭 element.type 把所有 wall/beam 覆盖成同一种材质。
MATERIAL_ID_ROLE = {
    str(spec["materialId"]): role
    for role, spec in ROLE_SPECS.items()
}


def _element_material_role(element: dict[str, Any], *, curtain_wall: bool) -> str | None:
    """解析骨架构件的稳定材质角色，并修复已知的类型级错误覆盖。"""
    element_id = str(element.get("id") or "")
    element_type = str(element.get("type") or "")
    if curtain_wall and element_type == "wall" and "_shell_" in element_id:
        return "glass"
    if element_id.startswith("curtain_mullion_"):
        return "frame"
    if element_type == "wall" and (
        element_id.startswith("wall_core_") or "shaft_wall" in element_id
    ):
        return "structure"
    explicit_role = MATERIAL_ID_ROLE.get(str(element.get("material")))
    return explicit_role or ELEMENT_ROLE.get(element_type)


def compact_asset_catalog(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只把选择材质所需的可信元数据交给模型，不暴露 URL。"""
    catalog: list[dict[str, Any]] = []
    for manifest in manifests:
        asset_id = manifest.get("assetId")
        maps = manifest.get("maps")
        if (
            not isinstance(asset_id, str)
            or manifest.get("kind") != "pbr_texture_set"
            or not isinstance(maps, dict)
            or "baseColor" not in maps
        ):
            continue
        classification = manifest.get("classification") or {}
        channels = sorted(maps)
        catalog.append({
            "assetId": asset_id,
            "kind": "pbr_texture_set",
            "name": str(manifest.get("name") or asset_id),
            "materialClass": classification.get("materialClass", "other"),
            "tags": list(classification.get("tags") or []),
            "recommendedRoles": list(classification.get("recommendedRoles") or []),
            "realWorldSizeMeters": manifest.get("realWorldSizeMeters", [1, 1]),
            "defaults": manifest.get("defaults", {}),
            "channels": channels,
            "baseColorOnly": channels == ["baseColor"],
            "sourceType": (manifest.get("source") or {}).get("type", "unknown"),
            "license": manifest.get("license", ""),
        })
    return catalog[:80]


def resolve_material_plan(
    raw_plan: dict[str, Any] | None,
    manifests: list[dict[str, Any]],
    architecture_plan: dict[str, Any] | None = None,
    user_message: str = "",
    *,
    procedural_materials_enabled: bool = False,
    role_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """把模型意图限制为固定角色、真实 assetId 和物理合理参数。

    ``role_specs`` 缺省按方案自动选择（建筑角色 / 物件角色）。显式传入是为了让
    调用方在"方案本身还没落成文档"时也能定住角色集，避免两处各判一次而分叉。
    """
    specs = role_specs or material_role_specs(architecture_plan)
    by_id = {
        item["assetId"]: item
        for item in manifests
        if isinstance(item, dict) and isinstance(item.get("assetId"), str)
    }
    requested_by_role: dict[str, dict[str, Any]] = {}
    raw_roles = raw_plan.get("roles", []) if isinstance(raw_plan, dict) else []
    if isinstance(raw_roles, list):
        for item in raw_roles:
            if isinstance(item, dict) and item.get("role") in specs:
                requested_by_role[str(item["role"])] = item

    roles: list[dict[str, Any]] = []
    resolved_assets: dict[str, dict[str, Any]] = {}
    rejected_asset_ids: list[str] = []
    rejected_procedural_preset_ids: list[str] = []
    automatic_preset = (
        infer_brick_preset(
            f"{user_message}\n{json.dumps(architecture_plan or {}, ensure_ascii=False)}"
        )
        if procedural_materials_enabled else None
    )
    stable_context = json.dumps(
        {"architecture": architecture_plan or {}, "request": user_message},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for role, fallback in specs.items():
        requested = requested_by_role.get(role, {})
        asset_id = requested.get("assetId")
        asset = by_id.get(asset_id) if isinstance(asset_id, str) else None
        classification = (asset or {}).get("classification") or {}
        recommended_roles = classification.get("recommendedRoles") or []
        if role == "glass" or (asset and recommended_roles and role not in recommended_roles):
            if asset_id:
                rejected_asset_ids.append(str(asset_id))
            asset = None
            asset_id = None
        elif asset_id and asset is None:
            rejected_asset_ids.append(str(asset_id))
            asset_id = None

        preset_id = requested.get("proceduralPresetId") if procedural_materials_enabled else None
        if role == "facade_primary" and not preset_id and not requested.get("procedural"):
            preset_id = automatic_preset
        recipe = None
        if role == "facade_primary" and not asset and preset_id:
            recipe = resolve_brick_preset(
                preset_id,
                requested.get("shaderAdjustments"),
                stable_context=stable_context,
            )
            if recipe is None:
                rejected_procedural_preset_ids.append(str(preset_id))

        defaults = (asset or {}).get("defaults") or {}
        material_class = str(classification.get("materialClass") or "other")
        base_color = _safe_color(
            defaults.get("baseColorTint") if asset else recipe.get("baseColor") if recipe else requested.get("baseColor"),
            [1.0, 1.0, 1.0] if asset else fallback["baseColor"],
        )
        roughness = _unit(
            defaults.get("roughness") if asset else recipe.get("roughness") if recipe else requested.get("roughness"),
            fallback["roughness"],
        )
        metallic = _unit(
            defaults.get("metallic") if asset else requested.get("metallic"),
            fallback["metallic"],
        )
        if material_class == "metal" or role in _METALLIC_ROLES:
            metallic = max(0.5, metallic)
        else:
            metallic = min(0.15, metallic)

        material = {
            "baseColor": base_color,
            "roughness": roughness,
            "metallic": metallic,
            "albedo": 1.0,
            "lightingCondition": "D65_noon",
        }
        if asset:
            material.update({
                "textureSet": asset_id,
                "normalScale": _range(defaults.get("normalScale"), 0, 4, 1),
                "uvScale": _positive_pair(defaults.get("uvScale"), [1, 1]),
            })
            resolved_assets[str(asset_id)] = deepcopy(asset)
        elif role == "facade_primary" and procedural_materials_enabled:
            procedural = recipe.get("procedural") if recipe else _safe_procedural_brick(requested.get("procedural"))
            if procedural:
                material["procedural"] = procedural
        if role == "glass":
            material.update({
                "materialClass": "glass",
                "side": "double",
                "transmission": 0.92,
                "ior": 1.5,
                "thickness": 0.012,
                "attenuationColor": [0.82, 0.94, 1.0],
                "attenuationDistance": 6.0,
                "clearcoat": 0.08,
                "clearcoatRoughness": 0.12,
            })
        roles.append({
            "role": role,
            "materialId": fallback["materialId"],
            "assetId": asset_id,
            "proceduralPresetId": recipe.get("presetId") if recipe else None,
            "material": material,
        })

    concept = str((raw_plan or {}).get("concept") or _fallback_concept(architecture_plan))[:160]
    palette = (raw_plan or {}).get("palette") if isinstance(raw_plan, dict) else []
    if not isinstance(palette, list):
        palette = []
    # 玻璃幕墙：外墙用物理玻璃近似表达（wall + material=glass），而非不透明墙板。
    curtain_wall = "玻璃幕墙" in user_message or "玻璃幕" in user_message
    return {
        "concept": concept,
        "palette": [str(item)[:40] for item in palette[:5]],
        "roles": roles,
        "resolvedAssets": resolved_assets,
        "rejectedAssetIds": sorted(set(rejected_asset_ids)),
        "rejectedProceduralPresetIds": sorted(set(rejected_procedural_preset_ids)),
        "curtainWall": curtain_wall,
    }


def apply_resolved_material_plan(
    blueprint: dict,
    material_plan: dict | None,
    *,
    role_specs: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """按骨架已有的语义材质角色写入方案，模型无法绕过资产白名单。

    ``role_specs`` 必须与产出该方案的 `resolve_material_plan` 用同一份角色表，
    否则物件场景的 wood/metal/glass 角色会被建筑角色白名单挡掉，
    结果是"材质方案批了却没写进蓝图"。
    """
    if not isinstance(material_plan, dict):
        return blueprint
    specs = role_specs or ROLE_SPECS
    materials = blueprint.setdefault("materials", {})
    if not isinstance(materials, dict):
        materials = {}
        blueprint["materials"] = materials
    role_material_ids: dict[str, str] = {}
    for item in material_plan.get("roles", []):
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        material_id = item.get("materialId")
        material = item.get("material")
        if role in specs and isinstance(material_id, str) and isinstance(material, dict):
            materials[material_id] = deepcopy(material)
            role_material_ids[str(role)] = material_id

    for element in blueprint.get("geometry", {}).get("elements", []):
        if not isinstance(element, dict):
            continue
        # 稳定语义 ID 可修复旧版本留下的错误覆盖；其他构件优先采用骨架明确
        # 写出的受控材质角色，最后才按元素类型使用旧版默认角色。
        role = _element_material_role(
            element,
            curtain_wall=material_plan.get("curtainWall") is True,
        )
        if role and role in role_material_ids:
            element["material"] = role_material_ids[role]

    resolved_assets = material_plan.get("resolvedAssets") or {}
    blueprint["assets"] = deepcopy(resolved_assets) if isinstance(resolved_assets, dict) else {}
    return blueprint

def _safe_color(value: Any, fallback: list[float]) -> list[float]:
    if (
        isinstance(value, list) and len(value) == 3
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    ):
        return [round(min(1.0, max(0.0, float(item))), 4) for item in value]
    return list(fallback)


def _unit(value: Any, fallback: float) -> float:
    return _range(value, 0, 1, fallback)


def _range(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return round(min(maximum, max(minimum, number)), 4)


def _positive_pair(value: Any, fallback: list[float]) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            pair = [float(item) for item in value]
        except (TypeError, ValueError):
            return list(fallback)
        if all(0 < item <= 64 for item in pair):
            return [round(item, 4) for item in pair]
    return list(fallback)


def _safe_procedural_brick(value: Any) -> dict[str, Any] | None:
    """只接收声明式红砖参数，丢弃未知字段并归一化到渲染器安全范围。"""
    if not isinstance(value, dict) or value.get("type") != "brick":
        return None

    raw_size = value.get("brickSize")
    if isinstance(raw_size, (list, tuple)) and len(raw_size) == 2:
        brick_size = [
            _range(raw_size[0], 0.04, 2.0, 0.24),
            _range(raw_size[1], 0.02, 1.0, 0.065),
        ]
    else:
        brick_size = [0.24, 0.065]
    max_mortar_width = min(0.03, min(brick_size) / 2 - 0.0001)
    weathering = value.get("weathering")
    if not isinstance(weathering, dict):
        weathering = {}

    return {
        "type": "brick",
        "seed": int(_range(value.get("seed"), 0, 2_147_483_647, 1)),
        "brickSize": brick_size,
        "mortarWidth": _range(value.get("mortarWidth"), 0.002, max_mortar_width, 0.01),
        "mortarDepth": _range(value.get("mortarDepth"), 0, 0.02, 0.006),
        "bond": value.get("bond") if value.get("bond") in {"running", "stack"} else "running",
        "secondaryColor": _safe_color(value.get("secondaryColor"), [0.68, 0.19, 0.08]),
        "colorVariation": _unit(value.get("colorVariation"), 0.12),
        "roughnessVariation": _unit(value.get("roughnessVariation"), 0.12),
        "edgeWear": _unit(value.get("edgeWear"), 0.05),
        "weathering": {
            "amount": _unit(weathering.get("amount"), 0),
            "scale": _range(weathering.get("scale"), 0.1, 100, 1.8),
            "efflorescence": _unit(weathering.get("efflorescence"), 0),
            "verticalStreaks": _unit(weathering.get("verticalStreaks"), 0),
            "baseDampness": _unit(weathering.get("baseDampness"), 0),
        },
    }


def _fallback_concept(architecture_plan: dict[str, Any] | None) -> str:
    source = json.dumps(architecture_plan or {}, ensure_ascii=False).lower()
    if any(term in source for term in ("chinese", "中式", "传统")):
        return "温润木色与低饱和矿物色形成克制的传统材质层级"
    if any(term in source for term in ("modern", "现代")):
        return "浅色主体、深色金属框和通透玻璃构成清晰的现代材质层级"
    return "耐久中性主材搭配少量深色框架与自然色点缀"
