"""Bounded pre-approval design completion using the existing block executor."""
from __future__ import annotations

import json
from typing import Any

from app.design.contracts import DesignDocument
from app.design.normalization import semantic_design_fingerprint
from app.design.resolver import architecture_plan_from_document, _stable_hash
from app.design.compilation import compile_document, project_compilation
from .design_blocks import ordered_blocks, block_of_design_field
from .design_workflow import draft_design_blocks
from .revision_patch import apply_design_patch

_ACTIONABLE_WARNINGS = frozenset({"design_instance_uncompiled", "material_region_unapplied"})


def _actionable(defect):
    return defect.severity == "error" or defect.code in _ACTIONABLE_WARNINGS

_COMPLETION_PROMPT = """你在人工审核前完善当前设计。只解决给定缺口，不进行无依据的装饰扩张。
保留用户要求及已采用决定；不要通过修改 design_constraints、expected 或删除要求伪造完成。
在选定设计块的现有协议内修改；关系无法表达则保留缺口，不发明新 Schema。
当前是设计完善任务，可以在指定体量/立面等块内新增有依据的设计对象；不能修改其他块。
最终是否完成由当前设计与编译证据判定，你的成功声明不算完成证据。
"""


class RevisionModelError(RuntimeError):
    def __init__(self, message, model_calls=0):
        super().__init__(message)
        self.model_calls = model_calls


async def _run_revision(payload: dict, callback=None):
    """Checkpoint completed model batches when running inside LangGraph."""
    from langgraph.config import get_config
    try:
        config = get_config()
    except RuntimeError:
        config = {}
    if "__pregel_call" in config.get("configurable", {}):
        from .revision_task import draft_revision_task
        outcome = await draft_revision_task(payload)
        if outcome.get("error"):
            raise RevisionModelError(outcome["error"], outcome.get("model_calls", 0))
        return outcome["patch"], outcome["diagnostics"]
    accounting = {"model_calls": 0}
    try:
        return await draft_design_blocks(**payload, on_reasoning_delta=callback, call_accounting=accounting)
    except Exception as exc:
        raise RevisionModelError(str(exc), accounting["model_calls"]) from exc


def _block(target: str):
    return block_of_design_field(target.strip("/").replace("/", "."))


def _signature(result, resolved) -> set[str]:
    return {g.id for g in resolved.design_gaps if g.status != "satisfied"} | {
        f"compile:{d.code}:{d.target}:{d.design_field}" for d in result.defects
        if _actionable(d)
    }


def plan_design_tasks(document, result, resolved, *, round_index: int, only_blocks=None):
    """Deterministically create work only from evidence; the LLM chooses the design fix."""
    by_block: dict[str, list[dict]] = {}
    for gap in resolved.design_gaps:
        block = _block(gap.target)
        if gap.status == "open" and block:
            by_block.setdefault(block.name, []).append(gap.model_dump(mode="json"))
    for defect in result.defects:
        block = _block(defect.design_field)
        if _actionable(defect) and block:
            by_block.setdefault(block.name, []).append({"id": f"compile:{defect.code}:{defect.target}:{defect.design_field}",
                "layer": "design", "category": "compilability", "target": defect.design_field, "evidence": defect.evidence})
    # 只由可能改变几何的字段失效依赖；concept/说明不触发全块重写。
    geometry_targets = ("/decisions/volumes", "/decisions/massing/width", "/decisions/massing/depth",
                        "/decisions/massing/floors", "/decisions/massing/modeled_floors",
                        "/decisions/massing/floor_height", "/decisions/massing/shape", "/decisions/massing/tiers")
    massing_evidence = by_block.get("massing") or []
    geometry_revision = any(("/" + str(g.get("target") or "").strip("/").replace(".", "/"))
                            .startswith(geometry_targets) for g in massing_evidence)
    if geometry_revision:
        for name in ("structure", "facade", "roof", "components"):
            by_block.setdefault(name, []).append({"id": "dependency:massing",
                "evidence": "体量几何修订必须原子核对楼层、开口、屋面与实例宿主"})
    if only_blocks is not None:
        if geometry_revision and not {"massing", "structure", "facade", "roof", "components"} <= set(only_blocks):
            # 限定块不足以原子修订几何，留下缺口；不能悄悄裁掉依赖。
            return []
        by_block = {k:v for k,v in by_block.items() if k in only_blocks}
    tasks = []
    for b in ordered_blocks("standard"):
        if b.name not in by_block:
            continue
        tasks.append({"id": f"design_r{document.revision}_{round_index}_{b.name}",
            "block": b.name, "base_revision": document.revision, "base_hash": _stable_hash(document),
            "gap_ids": [g["id"] for g in by_block[b.name]], "evidence": by_block[b.name],
            "write_fields": [f for f in b.fields if f != "design_constraints"],
            "depends_on": [t["id"] for t in tasks if t["block"] in b.depends_on],
            "completion_condition": "当前版本关联缺口关闭，且对应设计表达已编译落实", "status": "pending"})
    return tasks


