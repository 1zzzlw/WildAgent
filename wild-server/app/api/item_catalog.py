"""物品目录 API：列出、读取、导入 WILD 物品。

物品就是一份 `.wild` asset 文件（`meta.type = "asset"`）。这里**不定义任何新几何
类型、不新增引擎能力** —— 导入 = 严格校验 + 落盘 + 进目录。这就是"新增物品不必改
渲染引擎"的落点：引擎只认 12 种基础元素，物品是数据。

两个写者分开：

- `storage/item_catalog/manifest.json` + `items/` 由
  `scripts/item_catalog/build.py` 生成（内置物品）；
- `storage/item_catalog/imported/` 由本模块写（用户导入）。

同一个 manifest 被两处写迟早冲突，所以物理分开、读取时合并。
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from threading import Lock
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.item_catalog_validation import inspect_item_asset

router = APIRouter(prefix="/api/item-catalog", tags=["物品库"])

ITEM_ROOT = Path(__file__).resolve().parents[2] / "storage" / "item_catalog"
ITEMS_DIR = ITEM_ROOT / "items"
BUILTIN_MANIFEST = ITEM_ROOT / "manifest.json"
IMPORTED_DIR = ITEM_ROOT / "imported"
IMPORTED_MANIFEST = IMPORTED_DIR / "manifest.json"

#: 导入文件大小上限。物品是手写几何，正常在几十 KB；上限只是防误传整栋楼。
MAX_IMPORT_BYTES = 4 * 1024 * 1024
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_IMPORT_LOCK = Lock()


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _builtin_entries() -> list[dict]:
    manifest = _read_json(BUILTIN_MANIFEST, {})
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if not isinstance(items, list):
        return []
    return [
        {**entry, "source": "builtin"} for entry in items if isinstance(entry, dict)
    ]


def _imported_entries() -> list[dict]:
    manifest = _read_json(IMPORTED_MANIFEST, {})
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if not isinstance(items, list):
        return []
    return [
        {**entry, "source": "imported"} for entry in items if isinstance(entry, dict)
    ]


def _all_entries() -> list[dict]:
    merged = {entry["id"]: entry for entry in _builtin_entries() if entry.get("id")}
    for entry in _imported_entries():
        if entry.get("id") and entry["id"] not in merged:
            merged[entry["id"]] = entry
    return [merged[key] for key in sorted(merged)]


@router.get("")
async def list_items() -> dict:
    """目录索引。`footprint` 是 [宽, 高, 深]（米），来自生成时的几何实测。"""

    entries = _all_entries()
    by_category: dict[str, int] = {}
    for entry in entries:
        category = str(entry.get("category") or "other")
        by_category[category] = by_category.get(category, 0) + 1
    return {"count": len(entries), "categories": by_category, "items": entries}


@router.get("/{item_id}")
async def get_item(item_id: str) -> dict:
    """返回物品的完整 WILD 蓝图（前端放置时直接取这份 parts）。"""

    if not _SAFE_ID.match(item_id):
        raise HTTPException(status_code=400, detail="物品 id 不合法")
    for root in (ITEMS_DIR, IMPORTED_DIR):
        path = root / f"{item_id}.wild"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise HTTPException(
                    status_code=500, detail=f"物品文件损坏: {error}"
                ) from error
    raise HTTPException(status_code=404, detail=f"没有物品 {item_id}")


@router.delete("/{item_id}")
async def delete_item(item_id: str) -> dict:
    """删除用户导入的物品；内置目录始终只读。"""

    if not _SAFE_ID.match(item_id):
        raise HTTPException(status_code=400, detail="物品 id 不合法")
    path = IMPORTED_DIR / f"{item_id}.wild"
    with _IMPORT_LOCK:
        if not path.is_file():
            raise HTTPException(status_code=404, detail="只能删除用户导入的物品")
        manifest = _read_json(IMPORTED_MANIFEST, {"version": "1.0", "items": []})
        entries = manifest.get("items") if isinstance(manifest, dict) else []
        entries = [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("id") != item_id
        ]
        _write_json_atomic(IMPORTED_MANIFEST, {"version": "1.0", "items": entries})
        path.unlink()
    return {"ok": True, "id": item_id}


def _slugify(text: str) -> str:
    """把名称压成合法 id：只留 ASCII 小写与下划线。

    中文名在这里会被清空，此时退回 `item_<序号>` —— 不拿哈希，
    因为人要在 URL 里读得懂。
    """

    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")
    if slug:
        return slug[:48]
    existing = (
        {path.stem for path in IMPORTED_DIR.glob("*.wild")}
        if IMPORTED_DIR.is_dir()
        else set()
    )
    index = 1
    while f"item_{index}" in existing:
        index += 1
    return f"item_{index}"


def _unique_item_id(requested: str) -> str:
    """避免用户导入静默覆盖内置资产或已有导入。"""

    used = {entry.get("id") for entry in _all_entries()}
    if IMPORTED_DIR.is_dir():
        used.update(path.stem for path in IMPORTED_DIR.glob("*.wild"))
    if requested not in used:
        return requested
    index = 2
    while f"{requested}_{index}" in used:
        index += 1
    return f"{requested}_{index}"


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@router.post("/import")
async def import_item(file: Annotated[UploadFile, File()]) -> dict:
    """导入一份 `.wild` 物品；不完整或会被编辑器静默丢字段的文件直接拒绝。"""

    if Path(file.filename or "").suffix.lower() != ".wild":
        raise HTTPException(status_code=422, detail="请选择 .wild 物品文件")

    payload = await file.read(MAX_IMPORT_BYTES + 1)
    if len(payload) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 4 MB")
    try:
        blueprint = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=422, detail=f"不是合法 JSON：{error}"
        ) from error

    meta = blueprint.get("meta") if isinstance(blueprint, dict) else None
    name = (
        str((meta or {}).get("name") or "").strip()
        or Path(file.filename or "item").stem
    )
    geometry = blueprint.get("geometry") if isinstance(blueprint, dict) else None
    elements = geometry.get("elements") if isinstance(geometry, dict) else None

    requested = str((meta or {}).get("id") or "").strip().lower()
    issues = inspect_item_asset(blueprint)
    if issues:
        raise HTTPException(
            status_code=422,
            detail={"message": "物品校验失败，未写入目录", "issues": issues[:20]},
        )

    with _IMPORT_LOCK:
        item_id = _unique_item_id(
            requested if _SAFE_ID.match(requested) else _slugify(name)
        )
        IMPORTED_DIR.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(IMPORTED_DIR / f"{item_id}.wild", blueprint)

        footprint = _measure(elements if isinstance(elements, list) else [])
        entry = {
            "id": item_id,
            "name": name,
            "category": str((meta or {}).get("category") or "imported"),
            "tags": [str(tag) for tag in ((meta or {}).get("tags") or [])][:12],
            "footprint": footprint,
            "parts": len(elements) if isinstance(elements, list) else 0,
            "file": f"imported/{item_id}.wild",
            "needsReview": False,
        }

        manifest = _read_json(IMPORTED_MANIFEST, {"version": "1.0", "items": []})
        entries = (
            manifest.get("items") if isinstance(manifest.get("items"), list) else []
        )
        entries = [
            item
            for item in entries
            if isinstance(item, dict) and item.get("id") != item_id
        ]
        entries.append(entry)
        manifest = {
            "version": "1.0",
            "items": sorted(entries, key=lambda item: str(item.get("id"))),
        }
        _write_json_atomic(IMPORTED_MANIFEST, manifest)

    return {"item": entry, "ok": True}


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
