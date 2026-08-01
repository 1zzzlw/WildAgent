import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import WebSocketDisconnect

from app.api.ws_agent import (
    _handle_user_message,
    _process_user_message_safely,
    agent_websocket,
)
from app.services.agent_service import QueryResult


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


class ThinkingModeTest(unittest.IsolatedAsyncioTestCase):
    async def _run_request(self, thinking_mode, reasoning_delta=None):
        ws = Mock()
        ws.send_json = AsyncMock()
        data = {
            "type": "user_message",
            "request_id": "req_thinking",
            "session_id": "session_thinking",
            "scene_revision": 0,
            "message": "介绍一下当前场景",
            "thinking_mode": thinking_mode,
        }

        async def query_structured(*args, **kwargs):
            callback = kwargs.get("on_reasoning_delta")
            if reasoning_delta and callback:
                await callback(reasoning_delta)
            return QueryResult(text="处理完成")

        with patch(
            "app.api.ws_agent.agent_service.query_structured",
            side_effect=query_structured,
        ):
            await _handle_user_message(ws, data)

        return [call.args[0] for call in ws.send_json.await_args_list]

    async def test_disabled_mode_sends_no_thinking_logs(self):
        messages = await self._run_request(False)

        self.assertFalse(any(msg["type"].startswith("thinking_") for msg in messages))
    async def test_enabled_mode_streams_real_reasoning_content(self):
        messages = await self._run_request(True, "模型实际返回的思考")
        deltas = [msg for msg in messages if msg["type"] == "thinking_delta"]
        statuses = [msg for msg in messages if msg["type"] == "thinking_status"]

        self.assertEqual([msg["delta"] for msg in deltas], ["模型实际返回的思考"])
        self.assertEqual([msg["status"] for msg in statuses], ["thinking", "completed"])

    async def test_enabled_mode_reports_missing_reasoning_content(self):
        messages = await self._run_request(True)
        statuses = [msg for msg in messages if msg["type"] == "thinking_status"]

        self.assertEqual([msg["status"] for msg in statuses], ["thinking", "unsupported"])
        self.assertFalse(any(msg["type"] == "thinking_delta" for msg in messages))

    async def test_only_literal_true_enables_thinking_mode(self):
        messages = await self._run_request("true")

        self.assertFalse(any(msg["type"].startswith("thinking_") for msg in messages))


class InvalidBlueprintResponseTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_error_is_returned_as_readable_reply(self):
        ws = Mock()
        ws.send_json = AsyncMock()

        with patch(
            "app.api.ws_agent.agent_service.query_structured",
            AsyncMock(return_value=QueryResult(
                text="模型生成的无效 JSON",
                error=(
                    "Blueprint 结构预检未通过: "
                    "floor_bad.to 必须是包含 3 个有限数字的数组"
                ),
            )),
        ):
            await _handle_user_message(ws, {
                "request_id": "req_invalid_coordinate",
                "session_id": "session_invalid_coordinate",
                "message": "生成一座别墅",
                "thinking_mode": False,
            })

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        replies = [msg for msg in messages if msg["type"] == "agent_reply"]

        self.assertEqual(len(replies), 1)
        self.assertIn("生成结果未通过结构预检", replies[0]["content"])
        self.assertIn("floor_bad.to", replies[0]["content"])
