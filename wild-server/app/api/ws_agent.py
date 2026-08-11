"""
Agent WebSocket API

前端连接路径: ws://localhost:8000/ws/agent

消息协议（与前端 agentBridge.ts + types/agent.ts 对齐）：

前端 -> 后端:
  {
    "protocol_version": "1.0",
    "type": "user_message",
    "request_id": "req_xxx",
    "session_id": "sess_xxx",
    "scene_id": "scene_xxx",
    "scene_revision": 8,
    "message": "生成一座中式凉亭",
    "thinking_mode": false,
    "scene_summary": { "elements_count": 42, "types": [...], "bbox": {...} },
    "selection": []
  }

  心跳:
  { "protocol_version": "1.0", "type": "ping", "timestamp": 1234567890 }

后端 -> 前端:
  所有消息均包含 "protocol_version": "1.0"。
  agent_step:          { "type": "agent_step", "request_id": "...", "stage": "analyzing", "node": "classifier", "status": "running", "label": "意图分类", "detail": "..." }
  thinking_delta:      { "type": "thinking_delta", "request_id": "...", "delta": "..." }
  thinking_status:     { "type": "thinking_status", "request_id": "...", "status": "thinking|completed|unsupported|error" }
  blueprint_generated: { "type": "blueprint_generated", "request_id": "...", "session_id": "...", "filename": "YYYY-MM-DD/session_xxx_name.wild", "file_url": "/api/scenes/..." }
  agent_reply:         { "type": "agent_reply", "request_id": "...", "content": "..." }
  error:               { "type": "error", "request_id": "...", "error": "..." }

  心跳:
  pong:           { "type": "pong", "timestamp": 1234567890 }
  network_error:  { "type": "network_error", "error": "心跳超时，连接即将关闭", "reason": "heartbeat_timeout" }
  presence_update:{ "type": "presence_update", "online_count": 2, "clients": [{ "masked_ip": "113.96.*.*", "region": "广东省", ... }] }

心跳机制：
- 前端每 15s 发送 ping，后端立即回复 pong
- 后端监控（WebSocketHeartbeat）：空闲时超过 90s 未收到任何消息 → 发送 network_error → 关闭连接
  （90s 是为了兼容浏览器后台标签页对 setInterval 的节流，浏览器通常节流到 ~60s）
- AI 查询处理期间（is_processing=True）不触发心跳超时，避免长时间 LLM 调用被误判为断连
- user_message 改为后台任务执行（asyncio.create_task），确保接收循环不被阻塞，ping 能及时响应
- 同一时间只允许一条 user_message 在处理中（asyncio.Lock），并发请求会收到错误提示
- 前端收到 network_error 后通过 ElNotification 弹窗提示用户
- 前端监听页面可见性变化（visibilitychange），页面恢复可见时立即检测连接状态并补发心跳
"""
import json
import asyncio
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from app.agent.protocol import AGENT_PROTOCOL_VERSION, versioned_event
from app.services.agent_service import agent_service
from app.services.agent_delivery import (
    ArtifactSaveError,
    GenerationRejectedError,
    final_validation_results,
    prepare_blueprint_delivery,
)
from app.services.generation_job_service import generation_job_service
from app.extensions.presence import presence_service
from app.utils.ws_heartbeat import WebSocketHeartbeat

router = APIRouter()


async def _send_event(ws: WebSocket, payload: dict) -> None:
    """为所有后端事件附加统一协议版本。"""
    await ws.send_json(versioned_event(payload))


async def _run_persistent_langgraph(sink, payload: dict, resume: bool) -> None:
    """持久化任务 runner：事件写入 durable sink，不绑定某条物理连接。"""
    await _handle_with_langgraph(sink, payload, resume=resume)


async def startup_generation_jobs() -> None:
    """初始化 checkpointer，并恢复上次服务退出时未完成的精密模式任务。"""
    await generation_job_service.startup(_run_persistent_langgraph)


async def shutdown_generation_jobs() -> None:
    """在进程退出前暂停任务；checkpoint 和 running 状态保留用于下次恢复。"""
    await generation_job_service.shutdown()


async def _process_user_message_safely(
    ws: WebSocket, data: dict, heartbeat: WebSocketHeartbeat
):
    """在后台任务边界处理单条用户消息。

    这里统一维护心跳的 ``is_processing`` 状态，并把浏览器主动断开视为正常结束；
    其他异常尽量转成协议内的 ``error`` 消息，避免异常逃逸并终止接收循环。
    """
    request_id = data.get("request_id", "")
    # LLM 可能运行较久，处理期间不应因为没有收到新消息而触发心跳超时。
    heartbeat.is_processing = True
    try:
        await _handle_user_message(ws, data)
    except asyncio.CancelledError:
        logger.info(f"[{request_id}] WebSocket 已断开，取消生成任务")
        raise
    except WebSocketDisconnect:
        logger.info(f"[{request_id}] WebSocket 已断开，停止发送生成结果")
    except Exception as exc:
        logger.exception(f"[{request_id}] Agent 消息处理失败: {exc}")
        try:
            await _send_event(ws, {
                "type": "error",
                "request_id": request_id,
                "error": f"Agent 处理失败: {str(exc)}",
            })
        except Exception:
            # 发送错误时连接也可能已经断开，此时无需再次抛出。
            pass
    finally:
        # 无论成功、失败还是取消，都恢复心跳监控并刷新空闲计时起点。
        heartbeat.is_processing = False
        heartbeat.touch()


