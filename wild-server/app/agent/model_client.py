"""
Model Client —— LLM 工厂与 OpenAI-compatible 推理字段适配

职责：创建并返回 LLM 实例。
不做：持有全局变量、创建 Agent、持有 Prompt 逻辑。
"""
from typing import Any
from urllib.parse import urlparse
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk
from config import config, ModelConfig


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


def _reasoning_effort_from_budget(thinking_budget: int) -> str | None:
    """把统一 Token 预算映射为仅支持档位的供应商推理强度。"""
    if thinking_budget <= 0:
        return None
    if thinking_budget <= 4096:
        return "low"
    if thinking_budget <= 16384:
        return "high"
    return "max"


def _thinking_extra_body(model_cfg: ModelConfig, enable_thinking: bool) -> dict | None:
    """把 WildAgent 的统一思考控制映射到已知供应商协议。

    各家 Chat Completions 思考字段并不通用：DashScope 的 Qwen、GLM 和
    部分 Kimi 支持 ``thinking_budget``；DeepSeek 新模型和 Kimi K3 使用
    ``reasoning_effort``；Kimi K2.6 只有思考开关。未知端点不注入扩展字段，
    避免切换 OpenAI-compatible 服务时因不支持的参数返回 400。
    """
    hostname = (urlparse(model_cfg.base_url or "").hostname or "").casefold()
    model_name = (model_cfg.name or "").casefold()
    thinking_budget = int(getattr(model_cfg, "thinking_budget", 0) or 0)

    is_dashscope = (
        hostname.endswith(".aliyuncs.com")
        and (hostname.startswith("dashscope") or ".maas.aliyuncs.com" in hostname)
    )
    if is_dashscope:
        # DeepSeek R1 是固定思考模型；V3.1/V3.2/V4 使用开关和推理档位，
        # 但不支持 Qwen/Kimi 的精确 thinking_budget。
        if "deepseek" in model_name:
            if "r1" in model_name or "reasoner" in model_name:
                return None
            if any(version in model_name for version in ("v3.1", "v3.2", "v4")):
                extra_body: dict[str, Any] = {"enable_thinking": enable_thinking}
                effort = _reasoning_effort_from_budget(thinking_budget)
                if enable_thinking and effort:
                    extra_body["reasoning_effort"] = effort
                return extra_body
            return None

        # DashScope 上由 Moonshot 提供、带 kimi/ 前缀的模型能力不同，不能
        # 沿用阿里云直供 Kimi 的 thinking_budget 协议。
        if model_name.startswith("kimi/"):
            return None

        if model_name.startswith("kimi-"):
            if "k3" in model_name:
                return None
            if "k2.7" in model_name or "thinking" in model_name:
                if not enable_thinking:
                    return None
                return {"thinking_budget": thinking_budget} if thinking_budget > 0 else None
            if "k2.5" in model_name or "k2.6" in model_name:
                extra_body = {"enable_thinking": enable_thinking}
                if enable_thinking and thinking_budget > 0:
                    extra_body["thinking_budget"] = thinking_budget
                return extra_body
            return None

        if model_name.startswith("qwen") or model_name.startswith("glm"):
            # 名称带 thinking 的型号不能关闭思考，只在思考请求上限额。
            if "thinking" in model_name:
                if not enable_thinking:
                    return None
                return {"thinking_budget": thinking_budget} if thinking_budget > 0 else None
            extra_body = {"enable_thinking": enable_thinking}
            if enable_thinking and thinking_budget > 0:
                extra_body["thinking_budget"] = thinking_budget
            return extra_body
        return None

    if hostname == "api.deepseek.com" or hostname.endswith(".deepseek.com"):
        if "r1" in model_name or "reasoner" in model_name:
            return None
        if any(version in model_name for version in ("v3.1", "v3.2", "v4")):
            extra_body = {
                "thinking": {"type": "enabled" if enable_thinking else "disabled"},
            }
            effort = _reasoning_effort_from_budget(thinking_budget)
            if enable_thinking and effort:
                extra_body["reasoning_effort"] = effort
            return extra_body
        return None

    is_moonshot = (
        hostname in {"api.moonshot.ai", "api.moonshot.cn", "api.kimi.com", "api.kimi.ai"}
        or hostname.endswith(".moonshot.ai")
        or hostname.endswith(".moonshot.cn")
    )
    if is_moonshot:
        if "kimi-k3" in model_name:
            # K3 始终思考；普通节点也只能降到最低推理档位，不能真正关闭。
            if not enable_thinking:
                return {"reasoning_effort": "low"}
            effort = _reasoning_effort_from_budget(thinking_budget)
            return {"reasoning_effort": effort or "max"}
        if "kimi-k2.6" in model_name or "kimi-k2.5" in model_name:
            return {
                "thinking": {"type": "enabled" if enable_thinking else "disabled"},
            }
        # K2.7 Code 等固定思考模型不接受思考开关或 effort。
        return None

    return None


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
    """创建一个由调用方持有的 LangChain 聊天模型实例。

    Args:
        model_cfg: 可选模型配置。省略时使用全局 ``config.chat``。
        enable_thinking: 是否请求模型返回思考内容；已知供应商会映射为各自
            支持的开关、Token 预算或推理强度，未知端点不注入扩展字段。
        streaming: 是否使用流式 Chat Completions。

    Returns:
        实现 LangChain ChatModel 协议的模型对象。
    """
    if model_cfg is None:
        model_cfg = config.chat

    timeout = float(getattr(model_cfg, "timeout", 60.0) or 60.0)
    return ReasoningChatOpenAI(
        model=model_cfg.name,
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url or None,
        request_timeout=timeout if timeout > 0 else None,
        extra_body=_thinking_extra_body(model_cfg, enable_thinking),
        streaming=streaming,
        stream_usage=streaming,
    )
