"""LLM 配置接口的候选配置合并回归测试。"""

import pytest

from app.api.config_api import (
    ModelConfigUpdate,
    _test_model_config,
    test_llm_config as run_llm_config_test,
)
from config import config


def test_candidate_model_config_uses_unsaved_form_values(monkeypatch):
    monkeypatch.setattr(config.chat, "name", "wrong-saved-model")
    monkeypatch.setattr(config.chat, "api_key", "saved-secret")
    monkeypatch.setattr(config.chat, "base_url", "https://old.example/v1")

    candidate = _test_model_config(ModelConfigUpdate(
        name="correct-form-model",
        api_key=None,
        base_url="https://new.example/v1",
    ))

    assert candidate.name == "correct-form-model"
    assert candidate.api_key == "saved-secret"
    assert candidate.base_url == "https://new.example/v1"
    assert config.chat.name == "wrong-saved-model"


def test_candidate_model_config_can_test_new_api_key_without_saving(monkeypatch):
    monkeypatch.setattr(config.chat, "name", "saved-model")
    monkeypatch.setattr(config.chat, "api_key", "saved-secret")

    candidate = _test_model_config(ModelConfigUpdate(api_key="new-secret"))

    assert candidate.api_key == "new-secret"
    assert config.chat.api_key == "saved-secret"


def test_candidate_model_config_rejects_missing_api_key(monkeypatch):
    monkeypatch.setattr(config.chat, "api_key", "")

    with pytest.raises(ValueError, match="API Key"):
        _test_model_config(ModelConfigUpdate(name="model", api_key=None))


def test_candidate_model_config_does_not_mutate_saved_base_url(monkeypatch):
    monkeypatch.setattr(config.chat, "api_key", "saved-secret")
    monkeypatch.setattr(config.chat, "base_url", "https://saved.example/v1")

    candidate = _test_model_config(ModelConfigUpdate(
        name="candidate-model",
        base_url="",
    ))

    assert candidate.base_url == ""
    assert config.chat.base_url == "https://saved.example/v1"


def test_candidate_model_config_uses_thinking_budget_without_mutating_saved_value(
    monkeypatch,
):
    monkeypatch.setattr(config.chat, "api_key", "saved-secret")
    monkeypatch.setattr(config.chat, "thinking_budget", 4096)

    candidate = _test_model_config(ModelConfigUpdate(thinking_budget=8192))

    assert candidate.thinking_budget == 8192
    assert config.chat.thinking_budget == 4096


@pytest.mark.asyncio
async def test_connection_probe_uses_minimal_openai_compatible_payload(monkeypatch):
    calls = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            message = type("Message", (), {"content": "OK"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append({"client_options": kwargs})
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        async def close(self):
            calls.append({"closed": True})

    monkeypatch.setattr("openai.AsyncOpenAI", FakeClient)
    result = await run_llm_config_test(ModelConfigUpdate(
        name="generic-chat-model",
        api_key="candidate-secret",
        base_url="https://provider.example/v1",
    ))

    assert result["success"] is True
    assert calls[1] == {
        "model": "generic-chat-model",
        "messages": [{"role": "user", "content": "Reply with OK."}],
    }
    assert "extra_body" not in calls[1]
    assert "stream_options" not in calls[1]
