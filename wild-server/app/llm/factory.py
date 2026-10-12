"""按供应商分派到 creator；不持有模型缓存、提示词或 Agent。"""
from config import ModelConfig, config
from app.llm.creator import (
    get_dashscope_model,
    get_deepseek_model,
    get_mimo_model,
    get_moonshot_model,
    get_openai_model,
)
from app.llm.providers import resolve_connection

_CREATORS = {
    "openai": get_openai_model,
    "custom": get_openai_model,
    "dashscope": get_dashscope_model,
    "deepseek": get_deepseek_model,
    "moonshot": get_moonshot_model,
    "mimo": get_mimo_model,
}


def create_llm(model_cfg: ModelConfig | None = None, *, enable_thinking=False, streaming=False):
    model_cfg = model_cfg if model_cfg is not None else config.chat
    provider, base_url = resolve_connection(model_cfg)
    resolved = model_cfg.model_copy(update={"provider": provider, "base_url": base_url})
    return _CREATORS[provider](resolved, enable_thinking=enable_thinking, streaming=streaming)
