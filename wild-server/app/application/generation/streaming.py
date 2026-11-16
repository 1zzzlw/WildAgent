"""将 LangGraph 流事件投影为执行状态、进度与诊断。"""
import json
import time
from loguru import logger
from config import config
from app.infrastructure.observability.trace import record_node_call
from app.domain.validation.results import final_validation_results
from app.domain.blueprint.artifacts import retain_generation_blueprint
from app.application.generation.progress import _NODE_START_DETAILS
from app.application.generation.progress import _OUR_NODES
from app.application.generation.progress import _node_label
from app.application.generation.events import _send_event
from app.application.generation.events import _utc_now_iso
from app.agent.state import merge_state_mapping
from app.application.generation.context import GenerationExecution


async def consume_graph_events(run: GenerationExecution, event_stream) -> None:
    """按事件顺序更新执行状态，再发送各节点既有的消息。"""
    async for event in event_stream:
        kind = event.get("event")
        node_name = event.get("name", "")
        if kind in ("on_chain_start", "on_chain_end"):
            logger.info(f"[DEBUG astream] kind={kind}, name={node_name!r}")
        if node_name not in _OUR_NODES:
            continue

        label = _node_label(node_name)
        if kind == "on_chain_start":
            await _start_node(run, node_name, label)
        elif kind == "on_chain_end":
            node_output = _apply_node_output(run, event, node_name)
            _record_node_timing(run, node_name, node_output)
            diag = _collect_node_diagnostics(run, node_name, node_output)
            handler = _NODE_COMPLETION_HANDLERS.get(node_name)
            if handler is not None:
                await handler(run, node_name, label, node_output, diag)
            await _publish_plan_events(run, node_output)


async def _start_node(run, node_name, label):
    """记录节点开始时间并发送已有的执行进度。"""
    run.node_starts[node_name] = time.perf_counter()
    run.node_started_isos[node_name] = _utc_now_iso()
    detail = _NODE_START_DETAILS.get(node_name)
    if detail:
        await run.send_step("generating", node_name, "running", label, detail)


def _apply_node_output(run, event, node_name):
    """合并节点输出并保留可交付的蓝图候选。"""
    node_output = event.get("data", {}).get("output", {})
    if not isinstance(node_output, dict):
        node_output = {}
    run.node_outputs[node_name] = node_output
    for key, value in node_output.items():
        run.observed_state[key] = (
            merge_state_mapping(run.observed_state.get(key), value)
            if key in {"component_fragments", "component_diagnostics"}
            else value
        )
    if any(
        key in node_output
        for key in (
            "final_blueprint",
            "merged_blueprint",
            "skeleton_blueprint",
            "component_fragments",
        )
    ):
        run.retained_blueprint = retain_generation_blueprint(
            run.observed_state, run.retained_blueprint
        )
    run.final_state = dict(run.observed_state)
    return node_output


def _record_node_timing(run, node_name, node_output):
    """独立记录耗时和模型用量；观测故障不打断生成。"""
    node_started = run.node_starts.pop(node_name, None)
    node_started_iso = run.node_started_isos.pop(node_name, None)
    node_completed = time.perf_counter()
    if node_started is not None:
        diag_for_trace = node_output.get(f"{node_name}_diag", {})
        if not isinstance(diag_for_trace, dict):
            diag_for_trace = {}
        try:
            record_node_call(
                node_name,
                started_at=node_started_iso or _utc_now_iso(),
                completed_at=_utc_now_iso(),
                duration_ms=round((node_completed - node_started) * 1000),
                llm_ms=diag_for_trace.get("llm_ms"),
                rag_ms=diag_for_trace.get("rag_ms"),
                token_usage=diag_for_trace.get("token_usage"),
                retry_count=diag_for_trace.get("retry_count", 0),
                output_size=len(
                    json.dumps(node_output, ensure_ascii=False, default=str)
                ),
                error=diag_for_trace.get("error"),
                model=getattr(config.chat, "name", None),
            )
        except Exception as exc:
            logger.warning(f"[{run.request_id}] 节点观测记录失败 ({node_name}): {exc}")


