"""蓝图 REST API，保持原有 .wild URL，数据统一由 MySQL 仓储持久化。"""

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
import app.application.blueprints as use_cases

router = APIRouter(prefix="/api/scenes", tags=["scenes"])

NO_CACHE = {"Cache-Control": "no-store, max-age=0"}


@router.get("")
def list_scenes(request: Request):
    result = use_cases.list_scenes(getattr(request.state, "user", None))
    return JSONResponse(result, headers=NO_CACHE)


@router.get("/{filename:path}")
def get_scene(filename: str):
    result = use_cases.get_scene(filename)
    return JSONResponse(result, headers=NO_CACHE)


@router.put("/{filename:path}")
def update_scene(filename: str, request: Request, blueprint: dict=Body(...)):
    result = use_cases.update_scene(filename, getattr(request.state, "user", None), blueprint)
    return result


@router.delete("/{filename:path}")
def delete_scene(filename: str):
    result = use_cases.delete_scene(filename)
    return result

