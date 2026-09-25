"""对账：把蓝图与分片的**事实**回写为条目结果。

对应《动态节点设计规划》§5.2。两条不变量：

1. **只有这里能写计划态**（``status``）。处理器与模型都不许自报完成——"节点跑完 ≠
   业务要求完成"这条老问题在这里被结构性地解决：产物不存在、或存在但没并进蓝图，
   条目都不会变成 ``done``。
2. **每次改动蓝图之后都要重新对账**。配额强制、阳台去重、``fix_*`` 都会删改元素，
   漂移是静默的，只有重跑对账才能发现。

几何比对复用 ``validation/design_constraints.py`` 的 ``_opening_values_match``（容差 0.01），
与现有设计约束校验同一口径。
"""

from __future__ import annotations

from typing import Any

from app.agent.generation.components import COMPONENT_REGISTRY
from app.agent.plan.contracts import PlanDocument, PlanItem
from app.agent.plan.store import refresh_statuses, reset_for_retry, set_evidence, set_status
from app.agent.validation.design_constraints import _opening_values_match


def _geometry(blueprint: Any) -> tuple[list[dict], list[dict]]:
    if not isinstance(blueprint, dict):
        return [], []
    geometry = blueprint.get("geometry")
    if not isinstance(geometry, dict):
        return [], []
    elements = [item for item in geometry.get("elements", []) if isinstance(item, dict)]
    components = [item for item in geometry.get("components", []) if isinstance(item, dict)]
    return elements, components


def _produced_count(fragments: Any) -> int:
    if isinstance(fragments, list):
        return len([item for item in fragments if item])
    if isinstance(fragments, dict):
        return 1
    return 0


def _landed_count(kind: str, elements: list[dict], components: list[dict]) -> int:
    config = COMPONENT_REGISTRY.get(kind)
    bucket = elements if config is not None and config.is_element else components
    return len([entry for entry in bucket if entry.get("type") == kind])


def _slot_match(kind: str, design_brief: Any, components: list[dict]) -> tuple[int, int]:
    """按槽位逐项比对（门窗类构件的主要验收口径）。

    返回 ``(落地数, 槽位数)``；没有槽位时返回 ``(0, 0)``，由调用方回退到数量口径。
    """

    if not isinstance(design_brief, dict):
        return 0, 0
    slots = [
        slot
        for slot in design_brief.get("opening_slots", []) or []
        if isinstance(slot, dict) and slot.get("type") == kind
    ]
    if not slots:
        return 0, 0

    # 凸窗按既有约定可以占用普通窗位（design_constraints 的口径保持一致）。
    candidate_types = {kind}
    if kind == "window":
        candidate_types.add("bay_window")
    unmatched = [entry for entry in components if entry.get("type") in candidate_types]

    matched = 0
    for slot in slots:
        index = next(
            (
                position
                for position, entry in enumerate(unmatched)
                if entry.get("parentWall") == slot.get("wall_id")
                and _opening_values_match(entry.get("from"), slot.get("from"))
                and _opening_values_match(entry.get("width"), slot.get("width"))
                and _opening_values_match(entry.get("height"), slot.get("height"))
            ),
            None,
        )
        if index is None:
            continue
        matched += 1
        unmatched.pop(index)
    return matched, len(slots)


def _batch_merge_has_run(plan: PlanDocument, item: PlanItem) -> bool:
    """该条目的分片是否已经被并进蓝图（它的批次 ``merge`` 跑过）。

    用来区分 ``generate`` 的两种中间态："还没到合并那一步"（继续等，不算失败）与
    "合并过了但产物没落地"（算一次重试）。
    """

    return any(
        other.op == "merge" and item.id in other.depends_on and other.run.state != "idle"
        for other in plan.items
    )


def _final_merge_has_run(plan: PlanDocument) -> bool:
    """收尾合并是否跑过。

    **只有收尾合并有权删改元素**（配额强制、阳台去重、``fix_*`` 都在它里面），
    所以只有它能成为"产物没落地"的判据。批次合并不删不改，拿它当判据会把
    "还没归一"误判成"被删掉了"，白白烧掉重试额度。
    """

    return any(item.is_final_merge and item.run.state != "idle" for item in plan.items)


