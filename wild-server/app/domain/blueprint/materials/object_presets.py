"""物件生成链与静态物品目录共用的材质角色。"""

from __future__ import annotations

from typing import Any


OBJECT_MATERIALS: dict[str, dict[str, Any]] = {
    "wood": {
        "baseColor": [0.42, 0.26, 0.14],
        "roughness": 0.62,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
    "metal": {
        "baseColor": [0.16, 0.17, 0.18],
        "roughness": 0.32,
        "metallic": 0.8,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
    "glass": {
        "baseColor": [0.72, 0.88, 0.96],
        "roughness": 0.08,
        "metallic": 0.0,
        "albedo": 1.0,
        "materialClass": "glass",
        "transmission": 0.92,
        "ior": 1.5,
        "thickness": 0.012,
        "lightingCondition": "D65_noon",
    },
    "stone": {
        "baseColor": [0.62, 0.60, 0.57],
        "roughness": 0.78,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
    "fabric": {
        "baseColor": [0.46, 0.44, 0.42],
        "roughness": 0.92,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
    "accent": {
        "baseColor": [0.42, 0.20, 0.09],
        "roughness": 0.50,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
}


__all__ = ["OBJECT_MATERIALS"]
