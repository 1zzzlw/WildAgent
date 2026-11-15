"""访客显示信息与在线记录用例，独立于实际连接。"""
import secrets
import time
from app.infrastructure.redis.presence import PresenceStore

MAX_VISITOR_NAME_LENGTH = 24


def normalize_display_name(value: object) -> str:
    if not isinstance(value, str):
        return "访客"
    return " ".join(value.split())[:MAX_VISITOR_NAME_LENGTH] or "访客"


class PresenceService:
    def __init__(self, store=None):
        self.store = store or PresenceStore()

    async def register(self, *, display_name: object, masked_ip: str, region: str) -> dict:
        client = {"id": secrets.token_hex(16), "display_name": normalize_display_name(display_name),
                  "masked_ip": masked_ip, "region": region, "connected_at": int(time.time() * 1000)}
        await self.store.register(client)
        return client

    async def touch(self, identity: str) -> None:
        await self.store.touch(identity)

    async def rename(self, identity: str, display_name: object) -> bool:
        return await self.store.rename(identity, normalize_display_name(display_name))

    async def remove(self, identity: str) -> None:
        await self.store.remove(identity)

    async def snapshot(self) -> dict:
        clients = await self.store.list_active()
        return {"type": "presence_update", "online_count": len(clients), "clients": clients}


presence_records = PresenceService()
