"""
Agent WebSocket API

前端连接路径: ws://localhost:8000/ws/agent

消息协议（与前端 agentBridge.ts + types/agent.ts 对齐）：

前端 -> 后端:
  {
    "type": "user_message",
    "request_id": "req_xxx",
    "session_id": "sess_xxx",
    "scene_id": "scene_xxx",
    "scene_revision": 8,
    "message": "生成一座中式凉亭",
    "scene_summary": { "elements_count": 42, "types": [...], "bbox": {...} },
    "selection": []
  }

  心跳:
  { "type": "ping", "timestamp": 1234567890 }

后端 -> 前端:
  agent_step:          { "type": "agent_step", "request_id": "...", "stage": "analyzing", "content": "..." }
  blueprint_generated: { "type": "blueprint_generated", "request_id": "...", "blueprint": {...}, "file_path": "..." }
  agent_reply:         { "type": "agent_reply", "request_id": "...", "content": "..." }
  error:               { "type": "error", "request_id": "...", "error": "..." }

  心跳:
  pong:           { "type": "pong", "timestamp": 1234567890 }
  network_error:  { "type": "network_error", "error": "心跳超时，连接即将关闭", "reason": "heartbeat_timeout" }

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
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from app.services.agent_service import agent_service
from app.utils.blueprint_parser import save_blueprint_file, SCENES_DIR
from app.utils.ws_heartbeat import WebSocketHeartbeat

router = APIRouter()

@router.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
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
            await ws.send_json({
                "type": "network_error",
                "error": "心跳超时，连接已断开",
                "reason": "heartbeat_timeout"
            })
        except Exception:
            pass
        connection_alive = False
        try:
            await ws.close()
        except Exception:
            pass

    await heartbeat.start(on_heartbeat_timeout)

    # ---------- 消息处理锁 ----------
    processing_lock = asyncio.Lock()

    async def handle_user_message_safe(data: dict):
        """在锁保护下处理用户消息，同时更新心跳标记"""
        async with processing_lock:
            heartbeat.is_processing = True
            try:
                await _handle_user_message(ws, data)
            finally:
                heartbeat.is_processing = False
                heartbeat.touch()  # 处理完成后刷新心跳计时

    # ---------- 消息接收循环 ----------
    try:
        while connection_alive:
            raw = await ws.receive_text()
            heartbeat.touch()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({
                    "type": "error",
                    "request_id": None,
                    "error": "消息格式错误，需要 JSON"
                })
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                await ws.send_json({
                    "type": "pong",
                    "timestamp": data.get("timestamp", int(time.time() * 1000))
                })

            elif msg_type == "user_message":
                if processing_lock.locked():
                    await ws.send_json({
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "error": "正在处理上一条消息，请稍后再发送"
                    })
                else:
                    asyncio.create_task(handle_user_message_safe(data))

            else:
                await ws.send_json({
                    "type": "error",
                    "request_id": data.get("request_id"),
                    "error": f"未知消息类型: {msg_type}"
                })

    except WebSocketDisconnect:
        logger.info("Agent WebSocket 客户端已断开")
    except Exception as e:
        logger.error(f"Agent WebSocket 异常: {e}")
        try:
            await ws.send_json({
                "type": "network_error",
                "error": f"服务端异常: {str(e)}",
                "reason": "connection_lost"
            })
        except Exception:
            pass
    finally:
        connection_alive = False
        await heartbeat.stop()


async def _handle_user_message(ws: WebSocket, data: dict):
    request_id = data.get("request_id", "")
    message = data.get("message", "")

    logger.info(f"[{request_id}] 收到用户消息: {message[:80]}...")

    async def send_step(stage: str, content: str):
        """发送 agent_step 进度消息"""
        await ws.send_json({
            "type": "agent_step",
            "request_id": request_id,
            "stage": stage,
            "content": content,
        })

    # ===== Phase 1: 分析 + 生成（LLM 调用前发送进度） =====
    await send_step("analyzing", "正在分析您的建筑需求...")
    await send_step("generating", "正在调用 AI 生成建筑蓝图，请耐心等待...")

    # ===== Phase 2: LLM 查询 =====
    result = await agent_service.query_structured(message)

    # ===== Phase 3: 提取 Blueprint 后处理 =====
    if result.blueprint is not None:
        await send_step("validating", "正在校验蓝图数据结构...")

        if result.error:
            logger.warning(f"[{request_id}] Blueprint 结构警告: {result.error}")

        await send_step("saving", "正在保存蓝图文件...")

        try:
            file_path = save_blueprint_file(result.blueprint, SCENES_DIR)
            logger.info(f"[{request_id}] Blueprint 已保存: {file_path}")
        except Exception as e:
            logger.error(f"[{request_id}] 保存 Blueprint 失败: {e}")
            file_path = ""  # 保存失败不阻塞，前端仍可加载数据

        # 发送 blueprint_generated（只发文件路径，前端通过 HTTP 拉取）
        filename = Path(file_path).name if file_path else ""
        await ws.send_json({
            "type": "blueprint_generated",
            "request_id": request_id,
            "filename": filename,
            "file_url": f"/api/scenes/{filename}" if filename else "",
        })
    else:
        logger.warning(f"[{request_id}] 未从回复中提取到 Blueprint: {result.error}")

    # ===== Phase 4: 发送文本回复 =====
    await ws.send_json({
        "type": "agent_reply",
        "request_id": request_id,
        "content": result.text,
    })

    logger.info(f"[{request_id}] 处理完成")
