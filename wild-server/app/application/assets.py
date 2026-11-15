"""资产生成用例入口。"""
from typing import Any
from app.infrastructure.storage.assets import LocalAssetStorage
from app.infrastructure.storage.assets import asset_storage
from app.agent.workflows.assets.graph import asset_workflow
from app.agent.workflows.assets.graph import AssetWorkflowState
from app.infrastructure.storage.assets import AssetStorageError
from app.application.errors import ApplicationError


async def run_asset_workflow(
    request: dict[str, Any],
    maps: dict[str, dict[str, Any]],
    storage: LocalAssetStorage | None = None,
) -> AssetWorkflowState:
    return await asset_workflow.ainvoke({
        "request": request,
        "maps": maps,
        "storage": storage or asset_storage,
        "trace": [],
    })


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
