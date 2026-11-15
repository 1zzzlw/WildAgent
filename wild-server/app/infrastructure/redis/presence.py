"""Redis 在线信息存储；不保存物理连接。"""
import json
import time

from app.infrastructure.redis.connection import cache


class PresenceStore:
    TTL_SECONDS = 120

    async def register(self, client: dict) -> None:
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.set(cache.key("presence:client:" + client["id"]), json.dumps(client, ensure_ascii=False), ex=self.TTL_SECONDS)
            pipe.zadd(cache.key("presence:connections"), {client["id"]: time.time() + self.TTL_SECONDS})
            await pipe.execute()

    async def touch(self, identity: str) -> None:
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.expire(cache.key("presence:client:" + identity), self.TTL_SECONDS)
            pipe.zadd(cache.key("presence:connections"), {identity: time.time() + self.TTL_SECONDS})
            await pipe.execute()

    async def rename(self, identity: str, display_name: str) -> bool:
        key = cache.key("presence:client:" + identity)
        raw = await cache.async_client.get(key)
        if not raw:
            return False
        value = json.loads(raw)
        value["display_name"] = display_name
        await cache.async_client.set(key, json.dumps(value, ensure_ascii=False), xx=True, keepttl=True)
        return True

    async def remove(self, identity: str) -> None:
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.delete(cache.key("presence:client:" + identity))
            pipe.zrem(cache.key("presence:connections"), identity)
            await pipe.execute()

    async def list_active(self) -> list[dict]:
        key = cache.key("presence:connections")
        async with cache.async_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", time.time())
            pipe.zrange(key, 0, -1)
            _, identities = await pipe.execute()
        raw = await cache.async_client.mget([cache.key("presence:client:" + identity) for identity in identities]) if identities else []
        return sorted((json.loads(value) for value in raw if value), key=lambda client: client["connected_at"])
