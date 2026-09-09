"""建筑设计文档、版本化 Patch、批准和 SVG 预览 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.design.contracts import DesignDocument, DesignPatch
from app.design.repository import DesignConflictError, design_repository
from app.design.resolver import resolve_design


router = APIRouter(prefix="/api/designs", tags=["designs"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApproveDesignRequest(StrictRequest):
    base_revision: int = Field(ge=1)


def _package(document: DesignDocument, resolved: dict) -> dict:
    return {
        "document": document.model_dump(mode="json"),
        "resolved": resolved,
        "preview_url": f"/api/designs/{document.session_id}/preview.svg?revision={document.revision}",
    }


@router.get("/schema")
async def get_design_schema():
    return JSONResponse(content=DesignDocument.model_json_schema())


@router.get("/{session_id}")
async def get_design(session_id: str):
    try:
        document = design_repository.get(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="设计文档不存在")
    resolved = resolve_design(document).model_dump(mode="json")
    return JSONResponse(content=_package(document, resolved))


@router.patch("/{session_id}")
async def patch_design(session_id: str, patch: DesignPatch):
    try:
        document, resolved = design_repository.apply_patch(session_id, patch)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DesignConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content=_package(document, resolved))


@router.post("/{session_id}/approve")
async def approve_design(session_id: str, body: ApproveDesignRequest):
    try:
        document, resolved = design_repository.approve(session_id, body.base_revision)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DesignConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content=_package(document, resolved))


@router.get("/{session_id}/preview.svg")
async def get_design_preview(session_id: str):
    try:
        path = design_repository.svg_path(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="设计预览不存在")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
