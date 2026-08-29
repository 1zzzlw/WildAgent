"""配置管理 API"""
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
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


class ModelConfigResponse(BaseModel):
    """模型配置响应（隐藏 API Key）"""
    name: str
    api_key_set: bool
    base_url: str
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

        if not env_updates:
            return {
                "success": False,
                "message": "没有提供任何配置更新",
            }

        previous = {
            "CHAT__NAME": config.chat.name,
            "CHAT__API_KEY": config.chat.api_key,
            "CHAT__BASE_URL": config.chat.base_url or "",
        }
        saved_path = update_runtime_env(env_updates)
        try:
            if "CHAT__NAME" in env_updates:
                config.chat.name = env_updates["CHAT__NAME"]
            if "CHAT__API_KEY" in env_updates:
                config.chat.api_key = env_updates["CHAT__API_KEY"]
            if "CHAT__BASE_URL" in env_updates:
                config.chat.base_url = env_updates["CHAT__BASE_URL"]
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


@router.post("/llm/test")
async def test_llm_config() -> dict[str, Any]:
    """测试当前 LLM 配置是否可用"""
    try:
        from app.agent.model_client import create_llm
        
        logger.info("[config] 测试 LLM 连接...")
        
        # 创建测试 LLM
        test_llm = create_llm()
        
        # 发送简单测试请求
        response = await test_llm.ainvoke(
            [{"role": "user", "content": "请回复'测试成功'"}],
        )
        
        # 提取回复内容
        from app.agent.model_client import message_texts
        content, _ = message_texts(response)
        
        logger.info(f"[config] LLM 测试成功: {content[:50]}")
        
        return {
            "success": True,
            "message": "LLM 连接测试成功",
            "response": content[:100],
        }
    
    except Exception as e:
        logger.error(f"[config] LLM 测试失败: {e}")
        return {
            "success": False,
            "message": f"LLM 连接测试失败: {str(e)}",
            "error": str(e),
        }
