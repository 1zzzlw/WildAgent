"""创建各供应商客户端；思考参数在对应 creator 内处理。"""
from app.llm.client import ReasoningChatOpenAI


def _create(model_cfg, streaming, extra_body=None):
    return ReasoningChatOpenAI(
        model=model_cfg.name,
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
        request_timeout=model_cfg.timeout if model_cfg.timeout > 0 else None,
        max_retries=model_cfg.max_retries,
        extra_body=extra_body,
        streaming=streaming,
        stream_usage=streaming,
    )


def _effort(budget):
    if budget <= 4096:
        return "low"
    return "high" if budget <= 16384 else "max"


def get_openai_model(model_cfg, *, enable_thinking=False, streaming=False):
    return _create(model_cfg, streaming)


def get_mimo_model(model_cfg, *, enable_thinking=False, streaming=False):
    return _create(model_cfg, streaming, {"thinking": {"type": "enabled" if enable_thinking else "disabled"}})


def get_deepseek_model(model_cfg, *, enable_thinking=False, streaming=False):
    name = model_cfg.name.casefold()
    extra = None
    if not ("r1" in name or "reasoner" in name) and any(v in name for v in ("v3.1", "v3.2", "v4")):
        extra = {"thinking": {"type": "enabled" if enable_thinking else "disabled"}}
        if enable_thinking and model_cfg.thinking_budget:
            extra["reasoning_effort"] = _effort(model_cfg.thinking_budget)
    return _create(model_cfg, streaming, extra)


def get_moonshot_model(model_cfg, *, enable_thinking=False, streaming=False):
    name = model_cfg.name.casefold()
    extra = None
    if "kimi-k3" in name:
        effort = _effort(model_cfg.thinking_budget) if model_cfg.thinking_budget else "max"
        extra = {"reasoning_effort": effort if enable_thinking else "low"}
    elif "kimi-k2.6" in name or "kimi-k2.5" in name:
        extra = {"thinking": {"type": "enabled" if enable_thinking else "disabled"}}
    return _create(model_cfg, streaming, extra)


def get_dashscope_model(model_cfg, *, enable_thinking=False, streaming=False):
    name, budget = model_cfg.name.casefold(), model_cfg.thinking_budget
    extra = None
    if "deepseek" in name:
        if not ("r1" in name or "reasoner" in name) and any(v in name for v in ("v3.1", "v3.2", "v4")):
            extra = {"enable_thinking": enable_thinking}
            if enable_thinking and budget:
                extra["reasoning_effort"] = _effort(budget)
    elif name.startswith("kimi-"):
        if "k3" not in name:
            if "k2.7" in name or "thinking" in name:
                extra = {"thinking_budget": budget} if enable_thinking and budget else None
            elif "k2.5" in name or "k2.6" in name:
                extra = {"enable_thinking": enable_thinking}
                if enable_thinking and budget:
                    extra["thinking_budget"] = budget
    elif name.startswith(("qwen", "glm")):
        if "thinking" in name:
            extra = {"thinking_budget": budget} if enable_thinking and budget else None
        else:
            extra = {"enable_thinking": enable_thinking}
            if enable_thinking and budget:
                extra["thinking_budget"] = budget
    return _create(model_cfg, streaming, extra)
