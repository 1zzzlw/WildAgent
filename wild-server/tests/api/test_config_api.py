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


@pytest.mark.asyncio
async def test_mimo_connection_probe_uses_factory_default_endpoint(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = type("Chat", (), {"completions": self})()

        async def create(self, **kwargs):
            return type("Response", (), {"choices": []})()

        async def close(self):
            pass

    monkeypatch.setattr("openai.AsyncOpenAI", FakeClient)
    result = await run_llm_config_test(ModelConfigUpdate(provider="mimo", name="mimo-v2.6-flash",
                                                        api_key="test-key", base_url=""))
    assert result["success"]
    assert calls[0]["base_url"] == "https://api.xiaomimimo.com/v1"
    assert result["tested"]["provider"] == "mimo"


@pytest.mark.asyncio
@pytest.mark.parametrize("reload_fails", [False, True])
async def test_provider_save_hot_reload_and_failure_rollback(monkeypatch, tmp_path, reload_fails):
    import os
    from fastapi import HTTPException
    import app.api.config_api as api
    from app.services.agent_service import agent_service
    from app.llm.factory import create_llm

    monkeypatch.setattr(config.chat, "provider", "auto")
    monkeypatch.setattr(config.chat, "base_url", "")
    for field in ("provider", "name", "api_key", "base_url", "thinking_budget"):
        monkeypatch.setenv("CHAT__"+field.upper(), str(getattr(config.chat, field)))
    before = config.chat.model_dump()
    writes, models = [], []

    def save(updates, path=None):
        writes.append(dict(updates))
        return tmp_path / ".env"

    def reload():
        assert config.chat.provider == "mimo"
        if reload_fails:
            raise RuntimeError("mock reload failure")
        models.extend([create_llm(enable_thinking=False), create_llm(enable_thinking=True)])

    monkeypatch.setattr(api, "update_runtime_env", save)
    monkeypatch.setattr(agent_service, "reload_chat_models", reload)
    update = ModelConfigUpdate(provider="mimo")
    if reload_fails:
        with pytest.raises(HTTPException) as error:
            await api.update_llm_config(update)
        assert error.value.status_code == 500
        assert config.chat.model_dump() == before
        assert writes == [{"CHAT__PROVIDER": "mimo"}, {"CHAT__PROVIDER": "auto"}]
        assert os.environ["CHAT__PROVIDER"] == "auto"
    else:
        result = await api.update_llm_config(update)
        assert result["config"]["resolved_provider"] == "mimo"
        assert writes == [{"CHAT__PROVIDER": "mimo"}]
        assert [m.extra_body for m in models] == [
            {"thinking": {"type": "disabled"}}, {"thinking": {"type": "enabled"}}]
        monkeypatch.setattr(config.chat, "provider", "auto")


@pytest.mark.asyncio
async def test_invalid_custom_provider_is_rejected_before_persistence(monkeypatch):
    from fastapi import HTTPException
    import app.api.config_api as api
    writes = []
    monkeypatch.setattr(api, "update_runtime_env", lambda updates: writes.append(updates))
    with pytest.raises(HTTPException) as error:
        await api.update_llm_config(ModelConfigUpdate(provider="custom", base_url=""))
    assert error.value.status_code == 400 and writes == []
