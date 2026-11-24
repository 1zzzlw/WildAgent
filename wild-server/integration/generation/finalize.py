"""按意图交付生成结果，组织最终验收和成果保存。"""

from integration.generation.errors import _generation_failure_message
import asyncio
from loguru import logger
from agent.utils.blueprint.materials.recipes import without_procedural_materials
from integration.generation.delivery import ArtifactSaveError
from integration.generation.delivery import GenerationRejectedError
from integration.generation.delivery import commit_generation_result
from agent.utils.blueprint.artifacts import retain_generation_blueprint
from integration.generation.plan_summary import _plan_delivery_summary
from integration.generation.events import _send_event
from integration.generation.context import GenerationExecution


async def deliver_result(run: GenerationExecution) -> None:
    if run.resolved_intent == "chat":
        await deliver_chat(run)
    elif run.resolved_intent == "edit":
        await deliver_patch(run)
    else:
        await deliver_blueprint(run)


async def deliver_chat(run: GenerationExecution) -> None:
    chat_output = run.node_outputs.get("chat", run.final_state)
    chat_diag = chat_output.get("chat_diag", {})
    await _send_event(
        run.sink,
        {
            "type": "agent_reply",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "content": chat_output.get("chat_reply", "未生成回答"),
            "content_type": "chat",
            "cited_chunk_ids": chat_diag.get("cited_chunk_ids", []),
            "evidence_status": chat_diag.get("evidence_status", "none"),
        },
    )
    await run.send_debug(
        "session_metrics",
        {
            "node_count": 2,
            "active_nodes": 2,
            "skipped_nodes": 0,
            "total_rag_ms": chat_diag.get("rag_ms", 0),
            "total_llm_ms": chat_diag.get("llm_ms", 0),
            "total_tokens": chat_diag.get("token_usage")
            or {"input": 0, "output": 0, "total": 0},
            "fragment_total": 0,
            "validation_steps": 0,
            "validation_errors": 0,
            "status": chat_output.get("status", "complete"),
            "chat_mode": True,
        },
    )
    if run.thinking_mode:
        await run.send_thinking_status("completed", "处理已完成")
    await run.send_step("finished", "finished", "done", "处理完成", "处理完成")
    return


async def deliver_patch(run: GenerationExecution) -> None:
    patch_output = run.node_outputs.get("patch", run.final_state)
    scene_patch = patch_output.get("scene_patch")
    if patch_output.get("error") or not scene_patch:
        error_text = patch_output.get("error", "未生成修改提案")
        await _send_event(
            run.sink,
            {
                "type": "agent_reply",
                "request_id": run.request_id,
                "session_id": run.session_id,
                "content": f"无法生成可安全应用的修改提案：{error_text}",
            },
        )
        if run.thinking_mode:
            await run.send_thinking_status("error", error_text)
        await run.send_step("finished", "finished", "error", "处理失败", error_text)
        return

    operations = scene_patch.get("operations", [])
    summary = scene_patch.get("summary") or f"AI 提出了 {len(operations)} 项场景修改"
    await _send_event(
        run.sink,
        {
            "type": "patch_proposal",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "patch": {
                "type": "scene_patch",
                "patch_id": f"patch_{run.request_id}",
                "base_revision": run.data.get("scene_revision", 0),
                "source": "agent",
                "mode": "proposal",
                "requires_confirmation": True,
                "operations": operations,
                "summary": summary,
            },
        },
    )
    if run.thinking_mode:
        await run.send_thinking_status("completed", "修改提案已完成")
    await run.send_step(
        "finished",
        "finished",
        "done",
        "修改提案已完成",
        "等待用户确认",
    )
    return


