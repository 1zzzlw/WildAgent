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
    "plan_mode": true,
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
  execution_plan_ready:{ "type": "execution_plan_ready", "request_id": "...", "plan": {...} }
  execution_plan_review_required: { "type": "execution_plan_review_required", "request_id": "...", "plan": {...} }
  floor_plan_ready:    { "type": "floor_plan_ready", "request_id": "...", "floor_plan": {...}, "svg": "<svg...>" }
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
from config import config
from app.agent.intent_classifier import INTENT_LABELS, classify_intent_decision
from app.agent.protocol import AGENT_PROTOCOL_VERSION, versioned_event
from app.agent.procedural_material_recipes import without_procedural_materials
from app.agent.rag_security import (
    AccessContext,
    access_context_from_headers,
    check_content_safety,
    redact_pii,
)
from app.agent.rag_trace import (
    rag_trace_scope,
    record_final_answer,
    record_rag_error,
    record_rag_safety,
)
from app.agent.spatial_plan import is_confirmable_spatial_plan
from app.services.agent_service import agent_service
from app.services.agent_delivery import (
    ArtifactSaveError,
    GenerationRejectedError,
    commit_generation_result,
    final_validation_results,
)
from app.services.generation_job_service import GenerationPaused, generation_job_service
from app.extensions.presence import presence_service
from app.utils.ws_heartbeat import WebSocketHeartbeat

router = APIRouter()


async def _send_event(ws: WebSocket, payload: dict) -> None:
    """为所有后端事件附加统一协议版本。"""
    if payload.get("type") == "agent_reply":
        record_final_answer(str(payload.get("content") or ""))
    elif payload.get("type") == "error":
        record_rag_error(str(payload.get("error") or ""))
    await ws.send_json(versioned_event(payload))


async def _emit_agent_step(
    ws: WebSocket,
    request_id: str,
    session_id: str,
    *,
    stage: str,
    node: str,
    status: str,
    label: str,
    detail: str,
) -> None:
    """共享的结构化步骤事件；快速与精密模式使用同一 payload 形状。"""
    await _send_event(ws, {
        "type": "agent_step",
        "request_id": request_id,
        "session_id": session_id,
        "stage": stage,
        "step_id": node,
        "node": node,
        "status": status,
        "label": label,
        "detail": detail,
        "content": detail,
    })


async def _emit_debug_log(
    ws: WebSocket,
    request_id: str,
    session_id: str,
    *,
    category: str,
    data: dict,
) -> None:
    """共享的调试日志事件。"""
    await _send_event(ws, {
        "type": "debug_log",
        "request_id": request_id,
        "session_id": session_id,
        "category": category,
        "data": data,
    })


async def _emit_thinking_delta(
    ws: WebSocket,
    request_id: str,
    session_id: str,
    *,
    node: str | None,
    channel: str,
    delta: str,
) -> None:
    """共享的思考增量事件；``node`` 为空时省略该字段以保持快速模式旧协议形状。"""
    payload = {
        "type": "thinking_delta",
        "request_id": request_id,
        "session_id": session_id,
        "channel": channel,
        "delta": delta,
    }
    if node is not None:
        payload["node"] = node
    await _send_event(ws, payload)


async def _emit_thinking_status(
    ws: WebSocket,
    request_id: str,
    session_id: str,
    *,
    status: str,
    content: str = "",
) -> None:
    """共享的思考状态事件。"""
    await _send_event(ws, {
        "type": "thinking_status",
        "request_id": request_id,
        "session_id": session_id,
        "status": status,
        "content": content,
    })


async def _emit_floor_plan_ready(
    ws: WebSocket,
    request_id: str,
    session_id: str,
    *,
    floor_plan: dict,
    svg: str,
    svgs: dict[str, str],
    validation: list[dict],
    notice: str = "",
) -> None:
    """推送由 FloorPlanIR 确定性绘制的完整楼层预览。"""
    await _send_event(ws, {
        "type": "floor_plan_ready",
        "request_id": request_id,
        "session_id": session_id,
        "floor_plan": floor_plan,
        "svg": svg,
        "svgs": svgs,
        "validation": validation,
        "notice": notice,
        "continues_generation": False,
    })


