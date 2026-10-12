"""工厂的协议分派、真实 SDK 请求序列化和模型切换回归；不访问供应商。"""
import json

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.llm.factory import create_llm
from app.llm.providers import resolve_connection
from config import ModelConfig, config


@pytest.mark.parametrize("url,provider", [
    ("", "openai"),
    ("https://api.openai.com/v1", "openai"),
    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "dashscope"),
    ("https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "dashscope"),
    ("https://api.deepseek.com/v1", "deepseek"),
    ("https://api.moonshot.ai/v1", "moonshot"),
    ("https://api.kimi.com/v1", "moonshot"),
    ("https://api.xiaomimimo.com/v1", "mimo"),
    ("https://token-plan-cn.xiaomimimo.com/v1", "mimo"),
    ("https://token-plan-global.xiaomimimo.com/v1", "mimo"),
    ("https://api.xiaomimimo.com.other.example/v1", "custom"),
    ("https://compatible.example/v1", "custom"),
])
def test_auto_preserves_existing_endpoint_routing(url, provider):
    cfg = ModelConfig(base_url=url)
    resolved, base_url = resolve_connection(cfg)
    assert resolved == provider and base_url
    assert cfg.provider == "auto" and cfg.base_url == url


@pytest.mark.parametrize("provider", ["openai", "dashscope", "deepseek", "moonshot", "mimo"])
def test_explicit_provider_has_default_url_and_does_not_mutate_config(provider):
    cfg = ModelConfig(provider=provider, name="model", api_key="test-key")
    before = cfg.model_dump()
    model = create_llm(cfg)
    assert model.openai_api_base == resolve_connection(cfg)[1]
    assert cfg.model_dump() == before


@pytest.mark.parametrize("thinking", [False, True])
def test_mimo_request_serialization_keeps_thinking_switch_and_reasoning(thinking):
    cfg = ModelConfig(provider="mimo", name="mimo-v2.6-flash", api_key="test-key", thinking_budget=2048)
    model = create_llm(cfg, enable_thinking=thinking)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        assert request.url.host == "api.xiaomimimo.com"
        return httpx.Response(200, json={
            "id": "mock", "object": "chat.completion", "created": 0, "model": cfg.name,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "OK", "reasoning_content": "mock reasoning" if thinking else ""}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        })

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        with OpenAI(api_key="test-key", base_url=model.openai_api_base, http_client=http_client) as sdk:
            model.client = sdk.chat.completions
            result = model.invoke("Reply OK")
    assert requests[0]["thinking"] == {"type": "enabled" if thinking else "disabled"}
    assert "thinking_budget" not in requests[0] and "reasoning_effort" not in requests[0]
    assert "max_completion_tokens" not in requests[0]
    assert result.content == "OK"
    assert result.additional_kwargs.get("reasoning_content", "") == ("mock reasoning" if thinking else "")


def test_switching_provider_recreates_client_without_previous_protocol_leaking(monkeypatch):
    monkeypatch.setattr(config, "chat", ModelConfig(provider="dashscope", name="qwen-plus", api_key="test-key"))
    old = create_llm(enable_thinking=True)
    monkeypatch.setattr(config, "chat", ModelConfig(provider="mimo", name="mimo-v2.6-flash", api_key="test-key"))
    new = create_llm(enable_thinking=False)
    assert old.extra_body == {"enable_thinking": True, "thinking_budget": 4096}
    assert new.extra_body == {"thinking": {"type": "disabled"}}
    assert old.model_name == "qwen-plus" and new.model_name == "mimo-v2.6-flash"
    assert old is not new


def test_custom_endpoint_uses_standard_protocol_even_when_model_name_is_mimo():
    model = create_llm(ModelConfig(provider="custom", name="mimo-v2.6-flash", api_key="test-key",
                                  base_url="https://proxy.example/v1"), enable_thinking=True)
    assert model.extra_body is None


def test_custom_provider_without_url_is_rejected():
    with pytest.raises(ValueError, match="Base URL"):
        create_llm(ModelConfig(provider="custom", api_key="test-key"))


def test_unknown_provider_is_rejected_by_configuration_schema():
    with pytest.raises(ValidationError):
        ModelConfig(provider="unconfigured")
