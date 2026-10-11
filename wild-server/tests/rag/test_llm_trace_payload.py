"""模型返回的原始输出与思考沿现有请求 trace 落盘。"""
import json
import asyncio
from types import SimpleNamespace

import pytest

from app.llm import invocation
from app.rag.trace import persist_rag_trace, rag_trace_scope, record_rag_llm_call, trace_file_path
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
async def test_stream_timeout_covers_continuous_chunks_and_preserves_partial_trace(local_trace, monkeypatch):
    monkeypatch.setattr(config.chat, "timeout", 0.04)
    closed, received = [], []
    class Model:
        async def astream(self, messages):
            try:
                for i in range(100):
                    yield SimpleNamespace(content=str(i), additional_kwargs={"reasoning_content": "思考"})
                    await asyncio.sleep(0.005)
            finally:
                closed.append(True)
    async def emit(delta):
        received.append(delta)
    with pytest.raises(TimeoutError):
        with rag_trace_scope("req_deadline", session_id="session_deadline"):
            await invocation.stream_llm(Model(), [], on_reasoning_delta=emit)
    assert closed == [True] and 0 < len(received) < 100
    trace = json.loads(trace_file_path("session_deadline", "req_deadline").read_text(encoding="utf-8"))
    call = trace["llm_calls"][0]
    assert call["error_type"] == "TimeoutError" and call["response_content"]
    assert call["reasoning_content"] == "".join(received)


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
