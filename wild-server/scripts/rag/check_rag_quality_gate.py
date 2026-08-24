"""根据机器可读评测结果执行 CI RAG 质量门禁。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 RAG 评测是否达到 CI 门槛")
    parser.add_argument("eval_json", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("evals/rag_quality_gate.json"),
    )
    args = parser.parse_args()
    payload = json.loads(args.eval_json.read_text(encoding="utf-8"))
    gate = json.loads(args.config.read_text(encoding="utf-8"))
    stats = payload.get("stats") or {}

    checks = {
        "case_count": (
            int(stats.get("total_questions", 0)) >= int(gate["min_case_count"]),
            stats.get("total_questions"),
            f">={gate['min_case_count']}",
        ),
        "negative_count": (
            int(stats.get("negative_questions", 0)) >= int(gate["min_negative_count"]),
            stats.get("negative_questions"),
            f">={gate['min_negative_count']}",
        ),
        "hit_at_k": (
            float(stats.get("hit_at_k") or 0) >= float(gate["min_hit_at_k"]),
            stats.get("hit_at_k"),
            f">={gate['min_hit_at_k']}",
        ),
        "recall_at_k": (
            float(stats.get("recall_at_k") or 0) >= float(gate["min_recall_at_k"]),
            stats.get("recall_at_k"),
            f">={gate['min_recall_at_k']}",
        ),
        "mrr": (
            float(stats.get("mrr") or 0) >= float(gate["min_mrr"]),
            stats.get("mrr"),
            f">={gate['min_mrr']}",
        ),
        "retrieval_errors": (
            int(stats.get("retrieval_errors", 0)) <= int(gate["max_retrieval_errors"]),
            stats.get("retrieval_errors"),
            f"<={gate['max_retrieval_errors']}",
        ),
    }
    failed = []
    for name, (passed, actual, expected) in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}: actual={actual}, expected={expected}")
        if not passed:
            failed.append(name)
    if failed:
        print(f"RAG 质量门禁失败: {', '.join(failed)}")
        return 1
    print("RAG 质量门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
