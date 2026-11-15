"""物品目录用例：校验导入内容，调用目录存储。"""
import json
from pathlib import Path
from typing import Any
from app.application.errors import ApplicationError
from app.domain.components.catalog_validation import inspect_item_asset
from app.infrastructure.storage import item_catalog as storage

MAX_IMPORT_BYTES = 4 * 1024 * 1024


async def list_items() -> dict:
    """目录索引。`footprint` 是 [宽, 高, 深]（米），来自生成时的几何实测。"""

    entries = storage.list_entries()
    by_category: dict[str, int] = {}
    for entry in entries:
        category = str(entry.get("category") or "other")
        by_category[category] = by_category.get(category, 0) + 1
    return {"count": len(entries), "categories": by_category, "items": entries}


async def get_item(item_id: str) -> dict:
    try:
        return storage.get_item(item_id)
    except storage.CatalogStorageError as exc:
        raise ApplicationError(exc.code, exc.detail) from exc


async def delete_item(item_id: str) -> dict:
    try:
        return storage.delete_item(item_id)
    except storage.CatalogStorageError as exc:
        raise ApplicationError(exc.code, exc.detail) from exc


def import_item(filename: str, payload: bytes) -> dict:
    """导入一份 `.wild` 物品；不完整或会被编辑器静默丢字段的文件直接拒绝。"""

    if Path(filename or "").suffix.lower() != ".wild":
        raise ApplicationError('invalid_data', "请选择 .wild 物品文件")

    if len(payload) > MAX_IMPORT_BYTES:
        raise ApplicationError('payload_too_large', "文件超过 4 MB")
    try:
        blueprint = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApplicationError('invalid_data', f"不是合法 JSON：{error}") from error

    meta = blueprint.get("meta") if isinstance(blueprint, dict) else None
    name = (
        str((meta or {}).get("name") or "").strip()
        or Path(filename or "item").stem
    )
    geometry = blueprint.get("geometry") if isinstance(blueprint, dict) else None
    elements = geometry.get("elements") if isinstance(geometry, dict) else None

    requested = str((meta or {}).get("id") or "").strip().lower()
    issues = inspect_item_asset(blueprint)
    if issues:
        raise ApplicationError('invalid_data', {"message": "物品校验失败，未写入目录", "issues": issues[:20]})

    return storage.save_imported_item(blueprint, name, requested, _measure(elements if isinstance(elements, list) else []))


def _measure(elements: list[Any]) -> list[float]:
    """粗算包围盒（只覆盖 primitive 的规则形体）。仅用于目录展示。"""

    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for element in elements:
        if not isinstance(element, dict) or element.get("type") != "primitive":
            continue
        center = element.get("position") or [0, 0, 0]
        if len(center) != 3:
            continue
        shape = element.get("shape")
        if shape == "box":
            size = element.get("dimensions") or [0, 0, 0]
            half = [float(value) / 2 for value in size]
        elif shape == "sphere":
            half = [float(element.get("radius") or 0)] * 3
        elif shape == "cylinder":
            radius = float(element.get("radius") or element.get("radiusBottom") or 0)
            half = [radius, float(element.get("height") or 0) / 2, radius]
        else:
            continue
        for axis in range(3):
            low[axis] = min(low[axis], float(center[axis]) - half[axis])
            high[axis] = max(high[axis], float(center[axis]) + half[axis])
    if not all(value != float("inf") for value in low):
        return [0.0, 0.0, 0.0]
    return [round(high[axis] - low[axis], 3) for axis in range(3)]
