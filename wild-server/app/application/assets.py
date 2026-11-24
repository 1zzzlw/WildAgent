"""PBR 资产入库与查询。"""

import asyncio
from typing import Any, TypedDict

from app.application.errors import ApplicationError
from app.infrastructure.storage.assets import AssetStorageError, LocalAssetStorage, asset_storage


class _PbrIngestState(TypedDict, total=False):
    request: dict[str, Any]
    maps: dict[str, dict[str, Any]]
    storage: LocalAssetStorage
    intent: dict[str, Any]
    prepared: dict[str, Any]
    asset: dict[str, Any]
    patch: dict[str, Any]
    error: str
    trace: list[dict[str, Any]]


def _extract_material_intent(state: _PbrIngestState) -> dict[str, Any]:
    request = state["request"]
    try:
        roughness = float(request.get("roughness", 0.8))
        metallic = float(request.get("metallic", 0.0))
        base_color_tint = [float(value) for value in request.get("baseColorTint", [1, 1, 1])]
        normal_scale = float(request.get("normalScale", 1.0))
        uv_scale = [float(value) for value in request.get("uvScale", [1, 1])]
        real_world_size = [float(value) for value in request.get("realWorldSizeMeters", [1, 1])]
        if not 0 <= roughness <= 1 or not 0 <= metallic <= 1:
            raise AssetStorageError("roughness/metallic 必须在 0–1 范围")
        if len(base_color_tint) != 3 or any(not 0 <= value <= 1 for value in base_color_tint):
            raise AssetStorageError("baseColorTint 必须是三个 0–1 数字")
        if not 0 <= normal_scale <= 4:
            raise AssetStorageError("normalScale 必须在 0–4 范围")
        if len(uv_scale) != 2 or any(value <= 0 for value in uv_scale):
            raise AssetStorageError("uvScale 必须是两个正数")
        if len(real_world_size) != 2 or any(value <= 0 for value in real_world_size):
            raise AssetStorageError("realWorldSizeMeters 必须是两个正数")
        material_name = str(request.get("materialName") or request.get("name") or "pbr_material").strip()
        if not material_name:
            raise AssetStorageError("materialName 不能为空")
        intent = {
            "name": str(request.get("name", "PBR Material")),
            "materialName": material_name,
            "license": str(request.get("license", "User supplied")),
            "sourceType": str(request.get("sourceType", "local_upload")),
            "sourceUri": request.get("sourceUri"),
            "roughness": roughness,
            "metallic": metallic,
            "baseColorTint": base_color_tint,
            "normalScale": normal_scale,
            "uvScale": uv_scale,
            "realWorldSizeMeters": real_world_size,
            "materialClass": str(request.get("materialClass", "other")),
            "tags": list(request.get("tags") or []),
            "recommendedRoles": list(request.get("recommendedRoles") or []),
            "baseRevision": int(request.get("baseRevision", 1)),
        }
        return {
            "intent": intent,
            "trace": [{"node": "extract_material_intent", "status": "done"}],
        }
    except (TypeError, ValueError, AssetStorageError) as exc:
        return {
            "error": str(exc),
            "trace": [{"node": "extract_material_intent", "status": "error", "detail": str(exc)}],
        }


def _validate_asset(state: _PbrIngestState) -> dict[str, Any]:
    intent = state["intent"]
    storage = state["storage"]
    try:
        prepared = storage.prepare_pbr(
            state["maps"],
            name=intent["name"],
            license_name=intent["license"],
            source_type=intent["sourceType"],
            source_uri=intent.get("sourceUri"),
            material_class=intent["materialClass"],
            tags=intent["tags"],
            recommended_roles=intent["recommendedRoles"],
            real_world_size_meters=intent["realWorldSizeMeters"],
            roughness=intent["roughness"],
            metallic=intent["metallic"],
            base_color_tint=intent["baseColorTint"],
            normal_scale=intent["normalScale"],
            uv_scale=intent["uvScale"],
        )
        return {
            "prepared": prepared,
            "trace": [{
                "node": "validate_asset",
                "status": "done",
                "detail": f"{len(prepared['maps'])} 个纹理通道",
            }],
        }
    except AssetStorageError as exc:
        return {
            "error": str(exc),
            "trace": [{"node": "validate_asset", "status": "error", "detail": str(exc)}],
        }


