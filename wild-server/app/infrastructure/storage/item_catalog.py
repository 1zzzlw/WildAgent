"""物品目录文件存储；内置资料只读，用户导入使用独立清单。"""
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
import json
import re
import unicodedata
from common.paths import SERVER_ROOT

ITEM_ROOT = SERVER_ROOT / "storage" / "item_catalog"
ITEMS_DIR = ITEM_ROOT / "items"
BUILTIN_MANIFEST = ITEM_ROOT / "manifest.json"
IMPORTED_DIR = ITEM_ROOT / "imported"
IMPORTED_MANIFEST = IMPORTED_DIR / "manifest.json"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_IMPORT_LOCK = Lock()

class CatalogStorageError(Exception):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)

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

def list_entries() -> list[dict]:
    merged = {entry["id"]: entry for entry in _builtin_entries() if entry.get("id")}
    for entry in _imported_entries():
        if entry.get("id") and entry["id"] not in merged:
            merged[entry["id"]] = entry
    return [merged[key] for key in sorted(merged)]

def get_item(item_id: str) -> dict:
    """返回物品的完整 WILD 蓝图（前端放置时直接取这份 parts）。"""

    if not _SAFE_ID.match(item_id):
        raise CatalogStorageError('invalid_input', "物品 id 不合法")
    for root in (ITEMS_DIR, IMPORTED_DIR):
        path = root / f"{item_id}.wild"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise CatalogStorageError('internal_error', f"物品文件损坏: {error}") from error
    raise CatalogStorageError('not_found', f"没有物品 {item_id}")

def delete_item(item_id: str) -> dict:
    """删除用户导入的物品；内置目录始终只读。"""

    if not _SAFE_ID.match(item_id):
        raise CatalogStorageError('invalid_input', "物品 id 不合法")
    path = IMPORTED_DIR / f"{item_id}.wild"
    with _IMPORT_LOCK:
        if not path.is_file():
            raise CatalogStorageError('not_found', "只能删除用户导入的物品")
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

    used = {entry.get("id") for entry in list_entries()}
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


def save_imported_item(blueprint: dict, name: str, requested: str, footprint: list[float]) -> dict:
    meta = blueprint.get("meta") or {}
    elements = blueprint.get("geometry", {}).get("elements")
    with _IMPORT_LOCK:
        item_id = _unique_item_id(
            requested if _SAFE_ID.match(requested) else _slugify(name)
        )
        IMPORTED_DIR.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(IMPORTED_DIR / f"{item_id}.wild", blueprint)

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
