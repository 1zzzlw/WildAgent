"""编译诊断：编译器对外的四类输出。

区分这四类是整个重构的关键——它们对应四种完全不同的处置方式，
混成一句中文错误串（如旧的 ``f"骨架几何预检未通过: {detail}"``）就没人能据此行动。

| 类别 | 含义 | 处置 |
| --- | --- | --- |
| ``defects`` | 图纸**错了**（引用悬空/尺寸越界/枚举越界） | **必须改图纸**，收敛环据 ``design_field`` 定位设计块 |
| ``defaulted`` | 图纸**没说**，字段留给引擎默认值 | **档位决定**：低档接受；高档让模型补进图纸（🔴 **前置**：图纸层须有承接该字段的通道。门窗细部目前**没有**——`defaulted` 实测全部落在 `frameDepth`/`doorStyle` 这类字段上，而图纸只有"配额"没有"实例参数"，见 `docs-dev/2026-09-28-design-to-blueprint-compiler.md` §5.12） |
| ``unsupported`` | 能力缺失（引擎实现不了） | 只标记不阻断（红线），进交付清单 |
| ``uncompiled`` | 编译器暂无派生规则（迁移指示，**不是**能力缺失） | 走模型通道；随规则补齐而缩小 |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

#: ``error`` 阻断交付；``warn`` 只记录。
Severity = Literal["error", "warn"]

#: 编译模式。``final`` 出蓝图；``dry_run`` / ``probe`` 只回诊断。
#: ``probe`` 供设计节点当 tool 试算（见设计文档 §2.7）——它连蓝图都不回，模型污染不了产物。
MODE_FINAL = "final"
MODE_DRY_RUN = "dry_run"
MODE_PROBE = "probe"
MODES = (MODE_FINAL, MODE_DRY_RUN, MODE_PROBE)


@dataclass(frozen=True)
class CompileDefect:
    """图纸错了：编译器产不出合法产物，必须改图纸。"""

    code: str
    severity: Severity
    target: str
    evidence: str
    #: 该改图纸的哪一项（如 ``decisions.facades.front.ground_pattern``）。
    #: 收敛环据此把缺陷映射回"是哪一块的哪一项"。
    design_field: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "target": self.target,
            "evidence": self.evidence,
            "design_field": self.design_field,
        }


@dataclass(frozen=True)
class CompileDefault:
    """图纸没说：该字段未被图纸确定，产物里留给引擎默认值。

    这不是错误——编译是成功的。它只是如实告诉图纸作者"这里你没表态"，
    由档位决定要不要让模型把值补进图纸。

    ⚠️ **但"补进图纸"当前无处可写**：图纸协议里没有逐实例参数通道（只有 ``component_quota`` 计数），
    实测 ``defaulted`` 全部落在门窗注册表 ``optional_fields`` 上。⇒ 回灌的前置是图纸分层升级
    （`docs-dev/2026-09-28-design-to-blueprint-compiler.md` §3.3/§3.4、§5.12）。
    """

    target: str
    field: str
    reason: str = "engine_default"

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "field": self.field, "reason": self.reason}


@dataclass
class CompileResult:
    """一次编译的全部结果。"""

    mode: str
    blueprint: dict[str, Any] | None = None
    #: A 层派生结果（facade_plan + component_quota + 各类槽位）。
    #: 与 ``blueprint`` 同门控：``dry_run`` / ``probe`` 不回，避免被当成"可用的中间产物"。
    design_brief: dict[str, Any] | None = None
    defects: list[CompileDefect] = field(default_factory=list)
    defaulted: list[CompileDefault] = field(default_factory=list)
    #: 引擎做不到的构件类型（只标记不阻断）。
    unsupported: list[str] = field(default_factory=list)
    #: 编译器暂无派生规则的构件类型（迁移指示，不是能力缺失）。
    uncompiled: list[str] = field(default_factory=list)
    #: 旁路观测：各确定性阶段的统计（synthesized / snapped / pruned / split …）。
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """没有阻断级缺陷即视为编译成功。"""

        return not any(item.severity == "error" for item in self.defects)

    def summary(self) -> dict[str, Any]:
        geometry = (self.blueprint or {}).get("geometry", {})
        elements = geometry.get("elements", []) or []
        components = geometry.get("components", []) or []
        return {
            "mode": self.mode,
            "ok": self.ok,
            "elements": len(elements),
            "components": len(components),
            "defects": len(self.defects),
            "defaulted": len(self.defaulted),
            "unsupported": list(self.unsupported),
            "uncompiled": list(self.uncompiled),
        }


__all__ = [
    "CompileDefault",
    "CompileDefect",
    "CompileResult",
    "MODE_DRY_RUN",
    "MODE_FINAL",
    "MODE_PROBE",
    "MODES",
    "Severity",
]