@router.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    """维护一个 Agent WebSocket 连接的完整生命周期。

    接收循环始终保持轻量，只负责解析协议、回复 ping 和启动后台生成任务；
    耗时的 LLM 请求不会阻塞心跳。快速模式任务仍跟随连接生命周期；精密模式
    任务由持久化服务托管，断线后继续运行并在重连时补发关键事件。
    """
    await ws.accept()
    logger.info("Agent WebSocket 客户端已连接")

    # ---------- 心跳监控 ----------
    heartbeat = WebSocketHeartbeat(timeout=90, check_interval=10)
    connection_alive = True

    async def on_heartbeat_timeout(elapsed: float):
        """心跳超时回调：通知前端并关闭连接"""
        nonlocal connection_alive
        logger.warning(f"Agent WebSocket 心跳超时: {elapsed:.0f}s 未收到消息，关闭连接")
        try:
            await _send_event(ws, {
                "type": "network_error",
                "error": "心跳超时，连接已断开",
                "reason": "heartbeat_timeout"
            })
        except Exception:
            pass
        # 先翻转循环条件，再主动关闭 socket，让阻塞中的 receive_text() 退出。
        connection_alive = False
        try:
            await ws.close()
        except Exception:
            pass

    await heartbeat.start(on_heartbeat_timeout)
    await presence_service.connect(ws)

    # ---------- 消息处理状态 ----------
    # 锁保护真正的处理区；active_message_task 让接收循环能立即拒绝并发请求。
    processing_lock = asyncio.Lock()
    active_message_task: asyncio.Task | None = None

    async def handle_user_message_safe(data: dict):
        """在锁保护下处理用户消息，同时更新心跳标记"""
        async with processing_lock:
            await _process_user_message_safely(ws, data, heartbeat)

    # ---------- 消息接收循环 ----------
    try:
        while connection_alive:
            # receive_text 在没有消息时挂起，但不占用事件循环线程。
            raw = await ws.receive_text()
            # 任意合法/非法文本都表示连接仍活跃，应刷新最后消息时间。
            heartbeat.touch()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send_event(ws, {
                    "type": "error",
                    "request_id": None,
                    "error": "消息格式错误，需要 JSON"
                })
                continue

            protocol_version = data.get("protocol_version")
            if protocol_version not in (None, AGENT_PROTOCOL_VERSION):
                await _send_event(ws, {
                    "type": "error",
                    "request_id": data.get("request_id"),
                    "session_id": data.get("session_id"),
                    "code": "unsupported_protocol_version",
                    "error": (
                        f"不支持的 Agent 协议版本: {protocol_version}; "
                        f"服务端版本为 {AGENT_PROTOCOL_VERSION}"
                    ),
                })
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                # 原样回传前端时间戳，便于前端计算往返延迟。
                await _send_event(ws, {
                    "type": "pong",
                    "timestamp": data.get("timestamp", int(time.time() * 1000))
                })

            elif msg_type == "presence_identify":
                # 展示名仅交给可选 Presence 扩展，不进入 Agent 或会话数据。
                await presence_service.update_display_name(
                    ws,
                    data.get("display_name"),
                )

            elif msg_type == "user_message":
                if data.get("precision_mode") is True:
                    job, created = await generation_job_service.start_job(data, ws)
                    if not created:
                        await generation_job_service.resume_or_replay(
                            ws,
                            request_id=job.request_id,
                            session_id=job.session_id,
                            after_seq=int(data.get("last_event_seq") or 0),
                        )
                elif active_message_task is not None and not active_message_task.done():
                    await _send_event(ws, {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "error": "正在处理上一条消息，请稍后再发送"
                    })
                else:
                    # 后台执行保证接收循环继续响应 ping；任务引用用于退出时取消。
                    active_message_task = asyncio.create_task(
                        handle_user_message_safe(data)
                    )

            elif msg_type == "resume_generation":
                await generation_job_service.resume_or_replay(
                    ws,
                    request_id=data.get("request_id"),
                    session_id=str(data.get("session_id") or ""),
                    after_seq=int(data.get("last_event_seq") or 0),
                )

            else:
                await _send_event(ws, {
                    "type": "error",
                    "request_id": data.get("request_id"),
                    "error": f"未知消息类型: {msg_type}"
                })

    except WebSocketDisconnect:
        logger.info("Agent WebSocket 客户端已断开")
    except Exception as e:
        logger.error(f"Agent WebSocket 异常: {e}")
        try:
            await _send_event(ws, {
                "type": "network_error",
                "error": f"服务端异常: {str(e)}",
                "reason": "connection_lost"
            })
        except Exception:
            pass
    finally:
        connection_alive = False
        await generation_job_service.detach(ws)
        if active_message_task is not None:
            if not active_message_task.done():
                # 快速模式没有持久化边界，连接断开时仍取消下游 LLM 任务。
                active_message_task.cancel()
            try:
                await active_message_task
            except asyncio.CancelledError:
                pass
        await heartbeat.stop()
        await presence_service.disconnect(ws)


