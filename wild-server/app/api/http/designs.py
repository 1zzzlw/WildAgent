"""建筑设计文档、版本化 Patch 和批准 API。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from app.domain.design.contracts import DesignPatch
import app.application.designs as use_cases

router = APIRouter(prefix="/api/designs", tags=["designs"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApproveDesignRequest(StrictRequest):
    base_revision: int = Field(ge=1)


@router.get("/schema")
def get_design_schema():
    result = use_cases.get_design_schema()
    return JSONResponse(result)


@router.get("/{session_id}")
def get_design(session_id: str):
    result = use_cases.get_design(session_id)
    return JSONResponse(result)


@router.patch("/{session_id}")
def patch_design(session_id: str, patch: DesignPatch):
    result = use_cases.patch_design(session_id, patch)
    return JSONResponse(result)


@router.post("/{session_id}/approve")
def approve_design(session_id: str, body: ApproveDesignRequest):
    result = use_cases.approve_design(session_id, body.base_revision)
    return JSONResponse(result)
