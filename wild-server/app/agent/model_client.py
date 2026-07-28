"""
Model Client —— LLM 工厂

职责：创建并返回 LLM 实例。
不做：持有全局变量、创建 Agent、持有 Prompt 逻辑。
Prompt 逻辑已迁移到 app/agent/prompts.py。
"""

from langchain.chat_models import init_chat_model
from config import config, ModelConfig


def create_llm(model_cfg: ModelConfig | None = None):
    """创建 LLM 实例（每次调用返回新实例，由调用方持有）

    默认使用 config.chat，也可传入其他 ModelConfig：
        create_llm(config.embedding)
    """
    if model_cfg is None:
        model_cfg = config.chat

    return init_chat_model(
        model=model_cfg.name,
        model_provider="openai",
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
    )
