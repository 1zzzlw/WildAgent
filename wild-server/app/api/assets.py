"""PBR 纹理集入库、查询和静态文件访问 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.agent.asset_graph import run_asset_workflow
from app.services.asset_storage import AssetStorageError, asset_storage


router = APIRouter(prefix="/api/assets", tags=["assets"])


def _split_terms(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


async def _read_upload(upload: UploadFile | None) -> dict | None:
    if upload is None:
        return None
    data = await upload.read(asset_storage.max_file_bytes + 1)
    return {
        "filename": upload.filename or "texture",
        "mime_type": upload.content_type or "",
        "data": data,
    }


@router.post("/pbr")
async def upload_pbr_asset(
    name: Annotated[str, Form()],
    material_name: Annotated[str, Form()],
    license_name: Annotated[str, Form(alias="license")],
    base_revision: Annotated[int, Form()] = 1,
    source_type: Annotated[str, Form()] = "local_upload",
    source_uri: Annotated[str | None, Form()] = None,
    roughness: Annotated[float, Form()] = 0.8,
    metallic: Annotated[float, Form()] = 0.0,
    color_tint_r: Annotated[float, Form()] = 1.0,
    color_tint_g: Annotated[float, Form()] = 1.0,
    color_tint_b: Annotated[float, Form()] = 1.0,
    normal_scale: Annotated[float, Form()] = 1.0,
    uv_scale_x: Annotated[float, Form()] = 1.0,
    uv_scale_y: Annotated[float, Form()] = 1.0,
    material_class: Annotated[str, Form()] = "other",
    tags: Annotated[str, Form()] = "",
    recommended_roles: Annotated[str, Form()] = "",
    real_world_width: Annotated[float, Form()] = 1.0,
    real_world_height: Annotated[float, Form()] = 1.0,
    base_color: Annotated[UploadFile | None, File()] = None,
    normal: Annotated[UploadFile | None, File()] = None,
    roughness_map: Annotated[UploadFile | None, File()] = None,
    metalness_map: Annotated[UploadFile | None, File()] = None,
    ambient_occlusion: Annotated[UploadFile | None, File()] = None,
):
    if base_color is None:
        raise HTTPException(status_code=422, detail="base_color 为必填文件")
    uploads = {
        "baseColor": await _read_upload(base_color),
        "normal": await _read_upload(normal),
        "roughness": await _read_upload(roughness_map),
        "metalness": await _read_upload(metalness_map),
        "ambientOcclusion": await _read_upload(ambient_occlusion),
    }
    maps = {channel: item for channel, item in uploads.items() if item is not None}
    result = await run_asset_workflow(
        {
            "name": name,
            "materialName": material_name,
            "license": license_name,
            "sourceType": source_type,
            "sourceUri": source_uri,
            "roughness": roughness,
            "metallic": metallic,
            "baseColorTint": [color_tint_r, color_tint_g, color_tint_b],
            "normalScale": normal_scale,
            "uvScale": [uv_scale_x, uv_scale_y],
            "materialClass": material_class,
            "tags": _split_terms(tags),
            "recommendedRoles": _split_terms(recommended_roles),
            "realWorldSizeMeters": [real_world_width, real_world_height],
            "baseRevision": base_revision,
        },
        maps,
        asset_storage,
    )
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return JSONResponse({
        "asset": result["asset"],
        "patch": result["patch"],
        "trace": result.get("trace", []),
    })


@router.get("")
async def list_assets():
    return JSONResponse(
        asset_storage.list_manifests(),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.delete("/{asset_id}", status_code=204)
async def hide_asset(asset_id: str):
    try:
        asset_storage.hide_from_library(asset_id)
    except AssetStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="资产不存在") from exc


@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    try:
        manifest = asset_storage.get_manifest(asset_id)
    except AssetStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="资产不存在") from exc
    return JSONResponse(manifest, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/{asset_id}/files/{filename}")
async def get_asset_file(asset_id: str, filename: str):
    try:
        path = asset_storage.resolve_file(asset_id, filename)
        manifest = asset_storage.get_manifest(asset_id)
    except AssetStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="资产文件不存在") from exc
    map_entry = next(
        (item for item in manifest.get("maps", {}).values() if item.get("uri", "").endswith(f"/{filename}")),
        {},
    )
    return FileResponse(
        path,
        media_type=map_entry.get("mimeType", "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
