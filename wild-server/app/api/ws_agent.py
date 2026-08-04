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
    "thinking_mode": false,
    "scene_summary": { "elements_count": 42, "types": [...], "bbox": {...} },
    "selection": []
  }

  心跳:
  { "type": "ping", "timestamp": 1234567890 }

后端 -> 前端:
  agent_step:          { "type": "agent_step", "request_id": "...", "stage": "analyzing", "content": "..." }
  thinking_delta:      { "type": "thinking_delta", "request_id": "...", "delta": "..." }
  thinking_status:     { "type": "thinking_status", "request_id": "...", "status": "thinking|completed|unsupported|error" }
  blueprint_generated: { "type": "blueprint_generated", "request_id": "...", "blueprint": {...}, "file_path": "..." }
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
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from app.services.agent_service import agent_service
from app.extensions.presence import presence_service
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

            elif msg_type == "presence_identify":
                # 展示名仅交给可选 Presence 扩展，不进入 Agent 或会话数据。
                await presence_service.update_display_name(
                    ws,
                    data.get("display_name"),
                )

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
        await presence_service.disconnect(ws)


async def _handle_user_message(ws: WebSocket, data: dict):
    """前端传 precision_mode=true → LangGraph 精密模式; 否则 → LangChain 快速模式"""
    precision_mode = data.get("precision_mode") is True
    if precision_mode:
        await _handle_with_langgraph(ws, data)
    else:
        await _handle_with_langchain(ws, data)


# ── 节点名 → 展示标签 ──
_NODE_LABELS = {
    "skeleton": "骨架",
    "door": "门", "window": "窗", "roof": "屋顶",
    "railing": "栏杆", "canopy": "雨棚", "balcony": "阳台",
    "light": "灯具", "ramp": "坡道", "bay_window": "凸窗",
    "cornice": "檐口", "chimney": "烟囱",
    "merge": "合并", "validate": "校验", "callback": "修正",
}