def _collect_node_diagnostics(run, node_name, node_output):
    """收集节点诊断、骨架建议和累计 token 用量。"""
    if node_name == "skeleton":
        run.suggested_components = node_output.get("suggested_components", [])
        design_brief = node_output.get("design_brief", {})
        logger.info(f"[{run.request_id}] 骨架建议组件: {run.suggested_components}")
        if design_brief:
            quota = design_brief.get("component_quota", {})
            logger.info(f"[{run.request_id}] 设计清单配额: {quota}")

    # 收集诊断：每个节点把自己那层的诊断挂在 ``{node}_diag`` 下
    diag = node_output.get(f"{node_name}_diag", {})
    if diag:
        run.all_diags[node_name] = diag

    tu = diag.get("token_usage")
    if tu:
        run.total_tokens["input"] += tu.get("input", 0)
        run.total_tokens["output"] += tu.get("output", 0)
    return diag


async def _on_classifier_completed(run, node_name, label, node_output, diag):
    """发送 classifier 节点完成后的进度与诊断。"""
    intent = node_output.get("intent")
    run.resolved_intent = intent
    intent_label = {
        "generate": "生成建筑",
        "edit": "修改场景",
        "chat": "知识问答",
    }.get(intent, intent)
    await run.send_step(
        "generating",
        node_name,
        "done",
        label,
        f"意图：{intent_label} · {node_output.get('intent_reason', '')}",
    )
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": "done",
            "intent": intent,
            "target": node_output.get("intent_target"),
            "profile": node_output.get("intent_profile"),
            "reason": node_output.get("intent_reason"),
            "source": node_output.get("intent_source"),
        },
    )


async def _on_chat_completed(run, node_name, label, node_output, diag):
    """发送 chat 节点完成后的进度与诊断。"""
    chat_reply = node_output.get("chat_reply", "")
    chat_diag = node_output.get("chat_diag", {})
    await run.send_step(
        "generating",
        node_name,
        "done",
        label,
        f"{len(chat_reply)} 字符 · RAG {chat_diag.get('rag_chars', 0)} 字 · "
        f"LLM {chat_diag.get('llm_ms', 0)}ms",
    )
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": "done",
            "rag_chars": chat_diag.get("rag_chars"),
            "rag_ms": chat_diag.get("rag_ms"),
            "llm_chars": chat_diag.get("llm_chars"),
            "llm_ms": chat_diag.get("llm_ms"),
            "token_usage": chat_diag.get("token_usage"),
            "total_ms": chat_diag.get("total_ms"),
        },
    )


async def _on_patch_completed(run, node_name, label, node_output, diag):
    """发送 patch 节点完成后的进度与诊断。"""
    patch = node_output.get("scene_patch")
    patch_diag = node_output.get("patch_diag", {})
    if node_output.get("error") or not patch:
        await run.send_step(
            "generating",
            node_name,
            "error",
            label,
            node_output.get("error", "未生成修改提案"),
        )
        await run.send_debug(
            "node",
            {
                "node": node_name,
                "label": label,
                "stage": "error",
                **patch_diag,
            },
        )
    else:
        operation_count = patch_diag.get(
            "operation_count", len(patch.get("operations", []))
        )
        await run.send_step(
            "generating",
            node_name,
            "done",
            label,
            f"{operation_count} 项修改，等待用户确认",
        )
        await run.send_debug(
            "node",
            {
                "node": node_name,
                "label": label,
                "stage": "done",
                **patch_diag,
            },
        )


async def _on_architecture_completed(run, node_name, label, node_output, diag):
    """发送 architecture 节点完成后的进度与诊断。"""
    plan = node_output.get("architecture_plan", {})
    massing = plan.get("massing", {})
    stage = (
        "error"
        if node_output.get("error") or node_output.get("status") == "failed"
        else "done"
    )
    await run.send_step(
        "generating",
        node_name,
        stage,
        label,
        (node_output.get("error") or "建筑图纸未通过检查")
        if stage == "error"
        else "完整图纸 · "
        f"{massing.get('width', '?')}×{massing.get('depth', '?')}m · "
        f"{massing.get('floors', '?')}层 · {plan.get('roof', {}).get('type', '?')}屋顶",
    )
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": stage,
            **diag,
            "concept": plan.get("concept"),
            "massing": massing,
            "roof": plan.get("roof"),
        },
    )


async def _on_object_design_completed(run, node_name, label, node_output, diag):
    """发送 object_design 节点完成后的进度与诊断。"""
    plan = node_output.get("architecture_plan", {})
    objects = plan.get("objects") if isinstance(plan, dict) else None
    objects = objects if isinstance(objects, list) else []
    piece_count = sum(
        int(item.get("count") or 0) for item in objects if isinstance(item, dict)
    )
    await run.send_step(
        "generating",
        node_name,
        "done",
        label,
        f"{len(objects)} 类物件 · 共 {piece_count} 件"
        + (" · 使用确定性兜底" if diag.get("used_fallback") else ""),
    )
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": "done",
            **diag,
            "concept": plan.get("concept") if isinstance(plan, dict) else None,
            "objects": objects,
        },
    )


