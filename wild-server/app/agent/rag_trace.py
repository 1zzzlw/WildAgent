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

from loguru import logger

from app.agent.rag_security import AccessContext, access_context_scope, redact_pii
from config import config


_current_rag_trace: ContextVar["RAGTrace | None"] = ContextVar(
    "current_rag_trace",
    default=None,
)


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
    gate_decisions: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    safety: dict[str, Any] | None = None
    final_answer: str | None = None
    status: str = "running"
    error_type: str | None = None
    _started_perf: float = field(default_factory=time.perf_counter, repr=False)
    _elapsed_ms: int | None = field(default=None, repr=False)

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

        token_usage = {"input": 0, "output": 0, "total": 0}
        for call in self.llm_calls:
            usage = call.get("token_usage") or {}
            token_usage["input"] += int(usage.get("input", 0) or 0)
            token_usage["output"] += int(usage.get("output", 0) or 0)
            token_usage["total"] += int(usage.get("total", 0) or 0)

        context_chars = [int(item.get("context_chars", 0)) for item in self.contexts]
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "status": self.status,
            "error_type": self.error_type,
            "elapsed_ms": elapsed_ms,
            "summary": {
                "retrieval_calls": len(self.retrievals),
                "retrieval_ms": sum(
                    int(item.get("elapsed_ms", 0)) for item in self.retrievals
                ),
                "context_builds": len(self.contexts),
                "max_context_chars": max(context_chars, default=0),
                "llm_calls": len(self.llm_calls),
                "llm_ms": sum(int(item.get("elapsed_ms", 0)) for item in self.llm_calls),
                "token_usage": token_usage,
                "gate_rejections": sum(
                    1 for item in self.gate_decisions if item.get("decision") == "reject"
                ),
            },
            "retrievals": self.retrievals,
            "contexts": self.contexts,
            "llm_calls": self.llm_calls,
            "gate_decisions": self.gate_decisions,
            "citations": self.citations,
            "warnings": self.warnings,
            "safety": self.safety,
            "final_answer": self.final_answer,
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
) -> bool:
    """记录一次 LLM 调用耗时和供应商返回的 Token 用量。"""

    trace = get_current_rag_trace()
    if trace is None:
        return False
    trace.llm_calls.append(
        {
            "mode": mode,
            "elapsed_ms": elapsed_ms,
            "error_type": error_type,
            "token_usage": {
                "input": int((token_usage or {}).get("input", 0) or 0),
                "output": int((token_usage or {}).get("output", 0) or 0),
                "total": int((token_usage or {}).get("total", 0) or 0),
            },
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
