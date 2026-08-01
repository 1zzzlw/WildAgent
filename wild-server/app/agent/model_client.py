"""
Model Client —— LLM 工厂与 OpenAI-compatible 推理字段适配

职责：创建并返回 LLM 实例。
不做：持有全局变量、创建 Agent、持有 Prompt 逻辑。
Prompt 逻辑已迁移到 app/agent/prompts.py。
"""

from typing import Any

from langchain_openai import ChatOpenAI

from config import config, ModelConfig


class ReasoningChatOpenAI(ChatOpenAI):
    """保留兼容服务在流式响应中返回的 ``reasoning_content``。

    ``ChatOpenAI`` 只解析 OpenAI 标准字段，会忽略 DashScope 等兼容服务扩展的
    ``reasoning_content``。这里仅补回该字段，其余消息、工具调用和最终回复仍由
    LangChain 原有逻辑处理。
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        if generation_chunk is None:
            return None

        choices = (
            chunk.get("choices")
            or chunk.get("chunk", {}).get("choices")
            or []
        )
        delta: dict[str, Any] = (choices[0].get("delta") or {}) if choices else {}
        reasoning_delta = delta.get("reasoning_content")
        if reasoning_delta:
            generation_chunk.message.additional_kwargs["reasoning_content"] = (
                reasoning_delta
            )
        return generation_chunk


def create_llm(
    model_cfg: ModelConfig | None = None,
    *,
    enable_thinking: bool = False,
    streaming: bool = False,
):
    """创建一个由调用方持有的 LangChain 聊天模型实例。

    Args:
        model_cfg: 可选模型配置。省略时使用全局 ``config.chat``。
        enable_thinking: 是否向 OpenAI-compatible 服务传递思考开关。
        streaming: 是否使用流式 Chat Completions；思考模式需要开启。

    Returns:
        实现 LangChain ChatModel 协议的模型对象。

    每次调用都返回新实例，本模块不缓存客户端，也不负责 Agent、Prompt 或会话状态。
    """
    if model_cfg is None:
        # 常规对话统一走 chat 配置；显式参数可用于接入另一套聊天模型。
        model_cfg = config.chat

    # provider 固定为 openai，是因为项目依赖的是 OpenAI-compatible 协议；
    # 真实服务商由 model、api_key 和 base_url 共同决定。
    return ReasoningChatOpenAI(
        model=model_cfg.name,
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url or None,
        extra_body={"enable_thinking": enable_thinking},
        streaming=streaming,
    )
