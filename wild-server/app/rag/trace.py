"""RAG 请求级观测数据。

这个模块只负责记录事实，不参与检索排序、拒答判断或答案生成。
同一次 WebSocket 请求中的检索、上下文和 LLM 调用通过 request_id 串联起来，
最终原子保存 JSON 文件并输出一条 ``[RAG_TRACE]`` 控制台日志，便于后续做阈值校准和性能分析。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from loguru import logger

from app.agent.runtime import SERVER_INSTANCE_ID, runtime_fingerprint
from app.rag.security import AccessContext, access_context_scope, redact_pii
from config import config


_current_rag_trace: ContextVar["RAGTrace | None"] = ContextVar(
    "current_rag_trace",
    default=None,
)
_llm_trace_context: ContextVar[dict[str, Any]] = ContextVar("llm_trace_context", default={})


@contextmanager
def llm_trace_scope(*, item_id=None, stage=None, design_hash=None, candidate_fingerprint=None,
                    batch_load=None, marker_ids=None, injected_chunk_ids=None) -> Iterator[None]:
    """绑定调用归属，独立异步任务不会互相覆盖条目或修订阶段。"""
    values = {"item_id": item_id, "stage": stage, "design_hash": design_hash,
              "candidate_fingerprint": candidate_fingerprint, "batch_load": batch_load,
              "marker_ids": marker_ids, "injected_chunk_ids": injected_chunk_ids}
    token = _llm_trace_context.set({**_llm_trace_context.get(),
                                    **{k: v for k, v in values.items() if v is not None}})
    try:
        yield
    finally:
        _llm_trace_context.reset(token)


_SECRET_FIELDS = {"api_key", "openai_api_key", "authorization", "password", "secret",
                  "access_token", "refresh_token", "headers", "default_headers"}
_SECRET_TEXT = re.compile(r"(?i)(\b(?:api[_-]?key|authorization|password|access_token)"
                          r"[\"']?\s*[:=]\s*[\"']?)(?:Bearer\s+)?[^\s,\"'}]+")


def _public_trace_value(value: Any) -> Any:
    if isinstance(value, str):
        text, _ = redact_pii(value)
        return _SECRET_TEXT.sub(r"\1[redacted]", text)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): _public_trace_value(v) for k, v in value.items()
                if str(k).casefold() not in _SECRET_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_public_trace_value(v) for v in value]
    return {"type": type(value).__name__}


def _safe_model_config(llm: Any) -> dict[str, Any]:
    client = getattr(llm, "bound", llm)
    fields = ("model_name", "temperature", "top_p", "seed", "max_tokens",
              "frequency_penalty", "presence_penalty", "n", "logprobs", "top_logprobs",
              "stop", "max_retries", "request_timeout", "streaming", "reasoning_effort")
    result = {key: _public_trace_value(getattr(client, key)) for key in fields
              if getattr(client, key, None) is not None}
    timeout = getattr(client, "request_timeout", None)
    if timeout is not None and not isinstance(timeout, (int, float)):
        result["request_timeout"] = {key: getattr(timeout, key) for key in ("connect", "read", "write", "pool")
                                     if isinstance(getattr(timeout, key, None), (int, float))}
    raw_url = getattr(client, "openai_api_base", None)
    if raw_url:
        url = urlsplit(str(raw_url))
        host = url.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if url.port:
            host += f":{url.port}"
        result["base_url"] = urlunsplit((url.scheme, host, url.path, "", ""))
    for key in ("extra_body", "model_kwargs", "kwargs"):
        parameters = getattr(client if key != "kwargs" else llm, key, None)
        if isinstance(parameters, dict):
            allowed = {"thinking", "enable_thinking", "thinking_budget", "reasoning_effort",
                       "temperature", "top_p", "seed", "max_tokens", "max_completion_tokens",
                       "frequency_penalty", "presence_penalty", "n", "logprobs", "top_logprobs",
                       "response_format", "stop", "stream_options"}
            result[key] = _public_trace_value({k: v for k, v in parameters.items() if k in allowed})
    return result


def prepare_rag_llm_call(llm: Any, messages: Any) -> dict[str, Any]:
    """调用前保存实际输入；全文按摘要复用，调用结束沿同一 call_id 记录结果。"""
    trace = get_current_rag_trace()
    if trace is None:
        return {}
    rows, raw_rows = [], []
    for message in messages:
        if isinstance(message, dict):
            row = message
        elif isinstance(message, tuple) and len(message) == 2:
            row = {"role": message[0], "content": message[1]}
        else:
            kind = getattr(message, "type", type(message).__name__)
            row = {"role": {"human": "user", "ai": "assistant"}.get(kind, kind),
                   "content": getattr(message, "content", "")}
            for key in ("name", "tool_call_id", "tool_calls", "additional_kwargs"):
                if getattr(message, key, None):
                    row[key] = getattr(message, key)
        raw_rows.append(row)
        rows.append(_public_trace_value(row))
    raw_encoded = json.dumps(raw_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                             default=lambda value: {"type": type(value).__name__})
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    trace.llm_inputs.setdefault(digest, {"messages": rows, "redaction": "pii_and_credentials"})
    context = dict(_llm_trace_context.get())
    if "stage" not in context:
        from langchain_core.runnables.config import var_child_runnable_config
        metadata = (var_child_runnable_config.get() or {}).get("metadata") or {}
        if metadata.get("langgraph_node"):
            context["stage"] = metadata["langgraph_node"]
    return {"call_id": uuid4().hex, "messages_ref": digest, "messages_sha256": digest,
            "input_chars": len(raw_encoded), "input_bytes": len(raw_encoded.encode("utf-8")),
            "input_message_count": len(rows), "model_config": _safe_model_config(llm),
            "index_signatures": sorted({query["index_signature"] for retrieval in trace.retrievals
                                        for query in retrieval.get("queries", [])
                                        if query.get("index_signature")}),
            **_public_trace_value(context)}


def _runtime_snapshot() -> dict[str, Any]:
    try:
        return runtime_fingerprint()
    except OSError as exc:
        return {"server_instance_id": SERVER_INSTANCE_ID, "error_type": type(exc).__name__}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _query_preview(text: str, limit: int = 300) -> str:
    """压缩空白并截断问题，避免一条日志被超长 Prompt 淹没。"""

    redacted, _ = redact_pii(str(text or ""))
    compact = re.sub(r"\s+", " ", redacted).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def make_query_trace(
    text: str,
    metadata_filter: dict[str, Any] | None = None,
    effective_filter: dict[str, Any] | None = None,
    index_signature: str | None = None,
    ignored_access_filter_keys: list[str] | None = None,
) -> dict[str, Any]:
    """构造一条可读、可关联且体积受控的查询记录。"""

    raw_text, _ = redact_pii(str(text or ""))
    return {
        "query": _query_preview(raw_text),
        "query_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "metadata_filter": metadata_filter or {},
        "effective_filter": effective_filter or {},
        "index_signature": index_signature,
        "ignored_access_filter_keys": list(ignored_access_filter_keys or []),
    }


def _hit_to_dict(hit: Any) -> dict[str, Any]:
    metadata = getattr(hit, "metadata", None) or {}
    distance = getattr(hit, "distance", None)
    return {
        "chunk_id": getattr(hit, "id", None),
        "parent_chunk_id": metadata.get("parent_chunk_id"),
        "source": metadata.get("source") or metadata.get("path"),
        "heading": metadata.get("heading"),
        "raw_distance": float(distance) if distance is not None else None,
    }


@dataclass
class RAGTrace:
    """一次用户请求中的 RAG 观测记录。"""

    request_id: str
    session_id: str = "unknown"
    access_context: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=_utc_now)
    retrievals: list[dict[str, Any]] = field(default_factory=list)
    contexts: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    llm_inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    gate_decisions: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    safety: dict[str, Any] | None = None
    final_answer: str | None = None
    status: str = "running"
    error_type: str | None = None
    _started_perf: float = field(default_factory=time.perf_counter, repr=False)
    _elapsed_ms: int | None = field(default=None, repr=False)
    _previous: dict[str, Any] = field(default_factory=dict, repr=False)
    _execution_id: str = field(default_factory=lambda: uuid4().hex, repr=False)
    _runtime: dict[str, Any] = field(default_factory=_runtime_snapshot, repr=False)

    def finish(self, status: str = "completed", error_type: str | None = None) -> None:
        """结束计时；重复调用不会覆盖第一次结束结果。"""

        if self._elapsed_ms is not None:
            return
        if self.status == "error" and status == "completed":
            status = "error"
            error_type = error_type or self.error_type
        self.status = status
        self.error_type = error_type
        self._elapsed_ms = round((time.perf_counter() - self._started_perf) * 1000)

    def to_dict(self) -> dict[str, Any]:
        """转成适合 JSON 日志和测试断言的普通字典。"""

        elapsed_ms = self._elapsed_ms
        if elapsed_ms is None:
            elapsed_ms = round((time.perf_counter() - self._started_perf) * 1000)
        previous = self._previous
        records = {key: [*previous.get(key, []), *getattr(self, key)] for key in
                   ("retrievals", "contexts", "llm_calls", "nodes", "gate_decisions", "citations", "warnings")}
        executions = list(previous.get("executions") or [])
        if previous and not executions:
            executions.append({"id": "legacy", "started_at": previous.get("started_at"),
                               "elapsed_ms": previous.get("elapsed_ms", 0), "status": previous.get("status")})
        executions.append({"id": self._execution_id, "started_at": self.started_at,
                           "elapsed_ms": elapsed_ms, "status": self.status, "error_type": self.error_type,
                           "runtime": self._runtime})

        token_usage = {"input": 0, "output": 0, "total": 0}
        retry_count = 0
        for call in records["llm_calls"]:
            usage = call.get("token_usage") or {}
            token_usage["input"] += int(usage.get("input", 0) or 0)
            token_usage["output"] += int(usage.get("output", 0) or 0)
            token_usage["total"] += int(usage.get("total", 0) or 0)
            retry_count += int(call.get("retry_count") or 0)

        context_chars = [int(item.get("context_chars", 0)) for item in records["contexts"]]
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "started_at": previous.get("started_at", self.started_at),
            "status": self.status,
            "error_type": self.error_type,
            "elapsed_ms": int(previous.get("elapsed_ms", 0)) + elapsed_ms,
            "executions": executions,
            "summary": {
                "retrieval_calls": len(records["retrievals"]),
                "retrieval_ms": sum(
                    int(item.get("elapsed_ms", 0)) for item in records["retrievals"]
                ),
                "context_builds": len(records["contexts"]),
                "max_context_chars": max(context_chars, default=0),
                "llm_calls": len(records["llm_calls"]),
                "llm_ms": sum(int(item.get("elapsed_ms", 0)) for item in records["llm_calls"]),
                "token_usage": token_usage,
                "llm_retry_count": retry_count,
                "llm_input_chars": sum(int(item.get("input_chars", 0)) for item in records["llm_calls"]),
                "llm_output_chars": sum(int(item.get("output_chars", 0)) for item in records["llm_calls"]),
                "llm_transport_attempts": sum(len(item.get("transport_attempts") or [])
                                              for item in records["llm_calls"]),
                "node_calls": len(records["nodes"]),
                "node_ms": sum(
                    int(item.get("duration_ms", 0)) for item in records["nodes"]
                ),
                "gate_rejections": sum(
                    1 for item in records["gate_decisions"] if item.get("decision") == "reject"
                ),
            },
            **records,
            "llm_inputs": {**previous.get("llm_inputs", {}), **self.llm_inputs},
            "safety": self.safety or previous.get("safety"),
            "final_answer": self.final_answer if self.final_answer is not None else previous.get("final_answer"),
            "access_context": self.access_context,
        }


def get_current_rag_trace() -> RAGTrace | None:
    """获取当前异步任务绑定的追踪对象；非请求环境下返回 None。"""

    return _current_rag_trace.get()


def _safe_path_part(value: str) -> str:
    raw = str(value or "unknown")
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip(".")
    if not normalized:
        normalized = "id"
    # 只有发生替换/去点/截断时才加摘要，既阻止 ``..`` 路径穿越，也避免
    # ``a/b`` 与 ``a_b`` 等不同外部 ID 写入同一个文件。
    if normalized != raw or len(normalized) > 160:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return f"{normalized[:140]}-{digest}"
    return normalized


def trace_storage_root() -> Path:
    root = Path(config.rag.trace.root_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return root


def trace_file_path(session_id: str, request_id: str) -> Path:
    return (
        trace_storage_root()
        / _safe_path_part(session_id)
        / f"{_safe_path_part(request_id)}.json"
    )


def persist_rag_trace(trace: RAGTrace) -> Path | None:
    """使用同目录临时文件 + replace 原子写入，避免进程中断留下半个 JSON。"""

    if not config.rag.trace.enabled:
        return None
    target = trace_file_path(trace.session_id, trace.request_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target


@contextmanager
def rag_trace_scope(
    request_id: str,
    *,
    session_id: str | None = None,
    access_context: AccessContext | None = None,
    persist: bool | None = None,
) -> Iterator[RAGTrace]:
    """绑定一次请求的追踪上下文，并在退出时输出统一 JSON 日志。"""

    current = get_current_rag_trace()
    if current is not None and current.request_id == request_id:
        yield current
        return

    bound_access = access_context or AccessContext()
    trace = RAGTrace(
        request_id=str(request_id or "unknown"),
        session_id=str(session_id or request_id or "unknown"),
        access_context=bound_access.public_dict(),
    )
    if persist is not False and config.rag.trace.enabled:
        path = trace_file_path(trace.session_id, trace.request_id)
        if path.exists():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                if (previous.get("request_id") == trace.request_id and previous.get("session_id") == trace.session_id
                        and previous.get("access_context") == json.loads(json.dumps(trace.access_context))):
                    trace._previous = previous
            except (OSError, ValueError) as exc:
                logger.warning("不能恢复此前 trace：{}", type(exc).__name__)
    with access_context_scope(bound_access):
        token = _current_rag_trace.set(trace)
        try:
            yield trace
        except BaseException as exc:
            trace.finish(status="error", error_type=type(exc).__name__)
            raise
        else:
            trace.finish()
        finally:
            if trace._elapsed_ms is None:
                trace.finish()
            path = None
            persistence_error = None
            try:
                path = persist_rag_trace(trace) if persist is not False else None
            except Exception as exc:
                persistence_error = f"{type(exc).__name__}: {exc}"
            try:
                payload = trace.to_dict()
                payload.pop("llm_inputs", None)
                payload["llm_calls"] = [{k: v for k, v in call.items()
                                         if k not in {"response_content", "reasoning_content"}}
                                        for call in payload["llm_calls"]]
                payload["trace_file"] = str(path) if path else None
                payload["persistence_error"] = persistence_error
                logger.info(
                    "[RAG_TRACE] {}",
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    ),
                )
            except Exception:
                # 观测日志失败不能反过来改变 Agent 的回答或异常语义。
                pass
            finally:
                _current_rag_trace.reset(token)


def record_rag_retrieval(
    operation: str,
    queries: list[dict[str, Any]],
    hits: list[Any],
    elapsed_ms: int,
    error_type: str | None = None,
) -> bool:
    """记录一次真实检索；没有活动追踪上下文时安全地跳过。"""

    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.retrievals.append(
        {
            "operation": operation,
            "elapsed_ms": elapsed_ms,
            "error_type": error_type,
            "queries": queries,
            "hit_count": len(hits),
            "hits": [_hit_to_dict(hit) for hit in hits],
        }
    )
    return True


def record_rag_context(
    operation: str,
    base_chars: int,
    retrieved_chars: int,
    context_chars: int,
    retrieved_count: int,
    injected_chunk_ids: list[str] | None = None,
) -> bool:
    """记录拼给 LLM 的知识上下文大小。"""

    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.contexts.append(
        {
            "operation": operation,
            "base_chars": base_chars,
            "retrieved_chars": retrieved_chars,
            "context_chars": context_chars,
            "retrieved_count": retrieved_count,
            "injected_chunk_ids": list(injected_chunk_ids or []),
        }
    )
    return True


def record_rag_llm_call(
    mode: str,
    elapsed_ms: int,
    token_usage: dict[str, int] | None,
    error_type: str | None = None,
    retry_count: int = 0,
    *,
    response_content: str = "",
    reasoning_content: str = "",
    call_metadata: dict[str, Any] | None = None,
    transport_attempts: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
) -> bool:
    """记录调用统计与模型实际返回的完整输出、思考，沿请求 trace 落盘。"""

    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.llm_calls.append(
        {
            **(call_metadata or _public_trace_value(_llm_trace_context.get())),
            "call_id": (call_metadata or {}).get("call_id") or uuid4().hex,
            "request_id": trace.request_id,
            "execution_id": trace._execution_id,
            "server_instance_id": SERVER_INSTANCE_ID,
            "mode": mode,
            "elapsed_ms": elapsed_ms,
            "error_type": error_type,
            "retry_count": max(0, int(retry_count or 0)),
            "retry_scope": "invocation_wrapper",
            "response_content": _SECRET_TEXT.sub(r"\1[redacted]", response_content),
            "reasoning_content": _SECRET_TEXT.sub(r"\1[redacted]", reasoning_content),
            "output_chars": len(response_content),
            "reasoning_chars": len(reasoning_content),
            "finish_reason": finish_reason,
            "transport_attempts": list(transport_attempts or []),
            "sdk_retry_count": None,
            "token_usage": {
                "input": int((token_usage or {}).get("input", 0) or 0),
                "output": int((token_usage or {}).get("output", 0) or 0),
                "total": int((token_usage or {}).get("total", 0) or 0),
            },
        }
    )
    return True


def record_node_call(
    node_name: str,
    *,
    started_at: str,
    completed_at: str,
    duration_ms: int,
    llm_ms: int | None = None,
    rag_ms: int | None = None,
    token_usage: dict[str, int] | None = None,
    retry_count: int = 0,
    output_size: int | None = None,
    error: str | None = None,
    model: str | None = None,
) -> bool:
    """记录一次 Agent 节点执行的墙钟耗时与来源分解。

    这是请求级可观测性的最小协议：每个 node 一条记录，携带开始/结束时间、
    节点总耗时、LLM 与 RAG 子耗时、Token 用量、重试次数和输出规模。没有活动
    请求上下文（如命令行单测）时安全地跳过。
    """

    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.nodes.append(
        {
            "node_name": str(node_name or "?"),
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": max(0, int(duration_ms or 0)),
            "llm_ms": llm_ms,
            "rag_ms": rag_ms,
            "token_usage": {
                "input": int((token_usage or {}).get("input", 0) or 0),
                "output": int((token_usage or {}).get("output", 0) or 0),
                "total": int((token_usage or {}).get("total", 0) or 0),
            },
            "retry_count": max(0, int(retry_count or 0)),
            "output_size": output_size,
            "error": error,
            "model": model,
        }
    )
    return True


def record_rag_gate(decision: dict[str, Any]) -> bool:
    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.gate_decisions.append(dict(decision))
    return True


def record_rag_warning(code: str, message: str) -> bool:
    """记录不影响请求结果但影响结论可靠性的降级/告警。

    例如使用 hash fallback embedding（只在开发 smoke test 应出现）会使距离阈值
    失效；这类信息写入 Trace 后，离线校准与人工排查可以看到降级来源。
    """
    trace = get_current_rag_trace()
    if trace is None:
        return False
    redacted, _ = redact_pii(str(message or ""))
    limit = max(0, int(config.rag.trace.query_preview_chars))
    trace.warnings.append({
        "code": str(code or ""),
        "message": redacted[:limit] if limit else "",
    })
    return True


def get_injected_chunk_ids() -> list[str]:
    trace = get_current_rag_trace()
    if trace is None:
        return []
    ids: list[str] = []
    for context in trace.contexts:
        ids.extend(context.get("injected_chunk_ids") or [])
    return list(dict.fromkeys(item for item in ids if item))


def record_rag_citations(
    cited_chunk_ids: list[str] | tuple[str, ...],
    invalid_chunk_ids: list[str] | tuple[str, ...],
    appended_fallback: bool,
) -> bool:
    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.citations.append({
        "cited_chunk_ids": list(cited_chunk_ids),
        "invalid_chunk_ids": list(invalid_chunk_ids),
        "appended_fallback": appended_fallback,
    })
    return True


def record_rag_safety(result: dict[str, Any]) -> bool:
    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.safety = dict(result)
    return True


def record_final_answer(answer: str) -> bool:
    trace = get_current_rag_trace()
    if trace is None:
        return False
    redacted, _ = redact_pii(answer)
    limit = max(0, int(config.rag.trace.answer_preview_chars))
    trace.final_answer = redacted[:limit] if limit else ""
    return True


def record_rag_error(error: str, error_type: str = "HandledError") -> bool:
    """记录在业务层被转换成 error 事件的异常，避免 Trace 误标 completed。"""

    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.status = "error"
    trace.error_type = error_type
    redacted, _ = redact_pii(error)
    limit = max(0, int(config.rag.trace.answer_preview_chars))
    trace.final_answer = redacted[:limit] if limit else ""
    return True


def append_rag_feedback(
    session_id: str,
    request_id: str,
    *,
    rating: str,
    comment: str = "",
) -> Path:
    """把用户反馈关联到已经落盘的 request_id；不存在时明确报错。"""

    target = trace_file_path(session_id, request_id)
    if not target.exists():
        raise FileNotFoundError(target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    redacted_comment, _ = redact_pii(comment)
    feedback = payload.setdefault("feedback", [])
    feedback.append({
        "rating": rating,
        "comment": redacted_comment[:2000],
        "created_at": _utc_now(),
    })
    temporary = target.with_suffix(f"{target.suffix}.feedback.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target