async def _handle_with_langgraph(ws: WebSocket, data: dict):
    """LangGraph 精密模式：分片并行 + 每节点实时推送 RAG/LLM/思考诊断 + 性能汇总"""
    from app.agent.graph import build_generation_graph
    from app.agent.graph_state import GenerationState

    request_id = data.get("request_id", "")
    message = data.get("message", "")
    current_blueprint = data.get("blueprint")
    session_id = data.get("session_id", request_id)
    thinking_mode = data.get("thinking_mode") is True

    logger.info(f"[{request_id}] [precision] 收到: {message[:80]}...")

    async def send_step(stage: str, content: str):
        await ws.send_json({
            "type": "agent_step", "request_id": request_id,
            "stage": stage, "content": content,
        })

    async def send_debug(category: str, data_obj: dict):
        await ws.send_json({
            "type": "debug_log", "request_id": request_id,
            "category": category, "data": data_obj,
        })
    
    async def send_thinking_delta(node_name: str, delta: str):
        """实时推送节点的思考内容给前端（带节点标识）"""
        await ws.send_json({
            "type": "thinking_delta",
            "request_id": request_id,
            "node": node_name,  # 标记是哪个节点的思考
            "delta": delta,
        })

    # ── 初始状态 ──
    initial_state: GenerationState = {
        "user_message": message,
        "building_type": _detect_building_type(message),
        "session_id": session_id,
        "current_blueprint": current_blueprint,
        "thinking_mode": thinking_mode,
        "on_reasoning_delta": send_thinking_delta if thinking_mode else None,
        "max_retries": 3,
        "retry_count": 0,
    }

    # ── 流式执行（astream_events: 可获取节点 start/end 事件）──
    graph = build_generation_graph(enable_callback=False)
    all_diags: dict[str, dict] = {}
    final_state = None
    total_tokens = {"input": 0, "output": 0}
    suggested_components = []  # 存储骨架节点建议的组件列表

    _OUR_NODES = {"skeleton", "door", "window", "roof", "railing",
                  "canopy", "balcony", "light", "ramp", "bay_window",
                  "cornice", "chimney", "merge"}

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event.get("event")
            node_name = event.get("name", "")
            if node_name not in _OUR_NODES:
                continue

            label = _NODE_LABELS.get(node_name, node_name)

            # ── 节点开始 ──
            if kind == "on_chain_start":
                # skeleton 总是显示
                if node_name == "skeleton":
                    await send_step("generating", f"{node_name}:running:{label} RAG检索 → LLM规划中...")
                # merge/validate/callback 不显示 running 状态
                elif node_name not in ("merge", "validate", "callback"):
                    # 只有在建议列表中的组件才显示 running 状态
                    # 如果还没获取到建议列表，所有组件都显示（第一轮）
                    if not suggested_components or node_name in suggested_components:
                        await send_step("generating", f"{node_name}:running:{label} RAG检索 → LLM思考生成中...")

            # ── 节点结束 ──
            elif kind == "on_chain_end":
                node_output = event.get("data", {}).get("output", {})

                # ── skeleton 节点：提取建议的组件列表 ──
                if node_name == "skeleton":
                    suggested_components = node_output.get("suggested_components", [])
                    logger.info(f"[{request_id}] 骨架节点建议组件: {suggested_components}")

                # 提取诊断数据（现在 State 已声明所有 _diag 字段）
                diag_key = f"{node_name}_diag"
                diag = node_output.get(diag_key, {})
                if diag:
                    all_diags[node_name] = diag

                tu = diag.get("token_usage")
                if tu:
                    total_tokens["input"] += tu.get("input", 0)
                    total_tokens["output"] += tu.get("output", 0)

                # ── skeleton ──
                if node_name == "skeleton":
                    if node_output.get("error"):
                        await send_step("generating", f"{node_name}:error:{node_output['error']}")
                    else:
                        ec = diag.get("element_count", "?")
                        rc = diag.get("reasoning_chars", 0)
                        await send_step("generating",
                            f"{node_name}:done:骨架 {ec}构件 | RAG {diag.get('rag_chars',0)}字 {diag.get('rag_ms',0)}ms | LLM {diag.get('llm_chars',0)}字 {diag.get('llm_ms',0)}ms | 思考 {rc}字 | 建议组件: {', '.join(suggested_components)}")
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "rag_chars": diag.get("rag_chars"), "rag_ms": diag.get("rag_ms"),
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
                    await send_step("generating", f"{node_name}:done:合并完成")

                else:
                    # ── 组件节点 ──
                    if diag.get("skipped"):
                        # 已建议但被跳过的组件（用户明确排除）
                        await send_step("generating",
                            f"{node_name}:skipped:{label} 跳过 ({diag.get('reason','')})")
                    elif diag.get("error"):
                        await send_step("generating",
                            f"{node_name}:error:{diag['error']}")
                    else:
                        fc = diag.get("fragment_count", 0)
                        rc = diag.get("reasoning_chars", 0)
                        await send_step("generating",
                            f"{node_name}:done:{label} {fc}个 | RAG {diag.get('rag_chars',0)}字 {diag.get('rag_ms',0)}ms | LLM {diag.get('llm_chars',0)}字 {diag.get('llm_ms',0)}ms | 思考 {rc}字")
                        await send_debug("node", {
                            "node": node_name, "label": label, "stage": "done",
                            "rag_chars": diag.get("rag_chars"), "rag_ms": diag.get("rag_ms"),
                            "prompt_chars": diag.get("prompt_chars"),
                            "llm_chars": diag.get("llm_chars"), "llm_ms": diag.get("llm_ms"),
                            "token_usage": diag.get("token_usage"),
                            "reasoning_chars": rc,
                            "reasoning_preview": diag.get("reasoning_preview"),
                            "fragment_count": fc, "total_ms": diag.get("total_ms"),
                        })

                final_state = node_output

    except Exception as e:
        logger.exception(f"[{request_id}] LangGraph 异常: {e}")
        await ws.send_json({"type": "error", "request_id": request_id, "error": str(e)})
        return

    if final_state is None:
        await ws.send_json({"type": "error", "request_id": request_id, "error": "未返回结果"})
        return

    # ── 校验流水线（手动执行，每步实时推进度）──
    merged_blueprint = final_state.get("merged_blueprint")
    if not merged_blueprint:
        await ws.send_json({"type": "error", "request_id": request_id, "error": "合并后的 Blueprint 缺失"})
        return

    await send_step("generating", "validate:running:启动 15 步校验流水线...")

    from app.services.agent_service import run_validation_pipeline, _final_errors
    try:
        pipeline_results = run_validation_pipeline(merged_blueprint)
    except Exception as e:
        logger.exception(f"[{request_id}] 校验流水线执行失败: {e}")
        await ws.send_json({"type": "error", "request_id": request_id, "error": f"校验失败: {e}"})
        return

    # 逐步推送校验进度
    final_errors_list = _final_errors(pipeline_results)
    error_step_names = {r.name for r in final_errors_list}
    for pr in pipeline_results:
        output_text = pr.output
        if output_text.startswith("⏭️"):
            await send_step("generating",
                f"validate:running:[{pr.step}] {pr.name}: ⏭️ 跳过")
            continue
        if pr.name in error_step_names:
            await send_step("generating",
                f"validate:running:[{pr.step}] {pr.name}: ❌ {output_text[:150]}")
        elif pr.has_warning:
            await send_step("generating",
                f"validate:running:[{pr.step}] {pr.name}: ⚠️ {output_text[:150]}")
        else:
            await send_step("generating",
                f"validate:running:[{pr.step}] {pr.name}: ✅")

    # 汇总
    total_steps = len(pipeline_results)
    validation_errors = len(final_errors_list)
    validation_warnings = sum(1 for r in pipeline_results if r.has_warning and r.name not in error_step_names)
    validation_passed = total_steps - validation_errors - validation_warnings
    await send_step("generating",
        f"validate:done:校验 {total_steps}步 {validation_passed}✓ {validation_warnings}⚠ {validation_errors}✗")

    # ── 保存 Blueprint ──
    await send_step("generating", "saving:running:保存蓝图文件...")

    meta_name = merged_blueprint.get("meta", {}).get("name", "") or ""
    elements = merged_blueprint.get("geometry", {}).get("elements", [])
    components = merged_blueprint.get("geometry", {}).get("components", [])

    try:
        import datetime as _dt, re as _re
        def _slug(name, max_len=40):
            s = _re.sub(r"[^\w一-鿿]", "_", name, flags=_re.UNICODE)
            return _re.sub(r"_+", "_", s).strip("_")[:max_len]
        today = _dt.date.today().strftime("%Y-%m-%d")
        slug = _slug(meta_name)
        wild_filename = f"{session_id}_{slug}.wild" if slug else f"{session_id}.wild"
        rel_path = f"{today}/{wild_filename}"
        save_blueprint_file_as(merged_blueprint, SCENES_DIR, rel_path)
    except Exception as e:
        logger.error(f"[{request_id}] 保存失败: {e}")
        rel_path = ""

    if rel_path:
        await ws.send_json({
            "type": "blueprint_generated", "request_id": request_id,
            "session_id": session_id, "filename": rel_path,
            "file_url": f"/api/scenes/{rel_path}",
        })

    final_status = "complete" if validation_errors == 0 else "partial"
    await ws.send_json({
        "type": "agent_reply", "request_id": request_id,
        "content": f"已生成 {meta_name or '建筑'}（{len(elements)}元素 + {len(components)}组件, 校验 {final_status}: {validation_passed}✓ {validation_warnings}⚠ {validation_errors}✗）",
    })

    # ── 性能汇总 ──
    active_diags = {k: v for k, v in all_diags.items() if not v.get("skipped")}
    total_rag_ms = sum(v.get("rag_ms", 0) for v in active_diags.values())
    total_llm_ms = sum(v.get("llm_ms", 0) for v in active_diags.values())
    fragment_total = sum(v.get("fragment_count", 0) for v in active_diags.values())
    await send_debug("session_metrics", {
        "node_count": len(all_diags),
        "active_nodes": len(active_diags),
        "skipped_nodes": len(all_diags) - len(active_diags),
        "suggested_components": suggested_components,
        "total_rag_ms": total_rag_ms,
        "total_llm_ms": total_llm_ms,
        "total_tokens": {
            "input": total_tokens["input"],
            "output": total_tokens["output"],
            "total": total_tokens["input"] + total_tokens["output"],
        },
        "fragment_total": fragment_total,
        "validation_steps": len(pipeline_results),
        "validation_errors": validation_errors,
        "retry_count": 0,
        "max_retries": 3,
        "status": final_state.get("status", "?"),
    })

    logger.info(f"[{request_id}] [precision] 完成: {len(active_diags)}活跃节点, "
                f"建议组件: {suggested_components}, "
                f"RAG {total_rag_ms}ms, LLM {total_llm_ms}ms, "
                f"tokens {total_tokens['input']+total_tokens['output']}")



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


