"""生成用例入口：准备请求、恢复图、执行流、读取快照并交付结果。"""
import asyncio
from loguru import logger
from config import config
from app.agent.routing import detect_target_kind
from app.domain.design.architecture import resolve_complexity_profile
from app.infrastructure.observability.trace import rag_trace_scope
from app.domain.blueprint.artifacts import retain_generation_blueprint
from app.application.generation.jobs import generation_job_service
from app.application.generation.requests import _emit_safety_refusal_if_needed
from app.application.generation.requests import _payload_access_context
from app.application.generation.events import _send_event
from app.application.generation.events import EventSink
from app.application.generation.context import GenerationExecution
from app.application.generation.streaming import consume_graph_events
from app.application.generation.finalize import deliver_result
from app.application.generation.errors import _friendly_graph_error


async def run_generation(sink, payload: dict, resume: bool = False) -> None:
    """持久化任务 runner：事件写入 durable sink，不绑定某条物理连接。"""
    access = _payload_access_context(payload)
    with rag_trace_scope(
        str(payload.get("request_id") or "unknown"),
        session_id=str(payload.get("session_id") or payload.get("request_id") or "unknown"),
        access_context=access,
    ) as trace:
        if await _emit_safety_refusal_if_needed(sink, payload):
            return
        try:
            await execute_graph(sink, payload, resume=resume)
        except asyncio.CancelledError as exc:
            trace.finish(status="stopped" if exc.args == ("user_stop",) else "paused")
            raise


