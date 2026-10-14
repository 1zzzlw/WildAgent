"""模型返回的原始输出与思考沿现有请求 trace 落盘。"""
import json
import asyncio
from types import SimpleNamespace

import pytest

from app.llm import invocation
from app.rag.trace import llm_trace_scope, persist_rag_trace, rag_trace_scope, record_rag_llm_call, trace_file_path
from config import config


@pytest.fixture
def local_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(config.rag.trace, "enabled", True)
    monkeypatch.setattr(config.rag.trace, "root_dir", str(tmp_path))
    return tmp_path


def complete(coroutine):
    return asyncio.run(coroutine)


@pytest.mark.parametrize("mode", ["invoke", "stream"])
def test_actual_invocation_persists_full_response_and_reasoning(local_trace, mode):
    reasoning = "模型实际返回的设计说明。" * 1500
    content = json.dumps({"roof": {"type": "自由曲面"}}, ensure_ascii=False)

    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=content, additional_kwargs={"reasoning_content": reasoning},
                                   response_metadata={}, usage_metadata={})

        async def astream(self, messages):
            yield SimpleNamespace(content="", additional_kwargs={"reasoning_content": reasoning[:5000]})
            yield SimpleNamespace(content=content, additional_kwargs={"reasoning_content": reasoning[5000:]})

    with rag_trace_scope("req_payload", session_id="session_payload"):
        result = complete(getattr(invocation, f"{mode}_llm")(Model(), [{"role": "user", "content": "设计别墅"}]))
    path = trace_file_path("session_payload", "req_payload")
    assert path.is_relative_to(local_trace)
    trace = json.loads(path.read_text(encoding="utf-8"))
    call = trace["llm_calls"][0]
    assert len(trace["llm_calls"]) == 1
    assert call["reasoning_content"] == reasoning == result.reasoning
    assert call["response_content"] == content == result.content
    assert call["mode"] == mode
    assert call["request_id"] == "req_payload"
    assert call["call_id"] == result.call_id
    assert trace["llm_inputs"][call["messages_ref"]]["messages"] == [
        {"role": "user", "content": "设计别墅"}]
    assert call["input_chars"] > 0 and call["output_chars"] == len(content)
    assert call["finish_reason"] is None
    assert call["execution_id"] == trace["executions"][0]["id"]
    runtime = trace["executions"][0]["runtime"]
    assert runtime["server_instance_id"] == call["server_instance_id"]
    assert len(runtime["source_sha256"]) == len(runtime["knowledge_sha256"]) == 64


def test_stream_failure_preserves_received_partial_output(local_trace):
    class Model:
        async def astream(self, messages):
            yield SimpleNamespace(content='{"roof":', additional_kwargs={"reasoning_content": "已返回的部分思考"})
            raise RuntimeError("供应商中断流")

    with pytest.raises(RuntimeError, match="供应商中断流"):
        with rag_trace_scope("req_partial", session_id="session_payload"):
            complete(invocation.stream_llm(Model(), []))
    trace = json.loads(trace_file_path("session_payload", "req_partial").read_text(encoding="utf-8"))
    assert trace["status"] == "error"
    assert trace["llm_calls"][0]["error_type"] == "RuntimeError"
    assert trace["llm_calls"][0]["response_content"] == '{"roof":'
    assert trace["llm_calls"][0]["reasoning_content"] == "已返回的部分思考"


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0.08, 0])
async def test_stream_timeout_does_not_cut_off_continuous_model_output(local_trace, monkeypatch, timeout):
    monkeypatch.setattr(config.chat, "timeout", timeout)
    closed, received = [], []
    class Model:
        async def astream(self, messages):
            try:
                for i in range(8):
                    await asyncio.sleep(0.02)
                    yield SimpleNamespace(content=str(i), additional_kwargs={"reasoning_content": "思考"})
            finally:
                closed.append(True)
    async def emit(delta):
        received.append(delta)
    with rag_trace_scope("req_deadline", session_id="session_deadline"):
        result = await invocation.stream_llm(Model(), [], on_reasoning_delta=emit)
    assert closed == [True] and len(received) == 8
    trace = json.loads(trace_file_path("session_deadline", "req_deadline").read_text(encoding="utf-8"))
    call = trace["llm_calls"][0]
    assert call["error_type"] is None and call["response_content"] == result.content == "01234567"
    assert call["elapsed_ms"] > 80
    assert call["reasoning_content"] == "".join(received)