def _resolve_generate(
    item: PlanItem,
    plan: PlanDocument,
    state: dict[str, Any],
    elements: list[dict],
    components: list[dict],
) -> tuple[str | None, str, bool]:
    """返回 ``(新计划态, 证据, 是否计一次尝试)``；状态为 ``None`` 表示本轮不动它。"""

    fragments = (state.get("component_fragments") or {}).get(item.kind)
    produced = _produced_count(fragments)
    landed = _landed_count(item.kind, elements, components)
    matched, slots = _slot_match(item.kind, state.get("design_brief"), components)

    if slots:
        evidence = f"{item.label}：槽位落地 {matched}/{slots}，蓝图元素 {landed} 个"
        if matched >= slots and matched > 0:
            return "done", evidence, False
    else:
        evidence = f"{item.label}：已产出 {produced} 个，蓝图落地 {landed} 个"
        if produced > 0 and landed >= produced:
            return "done", evidence, False

    if item.run.state == "failed":
        # 执行失败的原因优先于尚未落地的结果，避免重规划把工具错误当成数量问题。
        if item.run.evidence:
            evidence = item.run.evidence
        if item.run.exhausted:
            suffix = "（重试耗尽）"
            return "abandoned", evidence if evidence.endswith(suffix) else evidence + suffix, False
        suffix = "（等待重试）"
        return "ready", evidence if evidence.endswith(suffix) else evidence + suffix, False
    if item.run.state == "succeeded":
        if not _batch_merge_has_run(plan, item):
            # 已产出，只等批次合并把它并进蓝图。本条不再可执行（store.poll_runnable）。
            return "ready", evidence + "（等待合并）", False
        if not _final_merge_has_run(plan):
            # 批次合并跑过了，但槽位吸附与配额强制只在收尾合并里做。此刻判"没落地"
            # 会误计重试，所以先等收尾归一——它跑完还没落地，才是真的没落地。
            return "ready", evidence + "（等待收尾归一）", False
        # 收尾归一跑过了仍然没落地：产物被去重/配额强制删掉了，计一次重试。
        return "ready", evidence + "（产物未并入蓝图）", True
    return None, evidence, False


def _resolve_simple(item: PlanItem, state: dict[str, Any]) -> tuple[str | None, str]:
    """merge / validate / fix / repair 的通用判定：执行态决定终态。"""

    if item.run.state == "idle":
        # 还没跑过：不动状态，也不写证据（避免每轮都刷一遍 label）。
        return None, ""
    evidence = item.run.evidence or item.label
    if item.run.state == "succeeded":
        return "done", evidence
    if item.run.state == "failed":
        if item.run.exhausted:
            return "abandoned", evidence + "（重试耗尽）"
        return "ready", evidence
    if item.run.state == "aborted":
        return "abandoned", evidence or "已中止"
    return None, evidence


def reconcile(
    plan: PlanDocument,
    state: dict[str, Any],
) -> tuple[PlanDocument, list[dict[str, Any]]]:
    """对账一次，返回 ``(新计划, 状态变化事件)``。

    事件供前端进度面板使用；只有发生状态变化的条目才会出现一条事件。
    """

    elements, components = _geometry(state.get("merged_blueprint"))
    events: list[dict[str, Any]] = []
    updated = plan

    for item in plan.items:
        if item.is_terminal:
            continue

        if item.op == "generate":
            new_status, evidence, consume_attempt = _resolve_generate(
                item, plan, state, elements, components
            )
        elif item.op in {"merge", "validate", "fix", "repair"}:
            new_status, evidence = _resolve_simple(item, state)
            consume_attempt = False
        else:  # pragma: no cover - op 是闭集，防御性分支
            new_status, evidence, consume_attempt = None, item.label, False

        if consume_attempt:
            # 产物没落地 → 计一次尝试后重跑（尝试耗尽自动转 abandoned）
            updated = reset_for_retry(updated, item.id, evidence=evidence)
            item = updated.item(item.id) or item
            events.append(
                {
                    "item_id": item.id,
                    "label": item.label,
                    "op": item.op,
                    "kind": item.kind,
                    "status": item.status,
                    "evidence": item.run.evidence,
                    "elapsed_ms": item.run.elapsed_ms,
                }
            )
        elif new_status is not None and new_status != item.status:
            updated = set_status(updated, item.id, new_status, evidence=evidence)
            events.append(
                {
                    "item_id": item.id,
                    "label": item.label,
                    "op": item.op,
                    "kind": item.kind,
                    "status": new_status,
                    "evidence": evidence,
                    "elapsed_ms": item.run.elapsed_ms,
                }
            )
        elif evidence and evidence != item.run.evidence:
            # 状态没变但事实变了（例如"产出了片段但槽位没对上"）：留证据，不产生事件。
            updated = set_evidence(updated, item.id, evidence)

    return refresh_statuses(updated), events


def ensure_artifact_consistency(plan: PlanDocument, state: dict[str, Any]) -> PlanDocument:
    """出交付清单前的最后一道断言（§5.2）：

    把已标 ``done`` 但产物已从蓝图消失的条目重新打开——配额强制、去重、``fix_*``
    都可能删掉元素，而这类漂移不会报错。

    "重新打开"必须走 ``reset_for_retry`` 而不是只改计划态：状态改回 ``ready`` 但执行态
    仍是 ``succeeded`` 的话，``poll_runnable`` 会跳过它（产物已出、只等合并），
    条目既跑不动也交付不了，只能等预算耗尽，变成静默卡死。计一次尝试则让重跑有上界。
    """

    elements, components = _geometry(state.get("merged_blueprint"))
    updated = plan
    for item in plan.items:
        if item.op != "generate" or item.status != "done":
            continue
        landed = _landed_count(item.kind, elements, components)
        if landed == 0:
            updated = reset_for_retry(
                updated, item.id, evidence="产物已不在蓝图中，重新对账"
            )
    return updated
