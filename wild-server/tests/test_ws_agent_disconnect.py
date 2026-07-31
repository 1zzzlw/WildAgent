import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import WebSocketDisconnect

from app.api.ws_agent import agent_websocket, _process_user_message_safely


class WebSocketDisconnectTest(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_cancels_active_generation_after_disconnect(self):
        generation_started = asyncio.Event()
        generation_cancelled = asyncio.Event()

        async def generate_until_cancelled(_ws, _data):
            generation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                generation_cancelled.set()
                raise

        class DisconnectingWebSocket:
            def __init__(self):
                self.accept = AsyncMock()
                self.send_json = AsyncMock()
                self.receive_count = 0

            async def receive_text(self):
                self.receive_count += 1
                if self.receive_count == 1:
                    return json.dumps({
                        "type": "user_message",
                        "request_id": "req_active",
                        "message": "生成别墅",
                    })
                await generation_started.wait()
                raise WebSocketDisconnect()

        ws = DisconnectingWebSocket()
        with patch(
            "app.api.ws_agent._handle_user_message",
            side_effect=generate_until_cancelled,
        ):
            await agent_websocket(ws)

        self.assertTrue(generation_cancelled.is_set())

    async def test_disconnect_is_handled_and_heartbeat_is_reset(self):
        ws = Mock()
        ws.send_json = AsyncMock()
        heartbeat = Mock()
        heartbeat.is_processing = False

        with patch(
            "app.api.ws_agent._handle_user_message",
            AsyncMock(side_effect=WebSocketDisconnect()),
        ):
            await _process_user_message_safely(
                ws,
                {"request_id": "req_disconnect"},
                heartbeat,
            )

        self.assertFalse(heartbeat.is_processing)
        heartbeat.touch.assert_called_once_with()
        ws.send_json.assert_not_awaited()

    async def test_cancellation_is_propagated_and_heartbeat_is_reset(self):
        ws = Mock()
        heartbeat = Mock()
        heartbeat.is_processing = False

        with patch(
            "app.api.ws_agent._handle_user_message",
            AsyncMock(side_effect=asyncio.CancelledError()),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await _process_user_message_safely(
                    ws,
                    {"request_id": "req_cancelled"},
                    heartbeat,
                )

        self.assertFalse(heartbeat.is_processing)
        heartbeat.touch.assert_called_once_with()
