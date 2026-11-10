"""物品配方注册表。

每条配方 = 一个物品 = 一份 `.wild` asset 文件。注册的只有"怎么生成零件"，
不涉及引擎、不涉及前端 —— 这是"新增物品不改引擎"的落点。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

#: 与 editor 目录一致的分类键，便于两边对照盘点。
CATEGORIES: tuple[str, ...] = (
    "furniture",
    "appliance",
    "kitchen",
    "bathroom",
    "outdoor",
    "lighting",
    "decor",
)


@dataclass(frozen=True)
class ItemRecipe:
    id: str
    name: str
    category: str
    build: Callable[[], list[dict]]
    tags: tuple[str, ...] = ()
    #: 参考尺寸 (宽, 高, 深)，仅为目录展示；真实尺寸以生成出的几何为准。
    footprint: tuple[float, float, float] | None = None
    #: 对应的 editor 物品 id（人工对照用，不参与产物）。
    source_item: str = ""
    extra_materials: dict[str, dict] = field(default_factory=dict)


REGISTRY: dict[str, ItemRecipe] = {}


def item(
    item_id: str,
    name: str,
    category: str,
    *,
    tags: tuple[str, ...] = (),
    footprint: tuple[float, float, float] | None = None,
    source_item: str = "",
    extra_materials: dict[str, dict] | None = None,
):
    """把一个生成函数登记成物品配方。"""

    if category not in CATEGORIES:
        raise ValueError(f"未知分类 {category!r}，可选: {CATEGORIES}")

    def decorator(build: Callable[[], list[dict]]) -> Callable[[], list[dict]]:
        if item_id in REGISTRY:
            raise ValueError(f"物品 id 重复: {item_id}")
        REGISTRY[item_id] = ItemRecipe(
            id=item_id,
            name=name,
            category=category,
            build=build,
            tags=tuple(tags),
            footprint=footprint,
            source_item=source_item,
            extra_materials=dict(extra_materials or {}),
        )
        return build

    return decorator


def load_all() -> dict[str, ItemRecipe]:
    """导入所有配方模块（副作用注册），返回注册表。"""

    from . import (  # noqa: F401  导入即注册
        appliance,
        bathroom,
        bedding,
        decor,
        electronics,
        kitchen,
        lighting,
        outdoor,
        seating,
        storage,
        tables,
    )

    return REGISTRY
