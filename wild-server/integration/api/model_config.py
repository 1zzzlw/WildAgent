"""配置管理 API"""

from typing import Any
from fastapi import APIRouter
import integration.model_settings as use_cases
from integration.model_settings import ModelConfigUpdate, ModelConfigResponse

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/llm", response_model=ModelConfigResponse)
async def get_llm_config():
    result = await use_cases.get_llm_config()
    return result


@router.post("/llm")
async def update_llm_config(update: ModelConfigUpdate) -> dict[str, Any]:
    result = await use_cases.update_llm_config(update)
    return result


@router.post("/llm/test")
async def test_llm_config(update: ModelConfigUpdate | None=None) -> dict[str, Any]:
    result = await use_cases.test_llm_config(update)
    return result

