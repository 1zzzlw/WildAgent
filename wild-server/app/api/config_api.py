"""配置管理 API"""
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from config import config
from app.utils.runtime_env import (
    runtime_env_host_path,
    runtime_env_is_persistent,
    runtime_env_path,
    update_runtime_env,
)


router = APIRouter(prefix="/api/config", tags=["config"])


class ModelConfigUpdate(BaseModel):
    """模型配置更新请求"""
    name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    thinking_budget: int | None = Field(default=None, ge=0, le=262144)


class ModelConfigResponse(BaseModel):
    """模型配置响应（隐藏 API Key）"""
    name: str
    api_key_set: bool
    base_url: str
    thinking_budget: int
    storage_path: str
    host_storage_path: str | None = None
    persistent: bool


@router.get("/llm", response_model=ModelConfigResponse)
async def get_llm_config():
    """获取当前 LLM 配置（隐藏完整 API Key）"""
    return ModelConfigResponse(
        name=config.chat.name,
        api_key_set=bool(config.chat.api_key),
        base_url=config.chat.base_url or "",
        thinking_budget=config.chat.thinking_budget,
        storage_path=str(runtime_env_path()),
        host_storage_path=runtime_env_host_path(),
        persistent=runtime_env_is_persistent(),
    )


@router.post("/llm")
async def update_llm_config(update: ModelConfigUpdate) -> dict[str, Any]:
    """持久化全站 Chat 模型配置，并重建当前进程的模型客户端。"""
    try:
        env_updates: dict[str, str] = {}
        updated_fields: list[str] = []
        if update.name is not None:
            name = update.name.strip()
            if not name:
                raise ValueError("模型名称不能为空")
            env_updates["CHAT__NAME"] = name
            updated_fields.append("模型名称")
        if update.api_key is not None:
            env_updates["CHAT__API_KEY"] = update.api_key.strip()
            updated_fields.append("API Key")
        if update.base_url is not None:
            env_updates["CHAT__BASE_URL"] = update.base_url.strip()
            updated_fields.append("Base URL")
        if update.thinking_budget is not None:
            env_updates["CHAT__THINKING_BUDGET"] = str(update.thinking_budget)
            updated_fields.append("思考预算")

        if not env_updates:
            return {
                "success": False,
                "message": "没有提供任何配置更新",
            }

        previous = {
            "CHAT__NAME": config.chat.name,
            "CHAT__API_KEY": config.chat.api_key,
            "CHAT__BASE_URL": config.chat.base_url or "",
            "CHAT__THINKING_BUDGET": str(config.chat.thinking_budget),
        }
        saved_path = update_runtime_env(env_updates)
        try:
            if "CHAT__NAME" in env_updates:
                config.chat.name = env_updates["CHAT__NAME"]
            if "CHAT__API_KEY" in env_updates:
                config.chat.api_key = env_updates["CHAT__API_KEY"]
            if "CHAT__BASE_URL" in env_updates:
                config.chat.base_url = env_updates["CHAT__BASE_URL"]
            if "CHAT__THINKING_BUDGET" in env_updates:
                config.chat.thinking_budget = int(env_updates["CHAT__THINKING_BUDGET"])
            os.environ.update(env_updates)
            from app.services.agent_service import agent_service

            agent_service.reload_chat_models()
        except Exception:
            rollback = {key: previous[key] for key in env_updates}
            try:
                update_runtime_env(rollback, saved_path)
            finally:
                config.chat.name = previous["CHAT__NAME"]
                config.chat.api_key = previous["CHAT__API_KEY"]
                config.chat.base_url = previous["CHAT__BASE_URL"]
                config.chat.thinking_budget = int(previous["CHAT__THINKING_BUDGET"])
                os.environ.update(rollback)
            raise

        logger.info(
            f"[config] Chat 模型配置已持久化并热重载: path={saved_path}, "
            f"fields={updated_fields}"
        )
        persistent = runtime_env_is_persistent()
        return {
            "success": True,
            "message": (
                f"配置已保存并立即生效（已更新: {', '.join(updated_fields)}；"
                f"路径: {saved_path}）"
            ),
            "config": {
                "name": config.chat.name,
                "api_key_set": bool(config.chat.api_key),
                "base_url": config.chat.base_url or "",
                "thinking_budget": config.chat.thinking_budget,
                "storage_path": str(saved_path),
                "host_storage_path": runtime_env_host_path(),
                "persistent": persistent,
            }
        }
    
    except ValueError as e:
        logger.warning(f"[config] 配置输入无效: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[config] 更新 LLM 配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _test_model_config(update: ModelConfigUpdate | None):
    """合并表单候选值与当前配置，但不修改运行时配置或持久化文件。"""
    from config import ModelConfig

    update = update or ModelConfigUpdate()
    name = update.name.strip() if update.name is not None else config.chat.name
    api_key = update.api_key.strip() if update.api_key else config.chat.api_key
    base_url = (
        update.base_url.strip()
        if update.base_url is not None
        else (config.chat.base_url or "")
    )
    thinking_budget = (
        update.thinking_budget
        if update.thinking_budget is not None
        else config.chat.thinking_budget
    )
    if not name:
        raise ValueError("模型名称不能为空")
    if not api_key:
        raise ValueError("API Key 不能为空；如已保存密钥，可将输入框留空")
    return ModelConfig(
        name=name,
        api_key=api_key,
        base_url=base_url,
        thinking_budget=thinking_budget,
        timeout=config.chat.timeout,
    )


@router.post("/llm/test")
async def test_llm_config(update: ModelConfigUpdate | None = None) -> dict[str, Any]:
    """用最小 OpenAI-compatible 请求测试候选配置，不复用 Agent 客户端。"""
    test_config = None
    try:
        from openai import AsyncOpenAI

        test_config = _test_model_config(update)
        logger.info(
            f"[config] 测试 LLM 连接: model={test_config.name}, "
            f"base_url={test_config.base_url or '<default>'}"
        )

        # 连接测试只验证最小 Chat Completions 标准协议，不携带 Agent、思考、
        # 流式统计、温度或 token 上限等供应商扩展参数。
        client_options: dict[str, Any] = {
            "api_key": test_config.api_key,
            "max_retries": 0,
        }
        if test_config.timeout > 0:
            client_options["timeout"] = test_config.timeout
        if test_config.base_url:
            client_options["base_url"] = test_config.base_url
        test_client = AsyncOpenAI(**client_options)
        try:
            response = await test_client.chat.completions.create(
                model=test_config.name,
                messages=[{"role": "user", "content": "Reply with OK."}],
            )
        finally:
            await test_client.close()

        # HTTP 成功即说明连接、鉴权和模型 ID 可用；正文为空不应把连接误判失败。
        content = ""
        choices = getattr(response, "choices", None) or []
        if choices:
            content = str(getattr(choices[0].message, "content", "") or "")
        
        logger.info(f"[config] LLM 通用连接测试成功: {content[:50]}")
        
        return {
            "success": True,
            "message": "LLM 连接测试成功",
            "response": content[:100],
            "tested": {
                "name": test_config.name,
                "base_url": test_config.base_url or "",
            },
        }

    except ValueError as e:
        logger.warning(f"[config] LLM 测试配置无效: {e}")
        return {
            "success": False,
            "message": str(e),
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"[config] LLM 测试失败: {e}")
        from app.agent.model_errors import classify_model_error

        error_info = classify_model_error(e)
        return {
            "success": False,
            "message": error_info["user_message"],
            "error": str(e),
            "error_category": error_info["category"],
            "retryable": error_info["retryable"],
            "tested": (
                {
                    "name": test_config.name,
                    "base_url": test_config.base_url or "",
                }
                if test_config is not None
                else None
            ),
        }