@pytest.mark.asyncio
async def test_empty_stream_chunks_do_not_extend_response_timeout(local_trace, monkeypatch):
    monkeypatch.setattr(config.chat, "timeout", 0.08)
    closed = []
    class Model:
        async def astream(self, messages):
            try:
                for _ in range(8):
                    await asyncio.sleep(0.02)
                    yield SimpleNamespace(content="", additional_kwargs={})
            finally:
                closed.append(True)
    with pytest.raises(TimeoutError):
        with rag_trace_scope("req_empty", session_id="session_empty"):
            await invocation.stream_llm(Model(), [])
    assert closed == [True]
    trace = json.loads(trace_file_path("session_empty", "req_empty").read_text(encoding="utf-8"))
    assert trace["llm_calls"][0]["error_type"] == "TimeoutError"


@pytest.mark.asyncio
@pytest.mark.parametrize("send_partial", [False, True])
async def test_stream_idle_timeout_preserves_partial_output_and_closes_stream(local_trace, monkeypatch, send_partial):
    monkeypatch.setattr(config.chat, "timeout", 0.03)
    closed = []
    class Model:
        async def astream(self, messages):
            try:
                if send_partial:
                    yield SimpleNamespace(content='{"roof":', additional_kwargs={"reasoning_content": "已返回"})
                await asyncio.Event().wait()
            finally:
                closed.append(True)
    with pytest.raises(TimeoutError):
        with rag_trace_scope("req_idle", session_id="session_idle"):
            await invocation.stream_llm(Model(), [])
    assert closed == [True]
    trace = json.loads(trace_file_path("session_idle", "req_idle").read_text(encoding="utf-8"))
    call = trace["llm_calls"][0]
    assert call["error_type"] == "TimeoutError"
    assert call["response_content"] == ('{"roof":' if send_partial else "")
    assert call["reasoning_content"] == ("已返回" if send_partial else "")


@pytest.mark.asyncio
async def test_stream_cancellation_still_closes_and_records_received_output(local_trace):
    closed, received = [], asyncio.Event()
    class Model:
        async def astream(self, messages):
            try:
                yield SimpleNamespace(content="", additional_kwargs={"reasoning_content": "已返回"})
                await asyncio.Event().wait()
            finally:
                closed.append(True)
    async def emit(_delta):
        received.set()
    with rag_trace_scope("req_cancel", session_id="session_cancel"):
        task = asyncio.create_task(invocation.stream_llm(Model(), [], on_reasoning_delta=emit))
        await received.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert closed == [True]
    trace = json.loads(trace_file_path("session_cancel", "req_cancel").read_text(encoding="utf-8"))
    assert trace["llm_calls"][0]["error_type"] == "CancelledError"
    assert trace["llm_calls"][0]["reasoning_content"] == "已返回"


def test_payload_recording_without_request_scope_is_a_noop():
    assert record_rag_llm_call("invoke", 1, None,
        response_content="模型输出", reasoning_content="模型思考") is False


