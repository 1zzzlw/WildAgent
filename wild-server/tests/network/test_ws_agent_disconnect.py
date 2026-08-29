import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import WebSocketDisconnect

from app.api.ws_agent import (
    _generation_failure_message,
    _handle_user_message,
    _prepare_server_request,
    _process_user_message_safely,
    agent_websocket,
)
from app.agent.rag_security import AccessContext
from app.extensions.presence import WebSocketConnectionRegistry
from app.agent.intent_classifier import IntentDecision
from app.services.agent_service import QueryResult
from app.services.generation_job_service import GenerationJob


def _intent_decision(intent: str) -> IntentDecision:
    return IntentDecision(
        intent=intent,
        confidence=0.9,
        target="test",
        requires_scene=intent == "edit",
        reason="test",
        source="llm",
    )


def test_server_normalizes_recent_intent_context():
    prepared = _prepare_server_request({
        "message": "继续",
        "plan_mode": False,
        "blueprint": {"geometry": {"elements": []}},
        "recent_messages": [
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
            {"role": "assistant", "content": "x" * 800},
        ],
    }, AccessContext())

    assert prepared["workflow_state"] == "scene_ready"
    assert [item["role"] for item in prepared["recent_messages"]] == [
        "user", "assistant", "user", "assistant",
    ]
    assert len(prepared["recent_messages"][-1]["content"]) == 500


class WebSocketDisconnectTest(unittest.IsolatedAsyncioTestCase):
    async def test_floor_plan_review_receives_immediate_resume_ack(self):
        class ReviewWebSocket:
            def __init__(self):
                self.accept = AsyncMock()
                self.send_json = AsyncMock()
                self.receive_count = 0

            async def receive_text(self):
                self.receive_count += 1
                if self.receive_count == 1:
                    return json.dumps({
                        "protocol_version": "1.0",
                        "type": "floor_plan_review",
                        "request_id": "req_review_ack",
                        "session_id": "session_review_ack",
                        "action": "revise",
                        "feedback": "把厨房移到北侧",
                    })
                raise WebSocketDisconnect()

        job = GenerationJob(
            request_id="req_review_ack",
            session_id="session_review_ack",
            payload={},
            status="running",
            last_event_seq=8,
        )
        ws = ReviewWebSocket()
        with (
            patch(
                "app.api.ws_agent.generation_job_service.submit_floor_plan_review",
                AsyncMock(return_value=job),
            ) as submit_review,
            patch(
                "app.api.ws_agent.generation_job_service.detach",
                AsyncMock(),
            ),
        ):
            await agent_websocket(ws)

        submit_review.assert_awaited_once()
        ack = next(
            call.args[0]
            for call in ws.send_json.await_args_list
            if call.args[0].get("type") == "generation_resumed"
        )
        self.assertEqual(ack["status"], "running")
        self.assertEqual(ack["last_event_seq"], 8)

    async def test_incompatible_protocol_version_is_rejected(self):
        class IncompatibleWebSocket:
            def __init__(self):
                self.accept = AsyncMock()
                self.send_json = AsyncMock()
                self.receive_count = 0

            async def receive_text(self):
                self.receive_count += 1
                if self.receive_count == 1:
                    return json.dumps({
                        "protocol_version": "9.9",
                        "type": "user_message",
                        "request_id": "req_version",
                        "session_id": "session_version",
                        "message": "hello",
                    })
                raise WebSocketDisconnect()

        ws = IncompatibleWebSocket()
        await agent_websocket(ws)

        error = next(
            call.args[0]
            for call in ws.send_json.await_args_list
            if call.args[0].get("code") == "unsupported_protocol_version"
        )
        self.assertEqual(error["protocol_version"], "1.0")
        self.assertEqual(error["request_id"], "req_version")

    async def test_quick_generation_is_also_detached_instead_of_cancelled(self):
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
                raise WebSocketDisconnect()

        job = GenerationJob(
            request_id="req_active",
            session_id="req_active",
            payload={},
            status="running",
        )
        ws = DisconnectingWebSocket()
        with (
            patch(
                "app.api.ws_agent.generation_job_service.start_job",
                AsyncMock(return_value=(job, True)),
            ) as start_job,
            patch(
                "app.api.ws_agent.generation_job_service.detach",
                AsyncMock(),
            ) as detach,
        ):
            await agent_websocket(ws)

        start_job.assert_awaited_once()
        detach.assert_awaited_once_with(ws)

    async def test_precision_generation_is_detached_instead_of_cancelled(self):
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
                        "request_id": "req_durable",
                        "session_id": "session_durable",
                        "message": "生成别墅",
                        "precision_mode": True,
                    })
                raise WebSocketDisconnect()

        job = GenerationJob(
            request_id="req_durable",
            session_id="session_durable",
            payload={},
            status="running",
        )
        ws = DisconnectingWebSocket()
        with (
            patch(
                "app.api.ws_agent.generation_job_service.start_job",
                AsyncMock(return_value=(job, True)),
            ) as start_job,
            patch(
                "app.api.ws_agent.generation_job_service.detach",
                AsyncMock(),
            ) as detach,
            patch(
                "app.api.ws_agent._handle_user_message",
                AsyncMock(),
            ) as direct_handler,
        ):
            await agent_websocket(ws)

        start_job.assert_awaited_once()
        detach.assert_awaited_once_with(ws)
        direct_handler.assert_not_awaited()

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


class WebSocketPresenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_connect_and_disconnect_broadcast_online_count(self):
        registry = WebSocketConnectionRegistry()
        first = Mock()
        first.send_json = AsyncMock()
        second = Mock()
        second.send_json = AsyncMock()

        await registry.connect(
            first,
            client_ip="113.96.1.8",
            region="广东省",
            display_name=" 张 工 ",
        )
        self.assertEqual(registry.online_count, 1)
        first_payload = first.send_json.await_args_list[-1].args[0]
        self.assertEqual(first_payload["online_count"], 1)
        self.assertEqual(first_payload["protocol_version"], "1.0")
        self.assertEqual(first_payload["clients"][0]["masked_ip"], "113.96.*.*")
        self.assertEqual(first_payload["clients"][0]["region"], "广东省")
        self.assertEqual(first_payload["clients"][0]["display_name"], "张 工")

        await registry.connect(
            second,
            client_ip="1.2.3.4",
            region="北京市",
            display_name="李工",
        )
        self.assertEqual(registry.online_count, 2)
        self.assertEqual(first.send_json.await_args_list[-1].args[0]["online_count"], 2)
        self.assertEqual(second.send_json.await_args_list[-1].args[0]["online_count"], 2)

        await registry.update_display_name(first, "王工")
        clients = first.send_json.await_args_list[-1].args[0]["clients"]
        self.assertEqual(clients[0]["display_name"], "王工")

        await registry.disconnect(second)
        self.assertEqual(registry.online_count, 1)
        self.assertEqual(first.send_json.await_args_list[-1].args[0]["online_count"], 1)

    async def test_disabled_extension_does_not_touch_websocket(self):
        registry = WebSocketConnectionRegistry(enabled=False)
        ws = Mock()
        ws.send_json = AsyncMock()

        await registry.connect(ws, client_ip="113.96.1.8", region="广东省")
        await registry.disconnect(ws)

        self.assertEqual(registry.online_count, 0)
        ws.send_json.assert_not_awaited()

    async def test_blank_or_long_visitor_name_is_normalized(self):
        registry = WebSocketConnectionRegistry()
        ws = Mock()
        ws.send_json = AsyncMock()

        await registry.connect(
            ws,
            client_ip="113.96.1.8",
            region="广东省",
            display_name="   ",
        )
        payload = ws.send_json.await_args_list[-1].args[0]
        self.assertEqual(payload["clients"][0]["display_name"], "访客")

        await registry.update_display_name(ws, "很长的访客名称" * 10)
        payload = ws.send_json.await_args_list[-1].args[0]
        self.assertLessEqual(len(payload["clients"][0]["display_name"]), 24)


