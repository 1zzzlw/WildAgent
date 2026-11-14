"""与 Agent 业务无关的 WebSocket Presence 注册表。"""

from __future__ import annotations

import asyncio
import os
import json
import secrets
import time

from fastapi import WebSocket
from app.infrastructure.cache import cache
from app.infrastructure.realtime import realtime_bus

from app.contracts.agent_events import versioned_event

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
    """Redis 保存连接元数据及过期时间，进程只保存实际 socket 引用。"""

    TTL_SECONDS = 120

    def __init__(self, enabled: bool | None = None, *, bus=realtime_bus):
        self.enabled = _presence_enabled() if enabled is None else enabled
        self.bus = bus
        self._connections: dict[WebSocket, str] = {}
        self._last_touch: dict[WebSocket, float] = {}
        self._lock = asyncio.Lock()
        self._task = None
        self._online_count = 0
        self._last_snapshot = None

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
                      region: str | None = None, display_name: str | None = None):
        if not self.enabled:
            return
        await self.startup()
        resolved_ip = client_ip or extract_client_ip(ws)
        client = {"id": secrets.token_hex(16),
                  "display_name": normalize_display_name(display_name if display_name is not None else _query_display_name(ws)),
                  "masked_ip": mask_ip(resolved_ip), "region": region or geoip_resolver.resolve_region(resolved_ip),
                  "connected_at": int(time.time() * 1000)}
        self._connections[ws] = client["id"]
        self._last_touch[ws] = time.time()
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.set(cache.key("presence:client:" + client["id"]), json.dumps(client, ensure_ascii=False), ex=self.TTL_SECONDS)
            pipe.zadd(cache.key("presence:connections"), {client["id"]: time.time() + self.TTL_SECONDS})
            await pipe.execute()
        await self._changed()

    async def touch(self, ws: WebSocket):
        identity = self._connections.get(ws)
        now = time.time()
        if not identity or now - self._last_touch.get(ws, 0) < 20:
            return
        self._last_touch[ws] = now
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.expire(cache.key("presence:client:" + identity), self.TTL_SECONDS)
            pipe.zadd(cache.key("presence:connections"), {identity: now + self.TTL_SECONDS})
            await pipe.execute()

    async def update_display_name(self, ws: WebSocket, display_name: object):
        identity = self._connections.get(ws)
        if not identity:
            return
        key = cache.key("presence:client:" + identity)
        raw = await cache.async_client.get(key)
        if raw:
            value = json.loads(raw)
            value["display_name"] = normalize_display_name(display_name)
            await cache.async_client.set(key, json.dumps(value, ensure_ascii=False), xx=True, keepttl=True)
            await self._changed()

    async def disconnect(self, ws: WebSocket):
        identity = self._connections.pop(ws, None)
        self._last_touch.pop(ws, None)
        if not identity:
            return
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.delete(cache.key("presence:client:" + identity))
            pipe.zrem(cache.key("presence:connections"), identity)
            await pipe.execute()
        await self._changed()

    async def _snapshot(self) -> dict:
        key = cache.key("presence:connections")
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", time.time())
            pipe.zrange(key, 0, -1)
            _, identities = await pipe.execute()
        raw = await cache.async_client.mget([cache.key("presence:client:" + identity) for identity in identities]) if identities else []
        clients = sorted((json.loads(value) for value in raw if value), key=lambda client: client["connected_at"])
        self._online_count = len(clients)
        return versioned_event({"type": "presence_update", "online_count": len(clients), "clients": clients})

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
            if payload == self._last_snapshot:
                return
            self._last_snapshot = payload
            connections = tuple(self._connections)
            results = await asyncio.gather(*(asyncio.wait_for(ws.send_json(payload), timeout=5)
                                            for ws in connections), return_exceptions=True)
            stale = [ws for ws, result in zip(connections, results) if isinstance(result, BaseException)]
        # 失败连接在锁外清理，广播不会被单个慢连接串行阻塞。
        for ws in stale:
            await self.disconnect(ws)


presence_service = WebSocketConnectionRegistry()
