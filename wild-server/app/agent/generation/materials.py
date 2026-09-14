"""受控程序化材质配方：模型选择语义，代码生成稳定 Shader 参数。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


BRICK_RECIPES: dict[str, dict[str, Any]] = {
    "brick_new_red": {
        "name": "新红砖",
        "description": "颜色整齐、轻微烧制色差，无明显老化",
        "tags": ["brick", "clean", "new", "warm_red"],
        "ranges": {
            "baseColor": ([0.50, 0.105, 0.045], [0.58, 0.15, 0.07]),
            "roughness": (0.80, 0.88),
            "brickWidth": (0.225, 0.255),
            "brickHeight": (0.06, 0.07),
            "mortarWidth": (0.008, 0.012),
            "mortarDepth": (0.0045, 0.0065),
            "secondaryColor": ([0.62, 0.16, 0.06], [0.72, 0.23, 0.095]),
            "colorVariation": (0.07, 0.12),
            "roughnessVariation": (0.07, 0.12),
            "edgeWear": (0.01, 0.035),
            "weathering": (0.015, 0.07),
            "weatherScale": (1.6, 2.15),
            "efflorescence": (0, 0.03),
            "verticalStreaks": (0, 0.035),
            "baseDampness": (0, 0.025),
        },
    },
    "brick_aged_red": {
        "name": "自然旧红砖",
        "description": "连续风化、少量雨痕和边缘磨损",
        "tags": ["brick", "aged", "weathered", "warm_red"],
        "ranges": {
            "baseColor": ([0.47, 0.09, 0.042], [0.56, 0.135, 0.065]),
            "roughness": (0.81, 0.9),
            "brickWidth": (0.22, 0.26),
            "brickHeight": (0.058, 0.072),
            "mortarWidth": (0.008, 0.013),
            "mortarDepth": (0.005, 0.008),
            "secondaryColor": ([0.59, 0.14, 0.055], [0.72, 0.22, 0.095]),
            "colorVariation": (0.11, 0.18),
            "roughnessVariation": (0.13, 0.2),
            "edgeWear": (0.04, 0.085),
            "weathering": (0.22, 0.34),
            "weatherScale": (1.45, 2.1),
            "efflorescence": (0.05, 0.15),
            "verticalStreaks": (0.09, 0.19),
            "baseDampness": (0.04, 0.12),
        },
    },
    "brick_salt_weathered": {
        "name": "潮湿盐碱红砖",
        "description": "墙脚潮湿、盐碱泛白和竖向流痕",
        "tags": ["brick", "damp", "efflorescence", "weathered"],
        "ranges": {
            "baseColor": ([0.41, 0.078, 0.035], [0.5, 0.115, 0.055]),
            "roughness": (0.83, 0.93),
            "brickWidth": (0.22, 0.255),
            "brickHeight": (0.058, 0.07),
            "mortarWidth": (0.009, 0.014),
            "mortarDepth": (0.005, 0.009),
            "secondaryColor": ([0.55, 0.125, 0.05], [0.67, 0.19, 0.08]),
            "colorVariation": (0.13, 0.2),
            "roughnessVariation": (0.16, 0.23),
            "edgeWear": (0.06, 0.1),
            "weathering": (0.4, 0.55),
            "weatherScale": (1.15, 1.6),
            "efflorescence": (0.36, 0.55),
            "verticalStreaks": (0.18, 0.3),
            "baseDampness": (0.26, 0.4),
        },
    },
}

_LEVELS: dict[str, dict[str, float]] = {
    "colorVariation": {"none": 0, "subtle": 0.08, "moderate": 0.14, "strong": 0.22},
    "roughnessVariation": {"none": 0, "subtle": 0.08, "moderate": 0.16, "strong": 0.24},
    "edgeWear": {"none": 0, "subtle": 0.025, "moderate": 0.06, "strong": 0.1},
    "weathering": {"none": 0, "subtle": 0.12, "moderate": 0.28, "strong": 0.48},
    "efflorescence": {"none": 0, "subtle": 0.1, "moderate": 0.24, "strong": 0.46},
    "verticalStreaks": {"none": 0, "subtle": 0.08, "moderate": 0.16, "strong": 0.28},
    "baseDampness": {"none": 0, "subtle": 0.08, "moderate": 0.2, "strong": 0.34},
}
_MORTAR_DEPTH = {"shallow": 0.003, "standard": 0.006, "deep": 0.009}


def compact_procedural_catalog() -> list[dict[str, Any]]:
    """返回只包含模型选择所需信息的内置配方目录。"""
    return [
        {
            "presetId": preset_id,
            "type": "brick",
            "name": preset["name"],
            "description": preset["description"],
            "tags": list(preset["tags"]),
            "recommendedRoles": ["facade_primary"],
            "adjustments": [
                "tone", "mortarDepth", "colorVariation", "roughnessVariation",
                "edgeWear", "weathering", "efflorescence", "verticalStreaks",
                "baseDampness", "cleanliness",
            ],
        }
        for preset_id, preset in BRICK_RECIPES.items()
    ]


def resolve_brick_preset(
    preset_id: Any,
    adjustments: Any = None,
    *,
    stable_context: str = "",
) -> dict[str, Any] | None:
    """把预设和有限语义覆盖转换为完整、稳定的红砖材质参数。"""
    if preset_id not in BRICK_RECIPES:
        return None
    preset = _sample_brick_recipe(
        BRICK_RECIPES[str(preset_id)],
        stable_context,
        str(preset_id),
    )
    procedural = preset["procedural"]
    weathering = procedural["weathering"]
    values = adjustments if isinstance(adjustments, dict) else {}

    for field in ("colorVariation", "roughnessVariation", "edgeWear"):
        mapped = _level_value(field, values.get(field))
        if mapped is not None:
            procedural[field] = mapped
    for field in ("weathering", "efflorescence", "verticalStreaks", "baseDampness"):
        mapped = _level_value(field, values.get(field))
        if mapped is None:
            continue
        target = "amount" if field == "weathering" else field
        weathering[target] = mapped
    if values.get("weathering") == "none":
        for field in ("efflorescence", "verticalStreaks", "baseDampness"):
            if field not in values:
                weathering[field] = 0

    mortar_depth = _MORTAR_DEPTH.get(str(values.get("mortarDepth") or ""))
    if mortar_depth is not None:
        procedural["mortarDepth"] = mortar_depth
    _apply_tone(preset, values.get("tone"))

    if values.get("cleanliness") == "clean":
        weathering["amount"] = min(weathering["amount"], 0.12)
        weathering["efflorescence"] = min(weathering["efflorescence"], 0.1)
        weathering["verticalStreaks"] = min(weathering["verticalStreaks"], 0.08)
        weathering["baseDampness"] = min(weathering["baseDampness"], 0.08)
    if any(weathering[field] > 0 for field in ("efflorescence", "verticalStreaks", "baseDampness")):
        weathering["amount"] = max(weathering["amount"], 0.12)

    procedural["seed"] = _stable_seed(stable_context, str(preset_id))
    return {
        "baseColor": preset["baseColor"],
        "roughness": preset["roughness"],
        "procedural": procedural,
        "presetId": str(preset_id),
    }


def infer_brick_preset(text: str) -> str | None:
    """模型不可用时，仅对明确出现的砖材语义做确定性回退。"""
    normalized = str(text or "").lower()
    if not any(term in normalized for term in ("红砖", "砖墙", "砖砌", "brick")):
        return None
    if any(term in normalized for term in ("盐碱", "返碱", "泛白", "潮湿", "受潮", "damp", "efflorescence")):
        return "brick_salt_weathered"
    if any(term in normalized for term in ("旧", "老", "风化", "年代感", "aged", "weathered")):
        return "brick_aged_red"
    return "brick_new_red"


def without_procedural_materials(blueprint: dict[str, Any]) -> dict[str, Any]:
    """返回移除程序化材质字段的 Blueprint 副本，用于服务端最终兜底。"""
    result = deepcopy(blueprint)
    materials = result.get("materials")
    if not isinstance(materials, dict):
        return result
    for material in materials.values():
        if isinstance(material, dict):
            material.pop("procedural", None)
    return result


def _level_value(field: str, value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    return _LEVELS[field].get(value)


def _sample_brick_recipe(
    recipe: dict[str, Any],
    stable_context: str,
    recipe_id: str,
) -> dict[str, Any]:
    ranges = recipe["ranges"]
    sample = lambda field: _sample_range(
        ranges[field],
        stable_context,
        recipe_id,
        field,
    )
    return {
        "baseColor": sample("baseColor"),
        "roughness": sample("roughness"),
        "procedural": {
            "type": "brick",
            "brickSize": [sample("brickWidth"), sample("brickHeight")],
            "mortarWidth": sample("mortarWidth"),
            "mortarDepth": sample("mortarDepth"),
            "bond": "running",
            "secondaryColor": sample("secondaryColor"),
            "colorVariation": sample("colorVariation"),
            "roughnessVariation": sample("roughnessVariation"),
            "edgeWear": sample("edgeWear"),
            "weathering": {
                "amount": sample("weathering"),
                "scale": sample("weatherScale"),
                "efflorescence": sample("efflorescence"),
                "verticalStreaks": sample("verticalStreaks"),
                "baseDampness": sample("baseDampness"),
            },
        },
    }


def _sample_range(
    bounds: tuple[Any, Any],
    stable_context: str,
    recipe_id: str,
    field: str,
) -> Any:
    low, high = bounds
    ratio = _stable_fraction(stable_context, recipe_id, field)
    if isinstance(low, list) and isinstance(high, list):
        return [
            round(float(start) + (float(end) - float(start)) * ratio, 4)
            for start, end in zip(low, high, strict=True)
        ]
    return round(float(low) + (float(high) - float(low)) * ratio, 4)


def _stable_fraction(context: str, recipe_id: str, field: str) -> float:
    payload = json.dumps(
        [context, recipe_id, field],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _apply_tone(preset: dict[str, Any], value: Any) -> None:
    color = preset["baseColor"]
    secondary = preset["procedural"]["secondaryColor"]
    if value == "dark":
        preset["baseColor"] = [round(channel * 0.84, 4) for channel in color]
        preset["procedural"]["secondaryColor"] = [round(channel * 0.88, 4) for channel in secondary]
    elif value == "light":
        preset["baseColor"] = [round(min(1, channel * 1.12), 4) for channel in color]
        preset["procedural"]["secondaryColor"] = [round(min(1, channel * 1.08), 4) for channel in secondary]
    elif value == "warm":
        preset["baseColor"] = [round(min(1, color[0] * 1.06), 4), color[1], round(color[2] * 0.92, 4)]


def _stable_seed(context: str, preset_id: str) -> int:
    payload = json.dumps([context, preset_id], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 2_147_483_647