def test_review_resume_preserves_previous_execution_and_does_not_duplicate_calls(local_trace):
    with rag_trace_scope("req_resume", session_id="session_resume"):
        record_rag_llm_call("invoke", 10, {"input": 2, "output": 3, "total": 5},
                            response_content="图纸回复", reasoning_content="供应商返回的说明")
    path = trace_file_path("session_resume", "req_resume")
    first = json.loads(path.read_text(encoding="utf-8"))
    with rag_trace_scope("req_resume", session_id="session_resume") as resumed:
        record_rag_llm_call("invoke", 20, {"input": 4, "output": 6, "total": 10},
                            response_content="构件回复")
        persist_rag_trace(resumed)
        persist_rag_trace(resumed)
    final = json.loads(path.read_text(encoding="utf-8"))
    assert final["started_at"] == first["started_at"]
    assert [c["response_content"] for c in final["llm_calls"]] == ["图纸回复", "构件回复"]
    assert final["summary"]["llm_calls"] == 2
    assert final["summary"]["token_usage"]["total"] == 15
    assert len(final["executions"]) == 2


def test_resume_can_append_to_the_previous_trace_format(local_trace):
    with rag_trace_scope("req_legacy", session_id="session_resume"):
        record_rag_llm_call("invoke", 10, None, response_content="此前回复")
    path = trace_file_path("session_resume", "req_legacy")
    previous = json.loads(path.read_text(encoding="utf-8"))
    previous.pop("executions")
    path.write_text(json.dumps(previous), encoding="utf-8")
    with rag_trace_scope("req_legacy", session_id="session_resume"):
        record_rag_llm_call("invoke", 20, None, response_content="恢复回复")
    final = json.loads(path.read_text(encoding="utf-8"))
    assert [c["response_content"] for c in final["llm_calls"]] == ["此前回复", "恢复回复"]
    assert final["executions"][0]["id"] == "legacy"


def test_resume_does_not_merge_a_different_users_trace(local_trace):
    from app.rag.security import AccessContext
    with rag_trace_scope("req_shared", session_id="session_resume", access_context=AccessContext(user_id="alice")):
        record_rag_llm_call("invoke", 10, None, response_content="其他用户回复")
    with rag_trace_scope("req_shared", session_id="session_resume", access_context=AccessContext(user_id="bob")):
        record_rag_llm_call("invoke", 20, None, response_content="当前用户回复")
    final = json.loads(trace_file_path("session_resume", "req_shared").read_text(encoding="utf-8"))
    assert [c["response_content"] for c in final["llm_calls"]] == ["当前用户回复"]


@pytest.mark.asyncio
async def test_parallel_calls_keep_task_context_and_deduplicate_input(local_trace):
    class Model:
        model_name = "test-model"
        temperature = 0.25

        async def ainvoke(self, messages):
            await asyncio.sleep(0)
            return SimpleNamespace(content="{}", response_metadata={"finish_reason": "stop"})

    messages = [{"role": "system", "content": "相同输入"}]
    async def call(item_id, stage):
        with llm_trace_scope(item_id=item_id, stage=stage, design_hash="approved-hash",
                             candidate_fingerprint="base-hash", marker_ids=[item_id + "-marker"],
                             batch_load={"marker_count": 1}, injected_chunk_ids=[item_id + "-knowledge"]):
            return await invocation.invoke_llm(Model(), messages)

    with rag_trace_scope("req_parallel", session_id="session_parallel"):
        await asyncio.gather(call("windows", "implement"), call("roof", "repair_1"))
        await invocation.invoke_llm(Model(), messages)
    trace = json.loads(trace_file_path("session_parallel", "req_parallel").read_text(encoding="utf-8"))
    calls = trace["llm_calls"]
    assert len(trace["llm_inputs"]) == 1
    assert len({call["call_id"] for call in calls}) == 3
    for call in calls[:2]:
        assert call["design_hash"] == "approved-hash"
        assert call["candidate_fingerprint"] == "base-hash"
        assert call["marker_ids"] == [call["item_id"] + "-marker"]
        assert call["batch_load"] == {"marker_count": 1}
        assert call["injected_chunk_ids"] == [call["item_id"] + "-knowledge"]
        assert call["stage"] == {"windows": "implement", "roof": "repair_1"}[call["item_id"]]
        assert call["model_config"]["model_name"] == "test-model"
        assert call["finish_reason"] == "stop"
    assert "item_id" not in calls[2] and "stage" not in calls[2]
    assert trace["summary"]["llm_input_chars"] == sum(c["input_chars"] for c in calls)