async def _handle_with_langchain(ws: WebSocket, data: dict):
    """执行一次用户请求，并把 QueryResult 翻译成 WebSocket 协议消息。

    根据 AgentService 的结构化结果分成三条出口：
    完整 Blueprint 会落盘，ScenePatch 等待前端确认，普通对话只返回文本。
    """
    request_id = data.get("request_id", "")
    message = data.get("message", "")
    current_blueprint = data.get("blueprint")
    # 只有 JSON 布尔值 true 才开启，避免字符串 "true" 等意外触发日志。
    thinking_mode = data.get("thinking_mode") is True
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

    reasoning_received = False

    async def send_reasoning_delta(delta: str):
        """实时转发模型接口实际返回的 reasoning_content。"""
        nonlocal reasoning_received
        reasoning_received = True
        await ws.send_json({
            "type": "thinking_delta",
            "request_id": request_id,
            "delta": delta,
        })

    async def send_thinking_status(status: str, content: str = ""):
        await ws.send_json({
            "type": "thinking_status",
            "request_id": request_id,
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
            # 用日期子目录格式保存：YYYY-MM-DD/{session_id}_{meta.name}.wild
            import datetime as _dt
            import re as _re

            def _slug(name: str, max_len: int = 40) -> str:
                s = _re.sub(r"[^\w\u4e00-\u9fff]", "_", name, flags=_re.UNICODE)
                s = _re.sub(r"_+", "_", s).strip("_")
                return s[:max_len]

            today = _dt.date.today().strftime("%Y-%m-%d")
            meta_name = result.blueprint.get("meta", {}).get("name", "") or ""
            slug = _slug(meta_name)
            wild_filename = f"{session_id}_{slug}.wild" if slug else f"{session_id}.wild"
            rel_path = f"{today}/{wild_filename}"

            # 完整蓝图由服务端保存，前端通过 scenes REST API 再读取文件。
            file_path = save_blueprint_file_as(
                result.blueprint, SCENES_DIR, rel_path
            )
            logger.info(f"[{request_id}] Blueprint 已保存: {file_path}")
        except Exception as e:
            logger.error(f"[{request_id}] 保存 Blueprint 失败: {e}")
            rel_path = ""
            wild_filename = ""
            file_path = ""

        # filename 返回完整相对路径（含日期目录），前端凭此拼接 GET/DELETE URL
        filename = rel_path if rel_path else ""
        await ws.send_json({
            "type": "blueprint_generated",
            "request_id": request_id,
            "session_id": session_id,
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

    elif result.error:
        # JSON 已被识别但结构预检失败时，不把无效 Blueprint 当作普通聊天回复。
        await ws.send_json({
            "type": "agent_reply",
            "request_id": request_id,
            "content": f"生成结果未通过结构预检：\n\n{result.error}",
        })

    else:
        # ── 对话类：纯文本 ──────────────────────────────────
        await ws.send_json({
            "type": "agent_reply",
            "request_id": request_id,
            "content": result.text,
        })

    logger.info(f"[{request_id}] 处理完成")
