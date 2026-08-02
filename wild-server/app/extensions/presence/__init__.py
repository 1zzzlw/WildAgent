"""WebSocket 在线状态扩展的公共入口。"""

from .service import WebSocketConnectionRegistry, presence_service

__all__ = ["WebSocketConnectionRegistry", "presence_service"]
