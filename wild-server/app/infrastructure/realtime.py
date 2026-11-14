"""Redis 负责跨实例通知；丢失通知后由 MySQL 事件序号补发。"""
import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable

from loguru import logger

from .cache import cache


class RealtimeBus:
    def __init__(self, *, client=None):
        self.instance_id = secrets.token_hex(16)
        self.handlers: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}
        self._task = None
        self._pubsub = None
        self._client = client
        self._owns_client = client is None

    async def start(self):
        if self._task is not None:
            return
        if self._client is None:
            self._client = cache.create_async_client(socket_timeout=None)
        self._pubsub = self._client.pubsub()
        await self._pubsub.subscribe(cache.key("runtime"))
        self._task = asyncio.create_task(self._listen(), name="redis-runtime-listener")

    def subscribe(self, topic: str, handler):
        self.handlers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler):
        if handler in self.handlers.get(topic, []):
            self.handlers[topic].remove(handler)

    async def publish(self, topic: str, data: dict):
        await cache.async_client.publish(cache.key("runtime"), json.dumps(
            {"origin": self.instance_id, "topic": topic, "data": data}, ensure_ascii=False))

    async def _listen(self):
        while True:
            try:
                async for message in self._pubsub.listen():
                    if message["type"] != "message":
                        continue
                    value = json.loads(message["data"])
                    if value["origin"] == self.instance_id:
                        continue
                    for handler in tuple(self.handlers.get(value["topic"], [])):
                        await handler(value["data"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Redis 实时通知连接中断，正在重连；历史事件可按序号补发")
                await asyncio.sleep(1)

    async def close(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._pubsub:
            await self._pubsub.aclose()
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
        self._task = self._pubsub = None


realtime_bus = RealtimeBus()


@asynccontextmanager
async def session_lock(session_id: str):
    lock = cache.async_client.lock(cache.key("session:lock:" + session_id), timeout=30,
                                   blocking_timeout=5)
    if not await lock.acquire():
        raise ValueError("当前会话正在处理其他操作，请稍后重试")
    try:
        yield
    finally:
        await lock.release()
