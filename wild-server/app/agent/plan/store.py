"""plan 的确定性 CRUD 与状态推进。

对应《动态节点设计规划》§2.6 与 §5.2：这里集中管理条目的增删改与状态推进，
处理器与节点不各自改 plan（对照 Claude Code 的 ``utils/task/framework.ts``）。

本模块全部是纯函数：不读外部状态、不调用模型、不使用随机数。
所有修改都在副本上进行并整体返回，便于单测与幂等重放。
"""

from __future__ import annotations

from app.agent.plan.contracts import (
    TERMINAL_STATUSES,
    ItemRun,
    PlanDocument,
    PlanHistoryEntry,
    PlanItem,
)


def _copy(plan: PlanDocument) -> PlanDocument:
    return plan.model_copy(deep=True)


def find_item(plan: PlanDocument, item_id: str) -> PlanItem | None:
    return plan.item(item_id)


def new_plan(
    items: list[PlanItem],
    *,
    detail_level: str = "standard",
    budget: dict[str, int] | None = None,
) -> PlanDocument:
    """由条目列表建立一份 PlanDocument（revision 从 1 开始）。"""

    plan = PlanDocument(
        detail_level=detail_level,  # type: ignore[arg-type]
        budget=dict(budget or {}),
        items=[item.model_copy(deep=True) for item in items],
    )
    return refresh_statuses(plan)


def is_settled(item: PlanItem) -> bool:
    """依赖是否已"落定"：进了终态，或本轮已成功产出。

    **依赖的语义是"产物可用"，不是"上游成功"**：``merge`` 必须在某个 ``generate``
    失败时照常运行（分片已在 ``component_fragments`` 里），否则局部失败会拖死整条链，
    违背"能力缺失只标记不阻断"的政策。

    这条判定还解开了一个真实死锁：``generate`` 要等 ``merge`` 把元素并进蓝图才算
    ``done``，而 ``merge`` 又依赖 ``generate``——按"依赖 = 上游终态"推导永远等不到。
    """

    return item.is_terminal or item.run.state == "succeeded"


#: 会"吃上游产物"的 op。上游被退回重跑之后，它们必须跟着重跑，否则新产物进不了蓝图。
_DOWNSTREAM_OPS: frozenset[str] = frozenset({"merge", "validate", "fix", "repair"})


def upstream_ids(item: PlanItem, items: list[PlanItem]) -> list[str]:
    """判定该条目"上游是否落定"要看的 id 集合。

    普通条目看 ``depends_on``。**收尾条目（全量校验、收尾合并）看全部生产条目**——
    它们的输入是"所有分片"，不是某几条 ``depends_on``：若只按 ``depends_on`` 判断，
    replanner 追加的条目会让收尾步骤一直保持 ``done``，新产物被静默丢弃。

    注意收尾条目的上游只算 ``generate`` 与批次 ``merge``，不算别的收尾条目——
    否则收尾合并与校验会互相当成对方的上游，永远重开。
    """

    upstream = list(item.depends_on)
    if item.op == "validate" or item.is_final_merge:
        upstream += [
            other.id for other in items if other.op == "generate" or other.is_batch_merge
        ]
    return upstream


def refresh_statuses(plan: PlanDocument) -> PlanDocument:
    """按依赖推导计划态：依赖落定 → ``ready``；上游被退回 → 已完成的下游条目重开。

    两条规则，都只是**推导**，不引入新状态：

    1. ``pending`` / ``blocked`` 且依赖全部落定 → ``ready``（悬空依赖永远落定不了，
       条目保持 ``blocked``，由结构校验 §2.7 拦）；
    2. 已完成（``done``）的下游条目，只要有上游没落定 → 退回 ``ready`` 并清执行态。
       没有这条，一次重试就会让批次/收尾合并保持 ``done``，重跑出来的新指标永远
       并不进蓝图——这是静默丢产物，比报错更难发现。

    不碰其它终态（``abandoned`` / ``skipped`` / ``unsupported``）：它们是"决定不做"，
    不是"做完了"，上游重跑不该把它们拉回来。

    只跑一趟，因此要求 ``plan.items`` 本身是拓扑序（展开规则保证：
    generate → 批次 merge → 收尾 merge → validate）。replanner 追加的条目挂在表尾，
    且不是收尾条目的上游，所以不破坏这个前提。
    """

    updated = _copy(plan)
    items = updated.items
    settled = {item.id for item in items if is_settled(item)}

    for item in items:
        upstream = upstream_ids(item, items)
        if item.status in {"pending", "blocked"}:
            item.status = "ready" if all(dep in settled for dep in upstream) else "blocked"
            continue
        if (
            item.status == "done"
            and item.op in _DOWNSTREAM_OPS
            and not all(dep in settled for dep in upstream)
        ):
            item.status = "ready"
            item.run.state = "idle"
            settled.discard(item.id)
    return updated