def _payload_access_context(payload: dict) -> AccessContext:
    raw = payload.get("_server_access_context")
    if not isinstance(raw, dict):
        return AccessContext()
    try:
        return AccessContext(
            user_id=str(raw.get("user_id") or "anonymous"),
            tenant_id=raw.get("tenant_id") or None,
            department=raw.get("department") or None,
            clearance_level=max(0, int(raw.get("clearance_level") or 0)),
            scopes=tuple(raw.get("scopes") or ("public",)),
            authenticated=raw.get("authenticated") is True,
        )
    except (TypeError, ValueError):
        return AccessContext()


def _prepare_server_request(data: dict, access: AccessContext) -> dict:
    """覆盖所有前端自报身份字段，并在进入持久化任务前完成 PII 脱敏。"""

    prepared = dict(data)
    prepared["plan_mode"] = prepared.get("plan_mode") is True
    prepared["_server_access_context"] = access.public_dict()
    message = str(prepared.get("message") or "")
    if config.rag.security.pii_redaction_enabled:
        message, pii_categories = redact_pii(message)
    else:
        pii_categories = []
    prepared["message"] = message
    recent_messages = []
    raw_recent = prepared.get("recent_messages")
    if isinstance(raw_recent, list):
        for item in raw_recent[-4:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content") or "").strip()[:500]
            if config.rag.security.pii_redaction_enabled:
                content, _ = redact_pii(content)
            if content:
                recent_messages.append({"role": role, "content": content})
    prepared["recent_messages"] = recent_messages
    prepared["workflow_state"] = (
        "plan_requested"
        if prepared["plan_mode"]
        else "scene_ready"
        if isinstance(prepared.get("blueprint"), dict)
        else "empty_scene"
    )
    safety = (
        check_content_safety(message)
        if config.rag.security.content_safety_enabled
        else {"allowed": True, "category": None, "matched_rule": None, "message": ""}
    )
    safety["pii_categories"] = pii_categories
    prepared["_server_safety"] = safety
    return prepared


async def _emit_safety_refusal_if_needed(sink, payload: dict) -> bool:
    safety = payload.get("_server_safety")
    if not isinstance(safety, dict):
        message = str(payload.get("message") or "")
        safety = check_content_safety(message)
        safety["pii_categories"] = []
    record_rag_safety(safety)
    if safety.get("allowed") is not False:
        return False
    refusal = str(safety.get("message") or "该请求无法继续处理。")
    record_final_answer(refusal)
    await _send_event(sink, {
        "type": "agent_reply",
        "request_id": payload.get("request_id"),
        "session_id": payload.get("session_id"),
        "content": refusal,
        "safety_category": safety.get("category"),
        "cited_chunk_ids": [],
    })
    return True


async def _run_persistent_langgraph(sink, payload: dict, resume: bool) -> None:
    """持久化任务 runner：事件写入 durable sink，不绑定某条物理连接。"""
    access = _payload_access_context(payload)
    with rag_trace_scope(
        str(payload.get("request_id") or "unknown"),
        session_id=str(payload.get("session_id") or payload.get("request_id") or "unknown"),
        access_context=access,
    ):
        if await _emit_safety_refusal_if_needed(sink, payload):
            return
        await _handle_with_langgraph(sink, payload, resume=resume)


async def startup_generation_jobs() -> None:
    """初始化 checkpointer，并恢复上次服务退出时未完成的生成任务。"""
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
    耗时的 LLM 请求不会阻塞心跳。快速与精密模式都由持久化图托管；区别只在
    推理深度和复杂度目标。生成类请求都会先进入独立平面规划和人工确认。
    """
    await ws.accept()
    logger.info("Agent WebSocket 客户端已连接")
    # 测试替身与轻量客户端可能不提供 headers；缺失时按 public 上下文处理。
    access_context = access_context_from_headers(
        getattr(ws, "headers", None) or {},
        config.rag.security.trusted_header_secret,
    )

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
                # 进入后台任务或持久化队列前，由服务端覆盖身份并脱敏输入。
                data = _prepare_server_request(data, access_context)
                job, created = await generation_job_service.start_job(data, ws)
                if not created:
                    await generation_job_service.resume_or_replay(
                        ws,
                        request_id=job.request_id,
                        session_id=job.session_id,
                        after_seq=int(data.get("last_event_seq") or 0),
                    )

            elif msg_type == "resume_generation":
                await generation_job_service.resume_or_replay(
                    ws,
                    request_id=data.get("request_id"),
                    session_id=str(data.get("session_id") or ""),
                    after_seq=int(data.get("last_event_seq") or 0),
                )

            elif msg_type == "floor_plan_review":
                feedback = str(data.get("feedback") or "")
                if config.rag.security.pii_redaction_enabled:
                    feedback, _ = redact_pii(feedback)
                try:
                    resumed_job = await generation_job_service.submit_floor_plan_review(
                        ws,
                        request_id=str(data.get("request_id") or ""),
                        session_id=str(data.get("session_id") or ""),
                        action=str(data.get("action") or ""),
                        feedback=feedback,
                    )
                    await _send_event(ws, {
                        "type": "generation_resumed",
                        "request_id": resumed_job.request_id,
                        "session_id": resumed_job.session_id,
                        "status": resumed_job.status,
                        "last_event_seq": resumed_job.last_event_seq,
                    })
                except ValueError as exc:
                    await _send_event(ws, {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "session_id": data.get("session_id"),
                        "code": "floor_plan_review_rejected",
                        "error": str(exc),
                    })

            elif msg_type == "style_review":
                feedback = str(data.get("feedback") or "")
                if config.rag.security.pii_redaction_enabled:
                    feedback, _ = redact_pii(feedback)
                try:
                    resumed_job = await generation_job_service.submit_style_review(
                        ws,
                        request_id=str(data.get("request_id") or ""),
                        session_id=str(data.get("session_id") or ""),
                        action=str(data.get("action") or ""),
                        style_package_id=str(data.get("style_package_id") or ""),
                        feedback=feedback,
                    )
                    await _send_event(ws, {
                        "type": "generation_resumed",
                        "request_id": resumed_job.request_id,
                        "session_id": resumed_job.session_id,
                        "status": resumed_job.status,
                        "last_event_seq": resumed_job.last_event_seq,
                    })
                except ValueError as exc:
                    await _send_event(ws, {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "session_id": data.get("session_id"),
                        "code": "style_review_rejected",
                        "error": str(exc),
                    })

            elif msg_type == "execution_plan_review":
                feedback = str(data.get("feedback") or "")
                if config.rag.security.pii_redaction_enabled:
                    feedback, _ = redact_pii(feedback)
                try:
                    resumed_job = await generation_job_service.submit_execution_plan_review(
                        ws,
                        request_id=str(data.get("request_id") or ""),
                        session_id=str(data.get("session_id") or ""),
                        action=str(data.get("action") or ""),
                        feedback=feedback,
                    )
                    await _send_event(ws, {
                        "type": "generation_resumed",
                        "request_id": resumed_job.request_id,
                        "session_id": resumed_job.session_id,
                        "status": resumed_job.status,
                        "last_event_seq": resumed_job.last_event_seq,
                    })
                except ValueError as exc:
                    await _send_event(ws, {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "session_id": data.get("session_id"),
                        "code": "execution_plan_review_rejected",
                        "error": str(exc),
                    })

            elif msg_type == "execution_feedback":
                feedback = str(data.get("feedback") or "")
                if config.rag.security.pii_redaction_enabled:
                    feedback, _ = redact_pii(feedback)
                try:
                    await generation_job_service.queue_execution_feedback(
                        request_id=str(data.get("request_id") or ""),
                        session_id=str(data.get("session_id") or ""),
                        feedback=feedback,
                    )
                except ValueError as exc:
                    await _send_event(ws, {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "session_id": data.get("session_id"),
                        "code": "execution_feedback_rejected",
                        "error": str(exc),
                    })
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
        await heartbeat.stop()
        await presence_service.disconnect(ws)


async def _handle_user_message(ws: WebSocket, data: dict):
    """兼容旧调用和单元测试的直接处理入口。

    实际 WebSocket 接收循环已把快速与精密请求统一交给持久化 LangGraph；这里
    暂时保留旧的快速 LangChain 分支，避免影响仍显式调用该内部函数的集成代码。
    """
    if "_server_access_context" not in data:
        data = _prepare_server_request(data, AccessContext())
    precision_mode = data.get("precision_mode") is True
    with rag_trace_scope(
        str(data.get("request_id") or "unknown"),
        session_id=str(data.get("session_id") or data.get("request_id") or "unknown"),
        access_context=_payload_access_context(data),
    ):
        if await _emit_safety_refusal_if_needed(ws, data):
            return
        if precision_mode:
            await _handle_with_langgraph(ws, data)
        else:
            await _handle_with_langchain(ws, data)


# ── 节点名 → 展示标签 ──
_NODE_LABELS = {
    "classifier": "意图分类",
    "chat": "知识问答",
    "patch": "场景修改",
    "planning_research": "计划研究",
    "planner": "执行计划",
    "plan_validator": "计划校验",
    "plan_review": "计划审核",
    "plan_executor": "计划调度",
    "architecture": "总体建筑方案",
    "floor_plan_design": "平面设计",
    "floor_plan_review": "平面审核",
    "material_plan": "材质方案",
    "skeleton": "主体装配",
    "style_review": "风格确认",
    "decor_assembly": "装饰装配",
    "merge": "合并", "final_validate": "最终校验", "callback": "修正",
}
# gen/val 标签动态生成: _node_label("door_gen") → "门·生成"
def _node_label(name: str) -> str:
    if name in _NODE_LABELS:
        return _NODE_LABELS[name]
    from app.agent.component_registry import get_implemented_components

    for component_config in get_implemented_components():
        ct, cl = component_config.component_type, component_config.label
        if name == f"{ct}_gen":
            return f"{cl}·生成"
        if name == f"{ct}_val":
            return f"{cl}·校验"
    return name


async def _handle_with_langgraph(ws, data: dict, *, resume: bool = False):
    """持久化 LangGraph：逐节点推送 RAG/LLM/确定性进度诊断与性能汇总。"""
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
        await _emit_agent_step(
            ws, request_id, session_id,
            stage=stage, node=node, status=status, label=label, detail=detail,
        )

    async def send_debug(category: str, data_obj: dict):
        await _emit_debug_log(
            ws, request_id, session_id, category=category, data=data_obj,
        )

    async def send_thinking_delta(node_name: str, delta: str):
        """实时推送节点的思考内容给前端（带节点标识）"""
        explicit_progress = node_name.endswith(":progress")
        public_node_name = node_name.removesuffix(":progress")
        channel = (
            "progress"
            if explicit_progress
            or public_node_name in {"architecture", "merge", "final_validate"}
            or public_node_name.endswith("_val")
            else "reasoning"
        )
        await _emit_thinking_delta(
            ws, request_id, session_id, node=public_node_name, channel=channel, delta=delta,
        )

    async def send_thinking_status(status: str, content: str = ''):
        await _emit_thinking_status(
            ws, request_id, session_id, status=status, content=content,
        )

    # ── 初始状态 ──
    initial_state: GenerationState = {
        "request_id": request_id,
        "user_message": message,
        "building_type": _detect_building_type(message),
        "session_id": session_id,
        "current_blueprint": current_blueprint,
        "selection": selection,
        "recent_messages": data.get("recent_messages", []),
        "workflow_state": str(data.get("workflow_state") or "idle"),
        "thinking_mode": thinking_mode,
        "procedural_materials_enabled": data.get("procedural_materials_enabled") is True,
        "plan_mode": data.get("plan_mode") is True,
        "execution_plan_history": [],
        "plan_replan_count": 0,
        "max_plan_replans": 3,
        "max_retries": 3,
        "retry_count": 0,
        "floor_plan_auto_repair_count": 0,
        "floor_plan_auto_repairing": False,
        "component_fragments": {},
        "component_diagnostics": {},
        "style_revision": 0,
    }

    if thinking_mode:
        await send_thinking_status("thinking", "正在收集节点思考内容")

    # ── 流式执行（astream_events: 可获取节点 start/end 事件）──
    from app.agent.graph import generation_recursion_limit, get_graph
    from app.agent.component_registry import get_implemented_components
    from app.agent.runtime_context import (
        bind_execution_feedback_poller,
        bind_reasoning_callback,
        reset_execution_feedback_poller,
        reset_reasoning_callback,
    )

    await generation_job_service.initialize()
    graph = get_graph(
        enable_callback=True,
        checkpointer=generation_job_service.checkpointer,
    )
    component_configs = {
        config.component_type: config for config in get_implemented_components()
    }
    graph_config = {
        "configurable": {"thread_id": f"generation:{request_id}"},
        "recursion_limit": generation_recursion_limit(
            len(component_configs),
            initial_state["max_retries"],
            plan_mode=initial_state["plan_mode"],
        ),
    }
    all_diags: dict[str, dict] = {}
    final_state = None
    resolved_intent = None
    node_outputs: dict[str, dict] = {}
    total_tokens = {"input": 0, "output": 0}
    suggested_components = []  # 存储骨架节点建议的组件列表

    # 生成所有可能的节点名（gen + val + 固定节点）
    _COMP_TYPES = set(component_configs)

    _OUR_NODES = {
        "classifier", "chat", "patch", "planning_research", "planner",
        "plan_validator", "plan_review", "plan_executor", "architecture",
        "floor_plan_design", "floor_plan_review", "material_plan", "skeleton",
        "style_review", "decor_assembly", "merge", "final_validate", "callback",
    }

    for ct in _COMP_TYPES:
        _OUR_NODES.add(f"{ct}_gen")
        _OUR_NODES.add(f"{ct}_val")

    # architecture/校验节点会通过同一回调发送可公开的执行摘要。快速模式也应
    # 展示这些摘要；模型原始 reasoning 是否存在仍由 enable_thinking 控制。
    reasoning_token = bind_reasoning_callback(send_thinking_delta)
    feedback_token = bind_execution_feedback_poller(
        lambda: generation_job_service.drain_execution_feedback(str(request_id))
    )

    try:
        graph_input = initial_state
        if resume:
            from langgraph.types import Command

            snapshot = await graph.aget_state(graph_config)
            if snapshot.values:
                resolved_intent = snapshot.values.get("intent")
                suggested_components = snapshot.values.get(
                    "suggested_components", []
                )
                if snapshot.next:
                    review = data.get("_floor_plan_review")
                    style_review_decision = data.get("_style_review")
                    plan_review_decision = data.get("_execution_plan_review")
                    graph_input = (
                        Command(resume=plan_review_decision)
                        if "plan_review" in snapshot.next and isinstance(plan_review_decision, dict)
                        else Command(resume=review)
                        if "floor_plan_review" in snapshot.next and isinstance(review, dict)
                        else Command(resume=style_review_decision)
                        if "style_review" in snapshot.next and isinstance(style_review_decision, dict)
                        else None
                    )
                    logger.info(
                        f"[{request_id}] 从 checkpoint 恢复，待执行节点: "
                        f"{', '.join(snapshot.next)}"
                    )
                else:
                    # 图已经结束但进程可能在结果落盘/发事件前退出；直接从最终状态交付。
                    final_state = dict(snapshot.values)
                    output_key = {
                        "generate": "final_validate",
                        "chat": "chat",
                        "edit": "patch",
                    }.get(resolved_intent)
                    if output_key:
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
                    "planning_research": "只读分析需求、当前场景和建筑知识",
                    "planner": "生成可审核的结构化执行计划",
                    "plan_validator": "检查能力白名单、依赖和安全门禁",
                    "plan_review": "等待用户批准或修改执行计划",
                    "plan_executor": "在节点边界吸收用户意见并调度下一步",
                    "architecture": "生成建筑方案候选并执行确定性评分",
                    "floor_plan_design": "调用平面模型规划空间、流线、墙体和门窗",
                    "floor_plan_review": "等待用户确认平面方案",
                    "material_plan": "解析材质角色并匹配受控 PBR 资产",
                    "skeleton": "按确认平面确定性装配主体并执行 G1-G6",
                    "style_review": "等待用户选择并确认建筑风格",
                    "decor_assembly": "按风格包生成 Decor IR 并执行 G7",
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
                    intent = node_output.get("intent")
                    resolved_intent = intent
                    confidence = node_output.get("intent_confidence")
                    if not isinstance(confidence, (int, float)):
                        confidence = 0.0
                    intent_label = {
                        "generate": "生成建筑",
                        "edit": "修改场景",
                        "chat": "知识问答",
                    }.get(intent, intent)
                    await send_step(
                        "generating", node_name, "done", label,
                        f"意图：{intent_label} · "
                        f"置信度 {float(confidence):.0%} · "
                        f"{node_output.get('intent_reason', '')}",
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        "intent": intent,
                        "confidence": node_output.get("intent_confidence"),
                        "target": node_output.get("intent_target"),
                        "reason": node_output.get("intent_reason"),
                        "source": node_output.get("intent_source"),
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
                    fallback_note = " · 使用确定性总体方案" if diag.get("used_fallback") else ""
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

                elif node_name == "planning_research":
                    research_diag = node_output.get("plan_research_diag", {})
                    await send_step(
                        "planning", node_name, "done", label,
                        node_output.get("plan_research_summary", "已完成只读研究"),
                    )
                    if research_diag:
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            **research_diag,
                        })

                elif node_name == "planner":
                    plan = node_output.get("execution_plan", {})
                    await send_step(
                        "planning", node_name, "done", label,
                        f"计划 v{plan.get('version', 1)} · {len(plan.get('steps', []))} 步",
                    )

                elif node_name == "plan_validator":
                    plan = node_output.get("execution_plan", {})
                    issues = node_output.get("execution_plan_validation", [])
                    await send_step(
                        "planning", node_name, "error" if issues else "done", label,
                        f"{len(issues)} 个问题" if issues else "白名单、依赖和建筑门禁均通过",
                    )
                    await _send_event(ws, {
                        "type": "execution_plan_ready",
                        "request_id": request_id,
                        "session_id": session_id,
                        "plan": plan,
                    })

                elif node_name == "plan_review":
                    approved = node_output.get("execution_plan_review_status") == "approved"
                    await send_step(
                        "planning", node_name, "done", label,
                        "执行计划已批准" if approved else "已收到计划修改意见",
                    )

                elif node_name == "plan_executor":
                    plan = node_output.get("execution_plan", {})
                    next_node = str(node_output.get("plan_next_node") or "")
                    await send_step(
                        "planning", node_name,
                        "error" if node_output.get("error") else "done",
                        label,
                        node_output.get("error") or (
                            "执行计划已完成" if next_node == "__end__"
                            else f"下一步：{_node_label(next_node)}"
                        ),
                    )
                    if plan:
                        await _send_event(ws, {
                            "type": "execution_plan_ready",
                            "request_id": request_id,
                            "session_id": session_id,
                            "plan": plan,
                        })

                elif node_name == "floor_plan_design":
                    floor_plan = node_output.get("floor_plan", {})
                    floor_diag = node_output.get("floor_plan_design_diag", {})
                    summary = floor_diag.get("floor_plan", {})
                    await send_step(
                        "generating", node_name, "done", label,
                        f"{summary.get('level_count', '?')} 层 · "
                        f"{summary.get('space_count', '?')} 个空间 · "
                        f"{len(node_output.get('floor_plan_validation', []))} 项待处理",
                    )
                    floor_plan_svg = str(node_output.get("floor_plan_svg") or "")
                    if floor_plan_svg:
                        await _emit_floor_plan_ready(
                            ws,
                            request_id,
                            session_id,
                            floor_plan=floor_plan,
                            svg=floor_plan_svg,
                            svgs=node_output.get("floor_plan_svgs", {}),
                            validation=node_output.get("floor_plan_validation", []),
                            notice=str(node_output.get("floor_plan_notice") or ""),
                        )
                    await send_debug("node", {
                        "node": node_name,
                        "label": label,
                        "stage": "done",
                        **floor_diag,
                    })

                elif node_name == "floor_plan_review":
                    approved = node_output.get("floor_plan_review_status") == "approved"
                    automatic = node_output.get("floor_plan_auto_repairing") is True
                    await send_step(
                        "generating",
                        node_name,
                        "done",
                        label,
                        "用户已确认，继续生成三维" if approved
                        else "工程预审未通过，正在自动修改平面" if automatic
                        else "已收到修改意见，重新生成平面",
                    )

                elif node_name == "material_plan":
                    material_diag = node_output.get("material_diag", {})
                    await send_step(
                        "generating", node_name, "done", label,
                        f"PBR 资产 {material_diag.get('selected_asset_count', 0)} 个 · "
                        f"{'受控回退' if material_diag.get('used_fallback') else '审美方案已解析'}",
                    )
                    if material_diag:
                        all_diags[node_name] = material_diag
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            **material_diag,
                        })

                elif node_name == "skeleton":
                    if node_output.get("error"):
                        await send_step(
                            "generating", node_name, "error", label,
                            node_output["error"],
                        )
                    else:
                        ec = diag.get("element_count", "?")
                        cc = diag.get("component_count", "?")
                        await send_step(
                            "generating", node_name, "done", label,
                            f"{ec} 元素 + {cc} 组件 · G1-G6 全部通过 · 确定性装配",
                        )
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "llm_ms": 0,
                            "token_usage": diag.get("token_usage"),
                            "element_count": diag.get("element_count"),
                            "component_count": diag.get("component_count"),
                            "gate_reports": diag.get("gate_reports", []),
                            "total_ms": diag.get("total_ms"),
                        })
                elif node_name == "style_review":
                    approved = node_output.get("style_review_status") == "approved"
                    await send_step(
                        "generating", node_name, "done", label,
                        f"已确认风格：{node_output.get('style_package_id')}" if approved else "已收到风格修改意见",
                    )
                elif node_name == "decor_assembly":
                    decor_diag = node_output.get("decor_diag", {})
                    await send_step(
                        "generating", node_name,
                        "error" if node_output.get("error") else "done",
                        label,
                        node_output.get("error") or f"{decor_diag.get('operation_count', 0)} 项参数化操作 · G7 通过",
                    )
                    if decor_diag:
                        all_diags[node_name] = decor_diag
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            **decor_diag,
                        })
                elif node_name == "merge":
                    merged = node_output.get("merged_blueprint", {})
                    geom = merged.get("geometry", {})
                    e_count = len(geom.get("elements", []))
                    c_count = len(geom.get("components", []))
                    merge_diag = node_output.get("merge_diag", {})
                    iters = merge_diag.get("iterations", [])
                    merge_errors = merge_diag.get("final_errors", 0)
                    merge_error_text = node_output.get("error")
                    iter_summary = ""
                    if iters:
                        last_iter = iters[-1]
                        iter_summary = f" | {len(iters)}轮校验 {last_iter['passed']}✓ {last_iter['errors']}✗"
                    await send_step(
                        "generating", node_name,
                        "error" if merge_error_text or merge_errors else "done",
                        label,
                        merge_error_text or f"{e_count} 元素 + {c_count} 组件{iter_summary}",
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
                            f"已发起第 {retry_number} 轮修复（每目标最多 "
                            f"{initial_state.get('max_retries', 3)} 次）",
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
        error_text = _friendly_graph_error(e)
        if thinking_mode:
            await send_thinking_status("error", error_text)
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error": error_text,
        })
        await send_step("finished", "finished", "error", "处理失败", error_text)
        return
    finally:
        reset_execution_feedback_poller(feedback_token)
        reset_reasoning_callback(reasoning_token)

    # interrupt 是正常的人工审核暂停点。此处必须先返回等待状态，不能继续保存或加载三维。
    snapshot = await graph.aget_state(graph_config)
    if "plan_review" in snapshot.next:
        values = snapshot.values or {}
        plan = values.get("execution_plan") or {}
        await send_step(
            "reviewing",
            "plan_review",
            "done",
            "计划审核",
            "批准后才会执行建筑生成；也可提交修改意见",
        )
        await generation_job_service.mark_waiting_for_review(
            request_id,
            "execution_plan",
        )
        await _send_event(ws, {
            "type": "execution_plan_review_required",
            "request_id": request_id,
            "session_id": session_id,
            "plan": plan,
            "version": int(plan.get("version") or 1),
        })
        raise GenerationPaused()

    if "floor_plan_review" in snapshot.next:
        values = snapshot.values or {}
        floor_plan = values.get("floor_plan") or {}
        revision = int(values.get("floor_plan_revision") or 0)
        can_confirm = is_confirmable_spatial_plan(
            floor_plan,
            values.get("floor_plan_validation"),
        )
        await send_step(
            "reviewing",
            "floor_plan_review",
            "done",
            "平面审核",
            "等待确认；也可以在输入框继续提交修改意见",
        )
        await generation_job_service.mark_waiting_for_review(request_id, "floor_plan")
        await _send_event(ws, {
            "type": "floor_plan_review_required",
            "request_id": request_id,
            "session_id": session_id,
            "revision": revision,
            "can_confirm": can_confirm,
            "fallback_reason": floor_plan.get("fallback_reason", ""),
            "notice": values.get("floor_plan_notice", ""),
        })
        raise GenerationPaused()

    if "style_review" in snapshot.next:
        from app.agent.plan2build.style_registry import style_registry

        values = snapshot.values or {}
        selected = str(values.get("style_package_id") or "") or style_registry.infer(
            str(values.get("user_message") or "")
        )
        packages = style_registry.recommend(
            str(values.get("user_message") or ""),
            values.get("architecture_plan"),
            include_id=selected,
        )
        await send_step(
            "reviewing",
            "style_review",
            "done",
            "风格确认",
            "主体 G1-G6 已通过；选择风格后才会装配装饰并交付三维",
        )
        await generation_job_service.mark_waiting_for_review(request_id, "style")
        await _send_event(ws, {
            "type": "style_review_required",
            "request_id": request_id,
            "session_id": session_id,
            "revision": int(values.get("style_revision") or 0),
            "selected_style_id": selected,
            "options": style_registry.public_options(packages),
        })
        raise GenerationPaused()

    if not snapshot.next and snapshot.values:
        # plan_executor 是最后一个调度节点时，业务产物在完整 checkpoint 中。
        final_state = dict(snapshot.values)

    if final_state is None:
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error": "未返回结果",
        })
        await send_step("finished", "finished", "error", "处理失败", "未返回结果")
        return

    resolved_intent = final_state.get("intent") or resolved_intent
    if resolved_intent not in {"generate", "edit", "chat"}:
        error_text = "意图分类未返回合法结果，已停止处理，未执行建筑生成或场景修改。"
        await _send_event(ws, {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "code": "invalid_intent",
            "error": error_text,
        })
        await send_step("finished", "finished", "error", "意图识别失败", error_text)
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
            "cited_chunk_ids": chat_diag.get("cited_chunk_ids", []),
            "evidence_status": chat_diag.get("evidence_status", "none"),
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
        error_event = {
            "type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error": upstream_failure,
        }
        terminal_model_error = final_state.get("terminal_model_error")
        if isinstance(terminal_model_error, dict):
            error_event["code"] = "model_service_error"
            error_event["error_category"] = terminal_model_error.get("category")
            error_event["retryable"] = terminal_model_error.get("retryable", False)
        await _send_event(ws, error_event)
        await send_step(
            "finished", "finished", "error", "生成失败", upstream_failure,
        )
        return
    if data.get("procedural_materials_enabled") is not True:
        merged_blueprint = without_procedural_materials(merged_blueprint)

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
        "plan_mode": final_state.get("plan_mode") is True,
        "plan_version": (final_state.get("execution_plan") or {}).get("version"),
        "plan_replan_count": int(final_state.get("plan_replan_count") or 0),
        "status": final_status,
    }
    await send_debug("session_metrics", session_metrics)

    try:
        delivery = commit_generation_result(
            session_id,
            request_id,
            merged_blueprint,
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


def _friendly_graph_error(exc: Exception) -> str:
    """隐藏框架内部提示，向用户说明递归保护真正代表什么。"""
    message = str(exc)
    if "recursion limit" in message.lower() or "graph_recursion_limit" in message.lower():
        return (
            "生成流程超过安全步数，系统已停止，避免继续循环消耗模型额度。"
            "请查看最先失败的节点；若是额度或鉴权错误，请先修复模型服务配置后重新生成。"
        )
    return message

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
        await _emit_agent_step(
            ws, request_id, session_id,
            stage=stage, node=step_id, status=status,
            label=label or stage_labels.get(stage, stage), detail=detail,
        )

    reasoning_received = False

    async def send_reasoning_delta(delta: str):
        """实时转发模型接口实际返回的 reasoning_content。"""
        nonlocal reasoning_received
        reasoning_received = True
        await _emit_thinking_delta(
            ws, request_id, session_id, node=None, channel="reasoning", delta=delta,
        )

    async def send_thinking_status(status: str, content: str = ""):
        await _emit_thinking_status(
            ws, request_id, session_id, status=status, content=content,
        )

    # Phase 1: 与精密模式复用同一个结构化意图分类器。
    decision = await classify_intent_decision(
        message,
        bool(current_blueprint),
        recent_messages=data.get("recent_messages"),
        workflow_state=str(data.get("workflow_state") or "idle"),
        selection=selection,
        plan_mode=data.get("plan_mode") is True,
    )
    await send_step(
        "analyzing",
        f"意图：{INTENT_LABELS[decision.intent]} · "
        f"置信度 {decision.confidence:.0%} · {decision.reason}",
        node="classifier",
        status="done",
        label="意图分类",
    )
    await send_step("generating", "正在调用 AI 处理，请耐心等待...")
    expected_output = {
        "generate": "blueprint",
        "edit": "patch",
        "chat": "text",
    }[decision.intent]

    # Phase 2: LLM 查询（输出协议由共享意图决策强制限定）
    if thinking_mode:
        await send_thinking_status("thinking")
    try:
        result = await agent_service.query_structured(
            message,
            current_blueprint,
            selection=selection,
            thinking_mode=thinking_mode,
            on_reasoning_delta=send_reasoning_delta if thinking_mode else None,
            expected_output=expected_output,
            resolved_intent=decision.intent,
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

    # Phase 3: 处理结果（按 AI 输出的格式分发）
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
        delivery_blueprint = (
            result.blueprint
            if data.get("procedural_materials_enabled") is True
            else without_procedural_materials(result.blueprint)
        )
        try:
            delivery = commit_generation_result(
                session_id,
                request_id,
                delivery_blueprint,
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
            "cited_chunk_ids": result.cited_chunk_ids,
            "evidence_status": result.evidence_status,
        })

    logger.info(f"[{request_id}] 处理完成")