@pytest.mark.asyncio
async def test_success_after_transport_retry_records_true_attempt_count(local_trace, monkeypatch):
    attempts = []
    class Model:
        max_retries = 2

        async def ainvoke(self, messages):
            attempts.append(1)
            if len(attempts) < 3:
                raise TimeoutError("transport timeout")
            return SimpleNamespace(content="{}", response_metadata={}, usage_metadata={})

    async def no_sleep(_attempt):
        pass
    monkeypatch.setattr(invocation, "_sleep_with_jitter", no_sleep)
    with rag_trace_scope("req_retry", session_id="session_retry"):
        result = await invocation.invoke_llm(Model(), [])
    trace = json.loads(trace_file_path("session_retry", "req_retry").read_text(encoding="utf-8"))
    call = trace["llm_calls"][0]
    assert result.retry_count == call["retry_count"] == trace["summary"]["llm_retry_count"] == 2
    assert [row["outcome"] for row in call["transport_attempts"]] == ["failed", "failed", "succeeded"]
    assert trace["summary"]["llm_transport_attempts"] == len(attempts) == 3
    assert call["sdk_retry_count"] is None
    assert call["model_config"]["max_retries"] == 2


@pytest.mark.asyncio
async def test_cancellation_during_backoff_does_not_count_an_unstarted_retry(local_trace, monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            raise TimeoutError("transport timeout")
    async def cancel_sleep(_attempt):
        raise asyncio.CancelledError()
    monkeypatch.setattr(invocation, "_sleep_with_jitter", cancel_sleep)
    with pytest.raises(asyncio.CancelledError):
        with rag_trace_scope("req_backoff", session_id="session_backoff"):
            await invocation.invoke_llm(Model(), [])
    trace = json.loads(trace_file_path("session_backoff", "req_backoff").read_text(encoding="utf-8"))
    call = trace["llm_calls"][0]
    assert call["retry_count"] == 0 and len(call["transport_attempts"]) == 1
    assert call["error_type"] == "CancelledError"


@pytest.mark.asyncio
async def test_authentication_is_excluded_from_inputs_model_config_and_console(local_trace, monkeypatch):
    logs = []
    monkeypatch.setattr("app.rag.trace.logger.info", lambda *args: logs.append(str(args)))
    class Model:
        model_name = "safe-model"
        openai_api_key = "never-store-model-key"
        openai_api_base = "https://url-user:url-secret@example.com/v1?api_key=query-secret#fragment"
        default_headers = {"Authorization": "Bearer header-secret"}
        extra_body = {"thinking": {"type": "enabled", "api_key": "nested-secret"},
                      "api_key": "body-secret"}

        async def ainvoke(self, messages):
            return SimpleNamespace(content="{}", response_metadata={})

    messages = [{"role": "user", "content": "Authorization: Bearer prompt-secret",
                 "api_key": "message-secret"}]
    with rag_trace_scope("req_secure", session_id="session_secure"):
        await invocation.invoke_llm(Model(), messages)
    data = trace_file_path("session_secure", "req_secure").read_text(encoding="utf-8")
    for secret in ("never-store-model-key", "url-secret", "query-secret", "header-secret",
                   "nested-secret", "body-secret", "prompt-secret", "message-secret"):
        assert secret not in data and secret not in "".join(logs)
    trace = json.loads(data)
    call = trace["llm_calls"][0]
    assert call["model_config"]["base_url"] == "https://example.com/v1"
    assert call["model_config"]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "llm_inputs" not in "".join(logs)
