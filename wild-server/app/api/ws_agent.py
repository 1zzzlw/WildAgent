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
  plan_ready:          { "type": "plan_ready", "request_id": "...", "plan": {...} }
  plan_item_updated:   { "type": "plan_item_updated", "request_id": "...", "item": {...} }
  design_review_required: { "type": "design_review_required", "request_id": "...", "document": {...}, "preview_url": "..." }
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
- 持久化生成任务运行期间由 GenerationJobService 动态探针豁免超时；旧直连处理仍使用 is_processing
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
from app.agent.routing import (
    INTENT_LABELS,
    classify_intent_decision,
    detect_target_kind,
    has_scene_content,
)
from app.agent.generation.architecture import detect_architecture_profile
from app.contracts.agent_events import AGENT_PROTOCOL_VERSION, versioned_event
from app.agent.generation.material.recipes import without_procedural_materials
from app.rag.security import (
    AccessContext,
    access_context_from_headers,
    check_content_safety,
    redact_pii,
)
from app.rag.trace import (
    rag_trace_scope,
    record_final_answer,
    record_node_call,
    record_rag_error,
    record_rag_safety,
)
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


def _utc_now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串，用于节点观测记录。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _plan_delivery_summary(plan_payload: object) -> dict:
    """交付清单：四个终态的计数 + 未完成条目（含能力缺失说明）。

    没有这条记录，交付就只能回答"成没成"，回答不了"哪几条没做成、为什么"——而后者
    正是 plan 驱动链存在的理由之一（《动态节点设计规划》§6.4）。
    """

    if not isinstance(plan_payload, dict) or not plan_payload:
        return {}
    try:
        from app.agent.plan.contracts import PlanDocument
        from app.agent.plan.store import terminal_stats

        plan = PlanDocument.model_validate(plan_payload)
    except Exception as exc:  # 计划不合法时不影响交付，只是少一份清单
        logger.warning(f"交付清单生成失败: {exc}")
        return {}

    stats = terminal_stats(plan)
    items = [
        {
            "item_id": item.id,
            "label": item.label,
            "op": item.op,
            "kind": item.kind,
            "status": item.status,
            "notice": str(item.params.get("notice") or ""),
            "evidence": item.run.evidence[:300],
        }
        for item in plan.items
        if item.status != "done"
    ]
    return {
        **stats,
        "give_up": plan.give_up,
        "llm_calls": plan.llm_calls,
        "revision": plan.revision,
        "items": items,
    }


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
    # 覆盖访问身份
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
        "scene_ready" if isinstance(prepared.get("blueprint"), dict) else "empty_scene"
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
    heartbeat = WebSocketHeartbeat(
        timeout=90,
        check_interval=10,
        processing_probe=lambda: generation_job_service.has_running_job_for(ws),
    )
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

            elif msg_type == "design_review":
                feedback = str(data.get("feedback") or "")
                if config.rag.security.pii_redaction_enabled:
                    feedback, _ = redact_pii(feedback)
                try:
                    resumed_job = await generation_job_service.submit_design_review(
                        ws,
                        request_id=str(data.get("request_id") or ""),
                        session_id=str(data.get("session_id") or ""),
                        action=str(data.get("action") or ""),
                        feedback=feedback,
                        base_revision=data.get("base_revision"),
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
                        "code": "design_review_rejected",
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
    with rag_trace_scope(
        str(data.get("request_id") or "unknown"),
        session_id=str(data.get("session_id") or data.get("request_id") or "unknown"),
        access_context=_payload_access_context(data),
    ):
        if await _emit_safety_refusal_if_needed(ws, data):
            return
        await _handle_with_langgraph(ws, data)


# ── 思考通道 ──
#
# 🔴 **通道由发送方逐条表态，不按节点名猜**：
#
# - 代码写的中文进度句 → 用 `"<node>:progress"`，前端显示为「执行说明」；
# - 模型自己吐出的思考 token → 用裸节点名，前端显示为「模型过程」。
#
# 这条规则是踩坑换来的：原先按节点名白名单把 `architecture` **一律**判成 progress，
# 而同一个节点两种都发 —— 于是它转发的**整段原始 CoT**（含大量自我推翻）被当成
# 「执行说明」倒给用户，看起来像"循环思考 / 出问题了"。
# 按节点名永远分不开同一个节点的两种输出，只有逐条表态才分得开。
_PROGRESS_SUFFIX = ":progress"


def _thinking_channel(node_name: str) -> str:
    """`"<node>:progress"` → `"progress"`（执行说明）；其余 → `"reasoning"`（模型过程）。"""

    return "progress" if str(node_name).endswith(_PROGRESS_SUFFIX) else "reasoning"


def _public_node_name(node_name: str) -> str:
    """去掉通道后缀，还原它挂在哪一个步骤上。"""

    return str(node_name).removesuffix(_PROGRESS_SUFFIX)


# ── 节点名 → 展示标签 ──
_NODE_LABELS = {
    "classifier": "意图分类",
    "chat": "知识问答",
    "patch": "场景修改",
    "architecture": "总体建筑方案",
    "object_design": "物件方案",
    "material_plan": "材质方案",
    "design_convergence": "设计收敛",
    "design_review": "建筑设计审核",
    "skeleton": "主体装配",
    "compile": "确定性编译",
    "plan": "执行计划",
    "execute": "执行计划条目",
    "replanner": "计划对账",
    "final_validate": "最终校验", "callback": "修正",
}


def _node_label(name: str) -> str:
    return _NODE_LABELS.get(name, name)


def _design_schedule_note(design_blocks: dict | None) -> str:
    """把设计期的 plan 调度压成一行：几批、最宽并发几块、落定几块。

    这是"plan 到底参与图纸了没有"唯一可观测的口径。只看产物看不出来 ——
    串行起草也能写出同一张图，只有**批次与并发数**能区分。块表的
    ``parallel_group="shell"`` 曾经一直是空转的声明（旧实现是纯串行 for 循环），
    所以这一行也兼作那条回归的现场证据。
    """

    if not isinstance(design_blocks, dict):
        return ""
    plan = design_blocks.get("plan")
    batches = design_blocks.get("batches")
    if not isinstance(plan, dict) or not isinstance(batches, list) or not batches:
        return ""
    items = [item for item in (plan.get("items") or []) if isinstance(item, dict)]
    settled = len([item for item in items if item.get("status") == "done"])
    widest = max(
        (
            len(batch.get("items") or [])
            for batch in batches
            if isinstance(batch, dict)
        ),
        default=0,
    )
    return (
        f" · 设计期 {len(batches)} 批（最宽 {widest} 并发）"
        f" · 落定 {settled}/{len(items)} 块"
    )


#: 会向 ws 推送 step 事件的节点全集 = 图节点全集（见 ``tests/agent/test_plan_graph.py``
#: 的 ``_EXPECTED_NODES``）+ 可选的 callback。图上加节点而这里不认，事件会在
#: astream 过滤处被静默吞掉——前端管线就会"跳节点"（compile/design_convergence
#: 上线时踩过：只改了生成链，忘了这张消费侧的表）。
_OUR_NODES = {
    "classifier", "chat", "patch", "architecture", "object_design",
    "material_plan", "design_convergence", "design_review",
    "skeleton", "compile",
    # plan 驱动链的循环三节点：条目级进度在它们的输出里，不在节点名里
    "plan", "execute", "replanner",
    "final_validate", "callback",
}

#: 节点开始（running）事件的固定文案；缺了哪个节点，它的"开始"事件就不发
#: （见事件循环里的 ``if detail:`` 门）。与 _OUR_NODES 必须同批维护。
_NODE_START_DETAILS = {
    "classifier": "分析用户意图",
    "chat": "RAG 检索知识库并生成回答",
    "patch": "分析当前场景并生成修改提案",
    "architecture": "生成唯一结构化建筑方案并校验设计契约",
    "object_design": "生成物件清单并校验设计契约",
    "material_plan": "解析材质角色并匹配受控 PBR 资产",
    "design_convergence": "试算图纸可编译性并收敛修订",
    "design_review": "等待用户审阅建筑设计文档与 SVG 方案图",
    "skeleton": "把批准方案展开为主体骨架和组件槽位（物件链）",
    "compile": "把批准的图纸确定性编译成蓝图",
    "plan": "由大模型制定批次与并发策略，再按方案、槽位和骨架展开合法条目",
    "execute": "执行当前串行条目或安全并发组",
    "replanner": "对账本轮结果并决定下一轮",
    "final_validate": "执行最终校验流水线",
    "callback": "修正失败组件",
}


async def _handle_with_langgraph(ws, data: dict, *, resume: bool = False):
    """持久化 LangGraph：逐节点推送 RAG/LLM/确定性进度诊断与性能汇总。"""
    from app.agent.state import GenerationState

    request_id = data.get("request_id", "")
    message = data.get("message", "")
    current_blueprint = data.get("blueprint")
    selection = data.get("selection", [])
    session_id = data.get("session_id", request_id)
    # 精密模式下强制开启思考（前端已做联动，此处兜底防止 localStorage 状态不一致）
    thinking_mode = data.get("thinking_mode") is True

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
        """实时推送节点的思考内容给前端（带节点标识）。通道判据见 :func:`_thinking_channel`。"""
        await _emit_thinking_delta(
            ws,
            request_id,
            session_id,
            node=_public_node_name(node_name),
            channel=_thinking_channel(node_name),
            delta=delta,
        )

    async def send_thinking_status(status: str, content: str = ''):
        await _emit_thinking_status(
            ws, request_id, session_id, status=status, content=content,
        )

    # ── 初始状态 ──
    #
    # `building_type` 只是入口的**预标签**（真正的 profile 由建筑方案节点带上下文重算），
    # 但它会写进会话元数据。所以物件需求不能借用建筑的兜底值：`detect_architecture_profile`
    # 在认不出建筑类型时返回 `residential_lowrise`，直接套用会把"生成一个桌子"标成低层住宅。
    # 这里用与意图路由同一套确定性关键词先判目标类型，只有建筑需求才预打建筑标签。
    preliminary_target = detect_target_kind(message, "generate")
    initial_state: GenerationState = {
        "request_id": request_id,
        "user_message": message,
        "building_type": (
            detect_architecture_profile(message)["id"]
            if preliminary_target == "architecture"
            else "asset"
        ),
        "session_id": session_id,
        "current_blueprint": current_blueprint,
        "selection": selection,
        "recent_messages": data.get("recent_messages", []),
        "workflow_state": str(data.get("workflow_state") or "idle"),
        "thinking_mode": thinking_mode,
        "procedural_materials_enabled": data.get("procedural_materials_enabled") is True,
        "max_retries": 3,
        "retry_count": 0,
        "component_fragments": {},
        "component_diagnostics": {},
        "style_revision": 0,
    }

    if thinking_mode:
        await send_thinking_status("thinking", "正在收集节点思考内容")

    # ── 流式执行（astream_events: 可获取节点 start/end 事件）──
    from app.agent.graph import get_graph, plan_recursion_limit
    from app.agent.generation.component.registry import get_implemented_components
    from app.agent.runtime import (
        bind_reasoning_callback,
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
    # 条目数在 plan 节点跑完前未知，用「构件类型数 × 3」估上界。每组是 generate + 批次 merge
    # 两条，加收尾 merge + validate 两条，所以 2×构件数 + 2 ≤ 3×构件数（构件类型数 ≥ 2）。
    # 上限只是安全余量，真正的停止条件是 replanner 的五重判定（《动态节点设计规划》§5.4）。
    recursion_limit = plan_recursion_limit(
        len(component_configs) * 3,
        initial_state["max_retries"],
    )
    graph_config = {
        "configurable": {"thread_id": f"generation:{request_id}"},
        "recursion_limit": recursion_limit,
    }
    all_diags: dict[str, dict] = {}
    final_state = None
    resolved_intent = None
    node_outputs: dict[str, dict] = {}
    total_tokens = {"input": 0, "output": 0}
    node_starts: dict[str, float] = {}  # 节点名 → perf_counter 起始点
    node_started_isos: dict[str, str] = {}  # 节点名 → UTC 起始时间
    suggested_components = []  # 存储骨架节点建议的组件列表

    # architecture/校验节点会通过同一回调发送可公开的执行摘要。快速模式也应
    # 展示这些摘要；模型原始 reasoning 是否存在仍由 enable_thinking 控制。
    reasoning_token = bind_reasoning_callback(send_thinking_delta)

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
                    graph_input = (
                        Command(resume=data.get("_design_review"))
                        if "design_review" in snapshot.next
                        and isinstance(data.get("_design_review"), dict)
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
            # ── 节点开始 ──
            if kind == "on_chain_start":
                node_starts[node_name] = time.perf_counter()
                node_started_isos[node_name] = _utc_now_iso()
                detail = _NODE_START_DETAILS.get(node_name)
                if detail:
                    await send_step("generating", node_name, "running", label, detail)

            # ── 节点结束 ──
            elif kind == "on_chain_end":
                node_output = event.get("data", {}).get("output", {})
                if not isinstance(node_output, dict):
                    node_output = {}
                node_outputs[node_name] = node_output

                # ── 请求级节点观测：墙钟耗时 + 子耗时分解 ──
                # 每个 request 落一条节点记录到 RAGTrace.nodes，供耗时/重试归因。
                node_started = node_starts.pop(node_name, None)
                node_started_iso = node_started_isos.pop(node_name, None)
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
                        logger.warning(f"[{request_id}] 节点观测记录失败 ({node_name}): {exc}")

                # skeleton：提取组件建议
                if node_name == "skeleton":
                    suggested_components = node_output.get("suggested_components", [])
                    design_brief = node_output.get("design_brief", {})
                    logger.info(f"[{request_id}] 骨架建议组件: {suggested_components}")
                    if design_brief:
                        quota = design_brief.get("component_quota", {})
                        logger.info(f"[{request_id}] 设计清单配额: {quota}")

                # 收集诊断：每个节点把自己那层的诊断挂在 ``{node}_diag`` 下
                diag = node_output.get(f"{node_name}_diag", {})
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
                    intent_label = {
                        "generate": "生成建筑",
                        "edit": "修改场景",
                        "chat": "知识问答",
                    }.get(intent, intent)
                    classifier_error = node_output.get("terminal_model_error")
                    await send_step(
                        "generating",
                        node_name,
                        "error" if classifier_error else "done",
                        label,
                        (
                            str(classifier_error.get("user_message") or "意图分类模型不可用")
                            if isinstance(classifier_error, dict)
                            else f"意图：{intent_label} · "
                            f"{node_output.get('intent_reason', '')}"
                        ),
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        "intent": intent,
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
                    # 设计期也跑在 plan 的调度语义上（`design_plan`）。把批次与并发如实
                    # 报出来：图纸阶段究竟发生了几批、同批几块，是"plan 到底参与了没有"
                    # 唯一可观测的证据 —— 只看结果看不出来，串行也能写出同样的图。
                    schedule_note = _design_schedule_note(diag.get("design_blocks"))
                    await send_step(
                        "generating", node_name, "done", label,
                        f"候选 {selected}/{candidate_count} · "
                        f"{massing.get('width', '?')}×{massing.get('depth', '?')}m · "
                        f"{massing.get('floors', '?')}层 · {plan.get('roof', {}).get('type', '?')}屋顶"
                        f"{fallback_note}{schedule_note}",
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
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
                    await send_step(
                        "generating", node_name, "done", label,
                        f"{len(objects)} 类物件 · 共 {piece_count} 件"
                        + (" · 使用确定性兜底" if diag.get("used_fallback") else ""),
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        **diag,
                        "concept": plan.get("concept") if isinstance(plan, dict) else None,
                        "objects": objects,
                    })

                elif node_name == "design_review":
                    approved = node_output.get("design_review_status") == "approved"
                    await send_step(
                        "reviewing", node_name, "done", label,
                        "建筑设计已批准" if approved else "已收到建筑设计修改意见",
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

                elif node_name == "design_convergence":
                    # 收敛环把图纸跑到编得出来再交人工审核；诊断键是 `design_convergence`
                    # （**不是** 节点名 + `_diag` 的通用约定），所以这里显式取。
                    convergence = node_output.get("design_convergence")
                    convergence = convergence if isinstance(convergence, dict) else {}
                    unfinished = convergence.get("unresolved") or []
                    note = ""
                    if convergence.get("reverted"):
                        note = " · 收敛后图纸不合法，已回退原图纸"
                    elif convergence.get("converged") is False:
                        note = f" · 仍有 {len(unfinished)} 条未解缺陷（不阻断）"
                    await send_step(
                        "generating", node_name, "done", label,
                        f"缺陷 {convergence.get('initial_defects', 0)}→"
                        f"{convergence.get('final_defects', 0)} · "
                        f"修订 {convergence.get('revisions', 0)} 轮 · "
                        f"{convergence.get('stop_reason') or '?'}{note}",
                    )
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        **convergence,
                    })

                elif node_name == "skeleton":
                    if node_output.get("error"):
                        await send_step(
                            "generating", node_name, "error", label,
                            node_output["error"],
                        )
                    else:
                        ec = diag.get("element_count", "?")
                        suggested = node_output.get("suggested_components") or []
                        await send_step(
                            "generating", node_name, "done", label,
                            f"已生成 {ec} 个主体元素 · 建议 {len(suggested)} 类后续组件",
                        )
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "llm_ms": diag.get("llm_ms"),
                            "token_usage": diag.get("token_usage"),
                            "element_count": diag.get("element_count"),
                            "suggested_components": suggested,
                            "deterministic_fallback": diag.get("deterministic_fallback", False),
                            "total_ms": diag.get("total_ms"),
                        })

                elif node_name == "compile":
                    # 编译**没有失败出口**（红线：图纸有问题只记进 compile_report，不阻断），
                    # 所以状态恒为 done；阻断级缺陷由 final_validate 那一步报 error。
                    report = node_output.get("compile_report")
                    report = report if isinstance(report, dict) else {}
                    uncompiled = [str(item) for item in (report.get("uncompiled") or [])]
                    unsupported = [str(item) for item in (report.get("unsupported") or [])]
                    detail = (
                        f"{report.get('elements', '?')} 元素 + {report.get('components', '?')} 构件 · "
                        f"缺陷 {report.get('defects', 0)} · 默认值 {report.get('defaulted', 0)}"
                    )
                    if uncompiled:
                        detail += f" · 待模型补 {len(uncompiled)} 类（{'、'.join(uncompiled)}）"
                    if unsupported:
                        detail += f" · 能力缺失 {len(unsupported)} 类"
                    if report.get("ok") is False:
                        detail += " · ⚠ 有阻断级缺陷"
                    await send_step("generating", node_name, "done", label, detail)
                    await send_debug("node", {
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

                elif node_name == "execute":
                    # 条目级进度：串行轮是一条；安全并发轮会一次返回同组的多条结果。
                    item_id = node_output.get("current_item_id")
                    execute_diag = node_output.get("execute_diag") or {}
                    item_ids = execute_diag.get("item_ids") or ([item_id] if item_id else [])
                    tool_calls = int(execute_diag.get("tool_calls") or 0)
                    if len(item_ids) > 1:
                        detail = (
                            f"并发 {len(item_ids)} 条：{'、'.join(item_ids)}"
                            f" · 工具调用 {tool_calls} 次"
                        )
                    else:
                        detail = f"{item_id or '无待办条目'} · 工具调用 {tool_calls} 次"
                    await send_step(
                        "generating", node_name, "done", label,
                        detail,
                    )
                    await send_debug("node", {
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
                    await send_step("generating", node_name, "done", label, detail)
                    await send_debug("node", {
                        "node": node_name, "label": label, "stage": "done",
                        **diag,
                    })

                elif node_name == "plan":
                    total = len(node_output.get("plan_events") or [])
                    budget = (node_output.get("plan") or {}).get("budget", {})
                    await send_step(
                        "generating", node_name, "done", label,
                        f"展开 {total} 条条目 · 档位预算 {budget.get('iterations', '?')} 轮",
                    )

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

                # plan 是数据：**每个产出 plan 的节点都推一次全量 plan**（plan / execute /
                # replanner 都返回 plan），前端整份替换。之所以不只在 plan 节点推一次：
                # replanner 追加的条目不会进 plan_events（增量只记状态变化），只推首次会让
                # 追加项永远到不了前端。plan_item_updated 是状态变化的增量提示，不是唯一通道。
                plan_payload = node_output.get("plan")
                if isinstance(plan_payload, dict) and plan_payload.get("items") is not None:
                    await _send_event(ws, {
                        "type": "plan_ready",
                        "request_id": request_id,
                        "session_id": session_id,
                        "plan": plan_payload,
                    })
                for item_event in node_output.get("plan_events") or []:
                    await _send_event(ws, {
                        "type": "plan_item_updated",
                        "request_id": request_id,
                        "session_id": session_id,
                        "item": item_event,
                    })
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
        reset_reasoning_callback(reasoning_token)

    # interrupt 是正常的人工审核暂停点。此处必须先返回等待状态，不能继续保存或加载三维。
    snapshot = await graph.aget_state(graph_config)
    if "design_review" in snapshot.next:
        values = snapshot.values or {}
        document = values.get("design_document") or {}
        resolved = values.get("resolved_design") or {}
        await send_step(
            "reviewing",
            "design_review",
            "done",
            "建筑设计审核",
            "请审阅 SVG、体量和立面；批准后才生成几何与组件",
        )
        await generation_job_service.mark_waiting_for_review(
            request_id,
            "design_document",
        )
        await _send_event(ws, {
            "type": "design_review_required",
            "request_id": request_id,
            "session_id": session_id,
            "document": document,
            "resolved": resolved,
            "preview_url": f"/api/designs/{session_id}/preview.svg?revision={document.get('revision', 1)}",
        })
        raise GenerationPaused()

    if not snapshot.next and snapshot.values:
        # 完成时以完整 checkpoint 为准，节点局部输出不一定包含所有业务产物。
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
        if thinking_mode:
            await send_thinking_status("error", upstream_failure)
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
        "plan_items": len((final_state.get("plan") or {}).get("items") or []),
        "plan_iterations": int((final_state.get("plan") or {}).get("iterations") or 0),
        "status": final_status,
    }
    # 交付清单（《动态节点设计规划》§6.4）：交付必须能回答"哪几条没做成、为什么"。
    plan_delivery = _plan_delivery_summary(final_state.get("plan"))
    if plan_delivery:
        session_metrics["plan_delivery"] = plan_delivery
        shortfall = [
            entry for entry in plan_delivery.get("items", []) if entry["status"] != "done"
        ]
        if shortfall:
            logger.warning(
                f"[{request_id}] 交付清单包含 {len(shortfall)} 条未完成项："
                + "; ".join(f"{entry['label']}（{entry['status']}）" for entry in shortfall[:5])
            )
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

    design_document = final_state.get("design_document") or {}
    design_hash = (merged_blueprint.get("meta") or {}).get("designHash")
    if isinstance(design_document, dict) and design_hash:
        try:
            from app.design.repository import design_repository

            design_repository.mark_compiled(
                session_id,
                revision=int(design_document.get("revision") or 0),
                design_hash=str(design_hash),
            )
        except Exception as exc:
            # Blueprint 已成功原子保存；状态回写失败不应把已交付产物伪装成生成失败。
            logger.warning(f"[{request_id}] DesignDocument compiled 状态回写失败: {exc}")

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

def _generation_failure_message(node_outputs: dict, final_state: dict) -> str:
    """优先返回真实上游错误，避免骨架失败被笼统的 Blueprint 缺失覆盖。"""
    terminal_model_error = final_state.get("terminal_model_error")
    if isinstance(terminal_model_error, dict) and terminal_model_error.get("user_message"):
        return str(terminal_model_error["user_message"])
    return (
        node_outputs.get("skeleton", {}).get("error")
        or node_outputs.get("execute", {}).get("error")
        or (final_state.get("plan") or {}).get("error")
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