async def _handle_user_message(ws: WebSocket, data: dict):
    """前端传 precision_mode=true → LangGraph 精密模式; 否则 → LangChain 快速模式

    意图判断（生成建筑 vs 普通对话）交由 LangGraph 的 classifier 节点完成，
    精密模式下所有消息都进入 LangGraph 图。
    """
    precision_mode = data.get("precision_mode") is True

    if precision_mode:
        await _handle_with_langgraph(ws, data)
    else:
        await _handle_with_langchain(ws, data)


# ── 节点名 → 展示标签 ──
_NODE_LABELS = {
    "classifier": "意图分类",
    "chat": "知识问答",
    "patch": "场景修改",
    "architecture": "建筑方案",
    "skeleton": "骨架",
    "merge": "合并", "final_validate": "最终校验", "callback": "修正",
}
# gen/val 标签动态生成: _node_label("door_gen") → "门·生成"
def _node_label(name: str) -> str:
    if name in _NODE_LABELS:
        return _NODE_LABELS[name]
    from app.agent.component_registry import get_implemented_components

    for config in get_implemented_components():
        ct, cl = config.component_type, config.label
        if name == f"{ct}_gen":
            return f"{cl}·生成"
        if name == f"{ct}_val":
            return f"{cl}·校验"
    return name


