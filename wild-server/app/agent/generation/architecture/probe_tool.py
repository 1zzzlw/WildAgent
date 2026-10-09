"""设计节点的**试算工具**：把编译器包成一个模型可反复调用的只读工具（设计文档 §2.7）。

为什么有它：设计期的缺陷要在"图纸写完之后"才被编译暴露出来，一轮编译才发现一处错，
代价是一次完整的重出（整块重写 + 再编译）。给模型一个"先算一遍再交卷"的通道，
它可以在**写这一块的时候**就发现"这个开间数会让入口越界"。

 三条不可越过的边界（§2.7 明确不接受的方向）：

1. **只回诊断，不回蓝图**。工具内部走 ``compile_design(..., mode="probe")``——该模式
   ``blueprint`` / ``design_brief`` 都恒为 ``None``，所以模型无论怎么调、传什么，
   **都拿不到也改不了蓝图**。链路始终是 图纸 →（编译器）→ 蓝图，模型只活在图纸侧。
2. **工具必须"全函数"（total）**。模型可反复调它，参数是自由文本 ⇒ 非法 JSON、
   越界图纸、归一化异常全都必须**转成可读文本**还回去，不许抛异常穿过 agent 中间件
   （实测 ``normalize_architecture_plan`` 有一条 ``ground[entrance_bay - 1]`` 越界会抛
   ``IndexError``；工具边界上抛出去就是掐掉整轮生成）。
3. **有界**。``max_calls`` 由调用方声明，``plan.tool_loop`` 再叠一层单条目总预算。

本模块**不并入** ``plan/tool_registry.py``：那张表的 ``category`` 是闭集、且语义是
"plan 条目的工具集"（``tools_for(item)`` 是条目数据的函数）；设计块的模型调用不是
plan 条目，混进去会让那条纪律失守。``run_tool_loop`` 只读 ``name`` / ``max_calls`` /
``tool`` 三个字段，所以这里的轻量声明就够用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.agent.compiler import MODE_PROBE, compile_design

#: 工具名。提示词里出现的是它，改名等于改模型看到的契约。
PROBE_TOOL_NAME = "probe_compile_design"

#: 一次回给模型的缺陷条数上限。图纸写歪时缺陷可能上百条，全塞回去会把上下文挤爆。
_DEFECT_LINES_LIMIT = 12

_PROBE_DESCRIPTION = (
    "试算：把一份**图纸草稿**交给确定性编译器，回答它「能不能被编译成蓝图」。"
    "参数 design_json 是图纸 JSON 的字符串（与 architecture_plan 同构；可以只写你已经确定的部分，"
    "缺的字段按图纸默认值处理）。"
    "**只回诊断、不回蓝图**——你无法用它产出或修改蓝图，只能用它验证自己的写法。"
    "返回：图纸合法时给出 error 缺陷条数、被默认填充的字段计数、以及仍缺编译规则的类型；"
    "图纸不合法时给出归一化报错，你要先把它修好。"
)


@dataclass(frozen=True)
class DesignToolSpec:
    """设计节点的工具声明。字段与 ``plan.ToolSpec`` 有交集的那三个，是 ``run_tool_loop`` 的契约。"""

    name: str
    tool: Any
    max_calls: int = 2


def probe_design_text(
    design: Any,
    *,
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    defect_limit: int = _DEFECT_LINES_LIMIT,
) -> str:
    """把一个图纸草稿试算成一段**给模型看**的文本。**不抛异常**（见模块说明第 2 条）。

    单独成函数而不是只写在工具里：单测不必起 langchain，也能直接钉住"非法输入不回蓝图、
    只回可读文本"这几条。
    """

    from app.agent.generation.architecture import normalize_architecture_plan

    if isinstance(design, str):
        try:
            raw = json.loads(design)
        except ValueError as exc:
            return f"❌ design_json 不是合法 JSON：{exc}。请传图纸对象的 JSON 字符串。"
    else:
        raw = design
    if not isinstance(raw, dict):
        return "❌ design_json 必须是一个 JSON **对象**（图纸），收到别的类型。"

    normalization_changes = []
    try:
        plan = normalize_architecture_plan(
            raw,
            user_message=user_message,
            complexity_profile=complexity_profile,
            architecture_profile=architecture_profile,
            normalization_changes=normalization_changes, input_source="model",
        )
    except Exception as exc:  # noqa: BLE001 —— 工具边界：任何异常都必须变成文本
        # 归一化失败是**模型最可能**撞到的一类（它写的就是图纸）。这条回执本身就是有用的
        # 反馈：告诉它"这份图纸连协议都没过，先修这个"。
        return f"❌ 图纸不合法（归一化失败）：{type(exc).__name__}: {exc}"

    try:
        result = compile_design(plan, mode=MODE_PROBE, user_message=user_message, normalized_input=True)
    except Exception as exc:  # noqa: BLE001 —— 编译器崩溃是我们的 bug，但也不许穿出去
        logger.warning(f"[probe] 试算时编译器抛错: {exc}")
        return f"❌ 编译器内部错误：{type(exc).__name__}: {exc}"

    errors = [item for item in result.defects if item.severity == "error"]
    warns = [item for item in result.defects if item.severity != "error"]
    lines = [
        (
            "✅ 这份图纸**可以被编译**。"
            if not errors
            else f"⚠️ 这份图纸现在**编不出来**，有 {len(errors)} 条 error 缺陷。"
        ),
        f"error 缺陷 {len(errors)} 条、warn {len(warns)} 条；"
        f"未表态（走引擎默认值）的字段 {len(result.defaulted)} 项。",
    ]

    if normalization_changes:
        lines.append("归一化变化（可编译不等于原方案已保留）：")
        for change in normalization_changes:
            lines.append(f"- {change['path']}: {change['before']!r} → {change['after']!r}；{change['reason']}")

    if errors:
        lines.append("")
        lines.append("必须消掉的缺陷（`图纸项` 就是你要改的字段）：")
        for item in errors[: max(1, int(defect_limit))]:
            where = f"（图纸项：{item.design_field}）" if item.design_field else ""
            lines.append(f"- [{item.code}] {item.evidence}{where}")
        if len(errors) > defect_limit:
            lines.append(f"- …另有 {len(errors) - defect_limit} 条同类缺陷未列出")

    if result.defaulted:
        targets = sorted({item.target for item in result.defaulted})
        lines.append("")
        lines.append(
            f"未表态的字段分布在 {len(targets)} 个目标上（前几个：{'、'.join(targets[:6])}）；"
            "档位越高越应该把它们补进图纸。"
        )
    if result.uncompiled:
        lines.append(
            f"这些类型编译器还没有派生规则，会交给下游模型补：{list(result.uncompiled)}。"
            "你**不需要**在图纸里为它们编坐标。"
        )
    if result.unsupported:
        lines.append(f"这些类型引擎做不到（只标记、不阻断）：{list(result.unsupported)}。")
    return "\n".join(lines)


def build_probe_tool(
    *,
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    max_calls: int = 2,
) -> DesignToolSpec:
    """按当前请求造一个 ``probe_compile_design`` 工具声明。

    参数（用户请求、两个档位 profile）用闭包固定住：模型只该传图纸，
    其余的"这次给谁算"必须由系统决定——否则模型可以拿别的请求去试算。
    """

    from langchain_core.tools import StructuredTool

    def probe_compile_design(design_json: str) -> str:
        return probe_design_text(
            design_json,
            user_message=user_message,
            complexity_profile=complexity_profile,
            architecture_profile=architecture_profile,
        )

    tool = StructuredTool.from_function(
        func=probe_compile_design,
        name=PROBE_TOOL_NAME,
        description=_PROBE_DESCRIPTION,
    )
    return DesignToolSpec(name=PROBE_TOOL_NAME, tool=tool, max_calls=max_calls)


__all__ = [
    "PROBE_TOOL_NAME",
    "DesignToolSpec",
    "build_probe_tool",
    "probe_design_text",
]
