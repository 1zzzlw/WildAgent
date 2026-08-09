"""与 Agent 业务无关的 WebSocket Presence 注册表。"""

from __future__ import annotations

import asyncio
import os
import secrets
import time

from fastapi import WebSocket

from app.agent.protocol import versioned_event

from .geoip import extract_client_ip, geoip_resolver, mask_ip

MAX_VISITOR_NAME_LENGTH = 24


def normalize_display_name(value: object) -> str:
    """把不可信的访客输入压缩为可安全展示的短名称。"""
    if not isinstance(value, str):
        return "访客"
    normalized = " ".join(value.split())[:MAX_VISITOR_NAME_LENGTH]
    return normalized or "访客"


def _query_display_name(ws: WebSocket) -> object:
    query_params = getattr(ws, "query_params", None)
    getter = getattr(query_params, "get", None)
    return getter("visitor_name") if callable(getter) else None


def _presence_enabled() -> bool:
    return os.getenv("PRESENCE__ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class WebSocketConnectionRegistry:
    """维护当前进程的连接列表，并串行广播在线快照。"""

    def __init__(self, enabled: bool | None = None):
        self.enabled = _presence_enabled() if enabled is None else enabled
        self._connections: dict[WebSocket, dict] = {}
        self._lock = asyncio.Lock()

    @property
    def online_count(self) -> int:
        return len(self._connections)

    async def connect(
        self,
        ws: WebSocket,
        *,
        client_ip: str | None = None,
        region: str | None = None,
        display_name: str | None = None,
    ):
        if not self.enabled:
            return
        resolved_ip = client_ip or extract_client_ip(ws)
        client = {
            "id": secrets.token_hex(4),
            "display_name": normalize_display_name(
                display_name if display_name is not None else _query_display_name(ws)
            ),
            "masked_ip": mask_ip(resolved_ip),
            "region": region or geoip_resolver.resolve_region(resolved_ip),
            "connected_at": int(time.time() * 1000),
        }
        async with self._lock:
            self._connections[ws] = client
            await self._broadcast_locked()

    async def update_display_name(self, ws: WebSocket, display_name: object):
        if not self.enabled:
            return
        async with self._lock:
            client = self._connections.get(ws)
            if client is None:
                return
            client["display_name"] = normalize_display_name(display_name)
            await self._broadcast_locked()

    async def disconnect(self, ws: WebSocket):
        if not self.enabled:
            return
        async with self._lock:
            if ws not in self._connections:
                return
            del self._connections[ws]
            await self._broadcast_locked()

    def _presence_payload(self) -> dict:
        clients = sorted(
            (client.copy() for client in self._connections.values()),
            key=lambda client: client["connected_at"],
        )
        return versioned_event({
            "type": "presence_update",
            "online_count": len(clients),
            "clients": clients,
        })

    async def _broadcast_locked(self):
        payload = self._presence_payload()
        stale_connections = []
        for connection in tuple(self._connections.keys()):
            try:
                await connection.send_json(payload)
            except Exception:
                stale_connections.append(connection)

        if not stale_connections:
            return

        for connection in stale_connections:
            self._connections.pop(connection, None)
        corrected_payload = self._presence_payload()
        for connection in tuple(self._connections.keys()):
            try:
                await connection.send_json(corrected_payload)
            except Exception:
                pass


presence_service = WebSocketConnectionRegistry()
