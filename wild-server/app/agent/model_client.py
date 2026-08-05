"""
Model Client —— LLM 工厂与 OpenAI-compatible 推理字段适配

职责：创建并返回 LLM 实例。
不做：持有全局变量、创建 Agent、持有 Prompt 逻辑。
"""
from typing import Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk
from config import config, ModelConfig


class ReasoningChatOpenAI(ChatOpenAI):
    """捕获 reasoning_content（DashScope/OpenAI-compatible 服务扩展字段）。

    覆盖两个路径：
    1. 流式：_convert_chunk_to_generation_chunk  处理每个 chunk
    2. 非流式：_create_chat_result                处理完整响应
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        """流式路径：补回 reasoning_content 到每个 chunk"""
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info,
        )
        if generation_chunk is None:
            return None

        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        delta: dict[str, Any] = (choices[0].get("delta") or {}) if choices else {}
        reasoning_delta = delta.get("reasoning_content")
        if reasoning_delta:
            generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_delta
        return generation_chunk

    def _create_chat_result(self, response: dict, *args: Any, **kwargs: Any) -> Any:
        """非流式路径：补回 reasoning_content 到最终消息

        使用 *args/**kwargs 兼容 LangChain 不同版本的签名差异（0.2: 3 参数，
        0.3+: 2 参数）。多余的参数原样转发给父类。
        """
        result = super()._create_chat_result(response, *args, **kwargs)

        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            reasoning = message.get("reasoning_content")
            if reasoning and result.generations:
                for gen in result.generations:
                    if hasattr(gen, "message"):
                        gen.message.additional_kwargs["reasoning_content"] = reasoning

        return result


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
        streaming: 是否使用流式 Chat Completions。

    Returns:
        实现 LangChain ChatModel 协议的模型对象。
    """
    if model_cfg is None:
        model_cfg = config.chat

    return ReasoningChatOpenAI(
        model=model_cfg.name,
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url or None,
        extra_body={"enable_thinking": enable_thinking},
        streaming=streaming,
    )
