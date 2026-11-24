"""生成事件协议与事件出口；不依赖具体 WebSocket 连接。"""
from agent.utils.observability.trace import record_final_answer
from agent.utils.observability.trace import record_rag_error
from typing import Protocol

from common.websocket import versioned_event


class EventSink(Protocol):
    async def send_json(self, payload: dict) -> None: ...


def _utc_now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串，用于节点观测记录。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def _send_event(ws: EventSink, payload: dict) -> None:
    """为所有后端事件附加统一协议版本。"""
    if payload.get("type") == "agent_reply":
        record_final_answer(str(payload.get("content") or ""))
        if payload.get("validation_passed") is False:
            record_rag_error(str(payload.get("content") or "校验未通过"))
    elif payload.get("type") == "error":
        record_rag_error(str(payload.get("error") or ""))
    await ws.send_json(versioned_event(payload))


async def _emit_agent_step(
    ws: EventSink,
    request_id: str,
    session_id: str,
    *,
    stage: str,
    node: str,
    status: str,
    label: str,
    detail: str,
) -> None:
    """统一的结构化步骤事件。"""
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
    ws: EventSink,
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
    ws: EventSink,
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
    ws: EventSink,
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
