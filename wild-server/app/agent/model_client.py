"""
Model Client —— LLM 工厂

职责：创建并返回 LLM 实例。
不做：持有全局变量、创建 Agent、持有 Prompt 逻辑。
Prompt 逻辑已迁移到 app/agent/prompts.py。
"""

from langchain.chat_models import init_chat_model
from config import config


def create_llm():
    """创建 LLM 实例（每次调用返回新实例，由调用方持有）"""
    return init_chat_model(
        model=config.model_name,
        model_provider="openai",
        api_key=config.model_api_key,
        base_url=config.model_base_url,
    )