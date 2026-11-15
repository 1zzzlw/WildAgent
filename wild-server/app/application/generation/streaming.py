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
    async for event in event_stream:
        kind = event.get("event")
        node_name = event.get("name", "")
        if kind in ("on_chain_start", "on_chain_end"):
            logger.info(f"[DEBUG astream] kind={kind}, name={node_name!r}")
        if node_name not in _OUR_NODES:
            continue

        label = _node_label(node_name)
        # ── 节点开始 ──
        if kind == "on_chain_start":
            run.node_starts[node_name] = time.perf_counter()
            run.node_started_isos[node_name] = _utc_now_iso()
            detail = _NODE_START_DETAILS.get(node_name)
            if detail:
                await run.send_step("generating", node_name, "running", label, detail)

        # ── 节点结束 ──
        elif kind == "on_chain_end":
            node_output = event.get("data", {}).get("output", {})
            if not isinstance(node_output, dict):
                node_output = {}
            run.node_outputs[node_name] = node_output
            for key, value in node_output.items():
                run.observed_state[key] = (merge_state_mapping(run.observed_state.get(key), value)
                                       if key in {"component_fragments", "component_diagnostics"} else value)
            if any(key in node_output for key in (
                    "final_blueprint", "merged_blueprint", "skeleton_blueprint", "component_fragments")):
                run.retained_blueprint = retain_generation_blueprint(run.observed_state, run.retained_blueprint)
            run.final_state = dict(run.observed_state)

            # ── 请求级节点观测：墙钟耗时 + 子耗时分解 ──
            # 每个 request 落一条节点记录到 RAGTrace.nodes，供耗时/重试归因。
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
                        output_size=len(json.dumps(node_output, ensure_ascii=False, default=str)),
                        error=diag_for_trace.get("error"),
                        model=getattr(config.chat, "name", None),
                    )
                except Exception as exc:
                    logger.warning(f"[{run.request_id}] 节点观测记录失败 ({node_name}): {exc}")

            # skeleton：提取组件建议
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

            # ── 节点完成处理 ──
            if node_name == "classifier":
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
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": "done",
                    "intent": intent,
                    "target": node_output.get("intent_target"),
                    "profile": node_output.get("intent_profile"),
                    "reason": node_output.get("intent_reason"),
                    "source": node_output.get("intent_source"),
                })

            elif node_name == "chat":
                chat_reply = node_output.get("chat_reply", "")
                chat_diag = node_output.get("chat_diag", {})
                await run.send_step(
                    "generating", node_name, "done", label,
                    f"{len(chat_reply)} 字符 · RAG {chat_diag.get('rag_chars', 0)} 字 · "
                    f"LLM {chat_diag.get('llm_ms', 0)}ms",
                )
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": "done",
                    "rag_chars": chat_diag.get("rag_chars"),
                    "rag_ms": chat_diag.get("rag_ms"),
                    "llm_chars": chat_diag.get("llm_chars"),
                    "llm_ms": chat_diag.get("llm_ms"),
                    "token_usage": chat_diag.get("token_usage"),
                    "total_ms": chat_diag.get("total_ms"),
                })

            elif node_name == "patch":
                patch = node_output.get("scene_patch")
                patch_diag = node_output.get("patch_diag", {})
                if node_output.get("error") or not patch:
                    await run.send_step(
                        "generating", node_name, "error", label,
                        node_output.get("error", "未生成修改提案"),
                    )
                    await run.send_debug("node", {
                        "node": node_name,
                        "label": label,
                        "stage": "error",
                        **patch_diag,
                    })
                else:
                    operation_count = patch_diag.get("operation_count", len(patch.get("operations", [])))
                    await run.send_step(
                        "generating", node_name, "done", label,
                        f"{operation_count} 项修改，等待用户确认",
                    )
                    await run.send_debug("node", {
                        "node": node_name,
                        "label": label,
                        "stage": "done",
                        **patch_diag,
                    })

            elif node_name == "architecture":
                plan = node_output.get("architecture_plan", {})
                massing = plan.get("massing", {})
                stage = "error" if node_output.get("error") or node_output.get("status") == "failed" else "done"
                await run.send_step(
                    "generating", node_name, stage, label,
                    (node_output.get("error") or "建筑图纸未通过检查") if stage == "error" else
                    "完整图纸 · "
                    f"{massing.get('width', '?')}×{massing.get('depth', '?')}m · "
                    f"{massing.get('floors', '?')}层 · {plan.get('roof', {}).get('type', '?')}屋顶",
                )
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": stage,
                    **diag,
                    "concept": plan.get("concept"),
                    "massing": massing,
                    "roof": plan.get("roof"),
                })

            elif node_name == "object_design":
                plan = node_output.get("architecture_plan", {})
                objects = plan.get("objects") if isinstance(plan, dict) else None
                objects = objects if isinstance(objects, list) else []
                piece_count = sum(
                    int(item.get("count") or 0)
                    for item in objects
                    if isinstance(item, dict)
                )
                await run.send_step(
                    "generating", node_name, "done", label,
                    f"{len(objects)} 类物件 · 共 {piece_count} 件"
                    + (" · 使用确定性兜底" if diag.get("used_fallback") else ""),
                )
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": "done",
                    **diag,
                    "concept": plan.get("concept") if isinstance(plan, dict) else None,
                    "objects": objects,
                })

            elif node_name == "material_plan":
                material_diag = node_output.get("material_diag", {})
                await run.send_step(
                    "generating", node_name, "done", label,
                    f"PBR 资产 {material_diag.get('selected_asset_count', 0)} 个 · "
                    f"{'受控回退' if material_diag.get('used_fallback') else '审美方案已解析'}",
                )
                if material_diag:
                    run.all_diags[node_name] = material_diag
                    await run.send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        **material_diag,
                    })
                document = node_output.get("design_document")
                if document:
                    await _send_event(run.sink, {
                        "type": "design_ready", "request_id": run.request_id, "session_id": run.session_id,
                        "document": document, "resolved": node_output.get("resolved_design") or {},
                        "preview_url": f"/api/designs/{run.session_id}/preview.svg?revision={document['revision']}",
                    })

            elif node_name == "skeleton":
                if node_output.get("error"):
                    await run.send_step(
                        "generating", node_name, "error", label,
                        node_output["error"],
                    )
                else:
                    ec = diag.get("element_count", "?")
                    suggested = node_output.get("suggested_components") or []
                    await run.send_step(
                        "generating", node_name, "done", label,
                        f"已生成 {ec} 个主体元素 · 建议 {len(suggested)} 类后续组件",
                    )
                    await run.send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        "llm_ms": diag.get("llm_ms"),
                        "token_usage": diag.get("token_usage"),
                        "element_count": diag.get("element_count"),
                        "suggested_components": suggested,
                        "deterministic_fallback": diag.get("deterministic_fallback", False),
                        "total_ms": diag.get("total_ms"),
                    })

            elif node_name == "compile":
                report = node_output.get("compile_report") or {}
                detail = f"{report.get('elements', '?')} 元素 + {report.get('components', '?')} 构件"
                if report.get("abandoned_markers"):
                    detail += f" · 舍弃 {len(report['abandoned_markers'])} 个图纸标记"
                repair = report.get("repair") or {}
                if repair.get("attempted"):
                    detail += " · 集中修复一次" + ("，已采用" if repair.get("accepted") else "，保留原稿")
                step_status = "error" if report.get("ok") is False else "done"
                await run.send_step("generating", node_name, step_status, label, detail)
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": "done",
                    **report,
                })
            elif node_name == "final_validate":
                # 校验流水线结果
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
                    "generating", node_name,
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

            elif node_name == "execute":
                # 条目级进度：串行轮是一条；安全并发轮会一次返回同组的多条结果。
                item_id = node_output.get("current_item_id")
                execute_diag = node_output.get("execute_diag") or {}
                for result in execute_diag.get("item_results") or []:
                    await run.send_step(
                        "generating", f"plan:{result['item_id']}",
                        "done" if result["run_state"] == "succeeded" else "error",
                        result.get("label") or result["kind"], result.get("evidence") or "",
                    )
                item_ids = execute_diag.get("item_ids") or ([item_id] if item_id else [])
                tool_calls = int(execute_diag.get("tool_calls") or 0)
                if len(item_ids) > 1:
                    detail = (
                        f"并发 {len(item_ids)} 条：{'、'.join(item_ids)}"
                        f" · 工具调用 {tool_calls} 次"
                    )
                else:
                    detail = f"{item_id or '无待办条目'} · 工具调用 {tool_calls} 次"
                await run.send_step(
                    "generating", node_name, "done", label,
                    detail,
                )
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": "done",
                    "item_id": item_id,
                    "item_ids": item_ids,
                    "parallel_count": len(item_ids),
                    "tool_calls": tool_calls,
                    "item_results": execute_diag.get("item_results") or [],
                })

            elif node_name == "replanner":
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
                await run.send_debug("node", {
                    "node": node_name, "label": label, "stage": "done",
                    **diag,
                })

            elif node_name == "plan":
                total = len(node_output.get("plan_events") or [])
                budget = (node_output.get("plan") or {}).get("budget", {})
                await run.send_step(
                    "generating", node_name, "done", label,
                    f"展开 {total} 条条目 · 档位预算 {budget.get('iterations', '?')} 轮",
                )

            elif node_name == "callback":
                retry_number = node_output.get("retry_count", 0)
                if node_output.get("error"):
                    await run.send_step(
                        "generating", node_name, "error", label,
                        f"修正失败：{node_output['error']}",
                    )
                else:
                    await run.send_step(
                        "generating", node_name, "done", label,
                        f"已发起第 {retry_number} 轮修复（每目标最多 "
                        f"{run.initial_state.get('max_retries', 3)} 次）",
                    )
                    await run.send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        "retry_count": retry_number,
                    })

            # plan 是数据：**每个产出 plan 的节点都推一次全量 plan**（plan / execute /
            # replanner 都返回 plan），前端整份替换。之所以不只在 plan 节点推一次：
            # replanner 追加的条目不会进 plan_events（增量只记状态变化），只推首次会让
            # 追加项永远到不了前端。plan_item_updated 是状态变化的增量提示，不是唯一通道。
            plan_payload = node_output.get("plan")
            if isinstance(plan_payload, dict) and plan_payload.get("items") is not None:
                await _send_event(run.sink, {
                    "type": "plan_ready",
                    "request_id": run.request_id,
                    "session_id": run.session_id,
                    "plan": plan_payload,
                })
            for item_event in node_output.get("plan_events") or []:
                await _send_event(run.sink, {
                    "type": "plan_item_updated",
                    "request_id": run.request_id,
                    "session_id": run.session_id,
                    "item": item_event,
                })

