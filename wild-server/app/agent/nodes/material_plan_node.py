"""生成分支的材质规划节点：AI 负责审美，解析器负责资产与物理约束。"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any

from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.model_client import create_llm
from app.agent.llm_invocation import invoke_llm
from app.agent.procedural_material_recipes import (
    compact_procedural_catalog,
    infer_brick_preset,
    resolve_brick_preset,
)
from app.agent.prompts import build_material_plan_prompt
from app.agent.runtime_context import get_reasoning_callback
from app.services.asset_storage import asset_storage
from app.utils.json_extractor import extract_json_object


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
) -> dict[str, Any]:
    """把模型意图限制为固定角色、真实 assetId 和物理合理参数。"""
    by_id = {
        item["assetId"]: item
        for item in manifests
        if isinstance(item, dict) and isinstance(item.get("assetId"), str)
    }
    requested_by_role: dict[str, dict[str, Any]] = {}
    raw_roles = raw_plan.get("roles", []) if isinstance(raw_plan, dict) else []
    if isinstance(raw_roles, list):
        for item in raw_roles:
            if isinstance(item, dict) and item.get("role") in ROLE_SPECS:
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
    for role, fallback in ROLE_SPECS.items():
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
        if material_class == "metal" or role == "frame":
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


def apply_resolved_material_plan(blueprint: dict, material_plan: dict | None) -> dict:
    """将已解析方案确定性写入骨架，模型无法绕过资产白名单。"""
    if not isinstance(material_plan, dict):
        return blueprint
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
        if role in ROLE_SPECS and isinstance(material_id, str) and isinstance(material, dict):
            materials[material_id] = deepcopy(material)
            role_material_ids[str(role)] = material_id

    for element in blueprint.get("geometry", {}).get("elements", []):
        if not isinstance(element, dict):
            continue
        role = ELEMENT_ROLE.get(str(element.get("type")))
        if role and role in role_material_ids:
            element["material"] = role_material_ids[role]

    # 玻璃幕墙（方案 A：wall + window）：外墙宿主保持上面的 facade_primary 不透明中性墙板，
    # 玻璃与竖梃/横梃由窗构件的 glassMaterial/frameMaterial + mullions 表达。
    # 既不把整片外墙设成 glass（会变「纯玻璃墙」），也不设成深色金属（会变「纯黑」）。
    # 因此这里刻意不对 wall 材质做任何额外改写。

    resolved_assets = material_plan.get("resolvedAssets") or {}
    blueprint["assets"] = deepcopy(resolved_assets) if isinstance(resolved_assets, dict) else {}
    return blueprint


async def material_planner(state: GenerationState) -> dict:
    started = time.time()
    architecture_plan = state.get("architecture_plan") or {}
    manifests = asset_storage.list_manifests()
    catalog = compact_asset_catalog(manifests)
    procedural_materials_enabled = state.get("procedural_materials_enabled") is True
    procedural_catalog = compact_procedural_catalog() if procedural_materials_enabled else []
    raw_plan = None
    error = None
    token_usage = None
    skipped_llm = False
    callback = get_reasoning_callback()

    # 确定性优先：没有任何可匹配的 PBR 资产时，LLM 的审美输出会被 ROLE_SPECS
    # 兜底与白名单几乎全部覆盖（只剩概念文案与颜色微调），不值得付出一次串行 LLM
    # 往返。此时直接走 resolve_material_plan(None, ...) 的确定性路径。
    if catalog:
        prompt = build_material_plan_prompt(architecture_plan, catalog, procedural_catalog)
        if callback:
            procedural_detail = "与程序化配方" if procedural_materials_enabled else ""
            await callback(
                "material_plan",
                f"正在根据建筑方案自动丰富材质语言，并匹配 PBR 素材{procedural_detail}...\n",
            )
        try:
            llm_result = await invoke_llm(
                create_llm(enable_thinking=False, streaming=False),
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": state.get("user_message", "")},
                ],
            )
            raw_plan = extract_json_object(llm_result.content)
            token_usage = llm_result.token_usage
        except Exception as exc:
            error = str(exc)
            logger.warning(f"[material_plan] 模型调用失败，使用受控回退材质: {exc}")
    else:
        skipped_llm = True
        logger.info(
            "[material_plan] 无可匹配 PBR 资产，跳过审美 LLM 调用，使用确定性材质方案"
        )

    plan = resolve_material_plan(
        raw_plan,
        manifests,
        architecture_plan,
        str(state.get("user_message") or ""),
        procedural_materials_enabled=procedural_materials_enabled,
    )
    if callback:
        selected = [
            item for item in plan["roles"] if item.get("assetId")
        ]
        procedural_selected = [
            item for item in plan["roles"] if item.get("proceduralPresetId")
        ]
        await callback(
            "material_plan",
            f"材质方案已确定：{plan['concept']}；匹配 {len(selected)} 个 PBR 资产，"
            f"启用 {len(procedural_selected)} 个程序化配方。\n",
        )
    return {
        "material_plan": plan,
        "material_diag": {
            "catalog_count": len(catalog),
            "procedural_catalog_count": len(procedural_catalog),
            "selected_asset_count": len(plan["resolvedAssets"]),
            "selected_procedural_count": sum(
                1 for item in plan["roles"] if item.get("proceduralPresetId")
            ),
            "procedural_materials_enabled": procedural_materials_enabled,
            "rejected_asset_ids": plan["rejectedAssetIds"],
            "rejected_procedural_preset_ids": plan["rejectedProceduralPresetIds"],
            "used_fallback": raw_plan is None,
            "skipped_llm": skipped_llm,
            "error": error,
            "token_usage": token_usage,
            "prompt_chars": len(prompt) if catalog else 0,
            "total_ms": int((time.time() - started) * 1000),
        },
    }


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