async def _on_material_plan_completed(run, node_name, label, node_output, diag):
    """发送 material_plan 节点完成后的进度与诊断。"""
    material_diag = node_output.get("material_diag", {})
    await run.send_step(
        "generating",
        node_name,
        "done",
        label,
        f"PBR 资产 {material_diag.get('selected_asset_count', 0)} 个 · "
        f"{'受控回退' if material_diag.get('used_fallback') else '审美方案已解析'}",
    )
    if material_diag:
        run.all_diags[node_name] = material_diag
        await run.send_debug(
            "node",
            {
                "node": node_name,
                "label": label,
                "stage": "done",
                **material_diag,
            },
        )
    document = node_output.get("design_document")
    if document:
        await _send_event(
            run.sink,
            {
                "type": "design_ready",
                "request_id": run.request_id,
                "session_id": run.session_id,
                "document": document,
                "resolved": node_output.get("resolved_design") or {},
                "preview_url": f"/api/designs/{run.session_id}/preview.svg?revision={document['revision']}",
            },
        )


async def _on_skeleton_completed(run, node_name, label, node_output, diag):
    """发送 skeleton 节点完成后的进度与诊断。"""
    if node_output.get("error"):
        await run.send_step(
            "generating",
            node_name,
            "error",
            label,
            node_output["error"],
        )
    else:
        ec = diag.get("element_count", "?")
        suggested = node_output.get("suggested_components") or []
        await run.send_step(
            "generating",
            node_name,
            "done",
            label,
            f"已生成 {ec} 个主体元素 · 建议 {len(suggested)} 类后续组件",
        )
        await run.send_debug(
            "node",
            {
                "node": node_name,
                "label": label,
                "stage": "done",
                "llm_ms": diag.get("llm_ms"),
                "token_usage": diag.get("token_usage"),
                "element_count": diag.get("element_count"),
                "suggested_components": suggested,
                "deterministic_fallback": diag.get("deterministic_fallback", False),
                "total_ms": diag.get("total_ms"),
            },
        )


async def _on_compile_completed(run, node_name, label, node_output, diag):
    """发送 compile 节点完成后的进度与诊断。"""
    report = node_output.get("compile_report") or {}
    detail = (
        f"{report.get('elements', '?')} 元素 + {report.get('components', '?')} 构件"
    )
    if report.get("abandoned_markers"):
        detail += f" · 舍弃 {len(report['abandoned_markers'])} 个图纸标记"
    repair = report.get("repair") or {}
    if repair.get("attempted"):
        detail += " · 集中修复一次" + (
            "，已采用" if repair.get("accepted") else "，保留原稿"
        )
    step_status = "error" if report.get("ok") is False else "done"
    await run.send_step("generating", node_name, step_status, label, detail)
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": "done",
            **report,
        },
    )


async def _on_final_validate_completed(run, node_name, label, node_output, diag):
    """发送 final_validate 节点完成后的进度与诊断。"""
    validation_results = node_output.get("validation_results", [])
    final_results = final_validation_results(validation_results)
    err_count = node_output.get(
        "validation_error_count",
        sum(1 for result in final_results if result.get("has_error")),
    )
    warn_count = node_output.get(
        "validation_warning_count",
        sum(
            1
            for result in final_results
            if result.get("has_warning") and not result.get("has_error")
        ),
    )
    ok_count = max(0, len(final_results) - err_count - warn_count)
    await run.send_step(
        "generating",
        node_name,
        "error" if err_count else "done",
        label,
        f"{len(final_results)} 步 · {ok_count}✓ {warn_count}⚠ {err_count}✗",
    )
    # 逐步推送校验详情
    for vr in final_results:
        out = vr.get("output", "")
        validation_node = f"validation_{vr.get('step', '?')}"
        validation_label = f"[{vr.get('step', '?')}] {vr.get('name', '?')}"
        if out.startswith("⏭️"):
            validation_status = "skipped"
            validation_detail = "跳过"
        elif vr.get("has_error"):
            validation_status = "error"
            validation_detail = out
        elif vr.get("has_warning"):
            validation_status = "done"
            validation_detail = f"警告：{out}"
        else:
            validation_status = "done"
            validation_detail = "通过"
        await run.send_step(
            "validating",
            validation_node,
            validation_status,
            validation_label,
            validation_detail,
        )


