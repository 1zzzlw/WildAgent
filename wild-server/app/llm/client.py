"""
OpenAI-compatible 响应解析与既有节点创建入口。
供应商分派及请求参数由 factory / creator 负责。
"""
from typing import Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk
from config import ModelConfig


def _response_mapping(value: Any) -> dict:
    """兼容 OpenAI SDK 的 Pydantic 响应对象和旧版字典响应。"""
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else {}
    legacy_dict = getattr(value, "dict", None)
    if callable(legacy_dict):
        dumped = legacy_dict()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def content_as_text(value: object) -> str:
    """兼容字符串和 OpenAI 多内容块消息。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            text for item in value
            if (text := content_as_text(item))
        )
    if isinstance(value, dict):
        for key in ("text", "content", "output_text"):
            text = content_as_text(value.get(key))
            if text:
                return text
    return ""


def message_texts(message: object) -> tuple[str, str]:
    """返回模型消息的普通内容和兼容推理内容。"""
    if isinstance(message, dict):
        content = content_as_text(message.get("content"))
        additional = message.get("additional_kwargs", {})
        metadata = message.get("response_metadata", {})
    else:
        content = content_as_text(getattr(message, "content", ""))
        additional = getattr(message, "additional_kwargs", {})
        metadata = getattr(message, "response_metadata", {})
    reasoning = ""
    if isinstance(additional, dict):
        reasoning = content_as_text(additional.get("reasoning_content"))
    if not reasoning and isinstance(metadata, dict):
        reasoning = content_as_text(metadata.get("reasoning_content"))
    return content, reasoning


class ReasoningChatOpenAI(ChatOpenAI):
    """捕获 reasoning_content（DashScope/OpenAI-compatible 服务扩展字段）+ 流式 usage。

    覆盖两个路径：
    1. 流式：_convert_chunk_to_generation_chunk  处理每个 chunk
       - 补回 reasoning_content 到 chunk
       - 捕获最终 chunk 中的 usage（DashScope 在最后一条 chunk 带 usage）
    2. 非流式：_create_chat_result                处理完整响应
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        """流式路径：补回 reasoning_content + 捕获 usage"""
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info,
        )
        if generation_chunk is None:
            return None

        chunk_data = _response_mapping(chunk)
        nested_chunk = _response_mapping(chunk_data.get("chunk", {}))
        choices = chunk_data.get("choices") or nested_chunk.get("choices") or []
        delta: dict[str, Any] = (choices[0].get("delta") or {}) if choices else {}
        reasoning_delta = delta.get("reasoning_content")
        if reasoning_delta:
            generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_delta

        # 捕获 usage（OpenAI-compatible 最终 chunk 带空 choices + usage 字段）
        usage = chunk_data.get("usage")
        if usage:
            generation_chunk.generation_info = generation_chunk.generation_info or {}
            generation_chunk.generation_info["usage"] = usage

        return generation_chunk

    def _create_chat_result(self, response: Any, *args: Any, **kwargs: Any) -> Any:
        """非流式路径：补回 reasoning_content 到最终消息

        使用 *args/**kwargs 兼容 LangChain 不同版本的签名差异（0.2: 3 参数，
        0.3+: 2 参数）。多余的参数原样转发给父类。
        """
        result = super()._create_chat_result(response, *args, **kwargs)

        response_data = _response_mapping(response)
        choices = response_data.get("choices") or []
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
    """保留节点调用入口，模型创建统一交给供应商工厂。"""
    from app.llm.factory import create_llm as create_model

    return create_model(model_cfg, enable_thinking=enable_thinking, streaming=streaming)
