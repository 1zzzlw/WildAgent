"""生成事件与物理 WebSocket 的适配，统一处理发送期间的断连。"""
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from integration.generation.events import _send_event


def is_disconnected(ws: WebSocket) -> bool:
    return any(getattr(ws, name, None) is WebSocketState.DISCONNECTED
               for name in ("application_state", "client_state"))


async def send_event(ws: WebSocket, payload: dict) -> None:
    try:
        await _send_event(ws, payload)
    except RuntimeError:
        if is_disconnected(ws):
            raise WebSocketDisconnect(code=1006) from None
        raise
