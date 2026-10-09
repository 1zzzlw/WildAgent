"""只读投影原始产物的错误，复用交付 validator，不执行任何自动修复。"""

from __future__ import annotations

from typing import Any


def pipeline_defect_messages(blueprint: dict[str, Any]) -> list[tuple[str, str]]:
    """把交付流水线在 ``error`` 上仍未通过的步骤投影成 ``[(步骤名, 消息), …]``。

    消息一律是校验器原文里的 ``❌`` 行（**不改写**）：证据必须能直接对得上
    ``spatial_tools`` 的输出，否则同一条缺陷在两处会有两种说法。
    """

    from app.agent.validation.candidate import evaluate_candidate

    found: list[tuple[str, str]] = []
    for step in evaluate_candidate(blueprint, source="compile")["errors"]:
        for line in str(step.output).splitlines():
            message = line.strip()
            if "❌" in message:
                found.append((str(step.name), message))
    return found


__all__ = ["pipeline_defect_messages"]