async def _on_execute_completed(run, node_name, label, node_output, diag):
    """发送 execute 节点完成后的进度与诊断。"""
    item_id = node_output.get("current_item_id")
    execute_diag = node_output.get("execute_diag") or {}
    for result in execute_diag.get("item_results") or []:
        await run.send_step(
            "generating",
            f"plan:{result['item_id']}",
            "done" if result["run_state"] == "succeeded" else "error",
            result.get("label") or result["kind"],
            result.get("evidence") or "",
        )
    item_ids = execute_diag.get("item_ids") or ([item_id] if item_id else [])
    tool_calls = int(execute_diag.get("tool_calls") or 0)
    if len(item_ids) > 1:
        detail = (
            f"并发 {len(item_ids)} 条：{'、'.join(item_ids)} · 工具调用 {tool_calls} 次"
        )
    else:
        detail = f"{item_id or '无待办条目'} · 工具调用 {tool_calls} 次"
    await run.send_step(
        "generating",
        node_name,
        "done",
        label,
        detail,
    )
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": "done",
            "item_id": item_id,
            "item_ids": item_ids,
            "parallel_count": len(item_ids),
            "tool_calls": tool_calls,
            "item_results": execute_diag.get("item_results") or [],
        },
    )


async def _on_replanner_completed(run, node_name, label, node_output, diag):
    """发送 replanner 节点完成后的进度与诊断。"""
    terminal = diag.get("terminal_stats")
    terminal = terminal if isinstance(terminal, dict) else {}
    detail = (
        f"第 {diag.get('iterations', '?')} 轮 · "
        f"完成 {terminal.get('done', 0)}/{terminal.get('total', 0)} · "
        f"无进展 {diag.get('no_progress_rounds', 0)} 轮"
    )
    finalization = diag.get("finalization")
    if isinstance(finalization, dict) and finalization.get("reason"):
        detail += f" · 转入确定性收尾：{finalization['reason']}"
    await run.send_step("generating", node_name, "done", label, detail)
    await run.send_debug(
        "node",
        {
            "node": node_name,
            "label": label,
            "stage": "done",
            **diag,
        },
    )


async def _on_plan_completed(run, node_name, label, node_output, diag):
    """发送 plan 节点完成后的进度与诊断。"""
    total = len(node_output.get("plan_events") or [])
    budget = (node_output.get("plan") or {}).get("budget", {})
    await run.send_step(
        "generating",
        node_name,
        "done",
        label,
        f"展开 {total} 条条目 · 档位预算 {budget.get('iterations', '?')} 轮",
    )


async def _on_callback_completed(run, node_name, label, node_output, diag):
    """发送 callback 节点完成后的进度与诊断。"""
    retry_number = node_output.get("retry_count", 0)
    if node_output.get("error"):
        await run.send_step(
            "generating",
            node_name,
            "error",
            label,
            f"修正失败：{node_output['error']}",
        )
    else:
        await run.send_step(
            "generating",
            node_name,
            "done",
            label,
            f"已发起第 {retry_number} 轮修复（每目标最多 "
            f"{run.initial_state.get('max_retries', 3)} 次）",
        )
        await run.send_debug(
            "node",
            {
                "node": node_name,
                "label": label,
                "stage": "done",
                "retry_count": retry_number,
            },
        )


async def _publish_plan_events(run, node_output):
    """发布完整计划和条目增量，保留后续追加的计划项。"""
    plan_payload = node_output.get("plan")
    if isinstance(plan_payload, dict) and plan_payload.get("items") is not None:
        await _send_event(
            run.sink,
            {
                "type": "plan_ready",
                "request_id": run.request_id,
                "session_id": run.session_id,
                "plan": plan_payload,
            },
        )
    for item_event in node_output.get("plan_events") or []:
        await _send_event(
            run.sink,
            {
                "type": "plan_item_updated",
                "request_id": run.request_id,
                "session_id": run.session_id,
                "item": item_event,
            },
        )


_NODE_COMPLETION_HANDLERS = {
    "classifier": _on_classifier_completed,
    "chat": _on_chat_completed,
    "patch": _on_patch_completed,
    "architecture": _on_architecture_completed,
    "object_design": _on_object_design_completed,
    "material_plan": _on_material_plan_completed,
    "skeleton": _on_skeleton_completed,
    "compile": _on_compile_completed,
    "final_validate": _on_final_validate_completed,
    "execute": _on_execute_completed,
    "replanner": _on_replanner_completed,
    "plan": _on_plan_completed,
    "callback": _on_callback_completed,
}
