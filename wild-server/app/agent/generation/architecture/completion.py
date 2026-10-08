"""Bounded pre-approval design completion using the existing block executor."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from app.design.contracts import DesignDocument
from app.design.resolver import architecture_plan_from_document, build_design_document, _stable_hash
from app.design.compilation import compile_document, project_compilation
from app.design.completeness import value_at
from .design_blocks import ordered_blocks, block_of_design_field
from .design_workflow import draft_design_blocks

_COMPLETION_PROMPT = """你在人工审核前完善当前设计。只解决给定缺口，不进行无依据的装饰扩张。
保留用户要求及已采用决定；不要通过修改 design_constraints、expected 或删除要求伪造完成。
在选定设计块的现有协议内修改；关系无法表达则保留缺口，不发明新 Schema。
当前是设计完善任务，可以在指定体量/立面等块内新增有依据的设计对象；不能修改其他块。
最终是否完成由当前设计与编译证据判定，你的成功声明不算完成证据。
"""


class RevisionModelError(RuntimeError):
    pass


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
            raise RevisionModelError(outcome["error"])
        return outcome["patch"], outcome["diagnostics"]
    try:
        return await draft_design_blocks(**payload, on_reasoning_delta=callback)
    except Exception as exc:
        raise RevisionModelError(str(exc)) from exc


def _block(target: str):
    return block_of_design_field(target.strip("/").replace("/", "."))


def _signature(result, resolved) -> set[str]:
    return {g.id for g in resolved.design_gaps if g.status == "open"} | {
        f"compile:{d.code}:{d.target}:{d.design_field}" for d in result.defects if d.severity == "error"
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
        if defect.severity == "error" and block:
            by_block.setdefault(block.name, []).append({"id": f"compile:{defect.code}:{defect.target}:{defect.design_field}",
                "layer": "design", "category": "compilability", "target": defect.design_field, "evidence": defect.evidence})
    # A massing change invalidates all dependent blocks. Draft their data in dependency order.
    if "massing" in by_block:
        for b in ordered_blocks("standard"):
            if b.name != "massing":
                by_block.setdefault(b.name, []).append({"id": "dependency:massing", "evidence": "体量修订后重建轴网、立面、屋顶及实例宿主关联"})
    if only_blocks is not None:
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
            "completion_condition": "当前版本关联缺口关闭且对应块无编译 error", "status": "pending"})
    return tasks


async def complete_design(*, document: dict, user_message: str, complexity_profile,
                          architecture_profile, thinking_mode: bool, max_rounds: int,
                          max_no_progress: int, on_reasoning_delta=None, only_blocks=None):
    from .convergence import ConvergenceOutcome
    from .planning import normalize_architecture_plan

    current = DesignDocument.model_validate(document)
    original = current.model_dump(mode="json")
    if current.status != "draft":
        return ConvergenceOutcome(plan=architecture_plan_from_document(current), changed=False,
            diag={"stop_reason": "approval_boundary", "initial_defects": 0, "final_defects": 0,
                  "revisions": 0, "rounds": [], "unresolved": [], "converged": False}, document=original)
    result = compile_document(current)
    resolved = project_compilation(current, result)
    initial_defects = sum(d.severity == "error" for d in result.defects)
    tasks_log, rounds = [], []
    # One model invocation per selected block, no internal probe or retry calls.
    call_budget = 9
    calls = 0
    no_progress = 0
    seen_designs = {current.decisions.model_dump_json()}
    stop = "max_rounds"
    for round_index in range(max(0, max_rounds)):
        tasks = plan_design_tasks(current, result, resolved, round_index=round_index, only_blocks=only_blocks)
        if not tasks:
            stop = "satisfied" if not any(g.status != "satisfied" for g in resolved.design_gaps) and not any(d.severity == "error" for d in result.defects) else "needs_review"
            break
        if calls + len(tasks) > call_budget:
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
        calls += len(tasks)
        normalization_changes = []
        try:
            patch, block_diag = await _run_revision(dict(
                base_prompt=_COMPLETION_PROMPT+"\n本轮任务与完成条件：\n"+json.dumps(tasks, ensure_ascii=False),
                user_request=user_message, thinking_mode=thinking_mode, only_blocks=blocks,
                complexity_profile=complexity_profile, architecture_profile=architecture_profile,
                current_plan=context, allow_probe=False, allow_design_changes=True, max_attempts=1,
            ), on_reasoning_delta)
            if _stable_hash(current) != base_hash:
                raise ValueError("stale_patch: 任务依据的设计版本已过期")
            allowed = {f for t in tasks for f in t["write_fields"]}
            # The massing block can echo intent but cannot alter it during completion.
            if "design_constraints" in patch and patch["design_constraints"] != plan["design_constraints"]:
                raise ValueError("补丁试图改变采用决定，已拒绝")
            patch.pop("design_constraints", None)
            if set(patch)-allowed:
                raise ValueError("补丁包含未授权设计字段")
            if not patch or block_diag.get("unsettled_blocks"):
                raise ValueError("设计块未全部完成，保留当前有效设计")
            merged = {**plan, **deepcopy(patch)}
            normalized = normalize_architecture_plan(merged, user_message=user_message,
                complexity_profile=complexity_profile, architecture_profile=architecture_profile,
                normalization_changes=normalization_changes, input_source="model")
            # Quota/required types are existing deterministic derivatives of facade/roof
            # decisions. Record these writes; do not require a second model to copy them.
            derived_fields = {"component_quota", "required_components", "detail_packages", "balcony_access_count", "balcony_width"}
            semantic_roots = {"massing", "volumes", "roof", "facades", "structural_grid", "circulation", "components", "curtain_wall"}
            for field in semantic_roots-allowed:
                if field in normalized and normalized[field] != plan.get(field):
                    raise ValueError(f"归一化越权修改 {field}，保留当前设计")
            derived_changes = {f: {"before": plan.get(f), "after": normalized[f]}
                               for f in derived_fields if f in normalized and normalized[f] != plan.get(f)}
            normalized = {**plan, **{f:v for f,v in normalized.items() if f in allowed|derived_fields}}
            normalized["design_constraints"] = plan["design_constraints"]
            normalized["normalization_changes"] = normalization_changes
            candidate = build_design_document(normalized, session_id=current.session_id,
                source_request=current.requirements.source_request,
                building_type=current.requirements.building_type,
                style_intent=current.requirements.style_intent, previous=current)
            for lock in current.locks:
                if value_at(current.model_dump(mode="json"), lock) != value_at(candidate.model_dump(mode="json"), lock):
                    raise ValueError(f"补丁修改锁定字段 {lock}")
            if candidate.decisions == current.decisions:
                raise ValueError("没有有效设计变化")
            if candidate.decisions.model_dump_json() in seen_designs:
                raise ValueError("设计反复回到已出现版本，停止重复应用补丁")
            seen_designs.add(candidate.decisions.model_dump_json())
            candidate_result = compile_document(candidate)
            candidate_resolved = project_compilation(candidate, candidate_result)
            after = _signature(candidate_result, candidate_resolved)
            # Satisfied adopted goals cannot be sacrificed to close a different gap.
            satisfied = {g.id for g in resolved.design_gaps if g.status == "satisfied"}
            if any(g.id in satisfied and g.status != "satisfied" for g in candidate_resolved.design_gaps):
                raise ValueError("补丁破坏已满足的设计决定")
            old_errors = {x for x in before if x.startswith("compile:")}
            if {x for x in after if x.startswith("compile:")} - old_errors:
                raise ValueError("补丁引入新的编译错误")
            closed = before-after
            no_progress = 0 if closed else no_progress+1
            current, result, resolved = candidate, candidate_result, candidate_resolved
            for task in tasks:
                task["status"] = "done" if not any(g in after for g in task["gap_ids"] if not g.startswith("dependency:")) else "open"
                task["result_hash"] = resolved.design_hash
                task["closed_gap_ids"] = sorted(closed.intersection(task["gap_ids"]))
            rounds.append({"blocks": blocks, "base_hash": base_hash, "result_hash": resolved.design_hash,
                           "closed_gap_ids": sorted(closed), "derived_changes": derived_changes, "normalization_changes": normalization_changes, "block_diagnostics": block_diag})
        except Exception as exc:
            no_progress += 1
            for t in tasks:
                t.update(status="failed", evidence_error=str(exc), model_error=isinstance(exc, RevisionModelError))
            rounds.append({"blocks": blocks, "base_hash": base_hash, "error": str(exc),
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
    compile_remaining = [d.to_dict() for d in result.defects if d.severity == "error"]
    if not remaining and not compile_remaining:
        stop = "satisfied"
    # Re-evaluate completion flags after every subsequent revision; old evidence stays historical.
    final_open = _signature(result, resolved)
    for t in tasks_log:
        if t["status"] == "done" and any(g in final_open for g in t["gap_ids"]):
            t["status"] = "invalidated"
    return ConvergenceOutcome(plan=architecture_plan_from_document(current),
        changed=current.model_dump(mode="json") != original, document=current.model_dump(mode="json"),
        diag={"stop_reason": stop, "initial_defects": initial_defects, "final_defects": len(compile_remaining),
              "revisions": current.revision-original["revision"], "rounds": rounds, "tasks": tasks_log,
              "converged": not remaining and not compile_remaining, "unresolved": compile_remaining,
              "design_gaps": remaining, "design_hash": resolved.design_hash,
              "budget": {"max_rounds": max_rounds, "max_model_calls": call_budget, "reserved_model_calls": calls,
                         "max_tasks": call_budget, "max_no_progress": max_no_progress}})
