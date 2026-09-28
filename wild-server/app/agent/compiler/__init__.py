"""通用编译器：设计图纸 → 蓝图（纯函数，零模型调用）。

对外只暴露 :func:`compile_design` 与其返回类型；四类输出的语义见
``app.agent.compiler.diagnostics``，实现说明见 ``app.agent.compiler.compile``。
"""

from app.agent.compiler.compile import compile_design
from app.agent.compiler.diagnostics import (
    MODE_DRY_RUN,
    MODE_FINAL,
    MODE_PROBE,
    MODES,
    CompileDefault,
    CompileDefect,
    CompileResult,
)

__all__ = [
    "compile_design",
    "CompileDefault",
    "CompileDefect",
    "CompileResult",
    "MODE_DRY_RUN",
    "MODE_FINAL",
    "MODE_PROBE",
    "MODES",
]
