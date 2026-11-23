"""连接关闭、后台发送失败与真正的处理异常应走各自的清理路径。"""
import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocket

from app.api.websocket import agent as ws_agent
from app.api.websocket.connections import WebSocketConnectionRegistry
from app.application.generation.jobs import GenerationJobNotFound


@pytest.mark.parametrize("scenario", [
    "closed_before_receive", "closed_during_message", "processing_error", "processing_error_after_close",
])
def test_closed_connections_are_cleaned_without_masking_processing_errors(monkeypatch, scenario):
    async def run():
        outgoing, errors, cleanup = [], [], []
        incoming = iter([
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": json.dumps({"type": "ping"})},
        ])

        async def receive():
            return next(incoming)

        async def send(message):
            outgoing.append(message)

        ws = WebSocket({"type": "websocket", "path": "/ws/agent", "headers": []}, receive, send)

        class Heartbeat:
            def __init__(self, **_options): pass
            async def start(self, _callback): pass
            def touch(self): pass
            async def stop(self): cleanup.append("heartbeat")

        async def connect(socket, **_options):
            if scenario == "closed_before_receive":
                await socket.close()

        async def touch(socket):
            if scenario in {"closed_during_message", "processing_error_after_close"}:
                await socket.close()
            if scenario.startswith("processing_error"):
                raise RuntimeError("连接登记服务异常")

        async def disconnect(_socket):
            cleanup.append("presence")

        async def detach(_socket):
            cleanup.append("subscriber")

        monkeypatch.setattr(ws_agent, "WebSocketHeartbeat", Heartbeat)
        monkeypatch.setattr(ws_agent, "presence_service", SimpleNamespace(connect=connect, touch=touch, disconnect=disconnect))
        monkeypatch.setattr(ws_agent.generation_job_service, "detach", detach)
        monkeypatch.setattr(ws_agent.logger, "error", lambda message: errors.append(message))
        await ws_agent.agent_websocket(ws)
        assert cleanup == ["subscriber", "heartbeat", "presence"]
        sent = [json.loads(message["text"]) for message in outgoing if message["type"] == "websocket.send"]
        if scenario.startswith("processing_error"):
            assert len(errors) == 1 and "连接登记服务异常" in errors[0]
            if scenario == "processing_error":
                assert sent[0]["type"] == "network_error"
            else:
                assert not sent
        else:
            assert not errors
            assert not sent

    asyncio.run(run())


def test_generation_registration_failure_and_missing_job_are_reported_by_request(monkeypatch):
    async def run():
        request = {"request_id": "req_missing", "session_id": "session_example"}
        incoming = [{"type": "websocket.connect"}]
        for kind in ("user_message", "resume_generation", "stop_generation", "ping"):
            incoming.append({"type": "websocket.receive", "text": json.dumps({**request, "type": kind})})
        incoming.append({"type": "websocket.disconnect", "code": 1000})
        frames = iter(incoming)
        outgoing = []

        async def receive():
            return next(frames)

        async def send(message):
            if message["type"] == "websocket.send":
                outgoing.append(json.loads(message["text"]))

        def fail_to_create_session(*_args):
            raise RuntimeError("database unavailable while preparing the generation")

        async def missing(*_args, **_kwargs):
            return None

        async def stop(*_args, **_kwargs):
            raise GenerationJobNotFound("找不到当前会话的任务")

        monkeypatch.setattr(ws_agent, "current_user", lambda _socket: {"id": "editor", "role": "editor"})
        monkeypatch.setattr(ws_agent, "check_session", lambda *_args: None)
        monkeypatch.setattr(ws_agent.conversations, "ensure", fail_to_create_session)
        monkeypatch.setattr(ws_agent, "presence_service", WebSocketConnectionRegistry(enabled=False))
        monkeypatch.setattr(ws_agent, "generation_job_service", SimpleNamespace(
            get_job=missing, resume_or_replay=missing, stop_job=stop, detach=missing,
            has_running_job_for=lambda _socket: False,
        ))
        socket = WebSocket({"type": "websocket", "path": "/ws/agent", "headers": []}, receive, send)
        await ws_agent.agent_websocket(socket)

        assert [event.get("code") for event in outgoing] == [
            "generation_start_failed", "generation_not_found", "generation_not_found", None,
        ]
        assert all(event["request_id"] == request["request_id"] for event in outgoing[:-1])
        assert all(event["session_id"] == request["session_id"] for event in outgoing[:-1])
        assert outgoing[-1]["type"] == "pong"

    asyncio.run(run())
