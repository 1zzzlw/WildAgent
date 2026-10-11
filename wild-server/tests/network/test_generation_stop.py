"""用户停止必须终止后台执行、保存已有记录，并且不能自动恢复。"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect

from app.api import ws_agent
from app.llm.invocation import invoke_llm, stream_llm
from app.rag.trace import trace_file_path
from app.services.generation_job_service import GenerationJobService, GenerationPaused
from config import config
from tests.network.test_generation_job_service import RecordingSubscriber


@pytest.mark.asyncio
async def test_stop_cancels_parallel_calls_flushes_partial_trace_and_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(config.rag.trace, "enabled", True)
    monkeypatch.setattr(config.rag.trace, "root_dir", str(tmp_path / "traces"))
    started = [asyncio.Event() for _ in range(3)]
    cancelled = []
    other_started, release_other = asyncio.Event(), asyncio.Event()

    class Model:
        def __init__(self, index):
            self.index = index

        async def astream(self, _messages):
            yield SimpleNamespace(content=f"partial-{self.index}", additional_kwargs={"reasoning_content": "returned reasoning"})
            started[self.index].set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(self.index)

    async def graph_handler(sink, payload, *, resume=False):
        if payload["request_id"] == "req_other":
            other_started.set()
            await release_other.wait()
            return
        await sink.send_json({"type": "agent_step", "request_id": payload["request_id"], "session_id": payload["session_id"], "node": "execute"})
        await asyncio.gather(*(stream_llm(Model(i), []) for i in range(3)))

    monkeypatch.setattr(ws_agent, "_handle_with_langgraph", graph_handler)
    service = GenerationJobService(tmp_path / "checkpoints.sqlite3")
    await service.startup(ws_agent._run_persistent_langgraph)
    subscriber = RecordingSubscriber()
    try:
        await service.start_job({"request_id": "req_stop", "session_id": "session_stop", "message": "生成别墅"}, subscriber)
        await service.start_job({"request_id": "req_other", "session_id": "session_other", "message": "另一个会话"}, subscriber)
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started), other_started.wait()), 3)
        job = await asyncio.wait_for(service.stop_job(subscriber, request_id="req_stop", session_id="session_stop"), 3)
        assert job.status == "stopped"
        assert sorted(cancelled) == [0, 1, 2]
        assert (await service.get_job("req_other")).status == "running"
        events = await service.events_after("req_stop", 0)
        assert [e["type"] for e in events] == ["agent_step", "generation_stopped"]
        trace = json.loads(trace_file_path("session_stop", "req_stop").read_text(encoding="utf-8"))
        assert trace["status"] == "stopped"
        assert len(trace["llm_calls"]) == 3
        assert {c["response_content"] for c in trace["llm_calls"]} == {f"partial-{i}" for i in range(3)}
        assert all(c["reasoning_content"] == "returned reasoning" for c in trace["llm_calls"])
        assert all(c["error_type"] == "CancelledError" for c in trace["llm_calls"])
        await service.publish_event("req_stop", {"type": "agent_reply", "content": "late reply"})
        assert (await service.get_job("req_stop")).status == "stopped"
        assert len(await service.events_after("req_stop", 0)) == 2
        release_other.set()
        await asyncio.gather(*service._active_tasks.values(), return_exceptions=True)
    finally:
        await service.shutdown()
    recovered = GenerationJobService(service.database_path)
    runner = AsyncMock()
    await recovered.startup(runner)
    try:
        runner.assert_not_called()
        replay = RecordingSubscriber()
        await recovered.resume_or_replay(replay, request_id="req_stop", session_id="session_stop")
        assert replay.messages[0]["status"] == "stopped"
        assert replay.messages[-1]["type"] == "generation_stopped"
    finally:
        await recovered.shutdown()


@pytest.mark.asyncio
async def test_stop_waiting_review_is_idempotent_and_releases_the_session(tmp_path):
    service = GenerationJobService(tmp_path / "checkpoints.sqlite3")

    async def runner(_sink, _payload, _resume):
        raise GenerationPaused()

    await service.startup(runner)
    subscriber = RecordingSubscriber()
    try:
        await service.start_job({"request_id": "req_review", "session_id": "session_review"}, subscriber)
        await asyncio.gather(*service._active_tasks.values())
        assert (await service.get_job("req_review")).status == "waiting_review"
        for _ in range(2):
            job = await service.stop_job(subscriber, request_id="req_review", session_id="session_review")
            assert job.status == "stopped"
        assert len(await service.events_after("req_review", 0)) == 1
        await service.mark_waiting_for_review("req_review", "design_document")
        assert (await service.get_job("req_review")).status == "stopped"
        assert await service.get_active_job_for_session("session_review") is None
        _, created = await service.start_job({"request_id": "req_new", "session_id": "session_review"}, subscriber)
        assert created
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_stop_rejects_a_different_session_and_keeps_completed_results(tmp_path):
    service = GenerationJobService(tmp_path / "checkpoints.sqlite3")
    await service.startup(AsyncMock())
    subscriber = RecordingSubscriber()
    try:
        await service.start_job({"request_id": "req_done", "session_id": "session_done"}, subscriber)
        await asyncio.gather(*service._active_tasks.values())
        with pytest.raises(ValueError):
            await service.stop_job(subscriber, request_id="req_done", session_id="session_wrong")
        job = await service.stop_job(subscriber, request_id="req_done", session_id="session_done")
        assert job.status == "completed"
        assert not await service.events_after("req_done", 0)
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_websocket_routes_stop_to_the_target_request():
    class Socket:
        accept = AsyncMock()
        send_json = AsyncMock()
        count = 0

        async def receive_text(self):
            self.count += 1
            if self.count == 1:
                return json.dumps({"type": "stop_generation", "request_id": "req_stop", "session_id": "session_stop"})
            raise WebSocketDisconnect()

    ws = Socket()
    with patch.object(ws_agent.generation_job_service, "stop_job", AsyncMock(), create=True) as stop:
        await ws_agent.agent_websocket(ws)
    stop.assert_awaited_once_with(ws, request_id="req_stop", session_id="session_stop")


@pytest.mark.asyncio
async def test_stop_retains_the_last_completed_langgraph_checkpoint(tmp_path):
    from langgraph.graph import END, START, StateGraph

    service = GenerationJobService(tmp_path / "checkpoints.sqlite3")
    reached = asyncio.Event()

    async def waiting(_state):
        reached.set()
        await asyncio.Event().wait()

    builder = StateGraph(dict)
    builder.add_node("prepared", lambda state: {**state, "prepared": True})
    builder.add_node("waiting", waiting)
    builder.add_edge(START, "prepared")
    builder.add_edge("prepared", "waiting")
    builder.add_edge("waiting", END)
    graph_config = {"configurable": {"thread_id": "generation:req_checkpoint"}}

    async def runner(_sink, _payload, _resume):
        await graph.ainvoke({"message": "原始需求"}, graph_config)

    await service.startup(runner)
    graph = builder.compile(checkpointer=service.checkpointer)
    subscriber = RecordingSubscriber()
    try:
        await service.start_job({"request_id": "req_checkpoint", "session_id": "session_checkpoint"}, subscriber)
        await asyncio.wait_for(reached.wait(), 3)
        await service.stop_job(subscriber, request_id="req_checkpoint", session_id="session_checkpoint")
        snapshot = await graph.aget_state(graph_config)
        assert snapshot.values == {"message": "原始需求", "prepared": True}
        assert snapshot.next == ("waiting",)
        assert (await service.get_job("req_checkpoint")).status == "stopped"
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_stopped_conversation_is_written_to_disk_and_survives_server_restart(tmp_path, monkeypatch):
    from app.api import sessions

    monkeypatch.setattr(sessions, "SESSIONS_DIR", tmp_path)
    turn = {
        "request_id": "req_saved", "status": "stopped", "completed_at": 123,
        "steps": [{"node": "architecture", "status": "stopped", "reasoning": "已有模型输出"}],
    }
    request = SimpleNamespace(json=AsyncMock(return_value={"turns": [turn]}))
    await sessions.replace_turns("session_saved", request)
    stored = json.loads((tmp_path / "session_saved.json").read_text(encoding="utf-8"))
    assert stored["turns"] == [turn]
    monkeypatch.setattr(sessions, "SERVER_INSTANCE_ID", "restarted-server")
    restored = await sessions.get_turns("session_saved")
    assert json.loads(restored.body) == [turn]


@pytest.mark.asyncio
async def test_stop_during_graph_event_delivery_closes_parallel_model_streams(tmp_path, monkeypatch):
    from langgraph.graph import END, START, StateGraph

    monkeypatch.setattr(config.rag.trace, "enabled", True)
    monkeypatch.setattr(config.rag.trace, "root_dir", str(tmp_path / "traces"))
    service = GenerationJobService(tmp_path / "checkpoints.sqlite3")
    monkeypatch.setattr(ws_agent, "generation_job_service", service)
    started = [asyncio.Event() for _ in range(3)]
    blocked = asyncio.Event()
    closed = []

    class Model:
        def __init__(self, index):
            self.index = index

        async def astream(self, _messages):
            try:
                yield SimpleNamespace(content=f"partial-{self.index}", additional_kwargs={})
                started[self.index].set()
                await asyncio.Event().wait()
            finally:
                closed.append(self.index)

    async def execute(_state):
        await asyncio.gather(*(stream_llm(Model(i), []) for i in range(3)))

    builder = StateGraph(dict)
    builder.add_node("execute", execute)
    builder.add_edge(START, "execute")
    builder.add_edge("execute", END)
    monkeypatch.setattr("app.agent.graph.get_graph", lambda **kwargs: builder.compile(checkpointer=kwargs["checkpointer"]))

    class Subscriber:
        async def send_json(self, payload):
            if payload.get("type") == "agent_step" and payload.get("node") == "execute":
                await asyncio.gather(*(event.wait() for event in started))
                blocked.set()
                await asyncio.Event().wait()

    task = asyncio.create_task(ws_agent._run_persistent_langgraph(
        Subscriber(), {"request_id": "req_event", "session_id": "session_event", "message": "生成别墅"}, False,
    ))
    try:
        await asyncio.wait_for(blocked.wait(), 3)
        task.cancel("user_stop")
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sorted(closed) == [0, 1, 2]
        trace = json.loads(trace_file_path("session_event", "req_event").read_text(encoding="utf-8"))
        assert trace["status"] == "stopped"
        assert {call["response_content"] for call in trace["llm_calls"]} == {f"partial-{i}" for i in range(3)}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["invoke", "stream_callback"])
async def test_cancelled_model_calls_are_logged_once_and_streams_are_closed(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(config.rag.trace, "enabled", True)
    monkeypatch.setattr(config.rag.trace, "root_dir", str(tmp_path))

    class Model:
        calls = 0
        closed = False

        async def ainvoke(self, _messages):
            self.calls += 1
            raise asyncio.CancelledError("user_stop")

        async def astream(self, _messages):
            self.calls += 1
            try:
                yield SimpleNamespace(content="received content", additional_kwargs={"reasoning_content": "received reasoning"})
                await asyncio.Event().wait()
            finally:
                self.closed = True

    model = Model()

    async def callback(_delta):
        raise asyncio.CancelledError("user_stop")

    async def handler(_sink, _payload, *, resume=False):
        if mode == "invoke":
            await invoke_llm(model, [])
        else:
            await stream_llm(model, [], on_reasoning_delta=callback)

    monkeypatch.setattr(ws_agent, "_handle_with_langgraph", handler)
    with pytest.raises(asyncio.CancelledError):
        await ws_agent._run_persistent_langgraph(RecordingSubscriber(), {"request_id": "req_model", "session_id": "session_model"}, False)
    trace = json.loads(trace_file_path("session_model", "req_model").read_text(encoding="utf-8"))
    assert trace["status"] == "stopped"
    assert model.calls == len(trace["llm_calls"]) == 1
    assert trace["llm_calls"][0]["error_type"] == "CancelledError"
    if mode == "stream_callback":
        assert trace["llm_calls"][0]["response_content"] == "received content"
        assert trace["llm_calls"][0]["reasoning_content"] == "received reasoning"
        assert model.closed