class ThinkingModeTest(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_fast_handler_uses_shared_intent_output_contract(self):
        ws = Mock()
        ws.send_json = AsyncMock()
        captured = {}

        async def query_structured(*args, **kwargs):
            captured.update(kwargs)
            return QueryResult(text="这是实现思路说明")

        with (
            patch(
                "app.api.ws_agent.agent_service.query_structured",
                side_effect=query_structured,
            ),
            patch(
                "app.api.ws_agent.classify_intent_decision",
                AsyncMock(return_value=_intent_decision("chat")),
            ),
        ):
            await _handle_user_message(ws, {
                "request_id": "req_shared_intent",
                "session_id": "session_shared_intent",
                "message": "你生成建筑的实现思路是什么",
                "thinking_mode": False,
            })

        self.assertEqual(captured["expected_output"], "text")

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

        with (
            patch(
                "app.api.ws_agent.agent_service.query_structured",
                side_effect=query_structured,
            ),
            patch(
                "app.api.ws_agent.classify_intent_decision",
                AsyncMock(return_value=_intent_decision("chat")),
            ),
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
    def test_langgraph_preserves_skeleton_failure_reason(self):
        error = _generation_failure_message(
            {
                "skeleton": {
                    "error": "骨架生成失败：模型未返回有效的 Blueprint JSON"
                }
            },
            {"status": "failed"},
        )

        self.assertIn("模型未返回有效的 Blueprint JSON", error)

    async def test_schema_error_is_returned_as_readable_reply(self):
        ws = Mock()
        ws.send_json = AsyncMock()

        with (
            patch(
                "app.api.ws_agent.agent_service.query_structured",
                AsyncMock(return_value=QueryResult(
                    text="模型生成的无效 JSON",
                    error=(
                        "Blueprint 结构预检未通过: "
                        "floor_bad.to 必须是包含 3 个有限数字的数组"
                    ),
                )),
            ),
            patch(
                "app.api.ws_agent.classify_intent_decision",
                AsyncMock(return_value=_intent_decision("generate")),
            ),
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


class GeneratedBlueprintResponseTest(unittest.IsolatedAsyncioTestCase):
    async def test_generated_event_carries_session_and_file_reference(self):
        ws = Mock()
        ws.send_json = AsyncMock()
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "缓存回归建筑"},
            "geometry": {"elements": []},
            "materials": {},
            "behaviors": {},
        }

        with (
            patch(
                "app.api.ws_agent.agent_service.query_structured",
                AsyncMock(return_value=QueryResult(text="生成完成", blueprint=blueprint)),
            ),
            patch(
                "app.api.ws_agent.classify_intent_decision",
                AsyncMock(return_value=_intent_decision("generate")),
            ),
            patch(
                "app.services.agent_delivery.save_blueprint_file_as",
                return_value="storage/scenes/session_cache.wild",
            ),
        ):
            await _handle_user_message(ws, {
                "request_id": "req_cache",
                "session_id": "session_cache",
                "message": "生成一栋建筑",
                "thinking_mode": False,
            })

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        generated = next(msg for msg in messages if msg["type"] == "blueprint_generated")
        self.assertEqual(generated["session_id"], "session_cache")
        self.assertRegex(
            generated["filename"],
            r"^\d{4}-\d{2}-\d{2}/session_cache_缓存回归建筑\.wild$",
        )
        self.assertEqual(generated["file_url"], f"/api/scenes/{generated['filename']}")
        self.assertNotIn("blueprint", generated)
        self.assertTrue(all(msg["protocol_version"] == "1.0" for msg in messages))