async def execute_graph(ws: EventSink, data: dict, *, resume: bool = False):
    run = GenerationExecution(sink=ws, data=data)
    from app.agent.state import GenerationState
    from app.agent.state import merge_state_mapping

    run.request_id = run.data.get("request_id", "")
    run.message = run.data.get("message", "")
    run.current_blueprint = run.data.get("blueprint")
    run.selection = run.data.get("selection", [])
    run.session_id = run.data.get("session_id", run.request_id)
    run.detail_level = resolve_complexity_profile(run.data.get("detail_level") or "minimal")["level"]
    # 开关只控制设计思考及其状态提示，普通执行摘要仍始终推送。
    run.thinking_mode = run.data.get("thinking_mode") is True

    logger.info(f"[{run.request_id}] [langgraph] 收到: {run.message[:80]}...")


    # ── 初始状态 ──
    #
    # building_type 是入口预标签，最终类型由分类器和建筑方案确定。
    # 先区分建筑与物件，避免把物件需求标为建筑。
    preliminary_target = detect_target_kind(run.message, "generate")
    run.initial_state: GenerationState = {
        "request_id": run.request_id,
        "user_message": run.message,
        "building_type": "custom" if preliminary_target == "architecture" else "asset",
        "session_id": run.session_id,
        "current_blueprint": run.current_blueprint,
        "selection": run.selection,
        "recent_messages": run.data.get("recent_messages", []),
        "workflow_state": str(run.data.get("workflow_state") or "idle"),
        "thinking_mode": run.data.get("thinking_mode") is True,
        "detail_level": run.detail_level,
        "procedural_materials_enabled": run.data.get("procedural_materials_enabled") is True,
        "max_retries": 3,
        "retry_count": 0,
        "component_fragments": {},
        "component_diagnostics": {},
        "style_revision": 0,
    }

    if run.thinking_mode:
        await run.send_thinking_status("thinking", "设计阶段将使用思考模式")

    # ── 流式执行（astream_events: 可获取节点 start/end 事件）──
    from app.agent.graph import get_graph
    from app.agent.graph import plan_recursion_limit
    from app.domain.components.registry import get_implemented_components
    from app.agent.runtime import bind_reasoning_callback
    from app.agent.runtime import reset_reasoning_callback

    run.component_configs = {
        config.component_type: config for config in get_implemented_components()
    }
    # 首次按构件类型估算图步骤；checkpoint 恢复时使用实际标记数量。
    recursion_limit = plan_recursion_limit(
        len(run.component_configs) * 3,
        run.initial_state["max_retries"],
    )
    run.graph_config = {
        "configurable": {"thread_id": f"generation:{run.request_id}"},
        "recursion_limit": recursion_limit,
    }
    run.all_diags: dict[str, dict] = {}
    run.final_state = None
    run.resolved_intent = None
    run.node_outputs: dict[str, dict] = {}
    run.total_tokens = {"input": 0, "output": 0}
    run.node_starts: dict[str, float] = {}  # 节点名 → perf_counter 起始点
    run.node_started_isos: dict[str, str] = {}  # 节点名 → UTC 起始时间
    run.suggested_components = []  # 存储骨架节点建议的组件列表
    run.observed_state = dict(run.initial_state)
    run.retained_blueprint = retain_generation_blueprint(run.observed_state)
    run.execution_error = None
    run.graph = None

    # 执行摘要始终推送；模型原始 reasoning 由 enable_thinking 控制。
    reasoning_token = bind_reasoning_callback(run.send_thinking_delta)
    event_stream = None

    try:
        await generation_job_service.initialize()
        run.graph = get_graph(enable_callback=True, checkpointer=generation_job_service.checkpointer)
        graph_input = run.initial_state
        if resume:
            snapshot = await run.graph.aget_state(run.graph_config)
            if snapshot.values:
                run.observed_state.update(snapshot.values)
                run.retained_blueprint = retain_generation_blueprint(run.observed_state, run.retained_blueprint)
                marker_count = len((snapshot.values.get("resolved_design") or {}).get("component_markers") or [])
                if marker_count:
                    run.graph_config["recursion_limit"] = plan_recursion_limit(marker_count, snapshot.values.get("max_retries", 3))
                run.resolved_intent = snapshot.values.get("intent")
                run.suggested_components = snapshot.values.get(
                    "suggested_components", []
                )
                if snapshot.next:
                    graph_input = None
                    logger.info(
                        f"[{run.request_id}] 从 checkpoint 恢复，待执行节点: "
                        f"{', '.join(snapshot.next)}"
                    )
                else:
                    # 图已经结束但进程可能在结果落盘/发事件前退出；直接从最终状态交付。
                    run.final_state = dict(snapshot.values)
                    output_key = {
                        "generate": "final_validate",
                        "chat": "chat",
                        "edit": "patch",
                    }.get(run.resolved_intent)
                    if output_key:
                        run.node_outputs[output_key] = run.final_state
                    graph_input = None
                    logger.info(f"[{run.request_id}] checkpoint 已完成，继续结果交付")

        async def empty_event_stream():
            if False:
                yield {}

        event_stream = (
            run.graph.astream_events(
                graph_input,
                config=run.graph_config,
                version="v2",
            )
            if run.final_state is None
            else empty_event_stream()
        )

        await consume_graph_events(run, event_stream)

    except Exception as e:
        logger.exception(f"[{run.request_id}] LangGraph 异常: {e}")
        if "classifier" in run.node_starts:
            from app.agent.workflows.intent.decision import IntentOutputError
            from app.infrastructure.llm.errors import classify_model_error

            error_event = {
                "type": "error",
                "request_id": run.request_id,
                "session_id": run.session_id,
            }
            if isinstance(e, IntentOutputError):
                error_text = str(e)
                error_event["code"] = "invalid_intent"
            else:
                model_error = classify_model_error(e)
                error_text = model_error["user_message"]
                error_event.update(
                    code="model_service_error",
                    error_category=model_error["category"],
                    retryable=model_error["retryable"],
                )
            error_event["error"] = error_text
            await run.send_step("generating", "classifier", "error", "意图分类", error_text)
            await _send_event(run.sink, error_event)
            if run.thinking_mode:
                await run.send_thinking_status("error", error_text)
            await run.send_step("finished", "finished", "error", "意图识别失败", error_text)
            return
        run.execution_error = _friendly_graph_error(e)
        run.final_state = {**run.observed_state, "status": "failed", "error": run.execution_error}
    finally:
        try:
            close = getattr(event_stream, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception as exc:
                    logger.error(f"[{run.request_id}] 关闭执行流失败，保留已有结果: {exc}")
                    run.execution_error = run.execution_error or str(exc)
        finally:
            reset_reasoning_callback(reasoning_token)

    # 图结束后读取完整 checkpoint，继续交付已有产物。
    snapshot = None
    if run.graph is not None:
        try:
            snapshot = await run.graph.aget_state(run.graph_config)
        except Exception as exc:
            logger.error(f"[{run.request_id}] checkpoint 读取失败，使用已收到的节点结果: {exc}")
            run.execution_error = run.execution_error or str(exc)
    if snapshot is not None and not snapshot.next and snapshot.values:
        # 完成时以完整 checkpoint 为准，节点局部输出不一定包含所有业务产物。
        run.final_state = dict(snapshot.values)
    if run.execution_error:
        run.final_state = {**(run.final_state or run.observed_state), "status": "failed", "error": run.execution_error}
    if run.final_state and run.final_state.get("terminal_model_error"):
        run.execution_error = run.execution_error or run.final_state["terminal_model_error"].get("user_message") or run.final_state.get("error")

    if (run.execution_error and run.final_state and run.final_state.get("plan") and "compile" not in run.node_outputs
            and (run.final_state.get("design_document") or {}).get("decisions", {}).get("kind") == "architecture"):
        # 图或 checkpoint 意外中断也要走相同编译入口，避免已收到的分片直接报废。
        try:
            from app.agent.nodes.compile_node import compile_node
            compiled_draft = await compile_node(run.final_state)
            run.final_state = {**run.final_state, **compiled_draft, "status": "failed", "error": run.execution_error}
            run.node_outputs["compile"] = compiled_draft
            run.retained_blueprint = retain_generation_blueprint(run.final_state, run.retained_blueprint)
            await run.send_debug("node", {"node": "compile", "stage": "done", **compiled_draft["compile_report"]})
        except Exception as exc:
            logger.error(f"[{run.request_id}] 中断后的编译未完成，仍保存原始分片: {exc}")

    if run.final_state is None:
        await _send_event(run.sink, {
            "type": "error",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "error": "未返回结果",
        })
        await run.send_step("finished", "finished", "error", "处理失败", "未返回结果")
        return

    run.resolved_intent = run.final_state.get("intent") or run.resolved_intent
    if run.execution_error and retain_generation_blueprint(run.final_state, run.retained_blueprint) is not None:
        run.resolved_intent = "generate"
    if run.resolved_intent not in {"generate", "edit", "chat"}:
        error_text = run.execution_error or "意图分类未返回合法结果，已停止处理，未执行建筑生成或场景修改。"
        await _send_event(run.sink, {
            "type": "error",
            "request_id": run.request_id,
            "session_id": run.session_id,
            "code": "generation_failed" if run.execution_error else "invalid_intent",
            "error": error_text,
        })
        await run.send_step("finished", "finished", "error", "执行失败" if run.execution_error else "意图识别失败", error_text)
        return

    # ── 知识问答：正式回答与执行过程分离 ──
    await deliver_result(run)
