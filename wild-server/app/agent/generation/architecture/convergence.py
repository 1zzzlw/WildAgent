"""编译可行性收敛环 —— 设计文档 §1.6 的**第二半**（缺陷回改）。

第一半在 `design_workflow.py`：首次成图时逐块写。
本模块是同一套块机制在"编译反馈"下的第二次进入：

    图纸 → compile(dry_run，纯函数) → 取 error 级缺陷
         → 按 design_field 映射回块 → 只重出那几块 → 合回图纸 → 再编译

为什么值得单独一环（§1.3）：现状的冻结点（`design_review`）落在**唯一的确定性
可行性校验之前**，人工刚批准的设计可以被编译器一票否决且没有修订通道。把编译
可行性验证挪到人工审核**之前**跑掉，审核的才是一份"确实编得出来"的图纸。

四条硬约束：

1. 🔴 **能力缺失只标记不阻断**（用户红线）：收敛不成功也**不失败**——如实记账，
   把最终缺陷交给人工审核。`unsupported` / `uncompiled` 由编译器另行归入四类输出，
   这里既不重复报、也不因它们继续修订。
2. 🔴 **有界**（§1.4）：迭代上限 + 缺陷数连续不下降低于阈值就停。
   无界重试会在坏图上烧完预算。
3. 🔴 **认不出的 `design_field` 不猜**：映射不到块就停。猜错会去改**另一个块**，
   那比不定位更糟（同一参数被两处夹取就会分叉，见 `MEMORY.md`）。
4. 🔴 **模型故障不掐掉整轮生成**：图纸本身是可用的，收敛只是"能不能更好"。
   在这里 `return model_failure_result(...)` 就又把冻结点挪回了校验之前——
   正是本次重构要拆掉的东西。故障如实记进 `diag.model_error` 即止。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence

from loguru import logger

from app.agent.compiler import MODE_DRY_RUN, compile_design
from app.agent.generation.architecture.design_blocks import block_of_design_field
from app.agent.generation.architecture.design_workflow import draft_design_blocks

#: 图纸修订轮数上限。**不是**"重试次数"：每一轮都会真调模型重出若干块。
_MAX_REVISION_ROUNDS = 3

#: 缺陷数连续这么多轮不下降就停。取 2 而不是 1：一轮没降可能是"改完这处那处又坏"
#: 的正常波动，连续两轮还把缺陷数维持在同一水平才说明这条路走不通。
_MAX_NO_PROGRESS_ROUNDS = 2

#: 收敛环专用的基础提示词。**不重写首次成图那份**（`build_architecture_plan_prompt`）——
#: 那份的任务是"从零设计"，这份的任务是"对着缺陷改"。任务不同，提示词就该不同。
_REPAIR_BASE_PROMPT = """你正在**修订**一份已经定稿的建筑设计图纸。

上一版图纸经过确定性编译后报出了若干缺陷。缺陷里写清了"错在哪、该改图纸的哪一项"。
你的任务是**只重出受影响的块**，把缺陷消掉。

