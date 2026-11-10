"""把零件表组装成一份**可直接编译的 `.wild` asset 蓝图**。

设计约束（重要）：

1. 物品就是一个 WILD 文件，不是一个新元素类型。`meta.type = "asset"`，
   引擎与编辑器都按普通蓝图对待它 —— 这样"新增物品"永远不会碰引擎代码。
2. 材质表**不在这里定义**，直接从轻量共享模块的 `OBJECT_MATERIALS` 取。
   同一份调色板若在两个地方各写一遍，迟早分叉；这里宁可 import 失败。
3. 目录元数据（分类/tags/footprint/缩略图）**不写进蓝图**，放 manifest。
   蓝图保持严格合法，才能被外部原样导入。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WILD_SERVER = REPO_ROOT / "wild-server"
if str(WILD_SERVER) not in sys.path:
    sys.path.insert(0, str(WILD_SERVER))

from app.shared.object_materials import OBJECT_MATERIALS  # noqa: E402

#: 物品可用的语义材质角色。故意只暴露这份受控表的键，避免物品里出现
#: 骨架没有定义、渲染时静默退化成灰的材质名。
MATERIAL_ROLES: tuple[str, ...] = tuple(OBJECT_MATERIALS)

#: 物品库**增量**补充的材质角色。
#:
#: 只增不改：基底永远是 `OBJECT_MATERIALS`（`setdefault` 语义），所以这里不会
#: 和物件链的调色板分叉。加这三个是因为受控六色里没有"植物绿"和"屏幕黑"，
#: 硬用 `accent` 会把树画成棕色、把电视画成木板 —— 那不是风格差异，是错的。
EXTRA_MATERIALS: dict[str, dict] = {
    "foliage": {
        "baseColor": [0.20, 0.34, 0.16],
        "roughness": 0.86,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
    "screen": {
        "baseColor": [0.045, 0.048, 0.055],
        "roughness": 0.16,
        "metallic": 0.0,
        "albedo": 1.0,
        "emissive": [0.02, 0.025, 0.03],
        "emissiveIntensity": 1.0,
        "lightingCondition": "D65_noon",
    },
    "porcelain": {
        "baseColor": [0.90, 0.90, 0.88],
        "roughness": 0.18,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    },
}

ITEMS_DIR = WILD_SERVER / "storage" / "item_catalog" / "items"
MANIFEST_PATH = WILD_SERVER / "storage" / "item_catalog" / "manifest.json"


def material_table(extra: dict[str, dict] | None = None) -> dict[str, dict]:
    table = {key: dict(value) for key, value in OBJECT_MATERIALS.items()}
    for name, definition in EXTRA_MATERIALS.items():
        table.setdefault(name, dict(definition))
    if extra:
        for name, definition in extra.items():
            table.setdefault(name, dict(definition))
    return table


def asset_blueprint(name: str, parts: list[dict], extra_materials: dict[str, dict] | None = None) -> dict:
    """组装 asset 蓝图。`parts` 的坐标已是物品局部坐标（底面中心为原点）。"""

    if not parts:
        raise ValueError(f"物品 {name!r} 没有任何零件")
    seen: set[str] = set()
    for part in parts:
        identifier = str(part.get("id") or "")
        if not identifier:
            raise ValueError(f"物品 {name!r} 有零件缺少 id")
        if identifier in seen:
            raise ValueError(f"物品 {name!r} 零件 id 重复: {identifier}")
        seen.add(identifier)
    return {
        "meta": {"version": "1.0", "type": "asset", "name": name},
        "geometry": {"elements": parts},
        "materials": material_table(extra_materials),
        "behaviors": {},
    }
