"""通用编译器：设计图纸 → 蓝图（纯函数，零模型调用）。

对外只暴露 :func:`compile_design` 与其返回类型；四类输出的语义见
``agent.utils.compilation.diagnostics``，实现说明见 ``agent.utils.compilation.compile``。
"""

from agent.utils.compilation.compile import compile_design
from agent.utils.compilation.diagnostics import MODE_DRY_RUN
from agent.utils.compilation.diagnostics import MODE_FINAL
from agent.utils.compilation.diagnostics import MODE_PROBE
from agent.utils.compilation.diagnostics import MODES
from agent.utils.compilation.diagnostics import CompileDefault
from agent.utils.compilation.diagnostics import CompileDefect
from agent.utils.compilation.diagnostics import CompileResult

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
