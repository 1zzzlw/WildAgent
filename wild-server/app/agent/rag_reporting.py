"""从落盘的 RAGTrace 计算不依赖外部服务的运行指标。"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _p95(values: list[int]) -> int | None:
    """使用 nearest-rank 定义计算 P95；空列表返回 None。"""

    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def summarize_rag_traces(
    root: Path,
    *,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> dict[str, Any]:
    """扫描 Trace JSON，汇总拒答、距离、延迟、Token、成本和反馈。"""

    traces: list[dict[str, Any]] = []
    malformed_files: list[str] = []
    paths = sorted(root.rglob("*.json")) if root.exists() else []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("request_id"):
                traces.append(payload)
        except (OSError, json.JSONDecodeError):
            malformed_files.append(str(path))

    elapsed: list[int] = []
    retrieval_elapsed: list[int] = []
    llm_elapsed: list[int] = []
    best_distances: list[float] = []
    retrieval_calls = 0
    empty_retrieval_calls = 0
    enforced_rejections = 0
    token_usage = Counter(input=0, output=0, total=0)
    feedback = Counter(up=0, down=0)

    for trace in traces:
        summary = trace.get("summary") or {}
        if trace.get("elapsed_ms") is not None:
            elapsed.append(int(trace["elapsed_ms"]))
        retrieval_elapsed.append(int(summary.get("retrieval_ms", 0) or 0))
        llm_elapsed.append(int(summary.get("llm_ms", 0) or 0))
        usage = summary.get("token_usage") or {}
        for key in token_usage:
            token_usage[key] += int(usage.get(key, 0) or 0)

        for retrieval in trace.get("retrievals") or []:
            retrieval_calls += 1
            hits = retrieval.get("hits") or []
            if not hits:
                empty_retrieval_calls += 1
            distances = [
                float(hit["raw_distance"])
                for hit in hits
                if hit.get("raw_distance") is not None
            ]
            if distances:
                best_distances.append(min(distances))

        enforced_rejections += sum(
            1
            for decision in trace.get("gate_decisions") or []
            if decision.get("enforced") is True
        )
        for item in trace.get("feedback") or []:
            rating = str(item.get("rating") or "").lower()
            if rating in feedback:
                feedback[rating] += 1

    estimated_cost = None
    if input_cost_per_million is not None and output_cost_per_million is not None:
        estimated_cost = round(
            token_usage["input"] / 1_000_000 * input_cost_per_million
            + token_usage["output"] / 1_000_000 * output_cost_per_million,
            6,
        )

    request_count = len(traces)
    return {
        "trace_root": str(root),
        "request_count": request_count,
        "malformed_file_count": len(malformed_files),
        "malformed_files": malformed_files,
        "completed_requests": sum(t.get("status") == "completed" for t in traces),
        "error_requests": sum(t.get("status") == "error" for t in traces),
        "retrieval_calls": retrieval_calls,
        "empty_retrieval_rate": (
            empty_retrieval_calls / retrieval_calls if retrieval_calls else None
        ),
        "average_best_distance": (
            sum(best_distances) / len(best_distances) if best_distances else None
        ),
        "enforced_rejection_count": enforced_rejections,
        "enforced_rejection_rate": (
            enforced_rejections / request_count if request_count else None
        ),
        "latency_ms": {
            "p95_total": _p95(elapsed),
            "p95_retrieval": _p95(retrieval_elapsed),
            "p95_llm": _p95(llm_elapsed),
        },
        "token_usage": dict(token_usage),
        "estimated_token_cost": estimated_cost,
        "cost_note": (
            "按传入的每百万 input/output Token 单价估算"
            if estimated_cost is not None
            else "未提供模型单价，不猜测成本"
        ),
        "feedback": dict(feedback),
    }
