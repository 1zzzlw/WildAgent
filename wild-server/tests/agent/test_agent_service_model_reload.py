"""运行时保存 Chat 配置后，AgentService 必须替换启动期模型客户端。"""

import app.services.agent_service as agent_service_module
from app.services.agent_service import AgentService


def test_reload_chat_models_replaces_normal_and_thinking_clients(monkeypatch) -> None:
    service = AgentService.__new__(AgentService)
    service.llm = "old-normal"
    service.thinking_llm = "old-thinking"
    created: list[tuple[bool, bool]] = []

    def fake_create_llm(*, enable_thinking: bool, streaming: bool = False):
        created.append((enable_thinking, streaming))
        return f"new-{enable_thinking}-{streaming}"

    monkeypatch.setattr(agent_service_module, "create_llm", fake_create_llm)

    service.reload_chat_models()

    assert service.llm == "new-False-False"
    assert service.thinking_llm == "new-True-True"
    assert created == [(False, False), (True, True)]


def test_reload_keeps_both_clients_when_thinking_client_creation_fails(monkeypatch) -> None:
    service = AgentService.__new__(AgentService)
    service.llm = "old-normal"
    service.thinking_llm = "old-thinking"

    def fake_create_llm(*, enable_thinking: bool, streaming: bool = False):
        if enable_thinking:
            raise ValueError("invalid model config")
        return "new-normal"

    monkeypatch.setattr(agent_service_module, "create_llm", fake_create_llm)
    import pytest

    with pytest.raises(ValueError, match="invalid model config"):
        service.reload_chat_models()
    assert service.llm == "old-normal"
    assert service.thinking_llm == "old-thinking"
