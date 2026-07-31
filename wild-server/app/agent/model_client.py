"""
Model Client —— LLM 工厂

职责：创建并返回 LLM 实例。
不做：持有全局变量、创建 Agent、持有 Prompt 逻辑。
Prompt 逻辑已迁移到 app/agent/prompts.py。
"""

from langchain.chat_models import init_chat_model

from config import config, ModelConfig


def create_llm(model_cfg: ModelConfig | None = None):
    """创建一个由调用方持有的 LangChain 聊天模型实例。

    Args:
        model_cfg: 可选模型配置。省略时使用全局 ``config.chat``。

    Returns:
        实现 LangChain ChatModel 协议的模型对象。

    每次调用都返回新实例，本模块不缓存客户端，也不负责 Agent、Prompt 或会话状态。
    """
    if model_cfg is None:
        # 常规对话统一走 chat 配置；显式参数可用于接入另一套聊天模型。
        model_cfg = config.chat

    # provider 固定为 openai，是因为项目依赖的是 OpenAI-compatible 协议；
    # 真实服务商由 model、api_key 和 base_url 共同决定。
    return init_chat_model(
        model=model_cfg.name,
        model_provider="openai",
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
    )
