import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import WebSocketDisconnect

from app.api.ws_agent import (
    _generation_failure_message,
    _handle_user_message,
    _prepare_server_request,
    _process_user_message_safely,
    agent_websocket,
)
from app.rag.security import AccessContext
from app.extensions.presence import WebSocketConnectionRegistry
from app.services.generation_job_service import GenerationJob, GenerationJobService


async def _run_graph_request(ws, data, outputs, reasoning_delta=None, reasoning_node="patch"):
    captured = {}

    class Graph:
        async def astream_events(self, state, **_kwargs):
            captured.update(state)
            if reasoning_delta:
                from app.agent.runtime import get_reasoning_callback

                await get_reasoning_callback()(reasoning_node, reasoning_delta)
            for node, output in outputs.items():
                yield {"event": "on_chain_end", "name": node, "data": {"output": output}}

        async def aget_state(self, _config):
            values = {}
            for output in outputs.values():
                values.update(output)
            return SimpleNamespace(next=(), values=values)

    with (
        patch("app.agent.graph.get_graph", return_value=Graph()),
        patch("app.api.ws_agent.generation_job_service.initialize", AsyncMock()),
        patch("app.api.ws_agent.generation_job_service._checkpointer", object()),
    ):
        await _handle_user_message(ws, data)
    return captured


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
    async def test_running_durable_job_is_visible_to_heartbeat_probe(self):
        service = GenerationJobService()
        subscriber = object()
        task = Mock()
        task.done.return_value = False
        service._subscribers["req_running"] = {id(subscriber): subscriber}
        service._active_tasks["req_running"] = task

        self.assertTrue(service.has_running_job_for(subscriber))
        task.done.return_value = True
        self.assertFalse(service.has_running_job_for(subscriber))

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

    async def test_generation_is_detached_instead_of_cancelled(self):
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
    async def _run_request(self, detail_level, reasoning_delta=None, thinking_mode=None, reasoning_node="patch"):
        ws = Mock()
        ws.send_json = AsyncMock()
        data = {
            "request_id": "req_thinking",
            "session_id": "session_thinking",
            "message": "修改墙厚",
            "detail_level": detail_level,
        }
        if thinking_mode is not None:
            data["thinking_mode"] = thinking_mode
        captured = await _run_graph_request(ws, data, {
            "classifier": {"intent": "edit", "thinking_mode": thinking_mode is not False},
            "patch": {
                "scene_patch": {
                    "operations": [{"op": "update_element", "id": "wall", "changes": {"thickness": 0.3}}],
                    "summary": "修改墙厚",
                },
                "status": "complete",
            },
        }, reasoning_delta, reasoning_node)
        self.assertEqual(captured["thinking_mode"], thinking_mode is not False)
        self.assertEqual(captured["detail_level"], detail_level)
        return [call.args[0] for call in ws.send_json.await_args_list]

    async def test_low_detail_still_collects_non_plan_node_thinking(self):
        messages = await self._run_request("minimal", "模型实际返回的思考")
        deltas = [msg for msg in messages if msg["type"] == "thinking_delta"]
        self.assertEqual([msg["delta"] for msg in deltas], ["模型实际返回的思考"])
        self.assertTrue(any(msg["type"] == "thinking_status" for msg in messages))
        proposal = next(msg for msg in messages if msg["type"] == "patch_proposal")
        self.assertTrue(proposal["patch"]["requires_confirmation"])

    async def test_enabled_mode_streams_real_reasoning_content(self):
        messages = await self._run_request("simple", "模型实际返回的思考")
        deltas = [msg for msg in messages if msg["type"] == "thinking_delta"]
        statuses = [msg for msg in messages if msg["type"] == "thinking_status"]
        self.assertEqual([msg["delta"] for msg in deltas], ["模型实际返回的思考"])
        self.assertEqual([msg["status"] for msg in statuses], ["thinking", "completed"])

    async def test_enabled_mode_does_not_fabricate_reasoning(self):
        messages = await self._run_request("detailed")
        self.assertFalse(any(msg["type"] == "thinking_delta" for msg in messages))
        self.assertTrue(any(msg["type"] == "patch_proposal" for msg in messages))

    async def test_standard_level_collects_thinking_without_extra_switch(self):
        messages = await self._run_request("standard")
        self.assertTrue(any(msg["type"] == "thinking_status" for msg in messages))

    async def test_explicit_off_reaches_graph_without_dropping_item_reasoning(self):
        messages = await self._run_request("simple", "构件条目实际思考", False, "plan:generate_1")
        deltas = [msg for msg in messages if msg["type"] == "thinking_delta"]
        self.assertEqual([msg["delta"] for msg in deltas], ["构件条目实际思考"])
        self.assertEqual(deltas[0]["node"], "plan:generate_1")


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

    async def test_graph_validation_failure_is_returned_with_original_reason(self):
        ws = Mock()
        ws.send_json = AsyncMock()
        error = "Blueprint 结构预检未通过: floor_bad.to 必须是包含 3 个有限数字的数组"
        await _run_graph_request(ws, {
            "request_id": "req_invalid_coordinate",
            "session_id": "session_invalid_coordinate",
            "message": "生成一座别墅",
            "detail_level": "minimal",
        }, {
            "classifier": {"intent": "generate"},
            "skeleton": {"error": error, "status": "failed"},
        })
        messages = [call.args[0] for call in ws.send_json.await_args_list]
        errors = [msg for msg in messages if msg["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("floor_bad.to", errors[0]["error"])


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

        from app.agent.validation.diagnostics import VALIDATOR_VERSION, blueprint_fingerprint
        evaluation = {
            "snapshot": {
                "blueprint_fingerprint": blueprint_fingerprint(blueprint),
                "validator_version": VALIDATOR_VERSION,
                "results": [], "error_count": 0, "warning_count": 0, "status": "complete",
            },
            "fulfillment": None,
        }
        with (
            patch("app.agent.validation.candidate.evaluate_candidate", return_value=evaluation),
            patch("app.services.agent_delivery.save_blueprint_file_as", return_value="storage/scenes/session_cache.wild"),
        ):
            await _run_graph_request(ws, {
                "request_id": "req_cache",
                "session_id": "session_cache",
                "message": "生成一栋建筑",
                "detail_level": "minimal",
            }, {
                "classifier": {"intent": "generate"},
                "final_validate": {"merged_blueprint": blueprint, "status": "complete"},
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