async def deliver_blueprint(run: GenerationExecution) -> None:
    if run.final_state.get("status") == "failed":
        run.execution_error = run.execution_error or run.final_state.get("error")
    # 保留完整 checkpoint；final_validate 的局部输出可能没有已有几何和设计上下文。
    merged_blueprint = retain_generation_blueprint(
        run.final_state, run.retained_blueprint
    )
    if merged_blueprint is None:
        upstream_failure = _generation_failure_message(
            run.node_outputs, run.final_state
        )
        error_event = {
            "type": "error",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "error": upstream_failure,
        }
        terminal_model_error = run.final_state.get("terminal_model_error")
        if isinstance(terminal_model_error, dict):
            error_event["code"] = "model_service_error"
            error_event["error_category"] = terminal_model_error.get("category")
            error_event["retryable"] = terminal_model_error.get("retryable", False)
        await _send_event(run.sink, error_event)
        if run.thinking_mode:
            await run.send_thinking_status("error", upstream_failure)
        await run.send_step(
            "finished",
            "finished",
            "error",
            "生成失败",
            upstream_failure,
        )
        return
    if (
        run.data.get("procedural_materials_enabled") is not True
        and not run.execution_error
    ):
        merged_blueprint = without_procedural_materials(merged_blueprint)

    validation_results = run.final_state.get("validation_results", [])
    validation_errors = run.final_state.get("validation_error_count", 0)
    validation_warnings = run.final_state.get("validation_warning_count", 0)
    final_status = run.final_state.get("status", "failed")
    #  P4：设计履约报告交给交付层，只进回复文案，**不进保存门禁**。
    design_fulfillment = run.final_state.get("design_fulfillment") or None
    # 交付开关可能改变材质内容，证据必须重新绑定实际落盘的那份 Blueprint。
    from agent.utils.validation.candidate import evaluate_candidate

    try:
        delivery_evaluation = evaluate_candidate(
            merged_blueprint,
            design_document=run.final_state.get("design_document"),
            design_brief=run.final_state.get("design_brief"),
            source="delivery",
        )
        delivery_snapshot = delivery_evaluation["snapshot"]
        validation_results = delivery_snapshot["results"]
        validation_errors = delivery_snapshot["error_count"]
        validation_warnings = delivery_snapshot["warning_count"]
        design_fulfillment = delivery_evaluation["fulfillment"]
        if final_status == "complete":
            final_status = delivery_snapshot["status"]
    except Exception as exc:
        logger.error(f"[{run.request_id}] 交付内容复检失败: {exc}")
        delivery_snapshot = None
        final_status = "failed"
        validation_results = [
            *validation_results,
            {
                "step": "delivery",
                "name": "validate_delivery",
                "output": f"交付内容复检失败: {exc}",
                "has_error": True,
                "has_warning": False,
            },
        ]
        validation_errors += 1

    active_diags = {
        key: value for key, value in run.all_diags.items() if not value.get("skipped")
    }
    total_rag_ms = sum(value.get("rag_ms", 0) for value in active_diags.values())
    total_llm_ms = sum(value.get("llm_ms", 0) for value in active_diags.values())
    session_metrics = {
        "node_count": len(active_diags),
        "active_nodes": len(active_diags),
        "skipped_nodes": sum(
            1 for value in run.all_diags.values() if value.get("stage") == "skipped"
        ),
        "suggested_components": run.suggested_components,
        "total_rag_ms": total_rag_ms,
        "total_llm_ms": total_llm_ms,
        "total_tokens": {
            "input": run.total_tokens["input"],
            "output": run.total_tokens["output"],
            "total": run.total_tokens["input"] + run.total_tokens["output"],
        },
        "fragment_total": sum(
            value.get("fragment_count", 0) for value in active_diags.values()
        ),
        "validation_steps": len(validation_results),
        "validation_errors": validation_errors,
        "retry_count": run.final_state.get("retry_count", 0),
        "max_retries": run.initial_state.get("max_retries", 3),
        "plan_items": len((run.final_state.get("plan") or {}).get("items") or []),
        "plan_iterations": int(
            (run.final_state.get("plan") or {}).get("iterations") or 0
        ),
        "status": final_status,
    }
    # 交付清单（《动态节点设计规划》§6.4）：交付必须能回答"哪几条没做成、为什么"。
    plan_delivery = _plan_delivery_summary(run.final_state.get("plan"))
    if plan_delivery:
        session_metrics["plan_delivery"] = plan_delivery
        shortfall = [
            entry
            for entry in plan_delivery.get("items", [])
            if entry["status"] != "done"
        ]
        if shortfall:
            logger.warning(
                f"[{run.request_id}] 交付清单包含 {len(shortfall)} 条未完成项："
                + "; ".join(
                    f"{entry['label']}（{entry['status']}）" for entry in shortfall[:5]
                )
            )
    try:
        delivery = await asyncio.to_thread(
            commit_generation_result,
            run.session_id,
            run.request_id,
            merged_blueprint,
            validation_results,
            status=final_status,
            error_count=validation_errors,
            warning_count=validation_warnings,
            fulfillment=design_fulfillment,
            validation_snapshot=delivery_snapshot,
        )
    except GenerationRejectedError as exc:
        await _send_event(
            run.sink,
            {
                "type": "agent_reply",
                "request_id": run.request_id,
                "session_id": run.session_id,
                "content": f"现有结果无法保存和展示：{exc}。",
                "validation_passed": False,
            },
        )
        if run.thinking_mode:
            await run.send_thinking_status("error", "现有结果无法展示")
        await run.send_step(
            "finished",
            "finished",
            "error",
            "现有结果无法展示",
            str(exc),
        )
        return
    except ArtifactSaveError as exc:
        logger.exception(f"[{run.request_id}] 保存失败: {exc}")
        await _send_event(
            run.sink,
            {
                "type": "error",
                "request_id": run.request_id,
                "session_id": run.session_id,
                "code": "artifact_save_failed",
                "error": f"Blueprint 已生成但保存失败: {exc}",
            },
        )
        await run.send_step("finished", "finished", "error", "保存失败", str(exc))
        return

    session_metrics["status"] = "complete" if delivery.validation_passed else "failed"
    session_metrics["validation_errors"] = delivery.validation.errors
    await run.send_debug("session_metrics", session_metrics)
    await _send_event(
        run.sink,
        {
            "type": "blueprint_generated",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "filename": delivery.filename,
            "file_url": delivery.file_url,
            "validation_passed": delivery.validation_passed,
        },
    )
    if run.thinking_mode:
        await run.send_thinking_status(
            "completed" if delivery.validation_passed else "error",
            "生成与校验已完成" if delivery.validation_passed else "已生成，校验未通过",
        )
    await run.send_step(
        "finished",
        "finished",
        "done" if delivery.validation_passed else "error",
        "生成完成" if delivery.validation_passed else "已生成，校验未通过",
        "Blueprint 已保存，可查看现有结果",
    )
    await _send_event(
        run.sink,
        {
            "type": "agent_reply",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "content": (
                f"执行错误：{run.execution_error}。\n\n" if run.execution_error else ""
            )
            + delivery.reply,
            "validation_passed": delivery.validation_passed,
        },
    )

    logger.info(
        f"[{run.request_id}] [langgraph] 完成: {len(active_diags)}活跃节点, "
        f"建议组件: {run.suggested_components}, RAG {total_rag_ms}ms, "
        f"LLM {total_llm_ms}ms, tokens {run.total_tokens['input'] + run.total_tokens['output']}"
    )