def poll_runnable(plan: PlanDocument) -> PlanItem | None:
    """取第一条可执行条目。

    规则（§4.1）：列表顺序即执行顺序，不排序、不依赖字典遍历顺序。
    已经成功产出、只等 ``merge`` 把它并进蓝图的条目不算可执行——否则第一轮跑完的
    条目会被反复重跑，队列永远走不到 ``merge``。
    """

    for item in plan.items:
        if item.status == "ready" and item.run.state != "succeeded":
            return item
    return None


def mark_running(plan: PlanDocument, item_id: str) -> tuple[PlanDocument, PlanItem | None]:
    updated = _copy(plan)
    item = updated.item(item_id)
    if item is None:
        return updated, None
    item.run.state = "running"
    return updated, item


def record_result(
    plan: PlanDocument,
    item_id: str,
    *,
    state: str,
    artifacts: list[str] | None = None,
    evidence: str = "",
    elapsed_ms: int | None = None,
    count_attempt: bool = True,
) -> PlanDocument:
    """写入一条条目的执行态。

    ``count_attempt`` 表示本次是否计入重试次数：成功与模型服务故障不计，
    普通失败计一次（§4.5 的 per-item 预算）。
    """

    updated = _copy(plan)
    item = updated.item(item_id)
    if item is None:
        return updated
    run = item.run if isinstance(item.run, ItemRun) else ItemRun()
    run.state = state  # type: ignore[assignment]
    if count_attempt:
        run.attempts += 1
    if artifacts is not None:
        run.artifacts = list(artifacts)
    run.evidence = evidence[:2000]
    if elapsed_ms is not None:
        run.elapsed_ms = elapsed_ms
    item.run = run
    return updated


def set_status(
    plan: PlanDocument,
    item_id: str,
    status: str,
    *,
    evidence: str | None = None,
) -> PlanDocument:
    """写计划态。只有 ``replanner``（reconcile）与 plan 阶段的结构判定可以调用。"""

    updated = _copy(plan)
    item = updated.item(item_id)
    if item is None:
        return updated
    item.status = status  # type: ignore[assignment]
    if evidence is not None:
        item.run.evidence = evidence[:2000]
    return updated


def reset_for_retry(plan: PlanDocument, item_id: str, *, evidence: str = "") -> PlanDocument:
    """把一条条目退回可执行：清执行态、计一次尝试。

    用途：条目本轮成功产出了，但产物没能并入蓝图（例如被配额强制删掉）。
    这时不能反复重跑同一条，也不能直接标 ``done``；只能计一次尝试后重跑，
    尝试耗尽就转 ``abandoned`` 进交付清单。
    """

    updated = _copy(plan)
    item = updated.item(item_id)
    if item is None:
        return updated
    item.run.attempts += 1
    item.run.state = "idle"
    if item.run.attempts >= item.run.max_attempts:
        item.status = "abandoned"
        item.run.evidence = (evidence or item.run.evidence) + "（重试耗尽）"
    else:
        item.status = "ready"
        item.run.evidence = evidence or item.run.evidence
    return updated


def set_evidence(plan: PlanDocument, item_id: str, evidence: str) -> PlanDocument:
    """只更新证据，不改状态。

    用途：状态没变但事实变了（例如"产出了片段但槽位没对上"），不留证据的话
    前端只能看到一条条一直 ``ready`` 的条目，无法归因。
    """

    updated = _copy(plan)
    item = updated.item(item_id)
    if item is None:
        return updated
    item.run.evidence = evidence[:2000]
    return updated


def append_items(
    plan: PlanDocument,
    items: list[PlanItem],
    *,
    reason: str = "",
    max_revision: int = 2,
) -> tuple[PlanDocument, bool]:
    """追加条目（``origin=emergent``）并递增 revision。

    返回 ``(plan, appended)``；``appended=False`` 表示已到追加上限（§5.4）。
    """

    if not items:
        return plan, False
    if plan.revision >= max_revision:
        return plan, False

    updated = _copy(plan)
    known = {item.id for item in updated.items}
    fresh: list[PlanItem] = []
    for item in items:
        if item.id in known:
            continue
        emergent = item.model_copy(deep=True)
        emergent.origin = "emergent"
        fresh.append(emergent)
        known.add(emergent.id)
    if not fresh:
        return plan, False

    updated.items.extend(fresh)
    updated.revision += 1
    updated.history.append(
        PlanHistoryEntry(
            revision=updated.revision,
            action="append_items",
            item_ids=[item.id for item in fresh],
            reason=reason[:500],
        )
    )
    return refresh_statuses(updated), True


def terminal_stats(plan: PlanDocument) -> dict[str, int]:
    """交付清单的统计口径（§6.4）：四个终态 + 未完成数量必须可校验。"""

    stats = {"total": len(plan.items), "done": 0, "abandoned": 0, "skipped": 0,
             "unsupported": 0, "unfinished": 0}
    for item in plan.items:
        if item.status in TERMINAL_STATUSES:
            stats[item.status] += 1
        else:
            stats["unfinished"] += 1
    return stats


def counts_are_consistent(plan: PlanDocument) -> bool:
    stats = terminal_stats(plan)
    return (
        stats["done"] + stats["abandoned"] + stats["skipped"] + stats["unsupported"]
        + stats["unfinished"]
        == stats["total"]
    )
