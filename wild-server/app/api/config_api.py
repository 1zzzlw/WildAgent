"""配置管理 API"""
from typing import Any
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from config import config


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


def update_env_file(key: str, value: str) -> None:
    """更新 .env 文件中的配置项
    
    Args:
        key: 环境变量键名（如 CHAT__NAME）
        value: 环境变量值
    """
    env_path = Path(".env")
    
    # 确保 .env 文件存在
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
        logger.info(f"[config] 创建新的 .env 文件")
    
    # 读取现有内容
    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    
    # 查找并更新已存在的配置项
    for i, line in enumerate(lines):
        # 忽略注释和空行
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        
        # 检查是否匹配目标键
        if stripped.startswith(f"{key}=") or stripped.split("=")[0].strip() == key:
            lines[i] = f"{key}={value}"
            updated = True
            logger.info(f"[config] 更新 .env 配置: {key}=***")
            break
    
    # 如果不存在，追加到文件末尾
    if not updated:
        lines.append(f"{key}={value}")
        logger.info(f"[config] 新增 .env 配置: {key}=***")
    
    # 写回文件
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.get("/llm", response_model=ModelConfigResponse)
async def get_llm_config():
    """获取当前 LLM 配置（隐藏完整 API Key）"""
    return ModelConfigResponse(
        name=config.chat.name,
        api_key_set=bool(config.chat.api_key),
        base_url=config.chat.base_url or "",
    )


@router.post("/llm")
async def update_llm_config(update: ModelConfigUpdate) -> dict[str, Any]:
    """更新 LLM 配置（同时更新内存和 .env 文件）"""
    try:
        updated_fields = []
        
        # 更新模型名称
        if update.name is not None:
            config.chat.name = update.name
            update_env_file("CHAT__NAME", update.name)
            updated_fields.append("模型名称")
            logger.info(f"[config] 已更新 LLM 模型名称: {update.name}")
        
        # 更新 API Key
        if update.api_key is not None:
            config.chat.api_key = update.api_key
            update_env_file("CHAT__API_KEY", update.api_key)
            updated_fields.append("API Key")
            logger.info(f"[config] 已更新 LLM API Key")
        
        # 更新 Base URL
        if update.base_url is not None:
            config.chat.base_url = update.base_url
            update_env_file("CHAT__BASE_URL", update.base_url)
            updated_fields.append("Base URL")
            logger.info(f"[config] 已更新 LLM Base URL: {update.base_url}")
        
        # 清除 LLM 实例缓存（如果有）
        from app.services.agent_service import agent_service
        if hasattr(agent_service, '_llm_cache'):
            agent_service._llm_cache.clear()
        
        if not updated_fields:
            return {
                "success": False,
                "message": "没有提供任何配置更新",
            }
        
        return {
            "success": True,
            "message": f"配置已保存到 .env 文件并立即生效（已更新: {', '.join(updated_fields)}）",
            "config": {
                "name": config.chat.name,
                "api_key_set": bool(config.chat.api_key),
                "base_url": config.chat.base_url or "",
            }
        }
    
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
