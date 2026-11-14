"""蓝图 REST API，保持原有 .wild URL，数据统一由 MySQL 仓储持久化。"""
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from app.repositories.blueprints import blueprint_repository, validate_filename

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
NO_CACHE = {"Cache-Control": "no-store, max-age=0"}


@router.get("")
def list_scenes(request: Request):
    user = getattr(request.state, "user", None) or {}
    return JSONResponse(blueprint_repository.list(user.get("id")), headers=NO_CACHE)


@router.get("/{filename:path}")
def get_scene(filename: str):
    try:
        row = blueprint_repository.get(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="蓝图不存在")
    return JSONResponse(row["blueprint_json"], headers=NO_CACHE)


@router.put("/{filename:path}")
def update_scene(filename: str, request: Request, blueprint: dict = Body(...)):
    if not isinstance(blueprint.get("meta"), dict) or not isinstance(blueprint.get("geometry"), dict):
        raise HTTPException(status_code=400, detail="JSON 必须包含 meta 和 geometry 对象")
    try:
        validate_filename(filename)
        user = getattr(request.state, "user", None) or {}
        path = blueprint_repository.save(filename, blueprint, owner_id=user.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "path": path}


@router.delete("/{filename:path}")
def delete_scene(filename: str):
    try:
        deleted = blueprint_repository.delete(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="蓝图不存在")
    return {"status": "deleted", "filename": filename}
