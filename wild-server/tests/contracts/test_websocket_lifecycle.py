"""连接关闭、后台发送失败与真正的处理异常应走各自的清理路径。"""
import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocket

from app.api.websocket import agent as ws_agent


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

        async def connect(socket):
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
