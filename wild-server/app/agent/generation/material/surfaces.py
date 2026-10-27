"""与 Core/材质面板相同的内置表面配方；不依赖外部纹理资产。"""
from copy import deepcopy
import json
from pathlib import Path

_CATALOG = json.loads((Path(__file__).resolve().parents[4] / "storage/knowledge_base/material-presets.json").read_text(encoding="utf-8"))
SURFACE_PRESETS = {item["id"]: item for item in _CATALOG}
DEFAULT_SURFACE_BY_ROLE = {
    "facade_primary": "plaster_lime", "structure": "concrete_fair",
    "floor": "tiles_limestone", "frame": "metal_brushed", "door": "planks_walnut",
    "glass": "glass_clear", "roof": "concrete_fair", "ground": "tiles_limestone",
    "wood": "planks_oak", "metal": "metal_brushed", "stone": "stone_travertine", "fabric": "fabric_linen",
}


def surface_catalog() -> list[dict]:
    return [{key: value for key, value in item.items() if key != "material"} for item in _CATALOG]


def resolve_surface(preset_id: str | None, role: str) -> dict | None:
    preset = SURFACE_PRESETS.get(preset_id) if isinstance(preset_id, str) else None
    if preset and role in preset["recommendedRoles"]:
        return deepcopy(preset["material"])
    return None