async def _handle_with_langgraph(ws, data: dict, *, resume: bool = False):
    """LangGraph 精密模式：分片并行 + 每节点实时推送 RAG/LLM/思考诊断 + 性能汇总"""
    from app.agent.graph_state import GenerationState

    request_id = data.get("request_id", "")
    message = data.get("message", "")
    current_blueprint = data.get("blueprint")
    selection = data.get("selection", [])
    session_id = data.get("session_id", request_id)
    # 精密模式下强制开启思考（前端已做联动，此处兜底防止 localStorage 状态不一致）
    thinking_mode = data.get("thinking_mode") is True or data.get("precision_mode") is True

    logger.info(f"[{request_id}] [precision] 收到: {message[:80]}...")

    async def send_step(
        stage: str,
        node: str,
        status: str,
        label: str,
        detail: str,
    ):
        await _send_event(ws, {
            "type": "agent_step", "request_id": request_id,
            "session_id": session_id,
            "stage": stage,
            "step_id": node,
            "node": node,
            "status": status,
            "label": label,
            "detail": detail,
            "content": detail,
        })

    async def send_debug(category: str, data_obj: dict):
        await _send_event(ws, {
            "type": "debug_log", "request_id": request_id,
            "session_id": session_id,
            "category": category, "data": data_obj,
        })
    
    async def send_thinking_delta(node_name: str, delta: str):
        """实时推送节点的思考内容给前端（带节点标识）"""
        await _send_event(ws, {
            "type": "thinking_delta",
            "request_id": request_id,
            "session_id": session_id,
            "node": node_name,  # 标记是哪个节点的思考
            "channel": "progress" if node_name in {"architecture", "merge", "final_validate"} or node_name.endswith("_val") else "reasoning",
            "delta": delta,
        })

    async def send_thinking_status(status: str, content: str = ''):
        await _send_event(ws, {
            "type": "thinking_status",
            "request_id": request_id,
            "session_id": session_id,
            "status": status,
            "content": content,
        })

    # ── 初始状态 ──
    initial_state: GenerationState = {
        "request_id": request_id,
        "user_message": message,
        "building_type": _detect_building_type(message),
        "session_id": session_id,
        "current_blueprint": current_blueprint,
        "selection": selection,
        "thinking_mode": thinking_mode,
        "max_retries": 3,
        "retry_count": 0,
        "component_fragments": {},
        "component_diagnostics": {},
    }

    if thinking_mode:
        await send_thinking_status("thinking", "正在收集节点思考内容")

    # ── 流式执行（astream_events: 可获取节点 start/end 事件）──
    from app.agent.graph import get_graph
    from app.agent.runtime_context import (
        bind_reasoning_callback,
        reset_reasoning_callback,
    )

    await generation_job_service.initialize()
    graph = get_graph(
        enable_callback=True,
        checkpointer=generation_job_service.checkpointer,
    )
    graph_config = {
        "configurable": {"thread_id": f"generation:{request_id}"},
    }
    all_diags: dict[str, dict] = {}
    final_state = None
    resolved_intent = "generate"
    node_outputs: dict[str, dict] = {}
    total_tokens = {"input": 0, "output": 0}
    suggested_components = []  # 存储骨架节点建议的组件列表

    # 生成所有可能的节点名（gen + val + 固定节点）
    from app.agent.component_registry import get_implemented_components

    _COMP_TYPES = {
        config.component_type for config in get_implemented_components()
    }
    _OUR_NODES = {"classifier", "chat", "patch", "architecture", "skeleton", "merge", "final_validate", "callback"}
    for ct in _COMP_TYPES:
        _OUR_NODES.add(f"{ct}_gen")
        _OUR_NODES.add(f"{ct}_val")

    reasoning_token = bind_reasoning_callback(
        send_thinking_delta if thinking_mode else None
    )
    try:
        graph_input = initial_state
        if resume:
            snapshot = await graph.aget_state(graph_config)
            if snapshot.values:
                resolved_intent = snapshot.values.get("intent", "generate")
                suggested_components = snapshot.values.get(
                    "suggested_components", []
                )
                if snapshot.next:
                    graph_input = None
                    logger.info(
                        f"[{request_id}] 从 checkpoint 恢复，待执行节点: "
                        f"{', '.join(snapshot.next)}"
                    )
                else:
                    # 图已经结束但进程可能在结果落盘/发事件前退出；直接从最终状态交付。
                    final_state = dict(snapshot.values)
                    output_key = {
                        "chat": "chat",
                        "edit": "patch",
                    }.get(resolved_intent, "final_validate")
                    node_outputs[output_key] = final_state
                    graph_input = None
                    logger.info(f"[{request_id}] checkpoint 已完成，继续结果交付")

        async def empty_event_stream():
            if False:
                yield {}

        event_stream = (
            graph.astream_events(
                graph_input,
                config=graph_config,
                version="v2",
            )
            if final_state is None
            else empty_event_stream()
        )
        async for event in event_stream:
            kind = event.get("event")
            node_name = event.get("name", "")
            if kind in ("on_chain_start", "on_chain_end"):
                logger.info(f"[DEBUG astream] kind={kind}, name={node_name!r}")
            if node_name not in _OUR_NODES:
                continue

            label = _node_label(node_name)
            is_gen = node_name.endswith("_gen")
            is_val = node_name.endswith("_val")
            comp_type = node_name[:-4] if is_gen or is_val else node_name

            # ── 节点开始 ──
            if kind == "on_chain_start":
                start_details = {
                    "classifier": "分析用户意图",
                    "chat": "RAG 检索知识库并生成回答",
                    "patch": "分析当前场景并生成修改提案",
                    "architecture": "生成建筑方案候选并执行确定性评分",
                    "skeleton": "RAG 检索并规划建筑骨架",
                    "merge": "合并所有组件分片",
                    "final_validate": "执行最终校验流水线",
                    "callback": "修正失败组件",
                }
                detail = start_details.get(node_name)
                if detail is None and is_gen:
                    detail = "RAG 检索并生成组件"
                elif detail is None and is_val:
                    detail = "执行组件工具校验"
                if detail:
                    await send_step("generating", node_name, "running", label, detail)

            # ── 节点结束 ──
            elif kind == "on_chain_end":
                node_output = event.get("data", {}).get("output", {})
                if not isinstance(node_output, dict):
                    node_output = {}
                node_outputs[node_name] = node_output

                # skeleton：提取组件建议
                if node_name == "skeleton":
                    suggested_components = node_output.get("suggested_components", [])
                    design_brief = node_output.get("design_brief", {})
                    logger.info(f"[{request_id}] 骨架建议组件: {suggested_components}")
                    if design_brief:
                        quota = design_brief.get("component_quota", {})
                        logger.info(f"[{request_id}] 设计清单配额: {quota}")

                # 收集诊断（gen_diag 和 val_diag）
                if is_gen:
                    diag_key = f"{comp_type}_gen_diag"
                elif is_val:
                    diag_key = f"{comp_type}_val_diag"
                else:
                    diag_key = f"{node_name}_diag"
                diag = node_output.get(diag_key, {})
                if diag:
                    all_diags[node_name] = diag

                tu = diag.get("token_usage")
                if tu:
                    total_tokens["input"] += tu.get("input", 0)
                    total_tokens["output"] += tu.get("output", 0)

                # ── 节点完成处理 ──
                if node_name == "classifier":
                    intent = node_output.get("intent", "generate")
                    resolved_intent = intent
                    intent_label = {
                        "generate": "生成建筑",
                        "edit": "修改场景",
                        "chat": "知识问答",
                    }.get(intent, intent)
                    await send_step(
                        "generating", node_name, "done", label,
                        f"意图：{intent_label}",
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        "intent": intent,
                    })

                elif node_name == "chat":
                    chat_reply = node_output.get("chat_reply", "")
                    chat_diag = node_output.get("chat_diag", {})
                    await send_step(
                        "generating", node_name, "done", label,
                        f"{len(chat_reply)} 字符 · RAG {chat_diag.get('rag_chars', 0)} 字 · "
                        f"LLM {chat_diag.get('llm_ms', 0)}ms",
                    )
                    await send_debug("node", {
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
                        await send_step(
                            "generating", node_name, "error", label,
                            node_output.get("error", "未生成修改提案"),
                        )
                        await send_debug("node", {
                            "node": node_name,
                            "label": label,
                            "stage": "error",
                            **patch_diag,
                        })
                    else:
                        operation_count = patch_diag.get("operation_count", len(patch.get("operations", [])))
                        await send_step(
                            "generating", node_name, "done", label,
                            f"{operation_count} 项修改，等待用户确认",
                        )
                        await send_debug("node", {
                            "node": node_name,
                            "label": label,
                            "stage": "done",
                            **patch_diag,
                        })

                elif node_name == "architecture":
                    plan = node_output.get("architecture_plan", {})
                    massing = plan.get("massing", {})
                    selected = diag.get("selected_index", 0) + 1
                    candidate_count = diag.get("candidate_count", 1)
                    fallback_note = " · 使用安全回退" if diag.get("used_fallback") else ""
                    await send_step(
                        "generating", node_name, "done", label,
                        f"候选 {selected}/{candidate_count} · "
                        f"{massing.get('width', '?')}×{massing.get('depth', '?')}m · "
                        f"{massing.get('floors', '?')}层 · {plan.get('roof', {}).get('type', '?')}屋顶"
                        f"{fallback_note}",
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        **diag,
                        "concept": plan.get("concept"),
                        "massing": massing,
                        "roof": plan.get("roof"),
                    })

                elif node_name == "skeleton":
                    if node_output.get("error"):
                        await send_step(
                            "generating", node_name, "error", label,
                            node_output["error"],
                        )
                    else:
                        ec = diag.get("element_count", "?")
                        rc = diag.get("reasoning_chars", 0)
                        await send_step(
                            "generating", node_name, "done", label,
                            f"{ec} 构件 · RAG {diag.get('rag_chars', 0)} 字 · "
                            f"LLM {diag.get('llm_chars', 0)} 字/{diag.get('llm_ms', 0)}ms · "
                            f"过程 {rc} 字 · 建议：{', '.join(suggested_components)}",
                        )
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "rag_chars": diag.get("rag_chars"), "rag_ms": diag.get("rag_ms"),
                            "rag_hits": diag.get("rag_hits", []),
                            "prompt_chars": diag.get("prompt_chars"),
                            "llm_chars": diag.get("llm_chars"), "llm_ms": diag.get("llm_ms"),
                            "token_usage": diag.get("token_usage"),
                            "element_count": diag.get("element_count"),
                            "reasoning_chars": rc,
                            "reasoning_preview": diag.get("reasoning_preview"),
                            "total_ms": diag.get("total_ms"),
                            "suggested_components": suggested_components,
                        })

                elif node_name == "merge":
                    merged = node_output.get("merged_blueprint", {})
                    geom = merged.get("geometry", {})
                    e_count = len(geom.get("elements", []))
                    c_count = len(geom.get("components", []))
                    merge_diag = node_output.get("merge_diag", {})
                    iters = merge_diag.get("iterations", [])
                    merge_errors = merge_diag.get("final_errors", 0)
                    iter_summary = ""
                    if iters:
                        last_iter = iters[-1]
                        iter_summary = f" | {len(iters)}轮校验 {last_iter['passed']}✓ {last_iter['errors']}✗"
                    await send_step(
                        "generating", node_name, "error" if merge_errors else "done", label,
                        f"{e_count} 元素 + {c_count} 组件{iter_summary}",
                    )
                    # 收集 merge 诊断到 all_diags
                    if merge_diag:
                        all_diags[node_name] = merge_diag
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        "element_count": e_count,
                        "component_count": c_count,
                        "iterations": iters,
                        "final_errors": merge_errors,
                        "design_errors": merge_diag.get("design_errors", []),
                        "total_ms": merge_diag.get("total_ms"),
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
                    await send_step(
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
                            validation_detail = out[:150]
                        elif vr.get("has_warning"):
                            validation_status = "done"
                            validation_detail = f"警告：{out[:150]}"
                        else:
                            validation_status = "done"
                            validation_detail = "通过"
                        await send_step(
                            "validating",
                            validation_node,
                            validation_status,
                            validation_label,
                            validation_detail,
                        )

                elif is_gen:
                    if diag.get("error"):
                        await send_step(
                            "generating", node_name, "error", label,
                            diag["error"],
                        )
                    else:
                        fc = diag.get("fragment_count", 0)
                        rc = diag.get("reasoning_chars", 0)
                        await send_step(
                            "generating", node_name, "done", label,
                            f"{fc} 个 · RAG {diag.get('rag_chars', 0)} 字 · "
                            f"LLM {diag.get('llm_chars', 0)} 字/{diag.get('llm_ms', 0)}ms · "
                            f"过程 {rc} 字",
                        )
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "rag_chars": diag.get("rag_chars"), "rag_ms": diag.get("rag_ms"),
                            "rag_hits": diag.get("rag_hits", []),
                            "prompt_chars": diag.get("prompt_chars"),
                            "llm_chars": diag.get("llm_chars"), "llm_ms": diag.get("llm_ms"),
                            "token_usage": diag.get("token_usage"),
                            "reasoning_chars": rc,
                            "reasoning_preview": diag.get("reasoning_preview"),
                            "fragment_count": fc, "total_ms": diag.get("total_ms"),
                        })

                elif node_name == "callback":
                    retry_number = node_output.get("retry_count", 0)
                    if node_output.get("error"):
                        await send_step(
                            "generating", node_name, "error", label,
                            f"修正失败：{node_output['error']}",
                        )
                    else:
                        await send_step(
                            "generating", node_name, "done", label,
                            f"已发起重试 {retry_number}/{initial_state.get('max_retries', 3)}",
                        )
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "retry_count": retry_number,
                        })

                elif is_val:
                    fc = diag.get("fragment_count", 0)
                    fixed = diag.get("validation_applied", False)
                    passed = diag.get("validation_passed", True)
                    result_label = "已修复并通过复检" if fixed and passed else (
                        "修复后复检仍有错误" if not passed else "通过"
                    )
                    await send_step(
                        "generating", node_name, "done" if passed else "error", label,
                        f"{fc} 个 · {result_label} · {diag.get('total_ms', 0)}ms",
                    )

                final_state = node_output

    except Exception as e:
        logger.exception(f"[{request_id}] LangGraph 异常: {e}")
        if thinking_mode:
            await send_thinking_status("error", str(e))
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error": str(e),
        })
        await send_step("finished", "finished", "error", "处理失败", str(e))
        return
    finally:
        reset_reasoning_callback(reasoning_token)

    if final_state is None:
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error": "未返回结果",
        })
        await send_step("finished", "finished", "error", "处理失败", "未返回结果")
        return

    # ── 知识问答：正式回答与执行过程分离 ──
    if resolved_intent == "chat":
        chat_output = node_outputs.get("chat", final_state)
        chat_diag = chat_output.get("chat_diag", {})
        await _send_event(ws, {
            "type": "agent_reply",
            "request_id": request_id,
            "session_id": session_id,
            "content": chat_output.get("chat_reply", "未生成回答"),
            "content_type": "chat",
        })
        await send_debug("session_metrics", {
            "node_count": 2,
            "active_nodes": 2,
            "skipped_nodes": 0,
            "total_rag_ms": chat_diag.get("rag_ms", 0),
            "total_llm_ms": chat_diag.get("llm_ms", 0),
            "total_tokens": chat_diag.get("token_usage") or {"input": 0, "output": 0, "total": 0},
            "fragment_total": 0,
            "validation_steps": 0,
            "validation_errors": 0,
            "status": chat_output.get("status", "complete"),
            "chat_mode": True,
        })
        if thinking_mode:
            await send_thinking_status("completed", "处理已完成")
        await send_step("finished", "finished", "done", "处理完成", "处理完成")
        return

    # ── 增量修改：只发送提案，等待前端确认 ──
    if resolved_intent == "edit":
        patch_output = node_outputs.get("patch", final_state)
        scene_patch = patch_output.get("scene_patch")
        if patch_output.get("error") or not scene_patch:
            error_text = patch_output.get("error", "未生成修改提案")
            await _send_event(ws, {
                "type": "agent_reply",
                "request_id": request_id,
                "session_id": session_id,
                "content": f"无法生成可安全应用的修改提案：{error_text}",
            })
            if thinking_mode:
                await send_thinking_status("error", error_text)
            await send_step("finished", "finished", "error", "处理失败", error_text)
            return

        operations = scene_patch.get("operations", [])
        summary = scene_patch.get("summary") or f"AI 提出了 {len(operations)} 项场景修改"
        await _send_event(ws, {
            "type": "patch_proposal",
            "request_id": request_id,
            "session_id": session_id,
            "patch": {
                "type": "scene_patch",
                "patch_id": f"patch_{request_id}",
                "base_revision": data.get("scene_revision", 0),
                "source": "agent",
                "mode": "proposal",
                "requires_confirmation": True,
                "operations": operations,
                "summary": summary,
            },
        })
        if thinking_mode:
            await send_thinking_status("completed", "修改提案已完成")
        await send_step(
            "finished", "finished", "done", "修改提案已完成", "等待用户确认",
        )
        return

    # ── 生成路径：以最后一次 final_validate 输出为准 ──
    final_state = node_outputs.get("final_validate", final_state)
    merged_blueprint = final_state.get("final_blueprint") or final_state.get("merged_blueprint")
    if not merged_blueprint:
        upstream_failure = _generation_failure_message(node_outputs, final_state)
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error": upstream_failure,
        })
        await send_step(
            "finished", "finished", "error", "生成失败", upstream_failure,
        )
        return

    validation_results = final_state.get("validation_results", [])
    validation_errors = final_state.get("validation_error_count", 0)
    validation_warnings = final_state.get("validation_warning_count", 0)
    final_status = final_state.get("status", "failed")

    active_diags = {key: value for key, value in all_diags.items() if not value.get("skipped")}
    total_rag_ms = sum(value.get("rag_ms", 0) for value in active_diags.values())
    total_llm_ms = sum(value.get("llm_ms", 0) for value in active_diags.values())
    session_metrics = {
        "node_count": len(active_diags),
        "active_nodes": len(active_diags),
        "skipped_nodes": sum(1 for value in all_diags.values() if value.get("stage") == "skipped"),
        "suggested_components": suggested_components,
        "total_rag_ms": total_rag_ms,
        "total_llm_ms": total_llm_ms,
        "total_tokens": {
            "input": total_tokens["input"],
            "output": total_tokens["output"],
            "total": total_tokens["input"] + total_tokens["output"],
        },
        "fragment_total": sum(value.get("fragment_count", 0) for value in active_diags.values()),
        "validation_steps": len(validation_results),
        "validation_errors": validation_errors,
        "retry_count": final_state.get("retry_count", 0),
        "max_retries": initial_state.get("max_retries", 3),
        "status": final_status,
    }
    await send_debug("session_metrics", session_metrics)

    try:
        delivery = prepare_blueprint_delivery(
            merged_blueprint,
            session_id,
            validation_results,
            status=final_status,
            error_count=validation_errors,
            warning_count=validation_warnings,
        )
    except GenerationRejectedError as exc:
        await _send_event(ws, {
            "type": "agent_reply",
            "request_id": request_id,
            "session_id": session_id,
            "content": (
                "生成结果仍有未解决的校验错误，已阻止保存和加载。"
                f"{exc}。"
            ),
        })
        if thinking_mode:
            await send_thinking_status("error", "校验未完全通过")
        await send_step(
            "finished", "finished", "error", "校验未完全通过", "未加载到场景",
        )
        return
    except ArtifactSaveError as exc:
        logger.exception(f"[{request_id}] 保存失败: {exc}")
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "code": "artifact_save_failed",
            "error": f"Blueprint 已生成但保存失败: {exc}",
        })
        await send_step("finished", "finished", "error", "保存失败", str(exc))
        return

    await _send_event(ws, {
        "type": "blueprint_generated",
        "request_id": request_id,
        "session_id": session_id,
        "filename": delivery.filename,
        "file_url": delivery.file_url,
    })
    if thinking_mode:
        await send_thinking_status("completed", "生成与校验已完成")
    await send_step("finished", "finished", "done", "生成完成", "Blueprint 已加载")
    await _send_event(ws, {
        "type": "agent_reply",
        "request_id": request_id,
        "session_id": session_id,
        "content": delivery.reply,
    })

    logger.info(
        f"[{request_id}] [precision] 完成: {len(active_diags)}活跃节点, "
        f"建议组件: {suggested_components}, RAG {total_rag_ms}ms, "
        f"LLM {total_llm_ms}ms, tokens {total_tokens['input'] + total_tokens['output']}"
    )



