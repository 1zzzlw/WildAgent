"""通用编译器：设计图纸 → 蓝图（纯函数，零模型调用）。

对外只暴露 :func:`compile_design` 与其返回类型；四类输出的语义见
``app.domain.compilation.diagnostics``，实现说明见 ``app.domain.compilation.compile``。
"""

from app.domain.compilation.compile import compile_design
from app.domain.compilation.diagnostics import MODE_DRY_RUN
from app.domain.compilation.diagnostics import MODE_FINAL
from app.domain.compilation.diagnostics import MODE_PROBE
from app.domain.compilation.diagnostics import MODES
from app.domain.compilation.diagnostics import CompileDefault
from app.domain.compilation.diagnostics import CompileDefect
from app.domain.compilation.diagnostics import CompileResult

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
