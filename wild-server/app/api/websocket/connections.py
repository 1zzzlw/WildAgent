"""与 Agent 业务无关的 WebSocket Presence 注册表。"""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import WebSocket
from app.application.presence import presence_records, public_presence_snapshot
from app.infrastructure.redis.events import realtime_bus

from app.application.generation.events import versioned_event

from app.infrastructure.geoip import extract_client_ip
from app.infrastructure.geoip import geoip_resolver
from app.infrastructure.geoip import mask_ip

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
    """Redis 保存连接元数据及过期时间，进程只保存实际 socket 引用。"""

    TTL_SECONDS = 120

    def __init__(self, enabled: bool | None = None, *, bus=realtime_bus):
        self.enabled = _presence_enabled() if enabled is None else enabled
        self.bus = bus
        self._connections: dict[WebSocket, str] = {}
        self._users: dict[WebSocket, dict | None] = {}
        self._last_sent: dict[WebSocket, dict] = {}
        self._last_touch: dict[WebSocket, float] = {}
        self._lock = asyncio.Lock()
        self._task = None
        self._online_count = 0

    @property
    def online_count(self) -> int:
        return self._online_count

    async def startup(self):
        if not self.enabled or self._task:
            return
        await self.bus.start()
        self.bus.subscribe("presence", self._remote_changed)
        self._task = asyncio.create_task(self._refresh_loop(), name="redis-presence-refresh")

    async def shutdown(self):
        self.bus.unsubscribe("presence", self._remote_changed)
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        for ws in tuple(self._connections):
            await self.disconnect(ws)

    async def connect(self, ws: WebSocket, *, client_ip: str | None = None,
                      region: str | None = None, display_name: str | None = None,
                      user: dict | None = None):
        if not self.enabled:
            return
        await self.startup()
        resolved_ip = client_ip or extract_client_ip(ws)
        client = await presence_records.register(
            display_name=display_name if display_name is not None else _query_display_name(ws),
            masked_ip=mask_ip(resolved_ip), region=region or geoip_resolver.resolve_region(resolved_ip),
            user=user,
        )
        self._connections[ws] = client["id"]
        self._users[ws] = user
        self._last_touch[ws] = time.time()
        await self._changed()

    async def touch(self, ws: WebSocket):
        identity = self._connections.get(ws)
        now = time.time()
        if not identity or now - self._last_touch.get(ws, 0) < 20:
            return
        self._last_touch[ws] = now
        await presence_records.touch(identity)

    async def update_display_name(self, ws: WebSocket, display_name: object):
        identity = self._connections.get(ws)
        if not identity:
            return
        if await presence_records.rename(identity, display_name):
            await self._changed()

    async def update_activity(self, ws: WebSocket, *, session_id: object, activity: object,
                              user: dict | None):
        identity = self._connections.get(ws)
        if identity and await presence_records.set_activity(
            identity, session_id=session_id, activity=activity, user=user
        ) and self._connections.get(ws) == identity:
            self._users[ws] = user
            await self._changed()

    async def disconnect(self, ws: WebSocket):
        identity = self._connections.pop(ws, None)
        self._last_touch.pop(ws, None)
        self._users.pop(ws, None)
        self._last_sent.pop(ws, None)
        if not identity:
            return
        await presence_records.remove(identity)
        await self._changed()

    async def _snapshot(self) -> dict:
        payload = await presence_records.snapshot()
        self._online_count = payload["online_count"]
        return versioned_event(payload)

    async def _changed(self):
        await self._broadcast()
        await self.bus.publish("presence", {})

    async def _remote_changed(self, _data: dict):
        await self._broadcast()

    async def _refresh_loop(self):
        while True:
            await asyncio.sleep(20)
            await self._broadcast()

    async def _broadcast(self):
        async with self._lock:
            payload = await self._snapshot()
            updates = [(ws, public_presence_snapshot(payload, self._users.get(ws))) for ws in self._connections]
            updates = [(ws, value) for ws, value in updates if self._last_sent.get(ws) != value]
            results = await asyncio.gather(*(asyncio.wait_for(ws.send_json(value), timeout=5)
                                            for ws, value in updates), return_exceptions=True)
            stale = []
            for (ws, value), result in zip(updates, results):
                if isinstance(result, BaseException):
                    stale.append(ws)
                elif ws in self._connections:
                    self._last_sent[ws] = value
        # 失败连接在锁外清理，广播不会被单个慢连接串行阻塞。
        for ws in stale:
            await self.disconnect(ws)


presence_service = WebSocketConnectionRegistry()