def _detect_building_type(message: str) -> str:
    """从用户消息推断建筑类型"""
    type_keywords = {
        "chinese_courtyard": ["中式庭院", "庭院", "四合院", "中式"],
        "pavilion": ["凉亭", "亭子", "亭"],
        "modern_house": ["现代", "别墅", "住宅", "房屋"],
        "garage": ["车库"],
        "tower": ["塔", "楼", "高楼", "大厦"],
    }
    for btype, keywords in type_keywords.items():
        if any(kw in message for kw in keywords):
            return btype
    return "building"


def _generation_failure_message(node_outputs: dict, final_state: dict) -> str:
    """优先返回真实上游错误，避免骨架失败被笼统的 Blueprint 缺失覆盖。"""
    return (
        node_outputs.get("skeleton", {}).get("error")
        or node_outputs.get("merge", {}).get("error")
        or final_state.get("error")
        or "最终 Blueprint 缺失"
    )


async def _handle_with_langchain(ws: WebSocket, data: dict):
    """执行一次用户请求，并把 QueryResult 翻译成 WebSocket 协议消息。

    根据 AgentService 的结构化结果分成三条出口：
    完整 Blueprint 会落盘，ScenePatch 等待前端确认，普通对话只返回文本。
    """
    request_id = data.get("request_id", "")
    message = data.get("message", "")
    current_blueprint = data.get("blueprint")
    selection = data.get("selection", [])
    # 只有 JSON 布尔值 true 才开启，避免字符串 "true" 等意外触发日志。
    thinking_mode = data.get("thinking_mode") is True
    # 相同 session_id 使用同一个文件名，因此后续生成会更新该会话的场景文件。
    session_id = data.get("session_id", request_id)

    logger.info(f"[{request_id}] 收到用户消息: {message[:80]}...")

    async def send_step(
        stage: str,
        detail: str,
        *,
        node: str | None = None,
        status: str = "running",
        label: str | None = None,
    ):
        """发送结构化步骤事件；content 仅保留可读文本，不承载协议字段。"""
        step_id = node or stage
        stage_labels = {
            "analyzing": "理解需求",
            "generating": "生成方案",
            "validating": "校验结果",
            "saving": "保存蓝图",
            "finished": "处理完成",
        }
        await _send_event(ws, {
            "type": "agent_step",
            "request_id": request_id,
            "session_id": session_id,
            "stage": stage,
            "step_id": step_id,
            "node": step_id,
            "status": status,
            "label": label or stage_labels.get(stage, stage),
            "detail": detail,
            "content": detail,
        })

    reasoning_received = False

    async def send_reasoning_delta(delta: str):
        """实时转发模型接口实际返回的 reasoning_content。"""
        nonlocal reasoning_received
        reasoning_received = True
        await _send_event(ws, {
            "type": "thinking_delta",
            "request_id": request_id,
            "session_id": session_id,
            "channel": "reasoning",
            "delta": delta,
        })

    async def send_thinking_status(status: str, content: str = ""):
        await _send_event(ws, {
            "type": "thinking_status",
            "request_id": request_id,
            "session_id": session_id,
            "status": status,
            "content": content,
        })

    # ===== Phase 1: 分析 + 生成 =====
    await send_step("analyzing", "正在分析您的需求...")
    await send_step("generating", "正在调用 AI 处理，请耐心等待...")

    # ===== Phase 2: LLM 查询（统一入口，AI 自行判断意图）=====
    if thinking_mode:
        await send_thinking_status("thinking")
    try:
        result = await agent_service.query_structured(
            message,
            current_blueprint,
            selection=selection,
            thinking_mode=thinking_mode,
            on_reasoning_delta=send_reasoning_delta if thinking_mode else None,
        )
    except Exception:
        if thinking_mode:
            await send_thinking_status("error", "模型思考请求失败。")
        raise

    if thinking_mode and reasoning_received:
        await send_thinking_status("completed")
    elif thinking_mode:
        await send_thinking_status(
            "unsupported",
            "当前模型接口没有返回 reasoning_content。",
        )

    # ===== Phase 3: 处理结果（按 AI 输出的格式分发）=====
    if result.blueprint is not None:
        # ── 生成类：完整 Blueprint ──────────────────────────
        # 只展示每个校验器最后一次结果，修正后的 recheck 覆盖初检。
        for pr in final_validation_results(result.pipeline_results):
            if pr.output.startswith("⏭️"):
                continue
            status = "❌" if pr.has_error else "⚠️" if pr.has_warning else "✅"
            await send_step(
                "validating",
                f"{status} {pr.output[:300]}",
                node=f"validation_{pr.step}",
                status="error" if pr.has_error else "done",
                label=f"[{pr.step}] {pr.name}",
            )

        await send_step("saving", "正在保存蓝图文件...")
        try:
            delivery = prepare_blueprint_delivery(
                result.blueprint,
                session_id,
                result.pipeline_results,
                status="failed" if result.error else "complete",
            )
        except GenerationRejectedError as exc:
            logger.warning(f"[{request_id}] 蓝图校验未通过，拒绝下发: {exc}")
            await send_step("finished", str(exc), status="error", label="校验未通过")
            await _send_event(ws, {
                "type": "agent_reply",
                "request_id": request_id,
                "session_id": session_id,
                "content": f"生成的蓝图未通过校验，无法加载到场景：{exc}。请修正需求后重试。",
            })
            return
        except ArtifactSaveError as exc:
            logger.error(f"[{request_id}] 保存 Blueprint 失败: {exc}")
            await _send_event(ws, {
                "type": "error",
                "request_id": request_id,
                "session_id": session_id,
                "code": "artifact_save_failed",
                "error": f"Blueprint 已生成，但服务端保存失败: {exc}",
            })
            await send_step("finished", str(exc), status="error", label="保存失败")
            return

        await _send_event(ws, {
            "type": "blueprint_generated",
            "request_id": request_id,
            "session_id": session_id,
            "filename": delivery.filename,
            "file_url": delivery.file_url,
        })
        await send_step("finished", "Blueprint 已加载", status="done", label="生成完成")
        await _send_event(ws, {
            "type": "agent_reply",
            "request_id": request_id,
            "session_id": session_id,
            "content": delivery.reply,
        })

    elif result.patch is not None:
        # ── 修改类：ScenePatch ──────────────────────────────
        for pr in final_validation_results(result.pipeline_results):
            if pr.output.startswith("⏭️"):
                continue
            status = "❌" if pr.has_error else "⚠️" if pr.has_warning else "✅"
            await send_step(
                "validating",
                f"{status} {pr.output[:300]}",
                node=f"validation_{pr.step}",
                status="error" if pr.has_error else "done",
                label=f"[{pr.step}] {pr.name}",
            )

        # 有 ❌ 级别错误则不发送 patch，改为错误提示
        if result.error:
            logger.warning(f"[{request_id}] Patch 校验失败，不发送: {result.error}")
            await send_step("finished", result.error, status="error", label="修改提案失败")
            await _send_event(ws, {
                "type": "agent_reply",
                "request_id": request_id,
                "session_id": session_id,
                "content": f"生成的修改方案存在问题，无法应用：\n\n{result.error}\n\n请重新描述你的需求。",
            })
        else:
            # Patch 只是 proposal，前端必须让用户确认后才能真正应用到当前场景。
            await send_step("finished", "等待用户确认", status="done", label="修改提案已完成")
            await _send_event(ws, {
                "type": "patch_proposal",
                "request_id": request_id,
                "session_id": session_id,
                "patch": {
                    "type": "scene_patch",
                    "patch_id": f"patch_{request_id}",
                    "base_revision": data.get("scene_revision", 0),
                    "source": "agent",
                    "mode": "proposal",
                    "requires_confirmation": True,
                    "operations": result.patch.get("operations", []),
                    "summary": result.patch.get("summary", "AI 修改建议"),
                },
            })
            logger.info(
                f"[{request_id}] Patch 已发送, "
                f"operations={len(result.patch.get('operations', []))}"
            )

    elif result.error:
        # JSON 已被识别但结构预检失败时，不把无效 Blueprint 当作普通聊天回复。
        needs_selection = result.error == "材质优化前必须先选中一个构件"
        await send_step(
            "finished",
            result.error,
            status="error",
            label="需要选择构件" if needs_selection else "结构预检失败",
        )
        await _send_event(ws, {
            "type": "agent_reply",
            "request_id": request_id,
            "session_id": session_id,
            "content": result.text if needs_selection else (
                f"生成结果未通过结构预检：\n\n{result.error}"
            ),
        })

    else:
        # ── 对话类：纯文本 ──────────────────────────────────
        await send_step("finished", "回答已生成", status="done", label="处理完成")
        await _send_event(ws, {
            "type": "agent_reply",
            "request_id": request_id,
            "session_id": session_id,
            "content": result.text,
        })

    logger.info(f"[{request_id}] 处理完成")
