"""Agent WebSocket 接口；负责连接、身份、协议解析与任务转交。"""
import json
import asyncio
import time
import re
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger
from config import config
from app.application.generation.events import AGENT_PROTOCOL_VERSION
from app.domain.access import access_context_from_headers
from app.application.generation.jobs import generation_job_service
from app.api.websocket.connections import presence_service
from app.api.websocket.heartbeat import WebSocketHeartbeat
from app.api.dependencies import current_user
from app.application.access import check_session
from app.application.errors import ApplicationError
from app.infrastructure.persistence.repositories.activity import record_activity
from app.infrastructure.persistence.repositories.conversations import conversations
from app.application.generation.requests import _prepare_server_request
from app.api.websocket.presenter import send_event as _send_event
from app.api.websocket.presenter import is_disconnected as _websocket_disconnected


router = APIRouter()


@router.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    """维护一个 Agent WebSocket 连接的完整生命周期。

    接收循环始终保持轻量，只负责解析协议、回复 ping 和启动后台生成任务；
    耗时的 LLM 请求不会阻塞心跳。所有请求均由持久化图托管；按请求决定
    推理深度和复杂度目标。图纸与材质确定后自动继续生成。
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

    # ---------- 消息接收循环 ----------
    try:
        await heartbeat.start(on_heartbeat_timeout)
        await presence_service.connect(ws, user=await asyncio.to_thread(current_user, ws))
        while connection_alive and not _websocket_disconnected(ws):
            # receive_text 在没有消息时挂起，但不占用事件循环线程。
            raw = await ws.receive_text()
            # 任意合法/非法文本都表示连接仍活跃，应刷新最后消息时间。
            heartbeat.touch()
            await presence_service.touch(ws)

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

            user = await asyncio.to_thread(current_user, ws) if msg_type not in {"ping", "presence_identify"} else None
            if msg_type == "presence_activity":
                try:
                    await presence_service.update_activity(
                        ws, session_id=data.get("session_id"), activity=data.get("activity"), user=user,
                    )
                except ApplicationError as exc:
                    await _send_event(ws, {"type": "error", "code": exc.code, "error": exc.detail})
                continue
            if msg_type not in {"ping", "presence_identify"} and (user or {}).get("role") != "editor":
                await _send_event(ws, {
                    "type": "error", "code": "permission_denied",
                    "request_id": data.get("request_id"), "session_id": data.get("session_id"),
                    "error": "请使用账号密码登录后操作",
                })
                continue

            if msg_type in {"user_message", "stop_generation", "resume_generation"}:
                session_id = str(data.get("session_id") or "")
                request_id = str(data.get("request_id") or "")
                if (not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id)
                        or (request_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id))):
                    await _send_event(ws, {"type": "error", "code": "invalid_request", "error": "无效的会话或任务标识"})
                    continue
                try:
                    await asyncio.to_thread(check_session, session_id, user)
                    previous = await generation_job_service.get_job(request_id) if request_id else None
                    if previous is not None and previous.session_id != session_id:
                        raise HTTPException(status_code=404, detail="任务不存在")
                    if msg_type == "user_message":
                        await asyncio.to_thread(conversations.ensure, session_id, user["id"])
                except (HTTPException, ApplicationError):
                    await _send_event(ws, {"type": "error", "code": "permission_denied", "request_id": request_id,
                                           "session_id": session_id, "error": "会话或任务不存在"})
                    continue

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
                data["_server_user_id"] = user["id"]
                await asyncio.to_thread(record_activity, user["id"], "ai.request",
                                       session_id=data.get("session_id"), request_id=data.get("request_id"),
                                       key="ai.request:" + str(data.get("request_id")),
                                       details={"message": data.get("message", "")[:12000]})
                job, created = await generation_job_service.start_job(data, ws)
                if not created:
                    await generation_job_service.resume_or_replay(
                        ws,
                        request_id=job.request_id,
                        session_id=job.session_id,
                        after_seq=int(data.get("last_event_seq") or 0),
                    )

            elif msg_type == "stop_generation":
                try:
                    await generation_job_service.stop_job(
                        ws, request_id=str(data.get("request_id") or ""),
                        session_id=str(data.get("session_id") or ""),
                    )
                except ValueError as exc:
                    await _send_event(ws, {
                        "type": "error", "code": "generation_stop_rejected",
                        "request_id": data.get("request_id"), "session_id": data.get("session_id"),
                        "error": str(exc),
                    })

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
        await heartbeat.stop()
        await presence_service.disconnect(ws)