def _register_asset(state: _PbrIngestState) -> dict[str, Any]:
    storage = state["storage"]
    try:
        asset = storage.register_prepared(state["prepared"])
        return {
            "asset": asset,
            "trace": [{"node": "register_asset", "status": "done", "detail": asset["assetId"]}],
        }
    except (AssetStorageError, OSError, ValueError) as exc:
        return {
            "error": str(exc),
            "trace": [{"node": "register_asset", "status": "error", "detail": str(exc)}],
        }


def _propose_wild_patch(state: _PbrIngestState) -> dict[str, Any]:
    intent = state["intent"]
    asset = state["asset"]
    patch = {
        "type": "scene_patch",
        "patch_id": f"asset_{asset['assetId']}",
        "base_revision": intent["baseRevision"],
        "source": "user",
        "mode": "apply",
        "requires_confirmation": False,
        "summary": f"入库并注册 PBR 材质 {intent['materialName']}",
        "operations": [
            {"op": "upsert_asset", "asset_id": asset["assetId"], "asset": asset},
            {
                "op": "upsert_material",
                "name": intent["materialName"],
                "material": {
                    "baseColor": intent["baseColorTint"],
                    "roughness": intent["roughness"],
                    "metallic": intent["metallic"],
                    "albedo": 1,
                    "lightingCondition": "D65_noon",
                    "textureSet": asset["assetId"],
                    "normalScale": intent["normalScale"],
                    "uvScale": intent["uvScale"],
                },
            },
        ],
    }
    return {
        "patch": patch,
        "trace": [{"node": "propose_wild_patch", "status": "done", "detail": "2 个操作"}],
    }


def _ingest_pbr_asset(
    request: dict[str, Any],
    maps: dict[str, dict[str, Any]],
    storage: LocalAssetStorage,
) -> _PbrIngestState:
    state: _PbrIngestState = {"request": request, "maps": maps, "storage": storage, "trace": []}
    for step in (_extract_material_intent, _validate_asset, _register_asset, _propose_wild_patch):
        result = step(state)
        state["trace"].extend(result.pop("trace"))
        state.update(result)
        if state.get("error"):
            break
    return state


async def run_asset_workflow(
    request: dict[str, Any],
    maps: dict[str, dict[str, Any]],
    storage: LocalAssetStorage | None = None,
) -> _PbrIngestState:
    return await asyncio.to_thread(_ingest_pbr_asset, request, maps, storage or asset_storage)


def upload_limit() -> int:
    return asset_storage.max_file_bytes


def list_assets() -> list[dict]:
    return asset_storage.list_manifests()


def hide_asset(asset_id: str) -> None:
    try:
        asset_storage.hide_from_library(asset_id)
    except AssetStorageError as exc:
        raise ApplicationError("invalid_input", str(exc)) from exc
    except FileNotFoundError as exc:
        raise ApplicationError("not_found", "资产不存在") from exc


def get_asset(asset_id: str) -> dict:
    try:
        return asset_storage.get_manifest(asset_id)
    except AssetStorageError as exc:
        raise ApplicationError("invalid_input", str(exc)) from exc
    except FileNotFoundError as exc:
        raise ApplicationError("not_found", "资产不存在") from exc


def get_asset_file(asset_id: str, filename: str):
    try:
        path = asset_storage.resolve_file(asset_id, filename)
        manifest = asset_storage.get_manifest(asset_id)
    except AssetStorageError as exc:
        raise ApplicationError("invalid_input", str(exc)) from exc
    except FileNotFoundError as exc:
        raise ApplicationError("not_found", "资产文件不存在") from exc
    map_entry = next(
        (item for item in manifest.get("maps", {}).values() if item.get("uri", "").endswith(f"/{filename}")),
        {},
    )
    return path, map_entry.get("mimeType", "application/octet-stream")
