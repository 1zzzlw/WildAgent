"""蓝图 REST API，保持原有 .wild URL，数据统一由 MySQL 仓储持久化。"""

from hashlib import sha256
from urllib.parse import unquote

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse, Response
import app.application.blueprints as use_cases

router = APIRouter(prefix="/api/scenes", tags=["scenes"])

NO_CACHE = {"Cache-Control": "no-store, max-age=0"}


@router.get("")
def list_scenes(request: Request):
    result = use_cases.list_scenes(getattr(request.state, "user", None))
    return JSONResponse(result, headers=NO_CACHE)


@router.get("/{filename:path}")
def get_scene(filename: str, request: Request):
    result = use_cases.get_scene(filename)
    response = JSONResponse(result)
    etag = '"' + sha256(response.body).hexdigest() + '"'
    headers = {"Cache-Control": "private, no-cache", "ETag": etag}
    candidates = request.headers.get("if-none-match", "").split(",")
    for candidate in candidates:
        candidate = candidate.strip().removeprefix("W/")
        if candidate == etag or candidate == "*":
            return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return response


@router.put("/{filename:path}")
def update_scene(filename: str, request: Request, blueprint: dict=Body(...),
                 x_operation_id: str | None = Header(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
                 x_operation_label: str = Header(default="", max_length=2400),
                 x_base_revision: int | None = Header(default=None, ge=0)):
    result = use_cases.update_scene(filename, getattr(request.state, "user", None), blueprint,
                                    operation_id=x_operation_id,
                                    label=unquote(x_operation_label)[:200] or "保存蓝图",
                                    base_revision=x_base_revision)
    return result


@router.delete("/{filename:path}")
def delete_scene(filename: str, request: Request):
    result = use_cases.delete_scene(filename, getattr(request.state, "user", None))
    return result

