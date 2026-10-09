"""plan 条目的处理器（《动态节点设计规划》§4.7–§4.12）。

一张表说清边界：

| op | 处理器形态 | 给工具吗 | 理由 |
| --- | --- | --- | --- |
| ``generate`` | **工具型**：模型 + 有界工具循环 | ✅ | 字段约束可能超出程序预取的知识，允许模型自己补检索、自查 |
| ``repair`` | **工具型**（模型出白名单动作、程序执行） | ✅ | 复用既有 ``callback_node``，模型不许直接写蓝图 |
| ``merge`` / ``validate`` / ``fix`` | **确定性** | ❌ | 这三类必须可复现、可对账，不经过模型 |

``merge`` 条目有两种作用域（§3.3）：``scope="batch"`` 只把一组分片并进蓝图，
``scope="final"`` 才是配额强制 + 全局归一化 + 校验修复循环。分派逻辑在本模块，
实现复用同一个 ``merge_fragments_node``（``generation/assembly/workflow.py``）。

关键校验由 plan 里显式的 ``validate`` 条目兜底（模型无法跳过）；模型自愿调工具只是加分项。
处理器全部复用既有实现：生成用 ``create_component_generator``/``create_component_validator``，
合并用 ``merge_fragments_node``，校验与修复用 ``run_validation_pipeline`` + ``apply_fixes``。
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from loguru import logger

from app.agent.generation.component.registry import COMPONENT_REGISTRY, ComponentConfig
from app.agent.plan.contracts import PlanItem
from app.agent.plan.tool_registry import tools_for

#: 生成处理器与校验处理器按构件类型缓存（工厂函数很轻，但没必要每轮重建）。
_GENERATORS: dict[str, Any] = {}
_VALIDATORS: dict[str, Any] = {}

#: 处理器的统一签名：``(state, item) -> (state 更新, 执行态, 产物 id, 证据, 工具轨迹)``
HandlerResult = tuple[dict[str, Any], str, list[str], str, list[dict[str, Any]]]
Handler = Callable[[dict[str, Any], PlanItem], Any]


def _generator_for(config: ComponentConfig):
    generator = _GENERATORS.get(config.component_type)
    if generator is None:
        from app.agent.generation.component.workflow import create_component_generator

        generator = create_component_generator(config)
        _GENERATORS[config.component_type] = generator
    return generator


def _validator_for(config: ComponentConfig):
    validator = _VALIDATORS.get(config.component_type)
    if validator is None:
        from app.agent.generation.component.workflow import create_component_validator

        validator = create_component_validator(config)
        _VALIDATORS[config.component_type] = validator
    return validator


def build_execution_context(state: dict[str, Any], item: PlanItem) -> dict[str, Any]:
    """组装一条条目需要的执行上下文（不写回 state）。

    只放该条目真正要用的东西：用户需求、骨架摘要、空间不变量、设计清单、本条目的策略提示、
    档位与思考开关。

    ``plan_item`` 是 plan 阶段导出的**策略**（subtype / guidance / reason）：
    生成处理器会把它作为形态提示拼进提示词，但坐标与数量仍以设计清单为准。

    这里是《动态节点设计规划》§2.8 的"② 执行上下文"：单次执行用完即丢，所以**作为参数
    传入处理器，不写进 LangGraph state**。
    """

    from app.agent.plan.expand import compile_gap_summary, resolve_detail_level

    skeleton = state.get("skeleton_blueprint")
    materials = skeleton.get("materials") if isinstance(skeleton, dict) else None

    return {
        "user_message": state.get("user_message", ""),
        "skeleton_summary": state.get("skeleton_summary", ""),
        "skeleton_blueprint": skeleton if isinstance(skeleton, dict) else {},
        "spatial_invariants": state.get("spatial_invariants", {}),
        "design_brief": state.get("design_brief"),
        "architecture_plan": state.get("architecture_plan"),
        "thinking_mode": state.get("thinking_mode", False),
        # D 段（全局约束）要用的两项：材质 id 白名单与档位，程序推导、模型只读。
        "material_ids": sorted(materials) if isinstance(materials, dict) else [],
        "detail_level": resolve_detail_level(state),
        # 图纸级缺口（用户指令 2026-09-29）：编译报告的 uncompiled/defects 紧凑摘要，
        # 让每个条目知道整张图纸还缺什么；条目自身的缺口在 plan_item.blueprint_gap。
        "blueprint_gaps": compile_gap_summary(state),
        "plan_item": {
            "id": item.id,
            "op": item.op,
            "kind": item.kind,
            "label": item.label,
            "target": item.target,
            **item.params,
        },
        "component_fragments": {},
        "component_diagnostics": {},
    }


def _fragment_count(fragments: Any, config: ComponentConfig) -> int:
    if config.is_list:
        return len([entry for entry in fragments if entry]) if isinstance(fragments, list) else 0
    return 1 if isinstance(fragments, dict) else 0


def _model_error(diagnostics: dict[str, Any]) -> dict[str, Any] | None:
    for diag in diagnostics.values():
        if not isinstance(diag, dict):
            continue
        error = diag.get("model_error")
        if isinstance(error, dict) and error.get("terminal_current_run"):
            return error
    return None


def _trace_entries(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    """把这一次执行涉及的检索/校验事实汇总成审计记录（§4.9）。"""

    entries: list[dict[str, Any]] = []
    for key, diag in diagnostics.items():
        if not isinstance(diag, dict):
            continue
        # 工具型调用自带轨迹（模型自己发起的检索/自查）
        for entry in diag.get("tool_trace") or []:
            if isinstance(entry, dict):
                entries.append({**entry, "step": key})
        if "rag_chars" in diag:
            entries.append(
                {
                    "tool": "search_knowledge",
                    "step": key,
                    "ok": not diag.get("rag_error"),
                    "chars": int(diag.get("rag_chars") or 0),
                    "mode": "prefetch",
                }
            )
        if "validation_passed" in diag:
            entries.append(
                {
                    "tool": "validate_component",
                    "step": key,
                    "ok": bool(diag.get("validation_passed")),
                    "chars": 0,
                    "mode": "deterministic",
                }
            )
    return entries


def _generation_failure_evidence(
    item: PlanItem,
    diagnostics: dict[str, Any],
) -> str:
    """把“0 个片段”还原成可供用户和 replanner 使用的真实失败证据。"""

    generated = diagnostics.get(f"{item.kind}_gen") or {}
    validated = diagnostics.get(f"{item.kind}_val") or {}
    tool_loop = generated.get("tool_loop") or {}
    if tool_loop.get("error"):
        return f"{item.label}：条目内工具调用失败：{str(tool_loop['error'])[:300]}"
    if generated.get("json_parse_failed"):
        return (
            f"{item.label}：模型回复 {int(generated.get('llm_chars') or 0)} 字，"
            "定向格式恢复后仍无法提取合法 JSON"
        )
    rejected = int(validated.get("rejected_fragment_count") or 0)
    if rejected:
        detail = str(validated.get("validation_details", {}).get("recheck") or "")
        return f"{item.label}：产出片段经确定性校验后被拒绝 {rejected} 个" + (f"；{detail[:500]}" if detail else "")
    generated_count = int(generated.get("fragment_count") or 0)
    if generated_count == 0:
        return f"{item.label}：模型输出中没有满足 type 与必填字段契约的合法片段"
    return f"{item.label}：未产出可交付片段（生成 {generated_count} 个，校验后为 0）"


async def run_generate(state: dict[str, Any], item: PlanItem) -> HandlerResult:
    """工具型生成：预取 RAG 是主力，模型可以在这基础上有界地补检索与自查。"""

    from app.agent.runtime import bind_item_tools, reset_item_tools

    from app.agent.generation.component.registry import generic_component_config

    config = COMPONENT_REGISTRY.get(item.kind)
    if config is None or not config.implemented:
        # 开放集通道：未知/未注册类型不再直接 failed，
        # 用通用配置进入生成通道——字段契约靠知识库检索，校验与修复环兜底。
        config = generic_component_config(item.kind, label=item.label)

    context = build_execution_context(state, item)
    tool_token = bind_item_tools(tools_for(item))
    try:
        generated = await _generator_for(config)(context)
    finally:
        reset_item_tools(tool_token)
    diagnostics = dict(generated.get("component_diagnostics", {}))

    terminal = _model_error(diagnostics)
    if terminal is not None:
        return (
            {"terminal_model_error": {**terminal, "item_id": item.id},
             "error": terminal.get("user_message", "模型服务故障"),
             "status": "failed"},
            "aborted", [], terminal.get("user_message", ""), _trace_entries(diagnostics),
        )

    checked = await _validator_for(config)({**context, **generated})
    diagnostics.update(checked.get("component_diagnostics", {}))
    fragments = checked.get("component_fragments", {}).get(item.kind)
    produced = _fragment_count(fragments, config)

    updates = {
        "component_fragments": checked.get("component_fragments", {}),
        "component_diagnostics": diagnostics,
    }
    if produced == 0:
        return (
            updates,
            "failed",
            [],
            _generation_failure_evidence(item, diagnostics),
            _trace_entries(diagnostics),
        )

    artifact_ids = [
        str(entry.get("id"))
        for entry in (fragments if isinstance(fragments, list) else [fragments])
        if isinstance(entry, dict) and entry.get("id")
    ]
    return (
        updates, "succeeded", artifact_ids,
        f"{item.label}：产出 {produced} 个片段", _trace_entries(diagnostics),
    )


async def run_merge(state: dict[str, Any], item: PlanItem) -> HandlerResult:
    """合并处理器：按条目的 scope 分派（§3.3）。

    ``scope="batch"`` 只把这一组的分片并进蓝图，任何删改都留给收尾合并——因为批次合并
    跑的时候后面还有分组没到场，此刻按配额剔超额、按槽位补缺失都会误伤。
    """

    from app.agent.generation.assembly.workflow import SCOPE_BATCH, merge_fragments_node

    scope = SCOPE_BATCH if item.is_batch_merge else "final"
    kinds = [str(kind) for kind in (item.target.get("component_types") or []) if kind]
    result = await merge_fragments_node(dict(state), scope=scope, component_types=kinds)
    updates = {key: value for key, value in result.items() if key != "status"}
    if result.get("error"):
        return (
            {**updates, "error": result["error"], "status": result.get("status", "failed")},
            "failed", [], str(result["error"]), [],
        )

    blueprint = result.get("merged_blueprint") or {}
    geometry = blueprint.get("geometry", {}) if isinstance(blueprint, dict) else {}
    elements = geometry.get("elements", []) or []
    components = geometry.get("components", []) or []
    entries = [*elements, *components]
    if item.is_batch_merge and kinds:
        # 批次合并的产物只认这一组：run.artifacts 是"这条条目产出了什么"的凭据。
        entries = [entry for entry in entries if entry.get("type") in set(kinds)]
    artifact_ids = [
        str(entry.get("id"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
    ]
    evidence = (
        f"{item.label}：已并入 {len(artifact_ids)} 个元素"
        if item.is_batch_merge
        else f"{item.label}：{len(elements)} 个结构元素 + {len(components)} 个构件"
    )
    return (
        updates, "succeeded", artifact_ids, evidence,
        [{"tool": "merge_fragments", "ok": True, "chars": 0, "mode": "deterministic"}],
    )


def run_validate(state: dict[str, Any], item: PlanItem) -> HandlerResult:
    from app.agent.validation.candidate import evaluate_candidate

    blueprint = state.get("merged_blueprint") or {}
    if not blueprint:
        return {}, "failed", [], "没有可校验的蓝图", []
    evaluated = evaluate_candidate(blueprint, design_document=state.get("design_document"),
                                   design_brief=state.get("design_brief"), source="plan_validate")
    snapshot = evaluated["snapshot"]
    updates = {"validation_results": snapshot["results"], "validation_snapshot": snapshot,
               "validation_issues": evaluated["issues"], "validation_error_count": snapshot["error_count"],
               "validation_warning_count": snapshot["warning_count"]}
    evidence = f"{item.label}：完整门禁 {snapshot['error_count']} 个错误"
    trace = [{"tool": r.name, "ok": not r.has_error, "chars": len(r.output), "mode": "deterministic"}
             for r in evaluated["results"]]
    return updates, ("failed" if evaluated["errors"] else "succeeded"), [], evidence, trace


def run_fix(state: dict[str, Any], item: PlanItem) -> HandlerResult:
    from copy import deepcopy
    from app.agent.generation.assembly.merge import apply_fixes
    from app.agent.validation.candidate import evaluate_candidate
    from app.agent.repair.state_updates import state_updates_from_candidate

    original = state.get("merged_blueprint")
    if not original:
        return {}, "failed", [], "没有可修复的蓝图", []
    kwargs = {"design_document": state.get("design_document"), "design_brief": state.get("design_brief")}
    before = evaluate_candidate(original, **kwargs)
    if not before["errors"]:
        return {}, "succeeded", [], "完整验收已通过，无需修复", []
    if before["approved_design_errors"]:
        return {"repair_audit": {"accepted": False, "stop_reason": "design_revision_required"}}, \
            "failed", [], "批准设计自身无效，需要修订并重新审核", []
    candidate = deepcopy(original)
    applied = apply_fixes(candidate, before["errors"])
    after = evaluate_candidate(candidate, source="plan_fix", **kwargs)
    trace = [{"tool": name, "ok": success, "chars": 0, "mode": "deterministic"} for name, success in applied]
    preserved = set((before["fulfillment"] or {}).get("satisfied_ids") or []) <= set(
        (after["fulfillment"] or {}).get("satisfied_ids") or [])
    if after["errors"] or not preserved or candidate == original:
        return {}, "failed", [], f"完整验收未通过，脚本候选已回滚；仍有 {len(after['errors'])} 个错误", trace
    ids = {e["id"] for bp in (original, candidate) for bucket in ("elements", "components")
           for e in (bp.get("geometry") or {}).get(bucket, [])}
    updates = state_updates_from_candidate(state, candidate, ids)
    updates["validation_snapshot"] = after["snapshot"]
    updates["repair_audit"] = {"accepted": True, "before_issue_count": len(before["issues"]),
                               "after_issue_count": 0}
    return updates, "succeeded", [], "脚本候选完整验收通过，已提交", trace


async def run_repair(state: dict[str, Any], item: PlanItem) -> HandlerResult:
    from app.agent.repair.workflow import callback_node
    from app.agent.validation.workflow import validate_node

    fixed, outcome, artifacts, evidence, trace = run_fix(state, item)
    if outcome == "succeeded" or (fixed.get("repair_audit") or {}).get("stop_reason"):
        return fixed, outcome, artifacts, evidence, trace
    # 脚本失败候选已回滚，模型基于原场景及同一完整门禁继续。
    validated = await validate_node(state)
    repaired = await callback_node({**state, **validated})
    accepted = bool((repaired.get("repair_audit") or {}).get("accepted"))
    reports = (repaired.get("repair_audit") or {}).get("actions") or []
    trace.extend({"tool": r.get("tool", "repair_action"), "ok": bool(r.get("success")),
                  "chars": 0, "mode": "model_whitelist"} for r in reports)
    updates = {**validated, **repaired}
    return updates, ("succeeded" if accepted else "failed"), [], (
        "完整验收通过，已提交修复候选" if accepted else "修复未完整通过，保留原产物"), trace


#: op → 处理器。新增 op 必须同时补进这里与 §2.3 的闭集，否则条目会以 failed 收场。
HANDLERS: dict[str, Handler] = {
    "generate": run_generate,
    "merge": run_merge,
    "validate": run_validate,
    "fix": run_fix,
    "repair": run_repair,
}


__all__ = ["HANDLERS", "build_execution_context"]
