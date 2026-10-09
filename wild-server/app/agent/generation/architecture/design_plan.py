"""设计期工作条目：把「分块起草」跑在 plan 的调度语义上（设计文档 §1.6）。

为什么要有这一层：块表（`design_blocks.DESIGN_BLOCKS`）**已经**用 `parallel_group`
声明了「哪几块可以并发」（`shell` = 结构 / 立面 / 屋顶），但那一直只是**声明** ——
`draft_design_blocks` 是纯串行 for 循环，于是那份声明空转，设计期永远是「一块一块排队」，
plan 这个节点也完全没参与图纸。

本模块把块表**确定性展开**成 plan 条目，交给既有的 `plan.store` 状态机调度：

- **依赖**来自块表的 ``depends_on``。它是**物理约束，不由模型产出** ——
  "先体量后立面"不是设计决策，让模型产出它只是白烧一次调用（`design_blocks` 里已记）。
- **并发** = 同一 ``parallel_group`` 且都 ``ready`` 的条目一次派发（:func:`next_batch`）。
- **有界重试** = ``ItemRun.max_attempts``（与 :data:`design_workflow._BLOCK_MAX_ATTEMPTS` 同源）。
- **计划态推导** = `refresh_statuses`。``abandoned`` 是终态 ⇒ 某块试满上限也**不会锁死下游**，
  仍然落到既有的"留空交下游归一化兜底"（用户红线：失败不阻断）。

条目 id 是 ``draft_<块名>``（确定性、可复现）；``op`` 取闭集里的 ``generate`` ——
"起草一个设计块"就是一次生成，不为它单开一个 op（开 op 要同批补执行器与测试）。
``kind`` 承载块名，``params.parallel_group`` 承载并发组。

 这份计划**不进 ``state.plan``**：它是设计期的内部调度，与"构件生成计划"是两份数据
（后者的 ``kind`` 是构件类型，条目里还有 ``merge`` / ``validate``）。混进一份里会让
``reconcile`` / ``expand`` 去处理它们不认识的条目。
"""

from __future__ import annotations

from typing import Any, Sequence

from app.agent.generation.architecture.design_blocks import DesignBlock
from app.agent.plan.contracts import ItemRun, PlanDocument, PlanItem
from app.agent.plan.store import (
    mark_running,
    new_plan,
    poll_runnable,
    record_result,
    refresh_statuses,
    set_status,
)

#: 一次最多并发几条。与 `plan.workflow._MAX_PARALLEL_ITEMS` 同一个量级：
#: 并发是用来吃掉网络往返延迟的，不是用来打满模型配额的。
MAX_DESIGN_PARALLEL = 3

#: 条目 id 前缀。确定性 id 是硬要求（`plan.contracts` 的模块约定）：同一份输入两次运行
#: 必须产出同一份计划，否则回归样例与双跑对照都失去意义。
_ITEM_ID_PREFIX = "draft_"

#: `PlanDocument.detail_level` 是闭集；认不出的档位按 ``standard`` 处理
#: （与 `design_blocks.blocks_for_level` 同一口径：宁可多写不可少写）。
_DETAIL_LEVELS = ("minimal", "simple", "standard", "detailed")


def design_item_id(block_name: str) -> str:
    return f"{_ITEM_ID_PREFIX}{block_name}"


def build_design_plan(
    blocks: Sequence[DesignBlock],
    *,
    level: str,
    max_attempts: int,
) -> PlanDocument:
    """把设计块表展开成一份 plan。

    依赖只保留**也在本计划里**的块：收敛环用 ``only_blocks`` 只重出受影响的块，
    留下的悬空依赖会让 :func:`plan.store.refresh_statuses` 永远推不出 ``ready``
    （条目被永久丢弃在 ``blocked``，表现为"重出之后图纸没变，也没报错"）。
    """

    selected = {block.name for block in blocks}
    details = str(level or "").strip().lower()
    items = [
        PlanItem(
            id=design_item_id(block.name),
            op="generate",
            kind=block.name,
            label=block.name,
            depends_on=[
                design_item_id(dependency)
                for dependency in block.depends_on
                if dependency in selected
            ],
            params={"parallel_group": block.parallel_group or ""},
            run=ItemRun(max_attempts=max(1, int(max_attempts))),
        )
        for block in blocks
    ]
    return new_plan(
        items,
        detail_level=details if details in _DETAIL_LEVELS else "standard",
    )


def next_batch(
    plan: PlanDocument,
    max_parallel: int = MAX_DESIGN_PARALLEL,
) -> list[PlanItem]:
    """本轮可安全并发的条目：第一条可执行 + 同并发组且未落定的兄弟。

    **串行是默认**：并发必须由块表的 ``parallel_group`` 显式声明 ——
    组为空就只返回第一条（`structure` / `facade` / `roof` 之外都不声明并发）。
    """

    first = poll_runnable(plan)
    if first is None:
        return []
    group = str(first.params.get("parallel_group") or "")
    if not group:
        return [first]
    selected = [
        item
        for item in plan.items
        if item.status == "ready"
        and item.run.state != "succeeded"
        and str(item.params.get("parallel_group") or "") == group
    ]
    return selected[: max(1, int(max_parallel))] or [first]


def start_batch(plan: PlanDocument, batch: Sequence[PlanItem]) -> PlanDocument:
    """把这批条目置为 ``running``（纯观测口径，不改计划态）。"""

    updated = plan
    for item in batch:
        updated, _running = mark_running(updated, item.id)
    return updated


def apply_batch_outcomes(
    plan: PlanDocument,
    outcomes: Sequence[tuple[str, bool, int, str]],
) -> PlanDocument:
    """写入一批条目的执行态，并推一次计划态。

    ``outcomes`` 每项是 ``(item_id, settled, attempts, evidence)``。

    - ``settled=True`` → ``succeeded`` / ``done``：依赖据此推导 ``ready``；
    - ``settled=False`` → ``failed`` / ``abandoned``：``abandoned`` 是**终态**，
      所以某块写不出来不会锁死它的下游，仍然是"留空交下游兜底"。

    ``attempts`` 用**实际**次数覆盖，而不是 ``+1`` —— 它必须与 ``architecture_diag``
    里的 ``attempts`` 逐条对得上，否则"哪一块最难写"没法从审计里读出来。
    """

    updated = plan
    for item_id, settled, attempts, evidence in outcomes:
        updated = record_result(
            updated,
            item_id,
            state="succeeded" if settled else "failed",
            evidence=evidence,
            count_attempt=False,
        )
        item = updated.item(item_id)
        if item is not None:
            item.run.attempts = max(0, int(attempts))
        updated = set_status(
            updated,
            item_id,
            "done" if settled else "abandoned",
            evidence=evidence,
        )
    return refresh_statuses(updated)


__all__ = [
    "MAX_DESIGN_PARALLEL",
    "apply_batch_outcomes",
    "build_design_plan",
    "design_item_id",
    "next_batch",
    "start_batch",
]
