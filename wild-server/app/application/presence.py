"""访客显示信息与在线记录用例，独立于实际连接。"""
import asyncio
import re
import secrets
import time
from app.application.access import check_owner
from app.application.errors import ApplicationError
from app.infrastructure.persistence.repositories.conversations import conversations
from app.infrastructure.redis.presence import PresenceStore

MAX_VISITOR_NAME_LENGTH = 24
SESSION_IDLE_SECONDS = 60


def public_presence_snapshot(snapshot: dict, user: dict | None) -> dict:
    """在线概况公开；会话位置只对该会话的可访问者公开。"""
    user = user or {}
    clients = []
    for value in snapshot["clients"]:
        client = {key: item for key, item in value.items() if not key.startswith("_")}
        owner_id = value.get("_session_owner_id")
        if owner_id is not None and user.get("id") != owner_id and user.get("identity") != 2:
            client.update(session_id=None, activity="idle")
        clients.append(client)
    return {**snapshot, "clients": clients}


def normalize_display_name(value: object) -> str:
    if not isinstance(value, str):
        return "访客"
    return " ".join(value.split())[:MAX_VISITOR_NAME_LENGTH] or "访客"


class PresenceService:
    def __init__(self, store=None):
        self.store = store or PresenceStore()

    async def register(self, *, display_name: object, masked_ip: str, region: str,
                       user: dict | None = None) -> dict:
        user = user or {}
        client = {"id": secrets.token_hex(16), "display_name": normalize_display_name(display_name),
                  "masked_ip": masked_ip, "region": region, "connected_at": int(time.time() * 1000),
                  "user_id": user.get("id"), "username": user.get("username"),
                  "can_edit": user.get("role") == "editor", "session_id": None, "activity": "idle"}
        await self.store.register(client)
        return client

    async def touch(self, identity: str) -> None:
        await self.store.touch(identity)

    async def rename(self, identity: str, display_name: object) -> bool:
        return await self.store.rename(identity, normalize_display_name(display_name))

    async def remove(self, identity: str) -> None:
        await self.store.remove(identity)

    async def set_activity(self, identity: str, *, session_id: object, activity: object,
                           user: dict | None) -> bool:
        if not isinstance(activity, str) or activity not in {"active", "idle", "generating"}:
            raise ApplicationError("invalid_input", "无效的会话活动状态")
        user = user or {}
        owner_id = None
        if session_id is not None:
            if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
                raise ApplicationError("invalid_input", "无效的会话标识")
            if user.get("role") != "editor" or not user.get("id"):
                raise ApplicationError("forbidden", "登录编辑账号后才能上报会话操作状态")
            exists, owner_id = await asyncio.to_thread(conversations.owner, session_id)
            check_owner(owner_id, user)
            # 尚未保存的本地草稿只对创建它的账号显示。
            if not exists:
                owner_id = user["id"]
        return await self.store.update(identity, {
            "session_id": session_id, "activity": activity if session_id else "idle",
            "user_id": user.get("id"), "username": user.get("username"),
            "can_edit": user.get("role") == "editor", "_session_owner_id": owner_id,
            "_activity_at": int(time.time() * 1000),
        })

    async def snapshot(self) -> dict:
        """内部快照；出站前由 public_presence_snapshot 按接收账号过滤。"""
        clients = await self.store.list_active()
        now = int(time.time() * 1000)
        for client in clients:
            if now - client.get("_activity_at", 0) >= SESSION_IDLE_SECONDS * 1000:
                client["activity"] = "idle"
        return {"type": "presence_update", "online_count": len(clients), "clients": clients,
                "session_activity_supported": True}


presence_records = PresenceService()
