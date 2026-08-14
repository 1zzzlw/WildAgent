"""稳定的诊断与校验快照 Schema。

- ``blueprint_fingerprint``：Blueprint 内容指纹，供校验结果按内容复用。
- ``ValidationSnapshot``：一次权威校验的结果快照（含设计约束、结构化问题、耗时与来源）。
- ``NodeDiagnostic``：节点级诊断的目标 Schema，保留 ``extra`` 承载节点特有字段以兼容前端。

设计意图：当前 ``validate_node`` 用 ``merge_diag.final_errors == 0`` 这种隐式条件判断
校验缓存是否可用；改为显式携带 Blueprint 指纹的 ``ValidationSnapshot`` 后，callback 已复检
通过的候选回到 ``final_validate`` 时指纹一致即可复用，不再重跑校验。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

# 校验器版本：修改校验/修复工具语义时递增，让旧的 ValidationSnapshot 自动失效。
VALIDATOR_VERSION = "1.0"


def blueprint_fingerprint(blueprint: dict | None) -> str:
    """Blueprint 内容指纹（稳定、键序无关）。"""
    if blueprint is None:
        return "none"
    payload = json.dumps(
        blueprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def step_result_to_dict(result: Any) -> dict:
    """把 ``PipelineStepResult``（或同构 dict）序列化为可存盘的 dict。"""
    return {
        "step": getattr(result, "step", None),
        "name": getattr(result, "name", "unknown"),
        "output": getattr(result, "output", ""),
        "has_error": bool(getattr(result, "has_error", False)),
        "has_warning": bool(getattr(result, "has_warning", False)),
    }


@dataclass
class NodeDiagnostic:
    """节点级诊断的稳定字段；``extra`` 承载节点特有字段，保证前端兼容。"""

    node: str = ""
    label: str = ""
    stage: str = "done"  # done | error | skipped
    rag_chars: int = 0
    rag_ms: int = 0
    rag_hits: list = field(default_factory=list)
    llm_chars: int = 0
    llm_ms: int = 0
    reasoning_chars: int = 0
    token_usage: dict | None = None
    total_ms: int = 0
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """输出与既有 ``*_diag`` 字典同构的扁平字典，避免破坏前端消费。"""
        data = {key: value for key, value in asdict(self).items() if key != "extra"}
        data.update(self.extra)
        return data


@dataclass
class ValidationSnapshot:
    """一次权威校验的结果快照，按 Blueprint 指纹 + 校验器版本复用。"""

    blueprint_fingerprint: str = ""
    validator_version: str = VALIDATOR_VERSION
    status: str = "complete"  # complete | partial | failed
    results: list = field(default_factory=list)  # PipelineStepResult
    design_errors: list = field(default_factory=list)
    issues: list = field(default_factory=list)  # 结构化 ValidationIssue
    error_count: int = 0
    warning_count: int = 0
    elapsed_ms: int = 0
    source: str = ""  # merge | final_validate | callback

    def matches(self, blueprint: dict | None) -> bool:
        """当前 Blueprint 与校验器版本一致时，可复用本快照。"""
        return (
            self.blueprint_fingerprint == blueprint_fingerprint(blueprint)
            and self.validator_version == VALIDATOR_VERSION
        )
