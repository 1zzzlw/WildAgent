"""基于正负样本 Top-1 距离校准 Retrieval Gate 阈值。"""

from __future__ import annotations

import math
from typing import Any


def calibrate_distance_threshold(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """选择 balanced accuracy 最高的阈值，同分时优先降低错误放行率。"""

    usable = []
    for item in samples:
        if "should_answer" not in item:
            continue
        distance = item.get("distance")
        usable.append({
            "should_answer": bool(item["should_answer"]),
            # 空召回等价于无法通过任何有限距离阈值，不能从误拒/正确拒答统计中消失。
            "distance": math.inf if distance is None else float(distance),
        })
    positives = [item for item in usable if item["should_answer"]]
    negatives = [item for item in usable if not item["should_answer"]]
    if not positives or not negatives:
        raise ValueError("阈值校准至少需要一个正样本和一个负样本")

    distances = sorted({item["distance"] for item in usable if math.isfinite(item["distance"])})
    if not distances:
        raise ValueError("所有样本都为空召回，无法校准有限距离阈值")
    candidates = [distances[0] - 1e-9]
    candidates.extend((left + right) / 2 for left, right in zip(distances, distances[1:]))
    candidates.append(distances[-1] + 1e-9)

    scored = []
    for threshold in candidates:
        true_positive = sum(item["distance"] <= threshold for item in positives)
        false_negative = len(positives) - true_positive
        false_positive = sum(item["distance"] <= threshold for item in negatives)
        true_negative = len(negatives) - false_positive
        true_positive_rate = true_positive / len(positives)
        true_negative_rate = true_negative / len(negatives)
        scored.append({
            "threshold": threshold,
            "balanced_accuracy": (true_positive_rate + true_negative_rate) / 2,
            "false_reject_rate": false_negative / len(positives),
            "false_accept_rate": false_positive / len(negatives),
            "true_positive": true_positive,
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
        })
    best = max(
        scored,
        key=lambda item: (
            item["balanced_accuracy"],
            -item["false_accept_rate"],
            -item["false_reject_rate"],
        ),
    )
    return {
        **best,
        "positive_samples": len(positives),
        "negative_samples": len(negatives),
        "sample_count": len(usable),
    }
