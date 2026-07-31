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
from app.utils.blueprint_parser import save_blueprint_file_as, SCENES_DIR
from app.utils.ws_heartbeat import WebSocketHeartbeat

router = APIRouter()


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
            await ws.send_json({
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
    耗时的 LLM 请求不会阻塞心跳。函数退出前会取消仍在运行的生成任务，并停止
    此连接专属的心跳监控器。
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
            await ws.send_json({
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
                await ws.send_json({
                    "type": "error",
                    "request_id": None,
                    "error": "消息格式错误，需要 JSON"
                })
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                # 原样回传前端时间戳，便于前端计算往返延迟。
                await ws.send_json({
                    "type": "pong",
                    "timestamp": data.get("timestamp", int(time.time() * 1000))
                })

            elif msg_type == "user_message":
                if active_message_task is not None and not active_message_task.done():
                    await ws.send_json({
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "error": "正在处理上一条消息，请稍后再发送"
                    })
                else:
                    # 后台执行保证接收循环继续响应 ping；任务引用用于退出时取消。
                    active_message_task = asyncio.create_task(
                        handle_user_message_safe(data)
                    )

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
        if active_message_task is not None:
            if not active_message_task.done():
                # 客户端离开后生成结果已无接收者，及时取消下游 LLM 任务。
                active_message_task.cancel()
            try:
                await active_message_task
            except asyncio.CancelledError:
                pass
        await heartbeat.stop()


async def _handle_user_message(ws: WebSocket, data: dict):
    """执行一次用户请求，并把 QueryResult 翻译成 WebSocket 协议消息。

    根据 AgentService 的结构化结果分成三条出口：
    完整 Blueprint 会落盘，ScenePatch 等待前端确认，普通对话只返回文本。
    """
    request_id = data.get("request_id", "")
    message = data.get("message", "")
    current_blueprint = data.get("blueprint")
    # 相同 session_id 使用同一个文件名，因此后续生成会更新该会话的场景文件。
    session_id = data.get("session_id", request_id)

    logger.info(f"[{request_id}] 收到用户消息: {message[:80]}...")

    async def send_step(stage: str, content: str):
        """发送一条仅用于前端展示进度的 agent_step 消息。"""
        await ws.send_json({
            "type": "agent_step",
            "request_id": request_id,
            "stage": stage,
            "content": content,
        })

    # ===== Phase 1: 分析 + 生成 =====
    await send_step("analyzing", "正在分析您的需求...")
    await send_step("generating", "正在调用 AI 处理，请耐心等待...")

    # ===== Phase 2: LLM 查询（统一入口，AI 自行判断意图）=====
    # ticker 与真实查询并行，只负责在长等待期间提供阶段性反馈。
    ticker_task = asyncio.create_task(_thinking_ticker(send_step))
    try:
        result = await agent_service.query_structured(message, current_blueprint)
    finally:
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass

    # ===== Phase 3: 处理结果（按 AI 输出的格式分发）=====
    if result.blueprint is not None:
        # ── 生成类：完整 Blueprint ──────────────────────────
        # 跳过项不展示；其余校验结果统一映射成前端可读的状态行。
        for pr in result.pipeline_results:
            if pr.output.startswith("⏭️"):
                continue
            status = "❌" if pr.has_error else "⚠️" if pr.has_warning else "✅"
            await send_step(
                "validating",
                f"{status} [{pr.step}] {pr.name}: {pr.output[:300]}"
            )

        if result.error:
            logger.warning(f"[{request_id}] 流水线校验警告: {result.error}")

        await send_step("saving", "正在保存蓝图文件...")

        try:
            # 完整蓝图由服务端保存，前端通过 scenes REST API 再读取文件。
            file_path = save_blueprint_file_as(
                result.blueprint, SCENES_DIR, f"{session_id}.wild"
            )
            logger.info(f"[{request_id}] Blueprint 已保存: {file_path}")
        except Exception as e:
            logger.error(f"[{request_id}] 保存 Blueprint 失败: {e}")
            file_path = ""

        filename = Path(file_path).name if file_path else ""
        await ws.send_json({
            "type": "blueprint_generated",
            "request_id": request_id,
            "filename": filename,
            "file_url": f"/api/scenes/{filename}" if filename else "",
        })

        await ws.send_json({
            "type": "agent_reply",
            "request_id": request_id,
            "content": result.text,
        })

    elif result.patch is not None:
        # ── 修改类：ScenePatch ──────────────────────────────
        for pr in result.pipeline_results:
            if pr.output.startswith("⏭️"):
                continue
            status = "❌" if pr.has_error else "⚠️" if pr.has_warning else "✅"
            await send_step(
                "validating",
                f"{status} [{pr.step}] {pr.name}: {pr.output[:300]}"
            )

        # 有 ❌ 级别错误则不发送 patch，改为错误提示
        if result.error:
            logger.warning(f"[{request_id}] Patch 校验失败，不发送: {result.error}")
            await ws.send_json({
                "type": "agent_reply",
                "request_id": request_id,
                "content": f"生成的修改方案存在问题，无法应用：\n\n{result.error}\n\n请重新描述你的需求。",
            })
        else:
            # Patch 只是 proposal，前端必须让用户确认后才能真正应用到当前场景。
            await ws.send_json({
                "type": "patch_proposal",
                "request_id": request_id,
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

            await ws.send_json({
                "type": "agent_reply",
                "request_id": request_id,
                "content": result.text,
            })

    else:
        # ── 对话类：纯文本 ──────────────────────────────────
        await ws.send_json({
            "type": "agent_reply",
            "request_id": request_id,
            "content": result.text,
        })

    logger.info(f"[{request_id}] 处理完成")


async def _thinking_ticker(send_step):
    """LLM 生成期间每 8 秒推一条思考进度，直到被取消"""
    # 文案数量有限；全部发送完后协程自然结束，不会循环重复。
    THINKING_MESSAGES = [
        "理解建筑需求，规划构件组合...",
        "计算空间布局与构件尺寸...",
        "生成墙体、楼板、屋顶参数...",
        "处理门窗坐标与材质定义...",
        "完善细节构件与约束关系...",
        "即将完成，正在整理输出...",
    ]
    for msg in THINKING_MESSAGES:
        await asyncio.sleep(8)
        try:
            await send_step("generating", msg)
        except Exception:
            break