def _task_groups(tasks: list[dict]) -> list[list[dict]]:
    groups = []
    for task in tasks:
        connected = [group for group in groups if any(t["id"] in task["depends_on"] for t in group)]
        merged = [task]
        for group in connected:
            merged.extend(group)
            groups.remove(group)
        groups.append(merged)
    return groups


def select_task_group(tasks: list[dict], remaining_calls: int) -> tuple[list[dict], list[dict]]:
    """选择预算可容纳的完整依赖组，不拆开原子修订。"""
    groups = _task_groups(tasks)
    selected = next((group for group in sorted(groups, key=len) if len(group) <= remaining_calls), [])
    chosen = {t["id"] for t in selected}
    return [t for t in tasks if t["id"] in chosen], [t for t in tasks if t["id"] not in chosen]


async def complete_design(*, document: dict, user_message: str, complexity_profile,
                          architecture_profile, thinking_mode: bool, max_rounds: int,
                          max_no_progress: int, on_reasoning_delta=None, only_blocks=None):
    from .convergence import ConvergenceOutcome

    current = DesignDocument.model_validate(document)
    original = current.model_dump(mode="json")
    if current.status != "draft":
        return ConvergenceOutcome(plan=architecture_plan_from_document(current), changed=False,
            diag={"stop_reason": "approval_boundary", "initial_defects": 0, "final_defects": 0,
                  "revisions": 0, "rounds": [], "unresolved": [], "converged": False}, document=original)
    result = compile_document(current)
    resolved = project_compilation(current, result)
    initial_defects = sum(_actionable(d) for d in result.defects)
    tasks_log, rounds = [], []
    # One model invocation per selected block, no internal probe or retry calls.
    call_budget = 9
    calls = 0
    reserved = 0
    no_progress = 0
    seen_designs = {semantic_design_fingerprint(current)}
    stop = "max_rounds"
    for round_index in range(max(0, max_rounds)):
        tasks = plan_design_tasks(current, result, resolved, round_index=round_index, only_blocks=only_blocks)
        if not tasks:
            stop = "satisfied" if not any(g.status != "satisfied" for g in resolved.design_gaps) and not any(d.severity == "error" for d in result.defects) else "needs_review"
            break
        tasks, _ = select_task_group(tasks, call_budget-calls)
        if not tasks:
            stop = "model_budget"
            break
        base_hash = _stable_hash(current)
        blocks = [t["block"] for t in tasks]
        before = _signature(result, resolved)
        if on_reasoning_delta:
            await on_reasoning_delta("architecture:progress", "\n### 设计完善\n"+"、".join(f"{t['block']}: {', '.join(t['gap_ids'])}" for t in tasks)+"\n")
        plan = architecture_plan_from_document(current)
        materials = current.decisions.materials.resolved_plan
        context = {**plan, "material_plan": materials.model_dump(mode="json") if materials else None}
        reserved += len(tasks)
        normalization_changes = []
        candidate_hash = None
        block_diag = {}
        actual_calls = 0
        try:
            patch, block_diag = await _run_revision(dict(
                base_prompt=_COMPLETION_PROMPT+"\n本轮任务与完成条件：\n"+json.dumps(tasks, ensure_ascii=False),
                user_request=user_message, thinking_mode=thinking_mode, only_blocks=blocks,
                complexity_profile=complexity_profile, architecture_profile=architecture_profile,
                current_plan=context, allow_probe=False, allow_design_changes=True, max_attempts=1,
            ), on_reasoning_delta)
            actual_calls = int(block_diag.get("model_calls") or 0)
            calls += actual_calls
            if _stable_hash(current) != base_hash:
                raise ValueError("stale_patch: 任务依据的设计版本已过期")
            if not patch or block_diag.get("unsettled_blocks"):
                raise ValueError("设计块未全部完成，保留当前有效设计")
            candidate, normalization_changes, derived_changes = apply_design_patch(
                current, patch, allowed_blocks=blocks, user_message=user_message,
                complexity_profile=complexity_profile, architecture_profile=architecture_profile,
            )
            candidate_hash = semantic_design_fingerprint(candidate)
            if candidate_hash in seen_designs:
                raise ValueError("设计反复回到已出现版本，停止重复应用补丁")
            seen_designs.add(candidate_hash)
            candidate_result = compile_document(candidate)
            candidate_resolved = project_compilation(candidate, candidate_result)
            after = _signature(candidate_result, candidate_resolved)
            # Satisfied adopted goals cannot be sacrificed to close a different gap.
            satisfied = {g.id for g in resolved.design_gaps if g.status == "satisfied"}
            candidate_status = {g.id: g.status for g in candidate_resolved.design_gaps}
            if any(candidate_status.get(gap_id) != "satisfied" for gap_id in satisfied):
                raise ValueError("补丁破坏已满足的设计决定")
            old_errors = {x for x in before if x.startswith("compile:")}
            if {x for x in after if x.startswith("compile:")} - old_errors:
                raise ValueError("补丁引入新的编译错误")
            closed = {gap_id for gap_id in before
                      if (gap_id.startswith("compile:") and gap_id not in after)
                      or candidate_status.get(gap_id) == "satisfied"}
            # 消失/unsupported/改 ID 不算设计要求闭合；只有明确收益才替换当前版本。
            required_ids = {g.id for g in resolved.design_gaps}
            if not required_ids <= set(candidate_status):
                raise ValueError("候选丢失稳定要求 ID")
            if not closed:
                raise ValueError("候选没有可证明的缺口闭合，拒绝写回")
            authorized_roots = {field for task in tasks for field in task["write_fields"]}
            changed_roots = {key for key in candidate.decisions.model_dump()
                             if candidate.decisions.model_dump()[key] != current.decisions.model_dump()[key]}
            if changed_roots - authorized_roots - {"component_quota", "required_components", "detail_packages", "design_rationale", "balcony_access_count", "balcony_width"}:
                raise ValueError("候选修改了缺口未授权的字段")
            no_progress = 0
            current, result, resolved = candidate, candidate_result, candidate_resolved
            for task in tasks:
                task["status"] = "done" if all(
                    g in closed if not g.startswith("dependency:") else (
                        not any(d.severity == "error" for d in candidate_result.defects)
                        and not any(gap.status == "open" for gap in candidate_resolved.design_gaps))
                    for g in task["gap_ids"]) else "open"
                task["result_hash"] = resolved.design_hash
                task["closed_gap_ids"] = sorted(closed.intersection(task["gap_ids"]))
            rounds.append({"blocks": blocks, "base_hash": base_hash, "result_hash": resolved.design_hash,
                           "accepted": True,
                           "candidate_hash": candidate_hash, "actual_model_calls": actual_calls,
                           "closed_gap_ids": sorted(closed), "derived_changes": derived_changes, "normalization_changes": normalization_changes, "block_diagnostics": block_diag})
        except Exception as exc:
            if isinstance(exc, RevisionModelError):
                actual_calls = exc.model_calls
                calls += actual_calls
            no_progress += 1
            for t in tasks:
                t.update(status="failed", evidence_error=str(exc), model_error=isinstance(exc, RevisionModelError))
            rounds.append({"blocks": blocks, "base_hash": base_hash, "error": str(exc),
                           "accepted": False, "candidate_hash": candidate_hash, "actual_model_calls": actual_calls,
                           "normalization_changes": normalization_changes})
        tasks_log.extend(tasks)
        if tasks and tasks[0].get("model_error"):
            stop = "model_error"
            break
        if no_progress >= max(1, max_no_progress):
            stop = "no_progress"
            break
    else:
        stop = "max_rounds"
    remaining = [g.model_dump(mode="json") for g in resolved.design_gaps if g.status != "satisfied"]
    compile_remaining = [d.to_dict() for d in result.defects if _actionable(d)]
    if not remaining and not compile_remaining:
        stop = "satisfied"
    # Re-evaluate completion flags after every subsequent revision; old evidence stays historical.
    final_open = _signature(result, resolved)
    final_status = {g.id: g.status for g in resolved.design_gaps}
    machine_open = any(_actionable(d) for d in result.defects) or any(
        gap.status == "open" for gap in resolved.design_gaps)
    for t in tasks_log:
        if t["status"] == "done" and any(
                g in final_open if g.startswith("compile:") else
                machine_open if g.startswith("dependency:") else
                final_status.get(g) != "satisfied" for g in t["gap_ids"]):
            t["status"] = "invalidated"
    remaining_tasks = plan_design_tasks(current, result, resolved, round_index=len(rounds), only_blocks=only_blocks)
    pending_groups = [{"blocks": [t["block"] for t in group], "estimated_calls": len(group),
                       "tasks": [{"id": t["id"], "depends_on": t["depends_on"]} for t in group]}
                      for group in _task_groups(remaining_tasks)]
    return ConvergenceOutcome(plan=architecture_plan_from_document(current),
        changed=current.model_dump(mode="json") != original, document=current.model_dump(mode="json"),
        diag={"stop_reason": stop, "initial_defects": initial_defects, "final_defects": len(compile_remaining),
              "revisions": current.revision-original["revision"], "rounds": rounds, "tasks": tasks_log,
              "converged": not remaining and not compile_remaining, "unresolved": compile_remaining,
              "design_gaps": remaining, "design_hash": resolved.design_hash,
              "budget": {"max_rounds": max_rounds, "max_model_calls": call_budget, "reserved_model_calls": reserved, "actual_model_calls": calls,
                         "remaining_model_calls": max(0, call_budget-calls),
                         "pending_task_groups": pending_groups,
                         "max_tasks": call_budget, "max_no_progress": max_no_progress}})