三条要求：
- 只改缺陷指到的字段，其余保持原样（别的块由它们自己的那一轮负责）；
- 不要引入新的体量、新的面或新的构件类型——那会制造新的缺陷；
- 改完之后，同一批字段仍必须满足块契约（会有检查，不过会带证据让你重出）。
"""


@dataclass
class ConvergenceOutcome:
    """一次收敛的最终产物。``plan`` 恒为可用图纸（哪怕一处没改）。"""

    plan: dict[str, Any]
    #: 相对入参是否真的变了。没变时调用方**不要**重建 DesignDocument。
    changed: bool
    diag: dict[str, Any] = field(default_factory=dict)


ReasoningEmitter = Callable[[str, str], Awaitable[None]]


def blocking_defects(result: Any) -> list[Any]:
    """``error`` 级缺陷。``warn`` 不进收敛环——它们不该驱动修订。"""

    return [item for item in result.defects if getattr(item, "severity", "") == "error"]


def design_level_defects(defects: Sequence[Any]) -> list[Any]:
    """能映射回设计块的缺陷。映射不到的不在这里，也不许猜。"""

    return [item for item in defects if block_of_design_field(getattr(item, "design_field", ""))]


def defect_fingerprint(defects: Sequence[Any]) -> frozenset[tuple[str, str, str]]:
    """缺陷指纹：``(code, design_field, evidence)`` 的集合。

    只用于诊断留档。**不用它判"有没有进展"**——`evidence` 里嵌着具体数值，
    改对一点点就会整串变样，集合"相等/包含"关系极不稳定；判进展一律用**条数**。
    """

    return frozenset(
        (
            str(getattr(item, "code", "")),
            str(getattr(item, "design_field", "")),
            str(getattr(item, "evidence", "")),
        )
        for item in defects
    )


async def converge_design(
    *,
    plan: dict[str, Any],
    raw_plan: dict[str, Any] | None,
    user_message: str,
    level: str,
    complexity_profile: dict[str, Any] | None,
    architecture_profile: dict[str, Any] | None,
    thinking_mode: bool,
    material_plan: dict[str, Any] | None = None,
    only_blocks: Sequence[str] | None = None,
    max_rounds: int = _MAX_REVISION_ROUNDS,
    max_no_progress: int = _MAX_NO_PROGRESS_ROUNDS,
    on_reasoning_delta: ReasoningEmitter | None = None,
) -> ConvergenceOutcome:
    """把图纸跑到"能编译"，返回最终图纸与诊断。

    收敛的判据是**不含设计级 error 缺陷**（§1.4）：此时即使还剩"整图级"缺陷
    （`design_field` 为空、映射不到块），也出环——它不属于任何块，重出任何一块都
    解决不了，只能交人工。

    🔴 ``raw_plan`` 是**合并基准**：重出的块字段会并进它再归一化。
    传 ``None`` 时基准退化成空字典，重新归一化出来的图纸就**只剩被重出的那几块**——
    调用方应尽量给首轮的原始草稿（图里由 ``architecture_diag.raw_plan`` 提供）。
    ``diag.raw_plan_available`` 会把这一点如实报出来，便于排查"为什么图纸缩水了"。
    """

    from app.agent.generation.architecture import normalize_architecture_plan

    compile_kwargs: dict[str, Any] = {
        "mode": MODE_DRY_RUN,
        "user_message": user_message,
        "material_plan": material_plan,
    }

    original = dict(plan)
    current = dict(plan)
    raw = dict(raw_plan or {})
    result = compile_design(current, **compile_kwargs)
    initial_count = len(blocking_defects(result))
    last_count = initial_count

    def _diag(rounds: list[dict[str, Any]], stop_reason: str) -> dict[str, Any]:
        final_blocking = blocking_defects(result)
        return {
            "stop_reason": stop_reason,
            "initial_defects": initial_count,
            "final_defects": len(final_blocking),
            "revisions": len(rounds),
            "rounds": rounds,
            "converged": not design_level_defects(final_blocking),
            "unresolved": [item.to_dict() for item in final_blocking],
            "changed": current != original,
        }

    rounds: list[dict[str, Any]] = []
    no_progress = 0
    # 默认就是"预算用尽"：循环跑满没 break、或 max_rounds<=0 时它原样保留。
    stop_reason = "max_rounds"

    for _ in range(max(0, int(max_rounds))):
        blocking = blocking_defects(result)
        targets = design_level_defects(blocking)
        if not targets:
            stop_reason = "converged"
            break

        blocks = sorted(
            {block_of_design_field(item.design_field).name for item in targets}  # type: ignore[union-attr]
        )
        if only_blocks is not None:
            allowed = {str(name) for name in only_blocks}
            blocks = [name for name in blocks if name in allowed]
            if not blocks:
                stop_reason = "outside_scope"
                break

        if on_reasoning_delta is not None:
            await on_reasoning_delta(
                "architecture",
                f"\n### 设计收敛\n编译报出 {len(blocking)} 条缺陷，"
                f"重出这些块：{'、'.join(blocks)}\n",
            )

        try:
            draft, block_diag = await draft_design_blocks(
                base_prompt=_REPAIR_BASE_PROMPT,
                user_request=user_message,
                level=level,
                thinking_mode=thinking_mode,
                on_reasoning_delta=on_reasoning_delta,
                only_blocks=blocks,
                defects=targets,
                # 与首轮成图同一套归一化参数（试算工具要用它），否则"试算通过、
                # 正式编译不通过"会变成一条查不出来的分叉。
                complexity_profile=complexity_profile,
                architecture_profile=architecture_profile,
            )
        except Exception as exc:
            # 红线 4：模型故障不把整轮生成掐掉。图纸仍然可用，如实记账即可。
            logger.warning(f"[convergence] 重出设计块时模型故障，保留原图纸: {exc}")
            stop_reason = "model_error"
            rounds.append(
                {
                    "blocks": blocks,
                    "defects_before": len(blocking),
                    "model_error": str(exc),
                }
            )
            break

        if not draft:
            # 一块都没写出来 ⇒ 图纸一个字节没变，再转一圈是纯烧钱。
            stop_reason = "no_draft"
            rounds.append(
                {
                    "blocks": blocks,
                    "defects_before": len(blocking),
                    "settled": [],
                    "unsettled": list(block_diag.get("unsettled_blocks") or []),
                }
            )
            break

        merged = {**raw, **draft}
        try:
            candidate = normalize_architecture_plan(
                merged,
                user_message=user_message,
                complexity_profile=complexity_profile,
                architecture_profile=architecture_profile,
            )
        except Exception as exc:
            # 🔴 **模型给的草稿是不可信输入**：归一化一旦抛错（实测有一条
            # `ground[entrance_bay - 1]` 越界），异常会一路穿出节点、把整轮生成掐掉——
            # 而上一版图纸**本来是可以编译的**。这正是"收敛失败不阻断"要挡住的事。
            # 注意这里**只**护归一化：编译器的崩溃是我们自己的 bug，必须暴露出来。
            logger.warning(f"[convergence] 修订后的图纸归一化失败，保留上一版: {exc}")
            stop_reason = "invalid_revision"
            rounds.append(
                {
                    "blocks": blocks,
                    "defects_before": len(blocking),
                    "normalize_error": str(exc),
                }
            )
            break
        outcome = compile_design(candidate, **compile_kwargs)
        count = len(blocking_defects(outcome))

        rounds.append(
            {
                "blocks": blocks,
                "defects_before": len(blocking),
                "defects_after": count,
                "unsettled": list(block_diag.get("unsettled_blocks") or []),
            }
        )

        # 判进展只看**条数**：fingerprint 里带数值，改对一点点就整串变样（见 defect_fingerprint）。
        no_progress = no_progress + 1 if count >= last_count else 0
        current, raw, result, last_count = candidate, merged, outcome, count

        if no_progress >= max(1, int(max_no_progress)):
            stop_reason = "no_progress"
            break

    diag = _diag(rounds, stop_reason)
    diag["level"] = level
    diag["raw_plan_available"] = bool(raw_plan)
    if stop_reason not in ("converged",):
        logger.warning(
            f"[convergence] 未完全收敛（{stop_reason}）："
            f"{diag['initial_defects']} → {diag['final_defects']} 条 error 缺陷"
        )
    return ConvergenceOutcome(plan=current, changed=diag["changed"], diag=diag)


__all__ = [
    "ConvergenceOutcome",
    "blocking_defects",
    "converge_design",
    "defect_fingerprint",
    "design_level_defects",
]
